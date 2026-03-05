#!/usr/bin/env python3
"""
CI pipeline driver (Python): dotnet tests+coverage (soft gate), Godot self-check, encoding scan.

Usage (Windows):
  py -3 scripts/python/ci_pipeline.py all \
    --solution Game.sln --configuration Debug \
    --godot-bin "C:\\Godot\\Godot_v4.5.1-stable_mono_win64_console.exe" \
    --build-solutions

Exit codes:
  0  success (or only soft gates failed)
  1  hard failure (dotnet tests failed or self-check failed)
"""
import argparse
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys


def run_cmd(args, cwd=None, timeout=900_000):
    p = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='ignore')
    try:
        out, _ = p.communicate(timeout=timeout/1000.0)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        return 124, out
    return p.returncode, out


def _safe_int(raw, default):
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def resolve_dotnet_stage_timeout_ms(cli_value):
    """
    Resolve outer timeout for run_dotnet stage.
    Priority:
      1) CLI --dotnet-stage-timeout-ms
      2) env CI_DOTNET_STAGE_TIMEOUT_MS
      3) derived default = max(60m, DOTNET_TEST_TIMEOUT_MS + 5m)
    """
    dotnet_test_timeout_ms = max(60_000, _safe_int(os.environ.get('DOTNET_TEST_TIMEOUT_MS', '1800000'), 1_800_000))
    derived_default = max(3_600_000, dotnet_test_timeout_ms + 300_000)

    if cli_value is not None:
        candidate = _safe_int(cli_value, derived_default)
    else:
        env_value = os.environ.get('CI_DOTNET_STAGE_TIMEOUT_MS', '')
        candidate = _safe_int(env_value, derived_default) if str(env_value).strip() else derived_default

    # Clamp to [5m, 3h] to avoid accidental 0/negative and runaway values.
    return max(300_000, min(candidate, 10_800_000))


