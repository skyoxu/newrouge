"""Read-only, provenance-limited GDD version and cumulative MVG projection."""
from __future__ import annotations

import json
from pathlib import Path

from _mvg_manifest import manifest_sha256
from _mvg_requirement_routes import FIELD, memberships, trace_errors, authority_ids
from _mvg_requirement_accounting import (VERIFICATION, EVIDENCE, verification_rows,
    evidence_rows, accounting_summary, trace_evidence_validation)


def attach_planning_routes(manifest: dict, proposal: dict, source: dict, *, requirement_ids, applied_manifest,
                           read_source=None) -> bool:
    """Attach descriptive routes only after the caller binds this exact manifest."""
    if trace_errors(proposal, applied_manifest, requirement_ids):
        return False
    manifest[FIELD] = memberships(proposal)
    manifest['coverage_table'] = proposal.get('coverage_table', [])
    manifest['requirement_routes_source'] = source
    manifest[VERIFICATION] = verification_rows(proposal)
    manifest[EVIDENCE] = evidence_rows(proposal)
    errors, valid = trace_evidence_validation(proposal, read_source=read_source)
    manifest['requirement_accounting'] = accounting_summary(proposal, valid_evidence_keys=valid)
    manifest['requirement_accounting']['evidence_errors'] = errors
    from _mvg_planning_completion import FIELD as COMPLETION_FIELD, bound_report, unavailable
    manifest[COMPLETION_FIELD] = (unavailable('Current Requirement evidence is missing or has changed.') if errors
        else bound_report(proposal, applied_manifest, manifest.get('path')))
    return True


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
    identity = topology.get('identity') if isinstance(topology.get('identity'), dict) else {}
    trustworthy = (
        topology.get('available') is True and topology.get('fresh') is True
        and (
            (identity.get('kind') == 'workspace' and identity.get('authority_ref') == 'local-workspace')
            or identity.get('revision') == snapshot.commit
        )
    )
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
        scene_candidates = {}
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
            for candidate in detail.get('godot', {}).get('candidates', []):
                scene_path = candidate.get('scene')
                if not scene_path or scene_path not in graph.get('nodes', {}):
                    continue
                scene = graph['nodes'][scene_path]
                entry = scene_candidates.setdefault(scene_path, {
                    'path': scene_path,
                    'classification': scene.get('classification'),
                    'nodes': sorted({str(node.get('parent') or '.') + '/' + str(node.get('name') or '(unnamed)') for node in scene.get('nodes', [])}),
                    'resources': sorted({resource for node in scene.get('nodes', []) for resource in node.get('resources', []) if isinstance(resource, str)}),
                    'evidence_sources': [],
                    'evidence': 'candidate_task_test_reference',
                })
                evidence = candidate.get('evidence')
                if isinstance(evidence, str) and evidence not in entry['evidence_sources']:
                    entry['evidence_sources'].append(evidence)
        versions.append({
            'id': path + '@' + sha[:16], 'gdd_path': path, 'gdd_sha256': sha,
            'mapping': 'traced' if mapped else 'unmapped',
            'task_ids': mapped, 'tasks': [{'id': id_, 'title': task_ids[id_]['task'].get('title'), 'status': task_ids[id_]['task'].get('status')} for id_ in mapped],
            'references': {key: sorted(values) for key, values in refs.items()},
            'scenes': [scenes[key] for key in sorted(scenes)],
            'scene_candidates': [scene_candidates[key] for key in sorted(scene_candidates) if key not in scenes],
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
        item = {'path': path, 'sha256': manifest_sha256(data),
                          'mvg_id': manifest.get('mvg_id'), 'coverage': manifest.get('coverage', {}),
                          'flows': flows, 'tests': manifest.get('tests', []),
                          FIELD: [], 'requirement_routes_source': None}
        from _mvg_planning_completion import FIELD as COMPLETION_FIELD, unavailable
        item[COMPLETION_FIELD] = unavailable()
        traces = []
        for trace_path in sorted(p for p in paths if p.startswith('docs/testing/mvg/planning/') and p.endswith('.json')):
            try:
                trace = json.loads(snapshot.read_text(trace_path))
            except (OSError, ValueError):
                continue
            if not isinstance(trace, dict):
                continue
            if (trace.get('applied_manifest_path') == path
                    and trace.get('applied_manifest_sha256') == item['sha256']
                    and trace.get('applied_manifest_candidate', trace.get('manifest_candidate')) == manifest):
                traces.append((str(trace.get('applied_at_utc') or ''), trace_path, trace))
        for _, trace_path, trace in sorted(traces, key=lambda row: (row[0], row[1]), reverse=True):
            if attach_planning_routes(item, trace, {'kind': 'formal_planning_trace',
                    'path': trace_path, 'sha256': snapshot.digest(trace_path)},
                    requirement_ids=authority_ids({'requirements': topology.get('nodes', {}).get('requirements', [])})
                    if trustworthy else set(), applied_manifest=manifest,
                    read_source=lambda ref: snapshot.read_bytes(ref) if ref in paths else None):
                break
        manifests.append(item)
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
        if manifest.get('planning_result'):
            copy['evidence']['reason'] = 'Local generated plan; commit it before running main verification.'
            result['manifests'].append(copy)
            continue
        for path in runs:
            try:
                summary = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if (summary.get('manifest') != manifest['path'] or summary.get('manifest_sha256') != manifest['sha256']
                    or summary.get('mode') != 'run' or summary.get('source_revision') != overview.get('revision')
                    or summary.get('base_commit') != overview.get('revision')):
                continue
            copy['evidence'] = {'status': 'passed' if summary.get('status') == 'passed' and summary.get('runtime_verified') is True else 'failed',
                                'run_id': summary.get('run_id'), 'reason': summary.get('reason', ''),
                                'runtime_verified': summary.get('runtime_verified') is True}
            break
        result['manifests'].append(copy)
    return result
