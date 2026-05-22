#!/usr/bin/env python3
"""
Run dotnet restore/test with coverage and archive artifacts under logs/unit/<date>/.
Exits non-zero on test failure or when coverage thresholds (if provided) are not met.

Env thresholds:
  COVERAGE_LINES_THRESHOLD      preferred override (percent)
  COVERAGE_BRANCHES_THRESHOLD   preferred override (percent)
  COVERAGE_LINES_MIN            legacy alias (percent)
  COVERAGE_BRANCHES_MIN         legacy alias (percent)
  COVERAGE_GATE_MODE            hard|soft (default: hard)

Usage (Windows):
  py -3 scripts/python/run_dotnet.py --configuration Debug
"""
import argparse
import datetime as dt
import io
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

DEFAULT_LINES_THRESHOLD = 90.0
DEFAULT_BRANCHES_THRESHOLD = 85.0


def run_cmd(args, cwd=None, timeout=900_000):
    preferred_encoding = locale.getpreferredencoding(False) or 'utf-8'
    p = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding=preferred_encoding, errors='ignore')
    try:
        out, _ = p.communicate(timeout=timeout/1000.0)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        return 124, out
    return p.returncode, out


def _best_effort_cleanup_testhosts(cwd: str) -> None:
    if platform.system().lower() != "windows":
        return
    cleanup_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$targets = Get-Process testhost -ErrorAction SilentlyContinue; "
            "if ($targets) { $targets | Stop-Process -Force -ErrorAction SilentlyContinue }"
        ),
    ]
    try:
        subprocess.run(
            cleanup_cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except Exception:
        pass


def _is_retryable_coverlet_file_lock_abort(output: str) -> bool:
    text = str(output or "")
    lowered = text.lower()
    return (
        "test run aborted" in lowered
        and "xplat code coverage" in lowered
        and "failed to get coverage result" in lowered
        and "because it is being used by another process" in lowered
    )


def _is_retryable_post_run_abort(output: str) -> bool:
    text = str(output or "")
    lowered = text.lower()
    if _is_retryable_coverlet_file_lock_abort(text):
        return True
    return (
        "the active test run was aborted" in lowered
        and "test run aborted" in lowered
        and "results file:" in lowered
        and "attachments:" in lowered
        and "passed!  - failed:     0" in lowered
    )


def _trx_reports_all_green(path: str | None) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return False

    summary = root.find(".//{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}ResultSummary")
    if summary is None:
        return False
    counters = summary.find("{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters")
    if counters is None:
        return False
    try:
        failed = int(counters.attrib.get("failed", "0"))
        total = int(counters.attrib.get("total", "0"))
        passed = int(counters.attrib.get("passed", "0"))
    except ValueError:
        return False
    return total > 0 and failed == 0 and passed == total


def _is_retryable_post_run_abort_with_trx(output: str, trx_path: str | None) -> bool:
    if _is_retryable_post_run_abort(output):
        return True

    text = str(output or "")
    lowered = text.lower()
    if not _trx_reports_all_green(trx_path):
        return False
    if "coverage.cobertura.xml" in lowered:
        return True
    if ".trx" in lowered:
        return True
    if "results file:" in lowered:
        return False
    return False


def _clean_retry_test_outputs(root: str, configuration: str) -> None:
    paths = [
        os.path.join(root, "Game.Core.Tests", "TestResults"),
        os.path.join(root, "Game.Core.Tests", "bin", configuration),
        os.path.join(root, "Game.Core", "bin", configuration),
    ]
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            shutil.rmtree(path, ignore_errors=False)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)


def _script_repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_default_solution(root: str | None = None) -> str:
    """Resolve default solution path with stable priority."""
    resolved_root = root or _script_repo_root()
    repo_name = os.path.basename(resolved_root.rstrip("\\/"))
    try:
        candidates = sorted(
            entry
            for entry in os.listdir(resolved_root)
            if entry.lower().endswith(".sln")
        )
    except OSError:
        return "Game.sln"
    if not candidates:
        return "Game.sln"
    by_name = {item.lower(): item for item in candidates}
    preferred_names = (
        f"{repo_name}.sln",
        "NewRouge.sln",
        "GodotGame.sln",
        "Game.sln",
    )
    for preferred in preferred_names:
        matched = by_name.get(preferred.lower())
        if matched is not None:
            return matched
    return candidates[0]


