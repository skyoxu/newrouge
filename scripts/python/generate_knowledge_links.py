#!/usr/bin/env python3
"""Generate project resource links from the latest project-health task scan."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from project_health_knowledge import base_dir, read_json
from _project_health_navigation import build_navigation
from build_knowledge_catalog import _atomic_json

def _resource_role(path: str, kind: str) -> str:
    name = Path(path).stem.lower()
    if kind == 'config':
        labels = {'card-pools': '卡池与商店牌池', 'card-definitions': '卡牌属性与效果', 'reward-pools': '奖励池', 'enemy-definitions': '敌人属性', 'enemy-intent-definitions': '敌人意图', 'warrior-starting-deck': '初始卡组', 'act1-config': '第一幕流程', 'relic-definitions': '遗物定义', 'event-definitions': '事件定义', 'curse-definitions': '诅咒定义', 'rest-options': '休息选项', 'shop-pools': '商店池'}
        for token, label in labels.items():
            if token in name: return label
        if name in {'en', 'zh-cn'}: return '界面文本本地化'
    return {'asset': '运行时素材', 'scene': 'Godot 场景', 'code': '实现代码'}.get(kind, '关联资源')

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
        task_title = str(task.get('title') or '')
        task_refs = task.get('test_refs', [])
        for kind in ('configs', 'assets', 'scenes', 'code'):
            for resource in nav.get(kind, []):
                entry_kind = 'asset' if kind == 'assets' else ('config' if kind == 'configs' else kind[:-1])
                confidence = 'confirmed' if resource.get('focus') == 'core' else 'inferred'
                entries.append({'id': f'{entry_kind}:{task.get("id")}:{resource.get("path")}', 'task_id': str(task.get('id')), 'task_title': task_title,
                                'path': resource.get('path'), 'kind': entry_kind,
                                'role': _resource_role(resource.get('path', ''), entry_kind),
                                'semantic_role': f'{task_title}中的{entry_kind}关联',
                                'parameters': resource.get('focused_fields') or resource.get('fields', []) if entry_kind == 'config' else [],
                                'readers': resource.get('readers', []),
                                'bindings': resource.get('nodes', []) or resource.get('users', []),
                                'confidence': confidence, 'reconstruction': 'semantic_reconstruction',
                                'test_refs': task_refs, 'source_revision': state.get('revision'),
                                'evidence': [{'path': resource.get('path'), 'line': resource.get('line'),
                                             'focus': resource.get('focus'), 'evidence_kind': resource.get('evidence_kind')} ]})
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
    catalog_path = root / 'docs/knowledge/catalog/knowledge-catalog.json'
    if catalog_path.exists():
        catalog = read_json(catalog_path)
        catalog_entries = [entry for entry in catalog.get('entries', [])
                           if not task_ids or str(entry.get('task_id')) not in task_ids]
        merged = catalog_entries + entries
        unique = {}
        for entry in merged:
            unique[entry.get('id')] = entry
        catalog['entries'] = list(unique.values())
        catalog['last_scan_revision'] = state.get('revision')
        _atomic_json(catalog_path, catalog)
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
