"""Governed 3C triplet compilation and binding producer using shared commit/journal.

Consumes a verified ok/stable Story 3.1 task-change preview plus explicit request,
revalidates 3A source audit proof (verify_current_proof), 3B committed adoption
(read_committed), optional protection/manifest anti-weakening and legacy A
chapter3-task-scope.json, compiles business views and master tasks via
compile_task_triplet/build_taskmaster_tasks and strict TaskJoinContext, allocates
permanent taskmaster_id/NG/GM identities ONLY during prepare, merges live Task
status inside the apply commit lock, and publishes catalog.v1.json last.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import base64
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import datetime as dt
from functools import wraps
import json
from pathlib import Path
import re
from typing import Any

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_inventory as inventory
import _b_route_operation_scope as op_scope
import _b_route_protection as protection
import _b_route_records as records
import _b_route_source_audit as source_audit
import _b_route_sources as sources
import _b_route_task_preview as task_preview
import _planning_apply_journal as journal
import build_taskmaster_tasks
import chapter3_task_scope
import compile_task_triplet


REQUEST_SCHEMA = journal.TASK_COMPILATION_REQUEST
OPERATION_SCHEMA = journal.TASK_COMPILATION_SCHEMA
PRODUCER = "task_compilation"
TRIPLET = {
    "master": ".taskmaster/tasks/tasks.json",
    "back": ".taskmaster/tasks/tasks_back.json",
    "gameplay": ".taskmaster/tasks/tasks_gameplay.json",
}
TRIPLET_SCHEMAS = {
    ".taskmaster/tasks/tasks.json": "newrouge.taskmaster-master.v1",
    ".taskmaster/tasks/tasks_back.json": "newrouge.taskmaster-back.v1",
    ".taskmaster/tasks/tasks_gameplay.json": "newrouge.taskmaster-gameplay.v1",
}
FLAGS = {
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}
EVENTS_BASE = "logs/ci/b-route-task-compilation"
_NG_RE = re.compile(r"^NG-(\d+)$")
_GM_RE = re.compile(r"^GM-(\d+)$")
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _fail(
    code: codec.ReasonCode,
    expected: Any,
    actual: Any,
    *,
    operation_id: str | None = None,
    resume_ref: str | None = None,
    stage: codec.Stage = codec.Stage.BUNDLE,
) -> None:
    raise codec.CodecError(
        codec.Diagnostic(code, stage, operation_id, expected, actual, resume_ref)
    )


def _require(
    condition: Any,
    expected: Any,
    actual: Any,
    code: codec.ReasonCode = codec.ReasonCode.CONFLICT,
    *,
    operation_id: str | None = None,
    resume_ref: str | None = None,
    stage: codec.Stage = codec.Stage.BUNDLE,
) -> None:
    if not condition:
        _fail(code, expected, actual, operation_id=operation_id, resume_ref=resume_ref, stage=stage)


def _validate_file_id(value: Any, label: str) -> str:
    _require(
        type(value) is str
        and _FILE_ID_RE.fullmatch(value) is not None
        and value.split(".", 1)[0].upper() not in _WIN_RESERVED,
        f"portable FileId for {label}",
        value,
        codec.ReasonCode.INVALID_ARGUMENT,
        stage=codec.Stage.PATH,
    )
    codec.validate_business_id(value)
    return value


def _events_path(root: Path, operation_id: str) -> Path:
    _validate_file_id(operation_id, "operation_id")
    rel = f"{EVENTS_BASE}/{operation_id}/events.jsonl"
    return journal._operation_path(root, rel)


def append_event(root: Path, operation_id: str, stage: str, status: str, detail: dict[str, Any] | None = None) -> str:
    """Append one deterministic JSONL audit event under logs/ci/b-route-task-compilation/<op>/events.jsonl."""
    path = _events_path(root, operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "newrouge.b-route-task-compilation-event.v1",
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "producer": PRODUCER,
        "operation_id": operation_id,
        "stage": stage,
        "status": status,
        "detail": detail or {},
        **FLAGS,
    }
    line = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line)
        stream.flush()
    return path.relative_to(Path(root).resolve()).as_posix()


def _dedupe_owned_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for ref in refs:
        key = codec.canonical_digest(ref)
        if key not in seen:
            seen[key] = deepcopy(ref)
    return [seen[k] for k in sorted(seen)]


def _read_bytes(root: Path, relative: str, *, optional: bool = False) -> bytes | None:
    path = journal._operation_path(root, relative)
    if optional and not path.exists():
        return None
    return codec.read_reference_bytes(root, relative)


class CompilationSnapshot:
    """Tracks non-triplet raw digests and triplet definition projections before apply freeze."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.files: dict[str, str | None] = {}
        self.triplet_projections: dict[str, str] = {}
        self.directories: dict[str, list[str]] = {}
        self.native_capture = None

    def read(self, name: str, *, optional: bool = False) -> bytes | None:
        raw = _read_bytes(self.root, name, optional=optional)
        digest = codec.raw_digest(raw) if raw is not None else None
        if name.casefold() in {p.casefold() for p in TRIPLET.values()}:
            _require(raw is not None, "existing Taskmaster triplet file", name, codec.ReasonCode.FILE_NOT_FOUND)
            proj = records.task_document_digest(name, raw)
            _require(
                name not in self.triplet_projections or self.triplet_projections[name] == proj,
                "stable Taskmaster triplet projection",
                name,
                codec.ReasonCode.INPUT_STALE,
            )
            self.triplet_projections[name] = proj
            return raw
        _require(
            name not in self.files or self.files[name] == digest,
            "stable observed compilation input",
            name,
            codec.ReasonCode.INPUT_STALE,
        )
        self.files[name] = digest
        return raw

    def ref(self, ref: dict[str, Any]) -> Any:
        _require(
            type(ref) is dict and set(ref) == {"path", "schema_version", "raw_digest"},
            "complete raw-bound reference",
            ref,
            codec.ReasonCode.INVALID_REFERENCE,
        )
        raw = self.read(ref["path"])
        _require(
            codec.raw_digest(raw) == ref["raw_digest"],
            ref["raw_digest"],
            ref["path"],
            codec.ReasonCode.DIGEST_MISMATCH,
        )
        if ref["schema_version"] == "raw.bytes.v1":
            return raw
        value = codec.strict_json_loads(raw)
        _require(
            type(value) is dict and value.get("schema_version") == ref["schema_version"],
            ref["schema_version"],
            ref["path"],
            codec.ReasonCode.SCHEMA_MISMATCH,
        )
        return value

    def verify(self) -> None:
        for name, expected in list(self.files.items()):
            raw = _read_bytes(self.root, name, optional=True)
            actual = codec.raw_digest(raw) if raw is not None else None
            _require(actual == expected, expected, name, codec.ReasonCode.INPUT_STALE)
        docs = {}
        for key, path in TRIPLET.items():
            if path in self.triplet_projections:
                raw = _read_bytes(self.root, path)
                actual_proj = records.task_document_digest(path, raw)
                _require(
                    actual_proj == self.triplet_projections[path],
                    self.triplet_projections[path],
                    actual_proj,
                    codec.ReasonCode.INPUT_STALE,
                    resume_ref=path,
                )
                docs[key] = codec.strict_json_loads(raw)
        if len(docs) == 3:
            records.TaskJoinContext(**docs).indexes()


def _merge_subtask_statuses(target_subtasks: list[dict[str, Any]], live_subtasks: list[dict[str, Any]]) -> None:
    live_by_id = {
        sub["id"]: sub for sub in live_subtasks if isinstance(sub, dict) and sub.get("id") is not None
    }
    for index, sub in enumerate(target_subtasks):
        if not isinstance(sub, dict):
            continue
        live_sub = None
        if sub.get("id") is not None:
            live_sub = live_by_id.get(sub["id"])
        elif index < len(live_subtasks) and isinstance(live_subtasks[index], dict):
            live_sub = live_subtasks[index]
        if live_sub is None:
            continue
        if "status" in live_sub:
            _require(
                type(live_sub["status"]) is str and live_sub["status"] in inventory.VIEW_STATES,
                "valid live subtask status",
                live_sub["status"],
                codec.ReasonCode.INVALID_ENUM,
            )
            sub["status"] = live_sub["status"]
        else:
            sub.pop("status", None)


