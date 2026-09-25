"""Read-only, provenance-limited GDD version and cumulative MVG projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def build_overview(snapshot, details: list[dict], topology: dict, graph: dict) -> dict:
    paths = set(snapshot.paths)
    registered = set()
    source_set = 'docs/workflows/chapter3-source-set.json'
    if source_set in paths:
        registered.update(json.loads(snapshot.read_text(source_set)).get('active_sources', []))
    # A configured GDD may precede the Chapter 3 source-set registry.
    if source_set not in paths:
        registered.update(path for path in paths if path.startswith('docs/gdd/') and path.endswith('.md'))
        registered.update(path for path in ('_bmad-output/gdd.md',) if path in paths)
    gdds = sorted(path for path in registered if path in paths and
                  (path.startswith('docs/gdd/') or path == '_bmad-output/gdd.md'))
    trustworthy = topology.get('available') is True and topology.get('fresh') is True and topology.get('identity', {}).get('revision') == snapshot.commit
    blocks = {}
    if trustworthy:
        for block in topology.get('nodes', {}).get('source_blocks', []):
            path = block.get('source_path')
            if path in gdds and (block.get('source_sha256') or block.get('source_file_sha256')) in (snapshot.digest(path), 'sha256:' + snapshot.digest(path)):
                blocks[str(block.get('block_id'))] = path
    task_ids = {str(row['task']['id']): row for row in details if isinstance(row.get('task'), dict)}
    associated = {path: set() for path in gdds}
    if trustworthy:
        for task_id, trace in topology.get('task_trace', {}).items():
            if task_id in task_ids:
                for block_id in trace.get('source_blocks', []):
                    if str(block_id) in blocks:
                        associated[blocks[str(block_id)]].add(task_id)

    versions = []
    for path in gdds:
        sha = snapshot.digest(path)
        mapped = sorted(associated[path], key=lambda item: (not item.isdigit(), int(item) if item.isdigit() else item))
        refs = {'overlays': set(), 'contracts': set(), 'adrs': set()}
        scenes = {}
        for task_id in mapped:
            detail = task_ids[task_id]
            for view in detail.get('mappings', {}).values():
                for row in view:
                    for field, key in (('overlay_refs', 'overlays'), ('contractRefs', 'contracts'), ('adr_refs', 'adrs')):
                        refs[key].update(value for value in row.get(field, []) if isinstance(value, str))
            for attachment in detail.get('godot', {}).get('scenes', []):
                scene_path = attachment.get('scene')
                if scene_path not in graph.get('nodes', {}):
                    continue
                scene = graph['nodes'][scene_path]
                scenes[scene_path] = {
                    'path': scene_path, 'classification': scene.get('classification'),
                    'nodes': sorted({str(node.get('parent') or '.') + '/' + str(node.get('name') or '(unnamed)') for node in scene.get('nodes', [])}),
                    'resources': sorted({resource for node in scene.get('nodes', []) for resource in node.get('resources', []) if isinstance(resource, str)}),
                    'evidence': 'declared_task_with_verified_static_attachment',
                }
        versions.append({
            'id': path + '@' + sha[:16], 'gdd_path': path, 'gdd_sha256': sha,
            'mapping': 'traced' if mapped else 'unmapped',
            'task_ids': mapped, 'tasks': [{'id': id_, 'title': task_ids[id_]['task'].get('title'), 'status': task_ids[id_]['task'].get('status')} for id_ in mapped],
            'references': {key: sorted(values) for key, values in refs.items()},
            'scenes': [scenes[key] for key in sorted(scenes)],
        })
    manifests = []
    for path in sorted(p for p in paths if p.startswith('docs/testing/mvg/') and p.endswith('.json')):
        data = snapshot.read_bytes(path)
        manifest = json.loads(data.decode('utf-8-sig'))
        if manifest.get('schema_version') != 'newrouge.mvg-integration.v1':
            continue
        flows = []
        for flow in manifest.get('flows', []):
            ids = {str(value) for value in flow.get('task_ids', [])}
            flows.append({'id': flow.get('id'), 'outcome': flow.get('outcome'),
                          'task_ids': sorted(ids), 'test_ids': flow.get('test_ids', []),
                          'handoffs': flow.get('handoffs', []),
                          'version_ids': [version['id'] for version in versions if ids.intersection(version['task_ids'])]})
        manifests.append({'path': path, 'sha256': 'sha256:' + hashlib.sha256(data).hexdigest(),
                          'mvg_id': manifest.get('mvg_id'), 'coverage': manifest.get('coverage', {}),
                          'flows': flows, 'tests': manifest.get('tests', [])})
    return {'schema_version': 'newrouge.knowledge-mvg-overview.v1', 'revision': snapshot.commit,
            'topology_fresh': trustworthy, 'versions': versions, 'manifests': manifests,
            'limitations': 'GDD source-set registration and static scene reachability do not prove Chapter 3 consumption or playability. Historical GDD revisions require separately published provenance.'}


def with_runtime_evidence(overview: dict, root: Path) -> dict:
    """Attach the latest matching run, never promoting a stale or workspace result."""
    result = {**overview, 'manifests': []}
    directory = root / 'logs/ci/mvg-acceptance'
    runs = sorted(directory.glob('*/summary.json'), key=lambda path: path.parent.name, reverse=True)[:200] if directory.exists() else []
    for manifest in overview.get('manifests', []):
        copy = dict(manifest)
        copy['evidence'] = {'status': 'not_verified', 'reason': 'No run matched this main revision and manifest content.'}
        for path in runs:
            try:
                summary = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if (summary.get('manifest') != manifest['path'] or summary.get('manifest_sha256') != manifest['sha256']
                    or summary.get('mode') != 'run' or summary.get('source_revision') != overview.get('revision')
                    or summary.get('base_commit') != overview.get('revision') or summary.get('workspace_dirty') is not False):
                continue
            copy['evidence'] = {'status': 'passed' if summary.get('status') == 'passed' and summary.get('runtime_verified') is True else 'failed',
                                'run_id': summary.get('run_id'), 'reason': summary.get('reason', ''),
                                'runtime_verified': summary.get('runtime_verified') is True}
            break
        result['manifests'].append(copy)
    return result
