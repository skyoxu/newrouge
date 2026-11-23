"""Pure read-only zero-write unified Task origin and applicable plan-set resolver.

Classifies a single master Task ID into one of:
- "B": governed B-route ownership proven across committed policy/catalog/origins
  and active bindings, with complete applicable plan set and applicable_set_digest.
- "A": zero B obligations, zero residual B references/labels, and verified live
  against policy.frozen_a_refs (Story 1.5 protection archive / chapter3-task-scope)
  and policy.switch_boundary.allowed_a_operations.
- "explicit_not_enabled_a": zero B traces anywhere and valid Accepted ADR-0040
  proving explicit non-activation.
- "blocked": fail-closed on any pending/in-flight conflict, missing/damaged
  governance, reverse-index mismatch, frozen-A drift/missing archive, missing
  non-Flow definition, or mid-read drift.

Without an explicit --report path, this module creates zero directories, files,
or locks (never calls initialize_lock_namespace or write leases). It never
grants execution_authorized, readiness, runtime_verified, or default_b_enabled.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from copy import deepcopy
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
import uuid

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_inventory as inventory
import _b_route_operation_scope as op_scope
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_records as records
import _planning_apply_journal as journal
import chapter3_task_scope


SCHEMA = "newrouge.b-route-task-origin-resolution.v1"
TRIPLET = {
    "master": ".taskmaster/tasks/tasks.json",
    "back": ".taskmaster/tasks/tasks_back.json",
    "gameplay": ".taskmaster/tasks/tasks_gameplay.json",
}
POLICY_PATH = records.BASE + "policy.v1.json"
CATALOG_PATH = records.CATALOG_PATH
ORIGINS_PATH = records.BASE + "task-origins.v1.json"
GOVERNANCE = (POLICY_PATH, CATALOG_PATH, ORIGINS_PATH)
ADR_0040 = preflight.ADR
CHAPTER3_TASK_SCOPE = "docs/workflows/chapter3-task-scope.json"
CAP_PENDING = op_scope.CAP_PENDING
OP_STORE = op_scope.STORE
BUSINESS_SCOPE_PREFIXES = ("task:", "plan:", "flow:", "requirement:", "command:", "state:")
A_READ_ONLY_OPERATIONS = frozenset({"inspect", "read"})

AUTHORIZATION_FLAGS = {
    "execution_authorized": False,
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}

_B_LABEL_RE = re.compile(
    r"^(?:b[-_]route(?:[:/_-].*)?|route[:=]b|b[-_]plan[:=].+|b[-_]binding[:=].+)$",
    re.IGNORECASE,
)
_NA_LABEL_RE = re.compile(
    r"^(?:n/?a|(?:mvg|flow|b[-_]route)[:=_-]n/?a|non[-_]flow|no[-_]flow|skip[-_](?:mvg|flow)|exempt[-_](?:mvg|flow))$",
    re.IGNORECASE,
)
_B_TRACE_KEYS = frozenset({"plan_refs", "binding_refs", "origin_route", "b_route_origin"})


def _diag(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(
        code,
        stage,
        entity_id,
        expected,
        actual,
        resume_ref,
    ).to_dict()


def _fail(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> None:
    raise codec.CodecError(
        codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref)
    )


def _base_result(task_id: int | None, operation: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "ok": False,
        "stable": False,
        "task_id": task_id,
        "operation": operation,
        "route": "blocked",
        "governance_state": "blocked",
        "route_required": None,
        "policy_ref": None,
        "catalog_ref": None,
        "origins_ref": None,
        "authority_ref": None,
        "task_definition_digest": None,
        "task_view_refs": [],
        "plan_refs": [],
        "binding_refs": [],
        "source_refs": [],
        "resolved_definitions": [],
        "dispositions": [],
        "applicable_flow_closure": [],
        "applicable_requirements": [],
        "applicable_obligations": [],
        "applicable_implementation_objects": [],
        "applicable_scope_ids": [],
        "applicable_set_digest": None,
        "non_flow_summary": {
            "has_non_flow_dispositions": False,
            "dispositions_by_kind": {
                "flow": 0,
                "other_verification": 0,
                "deferred": 0,
                "source_gap": 0,
            },
            "free_label_exemption_allowed": False,
            "detected_non_authoritative_labels": [],
            "downstream_definition_check_required": False,
            "downstream_impact_check_required": False,
        },
        "frozen_a_boundary": None,
        "pending_summary": {
            "legacy_pending_clear": False,
            "blocking_operations": [],
            "non_overlapping_unapplied_operations": [],
        },
        **AUTHORIZATION_FLAGS,
        "authorization": dict(AUTHORIZATION_FLAGS),
        "report_path": None,
        "diagnostics": [],
    }


def _validate_root(root: Path) -> Path:
    root_path = Path(root).absolute()
    try:
        for ancestor in reversed((root_path, *root_path.parents)):
            inventory.no_reparse(ancestor)
        if not root_path.is_dir():
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                stage=codec.Stage.PATH,
                expected="existing repository root directory",
                actual=str(root),
            )
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="safe contained repository root directory",
            actual=type(error).__name__,
        )
    return root_path


def _validate_operation(operation: Any) -> str | None:
    if operation is None:
        return None
    if type(operation) is not str or not operation.strip() or operation != operation.strip():
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            stage=codec.Stage.CONTENT,
            expected="nonempty unpadded operation string or null",
            actual=operation,
        )
    return operation


def _extract_labels(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for field in ("labels", "tags"):
        values = row.get(field)
        if type(values) is list:
            for item in values:
                if type(item) is str and item.strip():
                    found.append(item.strip())
        elif type(values) is str:
            for part in re.split(r"[;,]", values):
                token = part.strip()
                if token:
                    found.append(token)
    details = row.get("details")
    if type(details) is str:
        for line in details.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()
            if lowered.startswith("labels:") or lowered.startswith("tags:"):
                raw_labels = stripped.split(":", 1)[1]
                for part in re.split(r"[;,]", raw_labels):
                    token = part.strip()
                    if token:
                        found.append(token)
    return found


def _iter_strings(value: Any):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _iter_strings(item)
    elif type(value) is dict:
        for item in value.values():
            yield from _iter_strings(item)


def _scan_row_traces(row: Any, location: str) -> tuple[list[str], list[str]]:
    """Return (residual_b_traces, free_na_labels) for one Task row and its subtasks."""
    b_traces: list[str] = []
    na_labels: list[str] = []
    if type(row) is not dict:
        return b_traces, na_labels
    for key in sorted(row):
        lowered = key.casefold()
        if "b_route" in lowered or lowered in _B_TRACE_KEYS:
            b_traces.append(f"{location}:key:{key}")
        if lowered in ("mvg_applicable", "flow_applicable"):
            val = row[key]
            if val is False or (type(val) is str and _NA_LABEL_RE.fullmatch(val.strip())):
                na_labels.append(f"{location}:{key}={val}")
    for field in (
        "source_refs",
        "evidence_refs",
        "overlay_refs",
        "history_refs",
        "refs",
        "acceptance",
        "test_refs",
        "details",
        "overlay",
    ):
        if field in row:
            for text_val in _iter_strings(row[field]):
                if "docs/planning/b-route/" in text_val.replace("\\", "/").casefold():
                    b_traces.append(f"{location}:{field}:{text_val}")
    for label in _extract_labels(row):
        if _B_LABEL_RE.fullmatch(label):
            b_traces.append(f"{location}:label:{label}")
        if _NA_LABEL_RE.fullmatch(label):
            na_labels.append(f"{location}:label:{label}")
    subtasks = row.get("subtasks")
    if type(subtasks) is list:
        for s_idx, sub in enumerate(subtasks):
            sub_b, sub_na = _scan_row_traces(sub, f"{location}.subtasks[{s_idx}]")
            b_traces.extend(sub_b)
            na_labels.extend(sub_na)
    return b_traces, na_labels


def _scan_triplet_traces(docs: dict[str, Any]) -> tuple[list[str], dict[int, tuple[list[str], list[str]]]]:
    global_b: list[str] = []
    per_task: dict[int, tuple[list[str], list[str]]] = {}
    for idx, row in enumerate(docs["master"]["master"]["tasks"]):
        tid = row["id"]
        b_list, na_list = _scan_row_traces(row, f"master[{idx}]")
        global_b.extend(b_list)
        entry = per_task.setdefault(tid, ([], []))
        entry[0].extend(b_list)
        entry[1].extend(na_list)
    for view_name in ("back", "gameplay"):
        for idx, row in enumerate(docs[view_name]):
            tid = row["taskmaster_id"]
            b_list, na_list = _scan_row_traces(row, f"{view_name}[{idx}]")
            global_b.extend(b_list)
            entry = per_task.setdefault(tid, ([], []))
            entry[0].extend(b_list)
            entry[1].extend(na_list)
    return sorted(set(global_b)), {
        tid: (sorted(set(b_list)), sorted(set(na_list)))
        for tid, (b_list, na_list) in per_task.items()
    }


def _check_adr_0040_not_enabled(
    observations: preflight.Observations,
    *,
    entity_id: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    raw = observations.read(ADR_0040, optional=True)
    if raw is None:
        return False, _diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="Accepted ADR-0040 establishing explicit not-enabled A boundary",
            actual=None,
            resume_ref=ADR_0040,
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False, _diag(
            codec.ReasonCode.INVALID_UTF8,
            stage=codec.Stage.DECODE,
            entity_id=entity_id,
            expected="UTF-8 ADR-0040 governance document",
            actual="invalid UTF-8",
            resume_ref=ADR_0040,
        )
    authority_body = "\n".join(line for _, line in inventory.markdown_status_lines(text))
    statuses: list[str] = []
    for line in authority_body.splitlines():
        match = re.match(
            r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:status|\u72b6\u6001)(?:\*\*)?\s*[:\uff1a]\s*(.+?)\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            statuses.append(match[1].strip("* ").casefold())
    required_clauses = (
        "\u672c\u6587\u4e0d\u51bb\u7ed3 A\u3001\u4e0d\u5207\u6362\u9ed8\u8ba4 B\u3001\u4e0d\u9000\u51fa A",
        "\u8fc1\u79fb\u542f\u7528\u524d\u6cbf\u663e\u5f0f\u539f\u5165\u53e3\u6267\u884c\u5f53\u524d A",
    )
    if set(statuses) == {"accepted"} and all(clause in authority_body for clause in required_clauses):
        return True, None
    return False, _diag(
        codec.ReasonCode.IDENTITY_UNPROVABLE,
        stage=codec.Stage.BUNDLE,
        entity_id=entity_id,
        expected="Accepted ADR-0040 with explicit not-enabled governance clauses",
        actual={"statuses": sorted(set(statuses))},
        resume_ref=ADR_0040,
    )


def _inspect_pending(
    root: Path,
    observations: preflight.Observations,
    task_id: int,
    *,
    pending_summary: dict[str, Any],
    graph_bytes_holder: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], set[str], set[str]]]]:
    """Read-only zero-write pending inspection across legacy and B-route operations."""
    # 1. Legacy pending marker and unfinished legacy apply journals (no scope_id).
    observations.read(CAP_PENDING, optional=True)
    for legacy_dir in ("logs/ci/capability-planning", "logs/ci/mvg-planning"):
        for rel in observations.scan(legacy_dir):
            observations.read(rel, optional=True)
    op_scope._legacy_pending(root, None)
    pending_summary["legacy_pending_clear"] = True

    # 2. B-route operation store (pure read-only; returns empty if logs/ absent).
    observations.scan(OP_STORE)
    graph = journal.operation_state_graph(root)
    for rel, raw_bytes in graph["local_bytes"].items():
        observations.read(rel, optional=raw_bytes is None)
    graph_bytes_holder["bytes"] = dict(graph["local_bytes"])

    blocking_ops: list[dict[str, Any]] = []
    unapplied_ops: list[tuple[dict[str, Any], set[str], set[str]]] = []

    for op in graph["operations"]:
        op_id = op["operation_id"]
        if op_id in graph["terminals"] or op_id in graph["resolved_by"]:
            continue
        intent = graph["intents"].get(op_id)
        intent_path, pending_path = commit._paths(op_id)
        has_pending_marker = graph["local_bytes"].get(pending_path) is not None
        if intent is not None or has_pending_marker:
            phase = intent["phase"] if type(intent) is dict else None
            code = codec.ReasonCode.PENDING if has_pending_marker else codec.ReasonCode.UNPUBLISHED
            resume = intent_path if intent is not None else pending_path
            blocking_ops.append(
                {
                    "operation_id": op_id,
                    "state": op["state"],
                    "phase": phase,
                    "has_commit_intent": intent is not None,
                    "has_pending_marker": has_pending_marker,
                    "resume_ref": resume,
                }
            )
            pending_summary["blocking_operations"] = list(blocking_ops)
            _fail(
                code,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="no active in-flight commit.json or commit.pending.json operation",
                actual={
                    "operation_id": op_id,
                    "phase": phase,
                    "has_commit_intent": intent is not None,
                    "has_pending_marker": has_pending_marker,
                },
                resume_ref=resume,
            )
        if op.get("state") not in ("prepared", "reserved"):
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="known unapplied operation state (prepared|reserved)",
                actual=op.get("state"),
                resume_ref=journal._operation_ref(op_id),
            )
        frozen = op.get("frozen")
        if type(frozen) is not dict or type(frozen.get("scope_ids")) is not list or not frozen["scope_ids"]:
            _fail(
                codec.ReasonCode.PENDING,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="complete frozen scope_ids for unapplied operation",
                actual="unknown scope",
                resume_ref=journal._operation_ref(op_id),
            )
        raw_scopes = op_scope._scopes(frozen["scope_ids"])
        business_scopes = {s for s in raw_scopes if s.startswith(BUSINESS_SCOPE_PREFIXES)}
        named_scopes = {
            s for s in raw_scopes if not s.startswith("file:") and not s.startswith(BUSINESS_SCOPE_PREFIXES)
        }
        if not business_scopes:
            _fail(
                codec.ReasonCode.PENDING,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="known business scopes (task/plan/flow/requirement/command/state)",
                actual={"operation_id": op_id, "scope_ids": list(raw_scopes)},
                resume_ref=journal._operation_ref(op_id),
            )
        if f"task:{task_id}" in business_scopes:
            _fail(
                codec.ReasonCode.PENDING,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="nonoverlapping unapplied operation for queried Task",
                actual={"operation_id": op_id, "overlap": [f"task:{task_id}"]},
                resume_ref=journal._operation_ref(op_id),
            )
        unapplied_ops.append((op, business_scopes, named_scopes))

    pending_summary["blocking_operations"] = list(blocking_ops)
    return graph, unapplied_ops


def _check_unapplied_overlap(
    unapplied_ops: list[tuple[dict[str, Any], set[str], set[str]]],
    *,
    task_business_scopes: set[str],
    owning_scope_ids: set[str],
) -> list[dict[str, Any]]:
    non_overlapping: list[dict[str, Any]] = []
    for op, op_business_scopes, op_named_scopes in unapplied_ops:
        op_id = op["operation_id"]
        overlap = sorted((op_business_scopes & task_business_scopes) | (op_named_scopes & owning_scope_ids))
        if overlap:
            _fail(
                codec.ReasonCode.PENDING,
                stage=codec.Stage.BUNDLE,
                entity_id=op_id,
                expected="nonoverlapping business scope for unapplied prepared/reserved operation",
                actual={"operation_id": op_id, "state": op["state"], "overlap": overlap},
                resume_ref=journal._operation_ref(op_id),
            )
        non_overlapping.append(
            {
                "operation_id": op_id,
                "state": op["state"],
                "scope_ids": list(op["frozen"]["scope_ids"]),
            }
        )
    return non_overlapping


def _plan_ref_sort_key(ref: dict[str, Any]) -> tuple[str, int, str, str]:
    return (ref["entity_id"], ref["revision"], ref["path"], ref["digest"])


def _owned_ref_sort_key(ref: dict[str, Any]) -> tuple[str, str, str]:
    return (ref["owner"], ref["ref"], codec.canonical_digest(ref["files"]))


def _def_owner_sort_key(row: dict[str, Any]) -> tuple[str, str, str, int, str]:
    pref = row["plan_ref"]
    return (row["kind"], row["definition_id"], pref["entity_id"], pref["revision"], pref["digest"])


def _disposition_sort_key(row: dict[str, Any]) -> tuple[str, int, str, str]:
    return (row["plan_id"], row["plan_revision"], row["requirement_id"], row["disposition"])


def _load_formal_json(observations: preflight.Observations, ref: dict[str, Any]) -> dict[str, Any]:
    raw = observations.read(ref["path"])
    doc = codec.strict_json_loads(raw)
    digest = codec.raw_digest(raw) if ref["verification_mode"] == "raw" else codec.canonical_digest(doc)
    if digest != ref["digest"]:
        _fail(
            codec.ReasonCode.DIGEST_MISMATCH,
            stage=codec.Stage.REFERENCE,
            entity_id=ref["entity_id"],
            expected=ref["digest"],
            actual=digest,
            resume_ref=ref["path"],
        )
    return doc


def _observe_non_log_owned_ref(ref: dict[str, Any], observations: preflight.Observations) -> None:
    """Resolve/read non-log external OwnedRef files via Observations while preserving clean-clone log seals."""
    files = ref.get("files") if type(ref) is dict else None
    if type(files) is not list or not files:
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            stage=codec.Stage.REFERENCE,
            expected="nonempty OwnedRef files",
            actual=ref,
        )
    has_log = any(preflight.path(row["path"]).startswith("logs/") for row in files)
    if not has_log and ref.get("owner") != "contract":
        ref_loc = ref["ref"].partition("#")[0]
        if preflight.path(ref_loc).startswith("logs/"):
            has_log = True
    if not has_log:
        preflight.owned(ref, observations)
        return
    for row in files:
        rel = preflight.path(row["path"])
        if rel.startswith("logs/"):
            continue
        raw = observations.read(rel)
        actual = codec.raw_digest(raw)
        if actual != row["raw_digest"]:
            _fail(
                codec.ReasonCode.DIGEST_MISMATCH,
                stage=codec.Stage.REFERENCE,
                expected={"path": rel, "raw_digest": row["raw_digest"]},
                actual={"path": rel, "raw_digest": actual},
                resume_ref=rel,
            )


def _resolve_b_applicable_set(
    *,
    observations: preflight.Observations,
    catalog: dict[str, Any],
    origins: dict[str, Any],
    task_id: int,
    origins_row: dict[str, Any],
    catalog_row: dict[str, Any],
    active_bindings: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    task_na_labels: list[str],
    unapplied_ops: list[tuple[dict[str, Any], set[str], set[str]]],
) -> dict[str, Any]:
    # Verify three-way consistency explicitly between origins.tasks, catalog.task_index, and active bindings.
    origin_plans = {codec.canonical_digest(ref): ref for ref in origins_row["plan_refs"]}
    origin_bindings = {codec.canonical_digest(ref): ref for ref in origins_row["binding_refs"]}
    catalog_plans = {codec.canonical_digest(ref): ref for ref in catalog_row["plan_refs"]}
    catalog_bindings = {codec.canonical_digest(ref): ref for ref in catalog_row["binding_refs"]}
    active_plan_map = {
        codec.canonical_digest(binding_doc["plan_ref"]): binding_doc["plan_ref"]
        for _, binding_doc, _ in active_bindings
    }
    active_binding_map = {
        codec.canonical_digest(binding_ref): binding_ref
        for binding_ref, _, _ in active_bindings
    }

    if origin_plans != catalog_plans or origin_plans != active_plan_map:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="identical plan_refs across origins.tasks, catalog.task_index, and active bindings",
            actual={
                "origins_plans": sorted(origin_plans),
                "catalog_plans": sorted(catalog_plans),
                "active_binding_plans": sorted(active_plan_map),
            },
            resume_ref=ORIGINS_PATH,
        )
    if origin_bindings != catalog_bindings or origin_bindings != active_binding_map:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="identical binding_refs across origins.tasks, catalog.task_index, and active bindings",
            actual={
                "origins_bindings": sorted(origin_bindings),
                "catalog_bindings": sorted(catalog_bindings),
                "active_bindings": sorted(active_binding_map),
            },
            resume_ref=ORIGINS_PATH,
        )
    if not origin_plans or not origin_bindings:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="nonempty applicable plan_refs and binding_refs for B-route Task",
            actual={"plan_count": len(origin_plans), "binding_count": len(origin_bindings)},
            resume_ref=ORIGINS_PATH,
        )

    sorted_plan_refs = sorted((deepcopy(r) for r in origin_plans.values()), key=_plan_ref_sort_key)
    sorted_binding_refs = sorted((deepcopy(r) for r in origin_bindings.values()), key=_plan_ref_sort_key)
    sorted_source_refs = sorted((deepcopy(r) for r in origins_row["source_refs"]), key=_owned_ref_sort_key)
    for sref in sorted_source_refs:
        _observe_non_log_owned_ref(sref, observations)

    # Index catalog definition_owners with duplicate guard and load owner plans on demand.
    owners_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in catalog["definition_owners"]:
        owner_key = (row["kind"], row["definition_id"])
        if owner_key in owners_map:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="unique (kind, definition_id) in catalog.definition_owners",
                actual=list(owner_key),
                resume_ref=CATALOG_PATH,
            )
        owners_map[owner_key] = deepcopy(row)
    loaded_plans: dict[str, dict[str, Any]] = {}

    def load_plan(pref: dict[str, Any]) -> dict[str, Any]:
        key = codec.canonical_digest(pref)
        if key not in loaded_plans:
            plan_doc = _load_formal_json(observations, pref)
            if plan_doc.get("plan_id") != pref["entity_id"] or plan_doc.get("revision") != pref["revision"]:
                _fail(
                    codec.ReasonCode.REVISION_MISMATCH,
                    stage=codec.Stage.REFERENCE,
                    entity_id=pref["entity_id"],
                    expected=[pref["entity_id"], pref["revision"]],
                    actual=[plan_doc.get("plan_id"), plan_doc.get("revision")],
                    resume_ref=pref["path"],
                )
            loaded_plans[key] = plan_doc
        return loaded_plans[key]

    for pref in sorted_plan_refs:
        load_plan(pref)

    # Gather dispositions, flows, obligations, implementation objects, and validate non-Flow discipline.
    dispositions: list[dict[str, Any]] = []
    applicable_flow_ids: set[str] = set()
    applicable_req_ids: set[str] = set()
    seen_obligations: dict[tuple[str, int, str], dict[str, Any]] = {}
    seen_impl_objects: dict[tuple[str, int, str], dict[str, Any]] = {}
    task_binding_entries: list[Any] = []
    dispositions_by_kind = {"flow": 0, "other_verification": 0, "deferred": 0, "source_gap": 0}
    seen_dispositions: set[tuple[str, int, str]] = set()
    plan_indexes: dict[str, dict[str, Any]] = {}

    def _plan_index(pref: dict[str, Any], pdoc: dict[str, Any]) -> dict[str, Any]:
        pkey = codec.canonical_digest(pref)
        if pkey not in plan_indexes:
            req_evidence_by_id: dict[str, dict[str, Any]] = {}
            for row in pdoc["requirement_evidence"]:
                ev_id = row["evidence_id"]
                if ev_id in req_evidence_by_id:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(task_id),
                        expected="unique evidence_id in plan.requirement_evidence",
                        actual=ev_id,
                        resume_ref=pref["path"],
                    )
                req_evidence_by_id[ev_id] = row
            route_memberships_by_req: dict[str, list[str]] = {}
            for row in pdoc["requirement_route_memberships"]:
                route_memberships_by_req.setdefault(row["requirement_id"], []).append(row["flow_id"])
            plan_indexes[pkey] = {
                "req_defs": {r["requirement_id"]: r for r in pdoc["requirements"]},
                "verif_map": {r["requirement_id"]: r for r in pdoc["requirement_verification"]},
                "evidence_refs": {(r["owner"], r["ref"]): r for r in pdoc["evidence_source_refs"]},
                "route_memberships_by_req": route_memberships_by_req,
                "req_evidence_by_id": req_evidence_by_id,
            }
        return plan_indexes[pkey]

    def _validate_flow_owner(fid: str, *, resume_ref: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        owner = owners_map.get(("flow", fid))
        if owner is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="catalog definition_owner for flow",
                actual=fid,
                resume_ref=resume_ref,
            )
        owner_plan = load_plan(owner["plan_ref"])
        flow_def = next((f for f in owner_plan["definitions"]["flows"] if f["id"] == fid), None)
        if flow_def is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="flow definition in owner plan",
                actual=fid,
                resume_ref=owner["plan_ref"]["path"],
            )
        return owner, owner_plan, flow_def

    def _validate_requirement(target_plan_ref: dict[str, Any], target_plan_doc: dict[str, Any], req_id: str) -> None:
        t_plan_id = target_plan_doc["plan_id"]
        t_plan_rev = target_plan_doc["revision"]
        idx = _plan_index(target_plan_ref, target_plan_doc)
        req_defs = idx["req_defs"]
        verif_map = idx["verif_map"]
        evidence_refs = idx["evidence_refs"]
        route_memberships_by_req = idx["route_memberships_by_req"]
        req_evidence_by_id = idx["req_evidence_by_id"]

        applicable_req_ids.add(req_id)
        if req_id not in req_defs or req_id not in verif_map:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="committed requirement and requirement_verification disposition",
                actual={"plan_id": t_plan_id, "requirement_id": req_id},
                resume_ref=target_plan_ref["path"],
            )
        verif = verif_map[req_id]
        disp = verif["disposition"]
        if disp not in dispositions_by_kind:
            _fail(
                codec.ReasonCode.INVALID_ENUM,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="known requirement_verification disposition",
                actual=disp,
                resume_ref=target_plan_ref["path"],
            )
        if disp == "source_gap":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="resolved disposition (flow|other_verification|deferred); source_gap blocks execution",
                actual={"plan_id": t_plan_id, "requirement_id": req_id, "disposition": disp},
                resume_ref=target_plan_ref["path"],
            )
        if disp == "flow":
            fid = verif["flow_id"]
            _validate_flow_owner(fid, resume_ref=target_plan_ref["path"])
            applicable_flow_ids.add(fid)
        elif disp == "other_verification":
            if (
                not verif.get("rationale")
                or not verif.get("sink_id")
                or not verif.get("verification_ref")
                or ("other_verification", verif["verification_ref"]) not in evidence_refs
            ):
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="complete other_verification rationale, sink_id, and resolved verification_ref",
                    actual=verif,
                    resume_ref=target_plan_ref["path"],
                )
            _observe_non_log_owned_ref(
                evidence_refs[("other_verification", verif["verification_ref"])],
                observations,
            )
        elif disp == "deferred":
            if (
                not verif.get("rationale")
                or not verif.get("authority_ref")
                or ("authority", verif["authority_ref"]) not in evidence_refs
            ):
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="complete deferred rationale and resolved authority_ref",
                    actual=verif,
                    resume_ref=target_plan_ref["path"],
                )
            _observe_non_log_owned_ref(
                evidence_refs[("authority", verif["authority_ref"])],
                observations,
            )

        for ev_id in verif["evidence_ids"]:
            ev_row = req_evidence_by_id.get(ev_id)
            if ev_row is None or ev_row.get("requirement_id") != req_id:
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="declared requirement_evidence entry matching evidence_id",
                    actual={"plan_id": t_plan_id, "requirement_id": req_id, "evidence_id": ev_id},
                    resume_ref=target_plan_ref["path"],
                )
            ev_owned = evidence_refs.get((ev_row["kind"], ev_row["source_ref"]))
            if ev_owned is not None:
                _observe_non_log_owned_ref(ev_owned, observations)

        for route_fid in route_memberships_by_req.get(req_id, []):
            _validate_flow_owner(route_fid, resume_ref=target_plan_ref["path"])
            applicable_flow_ids.add(route_fid)

        disp_key = (t_plan_id, t_plan_rev, req_id)
        if disp_key not in seen_dispositions:
            seen_dispositions.add(disp_key)
            dispositions_by_kind[disp] += 1
            dispositions.append(
                {
                    "plan_id": t_plan_id,
                    "plan_revision": t_plan_rev,
                    "requirement_id": req_id,
                    "disposition": disp,
                    "flow_id": verif["flow_id"],
                    "rationale": verif["rationale"],
                    "sink_id": verif["sink_id"],
                    "verification_ref": verif["verification_ref"],
                    "authority_ref": verif["authority_ref"],
                    "evidence_ids": sorted(verif["evidence_ids"]),
                    "route_flow_ids": sorted(set(route_memberships_by_req.get(req_id, []))),
                }
            )

    for binding_ref, binding_doc, mapping in active_bindings:
        plan_ref = binding_doc["plan_ref"]
        plan_doc = load_plan(plan_ref)
        plan_id = plan_doc["plan_id"]
        plan_rev = plan_doc["revision"]
        task_binding_entries.append(mapping)

        obl_map = {row["id"]: row for row in binding_doc["obligations"]}
        mapped_reqs = list(mapping["requirement_ids"])
        mapped_flows = list(mapping["flow_ids"])
        mapped_obls = list(mapping["obligation_ids"])

        for obl_id in mapped_obls:
            if obl_id not in obl_map:
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="declared binding obligation",
                    actual=obl_id,
                    resume_ref=binding_ref["path"],
                )
            obl = obl_map[obl_id]
            task_binding_entries.append(obl)
            for vref in obl.get("verification_refs", []):
                _observe_non_log_owned_ref(vref, observations)
            obl_key = (plan_id, binding_doc["binding_revision"], obl["id"])
            if obl_key not in seen_obligations:
                seen_obligations[obl_key] = {
                    "plan_id": plan_id,
                    "binding_revision": binding_doc["binding_revision"],
                    "binding_stage": binding_doc["stage"],
                    **deepcopy(obl),
                }
            for req_id in obl["requirement_ids"]:
                if req_id not in mapped_reqs:
                    mapped_reqs.append(req_id)
            for flow_id in obl["flow_ids"]:
                if flow_id not in mapped_flows:
                    mapped_flows.append(flow_id)

        for obj in binding_doc["implementation_objects"]:
            if task_id in obj["responsible_task_ids"]:
                task_binding_entries.append(obj)
                obj_key = (plan_id, binding_doc["binding_revision"], obj["id"])
                if obj_key not in seen_impl_objects:
                    seen_impl_objects[obj_key] = {
                        "plan_id": plan_id,
                        "binding_revision": binding_doc["binding_revision"],
                        "binding_stage": binding_doc["stage"],
                        **deepcopy(obj),
                    }

        if not mapped_reqs and not mapped_flows:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="committed plan requirement disposition or flow definition; free-text N/A labels never grant exemption",
                actual={
                    "binding_path": binding_ref["path"],
                    "requirement_ids": mapped_reqs,
                    "flow_ids": mapped_flows,
                    "detected_non_authoritative_labels": task_na_labels,
                },
                resume_ref=binding_ref["path"],
            )

        cross_plan_reqs: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for flow_id in mapped_flows:
            owner, owner_plan, flow_def = _validate_flow_owner(flow_id, resume_ref=binding_ref["path"])
            applicable_flow_ids.add(flow_id)
            for freq_id in flow_def.get("requirement_ids", []):
                if owner_plan["plan_id"] == plan_id and owner_plan["revision"] == plan_rev:
                    if freq_id not in mapped_reqs:
                        mapped_reqs.append(freq_id)
                else:
                    cross_plan_reqs.append((owner["plan_ref"], owner_plan, freq_id))

        for req_id in mapped_reqs:
            _validate_requirement(plan_ref, plan_doc, req_id)
        for owner_pref, owner_pdoc, freq_id in cross_plan_reqs:
            _validate_requirement(owner_pref, owner_pdoc, freq_id)

    # Compute task-scoped recursive resolved_definitions closure across applicable flows,
    # commands/states linked to applicable requirements, and active binding uses.
    use_fields = {"kind", "definition_id", "owner_plan_id", "owner_revision"}

    def _collect_uses(obj: Any) -> list[dict[str, Any]]:
        return [child for child in records._walk(obj) if type(child) is dict and set(child) == use_fields]

    pending_uses: list[dict[str, Any]] = []
    resolved_def_map: dict[tuple[str, str], dict[str, Any]] = {}

    # Seed (a): task-applicable flows.
    for flow_id in sorted(applicable_flow_ids):
        owner, _owner_plan, flow_def = _validate_flow_owner(flow_id, resume_ref=CATALOG_PATH)
        resolved_def_map[("flow", flow_id)] = owner
        pending_uses.extend(_collect_uses(flow_def))

    # Seed (b): commands and states in applicable plans whose requirement_ids intersect applicable_req_ids.
    for pref in sorted_plan_refs:
        plan_doc = load_plan(pref)
        for kind, plural in (("command", "commands"), ("state", "states")):
            for defn in plan_doc["definitions"][plural]:
                if set(defn.get("requirement_ids", [])) & applicable_req_ids:
                    key = (kind, defn["id"])
                    owner = owners_map.get(key)
                    if owner is None:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            stage=codec.Stage.BUNDLE,
                            entity_id=str(task_id),
                            expected="explicit catalog definition owner",
                            actual=list(key),
                            resume_ref=CATALOG_PATH,
                        )
                    resolved_def_map[key] = owner
                    pending_uses.extend(_collect_uses(defn))

    # Seed (c): logical definition uses inside the task's active binding entries.
    for entry in task_binding_entries:
        pending_uses.extend(_collect_uses(entry))

    visited_defs: set[tuple[str, str, str]] = set()
    while pending_uses:
        use = pending_uses.pop()
        key = (use["kind"], use["definition_id"])
        if key not in owners_map:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="explicit catalog definition owner",
                actual=list(key),
                resume_ref=CATALOG_PATH,
            )
        owner = owners_map[key]
        pref = owner["plan_ref"]
        if pref["entity_id"] != use["owner_plan_id"] or pref["revision"] != use["owner_revision"]:
            _fail(
                codec.ReasonCode.REVISION_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected=[use["owner_plan_id"], use["owner_revision"]],
                actual=[pref["entity_id"], pref["revision"]],
                resume_ref=CATALOG_PATH,
            )
        resolved_def_map[key] = owner
        visit_id = (key[0], key[1], codec.canonical_digest(pref))
        if visit_id in visited_defs:
            continue
        visited_defs.add(visit_id)
        owner_plan = load_plan(pref)
        plural = {"flow": "flows", "command": "commands", "state": "states"}[key[0]]
        defn = next((r for r in owner_plan["definitions"][plural] if r["id"] == key[1]), None)
        if defn is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="declared owner definition in owner plan",
                actual=list(key),
                resume_ref=pref["path"],
            )
        if key[0] == "flow":
            applicable_flow_ids.add(key[1])
        pending_uses.extend(_collect_uses(defn))

    sorted_resolved_definitions = sorted(resolved_def_map.values(), key=_def_owner_sort_key)
    sorted_dispositions = sorted(dispositions, key=_disposition_sort_key)
    applicable_flow_closure = sorted(
        applicable_flow_ids | {k[1] for k in resolved_def_map if k[0] == "flow"}
    )
    applicable_command_ids = sorted(k[1] for k in resolved_def_map if k[0] == "command")
    applicable_state_ids = sorted(k[1] for k in resolved_def_map if k[0] == "state")
    applicable_plan_ids = sorted({ref["entity_id"] for ref in sorted_plan_refs} | {
        row["plan_ref"]["entity_id"] for row in sorted_resolved_definitions
    })

    # Determine owning catalog scope_ids.
    owning_scope_ids: set[str] = set()
    applicable_plan_keys = set(origin_plans) | {
        codec.canonical_digest(row["plan_ref"]) for row in sorted_resolved_definitions
    }
    applicable_binding_keys = set(origin_bindings)
    for head in catalog["scope_heads"]:
        head_plan_keys = {codec.canonical_digest(ref) for ref in head["plan_refs"]}
        head_binding_keys = {codec.canonical_digest(ref) for ref in head["binding_refs"]}
        if (head_plan_keys & applicable_plan_keys) or (head_binding_keys & applicable_binding_keys):
            owning_scope_ids.add(head["scope_id"])

    # Check overlap against unapplied prepared/reserved operations using business scopes ONLY.
    task_business_scopes = set(
        op_scope.resource_scopes(
            task_ids=[task_id],
            plan_ids=applicable_plan_ids,
            requirement_ids=sorted(applicable_req_ids),
            flow_ids=applicable_flow_closure,
            command_ids=applicable_command_ids,
            state_ids=applicable_state_ids,
        )
    )
    non_overlapping_ops = _check_unapplied_overlap(
        unapplied_ops,
        task_business_scopes=task_business_scopes,
        owning_scope_ids=owning_scope_ids,
    )

    has_non_flow = (dispositions_by_kind["other_verification"] + dispositions_by_kind["deferred"]) > 0
    downstream_checks_required = bool(has_non_flow or task_na_labels)
    applicable_set_payload = {
        "task_id": task_id,
        "plan_refs": sorted_plan_refs,
        "binding_refs": sorted_binding_refs,
        "source_refs": sorted_source_refs,
        "resolved_definitions": sorted_resolved_definitions,
        "dispositions": sorted_dispositions,
    }
    applicable_set_digest = codec.canonical_digest(applicable_set_payload)

    return {
        "plan_refs": sorted_plan_refs,
        "binding_refs": sorted_binding_refs,
        "source_refs": sorted_source_refs,
        "resolved_definitions": sorted_resolved_definitions,
        "dispositions": sorted_dispositions,
        "applicable_flow_closure": applicable_flow_closure,
        "applicable_requirements": sorted(applicable_req_ids),
        "applicable_obligations": sorted(
            seen_obligations.values(),
            key=lambda r: (r["plan_id"], r["binding_revision"], r["id"]),
        ),
        "applicable_implementation_objects": sorted(
            seen_impl_objects.values(),
            key=lambda r: (r["plan_id"], r["binding_revision"], r["id"]),
        ),
        "applicable_scope_ids": sorted(owning_scope_ids),
        "applicable_set_digest": applicable_set_digest,
        "non_flow_summary": {
            "has_non_flow_dispositions": has_non_flow,
            "dispositions_by_kind": dispositions_by_kind,
            "free_label_exemption_allowed": False,
            "detected_non_authoritative_labels": list(task_na_labels),
            "downstream_definition_check_required": downstream_checks_required,
            "downstream_impact_check_required": downstream_checks_required,
        },
        "non_overlapping_unapplied_operations": non_overlapping_ops,
    }


def _load_frozen_a_snapshot(
    root: Path,
    observations: preflight.Observations,
    snapshot_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify a Story 1.5 protection snapshot and record all its archive bytes in Observations."""
    observations.read(snapshot_path)
    snapshot, report, _raw_files = protection._load_snapshot(root, snapshot_path)
    parent = snapshot_path.rsplit("/", 1)[0] + "/" if "/" in snapshot_path else ""
    observations.read(parent + "inventory.json")
    observations.read(parent + "report.json", optional=True)
    for row in snapshot["raw_files"]:
        if row.get("exists") is True and row.get("artifact"):
            observations.read(parent + row["artifact"])
    return snapshot, report


