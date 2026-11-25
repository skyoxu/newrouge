#!/usr/bin/env python3
"""Plan, recommend, or execute MVG integration tests against an isolated snapshot."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import _b_route_evidence_reuse as evidence_reuse
import _b_route_inventory as inventory
from _mvg_manifest import manifest_sha256, read_manifest, recommend, validate_manifest
from _mvg_execution import execute_test
from _project_health_runtime_snapshot import prepare_snapshot

DEFAULT_MANIFEST = 'docs/testing/mvg/m1-critical.json'
_WRAPPER_SUFFIXES = ('.py', '.bat', '.cmd', '.ps1', '.sh')


def _is_script_wrapper_bin(bin_path: str) -> bool:
    if not bin_path or not bin_path.strip():
        return False
    raw = bin_path.strip()
    if raw.lower().endswith(_WRAPPER_SUFFIXES):
        return True
    resolved = shutil.which(raw) if not Path(raw).is_file() else raw
    return bool(resolved and str(resolved).lower().endswith(_WRAPPER_SUFFIXES))


def _check_root_no_reparse(raw_root: Path) -> Path:
    abs_root = raw_root.absolute()
    for ancestor in reversed((abs_root, *abs_root.parents)):
        inventory.no_reparse(ancestor)
    return abs_root.resolve()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def git(root: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                          timeout=30).stdout.decode('utf-8').strip()


def changed_paths(root: Path, base: str, revision: str = 'HEAD', *, workspace: bool = True) -> tuple[list[str], str]:
    try:
        paths = set()
        if base:
            resolved = git(root, 'rev-parse', '--verify', base + '^{commit}')
            paths.update(git(root, 'diff', '--name-only', '--no-renames', '-z', resolved, revision).split('\0'))
        if workspace:
            paths.update(git(root, 'diff', '--name-only', '--no-renames', '-z', revision).split('\0'))
            paths.update(git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0'))
        return sorted(paths - {''}), '' if paths - {''} else 'No changed paths; absence is not proof of no impact'
    except (subprocess.SubprocessError, OSError) as exc:
        return [], 'Git change range unavailable: ' + str(exc)


def register_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--root', default=None, help='Optional repository root override')
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST)
    parser.add_argument('--mode', choices=['plan', 'recommend', 'run'], default='plan')
    parser.add_argument('--snapshot', choices=['workspace', 'commit'], default='workspace')
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--base', default='', help='Optional comparison base; recommendations never exclude tests')
    parser.add_argument('--godot-bin', default=os.environ.get('GODOT_BIN', ''))
    parser.add_argument('--dotnet-bin', default=os.environ.get('DOTNET_BIN', 'dotnet'),
                        help='Dotnet executable or controlled protocol fixture wrapper')
    parser.add_argument('--timeout-sec', type=int, default=900, help='Global runtime budget')
    parser.add_argument('--challenge-input', action='store_true', help='After baseline passes, prove disconnected UI is detected')
    parser.add_argument('--verification-scope', default='',
                        help='Optional repo-relative path to sealed Story 4.2 VerificationScope JSON')
    parser.add_argument('--execution-strategy', choices=['scoped', 'conservative_superset'], default='scoped',
                        help='Execution scope strategy when --verification-scope is supplied')
    parser.add_argument('--protocol-fixture', action='store_true',
                        help='Explicitly mark runner binary as protocol fixture (never claims real Godot runtime_verified)')
    parser.add_argument('--stop-on-deterministic-failure', dest='stop_on_deterministic_failure',
                        action='store_true', default=True,
                        help='Stop before launching downstream GdUnit4 suites after a deterministic prerequisite fails')
    parser.add_argument('--no-stop-on-deterministic-failure', dest='stop_on_deterministic_failure',
                        action='store_false',
                        help='Continue launching downstream GdUnit4 suites even if a deterministic prerequisite failed')
    parser.add_argument('--reuse-evidence-from', action='append', default=[],
                        help='Optional repo-relative prior MVG run directory or coverage-receipt.json for same-snapshot evidence reuse (repeatable)')
    parser.add_argument('--reuse-build-from', default=None,
                        help='Optional repo-relative prior MVG run directory for identity-verified build/prewarm artifact reuse')
    parser.add_argument('--events-log', default=None,
                        help='Optional repo-relative JSONL path under logs/ for deduplicated execution and reuse events')


def run(args: argparse.Namespace, root: Path | None = None) -> int:
    if root is None and getattr(args, 'root', None):
        root = _check_root_no_reparse(Path(args.root))
    else:
        root = _check_root_no_reparse(root or Path(__file__).absolute().parents[2])
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = root / 'logs/ci/mvg-acceptance' / run_id
    out.mkdir(parents=True)
    scope_arg = str(getattr(args, 'verification_scope', '') or '').strip()
    if scope_arg:
        from _b_route_scope_runner import run_scoped_mvg
        exit_code, summary, _receipt = run_scoped_mvg(
            root=root,
            out=out,
            run_id=run_id,
            verification_scope_arg=scope_arg,
            manifest_arg=args.manifest,
            mode=args.mode,
            snapshot_mode=args.snapshot,
            revision_arg=args.revision,
            base_arg=args.base,
            godot_bin=args.godot_bin,
            dotnet_bin=getattr(args, 'dotnet_bin', os.environ.get('DOTNET_BIN', 'dotnet')),
            timeout_sec=args.timeout_sec,
            challenge_input=bool(args.challenge_input),
            execution_strategy=getattr(args, 'execution_strategy', 'scoped'),
            protocol_fixture=bool(getattr(args, 'protocol_fixture', False)),
            stop_on_deterministic_failure=bool(getattr(args, 'stop_on_deterministic_failure', True)),
            reuse_evidence_from=list(getattr(args, 'reuse_evidence_from', None) or []),
            reuse_build_from=getattr(args, 'reuse_build_from', None),
            events_log=getattr(args, 'events_log', None),
        )
        write_json(out / 'summary.json', summary)
        print(json.dumps({
            'status': summary['status'],
            'runtime_verified': summary['runtime_verified'],
            'automated_scope_passed': summary['automated_scope_passed'],
            'scope_id': summary.get('scope_id'),
            'receipt_id': summary.get('receipt_id'),
            'summary': str(out / 'summary.json'),
            'coverage_receipt': summary.get('coverage_receipt_path', ''),
            'reason': summary.get('reason', ''),
        }))
        return exit_code
    summary = {'schema_version': 'newrouge.mvg-acceptance.v1', 'run_id': run_id,
               'mode': args.mode, 'status': 'blocked', 'runtime_verified': False, 'steps': [],
               'authorizes_task_status_write': False}
    exit_code = 1
    try:
        if args.timeout_sec < 1:
            raise ValueError('timeout-sec must be positive')
        has_reuse_flags = (
            bool(getattr(args, 'reuse_evidence_from', None))
            or getattr(args, 'reuse_build_from', None) is not None
            or getattr(args, 'events_log', None) is not None
        )
        if has_reuse_flags:
            raise ValueError('--reuse-evidence-from, --reuse-build-from, and --events-log require --verification-scope')
        revision = git(root, 'rev-parse', '--verify', args.revision + '^{commit}')
        summary.update(base_commit=revision, workspace_dirty=bool(git(root, 'status', '--porcelain')))
        deadline = time.monotonic() + args.timeout_sec
        execution_root = root
        if args.mode == 'run' or args.snapshot == 'commit':
            execution_root = out / 'snapshot'
            snapshot = prepare_snapshot(root, execution_root, revision,
                                        'main' if args.snapshot == 'commit' else 'workspace', deadline)
            summary['source_revision'] = snapshot['source_revision']
            summary['snapshot_digest'] = snapshot['snapshot_digest']
            summary['input_manifest'] = str(out / 'input-manifest.json')
        manifest_path = inventory.safe_input(execution_root, args.manifest, allow_logs=False)
        manifest_sha = manifest_sha256(manifest_path.read_bytes())
        doc = read_manifest(execution_root, args.manifest)
        errors = validate_manifest(execution_root, doc, executable=args.mode == 'run')
        summary.update(
            mvg_id=doc.get('mvg_id'),
            manifest=args.manifest,
            manifest_sha256=manifest_sha,
            baseline_lineage=doc.get('baseline_lineage'),
            coverage=doc.get('coverage', {}),
            validation_errors=errors,
        )
        if errors:
            raise ValueError('; '.join(errors))
        comparison_revision = revision if args.snapshot == 'commit' else git(root, 'rev-parse', 'HEAD')
        paths, unknown = changed_paths(root, args.base, comparison_revision,
                                       workspace=args.snapshot == 'workspace')
        summary['recommendation'] = recommend(doc, paths, unknown_reason=unknown)
        summary['recommendation']['comparison_target'] = (summary.get('source_revision', 'workspace')
                                                          if args.snapshot == 'workspace' else revision)
        summary['recommendation']['includes_working_changes'] = args.snapshot == 'workspace'
        summary['required_tests'] = [test['id'] for test in doc['tests']]
        if args.mode != 'run':
            summary['status'] = 'planned' if args.mode == 'plan' else 'recommended'
            exit_code = 0
        else:
            dotnet_bin = getattr(args, 'dotnet_bin', os.environ.get('DOTNET_BIN', 'dotnet'))
            explicit_fixture = bool(getattr(args, 'protocol_fixture', False))
            protocol_fixture_only = bool(
                explicit_fixture
                or _is_script_wrapper_bin(args.godot_bin)
                or _is_script_wrapper_bin(dotnet_bin)
            )
            summary['protocol_fixture_only'] = protocol_fixture_only
            base_env = dict(os.environ)
            base_env['GDUNIT_STRICT_EXIT_CODE'] = '1'
            base_env.pop('MVG_INPUT_CHALLENGE', None)
            pre_snapshot_hashes = evidence_reuse.capture_snapshot_file_hashes(execution_root)
            summary['state_isolation'] = {
                'per_test_dirs_isolated': True,
                'pollution_detected': False,
                'polluted_tests': [],
                'checks': [],
            }
            godot_ready = False
            for test in doc['tests']:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Global runtime budget exhausted')
                step_out = out / test['id']
                step_iso = out / '_isolated' / test['id']
                step_env = evidence_reuse.prepare_isolated_test_env(base_env, step_iso)
                exec_kwargs = {'prewarm': not godot_ready}
                if protocol_fixture_only or dotnet_bin != 'dotnet':
                    exec_kwargs['dotnet_bin'] = dotnet_bin
                    exec_kwargs['protocol_fixture'] = protocol_fixture_only
                result = dict(execute_test(execution_root, test, step_out, args.godot_bin,
                                           deadline, step_env, **exec_kwargs))
                iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, step_iso)
                summary['state_isolation']['checks'].append({'test_id': test['id'], **iso})
                result['state_isolation'] = iso
                if iso['pollution_detected']:
                    summary['state_isolation']['pollution_detected'] = True
                    summary['state_isolation']['polluted_tests'].append(test['id'])
                    result['status'] = 'failed'
                    summary['steps'].append(result)
                    raise RuntimeError('Mutable snapshot state pollution detected: ' + test['id'])
                summary['steps'].append(result)
                if result['status'] != 'passed':
                    raise RuntimeError('Required test failed or is unverified: ' + test['id'])
                if test['kind'] == 'gdunit':
                    godot_ready = True
            if args.challenge_input:
                targets = [test for test in doc['tests'] if test.get('challenge') == 'disconnect-reward-input']
                if not targets:
                    raise ValueError('Manifest has no input challenge target')
                summary['challenges'] = []
                for test in targets:
                    step_out = out / ('challenge-' + test['id'])
                    step_iso = out / '_isolated' / ('challenge-' + test['id'])
                    challenge_env = evidence_reuse.prepare_isolated_test_env(base_env, step_iso)
                    challenge_env['MVG_INPUT_CHALLENGE'] = 'disconnect-reward-input'
                    exec_kwargs = {'prewarm': not godot_ready}
                    if protocol_fixture_only or dotnet_bin != 'dotnet':
                        exec_kwargs['dotnet_bin'] = dotnet_bin
                        exec_kwargs['protocol_fixture'] = protocol_fixture_only
                    result = dict(execute_test(execution_root, test, step_out,
                                               args.godot_bin, deadline, challenge_env, **exec_kwargs))
                    c_iso = evidence_reuse.verify_post_test_isolation(execution_root, pre_snapshot_hashes, step_iso)
                    summary['state_isolation']['checks'].append({'test_id': 'challenge-' + test['id'], **c_iso})
                    result['state_isolation'] = c_iso
                    if c_iso['pollution_detected']:
                        summary['state_isolation']['pollution_detected'] = True
                        summary['state_isolation']['polluted_tests'].append('challenge-' + test['id'])
                        result['defect_detected'] = False
                        summary['challenges'].append(result)
                        raise RuntimeError('Mutable snapshot state pollution detected: challenge-' + test['id'])
                    # A crash, missing runtime or compilation error is NOT a detected defect.
                    detected = (result['exit_code'] not in {0, 124, 127}
                                and result['evidence']['failed'] > 0
                                and result['evidence']['skipped'] == 0
                                and any('MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES' in message
                                        for message in result['evidence']['failure_messages'])
                                and result['evidence']['reason'] == 'failed-skipped-or-empty-tests')
                    result['defect_detected'] = detected
                    summary['challenges'].append(result)
                    if not detected:
                        raise RuntimeError('Disconnected input was not demonstrated by a test assertion')
            if protocol_fixture_only:
                summary.update(status='passed_protocol_fixture_only', runtime_verified=False,
                               protocol_fixture_only=True)
            else:
                summary.update(status='passed', runtime_verified=True, protocol_fixture_only=False)
            exit_code = 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
        summary['reason'] = str(exc)
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(out / 'summary.json', summary)
        print(json.dumps({'status': summary['status'], 'runtime_verified': summary['runtime_verified'],
                          'summary': str(out / 'summary.json'), 'reason': summary.get('reason', '')}))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    register_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
