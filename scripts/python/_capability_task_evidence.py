"""Reversible task-view transport. No semantic extraction or inferred links."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from _planning_skill_common import (
    SENSITIVE_CAPABILITY_KEYS, atomic_json, file_sha, load_json, repo_path,
)

VERSION = "newrouge.task-evidence.v1"
CATALOG = "task-evidence-references.json"
AUDIT_DIR = "evidence-transport"
MODE_ENV = "SC_CAPABILITY_TASK_VIEW_ENCODING"
GUIDE = (
    "Use relation_index.declared_links for declared links; omitted optional links are undeclared. "
    "Use content_objects for all semantic text. Do not infer undeclared relationships. "
    "Every indexed target has a body or an explicit external source pointer in this request. "
    "For each task and view, combine shared_fields with that view's view_specific_fields. "
    "The fields are disjoint; absent fields stay absent. view_order preserves original row order. "
    "Return original task-view keys and IDs, never transport object addresses."
)
TASK_INSTRUCTION = (
    "Analyze every complete Task View row below as auxiliary ownership and acceptance evidence. "
    "Preserve task identity, intent, Acceptance/test meaning, and exact Requirement refs. "
    "Do not infer Capability grouping or omit any row. This is a task-only batch: "
    "return source_block_analyses and requirement_analyses as empty arrays."
)
REQUIREMENT_FIELDS = ("requirement_ids", "semantic_refs", "requirement_refs", "requirement_ref")


def encoding_mode() -> str:
    mode = os.environ.get(MODE_ENV, "raw")
    if mode not in {"raw", "lossless-v1"}:
        raise ValueError("capability_input_integrity_unknown_task_encoding:" + mode)
    return mode


def workspace_encoding(workspace: Path) -> str:
    # Freeze the setting at prepare time: changing the environment between
    # candidates must never change their evidence representation.
    index = load_json(workspace / "analysis-input/analysis-index.json", {})
    mode = index.get("task_view_encoding", "raw")
    if mode not in {"raw", "lossless-v1"}:
        raise ValueError("capability_input_integrity_unknown_task_encoding:" + str(mode))
    return mode


def json_value(value: Any) -> str:
    """Canonical JSON equality, including bool/number and int/float distinctions."""
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("capability_input_integrity_non_string_json_key")
        for child in value.values():
            json_value(child)
    elif isinstance(value, list):
        for child in value:
            json_value(child)
    elif value is not None and type(value) not in (str, bool, int, float):
        raise ValueError("capability_input_integrity_non_json_value")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def value_sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json_value(value).encode("utf-8")).hexdigest()


def pointer_part(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("capability_input_integrity_invalid_json_pointer")
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def identity(row: dict) -> str:
    value = row.get("taskmaster_id", row.get("id"))
    if type(value) not in (int, str) or not str(value).strip():
        raise ValueError("capability_input_integrity_task_view_id_missing")
    return str(value)


def compress(payload: dict) -> dict:
    """Encode complete objects; context (including Source Blocks) stays verbatim."""
    json_value(payload)
    views = payload["task_views"]
    if not isinstance(views, dict):
        raise ValueError("capability_input_integrity_invalid_task_views")
    grouped: dict[str, dict[str, dict]] = {}
    order = {}
    for path, rows in views.items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("capability_input_integrity_invalid_task_view_rows:" + path)
        order[path] = []
        seen = set()
        for row in rows:
            key = identity(row)
            if key in seen:
                raise ValueError("capability_input_integrity_duplicate_task_view_id:" + path + "#" + key)
            seen.add(key)
            order[path].append(key)
            grouped.setdefault(key, {})[path] = row
    tasks = {}
    for key, rows in grouped.items():
        first = next(iter(rows.values()))
        shared = {field: value for field, value in first.items()
                  if len(rows) > 1 and all(field in row and json_value(row[field]) == json_value(value)
                                           for row in rows.values())}
        tasks[key] = {
            "shared_fields": shared,
            "view_specific_fields": {path: {field: value for field, value in row.items() if field not in shared}
                                     for path, row in rows.items()},
        }
    return copy.deepcopy({
        "schema_version": VERSION,
        "relation_index": {"view_order": order},
        "content_objects": {"tasks": tasks, "context": {key: value for key, value in payload.items()
                                                        if key != "task_views"}},
    })


def expand(packet: dict) -> dict:
    if packet.get("schema_version") != VERSION:
        raise ValueError("capability_input_integrity_unknown_task_evidence_version")
    objects = packet["content_objects"]
    context = copy.deepcopy(objects["context"])
    if "task_views" in context:
        raise ValueError("capability_input_integrity_reserved_context_key")
    views, used = {}, set()
    for path, keys in packet["relation_index"]["view_order"].items():
        views[path] = []
        for key in keys:
            if (path, key) in used:
                raise ValueError("capability_input_integrity_duplicate_encoded_row")
            used.add((path, key))
            task = objects["tasks"][key]
            shared, different = task["shared_fields"], task["view_specific_fields"][path]
            if shared.keys() & different.keys():
                raise ValueError("capability_input_integrity_shared_field_collision")
            row = copy.deepcopy({**shared, **different})
            if identity(row) != key:
                raise ValueError("capability_input_integrity_encoded_identity_mismatch")
            views[path].append(row)
    expected = {(path, key) for key, task in objects["tasks"].items() for path in task["view_specific_fields"]}
    if used != expected:
        raise ValueError("capability_input_integrity_unreferenced_encoded_object")
    context["task_views"] = views
    return context


def validate_roundtrip(original: dict, packet: dict) -> dict:
    expanded = expand(packet)
    if json_value(original) != json_value(expanded):
        raise ValueError("capability_input_integrity_task_evidence_roundtrip_mismatch")
    ids = [path + "#" + identity(row) for path, rows in original["task_views"].items() for row in rows]
    def object_count(value: Any) -> int:
        if isinstance(value, dict):
            return 1 + sum(object_count(child) for child in value.values())
        return sum(object_count(child) for child in value) if isinstance(value, list) else 0
    return {"roundtrip_equal": True, "coverage": 1.0, "task_view_keys": ids,
            "original_sha256": value_sha(original), "expanded_sha256": value_sha(expanded),
            "packet_sha256": value_sha(packet), "original_row_count": len(ids),
            "expanded_row_count": len(ids), "original_object_count": object_count(original),
            "encoded_object_count": object_count(packet),
            "encoded_task_count": len(packet["content_objects"]["tasks"])}


def validate_partition(original: list[str], retained: list[str], excluded: list[str]) -> None:
    if any(len(values) != len(set(values)) for values in (original, retained, excluded)):
        raise ValueError("capability_input_integrity_duplicate_partition_id")
    if set(retained) & set(excluded) or set(original) != set(retained) | set(excluded):
        raise ValueError("capability_input_integrity_exclusion_partition_mismatch")


def assert_blinded(value: Any, path: str = "") -> None:
    """Validate structured historical answers, not words in authored GDD text."""
    if isinstance(value, dict):
        schema = value.get("schema_version")
        if isinstance(schema, str) and schema in {"newrouge.capabilities.v1", "newrouge.capability-reference.v1"}:
            raise ValueError("capability_input_integrity_historical_capability_payload:" + path)
        for key, child in value.items():
            if key in SENSITIVE_CAPABILITY_KEYS:
                raise ValueError("capability_input_integrity_unblinded_field:" + path + "/" + key)
            assert_blinded(child, path + "/" + pointer_part(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_blinded(child, path + "/" + str(index))


def _refs(row: dict, field: str) -> list[str]:
    value = row[field]
    values = [value] if type(value) in (str, int) else value
    if not isinstance(values, list) or any(type(item) not in (str, int) or not str(item).strip() for item in values):
        raise ValueError("capability_input_integrity_invalid_declared_relation:" + field)
    # Match the existing task Requirement resolver; preserve the original
    # field value in the body, even when its declared ID has surrounding space.
    return [str(item).strip() if field in REQUIREMENT_FIELDS else str(item) for item in values]


def freeze_reference_catalog(root: Path, rows: list[dict]) -> dict:
    """Resolve explicit ADR identifiers and exact test paths once, before isolation."""
    requested = {"adr": set(), "test": set()}
    for row in rows:
        for field, kind in (("adr_refs", "adr"), ("test_refs", "test")):
            if field in row:
                requested[kind].update(_refs(row, field))
    result = {}
    for kind, refs in requested.items():
        result[kind] = {}
        for ref in sorted(refs):
            if kind == "adr" and ref.startswith("ADR-") and ref[4:].isdigit():
                matches = [path for path in (root / "docs/adr").glob("*.md")
                           if path.stem == ref or path.stem.startswith(ref + "-")]
            else:
                candidate = repo_path(root, ref)
                matches = [candidate] if candidate.is_file() else []
            if len(matches) == 1 and not matches[0].is_symlink():
                path = repo_path(root, matches[0])
                result[kind][ref] = {"path": path.relative_to(root.resolve()).as_posix(),
                                     "name": path.name, "sha256": file_sha(path), "status": "valid"}
            else:
                result[kind][ref] = {"status": "blocking_error", "reason": "missing_or_ambiguous_target"}
    return result


def declared_relations(payload: dict, catalog: dict) -> tuple[list[dict], dict]:
    """Index only schema-declared links. Unknown fields stay in semantic objects."""
    evidence = payload.get("related_evidence", {})
    requirements = evidence.get("requirements", [])
    blocks = evidence.get("source_blocks", [])
    masters = evidence.get("master_tasks", [])
    targets = {"requirement": {row["requirement_id"] for row in requirements},
               "source_block": {row["block_id"] for row in blocks},
               "task": {identity(row) for row in masters}}
    for kind, rows, key in (("requirement", requirements, "requirement_id"), ("source_block", blocks, "block_id")):
        if len(rows) != len(targets[kind]):
            raise ValueError("capability_input_integrity_duplicate_evidence_id:" + key)
    owners = []
    for path, rows in payload["task_views"].items():
        owners.extend((path + "#" + identity(row), row, {"taskmaster_id": "task",
                       **{field: "requirement" for field in REQUIREMENT_FIELDS},
                       "source_block_ids": "source_block", "adr_refs": "adr", "test_refs": "test"}) for row in rows)
    owners.extend((row["requirement_id"], row, {"source_block_ids": "source_block",
                   "dependency_ids": "requirement", "adr_refs": "adr", "test_refs": "test"}) for row in requirements)
    links, pointers = [], {"adr": {}, "test": {}}
    for owner, row, fields in owners:
        for field, kind in fields.items():
            if field not in row:
                # Absence is undeclared, never evidence that a relation exists.
                continue
            refs = _refs(row, field)
            for ref in refs:
                if kind in pointers:
                    target = catalog.get(kind, {}).get(ref, {})
                    valid = target.get("status") == "valid"
                    if valid:
                        pointers[kind][ref] = target
                else:
                    valid = ref in targets[kind]
                if not valid:
                    raise ValueError(f"capability_input_integrity_declared_target_missing:{owner}:{field}:{ref}")
            links.append({"owner": owner, "field": field, "kind": kind, "refs": refs, "status": "valid"})
    return links, pointers


def expansion_map(payload: dict, packet: dict, origins: dict | None = None) -> dict:
    """One reversible address for every encoded field, including empty values."""
    entries = []
    for path, rows in payload["task_views"].items():
        for ordinal, row in enumerate(rows):
            key = identity(row)
            task = packet["content_objects"]["tasks"][key]
            for field, value in row.items():
                suffix = ("shared_fields" if field in task["shared_fields"]
                          else "view_specific_fields/" + pointer_part(path))
                source = copy.deepcopy((origins or {}).get(path + "#" + key, {}))
                if source:
                    source["json_pointer"] += "/" + pointer_part(field)
                    source["original_json_pointer"] += "/" + pointer_part(field)
                    source["value_sha256"] = value_sha(value)
                entries.append({
                    "encoded_pointer": f"/content_objects/tasks/{pointer_part(key)}/{suffix}/{pointer_part(field)}",
                    "input_pointer": f"/task_views/{pointer_part(path)}/{ordinal}/{pointer_part(field)}",
                    "sha256": value_sha(value), "source": source,
                })
    for field, value in payload.items():
        if field != "task_views":
            entries.append({"encoded_pointer": "/content_objects/context/" + pointer_part(field),
                            "input_pointer": "/" + pointer_part(field), "sha256": value_sha(value)})
    return {"schema_version": VERSION + ".expansion-map", "input_file": "authoritative-input.json",
            "input_sha256": value_sha(payload), "packet_sha256": value_sha(packet), "fields": entries}


def validate_expansion_map(payload: dict, packet: dict, mapping: dict, *, workspace: Path | None = None) -> None:
    if mapping["input_sha256"] != value_sha(payload) or mapping["packet_sha256"] != value_sha(packet):
        raise ValueError("capability_input_integrity_expansion_map_identity_mismatch")
    expected = expansion_map(payload, packet)["fields"]
    actual = [{key: row[key] for key in ("encoded_pointer", "input_pointer", "sha256")} for row in mapping["fields"]]
    if json_value(actual) != json_value([{key: row[key] for key in ("encoded_pointer", "input_pointer", "sha256")}
                                        for row in expected]):
        raise ValueError("capability_input_integrity_expansion_map_coverage_mismatch")
    for row in mapping["fields"]:
        if (value_sha(resolve_pointer(payload, row["input_pointer"])) != row["sha256"]
                or value_sha(resolve_pointer(packet, row["encoded_pointer"])) != row["sha256"]):
            raise ValueError("capability_input_integrity_expansion_map_value_mismatch")
    if workspace is not None:
        origins, context_origins = _origins(workspace, payload)
        expected_map = expansion_map(payload, packet, origins)
        expected_map["context_origins"] = context_origins
        if json_value(expected_map) != json_value(mapping):
            raise ValueError("capability_input_integrity_expansion_source_mismatch")


def select_smaller(raw: str, encoded: str, measure_text: Callable[[str], str]) -> tuple[str, dict]:
    from _capability_input_integrity import measure_request
    measurements = {name: measure_request(measure_text(text), max_bytes=2**63 - 1, max_input_tokens=2**63 - 1)
                    for name, text in (("raw", raw), ("encoded", encoded))}
    before, after = measurements["raw"], measurements["encoded"]
    smaller = (after["request_bytes"] < before["request_bytes"]
               and after["input_token_estimate"] < before["input_token_estimate"])
    selected = "lossless-v1" if smaller else "raw"
    return (encoded if smaller else raw), {
        "selected_encoding": selected, "measurements": measurements,
        "byte_savings_ratio": 1 - after["request_bytes"] / max(1, before["request_bytes"]),
        "token_savings_ratio": 1 - after["input_token_estimate"] / max(1, before["input_token_estimate"]),
        "reason": "smaller_complete_request" if smaller else "no_complete_request_savings",
    }


def _complete_related_evidence(workspace: Path, rows: dict) -> dict:
    from _capability_input_integrity import task_related_evidence
    evidence = task_related_evidence(workspace, rows)
    analysis = workspace / "analysis-input"
    all_requirements = load_json(analysis / "semantic-requirements.v1.json", {})["requirements"]
    requirements = {row["requirement_id"]: row for row in all_requirements}
    selected = {row["requirement_id"] for row in evidence["requirements"]}
    pending = list(selected)
    # Explicit dependency closure only; cycles terminate and are not rewritten.
    while pending:
        row = requirements[pending.pop()]
        for ref in _refs(row, "dependency_ids") if "dependency_ids" in row else []:
            if ref not in requirements:
                raise ValueError("capability_input_integrity_declared_target_missing:dependency_ids:" + ref)
            if ref not in selected:
                selected.add(ref)
                pending.append(ref)
    evidence["requirements"] = [row for row in all_requirements if row["requirement_id"] in selected]
    source_ids = set()
    for row in evidence["requirements"] + [row for items in rows.values() for row in items]:
        if "source_block_ids" in row:
            source_ids.update(_refs(row, "source_block_ids"))
    all_blocks = load_json(analysis / "source-blocks.v1.json", {})["blocks"]
    evidence["source_blocks"] = [row for row in all_blocks if row["block_id"] in source_ids]
    if source_ids != {row["block_id"] for row in evidence["source_blocks"]}:
        raise ValueError("capability_input_integrity_declared_target_missing:source_block_ids")
    return evidence


def _origins(workspace: Path, payload: dict) -> tuple[dict, list[dict]]:
    analysis = workspace / "analysis-input"
    index = load_json(analysis / "analysis-index.json", {})
    transforms = {row["analysis_path"]: row for row in index.get("blinding_transformations", [])}
    for rel, expected in index.get("files", {}).items():
        if file_sha(repo_path(analysis, rel)) != expected:
            raise ValueError("capability_input_integrity_prepared_file_mismatch:" + rel)
    origins = {}
    for rel, rows in payload["task_views"].items():
        path = repo_path(analysis, rel)
        all_rows = load_json(path)
        positions = {identity(row): ordinal for ordinal, row in enumerate(all_rows)}
        for row in rows:
            key = identity(row)
            ordinal = positions[key]
            if json_value(all_rows[ordinal]) != json_value(row):
                raise ValueError("capability_input_integrity_origin_row_mismatch:" + rel + "#" + key)
            origins[rel + "#" + key] = {
                "prepared_file": "analysis-input/" + rel, "json_pointer": "/" + str(ordinal),
                "file_sha256": file_sha(path), "row_sha256": value_sha(row),
                "original_file": transforms.get(rel, {}).get("source_path", "analysis-input/" + rel),
                "original_json_pointer": "/" + str(ordinal),
                "original_file_sha256": transforms.get(rel, {}).get("source_sha256", file_sha(path)),
            }
    context_origins = []
    for field, rel, collection, id_field in (
        ("requirements", "semantic-requirements.v1.json", "requirements", "requirement_id"),
        ("source_blocks", "source-blocks.v1.json", "blocks", "block_id"),
    ):
        source = load_json(analysis / rel, {})
        positions = {row[id_field]: ordinal for ordinal, row in enumerate(source[collection])}
        for ordinal, row in enumerate(payload["related_evidence"][field]):
            pointer = f"/{collection}/{positions[row[id_field]]}"
            if json_value(resolve_pointer(source, pointer)) != json_value(row):
                raise ValueError("capability_input_integrity_origin_row_mismatch:" + row[id_field])
            context_origins.append({"input_pointer": f"/related_evidence/{field}/{ordinal}",
                "prepared_file": "analysis-input/" + rel, "json_pointer": pointer,
                "file_sha256": file_sha(analysis / rel), "row_sha256": value_sha(row),
                "original_file": transforms.get(rel, {}).get("source_path", "analysis-input/" + rel),
                "original_json_pointer": pointer,
                "original_file_sha256": transforms.get(rel, {}).get("source_sha256", file_sha(analysis / rel))})
    from _capability_input_integrity import task_master_rows
    for field, rel in (("master_tasks", "task-master.json"), ("readiness", "readiness-summary.json")):
        source = load_json(analysis / rel, {})
        if field == "master_tasks":
            all_rows = task_master_rows(source)
            prefix = "/master/tasks" if "master" in source else "/tasks"
            keys = {identity(row): ordinal for ordinal, row in enumerate(all_rows)}
        else:
            all_rows, prefix = source.get("tasks", []), "/tasks"
            keys = {str(row["task_id"]): ordinal for ordinal, row in enumerate(all_rows)}
        for ordinal, row in enumerate(payload["related_evidence"][field]):
            key = identity(row) if field == "master_tasks" else str(row["task_id"])
            pointer = prefix + "/" + str(keys[key])
            if json_value(resolve_pointer(source, pointer)) != json_value(row):
                raise ValueError("capability_input_integrity_origin_row_mismatch:" + key)
            context_origins.append({"input_pointer": f"/related_evidence/{field}/{ordinal}",
                "prepared_file": "analysis-input/" + rel, "json_pointer": pointer,
                "file_sha256": file_sha(analysis / rel), "row_sha256": value_sha(row),
                "original_file": transforms.get(rel, {}).get("source_path", "analysis-input/" + rel),
                "original_file_sha256": transforms.get(rel, {}).get("source_sha256", file_sha(analysis / rel))})
    for key, value in payload["related_evidence"].get("readiness_scope", {}).items():
        context_origins.append({"input_pointer": "/related_evidence/readiness_scope/" + pointer_part(key),
            "prepared_file": "analysis-input/readiness-summary.json", "json_pointer": "/" + pointer_part(key),
            "file_sha256": file_sha(analysis / "readiness-summary.json"), "value_sha256": value_sha(value)})
    return origins, context_origins


def validate_packet(payload: dict, packet: dict, catalog: dict) -> dict:
    """Reject extra side-channel content as well as missing semantic content."""
    assert_blinded(payload)
    assert_blinded(packet)
    expected = compress(payload)
    links, pointers = declared_relations(payload, catalog)
    expected["relation_index"]["declared_links"] = links
    expected["source_pointers"] = pointers
    if json_value(expected) != json_value(packet):
        raise ValueError("capability_input_integrity_packet_projection_mismatch")
    return validate_roundtrip(payload, packet)


def _raw_request(base: str, payload: dict) -> str:
    return "\n\n".join([base, TASK_INSTRUCTION,
        "===== COMPLETE TASK-VIEW ROWS =====\n" + json.dumps(payload["task_views"], ensure_ascii=False, separators=(",", ":")),
        "===== COMPLETE RELATED TASK EVIDENCE =====\n" + json.dumps(payload["related_evidence"], ensure_ascii=False,
            separators=(",", ":")) + "\n===== END COMPLETE RELATED TASK EVIDENCE ====="])


def build_task_request(workspace: Path, *, base: str, rows: dict, label: str,
                       measure_text: Callable[[str], str]) -> str:
    """Shared admission for Codex/API. Audits never become model attachments."""
    from _capability_input_integrity import task_related_evidence
    if workspace_encoding(workspace) == "raw":
        return _raw_request(base, {"task_views": rows, "related_evidence": task_related_evidence(workspace, rows)})
    audit = workspace / AUDIT_DIR / label
    try:
        payload = {"task_views": rows, "related_evidence": _complete_related_evidence(workspace, rows)}
        assert_blinded(payload)
        catalog_path = workspace / "analysis-input" / CATALOG
        index = load_json(workspace / "analysis-input/analysis-index.json", {})
        if (not catalog_path.is_file() or index.get("files", {}).get(CATALOG) != file_sha(catalog_path)):
            raise ValueError("capability_input_integrity_reference_catalog_missing_or_changed")
        links, pointers = declared_relations(payload, load_json(catalog_path))
        packet = compress(payload)
        packet["relation_index"]["declared_links"] = links
        packet["source_pointers"] = pointers
        assert_blinded(packet)
        coverage = validate_packet(payload, packet, load_json(catalog_path))
        origins, context_origins = _origins(workspace, payload)
        mapping = expansion_map(payload, packet, origins)
        mapping["context_origins"] = context_origins
        validate_expansion_map(payload, packet, mapping, workspace=workspace)
        encoded = "\n\n".join([base, TASK_INSTRUCTION, GUIDE,
            "===== LOSSLESS TASK EVIDENCE =====\n" + json.dumps(packet, ensure_ascii=False, separators=(",", ":"))])
        text, metrics = select_smaller(_raw_request(base, payload), encoded, measure_text)
        metrics.update(coverage)
        metrics.update(status="ready", model_comprehension="not_evaluated", blinding_checked=True,
                       requirement_count=len(payload["related_evidence"]["requirements"]),
                       source_block_count=len(payload["related_evidence"]["source_blocks"]),
                       declared_link_count=len(links))
        # These files are machine-only; the model receives exactly `text`.
        atomic_json(audit / "authoritative-input.json", payload)
        atomic_json(audit / "packet.json", packet)
        atomic_json(audit / "expansion-map.json", mapping)
        atomic_json(audit / "metrics.json", metrics)
        return text
    except (ValueError, KeyError, TypeError, OSError) as exc:
        atomic_json(audit / "metrics.json", {"status": "blocked", "model_invoked": False, "error": str(exc)})
        raise