def merge_live_triplet_payload(path: str, live_before_raw: bytes, frozen_after_payload: Any) -> Any:
    """Merge live Task and direct subtask status into a compiled triplet payload without changing definitions."""
    live = codec.strict_json_loads(live_before_raw)
    merged = deepcopy(frozen_after_payload)
    norm = path.casefold()
    if norm == ".taskmaster/tasks/tasks.json":
        _require(
            type(live) is dict and type(live.get("master")) is dict and type(live["master"].get("tasks")) is list,
            "valid live master tasks container",
            path,
            codec.ReasonCode.INVALID_TYPE,
        )
        live_by_id = {row["id"]: row for row in live["master"]["tasks"]}
        for row in merged["master"]["tasks"]:
            live_row = live_by_id.get(row["id"])
            if live_row is None:
                continue
            status = live_row.get("status")
            _require(
                type(status) is str and status in inventory.MASTER_STATES,
                "valid live master Task status",
                status,
                codec.ReasonCode.INVALID_ENUM,
            )
            row["status"] = status
            if "subtasks" in row and "subtasks" in live_row:
                _merge_subtask_statuses(row["subtasks"], live_row["subtasks"])
    elif norm in (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"):
        _require(type(live) is list, "valid live business-view task list", path, codec.ReasonCode.INVALID_TYPE)
        live_by_key = {(row["id"], row["taskmaster_id"]): row for row in live}
        for row in merged:
            live_row = live_by_key.get((row["id"], row["taskmaster_id"]))
            if live_row is None:
                continue
            status = live_row.get("status")
            _require(
                "status" in live_row and type(status) is str and status in inventory.VIEW_STATES,
                "valid live business-view Task status",
                status,
                codec.ReasonCode.INVALID_ENUM,
            )
            row["status"] = status
            if "subtasks" in row and "subtasks" in live_row:
                _merge_subtask_statuses(row["subtasks"], live_row["subtasks"])
    else:
        _fail(codec.ReasonCode.INVALID_REFERENCE, "actual Task triplet path", path)
    return merged


def merge_live_triplet_bytes(path: str, live_before_raw: bytes, frozen_after_payload: Any) -> bytes:
    """Deterministically serialize merged triplet bytes and prove exact projection invariance."""
    merged = merge_live_triplet_payload(path, live_before_raw, frozen_after_payload)
    out_raw = projection.serialized(merged)
    expected_proj = records.task_document_digest(path, projection.serialized(frozen_after_payload))
    actual_proj = records.task_document_digest(path, out_raw)
    _require(
        actual_proj == expected_proj,
        expected_proj,
        actual_proj,
        codec.ReasonCode.DIGEST_MISMATCH,
        resume_ref=path,
    )
    return out_raw


def _preview_digest_of(preview_doc: dict[str, Any]) -> str:
    keys = (
        "schema_version",
        "ok",
        "stable",
        "plan_id",
        "scope_id",
        "audit_ref",
        "authorization",
        "old_done_satisfies_new_obligations",
        "permanent_task_ids_allocated",
        "source_audit",
        "protection",
        "manifest_baseline",
        "requirement_accounting",
        "reuse_inventory",
        "view_deltas",
        "binding_preview",
        "origins_preview",
        "schema_compatibility",
        "diagnostics",
        "observations",
    )
    payload = {key: preview_doc[key] for key in keys}
    return codec.canonical_digest(payload)


def _strip_preview_status(deltas: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    cleaned: dict[str, list[dict[str, Any]]] = {"back": [], "gameplay": []}
    for view in ("back", "gameplay"):
        for row in deltas.get(view, []):
            item = deepcopy(row)
            item.pop("status", None)
            if isinstance(item.get("lineage"), dict):
                item["lineage"].pop("source_status", None)
                item["lineage"].pop("source_statuses", None)
            cleaned[view].append(item)
    return cleaned


def _verify_preview_equivalence(supplied: dict[str, Any], live: dict[str, Any], *, preview_path: str) -> None:
    _require(
        live.get("ok") is True and live.get("stable") is True,
        "live ok/stable 3.1 preview revalidation",
        live.get("diagnostics"),
        codec.ReasonCode.INPUT_STALE,
        resume_ref=preview_path,
    )
    if live.get("preview_digest") == supplied.get("preview_digest"):
        return
    # Allow ONLY lawful Task status advancement when every non-triplet observation
    # and the status-free preview semantics/bindings/origins remain identical.
    triplet_set = {p.casefold() for p in TRIPLET.values()}
    supplied_obs = {
        row["path"]: row for row in supplied.get("observations", [])
        if row["path"].casefold() not in triplet_set
    }
    live_obs = {
        row["path"]: row for row in live.get("observations", [])
        if row["path"].casefold() not in triplet_set
    }
    _require(
        supplied_obs == live_obs,
        "unchanged non-triplet observations since 3.1 preview",
        preview_path,
        codec.ReasonCode.INPUT_STALE,
        resume_ref=preview_path,
    )
    for key in (
        "plan_id",
        "scope_id",
        "audit_ref",
        "source_audit",
        "protection",
        "manifest_baseline",
        "requirement_accounting",
        "binding_preview",
        "origins_preview",
        "schema_compatibility",
    ):
        _require(
            codec.canonical_digest(supplied.get(key)) == codec.canonical_digest(live.get(key)),
            f"unchanged 3.1 preview {key}",
            key,
            codec.ReasonCode.INPUT_STALE,
            resume_ref=preview_path,
        )
    _require(
        codec.canonical_digest(_strip_preview_status(supplied["view_deltas"]))
        == codec.canonical_digest(_strip_preview_status(live["view_deltas"])),
        "unchanged status-free 3.1 view_deltas",
        preview_path,
        codec.ReasonCode.INPUT_STALE,
        resume_ref=preview_path,
    )


def _check_chapter3_task_scope(
    root: Path,
    *,
    view_deltas: dict[str, list[dict[str, Any]]],
    allocations: dict[str, Any],
    snapshot: CompilationSnapshot | None = None,
) -> None:
    cfg_rel = str(chapter3_task_scope.CONFIG).replace("\\", "/")
    if snapshot is not None:
        snapshot.read(cfg_rel, optional=True)
    try:
        scope = chapter3_task_scope.load_scope(root)
    except (ValueError, KeyError, TypeError) as error:
        _fail(
            codec.ReasonCode.CONFLICT,
            "valid legacy A chapter3-task-scope.json",
            str(error),
            resume_ref=cfg_rel,
        )
    if scope is None:
        return
    try:
        allowed = chapter3_task_scope.validate_master(root, scope)
    except (ValueError, KeyError, TypeError) as error:
        _fail(
            codec.ReasonCode.CONFLICT,
            "master task IDs matching frozen chapter3-task-scope.json",
            str(error),
            resume_ref=cfg_rel,
        )
    ops_check: list[dict[str, Any]] = []
    for view in ("back", "gameplay"):
        for delta in view_deltas.get(view, []):
            action = delta["action"]
            if delta.get("task_id") is None:
                ckey = delta["candidate_key"]
                alloc = allocations["task_ids"][ckey]
                ops_check.append({
                    "id": alloc["business_id"],
                    "action": "create",
                    "taskmaster_id": alloc["taskmaster_id"],
                })
            else:
                ops_check.append({
                    "id": delta.get("business_id"),
                    "action": action,
                    "taskmaster_id": delta["task_id"],
                })
    try:
        chapter3_task_scope.validate_candidate_operations(ops_check, allowed)
    except (ValueError, KeyError, TypeError) as error:
        _fail(
            codec.ReasonCode.CONFLICT,
            "operations compliant with frozen legacy A chapter3-task-scope.json",
            str(error),
            resume_ref=cfg_rel,
        )


def _load_triplet(snapshot: CompilationSnapshot) -> dict[str, Any]:
    raws = {key: snapshot.read(path) for key, path in TRIPLET.items()}
    docs = {key: codec.strict_json_loads(raw) for key, raw in raws.items()}
    join = records.TaskJoinContext(**docs)
    master_by_id, views = join.indexes()
    # Verify every master task has valid status/subtask shape and at least one view.
    mapped = set(views["back"].values()) | set(views["gameplay"].values())
    unmapped = sorted(set(master_by_id) - mapped)
    _require(
        not unmapped,
        "every master Task mapped by at least one business view",
        unmapped,
        codec.ReasonCode.MAPPING_MISMATCH,
        resume_ref=TRIPLET["master"],
    )
    for task in master_by_id.values():
        protection._task_state(task, master=True)
    for view_name in ("back", "gameplay"):
        for row in docs[view_name]:
            protection._task_state(row, master=False)
    return {
        "raws": raws,
        "docs": docs,
        "join": join,
        "master": master_by_id,
        "views": views,
        "back_by_tid": {row["taskmaster_id"]: row for row in docs["back"]},
        "gameplay_by_tid": {row["taskmaster_id"]: row for row in docs["gameplay"]},
    }


def _allocate_permanent_ids(
    *,
    triplet: dict[str, Any],
    view_deltas: dict[str, list[dict[str, Any]]],
    inventory_ops: list[dict[str, Any]],
    operation_id: str,
    existing_allocations: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], int]:
    """Allocate permanent taskmaster_id (max+1) and NG/GM business IDs only in prepare."""
    used_tids: set[int] = set()
    for tag_obj in triplet["docs"]["master"].values():
        if isinstance(tag_obj, dict) and isinstance(tag_obj.get("tasks"), list):
            for task in tag_obj["tasks"]:
                if isinstance(task, dict) and type(task.get("id")) is int:
                    used_tids.add(task["id"])
    used_bids: set[str] = set()
    max_ng = 0
    max_gm = 0
    for view_name in ("back", "gameplay"):
        for row in triplet["docs"][view_name]:
            bid = row["id"]
            used_bids.add(bid)
            used_tids.add(row["taskmaster_id"])
            m_ng = _NG_RE.match(bid)
            if m_ng:
                max_ng = max(max_ng, int(m_ng.group(1)))
            m_gm = _GM_RE.match(bid)
            if m_gm:
                max_gm = max(max_gm, int(m_gm.group(1)))

    # Reserve IDs claimed by any OTHER task_compilation operations in inventory.
    for op in inventory_ops:
        if op["operation_id"] == operation_id:
            continue
        if op["schema_version"] != OPERATION_SCHEMA:
            continue
        for claim in op["frozen"]["allocations"].get("task_ids", {}).values():
            used_tids.add(claim["taskmaster_id"])
            bid = claim["business_id"]
            used_bids.add(bid)
            m_ng = _NG_RE.match(bid)
            if m_ng:
                max_ng = max(max_ng, int(m_ng.group(1)))
            m_gm = _GM_RE.match(bid)
            if m_gm:
                max_gm = max(max_gm, int(m_gm.group(1)))

    next_tid_base = (max(used_tids) if used_tids else 0) + 1
    next_tid = next_tid_base
    next_ng = max_ng + 1
    next_gm = max_gm + 1

    # Collect unique candidate_keys deterministically.
    candidates: dict[str, dict[str, Any]] = {}
    for view_name in ("back", "gameplay"):
        for delta in view_deltas.get(view_name, []):
            if delta["action"] == "retire" or delta.get("task_id") is not None:
                continue
            ckey = delta["candidate_key"]
            _require(
                type(ckey) is str and bool(ckey),
                "nonempty candidate_key for unallocated delta",
                ckey,
                codec.ReasonCode.INVALID_TYPE,
            )
            if ckey in candidates:
                _require(
                    candidates[ckey]["view"] == view_name,
                    "one view per candidate_key",
                    ckey,
                )
            else:
                candidates[ckey] = {
                    "view": view_name,
                    "proposed_business_id": delta.get("proposed_business_id") or "",
                }

    allocated: dict[str, dict[str, Any]] = {}
    for ckey in sorted(candidates):
        info = candidates[ckey]
        view_name = info["view"]
        proposed_bid = info["proposed_business_id"]
        if existing_allocations is not None:
            _require(
                ckey in existing_allocations.get("task_ids", {}),
                "exact frozen allocation for candidate_key",
                ckey,
                codec.ReasonCode.INPUT_STALE,
            )
            frozen_item = deepcopy(existing_allocations["task_ids"][ckey])
            _require(
                frozen_item["view"] == view_name
                and frozen_item["taskmaster_id"] not in used_tids
                and frozen_item["business_id"] not in used_bids,
                "collision-free frozen Task ID allocation",
                frozen_item,
                codec.ReasonCode.CONFLICT,
            )
            used_tids.add(frozen_item["taskmaster_id"])
            used_bids.add(frozen_item["business_id"])
            allocated[ckey] = frozen_item
            continue

        while next_tid in used_tids:
            next_tid += 1
        tid = next_tid
        used_tids.add(tid)
        next_tid += 1

        is_placeholder = proposed_bid.startswith(("NG-CAND-", "GM-CAND-")) or not proposed_bid
        if not is_placeholder:
            pattern = _GM_RE if view_name == "gameplay" else _NG_RE
            _require(
                pattern.match(proposed_bid) is not None,
                f"permanent {'GM' if view_name == 'gameplay' else 'NG'} business ID",
                proposed_bid,
                codec.ReasonCode.CONFLICT,
            )
            _require(
                proposed_bid not in used_bids,
                "unique permanent business ID (no collision)",
                proposed_bid,
                codec.ReasonCode.CONFLICT,
            )
            bid = proposed_bid
            used_bids.add(bid)
        else:
            if view_name == "gameplay":
                while f"GM-{next_gm:04d}" in used_bids:
                    next_gm += 1
                bid = f"GM-{next_gm:04d}"
                next_gm += 1
            else:
                while f"NG-{next_ng:04d}" in used_bids:
                    next_ng += 1
                bid = f"NG-{next_ng:04d}"
                next_ng += 1
            used_bids.add(bid)

        allocated[ckey] = {
            "taskmaster_id": tid,
            "business_id": bid,
            "view": view_name,
            "proposed_business_id": proposed_bid,
        }

    return allocated, (existing_allocations["next_taskmaster_id_base"] if existing_allocations is not None else next_tid_base)


def _compile_views_and_master(
    *,
    triplet: dict[str, Any],
    view_deltas: dict[str, list[dict[str, Any]]],
    allocated: dict[str, dict[str, Any]],
    plan_id: str,
    plan_ref: dict[str, Any],
    binding_path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compile back/gameplay views via compile_task_triplet and master via build_taskmaster_tasks."""
    updated_views: dict[str, list[dict[str, Any]]] = {}
    touched_tids: set[int] = set()

    for view_name in ("back", "gameplay"):
        existing_rows = deepcopy(triplet["docs"][view_name])
        existing_by_tid = {row["taskmaster_id"]: row for row in existing_rows}
        candidates: list[dict[str, Any]] = []
        created_meta: dict[str, int] = {}

        protected_proposed_fields = frozenset({
            "id",
            "taskmaster_id",
            "status",
            "subtasks",
            "evidence_refs",
            "history",
            "source_refs",
            "requirement_ids",
            "semantic_refs",
            "semantic_review_tier",
            "taskmaster_exported",
        })

        def _validate_acceptance_entries(entries: Any) -> list[str]:
            _require(
                isinstance(entries, list) and bool(entries),
                "nonempty acceptance list with Refs:",
                entries,
                codec.ReasonCode.SEMANTIC_ERROR,
            )
            for item in entries:
                _require(
                    type(item) is str and "Refs:" in item,
                    "acceptance string entry containing 'Refs:'",
                    item,
                    codec.ReasonCode.SEMANTIC_ERROR,
                )
            return list(dict.fromkeys(entries))

        for delta in view_deltas.get(view_name, []):
            action = delta["action"]
            if action == "reuse":
                tid = delta["task_id"]
                touched_tids.add(tid)
                current = existing_by_tid[tid]
                merged_reqs = sorted(set(current.get("requirement_ids", [])) | set(delta.get("requirement_ids", [])))
                merged_sem = sorted(set(current.get("semantic_refs", [])) | set(merged_reqs))
                merged_src = list(dict.fromkeys([
                    *current.get("source_refs", []),
                    *delta.get("source_refs", []),
                    plan_ref["path"],
                ]))
                merged_labels = sorted(set(current.get("labels", [])) | {"b-route", "3c-compiled"})
                merged_ev = list(dict.fromkeys([*current.get("evidence_refs", []), binding_path]))
                patch: dict[str, Any] = {
                    "requirement_ids": merged_reqs,
                    "semantic_refs": merged_sem,
                    "source_refs": merged_src,
                    "labels": merged_labels,
                    "evidence_refs": merged_ev,
                    "semantic_review_tier": current.get("semantic_review_tier") or "targeted",
                }
                current_acc = list(current.get("acceptance", []))
                if not any(isinstance(acc, str) and "Refs:" in acc for acc in current_acc):
                    patch["acceptance"] = [
                        *current_acc,
                        f"Preserve {current['id']} under plan {plan_id}. Refs: {plan_ref['path']}",
                    ]
                candidates.append({
                    "id": current["id"],
                    "change_action": "update",
                    "field_updates": patch,
                })
                continue
            if action == "retire":
                # Preserve mature task row, ID, status, and history in Taskmaster views;
                # retirement removes this plan's binding/origin ownership only.
                candidates.append({
                    "id": delta["business_id"],
                    "change_action": "reuse",
                })
                continue
            if delta.get("task_id") is None:
                alloc = allocated[delta["candidate_key"]]
                bid = alloc["business_id"]
                tid = alloc["taskmaster_id"]
                created_meta[bid] = tid
                touched_tids.add(tid)
                labels = [
                    "3c-compiled" if lbl == "3c-preview" else lbl
                    for lbl in delta.get("labels", [])
                ]
                if "3c-compiled" not in labels:
                    labels.append("3c-compiled")
                source_refs = list(dict.fromkeys([
                    *delta.get("source_refs", []),
                    plan_ref["path"],
                ]))
                acceptance = list(delta.get("acceptance", []))
                if not acceptance:
                    acceptance = [f"Deliver {bid} under plan {plan_id}. Refs: {plan_ref['path']}"]
                cand_row: dict[str, Any] = {
                    "id": bid,
                    "change_action": "create",
                    "story_id": f"B-ROUTE-{plan_id}",
                    "title": delta["title"],
                    "description": delta.get("description") or delta["title"],
                    "status": "pending",
                    "priority": delta.get("priority") or "P2",
                    "layer": delta.get("layer") or ("core" if view_name == "gameplay" else "adapter"),
                    "owner": delta.get("owner") or ("gameplay" if view_name == "gameplay" else "architecture"),
                    "labels": sorted(set(labels)),
                    "source_refs": source_refs,
                    "requirement_ids": sorted(set(delta.get("requirement_ids", []))),
                    "semantic_refs": sorted(set(delta.get("semantic_refs", delta.get("requirement_ids", [])))),
                    "acceptance": acceptance,
                    "test_strategy": list(delta.get("test_strategy", [])),
                    "evidence_refs": [binding_path],
                }
                proposed_fields = delta.get("proposed_fields")
                if isinstance(proposed_fields, dict):
                    for key, val in proposed_fields.items():
                        _require(
                            key not in protected_proposed_fields,
                            "proposed_fields must not overwrite protected Task identity/status/history/refs",
                            key,
                            codec.ReasonCode.CONFLICT,
                        )
                        if key == "acceptance":
                            _require(
                                isinstance(val, list),
                                "acceptance list in proposed_fields",
                                val,
                                codec.ReasonCode.SEMANTIC_ERROR,
                            )
                            cand_row["acceptance"] = list(dict.fromkeys([*cand_row["acceptance"], *val]))
                        else:
                            cand_row[key] = deepcopy(val)
                cand_row["acceptance"] = _validate_acceptance_entries(cand_row["acceptance"])
                candidates.append(cand_row)
            else:
                tid = delta["task_id"]
                touched_tids.add(tid)
                current = existing_by_tid[tid]
                merged_reqs = sorted(set(current.get("requirement_ids", [])) | set(delta.get("requirement_ids", [])))
                merged_sem = sorted(set(current.get("semantic_refs", [])) | set(merged_reqs))
                merged_src = list(dict.fromkeys([
                    *current.get("source_refs", []),
                    *delta.get("source_refs", []),
                    plan_ref["path"],
                ]))
                merged_labels = sorted(set(current.get("labels", [])) | {"b-route", "3c-compiled"})
                merged_ev = list(dict.fromkeys([*current.get("evidence_refs", []), binding_path]))
                patch = {
                    "requirement_ids": merged_reqs,
                    "semantic_refs": merged_sem,
                    "source_refs": merged_src,
                    "labels": merged_labels,
                    "evidence_refs": merged_ev,
                    "semantic_review_tier": current.get("semantic_review_tier") or "targeted",
                }
                proposed_fields = delta.get("proposed_fields")
                if isinstance(proposed_fields, dict):
                    for key, val in proposed_fields.items():
                        _require(
                            key not in protected_proposed_fields,
                            "proposed_fields must not overwrite protected Task identity/status/history/refs",
                            key,
                            codec.ReasonCode.CONFLICT,
                        )
                        if key == "acceptance":
                            validated_val = _validate_acceptance_entries(val)
                            patch["acceptance"] = list(dict.fromkeys([*current.get("acceptance", []), *validated_val]))
                        else:
                            patch[key] = deepcopy(val)
                if "acceptance" in patch:
                    patch["acceptance"] = _validate_acceptance_entries(patch["acceptance"])
                candidates.append({
                    "id": current["id"],
                    "change_action": "update",
                    "field_updates": patch,
                })

        updated_rows, _ops, conflicts = compile_task_triplet.build_change_plan(
            existing_rows, candidates, view_name
        )
        _require(
            not conflicts,
            "conflict-free compile_task_triplet change plan",
            conflicts,
            codec.ReasonCode.CONFLICT,
        )
        for row in updated_rows:
            bid = row["id"]
            if bid in created_meta:
                row["taskmaster_id"] = created_meta[bid]
                row["taskmaster_exported"] = True
                row["semantic_review_tier"] = row.get("semantic_review_tier") or "targeted"
        updated_views[view_name] = updated_rows

    # Build updated master tasks.json reusing build_taskmaster_tasks helpers.
    master_doc = deepcopy(triplet["docs"]["master"])
    tag_tasks = master_doc["master"]["tasks"]
    existing_master_idx = {row["id"]: idx for idx, row in enumerate(tag_tasks)}

    rows_by_numeric: dict[int, list[dict[str, Any]]] = {}
    id_map: dict[str, int] = {}
    for view_name in ("back", "gameplay"):
        for row in updated_views[view_name]:
            tid = row["taskmaster_id"]
            id_map[row["id"]] = tid
            rows_by_numeric.setdefault(tid, []).append(row)

    for tid in sorted(touched_tids):
        src = build_taskmaster_tasks.merge_numeric_view_group(rows_by_numeric[tid], tid)
        title = src.get("title") or str(tid)
        description = src.get("description") or ""
        details_parts: list[str] = []
        if src.get("story_id"):
            details_parts.append(f"Story: {src['story_id']}")
        for key, label in (
            ("adr_refs", "ADR Refs"),
            ("chapter_refs", "Chapters"),
            ("overlay_refs", "Overlays"),
            ("test_refs", "Test Refs"),
            ("acceptance", "Acceptance"),
            ("test_strategy", "Test Strategy"),
            ("labels", "Labels"),
            ("owner", "Owner"),
            ("layer", "Layer"),
        ):
            val = src.get(key)
            if not val:
                continue
            text = "; ".join(str(v) for v in val) if isinstance(val, list) else str(val)
            details_parts.append(f"{label}: {text}")
        details = "\n".join(details_parts) if details_parts else ""
        ts = src.get("test_strategy")
        if isinstance(ts, list):
            test_strategy_str = "\n".join(str(x) for x in ts)
        elif isinstance(ts, str):
            test_strategy_str = ts
        else:
            test_strategy_str = ""
        dep_ids: list[int] = []
        for dep in build_taskmaster_tasks.get_dependencies(src):
            if type(dep) is int:
                _require(
                    dep in rows_by_numeric,
                    "existing dependency taskmaster_id",
                    dep,
                    codec.ReasonCode.CONFLICT,
                )
                num_dep = dep
            elif type(dep) is str and dep in id_map:
                num_dep = id_map[dep]
            elif type(dep) is str and dep in allocated:
                num_dep = allocated[dep]["taskmaster_id"]
            elif type(dep) is str and dep.isascii() and dep.isdecimal() and int(dep) in rows_by_numeric:
                num_dep = int(dep)
            else:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    "resolvable dependency taskmaster_id, business_id, or candidate_key",
                    dep,
                )
            if num_dep != tid and num_dep not in dep_ids:
                dep_ids.append(num_dep)
        generated_fields: dict[str, Any] = {
            "id": tid,
            "title": title,
            "description": description,
            "status": build_taskmaster_tasks.map_status(src.get("status")),
            "priority": build_taskmaster_tasks.map_priority(src.get("priority")),
            "dependencies": dep_ids,
        }
        if details:
            generated_fields["details"] = details
        if test_strategy_str:
            generated_fields["testStrategy"] = test_strategy_str

        if tid in existing_master_idx:
            idx = existing_master_idx[tid]
            tag_tasks[idx] = build_taskmaster_tasks.merge_master_fields(tag_tasks[idx], generated_fields)
        else:
            existing_master_idx[tid] = len(tag_tasks)
            tag_tasks.append(generated_fields)

    # Validate strict join on compiled triplet.
    compiled_join = records.TaskJoinContext(
        master=master_doc, back=updated_views["back"], gameplay=updated_views["gameplay"]
    )
    compiled_master, compiled_views = compiled_join.indexes()
    mapped = set(compiled_views["back"].values()) | set(compiled_views["gameplay"].values())
    _require(
        set(compiled_master) == mapped,
        "every compiled master Task mapped by at least one business view",
        sorted(set(compiled_master) - mapped),
        codec.ReasonCode.MAPPING_MISMATCH,
    )
    return master_doc, updated_views["back"], updated_views["gameplay"]


def _compile_binding_and_origins(
    *,
    preview_doc: dict[str, Any],
    allocated: dict[str, dict[str, Any]],
    current_origins: dict[str, Any],
    plan_id: str,
    plan_ref: dict[str, Any],
    binding_revision: int,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Materialize formal newrouge.b-route-binding.v1 and newrouge.b-route-origins.v1."""
    binding = deepcopy(preview_doc["binding_preview"])
    binding["binding_revision"] = binding_revision
    binding["plan_ref"] = deepcopy(plan_ref)
    binding["stage"] = "3C"

    for row in binding["task_mappings"]:
        if row["task_id"] is None:
            ckey = row.pop("candidate_key")
            alloc = allocated[ckey]
            row["task_id"] = alloc["taskmaster_id"]
            row["view_refs"] = [
                {"view": vref["view"], "business_id": alloc["business_id"]}
                for vref in row["view_refs"]
            ]
        else:
            row.pop("candidate_key", None)
    binding["task_mappings"].sort(key=lambda item: item["task_id"])

    for obj in binding["implementation_objects"]:
        ckeys = obj.pop("responsible_candidate_keys", [])
        tids = set(obj.get("responsible_task_ids", []))
        for ckey in ckeys:
            tids.add(allocated[ckey]["taskmaster_id"])
        obj["responsible_task_ids"] = sorted(tids)

    binding_path = f"{records.BASE}bindings/{plan_id}/{binding_revision}.json"
    checked = records.validate_record(binding, path=binding_path)
    if not checked.ok:
        raise codec.CodecError(checked.diagnostic)
    binding_raw = projection.serialized(binding)
    binding_ref = projection.reference(binding_path, binding_raw)

    # Merge origins against live committed origins without losing other plans or frozen_legacy_refs.
    origins_by_tid: dict[int, dict[str, Any]] = {
        row["task_id"]: deepcopy(row) for row in current_origins.get("tasks", [])
    }
    preview_origins_by_tid: dict[int, dict[str, Any]] = {}
    for row in preview_doc["origins_preview"]["tasks"]:
        if row["task_id"] is None:
            ckey = row["candidate_key"]
            tid = allocated[ckey]["taskmaster_id"]
        else:
            tid = row["task_id"]
        preview_origins_by_tid[tid] = deepcopy(row)

    mapped_tids = {row["task_id"] for row in binding["task_mappings"]}
    # Remove this plan from any task previously mapped to this plan that is no longer mapped (retire/split/merge).
    for tid in list(origins_by_tid):
        if tid in mapped_tids:
            continue
        row = origins_by_tid[tid]
        had_this_plan = any(p["entity_id"] == plan_id for p in row["plan_refs"]) or any(
            b["entity_id"] == plan_id for b in row["binding_refs"]
        )
        if not had_this_plan:
            continue
        rem_plans = [p for p in row["plan_refs"] if p["entity_id"] != plan_id]
        rem_bindings = [b for b in row["binding_refs"] if b["entity_id"] != plan_id]
        if not rem_plans:
            del origins_by_tid[tid]
        else:
            row["plan_refs"] = rem_plans
            row["binding_refs"] = rem_bindings

    for tid in sorted(mapped_tids):
        src_row = preview_origins_by_tid.get(tid)
        source_refs = deepcopy(src_row["source_refs"]) if src_row is not None else []
        existing = origins_by_tid.get(tid)
        if existing is None:
            origins_by_tid[tid] = {
                "task_id": tid,
                "source_refs": _dedupe_owned_refs(source_refs),
                "plan_refs": [deepcopy(plan_ref)],
                "binding_refs": [deepcopy(binding_ref)],
            }
        else:
            existing["source_refs"] = _dedupe_owned_refs(existing["source_refs"] + source_refs)
            existing["plan_refs"] = [p for p in existing["plan_refs"] if p["entity_id"] != plan_id] + [
                deepcopy(plan_ref)
            ]
            existing["binding_refs"] = [b for b in existing["binding_refs"] if b["entity_id"] != plan_id] + [
                deepcopy(binding_ref)
            ]

    origins = {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": int(current_origins["revision"]) + 1,
        "tasks": [origins_by_tid[tid] for tid in sorted(origins_by_tid)],
        "frozen_legacy_refs": deepcopy(current_origins.get("frozen_legacy_refs", [])),
    }
    origins_path = records.BASE + "task-origins.v1.json"
    origins_check = records.validate_record(origins, path=origins_path)
    if not origins_check.ok:
        raise codec.CodecError(origins_check.diagnostic)
    return binding, binding_path, binding_ref, origins


def _collect_plan_authority_files(snapshot: CompilationSnapshot, plan: dict[str, Any]) -> None:
    for child in records._walk(plan):
        if set(child) == {"owner", "ref", "files"}:
            for item in child["files"]:
                raw = snapshot.read(item["path"])
                _require(
                    codec.raw_digest(raw) == item["raw_digest"],
                    item["raw_digest"],
                    item["path"],
                    codec.ReasonCode.INPUT_STALE,
                )


def build(
    root: Path,
    request: dict[str, Any],
    *,
    allocations: dict[str, Any] | None = None,
    inventory_ops: list[dict[str, Any]] | None = None,
) -> tuple[CompilationSnapshot, dict[str, Any]]:
    """Revalidate 3A/3B/3.1/protection/manifest and deterministically build the frozen operation."""
    root = Path(root).resolve()
    journal.validate_operation_request(request)
    _require(
        request.get("schema_version") == REQUEST_SCHEMA and request.get("producer") == PRODUCER,
        REQUEST_SCHEMA,
        request.get("schema_version"),
        codec.ReasonCode.SCHEMA_MISMATCH,
    )
    operation_id = _validate_file_id(request["operation_id"], "operation_id")
    plan_id = _validate_file_id(request["plan_id"], "plan_id")
    scope_id = request["scope_id"]
    codec.validate_business_id(scope_id)

    # Check legacy pending markers before doing anything.
    op_scope._legacy_pending(root, None)

    snapshot = CompilationSnapshot(root)

    # 1. Read and validate 3.1 preview report and request references.
    preview_ref = request["preview_ref"]
    _require(
        preview_ref["schema_version"] == task_preview.SCHEMA,
        task_preview.SCHEMA,
        preview_ref["schema_version"],
        codec.ReasonCode.SCHEMA_MISMATCH,
    )
    preview_doc = snapshot.ref(preview_ref)
    _require(
        preview_doc.get("ok") is True and preview_doc.get("stable") is True,
        "ok=True and stable=True 3.1 task-change preview",
        {"ok": preview_doc.get("ok"), "stable": preview_doc.get("stable")},
        codec.ReasonCode.SEMANTIC_ERROR,
        resume_ref=preview_ref["path"],
    )
    _require(
        _preview_digest_of(preview_doc) == preview_doc.get("preview_digest"),
        preview_doc.get("preview_digest"),
        _preview_digest_of(preview_doc),
        codec.ReasonCode.DIGEST_MISMATCH,
        resume_ref=preview_ref["path"],
    )
    _require(
        preview_doc.get("plan_id") == plan_id
        and preview_doc.get("scope_id") == scope_id
        and preview_doc.get("audit_ref") == request["audit_ref"]["path"],
        "request plan_id/scope_id/audit_ref matching 3.1 preview",
        {"plan_id": preview_doc.get("plan_id"), "scope_id": preview_doc.get("scope_id"), "audit_ref": preview_doc.get("audit_ref")},
        codec.ReasonCode.CONFLICT,
        resume_ref=preview_ref["path"],
    )
    snapshot.ref(request["audit_ref"])

    protection_ref = request.get("protection_ref")
    manifest_ref = request.get("manifest_ref")
    change_intents_ref = request.get("change_intents_ref")
    if protection_ref is not None:
        snapshot.ref(protection_ref)
    if manifest_ref is not None:
        snapshot.ref(manifest_ref)
        if preview_doc.get("manifest_baseline") is not None:
            _require(
                preview_doc["manifest_baseline"]["path"] == manifest_ref["path"]
                and preview_doc["manifest_baseline"]["raw_digest"] == manifest_ref["raw_digest"],
                "manifest_ref matching 3.1 preview manifest_baseline",
                manifest_ref["path"],
                codec.ReasonCode.INPUT_STALE,
            )
    if change_intents_ref is not None:
        snapshot.ref(change_intents_ref)

    # 2. Revalidate committed 3B formal adoption via read_committed.
    # When revalidating an already-prepared/reserved operation (allocations is not None),
    # allow that same operation_id in read_committed while still blocking all other pending ops.
    read_op = operation_id if allocations is not None else None
    with commit.read_operation_context(read_op):
        committed = commit.read_committed(root, scope_ids=[scope_id], operation_id=read_op)
    _require(
        committed.get("status") == "committed" and committed.get("formal_adoption") is True,
        "committed 3B formal adoption",
        committed.get("status"),
        codec.ReasonCode.UNPUBLISHED,
        resume_ref=records.CATALOG_PATH,
    )
    catalog_raw = snapshot.read(records.CATALOG_PATH)
    _require(
        codec.raw_digest(catalog_raw) == committed["catalog_raw_digest"],
        committed["catalog_raw_digest"],
        codec.raw_digest(catalog_raw),
        codec.ReasonCode.INPUT_STALE,
        resume_ref=records.CATALOG_PATH,
    )
    catalog = codec.strict_json_loads(catalog_raw)
    policy_raw = snapshot.read(catalog["policy_ref"]["path"])
    _require(policy_raw is not None, "committed policy record", catalog["policy_ref"]["path"])
    origins_raw = _read_bytes(root, catalog["origins_ref"]["path"])
    current_origins = codec.strict_json_loads(origins_raw)

    # Locate exact committed plan_ref and any existing binding for plan_id.
    plan_ref = None
    existing_binding_ref = None
    affected_existing_heads: list[dict[str, Any]] = []
    for head in catalog["scope_heads"]:
        head_has_plan = False
        for ref in head["plan_refs"]:
            if ref["entity_id"] == plan_id:
                plan_ref = deepcopy(ref)
                head_has_plan = True
        for ref in head["binding_refs"]:
            if ref["entity_id"] == plan_id:
                existing_binding_ref = deepcopy(ref)
                head_has_plan = True
        if head_has_plan or head["scope_id"] == scope_id:
            affected_existing_heads.append(head)
    _require(
        plan_ref is not None,
        f"published 3B plan {plan_id} in catalog",
        plan_id,
        codec.ReasonCode.UNPUBLISHED,
        resume_ref=records.CATALOG_PATH,
    )
    plan_raw = snapshot.read(plan_ref["path"])
    plan = codec.strict_json_loads(plan_raw)
    _collect_plan_authority_files(snapshot, plan)

    existing_binding = None
    if existing_binding_ref is not None:
        existing_binding = codec.strict_json_loads(snapshot.read(existing_binding_ref["path"]))

    # Pin prior receipts for affected existing heads so receipt lineage is anchored.
    for head in affected_existing_heads:
        snapshot.read(head["receipt_ref"]["path"])

    # 4. Revalidate live 3.1 preview (including 3A verify_current_proof, 3B alignment, protection, manifest anti-weakening, change-intents).
    with commit.read_operation_context(read_op):
        live_preview = task_preview.preview_task_changes(
            root,
            plan_id=plan_id,
            scope_id=scope_id,
            audit_ref=request["audit_ref"]["path"],
            protection_ref=protection_ref["path"] if protection_ref is not None else None,
            manifest_ref=manifest_ref["path"] if manifest_ref is not None else None,
            change_intents_ref=change_intents_ref["path"] if change_intents_ref is not None else None,
        )
    _require(
        isinstance(live_preview.get("source_audit"), dict)
        and live_preview["source_audit"].get("planning_eligible") is True,
        "planning_eligible=True 3A source audit proof",
        live_preview.get("diagnostics"),
        codec.ReasonCode.UNPUBLISHED,
        resume_ref=request["audit_ref"]["path"],
    )
    _verify_preview_equivalence(preview_doc, live_preview, preview_path=preview_ref["path"])
    triplet_paths_cf = {p.casefold() for p in TRIPLET.values()}
    for obs_row in live_preview.get("observations", []):
        if isinstance(obs_row, dict) and isinstance(obs_row.get("path"), str):
            obs_path = obs_row["path"]
            if obs_path.casefold() not in triplet_paths_cf:
                snapshot.read(obs_path, optional=True)

    # 5. Load live triplet via strict TaskJoinContext.
    triplet = _load_triplet(snapshot)

    # 6. Compute binding revision & permanent Task IDs (reusing frozen allocations when provided).
    inv = inventory_ops if inventory_ops is not None else journal.operation_inventory(root)
    existing_binding_revs = [existing_binding["binding_revision"]] if existing_binding is not None else [0]
    for op in inv:
        if op["operation_id"] == operation_id:
            continue
        claim = op["frozen"]["allocations"]
        if claim.get("plan_id") == plan_id and claim.get("binding_revision") is not None:
            existing_binding_revs.append(claim["binding_revision"])
    binding_revision = (
        allocations["binding_revision"]
        if allocations is not None
        else max(existing_binding_revs) + 1
    )
    _require(
        binding_revision > (existing_binding["binding_revision"] if existing_binding is not None else 0),
        "strictly monotonic binding revision",
        binding_revision,
        codec.ReasonCode.REVISION_MISMATCH,
    )

    allocated_tasks, next_tid_base = _allocate_permanent_ids(
        triplet=triplet,
        view_deltas=preview_doc["view_deltas"],
        inventory_ops=inv,
        operation_id=operation_id,
        existing_allocations=allocations,
    )

    # 7. Compile formal binding, origins, and Taskmaster triplet.
    compiled_binding, binding_path, _binding_ref, compiled_origins = _compile_binding_and_origins(
        preview_doc=preview_doc,
        allocated=allocated_tasks,
        current_origins=current_origins,
        plan_id=plan_id,
        plan_ref=plan_ref,
        binding_revision=binding_revision,
    )
    _collect_plan_authority_files(snapshot, compiled_binding)
    _collect_plan_authority_files(snapshot, compiled_origins)

    compiled_master, compiled_back, compiled_gameplay = _compile_views_and_master(
        triplet=triplet,
        view_deltas=preview_doc["view_deltas"],
        allocated=allocated_tasks,
        plan_id=plan_id,
        plan_ref=plan_ref,
        binding_path=binding_path,
    )

    # 8. Build allocations claim (including task_definitions for all old + new affected tasks).
    affected_tids: set[int] = {row["task_id"] for row in compiled_binding["task_mappings"]}
    if existing_binding is not None:
        affected_tids.update(row["task_id"] for row in existing_binding["task_mappings"])
    for view_name in ("back", "gameplay"):
        for delta in preview_doc["view_deltas"].get(view_name, []):
            if delta.get("task_id") is not None:
                affected_tids.add(delta["task_id"])
            lineage = delta.get("lineage")
            if isinstance(lineage, dict):
                src_tid = lineage.get("source_task_id")
                if type(src_tid) is int:
                    affected_tids.add(src_tid)
                for src_item in lineage.get("source_task_ids", []) or []:
                    if type(src_item) is int:
                        affected_tids.add(src_item)

    compiled_master_by_id = {row["id"]: row for row in compiled_master["master"]["tasks"]}
    task_definitions: dict[str, str] = {}
    for tid in sorted(affected_tids):
        if tid in triplet["master"]:
            defn = {
                "master": protection.task_definition_projection(triplet["master"][tid]),
                "back": [
                    protection.task_definition_projection(row)
                    for row in triplet["docs"]["back"]
                    if row["taskmaster_id"] == tid
                ],
                "gameplay": [
                    protection.task_definition_projection(row)
                    for row in triplet["docs"]["gameplay"]
                    if row["taskmaster_id"] == tid
                ],
            }
        else:
            defn = {
                "master": protection.task_definition_projection(compiled_master_by_id[tid]),
                "back": [
                    protection.task_definition_projection(row)
                    for row in compiled_back
                    if row["taskmaster_id"] == tid
                ],
                "gameplay": [
                    protection.task_definition_projection(row)
                    for row in compiled_gameplay
                    if row["taskmaster_id"] == tid
                ],
            }
        task_definitions[str(tid)] = codec.canonical_digest(defn)

    proposed_allocations = {
        "plan_id": plan_id,
        "plan_revision": plan["revision"],
        "binding_revision": binding_revision,
        "origins_revision": compiled_origins["revision"],
        "next_taskmaster_id_base": next_tid_base,
        "task_ids": allocated_tasks,
        "task_definitions": task_definitions,
    }
    _require(
        allocations is None or allocations == proposed_allocations,
        "unchanged frozen task_compilation allocations",
        proposed_allocations,
        codec.ReasonCode.INPUT_STALE,
    )

    # 9. Enforce legacy A chapter3-task-scope.json (if present) before finalizing targets.
    _check_chapter3_task_scope(
        root, view_deltas=preview_doc["view_deltas"], allocations=proposed_allocations, snapshot=snapshot
    )

    # 10. Assemble immutable_bytes targets (binding, origins) and task_definition_projection targets (triplet).
    binding_raw = projection.serialized(compiled_binding)
    origins_after_raw = projection.serialized(compiled_origins)
    origins_path = records.BASE + "task-origins.v1.json"
    if allocations is None:
        _require(
            _read_bytes(root, binding_path, optional=True) is None,
            "fresh immutable binding revision path",
            binding_path,
            codec.ReasonCode.CONFLICT,
        )

    targets: list[dict[str, Any]] = [
        {
            "path": binding_path,
            "schema_version": "newrouge.b-route-binding.v1",
            "before_raw_digest": None,
            "after_payload": compiled_binding,
            "after_raw_digest": codec.raw_digest(binding_raw),
            "verification_mode": "immutable_bytes",
        },
        {
            "path": origins_path,
            "schema_version": "newrouge.b-route-origins.v1",
            "before_raw_digest": codec.raw_digest(origins_raw),
            "after_payload": compiled_origins,
            "after_raw_digest": codec.raw_digest(origins_after_raw),
            "verification_mode": "immutable_bytes",
        },
    ]

    triplet_before_proj: dict[str, str] = {}
    triplet_after_proj: dict[str, str] = {}
    for key, payload in (("master", compiled_master), ("back", compiled_back), ("gameplay", compiled_gameplay)):
        tpath = TRIPLET[key]
        before_raw = triplet["raws"][key]
        after_raw = projection.serialized(payload)
        b_proj = records.task_document_digest(tpath, before_raw)
        a_proj = records.task_document_digest(tpath, after_raw)
        triplet_before_proj[tpath] = b_proj
        triplet_after_proj[tpath] = a_proj
        targets.append({
            "path": tpath,
            "schema_version": TRIPLET_SCHEMAS[tpath],
            "before_raw_digest": codec.raw_digest(before_raw),
            "after_payload": payload,
            "after_raw_digest": codec.raw_digest(after_raw),
            "verification_mode": "task_definition_projection",
            "codec_version": records.PROJECTION_CODEC,
            "before_projection_digest": b_proj,
            "after_projection_digest": a_proj,
        })

    # 11. Compute old + new resource_scopes union.
    old_scope_ids = sorted({scope_id} | {head["scope_id"] for head in affected_existing_heads})
    new_scope_ids = list(
        op_scope.resource_scopes(
            target_paths=[row["path"] for row in targets],
            plan_ids=[plan_id],
            requirement_ids=[row["requirement_id"] for row in plan["requirements"]],
            flow_ids=[row["id"] for row in plan["definitions"]["flows"]],
            command_ids=[row["id"] for row in plan["definitions"]["commands"]],
            state_ids=[row["id"] for row in plan["definitions"]["states"]],
            task_ids=sorted(affected_tids),
        )
    )
    scope_ids = sorted(set(old_scope_ids) | set(new_scope_ids))

    # 12. Build authority_refs (strictly excluding all target paths).
    target_set = {row["path"] for row in targets}
    authority_refs = [
        {"path": name, "schema_version": "raw.bytes.v1", "raw_digest": digest}
        for name, digest in sorted(snapshot.files.items())
        if digest is not None and name not in target_set
    ]

    # Compute current affected semantic frame digest using _PublishedBundle.
    bundle = records._PublishedBundle(
        {records.CATALOG_PATH: catalog_raw}, root, records.CATALOG_PATH, None, triplet["join"]
    )
    loaded_cat = bundle.load(records.CATALOG_PATH)
    bundle.select(loaded_cat, [scope_id])
    bundle.expand()
    bundle.relationships(loaded_cat)
    bundle.bytes.stable()

    frozen = {
        "producer": PRODUCER,
        "request": deepcopy(request),
        "allocations": proposed_allocations,
        "scope_ids": scope_ids,
        "authority_refs": authority_refs,
        "targets": targets,
        "compilation": {
            "plan_id": plan_id,
            "scope_id": scope_id,
            "preview_digest": preview_doc["preview_digest"],
            "current_catalog_digest": codec.raw_digest(catalog_raw),
            "current_frame_digest": codec.canonical_digest(bundle.semantic_frame),
            "plan_ref": deepcopy(plan_ref),
            "old_scope_ids": old_scope_ids,
            "new_scope_ids": new_scope_ids,
            "triplet_before_projections": triplet_before_proj,
            "triplet_after_projections": triplet_after_proj,
        },
    }
    journal._operation_schema(frozen, "Frozen")

    # 13. Dry-run validate future receipt + catalog bundle before any persistence.
    candidates = {row["path"]: projection.serialized(row["after_payload"]) for row in targets}
    candidates[records.CATALOG_PATH] = catalog_raw
    compiled_join = records.TaskJoinContext(
        master=compiled_master, back=compiled_back, gameplay=compiled_gameplay
    )
    draft_bundle = records._Bundle(candidates, root, records.CATALOG_PATH, None, compiled_join)
    owners = {(row["kind"], row["definition_id"]): row for row in catalog["definition_owners"]}
    pre_receipt = projection.receipt_for_frozen(
        operation_id=operation_id, frozen=frozen, resolved_definitions=[], catalog_before=catalog_raw
    )
    resolved = draft_bundle.closure(
        pre_receipt["plan_refs"], pre_receipt["binding_refs"], owners, records.BASE + f"commits/{operation_id}.json"
    )
    full_receipt = projection.receipt_for_frozen(
        operation_id=operation_id,
        frozen=frozen,
        resolved_definitions=[resolved[k] for k in sorted(resolved)],
        catalog_before=catalog_raw,
    )
    projection.catalog_for_receipt(
        current_catalog=catalog_raw,
        receipt=full_receipt,
        candidates=candidates,
        task_join=compiled_join,
        root=root,
        frozen=frozen,
    )

    snapshot.verify()
    return snapshot, frozen


def _result(envelope: dict[str, Any], *, event_log: str | None = None) -> dict[str, Any]:
    res = {
        "producer": PRODUCER,
        "operation_id": envelope["operation_id"],
        "state": envelope["state"],
        "scope_ids": envelope["frozen"]["scope_ids"],
        "request_digest": envelope["request_digest"],
        "frozen_digest": envelope["frozen_digest"],
        "allocations": envelope["frozen"]["allocations"],
        "resume_ref": journal._operation_ref(envelope["operation_id"]),
        "chapter4_5_required": True,
        "chapter6_authorized": False,
        "formal_adoption": False,
        "diagnostics": [],
        **FLAGS,
    }
    if event_log is not None:
        res["event_log"] = event_log
    return res


def public(function):
    @wraps(function)
    def checked(root, *, operation_id, **kwargs):
        try:
            return function(root, operation_id=operation_id, **kwargs)
        except codec.CodecError as error:
            diagnostic = error.diagnostic
            if diagnostic.entity_id is None and type(operation_id) is str:
                diagnostic = replace(diagnostic, entity_id=operation_id)
            raise codec.CodecError(diagnostic) from error
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                "complete governed task compilation evidence",
                f"{type(error).__name__}: {error}",
                operation_id=operation_id if type(operation_id) is str else None,
            )

    return checked


def _run(root: Path, operation_id: str, request_raw: bytes, *, reserve_only: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    _validate_file_id(operation_id, "operation_id")
    request = journal.validate_operation_request(request_raw)
    _require(
        request.get("schema_version") == REQUEST_SCHEMA and request.get("producer") == PRODUCER,
        REQUEST_SCHEMA,
        request.get("schema_version"),
        codec.ReasonCode.SCHEMA_MISMATCH,
        operation_id=operation_id,
    )
    _require(
        request["operation_id"] == operation_id,
        operation_id,
        request["operation_id"],
        codec.ReasonCode.CONFLICT,
        operation_id=operation_id,
    )
    inv = journal.operation_inventory(root)
    existing = next((row for row in inv if row["operation_id"] == operation_id), None)
    _require(
        not reserve_only or existing is not None,
        "existing prepared task compilation operation",
        operation_id,
        codec.ReasonCode.FILE_NOT_FOUND,
        operation_id=operation_id,
    )
    if existing is not None:
        _require(
            existing["schema_version"] == OPERATION_SCHEMA,
            OPERATION_SCHEMA,
            existing["schema_version"],
            codec.ReasonCode.CONFLICT,
            operation_id=operation_id,
        )
        _require(
            existing["request_digest"] == codec.canonical_digest(request),
            "same ID and complete request for task_compilation",
            operation_id,
            codec.ReasonCode.CONFLICT,
            operation_id=operation_id,
        )
        if commit.validate_local(root, existing) is not None:
            return _result(existing)
        request = existing["frozen"]["request"]
        request_raw = base64.b64decode(existing["request_raw_base64"], validate=True)

    op_scope.initialize_lock_namespace(root)
    snapshot, frozen = build(
        root,
        request,
        allocations=existing["frozen"]["allocations"] if existing is not None else None,
        inventory_ops=inv,
    )
    if existing is not None:
        existing_targets = existing["frozen"]["targets"]
        _require(
            len(frozen["targets"]) == len(existing_targets)
            and frozen["allocations"] == existing["frozen"]["allocations"]
            and frozen["scope_ids"] == existing["frozen"]["scope_ids"],
            "unchanged frozen task compilation operation",
            operation_id,
            codec.ReasonCode.INPUT_STALE,
            operation_id=operation_id,
        )
        for cur_t, old_t in zip(frozen["targets"], existing_targets):
            _require(
                cur_t["path"] == old_t["path"]
                and cur_t["verification_mode"] == old_t["verification_mode"],
                "same target sequence between prepare and reserve",
                cur_t["path"],
                codec.ReasonCode.INPUT_STALE,
                operation_id=operation_id,
            )
            if cur_t["verification_mode"] == "immutable_bytes":
                _require(
                    cur_t["before_raw_digest"] == old_t["before_raw_digest"]
                    and cur_t["after_raw_digest"] == old_t["after_raw_digest"],
                    "unchanged immutable formal targets between prepare and reserve",
                    cur_t["path"],
                    codec.ReasonCode.INPUT_STALE,
                    operation_id=operation_id,
                )
            else:
                _require(
                    cur_t["before_projection_digest"] == old_t["before_projection_digest"]
                    and cur_t["after_projection_digest"] == old_t["after_projection_digest"],
                    "unchanged triplet definition projection between prepare and reserve",
                    cur_t["path"],
                    codec.ReasonCode.INPUT_STALE,
                    operation_id=operation_id,
                )
        frozen = existing["frozen"]

    with op_scope.business_guard(root, frozen["scope_ids"], operation_id=operation_id):
        snapshot.verify()
        current = journal.operation_inventory(root)
        live_existing = next((row for row in current if row["operation_id"] == operation_id), None)
        _require(
            not reserve_only or live_existing is not None,
            "existing prepared task compilation operation under lease",
            operation_id,
            codec.ReasonCode.FILE_NOT_FOUND,
            operation_id=operation_id,
        )
        if live_existing is not None:
            _require(
                live_existing["request_digest"] == codec.canonical_digest(request)
                and live_existing["frozen"] == frozen,
                "unchanged persisted task compilation operation under lease",
                operation_id,
                codec.ReasonCode.CONFLICT,
                operation_id=operation_id,
            )
            new_state = "reserved" if (reserve_only or live_existing["state"] == "reserved") else live_existing["state"]
            value = {**live_existing, "state": new_state}
        else:
            # Recheck ID and binding_revision allocations under lock against live inventory
            # without re-entering business_guard (snapshot.verify() already pins all files/projections).
            locked_triplet = _load_triplet(snapshot)
            locked_preview = snapshot.ref(request["preview_ref"])
            locked_plan_id = frozen["allocations"]["plan_id"]
            locked_binding_rev = frozen["allocations"]["binding_revision"]
            for other in current:
                if other["operation_id"] == operation_id:
                    continue
                other_claim = other["frozen"]["allocations"]
                if (
                    other_claim.get("plan_id") == locked_plan_id
                    and other_claim.get("binding_revision") == locked_binding_rev
                ):
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        "unique monotonic binding_revision under lease",
                        locked_binding_rev,
                        operation_id=operation_id,
                    )
            locked_allocated, _locked_base = _allocate_permanent_ids(
                triplet=locked_triplet,
                view_deltas=locked_preview["view_deltas"],
                inventory_ops=current,
                operation_id=operation_id,
                existing_allocations=frozen["allocations"],
            )
            _require(
                locked_allocated == frozen["allocations"]["task_ids"],
                "unchanged allocations under lease",
                operation_id,
                codec.ReasonCode.INPUT_STALE,
                operation_id=operation_id,
            )
            value = journal.draft_operation(root, request_raw=request_raw, frozen=frozen)

        captured = {
            journal._operation_ref(row["operation_id"]): codec.read_reference_bytes(
                root, journal._operation_ref(row["operation_id"])
            )
            for row in current
        }
        index_rel = journal.OPERATION_STORE + "/pending.json"
        index_path = journal._operation_path(root, index_rel)
        index_raw = index_path.read_bytes() if index_path.exists() else None

        def unchanged():
            snapshot.verify()
            _require(
                all(codec.read_reference_bytes(root, name) == raw for name, raw in captured.items())
                and (index_path.read_bytes() if index_path.exists() else None) == index_raw,
                "same operation/index at short writer boundary",
                operation_id,
                codec.ReasonCode.INPUT_STALE,
                operation_id=operation_id,
            )

        with op_scope.writer_boundary(root, recheck=unchanged):
            if live_existing != value:
                journal._operation_write(root, value, current, verify=False)
        persisted = journal.read_operation(root, operation_id=operation_id)
        _require(
            persisted == value,
            "complete persisted task compilation operation",
            operation_id,
            codec.ReasonCode.CONFLICT,
            operation_id=operation_id,
        )
        event_log = append_event(
            root,
            operation_id,
            "reserve" if reserve_only else "prepare",
            persisted["state"],
            {
                "plan_id": persisted["frozen"]["allocations"]["plan_id"],
                "binding_revision": persisted["frozen"]["allocations"]["binding_revision"],
                "allocated_task_count": len(persisted["frozen"]["allocations"]["task_ids"]),
                "frozen_digest": persisted["frozen_digest"],
            },
        )
        return _result(persisted, event_log=event_log)


@public
def prepare(root: Path | str, *, operation_id: str, request_ref: str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    raw = _read_bytes(root_path, request_ref)
    return _run(root_path, operation_id, raw, reserve_only=False)


@public
def reserve(root: Path | str, *, operation_id: str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA,
        OPERATION_SCHEMA,
        envelope["schema_version"],
        codec.ReasonCode.SCHEMA_MISMATCH,
        operation_id=operation_id,
    )
    return _run(
        root_path,
        operation_id,
        base64.b64decode(envelope["request_raw_base64"], validate=True),
        reserve_only=True,
    )


@public
def inspect(root: Path | str, *, operation_id: str) -> dict[str, Any]:
    """Read-only inspection of a prepared/reserved task compilation operation."""
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA,
        OPERATION_SCHEMA,
        envelope["schema_version"],
        codec.ReasonCode.SCHEMA_MISMATCH,
        operation_id=operation_id,
    )
    intent = commit.validate_local(root_path, envelope)
    sealed = commit._sealed_targets(intent) if intent is not None else None
    snapshot = CompilationSnapshot(root_path)
    differences: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ref in envelope["frozen"]["authority_refs"]:
        if intent is not None and ref["path"] == records.CATALOG_PATH and intent.get("catalog_after") is not None:
            actual_cat = _read_bytes(root_path, records.CATALOG_PATH, optional=True)
            cat_digest = codec.raw_digest(actual_cat) if actual_cat is not None else None
            if cat_digest not in {ref["raw_digest"], intent["catalog_after_digest"]}:
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.BUNDLE,
                        operation_id,
                        ref["raw_digest"],
                        cat_digest,
                        records.CATALOG_PATH,
                    ).to_dict()
                )
            continue
        try:
            snapshot.ref(ref)
        except codec.CodecError as err:
            diagnostics.append(err.diagnostic.to_dict())
    for target in envelope["frozen"]["targets"]:
        current = _read_bytes(root_path, target["path"], optional=True)
        digest = codec.raw_digest(current) if current is not None else None
        if target["verification_mode"] == "task_definition_projection":
            actual_proj = records.task_document_digest(target["path"], current) if current is not None else None
            matches_before = actual_proj == target["before_projection_digest"]
            matches_after = (
                sealed is not None
                and target["path"] in sealed
                and digest == sealed[target["path"]]["after_digest"]
                and actual_proj == target["after_projection_digest"]
            )
            matches = matches_before or matches_after
            row = {
                "path": target["path"],
                "verification_mode": target["verification_mode"],
                "expected_before_projection": target["before_projection_digest"],
                "actual_projection": actual_proj,
                "actual_raw_digest": digest,
                "frozen_after_projection": target["after_projection_digest"],
                "matches_before": matches_before,
            }
            differences.append(row)
            if not matches:
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.TARGET,
                        operation_id,
                        target["before_projection_digest"],
                        actual_proj,
                        journal._operation_ref(operation_id),
                    ).to_dict()
                )
        else:
            matches_before = digest == target["before_raw_digest"]
            matches_after = (
                sealed is not None
                and target["path"] in sealed
                and digest == sealed[target["path"]]["after_digest"]
            )
            matches = matches_before or matches_after
            row = {
                "path": target["path"],
                "verification_mode": target["verification_mode"],
                "expected_before": target["before_raw_digest"],
                "actual": digest,
                "frozen_after": target["after_raw_digest"],
                "matches_before": matches_before,
            }
            differences.append(row)
            if not matches:
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.TARGET,
                        operation_id,
                        target["before_raw_digest"],
                        digest,
                        journal._operation_ref(operation_id),
                    ).to_dict()
                )
    try:
        snapshot.verify()
    except codec.CodecError as err:
        diagnostics.append(err.diagnostic.to_dict())
    return {
        **_result(envelope),
        "target_differences": differences,
        "diagnostics": diagnostics,
        "status": "blocked" if diagnostics else "inspected",
        "eligibility": "read-only inspect; reserve and apply revalidate current proof and live triplet projection",
    }


