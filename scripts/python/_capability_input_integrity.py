"""Lossless Capability transport checks performed before any model request."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path

DEFAULT_MAX_INPUT_TOKENS = 96000
# Keep a hard bound for the Codex text transport while allowing the complete
# current Capability evidence bundle (without clipping source or task fields).
CODEX_MAX_TURN_BYTES = 2 * 1024 * 1024
REPORT_NAME = 'runner-input-integrity.json'


def configured_input_limit() -> int:
    """Operator input allowance; never infer capacity from a default model name."""
    return int(os.environ.get('SC_CAPABILITY_MAX_INPUT_TOKENS') or DEFAULT_MAX_INPUT_TOKENS)


def _rows_by_id(rows: Any, key: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError('capability_input_integrity_invalid_rows:' + key)
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key]:
            raise ValueError('capability_input_integrity_invalid_id:' + key)
        if row[key] in result:
            raise ValueError('capability_input_integrity_duplicate_authority_id:' + row[key])
        result[row[key]] = row
    return result


def validate_batches(workspace: Path, index: dict) -> dict:
    """Compare entire rows, not just model-returned IDs or source file hashes."""
    analysis = workspace / 'analysis-input'
    ledger = load_json(analysis / 'source-blocks.v1.json', {})
    semantics = load_json(analysis / 'semantic-requirements.v1.json', {})
    blocks = _rows_by_id(ledger.get('blocks'), 'block_id')
    requirements = _rows_by_id(semantics.get('requirements'), 'requirement_id')
    rows = index.get('batches')
    if not isinstance(rows, list) or not rows or index.get('batch_count') != len(rows):
        raise ValueError('capability_input_integrity_batch_count_mismatch')
    seen_blocks, seen_requirements, seen_paths = set(), set(), set()
    for ordinal, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError('capability_input_integrity_invalid_batch_row')
        rel = str(row.get('path') or '')
        path = repo_path(analysis, rel)
        if (not path.is_relative_to((analysis / 'model-batches').resolve())
                or not path.is_file() or rel in seen_paths):
            raise ValueError('capability_input_integrity_invalid_batch_path:' + rel)
        seen_paths.add(rel)
        if file_sha(path) != row.get('sha256'):
            raise ValueError('capability_input_integrity_batch_hash_mismatch:' + rel)
        batch = load_json(path, {})
        if (batch.get('schema_version') != 'newrouge.capability-model-batch.v1'
                or batch.get('batch_index') != ordinal or batch.get('batch_count') != len(rows)):
            raise ValueError('capability_input_integrity_batch_sequence_mismatch:' + rel)
        batch_blocks = _rows_by_id(batch.get('blocks'), 'block_id')
        batch_requirements = _rows_by_id(batch.get('requirements'), 'requirement_id')
        if set(row.get('block_ids', [])) != set(batch_blocks):
            raise ValueError('capability_input_integrity_batch_block_index_mismatch:' + rel)
        if set(row.get('requirement_ids', [])) != set(batch_requirements):
            raise ValueError('capability_input_integrity_batch_requirement_index_mismatch:' + rel)
        for block_id, body in batch_blocks.items():
            if block_id in seen_blocks:
                raise ValueError('capability_input_integrity_duplicate_source_block:' + block_id)
            if blocks.get(block_id) != body:
                raise ValueError('capability_input_integrity_source_block_body_mismatch:' + block_id)
            seen_blocks.add(block_id)
        for requirement_id, body in batch_requirements.items():
            if requirements.get(requirement_id) != body:
                raise ValueError('capability_input_integrity_requirement_body_mismatch:' + requirement_id)
            seen_requirements.add(requirement_id)
    if seen_blocks != set(blocks) or index.get('block_count') != len(blocks):
        raise ValueError('capability_input_integrity_source_block_coverage_mismatch')
    if seen_requirements != set(requirements) or index.get('requirement_count') != len(requirements):
        raise ValueError('capability_input_integrity_requirement_coverage_mismatch')
    prepared = load_json(analysis / 'analysis-index.json', {})
    if prepared:
        identity = {key: value for key, value in prepared.items()
                    if key not in {'analysis_identity_sha256', 'repository_identity'}}
        if canonical_sha(identity) != prepared.get('analysis_identity_sha256'):
            raise ValueError('capability_input_integrity_analysis_identity_mismatch')
        for rel, expected in prepared.get('files', {}).items():
            path = repo_path(analysis, rel)
            if not path.is_file() or file_sha(path) != expected:
                raise ValueError('capability_input_integrity_prepared_file_mismatch:' + rel)
    return {'complete': True, 'source_block_ids': sorted(seen_blocks),
            'requirement_ids': sorted(seen_requirements), 'batch_count': len(rows),
            'batch_index_sha256': file_sha(analysis / 'model-batches/batch-index.json'),
            'analysis_identity_sha256': prepared.get('analysis_identity_sha256')}


def compact_file_section(workspace: Path, path: Path) -> str:
    """Minify JSON whitespace without dropping any key, list item or string."""
    rel = path.resolve().relative_to(workspace.resolve()).as_posix()
    text = path.read_text(encoding='utf-8')
    if path.suffix.lower() == '.json':
        text = json.dumps(json.loads(text), ensure_ascii=False, separators=(',', ':'))
    return f'===== FILE: {rel} =====\n{text}\n===== END FILE: {rel} ====='


def measure_request(payload: str, *, max_bytes: int, max_input_tokens: int,
                    reserved_tokens: int = 0) -> dict:
    """Bound the final serialized request, including wrappers and prompt text."""
    if max_bytes <= 0 or max_input_tokens <= 0 or reserved_tokens < 0:
        raise ValueError('capability_input_integrity_invalid_budget')
    data = payload.encode('utf-8')
    if len(data) > max_bytes:
        raise ValueError(f'runner_input_too_large:complete_request_bytes={len(data)};limit={max_bytes}')
    try:
        import tiktoken
        counts = {name: len(tiktoken.get_encoding(name).encode(payload, disallowed_special=()))
                  for name in ('o200k_base', 'cl100k_base')}
        # Context policy is conservative, not a claim about an unknown model's tokenizer.
        tokens = (max(counts.values()) * 11 + 9) // 10
        counter = 'max(o200k_base,cl100k_base)+10_percent'
    except ImportError:
        counts, tokens, counter = {}, len(data), 'utf8_byte_upper_bound'
    report = {'request_sha256': 'sha256:' + hashlib.sha256(data).hexdigest(),
              'request_bytes': len(data), 'input_token_estimate': tokens, 'token_counts': counts,
              'token_counter': counter, 'max_bytes': max_bytes, 'max_input_tokens': max_input_tokens,
              'reserved_continuation_tokens': reserved_tokens, 'truncation_allowed': False}
    if tokens + reserved_tokens > max_input_tokens:
        raise ValueError(f'runner_context_budget_exceeded:estimated_input_tokens={tokens};'
                         f'continuation_reserve={reserved_tokens};limit={max_input_tokens}')
    return report


def check_workspace_request(workspace: Path, payload: str, *, max_bytes: int,
                            max_input_tokens: int) -> dict:
    """Persist final input admission without modifying or trimming evidence."""
    try:
        report = measure_request(payload, max_bytes=max_bytes, max_input_tokens=max_input_tokens)
    except ValueError as exc:
        atomic_json(workspace / REPORT_NAME, {'status': 'blocked', 'reason': str(exc),
            'complete_request_bytes': len(payload.encode('utf-8')), 'model_invoked': False,
            'truncation_allowed': False})
        raise
    atomic_json(workspace / REPORT_NAME, {'status': 'ready', 'complete': True, **report})
    return report
