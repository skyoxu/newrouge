#!/usr/bin/env python3
"""Generate project resource links from the latest project-health task scan."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from project_health_knowledge import base_dir, read_json
from _project_health_navigation import build_navigation
from build_knowledge_catalog import _atomic_json

def generate(root: Path, task_ids: set[str] | None = None, write_task_refs: bool = False) -> dict:
    latest = base_dir(root) / 'latest.json'
    if not latest.exists():
        raise ValueError('A successful local source scan is required')
    state = read_json(latest)
    available_ids = {str(item['task']['id']) for item in state.get('tasks', [])}
    if task_ids and not task_ids <= available_ids:
        raise ValueError('Selected task is absent from the source scan')
    entries = []
    for item in state.get('tasks', []):
        task = item.get('task', {})
        if task_ids and str(task.get('id')) not in task_ids:
            continue
        nav = build_navigation(item, state)
        for kind in ('configs', 'assets', 'scenes', 'code'):
            for resource in nav.get(kind, []):
                entries.append({'id': f'{kind[:-1]}:{resource.get("path")}', 'task_id': str(task.get('id')), 'path': resource.get('path'), 'kind': 'asset' if kind == 'assets' else ('config' if kind == 'configs' else kind[:-1]), 'role': resource.get('evidence_kind', '关联资源'), 'confidence': 'confirmed' if resource.get('focus') == 'core' else 'inferred', 'source_revision': state.get('revision'), 'evidence': [{'path': resource.get('path'), 'line': resource.get('line')} ]})
    out = root / 'docs/knowledge/generated/task-resource-links.json'
    if task_ids and out.exists():
        previous = read_json(out)
        entries = [entry for entry in previous.get('generated', [])
                   if str(entry.get('task_id')) not in task_ids] + entries
    revisions = {entry.get('source_revision') for entry in entries}
    payload = {'schema_version': '1.0', 'generated_at': datetime.now(timezone.utc).isoformat(),
               'source_revision': state.get('revision') if len(revisions) <= 1 else None,
               'task_ids': sorted({str(entry['task_id']) for entry in entries}), 'generated': entries}
    _atomic_json(out, payload)
    updated_tasks = 0
    if write_task_refs:
        task_file = root / '.taskmaster/tasks/tasks_gameplay.json'
        rows = json.loads(task_file.read_text(encoding='utf-8'))
        by_task = {}
        for entry in entries:
            by_task.setdefault(str(entry.get('task_id')), []).append(entry.get('id'))
        selected = task_ids or set(by_task)
        for row in rows:
            task_key = str(row.get('taskmaster_id'))
            if task_key in selected:
                refs = sorted(set(by_task.get(task_key, [])))
                row['knowledge_entry_ids'] = refs
                row['knowledge_scan_revision'] = state.get('revision')
                updated_tasks += 1
        _atomic_json(task_file, rows)
    return {'status': 'ok', 'entries': len(entries), 'updated_tasks': updated_tasks, 'path': 'docs/knowledge/generated/task-resource-links.json', 'source_revision': state.get('revision')}

def main(argv=None) -> int:
    p = argparse.ArgumentParser(); p.add_argument('--repo-root', type=Path, default=Path.cwd()); p.add_argument('--task-id', action='append', dest='task_ids'); p.add_argument('--write-task-refs', action='store_true'); args = p.parse_args(argv); print(json.dumps(generate(args.repo_root.resolve(), set(args.task_ids or []), args.write_task_refs), ensure_ascii=False)); return 0
if __name__ == '__main__': raise SystemExit(main())
