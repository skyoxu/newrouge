"""Lossless Capability transport checks performed before any model request."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path

DEFAULT_MAX_INPUT_TOKENS = 96000
# Codex CLI rejects stdin above 1,048,576 characters. Keep the byte check too;
# it is conservative for non-ASCII evidence and prevents encoding surprises.
CODEX_MAX_TURN_BYTES = 1 * 1024 * 1024
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
    index_path = analysis / 'analysis-index.json'
    if not index_path.is_file():
        raise ValueError('capability_input_integrity_analysis_index_missing')
    prepared = load_json(index_path, {})
    if not prepared:
        raise ValueError('capability_input_integrity_analysis_index_invalid')
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


def _task_view_requirement_refs(row: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("requirement_ids", "semantic_refs", "requirement_refs", "requirement_ref"):
        values = row.get(key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list) or any(not isinstance(value, (str, int)) for value in values):
            raise ValueError(f"capability_input_integrity_invalid_task_requirement_refs:{key}")
        refs.update(str(value).strip() for value in values if str(value).strip())
    return refs


def task_view_batch_rows(workspace: Path, batch_index: dict[str, Any]) -> tuple[list[dict[str, list[dict[str, Any]]]], dict[str, Any]]:
    """Pack complete task-view rows into the Requirement batches they support."""
    rows = batch_index.get("batches")
    if not isinstance(rows, list) or not rows:
        raise ValueError("capability_input_integrity_batch_count_mismatch")
    requirements_by_batch = [
        {str(value) for value in row.get("requirement_ids", [])}
        for row in rows
    ]
    selected: list[dict[str, list[dict[str, Any]]]] = [dict() for _ in rows]
    coverage: dict[str, Any] = {"views": {}, "batch_row_counts": [0] * len(rows)}
    view_dir = workspace / "analysis-input" / "task-views"
    if not view_dir.is_dir():
        return [dict() for _ in rows], coverage
    prepared = load_json(workspace / "analysis-input/analysis-index.json", {})
    expected_view_files = {str(name) for name in prepared.get("files", {})
                           if str(name).startswith("task-views/")}
    discovered_paths = list(view_dir.rglob("*.json"))
    if any(path.parent != view_dir for path in discovered_paths):
        raise ValueError("capability_input_integrity_nested_task_view_unsupported")
    discovered = {"task-views/" + path.name for path in discovered_paths}
    if discovered != expected_view_files:
        raise ValueError("capability_input_integrity_task_view_inventory_mismatch")
    identities: set[str] = set()
    for path in sorted(view_dir.rglob("*.json"), key=lambda value: value.as_posix()):
        if path.is_symlink() or not path.resolve().is_relative_to(view_dir.resolve()):
            raise ValueError(f"capability_input_integrity_unsafe_task_view:{path.name}")
        rel = path.resolve().relative_to(workspace.resolve()).as_posix()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"capability_input_integrity_invalid_task_view:{rel}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"capability_input_integrity_invalid_task_view_rows:{rel}")
        assignments: list[list[int]] = []
        for row_index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"capability_input_integrity_invalid_task_view_row:{rel}:{row_index}")
            identity = item.get("taskmaster_id", item.get("id"))
            if (isinstance(identity, bool) or not isinstance(identity, (str, int))
                    or not str(identity).strip()):
                raise ValueError(f"capability_input_integrity_task_view_id_missing:{rel}:{row_index}")
            identity_key = f"{path.relative_to(view_dir).as_posix()}#{identity}"
            if identity_key in identities:
                raise ValueError(f"capability_input_integrity_duplicate_task_view_id:{identity_key}")
            identities.add(identity_key)
            refs = _task_view_requirement_refs(item)
            unknown_refs = refs.difference(set().union(*requirements_by_batch))
            if unknown_refs:
                raise ValueError(
                    f"capability_input_integrity_unknown_task_requirement_ref:{rel}:{row_index}:"
                    f"{','.join(sorted(unknown_refs))}"
                )
            matches = [index for index, allowed in enumerate(requirements_by_batch)
                       if refs.intersection(allowed)] or [0]
            assignments.append(matches)
            for index in matches:
                selected[index].setdefault(rel, []).append(item)
                coverage["batch_row_counts"][index] += 1
        coverage["views"][rel] = {
            "row_count": len(payload),
            "sha256": file_sha(path),
            "row_keys": [f"{path.relative_to(view_dir).as_posix()}#{item.get('taskmaster_id', item.get('id'))}"
                         for item in payload],
            "assigned_batch_indexes": assignments,
        }
    return selected, coverage


def task_view_batch_sections(workspace: Path, batch_index: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Serialize complete task-view rows for their assigned model batches."""
    selected, coverage = task_view_batch_rows(workspace, batch_index)
    sections: list[str] = []
    for view_rows in selected:
        if not view_rows:
            sections.append("")
            continue
        fragments = [
            "===== COMPLETE TASK-VIEW ROWS FOR THIS REQUIREMENT BATCH =====",
            "Rows are complete authoritative objects. Preserve every field and value; "
            "a row may repeat when it references multiple Requirement batches.",
        ]
        for rel in sorted(view_rows):
            fragments.extend([
                f"===== FILE: {rel} (batch-scoped complete rows) =====",
                json.dumps(view_rows[rel], ensure_ascii=False, separators=(",", ":")),
                f"===== END FILE: {rel} (batch-scoped complete rows) =====",
            ])
        sections.append("\n".join(fragments))
    return sections, coverage


