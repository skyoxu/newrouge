#!/usr/bin/env python3
"""Main-only investigation CLI used by the project-health HTTP service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from _knowledge_catalog_builder import GitSnapshot, build_layers
from _knowledge_locator_core import locate, tokens
from _project_health_tasks import attach_task_scenes, task_details, task_page, task_summary
from impact_analysis_index import build_and_publish_index
from impact_analysis_index import ImpactIndexError
from impact_analyzer import ImpactAnalyzer

CONFIG = 'scripts/python/project_health_knowledge_config.json'
REF = 'refs/project-health/main'


def base_dir(root: Path) -> Path:
    return root / 'logs/ci/project-health-knowledge'


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Git operation failed')
    return result.stdout.strip()


class HealthSnapshot(GitSnapshot):
    def _git_text(self, *args: str) -> str:
        return git(self.root, '-c', 'core.quotepath=false', *args)


def safe_file(root: Path, relative: str) -> Path:
    p = PurePosixPath(relative)
    if not relative or '\\' in relative or ':' in relative or p.is_absolute() or '..' in p.parts:
        raise ValueError('Expected a repository-relative path')
    candidate = root.joinpath(*p.parts)
    candidate.resolve().relative_to(root.resolve())
    if any(parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)()
           for parent in (candidate, *candidate.parents) if parent != root.parent):
        raise ValueError('Symlinks are not supported')
    return candidate


def load_config(root: Path) -> dict:
    path = root / CONFIG
    config = read_json(path) if path.exists() else {'gdd_paths': [], 'task_scene_bindings': [], 'query_aliases': {}}
    return validate_config(root, config)


def validate_config(root: Path, config: dict) -> dict:
    if set(config) != {'gdd_paths', 'task_scene_bindings', 'query_aliases'}:
        raise ValueError('Unexpected configuration keys')
    if not isinstance(config['gdd_paths'], list) or len(config['gdd_paths']) > 100:
        raise ValueError('gdd_paths must be an array of at most 100 paths')
    for value in config['gdd_paths']:
        if not isinstance(value, str):
            raise ValueError('GDD paths must be strings')
        safe_file(root, value)
        if Path(value).suffix.lower() not in {'.md', '.txt', '.json'}:
            raise ValueError('GDD sources must be UTF-8 Markdown, text or JSON')
    if not isinstance(config['task_scene_bindings'], list) or not all(isinstance(x, dict) for x in config['task_scene_bindings']):
        raise ValueError('task_scene_bindings must be an array of objects')
    if not isinstance(config['query_aliases'], dict) or not all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(q, str) and len(q) <= 500 for q in v)
        for k, v in config['query_aliases'].items()
    ):
        raise ValueError('query_aliases must map text to arrays of query strings')
    return config


def scan(root: Path) -> dict:
    base = base_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    lock = base / 'scan.lock'
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError('Scan already running; inspect scan.lock after an interrupted process') from exc
    try:
        config = load_config(root)
        # Fetch only main. Never check out or reset the developer's branch.
        git(root, 'fetch', '--no-tags', 'origin', f'refs/heads/main:{REF}')
        revision = git(root, 'rev-parse', REF)
        snapshot = base / 'snapshots' / revision
        if not snapshot.exists():
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            git(root, 'worktree', 'add', '--detach', str(snapshot), revision)
        if git(snapshot, 'rev-parse', 'HEAD') != revision:
            raise RuntimeError('Snapshot HEAD changed')
        if git(snapshot, 'status', '--porcelain', '--untracked-files=no'):
            raise RuntimeError('Snapshot contains tracked modifications; refusing mixed revision')
        trusted = HealthSnapshot(snapshot, revision)
        policies = read_json(snapshot / 'knowledge/policies/consumer-policies.v1.json')
        exclusions = read_json(snapshot / 'knowledge/policies/source-exclusions.v1.json')
        _, catalog, projections = build_layers(trusted, exclusions, policies)
        index = build_and_publish_index(snapshot, revision=revision, trusted_ref=None,
                                        config_relative='scripts/python/impact_analysis_config.v1.json',
                                        aliases_relative='scripts/python/impact_target_aliases.v1.json',
                                        output_root=snapshot / 'logs/ci')
        # Only tracked, bounded UTF-8 source files enter the investigation workspace.
        selected = {m['source_path'] for m in catalog['modules']}
        selected.update(config['gdd_paths'])
        selected.update(p for p in trusted.paths if p.startswith(('Game.Godot/', 'Game.Core/', 'Game.Core.Tests/', 'Tests.Godot/'))
                        and Path(p).suffix in {'.tscn', '.tres', '.cs', '.gd'})
        sources = {}
        for path in sorted(selected & set(trusted.paths)):
            data = trusted.read_bytes(path)
            if len(data) <= 4 * 1024 * 1024:
                try:
                    sources[path] = data.decode('utf-8-sig')
                except UnicodeDecodeError:
                    pass
        details = task_details(snapshot)
        attach_task_scenes(details, sources, config['task_scene_bindings'])
        gdds = [{'path': p, 'available': p in sources, 'role': 'supplementary-design-source',
                 'sha256': trusted.digest(p) if p in sources else None}
                for p in config['gdd_paths']]
        pointer = snapshot / 'knowledge/indexes/current.json'
        publication = read_json(pointer) if pointer.exists() else {}
        result = {'schema_version': 'newrouge.project-health-knowledge.v1', 'revision': revision,
                  'scanned_at': datetime.now(timezone.utc).isoformat(), 'branch': 'main',
                  'snapshot': str(snapshot), 'summary': task_summary(details), 'tasks': details,
                  'gdd_files': gdds, 'config': config, 'index': index,
                  'catalog': catalog, 'policies': policies, 'projections': projections,
                  'sources': sources, 'publication': {'main_commit': publication.get('main_commit'),
                  'matches_scan': publication.get('main_commit') == revision,
                  'note': 'Exploratory catalogs are not published or frozen KCP authority.'}}
        # Commit only complete successful scans; failures retain the previous dated result.
        write_json(base / 'latest.json', result)
        return status(result)
    finally:
        lock.rmdir()


def status(state: dict) -> dict:
    return {key: state[key] for key in ('schema_version', 'revision', 'scanned_at', 'branch',
                                       'summary', 'gdd_files', 'publication', 'config')}


def query(root: Path, state: dict, request: dict) -> dict:
    query_text = request.get('query')
    if not isinstance(query_text, str) or not query_text.strip() or len(query_text) > 2000:
        raise ValueError('Query must contain 1 to 2000 characters')
    queries = [query_text]
    for key, values in state['config']['query_aliases'].items():
        if key.casefold() in query_text.casefold():
            queries.extend(values)
    queries = list(dict.fromkeys(queries))[:12]
    consumer = request.get('consumer', 'repository-session')
    policy = next((p for p in state['policies']['policies'] if p['consumer'] == consumer), None)
    projection = next((p for p in state['projections']['projections'] if p['consumer'] == consumer), None)
    if not policy or not projection:
        raise ValueError('Unknown knowledge consumer')
    candidates = {}
    for text in queries:
        found = locate({'query': text}, state['catalog'], policy, set(projection['eligible_module_ids']), 12)
        for item in found['candidates']:
            candidates.setdefault(item['module_id'], {**item, 'matched_query': text})
    supplemental = []
    for item in state['gdd_files']:
        content = state['sources'].get(item['path'], '')
        if item['available'] and any(any(t in content.casefold() for t in tokens(q)) for q in queries):
            supplemental.append(item)
    snapshot = Path(state['snapshot'])
    analyzer = ImpactAnalyzer(snapshot, snapshot / state['index']['index_path'], state['revision'], exploratory=True)
    targets = []
    needles = set(t for q in queries for t in tokens(q))
    for symbol in analyzer.resolver.symbol_index.symbols:
        if symbol.kind.startswith('__'):
            continue
        if any(t in symbol.identity.casefold() for t in needles):
            targets.append({'type': symbol.kind, 'id': symbol.identity, 'path': symbol.path})
    for path in analyzer.hashes:
        if any(t in path.casefold() for t in needles):
            targets.append({'type': 'file', 'id': path, 'path': path})
    try:
        preview = analyzer.explore(request['target']) if request.get('target') else None
    except ImpactIndexError as exc:
        preview = {'status': 'blocked', 'code': exc.code, 'reason': exc.reason, 'handoff_eligible': False}
    result = {'status': 'exploratory', 'handoff_eligible': False, 'revision': state['revision'],
              'queries': queries, 'consumer': consumer, 'knowledge': list(candidates.values()),
              'gdd_supplements': supplemental, 'impact_targets': targets[:80],
              'impact_target_total': len(targets), 'impact_preview': preview,
              'impact_skipped_methods': analyzer.resolver.symbol_index.skipped_methods,
              'next_step': 'Select an exact Impact target. Formal handoff requires existing KCP accept/freeze and analyze_impact CLI.'}
    evidence = base_dir(root) / 'queries' / (uuid.uuid4().hex + '.json')
    write_json(evidence, result)
    result['evidence_path'] = evidence.relative_to(root).as_posix()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('scan', 'status', 'tasks', 'task', 'query', 'source'))
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--task-id')
    parser.add_argument('--path')
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.action == 'scan':
            result = scan(root)
        else:
            state = read_json(base_dir(root) / 'latest.json')
            if args.action == 'status':
                result = status(state)
            elif args.action == 'tasks':
                result = task_page(state['tasks'], args.page)
            elif args.action == 'task':
                result = next((x for x in state['tasks'] if str(x['task']['id']) == args.task_id), None)
                if result is None:
                    raise ValueError('Task not found')
            elif args.action == 'source':
                if args.path not in state['sources']:
                    raise ValueError('Source is not in the scanned allowlist')
                result = {'path': args.path, 'revision': state['revision'], 'content': state['sources'][args.path]}
            else:
                result = query(root, state, json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'reason': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