def _parse_task_scope(observations: preflight.Observations, scope_path: str) -> set[int]:
    raw = observations.read(scope_path)
    scope_doc = codec.strict_json_loads(raw)
    if (
        type(scope_doc) is not dict
        or scope_doc.get("schema_version") != "chapter3.task-scope.v1"
        or scope_doc.get("mode") != "reconcile-existing-only"
    ):
        _fail(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            stage=codec.Stage.SCHEMA,
            expected="chapter3.task-scope.v1 with mode=reconcile-existing-only",
            actual=scope_doc.get("schema_version") if type(scope_doc) is dict else type(scope_doc).__name__,
            resume_ref=scope_path,
        )
    if scope_doc.get("master_path") not in (None, TRIPLET["master"]):
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.SCHEMA,
            expected=TRIPLET["master"],
            actual=scope_doc.get("master_path"),
            resume_ref=scope_path,
        )
    try:
        return chapter3_task_scope.allowed_ids(scope_doc)
    except (KeyError, TypeError, ValueError) as error:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            expected="valid chapter3-task-scope.json allowed_numeric_task_ids",
            actual=str(error),
            resume_ref=scope_path,
        )
    return set()


def _resolve_frozen_a_candidate(
    *,
    root: Path,
    observations: preflight.Observations,
    policy: dict[str, Any],
    origins: dict[str, Any],
    task_id: int,
    operation: str | None,
    live_task_def_digest: str,
    task_b_traces: list[str],
    task_na_labels: list[str],
    unapplied_ops: list[tuple[dict[str, Any], set[str], set[str]]],
) -> dict[str, Any]:
    # 1. Zero overlapping unapplied operations on task:<task_id>.
    non_overlapping_ops = _check_unapplied_overlap(
        unapplied_ops,
        task_business_scopes=set(op_scope.resource_scopes(task_ids=[task_id])),
        owning_scope_ids=set(),
    )

    # 2. Zero residual B references or free-text exemption labels on Task rows.
    if task_b_traces or task_na_labels:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="zero residual B references or exemption labels for frozen-A candidate",
            actual={
                "residual_b_traces": task_b_traces,
                "non_authoritative_labels": task_na_labels,
                "route_required": "B",
            },
            resume_ref=ORIGINS_PATH,
        )

    # 3. Verify policy.switch_boundary allowed_a_operations and a_write_allowed.
    switch = policy["switch_boundary"]
    allowed_a_ops = list(switch["allowed_a_operations"])
    a_write_allowed = switch["a_write_allowed"]
    if not allowed_a_ops:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected={"allowed_a_operations": "nonempty", "route_required": "B"},
            actual={"allowed_a_operations": allowed_a_ops, "a_write_allowed": a_write_allowed},
            resume_ref=POLICY_PATH,
        )
    if operation is not None:
        if operation not in allowed_a_ops:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"allowed_a_operations": allowed_a_ops, "route_required": "B"},
                actual={"operation": operation, "route_required": "B"},
                resume_ref=POLICY_PATH,
            )
        if not a_write_allowed and operation not in A_READ_ONLY_OPERATIONS:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"a_write_allowed": True, "route_required": "B"},
                actual={"operation": operation, "a_write_allowed": False, "route_required": "B"},
                resume_ref=POLICY_PATH,
            )

    # 4. Require readable, live-verified policy.frozen_a_refs (and origins.frozen_legacy_refs).
    frozen_a_refs = policy["frozen_a_refs"]
    if not frozen_a_refs:
        _fail(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="nonempty readable policy.frozen_a_refs proving frozen A baseline",
            actual={"frozen_a_refs": [], "route_required": "B"},
            resume_ref=POLICY_PATH,
        )

    for legacy_ref in origins["frozen_legacy_refs"]:
        preflight.owned(legacy_ref, observations)

    snapshots: list[tuple[str, dict[str, Any]]] = []
    task_scopes: list[tuple[str, set[int]]] = []
    matched_refs: list[dict[str, Any]] = []

    for ref in frozen_a_refs:
        owner = ref["owner"]
        if owner not in ("frozen_a_inventory", "authority"):
            _fail(
                codec.ReasonCode.INVALID_REFERENCE,
                stage=codec.Stage.REFERENCE,
                entity_id=str(task_id),
                expected="policy.frozen_a_refs owner in (frozen_a_inventory, authority)",
                actual=owner,
                resume_ref=POLICY_PATH,
            )
        preflight.owned(ref, observations)
        ref_path = ref["ref"].partition("#")[0]
        if owner == "authority" and not ref_path.endswith(".json"):
            matched_refs.append({"owner": owner, "ref": ref["ref"], "kind": "authority"})
            continue
        doc = codec.strict_json_loads(observations.read(ref_path))
        if type(doc) is not dict:
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                stage=codec.Stage.SCHEMA,
                entity_id=str(task_id),
                expected="frozen-A JSON object",
                actual=type(doc).__name__,
                resume_ref=ref_path,
            )
        if doc.get("schema_version") == protection.SCHEMA:
            snapshot, _report = _load_frozen_a_snapshot(root, observations, ref_path)
            snapshots.append((ref_path, snapshot))
            matched_refs.append({"owner": owner, "ref": ref["ref"], "kind": "protection_snapshot"})
        elif doc.get("document_version") == preflight.PROTECTION_VERSION:
            definition = doc.get("definition")
            if type(definition) is not dict:
                _fail(
                    codec.ReasonCode.INVALID_TYPE,
                    stage=codec.Stage.SCHEMA,
                    entity_id=str(task_id),
                    expected="definition object in protection-input document",
                    actual=type(definition).__name__,
                    resume_ref=ref_path,
                )
            if (
                definition.get("projection_codec") != codec.PROJECTION_CODEC
                or definition.get("content_codec") != codec.CODEC_VERSION
                or definition.get("mutable_allowlist") != ["Task.status", "Task.subtasks[].status"]
            ):
                _fail(
                    codec.ReasonCode.UNKNOWN_CODEC_VERSION,
                    stage=codec.Stage.SCHEMA,
                    entity_id=str(task_id),
                    expected="Story 1.5 exact definition projection",
                    actual=definition,
                    resume_ref=ref_path,
                )
            if not protection._same_json(doc.get("authorization"), protection.AUTHORIZATION):
                _fail(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected=protection.AUTHORIZATION,
                    actual=doc.get("authorization"),
                    resume_ref=ref_path,
                )
            for opt_key in (
                "inventory_ref",
                "task_definitions_ref",
                "triplet_definition_ref",
                "raw_archive_index_ref",
                "frozen_a_candidates_ref",
                "historical_inventory_ref",
            ):
                if opt_key in doc:
                    preflight.owned(doc[opt_key], observations)
            snap_ref = doc.get("snapshot_ref")
            if type(snap_ref) is not dict:
                _fail(
                    codec.ReasonCode.MISSING_REQUIRED_FIELD,
                    stage=codec.Stage.SCHEMA,
                    entity_id=str(task_id),
                    expected="snapshot_ref in protection-input document",
                    actual=None,
                    resume_ref=ref_path,
                )
            preflight.owned(snap_ref, observations)
            snap_path = snap_ref["ref"].partition("#")[0]
            snapshot, _report = _load_frozen_a_snapshot(root, observations, snap_path)
            snapshots.append((snap_path, snapshot))
            matched_refs.append({"owner": owner, "ref": ref["ref"], "kind": "protection_input"})
        elif doc.get("schema_version") == "chapter3.task-scope.v1":
            ids = _parse_task_scope(observations, ref_path)
            task_scopes.append((ref_path, ids))
            matched_refs.append({"owner": owner, "ref": ref["ref"], "kind": "chapter3_task_scope"})
        else:
            _fail(
                codec.ReasonCode.UNKNOWN_SCHEMA,
                stage=codec.Stage.SCHEMA,
                entity_id=str(task_id),
                expected="Story 1.5 protection snapshot/input or chapter3.task-scope.v1",
                actual=doc.get("schema_version") or doc.get("document_version"),
                resume_ref=ref_path,
            )

    # Also enforce docs/workflows/chapter3-task-scope.json if present on disk.
    if observations.read(CHAPTER3_TASK_SCOPE, optional=True) is not None:
        if not any(p == CHAPTER3_TASK_SCOPE for p, _ in task_scopes):
            task_scopes.append((CHAPTER3_TASK_SCOPE, _parse_task_scope(observations, CHAPTER3_TASK_SCOPE)))

    if not snapshots:
        _fail(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            stage=codec.Stage.BUNDLE,
            entity_id=str(task_id),
            expected="at least one readable Story 1.5 protection snapshot in policy.frozen_a_refs",
            actual={"matched_refs": matched_refs, "route_required": "B"},
            resume_ref=POLICY_PATH,
        )

    # 5. Check frozen Task ID against every chapter3-task-scope.json boundary.
    for scope_path, allowed_task_ids in task_scopes:
        if task_id not in allowed_task_ids:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"task_id_in_frozen_scope": True, "route_required": "B"},
                actual={"task_id": task_id, "scope_path": scope_path, "route_required": "B"},
                resume_ref=scope_path,
            )

    # 6. Check frozen Task ID, capture completeness, definition projection, and live source scope in every snapshot.
    verified_digests: set[str] = set()
    for snap_path, snapshot in snapshots:
        if snapshot.get("capture_complete") is not True:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"capture_complete": True, "route_required": "B"},
                actual={"capture_complete": snapshot.get("capture_complete"), "route_required": "B"},
                resume_ref=snap_path,
            )
        snap_tasks = {row["task_id"]: row for row in snapshot["tasks"]}
        snap_candidates = {row["task_id"]: row for row in snapshot["frozen_a"]["candidates"]}
        snap_raw_index = {row["path"]: row for row in snapshot["raw_files"]}

        if task_id not in snap_tasks or task_id not in snap_candidates:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"task_id_in_frozen_snapshot": True, "route_required": "B"},
                actual={"task_id": task_id, "snapshot": snap_path, "route_required": "B"},
                resume_ref=snap_path,
            )

        frozen_task_entry = snap_tasks[task_id]
        frozen_candidate = snap_candidates[task_id]
        blocking_reasons = frozen_candidate.get("blocking_reasons")
        if type(blocking_reasons) is not list or "historical_evidence_not_proven" in blocking_reasons:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"historical_evidence_proven": True, "route_required": "B"},
                actual={"blocking_reasons": blocking_reasons, "route_required": "B"},
                resume_ref=snap_path,
            )
        frozen_def_digest = frozen_task_entry["definition_digest"]
        if frozen_candidate.get("definition_digest") != frozen_def_digest:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected=frozen_def_digest,
                actual=frozen_candidate.get("definition_digest"),
                resume_ref=snap_path,
            )
        verified_digests.add(frozen_def_digest)
        if len(verified_digests) > 1:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="consistent frozen definition digest across policy.frozen_a_refs snapshots",
                actual=sorted(verified_digests),
                resume_ref=POLICY_PATH,
            )

        if live_task_def_digest != frozen_def_digest:
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"frozen_definition_digest": frozen_def_digest, "route_required": "B"},
                actual={"live_definition_digest": live_task_def_digest, "route_required": "B"},
                resume_ref=TRIPLET["master"],
            )

        # Verify frozen source scope matches live bytes on disk.
        source_scope = frozen_candidate.get("source_scope")
        if type(source_scope) is not dict:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="complete frozen source_scope in snapshot candidate",
                actual=source_scope,
                resume_ref=snap_path,
            )
        source_set = source_scope.get("source_set")
        if type(source_set) is not dict or type(source_set.get("path")) is not str or not source_set["path"].strip():
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"source_set": "object with canonical path", "route_required": "B"},
                actual={"source_set": source_set, "route_required": "B"},
                resume_ref=snap_path,
            )
        ss_path = source_set["path"]
        expected_ss_digest = source_set.get("raw_digest")
        if expected_ss_digest is not None:
            protection._checked_digest(expected_ss_digest, ss_path)
        live_ss = observations.read(ss_path, optional=True)
        actual_ss_digest = codec.raw_digest(live_ss) if live_ss is not None else None
        if actual_ss_digest != expected_ss_digest:
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected={"path": ss_path, "raw_digest": expected_ss_digest, "route_required": "B"},
                actual={"path": ss_path, "raw_digest": actual_ss_digest, "route_required": "B"},
                resume_ref=ss_path,
            )

        task_sources = source_scope.get("task_source_references")
        if type(task_sources) is not list or not task_sources:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected="nonempty proven task_source_references in frozen source_scope",
                actual={"task_source_references": task_sources, "route_required": "B"},
                resume_ref=snap_path,
            )
        for sref in task_sources:
            if type(sref) is not dict or sref.get("state") != "present" or type(sref.get("path")) is not str:
                _fail(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="present frozen task source reference",
                    actual=sref,
                    resume_ref=snap_path,
                )
            src_path = sref["path"]
            archived_row = snap_raw_index.get(src_path)
            if archived_row is None or not archived_row.get("exists") or not archived_row.get("raw_digest"):
                _fail(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected="archived raw digest for frozen task source",
                    actual=src_path,
                    resume_ref=snap_path,
                )
            live_src = observations.read(src_path)
            actual_src_digest = codec.raw_digest(live_src)
            if actual_src_digest != archived_row["raw_digest"]:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(task_id),
                    expected={"path": src_path, "raw_digest": archived_row["raw_digest"], "route_required": "B"},
                    actual={"path": src_path, "raw_digest": actual_src_digest, "route_required": "B"},
                    resume_ref=src_path,
                )

    return {
        "frozen_a_boundary": {
            "verified": True,
            "allowed_a_operations": allowed_a_ops,
            "a_write_allowed": a_write_allowed,
            "default_route": switch["default_route"],
            "matched_frozen_refs": matched_refs,
            "source_scope_verified": True,
            "projection_verified": True,
        },
        "non_overlapping_unapplied_operations": non_overlapping_ops,
    }