def measure_request(payload: str, *, max_bytes: int, max_input_tokens: int,
                    reserved_tokens: int = 0) -> dict:
    """Bound the final serialized request, including wrappers and prompt text."""
    if max_bytes <= 0 or max_input_tokens <= 0 or reserved_tokens < 0:
        raise ValueError('capability_input_integrity_invalid_budget')
    data = payload.encode('utf-8')
    if len(payload) > max_bytes:
        raise ValueError(f'runner_input_too_large:complete_request_chars={len(payload)};'
                         f'complete_request_bytes={len(data)};limit={max_bytes}')
    if len(data) > max_bytes:
        raise ValueError(f'runner_input_too_large:complete_request_chars={len(payload)};'
                         f'complete_request_bytes={len(data)};limit={max_bytes}')
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
              'request_chars': len(payload), 'request_bytes': len(data), 'input_token_estimate': tokens, 'token_counts': counts,
              'token_counter': counter, 'max_bytes': max_bytes, 'max_input_tokens': max_input_tokens,
              'reserved_continuation_tokens': reserved_tokens, 'truncation_allowed': False}
    if tokens + reserved_tokens > max_input_tokens:
        raise ValueError(f'runner_context_budget_exceeded:estimated_input_tokens={tokens};'
                         f'continuation_reserve={reserved_tokens};limit={max_input_tokens};'
                         f'complete_request_chars={len(payload)};complete_request_bytes={len(data)}')
    return report


def schema_max_json_chars(schema: dict[str, Any]) -> int:
    """Conservative character bound for one JSON value accepted by a bounded schema."""
    kind = schema.get("type")
    if "const" in schema:
        return len(json.dumps(schema["const"], ensure_ascii=False, separators=(",", ":")))
    if isinstance(schema.get("enum"), list):
        return max(
            (len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
             for value in schema["enum"]),
            default=2,
        )
    if kind == "string":
        if isinstance(schema.get("maxLength"), int):
            # JSON escaping can expand each character to six ASCII characters.
            return schema["maxLength"] * 6 + 2
        raise ValueError("capability_input_integrity_unbounded_schema_string")
    if kind in {"integer", "number"}:
        if isinstance(schema.get("maximum"), (int, float)) and isinstance(schema.get("minimum"), (int, float)):
            return max(len(str(schema["maximum"])), len(str(schema["minimum"]))) + 2
        raise ValueError("capability_input_integrity_unbounded_schema_number")
    if kind == "boolean":
        return 5
    if kind == "array":
        count = schema.get("maxItems")
        if not isinstance(count, int) or count < 0:
            raise ValueError("capability_input_integrity_unbounded_schema_array")
        item = schema.get("items")
        if not isinstance(item, dict):
            raise ValueError("capability_input_integrity_invalid_schema_array")
        return 2 + count * schema_max_json_chars(item) + max(0, count - 1)
    if kind == "object":
        props = schema.get("properties")
        required = schema.get("required")
        if (not isinstance(props, dict) or not isinstance(required, list)
                or schema.get("additionalProperties", False) is not False):
            raise ValueError("capability_input_integrity_invalid_schema_object")
        if set(required) != set(props):
            raise ValueError("capability_input_integrity_optional_schema_fields_unsupported")
        members = []
        for key, child in props.items():
            members.append(len(json.dumps(str(key), ensure_ascii=False)) + 1 + schema_max_json_chars(child))
        return 2 + sum(members) + max(0, len(members) - 1)
    raise ValueError("capability_input_integrity_unsupported_output_schema")


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
