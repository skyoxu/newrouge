#!/usr/bin/env python3
"""Capture task resource knowledge as an explicit Chapter 6 stage."""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

def _semantic_prompt_entries(entries: list[dict]) -> list[dict]:
    compact = []
    for entry in entries:
        if entry.get('kind') != 'config':
            continue
        item = {key: entry.get(key) for key in (
            'id', 'path', 'kind', 'role', 'task_title', 'readers', 'bindings', 'evidence', 'test_refs')}
        fields = entry.get('parameters') if isinstance(entry.get('parameters'), list) else []
        prioritized = sorted(
            (field for field in fields if isinstance(field, dict) and isinstance(field.get('pointer'), str)),
            key=lambda field: (field.get('kind') != 'numeric_parameter', field.get('line') or 0),
        )
        item['available_parameters'] = [
            {key: field.get(key) for key in ('pointer', 'value', 'line', 'record_id', 'kind')}
            for field in prioritized[:80]
        ]
        item['available_parameters_truncated'] = len(fields) > 80
        compact.append(item)
    return compact

def _validate_semantic_entries(model: object, entries: list[dict]) -> tuple[bool, list[dict], str | None]:
    if not isinstance(model, list) or not all(isinstance(item, dict) for item in model):
        return False, [], 'Semantic output must be an array of objects'
    available = {str(entry.get('path')): entry for entry in entries if entry.get('path')}
    normalized = []
    for item in model:
        path = str(item.get('path') or '')
        if path not in available:
            return False, [], f'Unknown resource path: {path}'
        parameters = item.get('parameters', [])
        if not isinstance(parameters, list) or not all(isinstance(parameter, dict) for parameter in parameters):
            return False, [], f'Parameters must be an array of objects: {path}'
        source = available[path]
        fields = source.get('parameters') if source.get('kind') == 'config' else []
        fields_by_pointer = {
            str(field.get('pointer')): field for field in fields or []
            if isinstance(field, dict) and isinstance(field.get('pointer'), str)}
        validated_parameters = []
        for parameter in parameters:
            pointer = parameter.get('pointer') or parameter.get('key')
            if not isinstance(pointer, str) or pointer not in fields_by_pointer:
                return False, [], f'Unknown parameter pointer for {path}: {pointer}'
            field = fields_by_pointer[pointer]
            validated_parameters.append({
                'pointer': pointer,
                'meaning': str(parameter.get('meaning') or parameter.get('description') or ''),
                'value': field.get('value'),
                'line': field.get('line'),
                'evidence_status': 'field_exists_semantic_inference',
            })
        clean = dict(item)
        clean['id'] = source.get('id')
        clean['path'] = path
        clean['parameters'] = validated_parameters
        normalized.append(clean)
    return True, normalized, None

def _semantic_enrich(root: Path, task_id: str, backend: str) -> dict:
    sys.path.insert(0, str(root / 'scripts/sc'))
    from _llm_backend import run_llm_exec
    links = root / 'docs/knowledge/generated/task-resource-links.json'
    payload = json.loads(links.read_text(encoding='utf-8')) if links.exists() else {'generated': []}
    entries = [x for x in payload.get('generated', []) if str(x.get('task_id')) == str(task_id)]
    prompt_entries = _semantic_prompt_entries(entries)
    prompt = ('Return a JSON array only. Explain each supplied configuration resource for a developer implementing this task. '
              'For each item keep id and path, then add explanation, parameter_guidance, modification_impact, and parameters. '
              'parameters must be an array of objects with pointer and meaning. Use only exact pointer values listed in '
              'available_parameters for that same resource. Select only fields relevant to the task. '
              'Do not invent paths, fields, runtime observations, or task evidence. Omit unrelated resources.\n' +
              json.dumps(prompt_entries, ensure_ascii=False, separators=(',', ':')))
    out = root / 'docs/knowledge/generated' / f'task-{task_id}-semantic.json'
    rc, trace, command = 1, '', []
    validation_error = None
    model = None
    for attempt in range(1, 6):
        rc, trace, command = run_llm_exec(backend=backend, root=root, prompt=prompt, output_last_message=out, timeout_sec=300)
        if rc == 0:
            try:
                candidate = json.loads(out.read_text(encoding='utf-8'))
                valid, model, validation_error = _validate_semantic_entries(candidate, entries)
                if valid:
                    break
            except (OSError, json.JSONDecodeError) as exc:
                validation_error = str(exc)
        if attempt < 5:
            time.sleep(1)
    if rc != 0 or model is None:
        error = validation_error or trace[-1000:] or 'Semantic output validation failed'
        out.write_text(json.dumps({'status': 'unverified', 'task_id': task_id, 'generated_by': 'llm-assisted-semantic-analysis', 'attempts': 5, 'error': error}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {'status': 'unverified', 'rc': rc, 'attempts': 5}
    out.write_text(json.dumps({'status': 'verified', 'task_id': task_id, 'generated_by': 'llm-assisted-semantic-analysis', 'backend': backend, 'entries': model}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'status': 'verified', 'entries': len(model), 'attempts': attempt, 'command': command}

def run(root: Path, task_id: str, write_task_refs: bool = False, semantic: bool = False, llm_backend: str = 'codex-cli') -> dict:
    commands = [
        [sys.executable, str(root / 'scripts/python/dev_cli.py'), 'project-health-scan', '--repo-root', str(root)],
        [sys.executable, str(root / 'scripts/python/dev_cli.py'), 'generate-knowledge-links', '--repo-root', str(root), '--task-id', task_id] + (['--write-task-refs'] if write_task_refs else []),
        [sys.executable, str(root / 'scripts/python/dev_cli.py'), 'init-knowledge-catalog', '--repo-root', str(root), '--validate'],
    ]
    steps = []
    for command in commands:
        proc = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
        steps.append({'command': command, 'returncode': proc.returncode, 'stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-2000:]})
        if proc.returncode:
            return {'status': 'knowledge_capture_failed', 'task_id': task_id, 'stop_step': len(steps), 'steps': steps}
    if semantic:
        semantic_result = _semantic_enrich(root, task_id, llm_backend)
        return {'status': 'knowledge_captured', 'task_id': task_id, 'semantic_status': semantic_result, 'steps': steps}
    return {'status': 'knowledge_captured', 'task_id': task_id, 'steps': steps}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=Path.cwd()); parser.add_argument('--task-id', required=True); parser.add_argument('--write-task-refs', action='store_true'); parser.add_argument('--semantic', action='store_true'); parser.add_argument('--llm-backend', default='codex-cli')
    args = parser.parse_args(argv)
    result = run(args.repo_root.resolve(), args.task_id, args.write_task_refs, args.semantic, args.llm_backend)
    print(json.dumps(result, ensure_ascii=False)); return 0 if result['status'] == 'knowledge_captured' else 1
if __name__ == '__main__': raise SystemExit(main())