@contextmanager
def commit_context(root: Path, *, operation_id: str):
    """Initial apply admission context for shared _b_route_commit.execute."""
    root = Path(root).resolve()
    envelope = journal.read_operation(root, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA and envelope["state"] == "reserved",
        "reserved task_compilation operation",
        operation_id,
        codec.ReasonCode.CONFLICT,
        operation_id=operation_id,
    )
    request = envelope["frozen"]["request"]
    snapshot, checked_frozen = build(
        root, request, allocations=envelope["frozen"]["allocations"]
    )
    # Compare status-invariant structure: live status may have advanced before apply lock.
    _require(
        checked_frozen["allocations"] == envelope["frozen"]["allocations"]
        and checked_frozen["scope_ids"] == envelope["frozen"]["scope_ids"]
        and checked_frozen["compilation"]["triplet_before_projections"]
        == envelope["frozen"]["compilation"]["triplet_before_projections"]
        and checked_frozen["compilation"]["triplet_after_projections"]
        == envelope["frozen"]["compilation"]["triplet_after_projections"]
        and checked_frozen["compilation"]["preview_digest"]
        == envelope["frozen"]["compilation"]["preview_digest"],
        "unchanged reserved task compilation semantics before apply freeze",
        operation_id,
        codec.ReasonCode.INPUT_STALE,
        operation_id=operation_id,
    )
    for frozen_t, checked_t in zip(envelope["frozen"]["targets"], checked_frozen["targets"]):
        _require(
            frozen_t["path"] == checked_t["path"]
            and frozen_t["verification_mode"] == checked_t["verification_mode"],
            "same target sequence before apply freeze",
            frozen_t["path"],
            codec.ReasonCode.INPUT_STALE,
        )
        if frozen_t["verification_mode"] == "immutable_bytes":
            _require(
                frozen_t["before_raw_digest"] == checked_t["before_raw_digest"]
                and frozen_t["after_raw_digest"] == checked_t["after_raw_digest"],
                "unchanged immutable formal targets before apply freeze",
                frozen_t["path"],
                codec.ReasonCode.INPUT_STALE,
            )
        else:
            _require(
                frozen_t["before_projection_digest"] == checked_t["before_projection_digest"]
                and frozen_t["after_projection_digest"] == checked_t["after_projection_digest"],
                "unchanged triplet definition projection before apply freeze",
                frozen_t["path"],
                codec.ReasonCode.INPUT_STALE,
            )
    snapshot.verify()
    yield snapshot, envelope