def resolve_task_origin(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    before_reread: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Pure read-only zero-write Task origin and applicable plan-set resolver."""
    validated_tid: int | None = None
    validated_op: str | None = None
    result = _base_result(None, None)
    observations: preflight.Observations | None = None
    graph_bytes_holder: dict[str, Any] = {"bytes": None}

    try:
        root_path = _validate_root(Path(root))
        validated_tid = codec.validate_task_id(task_id)
        validated_op = _validate_operation(operation)
        result = _base_result(validated_tid, validated_op)
        observations = preflight.Observations(root_path)

        # 1. Read and join the Taskmaster triplet strictly.
        triplet_raw = {name: observations.read(rel) for name, rel in TRIPLET.items()}
        docs = {name: codec.strict_json_loads(raw) for name, raw in triplet_raw.items()}
        task_join = records.TaskJoinContext(**docs)
        master_tasks, _views = task_join.indexes()

        if validated_tid not in master_tasks:
            _fail(
                codec.ReasonCode.UNKNOWN_ENTITY,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected="existing master Task ID",
                actual=validated_tid,
                resume_ref=TRIPLET["master"],
            )
        master_row = master_tasks[validated_tid]
        back_rows = [row for row in docs["back"] if row["taskmaster_id"] == validated_tid]
        gameplay_rows = [row for row in docs["gameplay"] if row["taskmaster_id"] == validated_tid]
        if not back_rows and not gameplay_rows:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected="at least one business view row mapped to master Task",
                actual=validated_tid,
                resume_ref=TRIPLET["master"],
            )

        protection._task_state(master_row, master=True)
        for row in (*back_rows, *gameplay_rows):
            protection._task_state(row, master=False)
        live_task_def = {
            "master": protection.task_definition_projection(master_row),
            "back": [protection.task_definition_projection(row) for row in back_rows],
            "gameplay": [protection.task_definition_projection(row) for row in gameplay_rows],
        }
        live_task_def_digest = codec.canonical_digest(live_task_def)
        result["task_definition_digest"] = live_task_def_digest
        result["task_view_refs"] = sorted(
            [
                *({"view": "back", "business_id": r["id"]} for r in back_rows),
                *({"view": "gameplay", "business_id": r["id"]} for r in gameplay_rows),
            ],
            key=lambda item: (item["view"], item["business_id"]),
        )

        # 2. Check legacy pending and B-route operation store (pure read-only).
        graph, unapplied_ops = _inspect_pending(
            root_path,
            observations,
            validated_tid,
            pending_summary=result["pending_summary"],
            graph_bytes_holder=graph_bytes_holder,
        )

        # 3. Observe governance directory and triplet B-route traces.
        discovered = observations.scan("docs/planning/b-route")
        managed_traces = [p for p in discovered if records._managed_candidate(p)]
        for rel in discovered:
            observations.read(rel)
        gov_raw = {rel: observations.read(rel, optional=True) for rel in GOVERNANCE}
        global_b_traces, per_task_traces = _scan_triplet_traces(docs)
        task_b_traces, task_na_labels = per_task_traces.get(validated_tid, ([], []))

        # 4. Check explicit_not_enabled_a (zero B traces + valid Accepted ADR-0040).
        has_any_b_trace = bool(discovered or graph["operations"] or global_b_traces)
        if not has_any_b_trace and all(raw is None for raw in gov_raw.values()):
            adr_ok, adr_diag = _check_adr_0040_not_enabled(observations, entity_id=str(validated_tid))
            if not adr_ok:
                result["diagnostics"].append(adr_diag)
            else:
                result["route"] = "explicit_not_enabled_a"
                result["governance_state"] = "explicitly_not_enabled"
                result["authority_ref"] = ADR_0040
                result["frozen_a_boundary"] = {
                    "verified": False,
                    "allowed_a_operations": [],
                    "a_write_allowed": True,
                    "default_route": "A",
                    "matched_frozen_refs": [],
                    "source_scope_verified": False,
                    "projection_verified": False,
                }
                result["ok"] = True
        elif any(raw is None for raw in gov_raw.values()):
            missing = [rel for rel, raw in gov_raw.items() if raw is None]
            for rel in missing:
                result["diagnostics"].append(
                    _diag(
                        codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(validated_tid),
                        expected={"path": rel, "value": "committed governance file required when B traces exist"},
                        actual=None,
                        resume_ref=rel,
                    )
                )
            for rel in managed_traces:
                checked = records.validate_record(observations.read(rel), path=rel)
                if not checked.ok:
                    diag = checked.diagnostic.to_dict()
                    if diag.get("entity_id") is None:
                        diag["entity_id"] = str(validated_tid)
                    result["diagnostics"].append(diag)
        else:
            # 5. Full committed governance validation.
            policy_raw = gov_raw[POLICY_PATH]
            catalog_raw = gov_raw[CATALOG_PATH]
            origins_raw = gov_raw[ORIGINS_PATH]
            for rel in managed_traces:
                checked = records.validate_record(observations.read(rel), path=rel)
                if not checked.ok:
                    raise codec.CodecError(checked.diagnostic)

            policy = codec.strict_json_loads(policy_raw)
            catalog = codec.strict_json_loads(catalog_raw)
            origins = codec.strict_json_loads(origins_raw)

            for auth_ref in policy["switch_boundary"]["authority_refs"]:
                _observe_non_log_owned_ref(auth_ref, observations)

            if catalog["scope_heads"]:
                pub_info = records.published_bundle(
                    root_path,
                    catalog_raw=catalog_raw,
                    scope_ids=None,
                    task_join=task_join,
                    _protection=True,
                )
                for formal_path in pub_info["formal_paths"]:
                    observations.read(formal_path)
            else:
                if catalog["definition_owners"] or catalog["task_index"] or origins["tasks"]:
                    _fail(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(validated_tid),
                        expected="empty definition_owners/task_index/origins.tasks when scope_heads is empty",
                        actual={
                            "definition_owners": len(catalog["definition_owners"]),
                            "task_index": len(catalog["task_index"]),
                            "origins_tasks": len(origins["tasks"]),
                        },
                        resume_ref=CATALOG_PATH,
                    )
                checked_bundle = records.validate_bundle(
                    {
                        CATALOG_PATH: catalog_raw,
                        POLICY_PATH: policy_raw,
                        ORIGINS_PATH: origins_raw,
                    },
                    root=root_path,
                    task_join=task_join,
                )
                if not checked_bundle.ok:
                    raise codec.CodecError(checked_bundle.diagnostic)

            result["governance_state"] = "committed_b"
            result["policy_ref"] = deepcopy(catalog["policy_ref"])
            result["catalog_ref"] = {
                "path": CATALOG_PATH,
                "revision": catalog["revision"],
                "raw_digest": codec.raw_digest(catalog_raw),
            }
            result["origins_ref"] = deepcopy(catalog["origins_ref"])

            # Reject duplicate keys in catalog.definition_owners, origins.tasks, and catalog.task_index.
            seen_owner_keys: set[tuple[str, str]] = set()
            for row in catalog["definition_owners"]:
                okey = (row["kind"], row["definition_id"])
                if okey in seen_owner_keys:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(validated_tid),
                        expected="unique (kind, definition_id) in catalog.definition_owners",
                        actual=list(okey),
                        resume_ref=CATALOG_PATH,
                    )
                seen_owner_keys.add(okey)

            origins_by_tid: dict[int, dict[str, Any]] = {}
            for row in origins["tasks"]:
                rtid = row["task_id"]
                if rtid in origins_by_tid:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(rtid),
                        expected="unique task_id in origins.tasks",
                        actual=rtid,
                        resume_ref=ORIGINS_PATH,
                    )
                origins_by_tid[rtid] = row

            catalog_by_tid: dict[int, dict[str, Any]] = {}
            for row in catalog["task_index"]:
                rtid = row["task_id"]
                if rtid in catalog_by_tid:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(rtid),
                        expected="unique task_id in catalog.task_index",
                        actual=rtid,
                        resume_ref=CATALOG_PATH,
                    )
                catalog_by_tid[rtid] = row

            # 6. Collect active bindings from catalog.scope_heads and inspect reverse mappings for task_id.
            seen_bindings: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
            for head in catalog["scope_heads"]:
                for bref in head["binding_refs"]:
                    bkey = codec.canonical_digest(bref)
                    if bkey not in seen_bindings:
                        bdoc = _load_formal_json(observations, bref)
                        seen_bindings[bkey] = (bref, bdoc)

            active_bindings_for_task: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
            for bref, bdoc in seen_bindings.values():
                for mapping in bdoc["task_mappings"]:
                    if mapping["task_id"] == validated_tid:
                        active_bindings_for_task.append((bref, bdoc, mapping))

            origins_row = origins_by_tid.get(validated_tid)
            catalog_row = catalog_by_tid.get(validated_tid)

            any_b_entry = (origins_row is not None) or (catalog_row is not None) or bool(active_bindings_for_task)
            all_b_entries = (origins_row is not None) and (catalog_row is not None) and bool(active_bindings_for_task)

            if any_b_entry and not all_b_entries:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(validated_tid),
                    expected="three-way reverse consistency across origins.tasks, catalog.task_index, and active bindings",
                    actual={
                        "in_origins": origins_row is not None,
                        "in_catalog_task_index": catalog_row is not None,
                        "active_binding_count": len(active_bindings_for_task),
                    },
                    resume_ref=ORIGINS_PATH,
                )

            if all_b_entries:
                b_resolved = _resolve_b_applicable_set(
                    observations=observations,
                    catalog=catalog,
                    origins=origins,
                    task_id=validated_tid,
                    origins_row=origins_row,
                    catalog_row=catalog_row,
                    active_bindings=active_bindings_for_task,
                    task_na_labels=task_na_labels,
                    unapplied_ops=unapplied_ops,
                )
                result["route"] = "B"
                result["route_required"] = "B"
                result["plan_refs"] = b_resolved["plan_refs"]
                result["binding_refs"] = b_resolved["binding_refs"]
                result["source_refs"] = b_resolved["source_refs"]
                result["resolved_definitions"] = b_resolved["resolved_definitions"]
                result["dispositions"] = b_resolved["dispositions"]
                result["applicable_flow_closure"] = b_resolved["applicable_flow_closure"]
                result["applicable_requirements"] = b_resolved["applicable_requirements"]
                result["applicable_obligations"] = b_resolved["applicable_obligations"]
                result["applicable_implementation_objects"] = b_resolved["applicable_implementation_objects"]
                result["applicable_scope_ids"] = b_resolved["applicable_scope_ids"]
                result["applicable_set_digest"] = b_resolved["applicable_set_digest"]
                result["non_flow_summary"] = b_resolved["non_flow_summary"]
                result["pending_summary"]["non_overlapping_unapplied_operations"] = b_resolved[
                    "non_overlapping_unapplied_operations"
                ]
                result["ok"] = True
            else:
                try:
                    a_resolved = _resolve_frozen_a_candidate(
                        root=root_path,
                        observations=observations,
                        policy=policy,
                        origins=origins,
                        task_id=validated_tid,
                        operation=validated_op,
                        live_task_def_digest=live_task_def_digest,
                        task_b_traces=task_b_traces,
                        task_na_labels=task_na_labels,
                        unapplied_ops=unapplied_ops,
                    )
                except codec.CodecError:
                    result["route_required"] = "B"
                    raise
                result["route"] = "A"
                result["route_required"] = "A"
                result["frozen_a_boundary"] = a_resolved["frozen_a_boundary"]
                result["pending_summary"]["non_overlapping_unapplied_operations"] = a_resolved[
                    "non_overlapping_unapplied_operations"
                ]
                result["ok"] = True
    except codec.CodecError as error:
        diag_dict = error.diagnostic.to_dict()
        if diag_dict.get("entity_id") is None and validated_tid is not None:
            diag_dict["entity_id"] = str(validated_tid)
        actual_obj = diag_dict.get("actual")
        expected_obj = diag_dict.get("expected")
        if (type(actual_obj) is dict and actual_obj.get("route_required") == "B") or (
            type(expected_obj) is dict and expected_obj.get("route_required") == "B"
        ):
            result["route_required"] = "B"
        result["route"] = "blocked"
        result["ok"] = False
        result["applicable_set_digest"] = None
        result["diagnostics"].append(diag_dict)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        result["route"] = "blocked"
        result["ok"] = False
        result["applicable_set_digest"] = None
        result["diagnostics"].append(
            _diag(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid) if validated_tid is not None else None,
                expected="complete readable Task origin resolution inputs",
                actual=f"{type(error).__name__}: {error}",
            )
        )

    # Final double-read drift check without writing any lock or directory.
    if before_reread is not None:
        before_reread()
    if observations is not None:
        drift = observations.finish()
        initial_graph_bytes = graph_bytes_holder["bytes"]
        if initial_graph_bytes is not None:
            try:
                final_graph = journal.operation_state_graph(observations.root)
                if final_graph["local_bytes"] != initial_graph_bytes:
                    drift.append(
                        _diag(
                            codec.ReasonCode.FILE_CHANGED,
                            stage=codec.Stage.BUNDLE,
                            entity_id=str(validated_tid) if validated_tid is not None else None,
                            expected="unchanged operation_state_graph during read-only resolution",
                            actual="operation store changed during resolution",
                            resume_ref=OP_STORE,
                        )
                    )
            except codec.CodecError as error:
                drift.append(error.diagnostic.to_dict())
            except (OSError, ValueError, RuntimeError) as error:
                drift.append(
                    _diag(
                        codec.ReasonCode.FILE_CHANGED,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(validated_tid) if validated_tid is not None else None,
                        expected="stable operation_state_graph during resolution",
                        actual=type(error).__name__,
                        resume_ref=OP_STORE,
                    )
                )
        if drift:
            old_diags = list(result["diagnostics"])
            result = _base_result(validated_tid, validated_op)
            result["diagnostics"] = [*old_diags, *drift]
            result["stable"] = False
            result["ok"] = False
            result["route"] = "blocked"
            result["applicable_set_digest"] = None
        else:
            has_file_changed = any(
                row.get("reason_code") == codec.ReasonCode.FILE_CHANGED.value
                for row in result["diagnostics"]
            )
            if has_file_changed:
                old_diags = list(result["diagnostics"])
                result = _base_result(validated_tid, validated_op)
                result["diagnostics"] = old_diags
                result["stable"] = False
                result["ok"] = False
                result["route"] = "blocked"
                result["applicable_set_digest"] = None
            else:
                result["stable"] = True

    # Re-assert mandatory non-authorization invariants.
    for key, val in AUTHORIZATION_FLAGS.items():
        result[key] = val
    result["authorization"] = dict(AUTHORIZATION_FLAGS)
    return result


def write_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> str:
    """Explicit opt-in report writer under logs/ci/; never overwrites existing files."""
    root_path = _validate_root(Path(root))
    try:
        inventory.canonical_path(report_rel, allow_logs=True)
    except (TypeError, ValueError):
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="canonical repository-relative POSIX path under logs/ci/",
            actual=report_rel,
            resume_ref=str(report_rel),
        )
    if not report_rel.startswith("logs/ci/") or not report_rel.endswith(".json"):
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="new logs/ci/<...>.json report path",
            actual=report_rel,
            resume_ref=report_rel,
        )
    try:
        target = inventory.safe_input(root_path, report_rel, allow_logs=True)
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="safe contained report path under logs/ci/",
            actual=type(error).__name__,
            resume_ref=report_rel,
        )
    if target.exists():
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.PATH,
            expected="nonexistent report path (never overwrite existing report)",
            actual=report_rel,
            resume_ref=report_rel,
        )
    try:
        current = root_path
        for part in report_rel.split("/")[:-1]:
            current = current / part
            current.mkdir(exist_ok=True)
            inventory.no_reparse(current)
        target = inventory.safe_input(root_path, report_rel, allow_logs=True)
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="safe contained report directory under logs/ci/",
            actual=type(error).__name__,
            resume_ref=report_rel,
        )
    if target.exists():
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.PATH,
            expected="nonexistent report path",
            actual=report_rel,
            resume_ref=report_rel,
        )
    output_payload = deepcopy(payload)
    output_payload["report_path"] = report_rel
    serialized = (json.dumps(output_payload, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    created_temp = False
    try:
        with temporary.open("xb") as stream:
            created_temp = True
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise
        except OSError:
            if target.exists():
                raise FileExistsError(report_rel)
            with target.open("xb") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError as error:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.PATH,
            expected="exclusive atomic report write",
            actual=type(error).__name__,
            resume_ref=report_rel,
        )
    finally:
        if created_temp:
            temporary.unlink(missing_ok=True)
    return report_rel
