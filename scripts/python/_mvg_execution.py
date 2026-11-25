"""Bounded child execution and positive test-report evidence for MVG runs."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def run_child(command: list[str], root: Path, log: Path, timeout: float, env: dict | None = None) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as output:
        try:
            process = subprocess.Popen(command, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                       env=env, start_new_session=os.name != 'nt')
        except OSError as exc:
            output.write(str(exc))
            return 127
        try:
            return process.wait(timeout=max(0.1, timeout))
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=15)
            return 124


def read_test_evidence(directory: Path, kind: str, expected: str, min_tests: int) -> dict:
    result = {'passed': False, 'tests': 0, 'failed': 0, 'skipped': 0, 'reports': [],
              'failure_messages': [], 'reason': ''}
    files = list(directory.rglob('*.trx' if kind == 'dotnet' else 'results.xml'))
    if not files:
        return {**result, 'reason': 'missing-test-report'}
    try:
        seen_identities: set[str] = set()
        for path in files:
            tree = ET.parse(path).getroot()
            result['reports'].append(str(path))
            local_cases = [node for node in tree.iter()
                           if node.tag.split('}')[-1] == ('UnitTestResult' if kind == 'dotnet' else 'testcase')]
            identities = [
                case.get('testName', '') if kind == 'dotnet'
                else (case.get('classname', expected) + ':' + case.get('name', ''))
                for case in local_cases
            ]
            if len(identities) != len(set(identities)) or seen_identities.intersection(identities):
                return {**result, 'reason': 'duplicate-test-results'}
            seen_identities.update(identities)
            for node in tree.iter():
                tag = node.tag.split('}')[-1]
                if tag in {'testsuite', 'testsuites'} and 'tests' in node.attrib:
                    if int(node.get('tests')) != len(list(node.iter('testcase'))):
                        return {**result, 'reason': 'inconsistent-test-count'}
                if tag == 'Counters':
                    counts = {'total': len(local_cases),
                              'passed': sum(c.get('outcome') == 'Passed' for c in local_cases),
                              'failed': sum(c.get('outcome') == 'Failed' for c in local_cases)}
                    if any(key in node.attrib and int(node.get(key)) != count for key, count in counts.items()):
                        return {**result, 'reason': 'inconsistent-test-count'}
            # Suite/setup errors can exist without a failed testcase. Never lose them.
            for node in tree.iter():
                tag = node.tag.split('}')[-1]
                if tag in {'testsuites', 'testsuite'}:
                    if any(int(node.get(key, '0')) > 0 for key in ('errors', 'failures', 'skipped')):
                        result['reason'] = 'reported-suite-failure'
                if tag == 'ResultSummary' and node.get('outcome') not in {None, 'Completed', 'Passed'}:
                    result['reason'] = 'reported-suite-failure'
            if kind == 'dotnet':
                cases = [node for node in tree.iter() if node.tag.split('}')[-1] == 'UnitTestResult']
                for case in cases:
                    class_name = case.get('testName', '').split('(', 1)[0].rsplit('.', 1)[0]
                    if expected != class_name:
                        return {**result, 'reason': 'unexpected-test-selection'}
                    outcome = case.get('outcome', '')
                    result['tests'] += 1
                    result['failed'] += outcome == 'Failed'
                    result['skipped'] += outcome not in {'Passed', 'Failed'}
            else:
                for suite in tree.iter('testsuite'):
                    for case in suite.findall('testcase'):
                        if (suite.get('name', '') != expected or
                                case.get('classname', expected) != expected):
                            return {**result, 'reason': 'unexpected-test-selection'}
                        result['tests'] += 1
                        result['failed'] += case.find('failure') is not None or case.find('error') is not None
                        for failure in case.findall('failure'):
                            result['failure_messages'].append(''.join(failure.itertext()))
                        result['skipped'] += case.find('skipped') is not None
        result['passed'] = (result['tests'] >= min_tests and not result['failed']
                            and not result['skipped'] and not result['reason'])
        result['reason'] = ('verified' if result['passed'] else
                            'failed-skipped-or-empty-tests' if result['failed'] or result['skipped']
                            else result['reason'] or 'failed-skipped-or-empty-tests')
    except (ET.ParseError, OSError, ValueError) as exc:
        result['reason'] = f'invalid-test-report:{exc}'
    return result


def execute_test(root: Path, test: dict, out: Path, godot_bin: str, deadline: float,
                 env: dict | None = None, *, prewarm: bool = True, no_build: bool = False,
                 dotnet_bin: str = 'dotnet', protocol_fixture: bool = False) -> dict:
    if (out / 'command.json').exists() or (out / 'console.log').exists():
        raise FileExistsError(f'Test output directory already contains execution artifacts: {out}')
    out.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    started_mono = time.monotonic()
    if test['kind'] == 'dotnet':
        dotnet_resolved = (shutil.which(dotnet_bin)
                           if (dotnet_bin and not Path(dotnet_bin).is_file()) else dotnet_bin) or dotnet_bin
        dotnet_low = str(dotnet_resolved).lower()
        if dotnet_low.endswith('.py'):
            dotnet_cmd = [sys.executable, '-B', str(dotnet_resolved)]
        elif dotnet_low.endswith(('.bat', '.cmd')):
            dotnet_cmd = ['cmd', '/c', str(dotnet_resolved)]
        elif dotnet_low.endswith('.ps1'):
            dotnet_cmd = ['pwsh', '-NoProfile', '-File', str(dotnet_resolved)]
        else:
            dotnet_cmd = [dotnet_bin]
        command = [*dotnet_cmd, 'test', 'Game.Core.Tests/Game.Core.Tests.csproj', '--configuration', 'Debug']
        if no_build:
            command.append('--no-build')
        command.extend(['--filter', 'FullyQualifiedName~' + test['selector'],
                        '--logger', 'trx;LogFileName=results.trx', '--results-directory', str(out)])
        expected = test['selector']
        report_dir = out
    else:
        # run_gdunit also copies project reports. Archive prior reports to prevent stale reuse.
        previous = root / 'Tests.Godot/reports'
        if previous.exists():
            previous.rename(out / 'previous-project-reports')
        report = out / 'current'
        godot_resolved = (shutil.which(godot_bin)
                          if (godot_bin and not Path(godot_bin).is_file()) else godot_bin) or godot_bin
        godot_low = str(godot_resolved).lower()
        if not godot_bin:
            command = []
        elif godot_low.endswith('.py'):
            command = [sys.executable, '-B', str(godot_resolved),
                       '--project', 'Tests.Godot', '--add', test['path'].removeprefix('Tests.Godot/'),
                       '--timeout-sec', str(max(1, int(deadline - time.monotonic()))), '--rd', str(report)]
            if prewarm:
                command.append('--prewarm')
        elif godot_low.endswith(('.bat', '.cmd')):
            command = ['cmd', '/c', str(godot_resolved),
                       '--project', 'Tests.Godot', '--add', test['path'].removeprefix('Tests.Godot/'),
                       '--timeout-sec', str(max(1, int(deadline - time.monotonic()))), '--rd', str(report)]
            if prewarm:
                command.append('--prewarm')
        elif godot_low.endswith('.ps1'):
            command = ['pwsh', '-NoProfile', '-File', str(godot_resolved),
                       '--project', 'Tests.Godot', '--add', test['path'].removeprefix('Tests.Godot/'),
                       '--timeout-sec', str(max(1, int(deadline - time.monotonic()))), '--rd', str(report)]
            if prewarm:
                command.append('--prewarm')
        else:
            command = [sys.executable, 'scripts/python/run_gdunit.py', '--godot-bin', godot_bin,
                       '--project', 'Tests.Godot', '--add', test['path'].removeprefix('Tests.Godot/'),
                       '--timeout-sec', str(max(1, int(deadline - time.monotonic()))), '--rd', str(report)]
            if prewarm:
                command.append('--prewarm')
        expected = Path(test['path']).stem
        report_dir = out / 'current'
    if command:
        rc = run_child(command, root, out / 'console.log', deadline - time.monotonic(), env)
    else:
        (out / 'console.log').write_text('Godot binary not provided\n', encoding='utf-8')
        rc = 127
    evidence = read_test_evidence(report_dir, test['kind'], expected, test['min_tests'])
    finished_at = datetime.now(timezone.utc).isoformat()
    elapsed_seconds = round(max(0.0, time.monotonic() - started_mono), 4)
    command_record = out / 'command.json'
    command_payload = {
        'id': test['id'],
        'kind': test['kind'],
        'evidence_level': test.get('evidence_level', ''),
        'expected': expected,
        'min_tests': test.get('min_tests', 1),
        'cwd': str(root),
        'command': command,
        'no_build': bool(no_build) if test['kind'] == 'dotnet' else False,
        'prewarm': bool(prewarm) if test['kind'] == 'gdunit' else False,
        'exit_code': rc,
        'protocol_fixture': bool(protocol_fixture),
        'started_at': started_at,
        'finished_at': finished_at,
        'elapsed_seconds': elapsed_seconds,
        'log_path': str(out / 'console.log'),
        'report_paths': list(evidence.get('reports', [])),
    }
    command_record.write_text(json.dumps(command_payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'id': test['id'], 'evidence_level': test['evidence_level'], 'command': command,
            'command_record': str(command_record),
            'started_at': started_at, 'finished_at': finished_at, 'elapsed_seconds': elapsed_seconds,
            'exit_code': rc, 'status': 'passed' if rc == 0 and evidence['passed'] else 'failed',
            'evidence': evidence, 'log': str(out / 'console.log')}