def verify_saved(root: Path, envelope: dict[str, Any]) -> None:
    """Re-verify saved request inputs and 3A current proof during unfinished apply/verify/publish/recover."""
    root = Path(root).resolve()
    journal._operation_validate(root, envelope)
    request = envelope["frozen"]["request"]
    op_scope._legacy_pending(root, None)
    for key in ("audit_ref", "preview_ref", "protection_ref", "manifest_ref", "change_intents_ref"):
        ref = request.get(key)
        if ref is None:
            continue
        raw = _read_bytes(root, ref["path"])
        _require(
            codec.raw_digest(raw) == ref["raw_digest"],
            ref["raw_digest"],
            ref["path"],
            codec.ReasonCode.INPUT_STALE,
        )
    audit_obs = sources.Observations(root)
    audit_proof = source_audit.verify_current_proof(
        audit_obs, request["audit_ref"]["path"], scope_id=request["scope_id"]
    )
    audit_obs.verify()
    audit_report = audit_proof.get("report") if isinstance(audit_proof, dict) else None
    _require(
        isinstance(audit_report, dict) and audit_report.get("planning_eligible") is True,
        "planning_eligible=True 3A source audit proof",
        audit_report.get("semantic_blockers") if isinstance(audit_report, dict) else audit_proof,
        codec.ReasonCode.INPUT_STALE,
        resume_ref=request["audit_ref"]["path"],
    )
    cfg_rel = str(chapter3_task_scope.CONFIG).replace("\\", "/")
    cfg_auth = next((ref for ref in envelope["frozen"]["authority_refs"] if ref["path"] == cfg_rel), None)
    cfg_raw = _read_bytes(root, cfg_rel, optional=True)
    if cfg_auth is not None:
        _require(
            cfg_raw is not None and codec.raw_digest(cfg_raw) == cfg_auth["raw_digest"],
            cfg_auth["raw_digest"],
            cfg_rel,
            codec.ReasonCode.INPUT_STALE,
            resume_ref=cfg_rel,
        )
    else:
        _require(
            cfg_raw is None,
            "absent legacy A chapter3-task-scope.json matching prepared state",
            cfg_rel,
            codec.ReasonCode.INPUT_STALE,
            resume_ref=cfg_rel,
        )
    if cfg_raw is not None:
        preview_doc = codec.strict_json_loads(_read_bytes(root, request["preview_ref"]["path"]))
        _check_chapter3_task_scope(
            root,
            view_deltas=preview_doc["view_deltas"],
            allocations=envelope["frozen"]["allocations"],
        )


