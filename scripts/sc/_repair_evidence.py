"""Build actionable guidance from the failed step's existing producer artifacts."""
from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


_SOURCE_REF = re.compile(
    r'(?:Game[.]Core(?:[.]Tests)?|Game[.]Godot(?:[.]Tests)?|Tests[.]Godot|scripts|docs|Scenes|Assets|[.]taskmaster)/'
    r'[^\r\n\"<>`]+?[.](?:csproj|cs|gd|py|md|json|tscn|tres|sln)\b'
)


def _json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _file(raw: Any, *, root: Path, base: Path, snapshot_first: bool = True) -> Path | None:
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        path = Path(text)
        direct = path if path.is_absolute() else root / path
        candidates = [base / path.name, direct, base / path] if snapshot_first else [direct]
        return next((item for item in candidates if item.is_file()), None)
    except (OSError, ValueError):
        return None


def _matches(payload: dict[str, Any], *, task_id: str, run_id: str) -> bool:
    return all(not payload.get(key) or not expected or str(payload[key]).strip() == expected
               for key, expected in [('task_id', task_id), ('run_id', run_id)])


def _source_files(values: list[str]) -> list[str]:
    paths: list[str] = []
    for value in values:
        text = value.replace('\\', '/')
        paths.extend(match.group(0) for match in _SOURCE_REF.finditer(text))
        for name in ['tasks.json', 'tasks_back.json', 'tasks_gameplay.json']:
            if name in text:
                paths.append(f'.taskmaster/tasks/{name}')
    return list(dict.fromkeys(path for path in paths if '/../' not in path))


def _cmd(step: dict[str, Any]) -> list[str]:
    value = step.get('cmd')
    return [str(token) for token in value] if isinstance(value, list) else []


def _recommendation(rec_id: str, title: str, why: str, actions: list[str], files: list[str], cmd: list[str]) -> dict[str, Any]:
    return {
        'id': rec_id, 'title': title, 'why': why, 'actions': list(dict.fromkeys(actions)),
        'files': list(dict.fromkeys(files)), 'commands': [subprocess.list2cmdline(cmd)] if cmd else [],
    }


def _trx_recommendations(check: dict[str, Any], *, root: Path, summary_path: Path, run_id: str, fallback_cmd: list[str]) -> list[dict[str, Any]]:
    raw_dir = str(check.get('artifacts_dir') or '').strip()
    if not raw_dir or not run_id:
        return []
    directory = Path(raw_dir)
    if not directory.is_absolute():
        directory = root / directory
    try:
        if (directory / 'run_id.txt').read_text(encoding='utf-8').strip() != run_id:
            return []
        unit_summary = _json(directory / 'summary.json')
        if unit_summary.get('restore_rc') != 0 or 'test_rc' not in unit_summary:
            return []
        trx = directory / 'tests.trx'
        if trx.stat().st_size > 8 * 1024 * 1024:
            return []
        report = ET.parse(trx).getroot()
    except (OSError, UnicodeError, ValueError, ET.ParseError):
        return []
    definitions = {node.get('id'): node for node in report.iter() if node.tag.rsplit('}', 1)[-1] == 'UnitTest'}
    recommendations: list[dict[str, Any]] = []
    for index, result in enumerate(report.iter()):
        if result.tag.rsplit('}', 1)[-1] != 'UnitTestResult' or result.get('outcome', '').lower() != 'failed':
            continue
        name = result.get('testName') or result.get('testId') or 'unnamed test'
        messages = [node.text.strip() for node in result.iter() if node.text and node.tag.rsplit('}', 1)[-1] in {'Message', 'StackTrace'}]
        cmd = _cmd(check) or fallback_cmd
        definition = definitions.get(result.get('testId'))
        method = next((node for node in definition.iter() if node.tag.rsplit('}', 1)[-1] == 'TestMethod'), None) if definition is not None else None
        if method is not None and method.get('className') and method.get('name') and _cmd(check):
            narrowed: list[str] = []
            iterator = iter(cmd)
            for token in iterator:
                if token == '--filter':
                    next(iterator, None)
                else:
                    narrowed.append(token)
            cmd = narrowed + ['--filter', f"FullyQualifiedName={method.get('className')}.{method.get('name')}"]
        recommendations.append(_recommendation(
            f'sc-test-failed-test-{index}', f'Fix failed test: {name}', 'The bound TRX result records a failed unit test.',
            messages or ['Repair this test failure before resuming the pipeline.'],
            [str(summary_path), str(trx)] + _source_files(messages), cmd,
        ))
    return recommendations