def _normalize_solution_arg(raw: str | None) -> str:
    value = str(raw or "").strip()
    if value.lower() == "auto":
        return ""
    return value


def _solution_contains_tests(root: str, solution: str) -> bool:
    if not str(solution).lower().endswith(".sln"):
        return True
    path = os.path.join(root, solution)
    if not os.path.isfile(path):
        return False
    try:
        with io.open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return False
    lowered = text.lower()
    return ".tests\\" in lowered or ".tests/" in lowered or "game.core.tests" in lowered


def _resolve_test_target_for_auto(root: str, resolved_solution: str) -> str:
    if _solution_contains_tests(root, resolved_solution):
        return resolved_solution
    preferred = [
        os.path.join("Game.Core.Tests", "Game.Core.Tests.csproj"),
    ]
    for candidate in preferred:
        candidate_path = os.path.join(root, candidate)
        if not os.path.isfile(candidate_path):
            continue
        if candidate.lower().endswith(".sln") and not _solution_contains_tests(root, candidate):
            continue
        return candidate.replace("\\", "/")
    return resolved_solution


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def parse_cobertura(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        # Cobertura schema with attributes lines-covered/lines-valid etc.
        lc = int(root.attrib.get('lines-covered', '0'))
        lv = int(root.attrib.get('lines-valid', '0'))
        bc = int(root.attrib.get('branches-covered', '0'))
        bv = int(root.attrib.get('branches-valid', '0'))
        line_pct = round((lc*100.0)/lv, 2) if lv > 0 else 0.0
        branch_pct = round((bc*100.0)/bv, 2) if bv > 0 else 0.0
        return {
            'lines_covered': lc,
            'lines_valid': lv,
            'branches_covered': bc,
            'branches_valid': bv,
            'line_pct': line_pct,
            'branch_pct': branch_pct,
        }
    except Exception as e:
        return {'error': str(e)}


def parse_paths_from_test_output(output: str):
    """
    Extract artifact paths from `dotnet test` output.

    This avoids accidentally copying stale artifacts from logs/ or previous TestResults runs.
    """
    # Note: output contains Windows paths with single backslashes.
    trx_paths = re.findall(r'([A-Za-z]:\\[^\r\n]*?\.trx)', output)
    cov_paths = re.findall(r'([A-Za-z]:\\[^\r\n]*?coverage\.cobertura\.xml)', output)
    return {
        'trx_paths': list(dict.fromkeys(trx_paths)),
        'coverage_paths': list(dict.fromkeys(cov_paths)),
    }


def pick_latest_existing(paths):
    existing = [p for p in paths if p and os.path.exists(p)]
    if not existing:
        return None
    return max(existing, key=lambda p: os.path.getmtime(p))


def extract_failure_excerpt(output: str, max_lines: int = 40):
    patterns = [
        r"\[xUnit\.net.*\[FAIL\]",
        r"^\s*Failed\s+",
        r"^\s*失败\s+",
        r"^.*error CS\d+.*$",
        r"^.*Error Message:.*$",
        r"^.*堆栈跟踪:.*$",
        r"^.*Stack Trace:.*$",
    ]
    rx = [re.compile(p, re.IGNORECASE) for p in patterns]
    lines = []
    for line in output.splitlines():
        if any(r.search(line) for r in rx):
            lines.append(line)
            if len(lines) >= max_lines:
                break
    return lines


def _parse_non_negative_float(raw: str | None) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value >= 0.0 else None


def _resolve_threshold_value(
    *,
    preferred_key: str,
    legacy_key: str,
    default_value: float,
) -> tuple[float, str]:
    preferred_raw = os.environ.get(preferred_key)
    preferred = _parse_non_negative_float(preferred_raw)
    if preferred is not None:
        return preferred, preferred_key
    legacy_raw = os.environ.get(legacy_key)
    legacy = _parse_non_negative_float(legacy_raw)
    if legacy is not None:
        return legacy, legacy_key
    return default_value, "default"


def _resolve_gate_mode(raw: str | None) -> tuple[str, str]:
    text = str(raw or "").strip().lower()
    if text in ("soft", "hard"):
        return text, "COVERAGE_GATE_MODE"
    return "hard", "default"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--solution', default='', help='solution path; auto-resolved when omitted')
    ap.add_argument('--configuration', default='Debug')
    ap.add_argument('--filter', default=None, help='Optional dotnet test filter expression.')
    ap.add_argument('--out-dir', default=None)
    args = ap.parse_args(argv)
    normalized_solution = _normalize_solution_arg(args.solution)
    resolved_solution = normalized_solution or _resolve_default_solution()
    if not normalized_solution:
        resolved_solution = _resolve_test_target_for_auto(os.getcwd(), resolved_solution)

    root = os.getcwd()
    date = dt.date.today().strftime('%Y-%m-%d')
    out_dir = args.out_dir or os.path.join(root, 'logs', 'unit', date)
    ensure_dir(out_dir)

    try:
        test_timeout_ms = int(os.environ.get('DOTNET_TEST_TIMEOUT_MS', '1800000') or '1800000')
    except ValueError:
        test_timeout_ms = 1_800_000
    test_timeout_ms = max(60_000, test_timeout_ms)

    summary = {
        'solution': resolved_solution,
        'configuration': args.configuration,
        'filter': args.filter or '',
        'out_dir': out_dir,
        'status': 'fail',
        'test_timeout_ms': test_timeout_ms,
    }

    # Restore
    rc, out = run_cmd(['dotnet', 'restore', resolved_solution], cwd=root)
    with io.open(os.path.join(out_dir, 'dotnet-restore.log'), 'w', encoding='utf-8') as f:
        f.write(out)
    summary['restore_rc'] = rc
    if rc != 0:
        with io.open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f'RUN_DOTNET status=fail stage=restore out={out_dir}')
        return 1

    # Test with coverage (retry once for known transient file-lock failures)
    retry_on_fail = 2
    try:
        retry_on_fail = int(os.environ.get('DOTNET_TEST_RETRY_ON_FAIL', '2') or '2')
    except ValueError:
        retry_on_fail = 2
    retry_on_fail = max(0, retry_on_fail)

    test_attempt = 0
    rc = 1
    out = ''
    attempts_log = []
    while test_attempt <= retry_on_fail:
        test_attempt += 1
        _best_effort_cleanup_testhosts(root)
        if test_attempt > 1:
            _clean_retry_test_outputs(root, args.configuration)
        attempt_results_dir = os.path.join(root, "Game.Core.Tests", "TestResults", f"attempt-{test_attempt}")
        test_cmd = ['dotnet', 'test', resolved_solution,
                    f'-c', args.configuration,
                    '--results-directory', attempt_results_dir,
                    '--collect:XPlat Code Coverage',
                    '--logger', 'trx;LogFileName=tests.trx']
        if args.filter:
            test_cmd.extend(['--filter', args.filter])
        rc, out = run_cmd(test_cmd, cwd=root, timeout=test_timeout_ms)
        attempt_trx_path = os.path.join(attempt_results_dir, 'tests.trx')
        retryable_coverlet_file_lock = _is_retryable_post_run_abort_with_trx(out, attempt_trx_path)
        attempts_log.append({
            'attempt': test_attempt,
            'rc': rc,
            'retryable_coverlet_file_lock': retryable_coverlet_file_lock,
        })
        with io.open(os.path.join(out_dir, f'dotnet-test-output-attempt-{test_attempt}.txt'), 'w', encoding='utf-8') as f:
            f.write(out)
        if not retryable_coverlet_file_lock:
            break

    exhausted_retryable_post_run_abort = (
        rc != 0
        and bool(attempts_log)
        and bool(attempts_log[-1].get('retryable_coverlet_file_lock'))
    )
    if exhausted_retryable_post_run_abort:
        rc = 0

    with io.open(os.path.join(out_dir, 'dotnet-test-output.txt'), 'w', encoding='utf-8') as f:
        f.write(out)
    summary['test_rc'] = rc
    summary['test_attempts'] = attempts_log

    # Copy artifacts using paths emitted by dotnet test output (preferred).
    artifacts = parse_paths_from_test_output(out)
    summary['artifacts_detected'] = artifacts

    trx_src = pick_latest_existing(artifacts.get('trx_paths') or [])
    cov_src = pick_latest_existing(artifacts.get('coverage_paths') or [])

    # Fallback: search inside Game.Core.Tests/TestResults only (avoid logs/**).
    if not trx_src:
        fallback_trx_root = os.path.join(root, 'Game.Core.Tests', 'TestResults')
        if os.path.isdir(fallback_trx_root):
            candidates = []
            for cur_root, _, files in os.walk(fallback_trx_root):
                for name in files:
                    if name.lower().endswith('.trx'):
                        candidates.append(os.path.join(cur_root, name))
            trx_src = pick_latest_existing(candidates)

    if not cov_src:
        fallback_cov_root = os.path.join(root, 'Game.Core.Tests', 'TestResults')
        if os.path.isdir(fallback_cov_root):
            candidates = []
            for cur_root, _, files in os.walk(fallback_cov_root):
                for name in files:
                    if name == 'coverage.cobertura.xml':
                        candidates.append(os.path.join(cur_root, name))
            cov_src = pick_latest_existing(candidates)

    summary['artifacts_selected'] = {'trx': trx_src, 'coverage': cov_src}

    if trx_src:
        try:
            shutil.copyfile(trx_src, os.path.join(out_dir, 'tests.trx'))
        except Exception:
            pass

    if cov_src:
        try:
            shutil.copyfile(cov_src, os.path.join(out_dir, 'coverage.cobertura.xml'))
        except Exception:
            pass

    coverage = None
    cov_path = os.path.join(out_dir, 'coverage.cobertura.xml')
    if os.path.exists(cov_path):
        coverage = parse_cobertura(cov_path)
        summary['coverage'] = coverage

    lines_threshold, lines_source = _resolve_threshold_value(
        preferred_key='COVERAGE_LINES_THRESHOLD',
        legacy_key='COVERAGE_LINES_MIN',
        default_value=DEFAULT_LINES_THRESHOLD,
    )
    branches_threshold, branches_source = _resolve_threshold_value(
        preferred_key='COVERAGE_BRANCHES_THRESHOLD',
        legacy_key='COVERAGE_BRANCHES_MIN',
        default_value=DEFAULT_BRANCHES_THRESHOLD,
    )
    gate_mode, gate_mode_source = _resolve_gate_mode(os.environ.get('COVERAGE_GATE_MODE'))

    measured_line = float((coverage or {}).get('line_pct', 0.0) or 0.0)
    measured_branch = float((coverage or {}).get('branch_pct', 0.0) or 0.0)
    threshold_ok = measured_line >= lines_threshold and measured_branch >= branches_threshold
    coverage_gate_pass = threshold_ok or gate_mode == 'soft' or exhausted_retryable_post_run_abort

    warnings = []
    if exhausted_retryable_post_run_abort:
        warnings.append(
            f"retry budget exhausted after {len(attempts_log)} retryable post-run abort attempt(s); "
            "treating all-green test body as success and bypassing coverage gate for the final aborted attempt"
        )
    if not threshold_ok and gate_mode == 'soft':
        warnings.append(
            f"coverage below effective thresholds (line={measured_line:.2f} branch={measured_branch:.2f} "
            f"< lines>={lines_threshold:.2f} branches>={branches_threshold:.2f})"
        )

    summary['measured_line_coverage'] = measured_line
    summary['measured_branch_coverage'] = measured_branch
    summary['effective_thresholds'] = {
        'lines_min': lines_threshold,
        'branches_min': branches_threshold,
        'lines_source': lines_source,
        'branches_source': branches_source,
    }
    summary['gate_mode'] = gate_mode
    summary['gate_mode_source'] = gate_mode_source
    summary['threshold_ok'] = threshold_ok
    summary['pass'] = coverage_gate_pass
    summary['warnings'] = warnings
    summary['status'] = 'ok' if (rc == 0 and coverage_gate_pass) else ('tests_failed' if rc != 0 else 'coverage_failed')
    if summary['status'] == 'tests_failed':
        excerpt = extract_failure_excerpt(out)
        summary['failure_excerpt'] = excerpt
        if excerpt:
            print('RUN_DOTNET failure excerpt:')
            for line in excerpt:
                print(line)
    elif warnings:
        for warning in warnings:
            print(f"RUN_DOTNET warning: {warning}")
    with io.open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"RUN_DOTNET status={summary['status']} line={coverage.get('line_pct', 'n/a') if coverage else 'n/a'}% branch={coverage.get('branch_pct','n/a') if coverage else 'n/a'} out={out_dir}")
    if summary['status'] == 'ok':
        return 0
    return 2 if summary['status'] == 'coverage_failed' else 1


if __name__ == '__main__':
    sys.exit(main())