def read_json(path):
    try:
        with io.open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def run_env_evidence_preflight(root: str, godot_bin: str):
    """
    Generate deterministic environment evidence artifacts before unit tests.
    This keeps cold CI workspaces aligned with acceptance test expectations.
    """
    sc_dir = os.path.join(root, 'scripts', 'sc')
    if not os.path.isdir(sc_dir):
        return 1, {'status': 'fail', 'reason': f'missing scripts/sc: {sc_dir}'}

    added_path = False
    if sc_dir not in sys.path:
        sys.path.insert(0, sc_dir)
        added_path = True

    try:
        from _env_evidence_preflight import step_env_evidence_preflight
        from _util import ci_dir

        step = step_env_evidence_preflight(ci_dir('ci-pipeline-env-preflight'), godot_bin=godot_bin, task_id='1')
        details = dict(getattr(step, 'details', {}) or {})
        details.update(
            {
                'name': getattr(step, 'name', 'env-evidence-preflight'),
                'status': getattr(step, 'status', 'fail'),
                'rc': getattr(step, 'rc', 1),
                'log': getattr(step, 'log', None),
            }
        )
        return int(getattr(step, 'rc', 1)), details
    except Exception as exc:
        return 1, {'status': 'fail', 'reason': f'env preflight import/exec error: {exc}'}
    finally:
        if added_path:
            try:
                sys.path.remove(sc_dir)
            except ValueError:
                pass


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    ap_all = sub.add_parser('all')
    ap_all.add_argument('--solution', default='Game.sln')
    ap_all.add_argument('--configuration', default='Debug')
    ap_all.add_argument('--godot-bin', required=True)
    ap_all.add_argument('--project', default='project.godot')
    ap_all.add_argument('--build-solutions', action='store_true')
    ap_all.add_argument(
        '--dotnet-stage-timeout-ms',
        type=int,
        default=None,
        help='Outer timeout for run_dotnet stage in milliseconds. Default derives from DOTNET_TEST_TIMEOUT_MS and is at least 3600000.',
    )

    args = ap.parse_args()
    if args.cmd != 'all':
        print('Unsupported command')
        return 1

    root = os.getcwd()
    date = dt.date.today().strftime('%Y-%m-%d')
    ci_dir = os.path.join('logs', 'ci', date)
    os.makedirs(ci_dir, exist_ok=True)

    summary = {
        'manual_triplet_examples': {},
        'whitelist_expiry_warning': {},
        'preflight_env_evidence': {},
        'preflight_task1': {},
        'dotnet': {},
        'selfcheck': {},
        'encoding': {},
        'status': 'ok'
    }
    hard_fail = False

    # Keep preflight/test environment deterministic.
    os.environ['GODOT_BIN'] = args.godot_bin

    # 0) Enforce unified task-level entrypoint command policy (hard gate)
    rc0, out0 = run_cmd(
        [
            'py',
            '-3',
            'scripts/python/forbid_manual_sc_triplet_examples.py',
            '--root',
            '.',
            '--mode',
            'all',
            '--whitelist',
            'docs/workflows/unified-pipeline-command-whitelist.txt',
            '--whitelist-metadata',
            'require',
        ],
        cwd=root,
    )
    with io.open(os.path.join(ci_dir, 'forbid-manual-sc-triplet-examples.log'), 'w', encoding='utf-8') as f:
        f.write(out0)
    manual_sum = read_json(os.path.join('logs', 'ci', date, 'forbid-manual-sc-triplet-examples.json')) or {}
    summary['manual_triplet_examples'] = {
        'rc': rc0,
        'status': 'ok' if rc0 == 0 else 'fail',
        'hits_count': manual_sum.get('hits_count'),
        'scanned_files': manual_sum.get('scanned_files'),
        'mode': manual_sum.get('mode'),
    }
    if rc0 != 0:
        hard_fail = True

    # 0.5) Soft warning: whitelist expiry horizon.
    rcw, outw = run_cmd(
        [
            'py',
            '-3',
            'scripts/python/warn_whitelist_expiry.py',
            '--root',
            '.',
            '--whitelist',
            'docs/workflows/unified-pipeline-command-whitelist.txt',
        ],
        cwd=root,
    )
    with io.open(os.path.join(ci_dir, 'whitelist-expiry-warning.log'), 'w', encoding='utf-8') as f:
        f.write(outw)
    warn_sum = read_json(os.path.join('logs', 'ci', date, 'whitelist-expiry-warning.json')) or {}
    summary['whitelist_expiry_warning'] = {
        'rc': rcw,
        'status': warn_sum.get('status') or ('ok' if rcw == 0 else 'warn'),
        'expiring_soon_count': warn_sum.get('expiring_soon_count'),
        'expired_count': warn_sum.get('expired_count'),
        'warn_days': warn_sum.get('warn_days'),
    }

    # 1) Environment preflight artifacts (hard gate)
    preflight_rc, preflight_details = run_env_evidence_preflight(root, args.godot_bin)
    summary['preflight_env_evidence'] = preflight_details
    summary['preflight_task1'] = preflight_details
    if preflight_rc != 0:
        hard_fail = True

    # 2) Dotnet tests + coverage (soft gate on coverage)
    dotnet_stage_timeout_ms = resolve_dotnet_stage_timeout_ms(args.dotnet_stage_timeout_ms)
    rc, out = run_cmd(['py', '-3', 'scripts/python/run_dotnet.py',
                       '--solution', args.solution,
                       '--configuration', args.configuration], cwd=root, timeout=dotnet_stage_timeout_ms)
    with io.open(os.path.join(ci_dir, 'dotnet-run-dotnet-stdout.txt'), 'w', encoding='utf-8') as f:
        f.write(out)
    dotnet_sum = read_json(os.path.join('logs', 'unit', date, 'summary.json')) or {}
    dotnet_status = dotnet_sum.get('status')
    if rc == 124 and not dotnet_status:
        dotnet_status = 'timeout'
    timeout_reason = None
    if rc == 124:
        timeout_reason = 'ci_pipeline_dotnet_stage_timeout'
        tail = '\n'.join((out or '').splitlines()[-120:])
        with io.open(os.path.join(ci_dir, 'dotnet-timeout-tail.txt'), 'w', encoding='utf-8') as f:
            f.write(tail)
    summary['dotnet'] = {
        'rc': rc,
        'stage_timeout_ms': dotnet_stage_timeout_ms,
        'timed_out': rc == 124,
        'reason': timeout_reason,
        'line_pct': (dotnet_sum.get('coverage') or {}).get('line_pct'),
        'branch_pct': (dotnet_sum.get('coverage') or {}).get('branch_pct'),
        'status': dotnet_status,
        'test_attempts': dotnet_sum.get('test_attempts') or [],
        'failure_excerpt': dotnet_sum.get('failure_excerpt') or [],
    }
    # Persist dotnet detailed outputs into logs/ci for artifact-based diagnosis.
    try:
        unit_dir = os.path.join('logs', 'unit', date)
        for file_name in ('dotnet-test-output.txt', 'dotnet-restore.log', 'summary.json'):
            src = os.path.join(unit_dir, file_name)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(ci_dir, f'dotnet-{file_name}'))
        attempt_files = [name for name in os.listdir(unit_dir) if name.startswith('dotnet-test-output-attempt-')]
        for attempt_name in attempt_files:
            src = os.path.join(unit_dir, attempt_name)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(ci_dir, attempt_name))
    except Exception:
        pass
    if rc not in (0, 2) or summary['dotnet']['status'] == 'tests_failed':
        hard_fail = True

    # 3) Godot self-check (hard gate)
    # ensure autoload fixed (explicit project path)
    _ = run_cmd(['py', '-3', 'scripts/python/godot_selfcheck.py', 'fix-autoload', '--project', args.project], cwd=root)
    sc_args = ['py', '-3', 'scripts/python/godot_selfcheck.py', 'run', '--godot-bin', args.godot_bin, '--project', args.project]
    if args.build_solutions:
        sc_args.append('--build-solutions')
    rc2, out2 = run_cmd(sc_args, cwd=root, timeout=600_000)
    # persist raw stdout for diagnosis
    os.makedirs(os.path.join('logs', 'ci', date), exist_ok=True)
    with io.open(os.path.join('logs', 'ci', date, 'selfcheck-stdout.txt'), 'w', encoding='utf-8') as f:
        f.write(out2)
    sc_sum = read_json(os.path.join('logs', 'e2e', date, 'selfcheck-summary.json')) or {}
    # fallback: parse status from stdout if summary missing
    if not sc_sum:
        import re
        m = re.search(r"SELF_CHECK status=([a-z]+).*? out=([^\r\n]+)", out2)
        if m:
            sc_status = m.group(1)
            sc_out = m.group(2)
            sc_sum = {'status': sc_status, 'out': sc_out, 'note': 'parsed-from-stdout'}
    # as ultimate fallback, trust process rc (0==ok)
    # Copy Godot selfcheck raw console/stderr into ci logs if present
    try:
        e2e_dir = os.path.join('logs', 'e2e', date)
        ci_dir = os.path.join('logs', 'ci', date)
        cons = [p for p in os.listdir(e2e_dir) if p.startswith('godot-selfcheck-console-')]
        if cons:
            cons.sort()
            src = os.path.join(e2e_dir, cons[-1])
            with io.open(src, 'r', encoding='utf-8', errors='ignore') as rf, io.open(os.path.join(ci_dir, 'selfcheck-console.txt'), 'w', encoding='utf-8') as wf:
                wf.write(rf.read())
        errs = [p for p in os.listdir(e2e_dir) if p.startswith('godot-selfcheck-stderr-')]
        if errs:
            errs.sort()
            src = os.path.join(e2e_dir, errs[-1])
            with io.open(src, 'r', encoding='utf-8', errors='ignore') as rf, io.open(os.path.join(ci_dir, 'selfcheck-stderr.txt'), 'w', encoding='utf-8') as wf:
                wf.write(rf.read())
    except Exception:
        pass

    sc_ok = (sc_sum.get('status') == 'ok') or (rc2 == 0)
    summary['selfcheck'] = sc_sum or {'status': 'fail', 'note': 'no-summary'}
    if not sc_ok:
        hard_fail = True

    # 4) Encoding scan (soft gate)
    rc3, out3 = run_cmd(['py', '-3', 'scripts/python/check_encoding.py', '--since-today'], cwd=root)
    enc_sum = read_json(os.path.join('logs', 'ci', date, 'encoding', 'session-summary.json')) or {}
    summary['encoding'] = enc_sum

    summary['status'] = 'ok' if not hard_fail else 'fail'
    with io.open(os.path.join(ci_dir, 'ci-pipeline-summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(
        "CI_PIPELINE status={status} manual_examples={manual_examples} whitelist_expiry={whitelist_expiry} "
        "dotnet={dotnet} dotnet_rc={dotnet_rc} dotnet_timeout_ms={dotnet_timeout_ms} "
        "selfcheck={selfcheck} encoding_bad={encoding_bad}".format(
            status=summary['status'],
            manual_examples=summary['manual_triplet_examples'].get('status'),
            whitelist_expiry=summary['whitelist_expiry_warning'].get('status'),
            dotnet=summary['dotnet'].get('status'),
            dotnet_rc=summary['dotnet'].get('rc'),
            dotnet_timeout_ms=summary['dotnet'].get('stage_timeout_ms'),
            selfcheck=summary['selfcheck'].get('status'),
            encoding_bad=summary['encoding'].get('bad', 'n/a'),
        )
    )
    return 0 if not hard_fail else 1


if __name__ == '__main__':
    sys.exit(main())