def _errors(payload: Any) -> list[str]:
    errors: list[str] = []
    if isinstance(payload, list):
        for value in payload:
            errors.extend(_errors(value))
    elif isinstance(payload, dict):
        if str(payload.get('status') or '').lower() in {'ok', 'passed', 'skipped'}:
            return []
        for key, value in payload.items():
            if key in {'error', 'errors'}:
                if isinstance(value, str) and value.strip():
                    errors.append(value.strip())
                elif isinstance(value, list):
                    errors.extend(str(item).strip() for item in value if isinstance(item, str) and item.strip())
            elif key in {'missing_refs', 'missing_contracts', 'missing_overlays', 'missing_adrs'} and isinstance(value, list):
                errors.extend(f'{key}: {item}' for item in value if isinstance(item, str))
            if key != 'warnings' and isinstance(value, (dict, list)):
                errors.extend(_errors(value))
    return list(dict.fromkeys(errors))


def _check_recommendation(check: dict[str, Any], *, root: Path, summary_path: Path, task_id: str, run_id: str, fallback_cmd: list[str]) -> dict[str, Any]:
    name = str(check.get('name') or 'unknown')
    files = [str(summary_path)]
    errors = _errors(check.get('details'))
    cmd = _cmd(check)
    raw_report = str(check.get('summary_file') or '')
    if not raw_report:
        raw_report = next((cmd[index + 1] for index, token in enumerate(cmd[:-1]) if token in {'--out', '--out-json'}), '')
    report = _file(raw_report, root=root, base=summary_path.parent)
    if report is not None:
        payload = _json(report)
        if _matches(payload, task_id=task_id, run_id=run_id):
            files.append(str(report))
            errors.extend(_errors(payload))
    log = _file(check.get('log'), root=root, base=summary_path.parent)
    if log is not None:
        files.append(str(log))
        if not errors:
            try:
                errors.extend(line.strip() for line in log.read_text(encoding='utf-8', errors='replace')[:131072].splitlines()
                              if re.search(r'\b(error|fail(?:ed|ure)?|missing|not found)\b', line, re.I))
            except OSError:
                pass
    files.extend(_source_files(errors))
    return _recommendation(
        f'failed-check-{name}', f'Repair failed check: {name}', 'The failed child step identifies the check to repair and rerun.',
        errors or ['Inspect the bound check report before resuming.'], files, cmd or fallback_cmd,
    )


def _llm_recommendations(payload: dict[str, Any], summary_path: Path, fallback_cmd: list[str]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    steps = payload.get('steps') if isinstance(payload.get('steps'), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        details = step.get('details') if isinstance(step.get('details'), dict) else {}
        contract = details.get('review_contract') if isinstance(details.get('review_contract'), dict) else {}
        findings = contract.get('findings') if isinstance(contract.get('findings'), list) else []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            severity = str(finding.get('severity') or '').strip().upper()
            disposition = finding.get('disposition') if isinstance(finding.get('disposition'), dict) else {}
            if disposition.get('action') == 'defer' and severity not in {'P0', 'P1'}:
                continue
            finding_id = str(finding.get('finding_id') or 'unnamed')
            actions = [
                json.dumps(finding[key], ensure_ascii=False) if isinstance(finding[key], (dict, list)) else str(finding[key]).strip()
                for key in ['required_action', 'verification'] if finding.get(key)
            ]
            evidence = [str(value) for value in finding.get('evidence', [])] if isinstance(finding.get('evidence'), list) else []
            authorities = [str(value) for value in finding.get('authority_refs', [])] if isinstance(finding.get('authority_refs'), list) else []
            recommendations.append(_recommendation(
                f'llm-finding-{finding_id}', f'{severity} finding: {finding_id}', str(finding.get('claim') or 'Address the recorded reviewer finding.'),
                actions or ['Open the recorded Review Contract and address this finding.'],
                [str(summary_path)] + _source_files(evidence + authorities), fallback_cmd,
            ))
    return recommendations


def build_evidence_recommendations(*, root: Path, task_id: str, run_id: str, step_name: str, step: dict[str, Any]) -> list[dict[str, Any]]:
    summary_path = _file(step.get('summary_file'), root=root, base=root, snapshot_first=False)
    payload = _json(summary_path)
    if summary_path is None or not payload or not _matches(payload, task_id=task_id, run_id=run_id):
        return []
    fallback_cmd = _cmd(step)
    if step_name == 'sc-llm-review':
        return _llm_recommendations(payload, summary_path, fallback_cmd)
    recommendations: list[dict[str, Any]] = []
    checks = payload.get('steps') if isinstance(payload.get('steps'), list) else []
    for check in checks:
        if not isinstance(check, dict) or check.get('status') != 'fail':
            continue
        test_recs = _trx_recommendations(check, root=root, summary_path=summary_path, run_id=run_id, fallback_cmd=fallback_cmd) if check.get('name') == 'unit' else []
        recommendations.extend(test_recs or [_check_recommendation(
            check, root=root, summary_path=summary_path, task_id=task_id, run_id=run_id, fallback_cmd=fallback_cmd,
        )])
    return recommendations
