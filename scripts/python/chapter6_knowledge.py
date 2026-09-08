#!/usr/bin/env python3
"""Capture task resource knowledge as an explicit Chapter 6 stage."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def run(root: Path, task_id: str, write_task_refs: bool = False) -> dict:
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
    return {'status': 'knowledge_captured', 'task_id': task_id, 'steps': steps}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=Path.cwd()); parser.add_argument('--task-id', required=True); parser.add_argument('--write-task-refs', action='store_true')
    args = parser.parse_args(argv)
    result = run(args.repo_root.resolve(), args.task_id, args.write_task_refs)
    print(json.dumps(result, ensure_ascii=False)); return 0 if result['status'] == 'knowledge_captured' else 1
if __name__ == '__main__': raise SystemExit(main())
