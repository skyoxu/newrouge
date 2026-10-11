"""Explicit maintainer publication of reviewed Chapter 6 semantic candidates."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path

SCHEMA = 'newrouge.chapter6-semantic-publication.v1'
TEXT_SUFFIXES = {'.json', '.csv', '.cs', '.gd', '.tscn', '.tres', '.cfg', '.ini', '.yaml', '.yml', '.md', '.txt'}


def _task_id(value: str) -> str:
    if not re.fullmatch(r'[1-9][0-9]*', str(value)):
        raise ValueError('invalid_task_id')
    return str(value)


def content_hash(path: str, data: bytes) -> str:
    if Path(path).suffix.lower() in TEXT_SUFFIXES:
        data = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def task_entries(root: Path, task_id: str) -> list[dict]:
    links = load_json(root / 'docs/knowledge/generated/task-resource-links.json', {})
    return [row for row in links.get('generated', [])
            if isinstance(row, dict) and str(row.get('task_id')) == _task_id(task_id)]


def prepare_identity(root: Path, task_id: str, entries: list[dict]) -> dict:
    paths = {str(row['path']) for row in entries if row.get('path')}
    for row in entries:
        paths.update(str(ref['reader']) for ref in row.get('readers', []) if ref.get('reader'))
        paths.update(str(ref['source']) for ref in row.get('bindings', []) if ref.get('source'))
    paths.update(path for path in ('.taskmaster/tasks/tasks.json', '.taskmaster/tasks/tasks_back.json',
                                  '.taskmaster/tasks/tasks_gameplay.json') if (root / path).is_file())
    hashes = {}
    for path in sorted(paths):
        source = repo_path(root, path)
        if not source.is_file():
            raise ValueError('semantic_source_missing:' + path)
        hashes[source.relative_to(root.resolve()).as_posix()] = content_hash(path, source.read_bytes())
    return {'schema_version': SCHEMA, 'task_id': _task_id(task_id),
            'resource_mapping_sha256': canonical_sha(entries), 'source_hashes': hashes}


def publish(root: Path, task_id: str, *, candidate_sha256: str, reviewed_by: str,
            review_note: str, confirm: bool = False) -> dict:
    """Validate review identity and current sources before an atomic publication."""
    root, task_id = root.resolve(), _task_id(task_id)
    candidate = root / f'logs/ci/chapter6-knowledge/task-{task_id}/semantic-candidate.json'
    if not candidate.is_file() or file_sha(candidate) != candidate_sha256:
        raise ValueError('candidate_hash_mismatch')
    if not reviewed_by.strip() or not review_note.strip():
        raise ValueError('explicit_semantic_review_required')
    payload = load_json(candidate, {})
    if payload.get('status') != 'verified' or payload.get('task_id') != task_id:
        raise ValueError('semantic_candidate_not_verified_for_task')
    master = load_json(root / '.taskmaster/tasks/tasks.json', {})
    if task_id not in {str(row.get('id')) for row in master.get('master', {}).get('tasks', [])}:
        raise ValueError('semantic_task_missing')
    identity = payload.get('input_identity')
    if not isinstance(identity, dict) or identity.get('schema_version') != SCHEMA:
        raise ValueError('semantic_candidate_input_identity_missing')
    entries = task_entries(root, task_id)
    if identity.get('resource_mapping_sha256') != canonical_sha(entries):
        raise ValueError('semantic_resource_mapping_changed')
    current = prepare_identity(root, task_id, entries)
    if identity != current:
        raise ValueError('semantic_source_changed')
    model = payload.get('entries')
    if (not isinstance(model, list) or not model
            or any(not isinstance(row, dict) or not str(row.get('explanation') or '').strip() for row in model)
            or len({row.get('path') for row in model}) != len(model)):
        raise ValueError('semantic_explanations_missing_or_duplicate')
    from chapter6_knowledge import _validate_semantic_entries
    valid, normalized, error = _validate_semantic_entries(model, entries)
    if not valid:
        raise ValueError('semantic_publication_invalid:' + str(error))
    output = root / f'docs/knowledge/generated/task-{task_id}-semantic.json'
    result = {'status': 'preview', 'task_id': task_id, 'entries': len(normalized),
              'path': output.relative_to(root).as_posix(), 'candidate_sha256': candidate_sha256,
              'scope': 'partial', 'runtime_verified': False}
    if not confirm:
        return result
    reviewed = {'schema_version': SCHEMA, 'candidate_path': candidate.relative_to(root).as_posix(),
                'candidate_sha256': candidate_sha256, 'reviewed_by': reviewed_by.strip(),
                'review_note': review_note.strip(), 'published_at_utc': datetime.now(timezone.utc).isoformat()}
    published = {**payload, 'entries': normalized, 'publication': reviewed,
                 'coverage': {**(payload.get('coverage') or {}), 'scope': 'partial'}, 'runtime_verified': False}
    published_bytes = (json.dumps(published, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    published_sha256 = 'sha256:' + hashlib.sha256(published_bytes).hexdigest()
    evidence = root / f'logs/ci/chapter6-knowledge/task-{task_id}/publications/{candidate_sha256[7:]}/{published_sha256[7:]}.json'
    atomic_json(evidence, {**reviewed, **result, 'status': 'published', 'published_sha256': published_sha256})
    atomic_json(output, published)
    return {**result, 'status': 'published', 'evidence_path': evidence.relative_to(root).as_posix()}


def load_for_navigation(root: Path, task_id: str, state: dict) -> tuple[dict | None, dict | None]:
    """Expose provenance and suppress model suggestions bound to stale evidence."""
    task_id = _task_id(task_id)
    path = root / f'docs/knowledge/generated/task-{task_id}-semantic.json'
    if not path.is_file():
        return None, None
    try:
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            raise ValueError('semantic_payload_invalid')
    except (OSError, ValueError):
        return None, {'scope': 'partial', 'freshness': 'invalid', 'path': path.relative_to(root).as_posix()}
    info = {'scope': 'partial', 'freshness': 'legacy_unbound', 'path': path.relative_to(root).as_posix(),
            'generated_at_utc': payload.get('generated_at_utc'), 'runtime_verified': False}
    identity, reviewed = payload.get('input_identity'), payload.get('publication')
    if 'input_identity' not in payload and 'publication' not in payload:
        if (payload.get('status') != 'verified' or str(payload.get('task_id')) != task_id
                or not isinstance(payload.get('entries'), list)
                or not all(isinstance(row, dict) for row in payload['entries'])):
            return None, {**info, 'freshness': 'invalid'}
        return payload, info
    if not isinstance(identity, dict) or not isinstance(reviewed, dict):
        return None, {**info, 'freshness': 'invalid'}
    info.update(candidate_path=reviewed.get('candidate_path'), candidate_sha256=reviewed.get('candidate_sha256'),
                reviewed_by=reviewed.get('reviewed_by'),
                published_at_utc=reviewed.get('published_at_utc'), coverage=payload.get('coverage', {}))
    if (identity.get('schema_version') != SCHEMA or identity.get('task_id') != task_id
            or not isinstance(identity.get('source_hashes'), dict) or not identity['source_hashes']
            or payload.get('status') != 'verified' or payload.get('task_id') != task_id):
        return None, {**info, 'freshness': 'invalid'}
    digest = str(reviewed.get('candidate_sha256') or '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        return None, {**info, 'freshness': 'invalid'}
    published_sha256 = file_sha(path)
    receipt_path = root / f'logs/ci/chapter6-knowledge/task-{task_id}/publications/{digest[7:]}/{published_sha256[7:]}.json'
    try:
        receipt = load_json(receipt_path, {})
        if (not isinstance(receipt, dict) or receipt.get('status') != 'published'
                or any(receipt.get(key) != value for key, value in reviewed.items())
                or receipt.get('published_sha256') != file_sha(path)):
            return None, {**info, 'freshness': 'invalid'}
    except (OSError, ValueError):
        return None, {**info, 'freshness': 'invalid'}
    changed = []
    snapshot = None
    sources = state.get('sources', {})
    for source_path, expected in identity['source_hashes'].items():
        try:
            if source_path in sources:
                data = sources[source_path].encode('utf-8')
            elif re.fullmatch(r'[0-9a-f]{40}', str(state.get('revision') or '')):
                if snapshot is None:
                    from _knowledge_catalog_builder import LocalMainSnapshot
                    snapshot = LocalMainSnapshot(root, state['revision'])
                if source_path not in snapshot.paths:
                    raise ValueError('semantic_snapshot_source_missing')
                data = snapshot.read_bytes(source_path)
            elif source_path in state.get('file_manifest', []):
                data = repo_path(root, source_path).read_bytes()
            else:
                raise ValueError('semantic_snapshot_source_missing')
            if content_hash(source_path, data) != expected:
                changed.append(source_path)
        except (OSError, ValueError, UnicodeError):
            changed.append(source_path)
    if identity.get('resource_mapping_sha256') != canonical_sha(task_entries(root, task_id)):
        changed.append('docs/knowledge/generated/task-resource-links.json')
    if changed:
        return None, {**info, 'freshness': 'stale', 'changed_paths': changed}
    return payload, {**info, 'freshness': 'current'}
