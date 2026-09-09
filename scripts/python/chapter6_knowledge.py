#!/usr/bin/env python3
"""Capture task resource knowledge as an explicit Chapter 6 stage."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def _semantic_enrich(root: Path, task_id: str, backend: str) -> dict:
    sys.path.insert(0, str(root / 'scripts/sc'))
    from _llm_backend import run_llm_exec
    links = root / 'docs/knowledge/generated/task-resource-links.json'
    payload = json.loads(links.read_text(encoding='utf-8')) if links.exists() else {'generated': []}
    entries = [x for x in payload.get('generated', []) if str(x.get('task_id')) == str(task_id)]
    prompt = ('Return JSON array only. Explain each resource for a developer. Do not invent paths or fields. '
              'For each item keep id/path and add explanation, parameter_guidance, modification_impact.\n' +
              json.dumps(entries, ensure_ascii=False))
    out = root / 'docs/knowledge/generated' / f'task-{task_id}-semantic.json'
    rc, trace, command = 1, '', []
    for attempt in range(1, 6):
        rc, trace, command = run_llm_exec(backend=backend, root=root, prompt=prompt, output_last_message=out, timeout_sec=300)
        if rc == 0:
            break
        if attempt < 5:
            import time
            time.sleep(1)
    if rc != 0:
        out.write_text(json.dumps({'status': 'unverified', 'task_id': task_id, 'generated_by': 'llm-assisted-semantic-analysis', 'attempts': 5, 'error': trace[-1000:]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {'status': 'unverified', 'rc': rc, 'attempts': 5}
    try:
        model = json.loads(out.read_text(encoding='utf-8'))
        valid = isinstance(model, list) and all(str(x.get('path')) in {str(e.get('path')) for e in entries} for x in model if isinstance(x, dict))
    except (OSError, json.JSONDecodeError): valid = False
    if not valid:
        return {'status': 'unverified', 'rc': 1, 'attempts': 5}
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