def verify_observations(root: Path, envelope: dict[str, Any], intent: dict[str, Any], *, facts, published: bool = False) -> None:
    """Verify frozen commit.json observations; after commit.json freeze, ANY triplet edit blocks."""
    from _b_route_commit import _catalog_frame, _classify_target, _decode, _digest, _read, _sealed_targets
    import _b_route_adoption_review as review

    root = Path(root).absolute()
    _require(
        intent["policy_identity"] == review.policy_identity(),
        "same reviewed task compilation rules",
        "policy changed",
        codec.ReasonCode.INPUT_STALE,
    )
    sealed = _sealed_targets(intent)
    permitted = {
        str(root / path): (
            {row["after_digest"]} if published else {row["before_digest"], row["after_digest"]}
        )
        for path, row in sealed.items()
    }
    permitted[str(root / records.CATALOG_PATH)] = {_digest(_decode(intent["catalog_before"]))}
    if intent["catalog_after"] is not None:
        permitted[str(root / records.CATALOG_PATH)].add(_digest(_decode(intent["catalog_after"])))

    for name, expected in intent["files"].items():
        if name == str(root / records.CATALOG_PATH):
            continue
        obs_path = Path(name)
        journal._operation_no_reparse(obs_path)
        rel = obs_path.resolve().relative_to(root.resolve()).as_posix()
        actual = _digest(_read(root, rel, optional=True))
        _require(
            actual in permitted.get(name, {expected}),
            "unchanged compilation input or exact sealed target image",
            rel,
            codec.ReasonCode.INPUT_STALE,
        )
        facts.file(name, actual)

    for ref in envelope["frozen"]["authority_refs"]:
        if ref["path"] == records.CATALOG_PATH:
            continue
        actual = _digest(_read(root, ref["path"], optional=True))
        key = str(root / ref["path"])
        _require(
            actual in permitted.get(key, {ref["raw_digest"]}),
            ref["raw_digest"],
            ref["path"],
            codec.ReasonCode.INPUT_STALE,
        )
        facts.file(key, actual)

    for target in envelope["frozen"]["targets"]:
        checked = _classify_target(root, target, sealed=sealed)
        if published:
            _require(
                checked["state"] == "after",
                "all sealed targets in after state once published",
                target["path"],
                codec.ReasonCode.CONFLICT,
            )
        facts.file(str(root / target["path"]), checked["actual_raw_digest"])

    actual_catalog = _read(root, records.CATALOG_PATH)
    expected_catalog = _decode(intent["catalog_after"]) if published else _decode(intent["catalog_before"])
    if actual_catalog != expected_catalog and (published or actual_catalog != _decode(intent["catalog_after"])):
        _require(
            _catalog_frame(root, envelope, actual_catalog, intent["before_files"])
            == _catalog_frame(root, envelope, expected_catalog, intent["before_files"]),
            "unchanged affected catalog scope after unrelated publication",
            records.CATALOG_PATH,
            codec.ReasonCode.INPUT_STALE,
        )
    _require(
        _catalog_frame(
            root,
            envelope,
            _decode(intent["catalog_before"]),
            intent["before_files"],
            origins_raw=_decode(intent["origins_before"]),
        )
        == intent["catalog_frame"],
        "exact original catalog before frame",
        envelope["operation_id"],
        codec.ReasonCode.CONFLICT,
    )
    facts.file(str(root / records.CATALOG_PATH), _digest(actual_catalog))
