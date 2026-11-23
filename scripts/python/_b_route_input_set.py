"""Unified B-route InputSet builder, freshness evaluator, and business-scope guard.

This module is the single owner of:
- Constructing the complete, normalized Task InputSet across Story 3.3 applicable
  plans, Story 3.4 bindings (including optional single-slot candidate binding
  replacement), Task definition projections, ADRs/Overlays/Contracts, MVG manifests
  or legal non-Flow other_verification evidence, transitive dependency closures,
  and policy/codec/environment rules.
- Computing the deterministic ``input_set_digest`` without hashing volatile
  whole-file containers (catalog.revision, origins.revision, Task status, unrelated
  Tasks, or Git HEAD).
- Comparing against a baseline InputSet to emit exact ``invalidated_items`` and
  the earliest owning ``return_stage`` (3A | 3B | 3C | 4 | 5).
- Providing ``guarded_input_set`` which holds only business scope leases
  (``review_only=True``, never acquiring the global writer lock) and revalidates
  both upon entering the lease and on explicit ``revalidate()``.

Default read-only mode creates zero directories, files, or locks. Never grants
``execution_authorized``, ``readiness``, ``runtime_verified``, or
``default_b_enabled``.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterator

import _b_route_adoption_review as adoption_review
import _b_route_chapter4_binding as ch4_binding
import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_operation_scope as op_scope
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_record_owners as record_owners
import _b_route_records as records
import _b_route_task_resolver as resolver
import _chapter5_contract_bindings as contract_bindings
import _mvg_manifest as mvg_manifest
import _planning_apply_journal as journal
import validate_overlay_execution as overlay_exec


SCHEMA = "newrouge.b-route-input-set.v1"
STAGE_ORDER = ("3A", "3B", "3C", "4", "5")
STAGE_RANK = {stage: idx for idx, stage in enumerate(STAGE_ORDER)}
LOCK_MODES = frozenset({"none", "scope"})
DEFAULT_MAX_ATTEMPTS = 3
MAX_ATTEMPTS_LIMIT = 5

AUTHORIZATION_FLAGS = {
    "execution_authorized": False,
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}

_ADR_ID_RE = re.compile(r"^ADR-\d{4}$", re.IGNORECASE)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_POS_INT_STR_RE = re.compile(r"^[1-9][0-9]*$")

_ITEM_REQUIRED_KEYS = frozenset(
    {
        "category",
        "locator",
        "raw_digest",
        "normalization_mode",
        "codec_version",
        "normalized_digest",
        "return_stage",
        "sealed_log",
        "committed",
        "details",
    }
)


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


def _earliest_stage(stages: list[str | None]) -> str | None:
    valid = [s for s in stages if s in STAGE_RANK]
    if not valid:
        return None
    return min(valid, key=lambda s: STAGE_RANK[s])


def _stage_for_path(path_value: str | None) -> str | None:
    if type(path_value) is not str or not path_value:
        return None
    norm = path_value.replace("\\", "/").rstrip("/").casefold()
    if (
        norm == "docs/gdd"
        or norm.startswith("docs/gdd/")
        or norm == "docs/prd"
        or norm.startswith("docs/prd/")
        or norm == "docs/workflows/chapter3-source-set.json"
        or "source-manifest" in norm
        or "source-blocks" in norm
    ):
        return "3A"
    if norm == "docs/planning/b-route/plans" or norm.startswith("docs/planning/b-route/plans/"):
        return "3B"
    if (
        norm == ".taskmaster/tasks"
        or norm.startswith(".taskmaster/tasks/")
        or norm == "docs/planning/b-route/task-origins.v1.json"
    ):
        return "3C"
    if (
        norm == "game.core/contracts"
        or norm.startswith("game.core/contracts/")
        or norm == "docs/adr"
        or norm.startswith("docs/adr/")
        or norm == "docs/architecture/overlays"
        or norm.startswith("docs/architecture/overlays/")
        or norm == "docs/planning/b-route/bindings"
        or norm.startswith("docs/planning/b-route/bindings/")
    ):
        return "4"
    if (
        norm == "docs/testing/mvg"
        or norm.startswith("docs/testing/mvg/")
        or norm == "docs/planning/b-route/policy.v1.json"
        or norm == "docs/testing"
        or norm.startswith("docs/testing/")
    ):
        return "5"
    return None


def _stage_for_diag(diag: dict[str, Any] | None) -> str | None:
    if type(diag) is not dict:
        return None
    direct = _stage_for_path(diag.get("resume_ref"))
    if direct is not None:
        return direct
    for field in ("expected", "actual"):
        val = diag.get(field)
        if type(val) is str:
            st = _stage_for_path(val)
            if st is not None:
                return st
        elif type(val) is dict:
            for key in ("path", "ref"):
                st = _stage_for_path(val.get(key))
                if st is not None:
                    return st
            nested = val.get("value")
            if type(nested) is dict:
                for key in ("path", "ref"):
                    st = _stage_for_path(nested.get(key))
                    if st is not None:
                        return st
    return None


def _base_result(
    task_id: int | None,
    operation: str | None,
    *,
    lock_mode: str = "none",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "ok": False,
        "stable": False,
        "valid_input_set": False,
        "task_id": task_id,
        "operation": operation,
        "route": "blocked",
        "governance_state": "blocked",
        "lock_mode": lock_mode,
        "uses_global_writer_lock": False,
        "uses_candidate_binding": False,
        "candidate_binding": None,
        "input_set_digest": None,
        "applicable_set_digest": None,
        "scope_ids": [],
        "items": [],
        "dependency_eligibility": None,
        "freshness": {
            "compared": False,
            "fresh": None,
            "status": "not_compared",
            "baseline_digest": None,
            "current_digest": None,
            "return_stage": None,
            "invalidated_items": [],
        },
        "return_stage": None,
        "read_attempts": 0,
        "clean_clone_sealed_logs": [],
        "origin_summary": None,
        **AUTHORIZATION_FLAGS,
        "authorization": dict(AUTHORIZATION_FLAGS),
        "report_path": None,
        "diagnostics": [],
    }


def _validate_max_attempts(max_attempts: Any) -> int:
    if type(max_attempts) is not int or max_attempts < 1 or max_attempts > MAX_ATTEMPTS_LIMIT:
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            stage=codec.Stage.CONTENT,
            expected=f"integer max_attempts between 1 and {MAX_ATTEMPTS_LIMIT}",
            actual=max_attempts,
        )
    return max_attempts


def _validate_lock_mode(lock_mode: Any) -> str:
    if type(lock_mode) is not str or lock_mode not in LOCK_MODES:
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            stage=codec.Stage.CONTENT,
            expected="lock_mode in ('none', 'scope')",
            actual=lock_mode,
        )
    return lock_mode


def _json_raw_bytes(value: Any) -> bytes:
    codec.validate_json_value(value)
    import json

    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))).encode(
        "utf-8"
    )


def _make_item(
    *,
    category: str,
    locator: str,
    raw_digest: str,
    normalization_mode: str,
    codec_version: str,
    normalized_digest: str,
    return_stage: str,
    sealed_log: bool = False,
    committed: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if return_stage not in STAGE_RANK:
        _fail(
            codec.ReasonCode.INVALID_ENUM,
            stage=codec.Stage.CONTENT,
            expected=list(STAGE_ORDER),
            actual=return_stage,
        )
    return {
        "category": category,
        "locator": locator,
        "raw_digest": raw_digest,
        "normalization_mode": normalization_mode,
        "codec_version": codec_version,
        "normalized_digest": normalized_digest,
        "return_stage": return_stage,
        "sealed_log": bool(sealed_log),
        "committed": bool(committed),
        "details": deepcopy(details) if details is not None else {},
    }


def compute_input_set_digest(
    *,
    task_id: int,
    route: str,
    uses_candidate_binding: bool,
    items: list[dict[str, Any]],
) -> str:
    """Compute the canonical InputSet digest strictly from normalized item identities."""
    sorted_items = sorted(items, key=lambda r: (r["category"], r["locator"]))
    canonical_entries = [
        {
            "category": row["category"],
            "locator": row["locator"],
            "normalization_mode": row["normalization_mode"],
            "codec_version": row["codec_version"],
            "normalized_digest": row["normalized_digest"],
            "committed": row["committed"],
        }
        for row in sorted_items
    ]
    return codec.canonical_digest(
        {
            "schema_version": SCHEMA,
            "task_id": task_id,
            "route": route,
            "uses_candidate_binding": bool(uses_candidate_binding),
            "items": canonical_entries,
        }
    )


def _validate_baseline_doc(doc: Any, *, expected_task_id: int, resume_ref: str | None) -> dict[str, Any]:
    if type(doc) is not dict:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="InputSet JSON object",
            actual=type(doc).__name__,
            resume_ref=resume_ref,
        )
    if doc.get("schema_version") != SCHEMA:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected=SCHEMA,
            actual=doc.get("schema_version"),
            resume_ref=resume_ref,
        )
    if type(doc.get("task_id")) is not int:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="integer task_id",
            actual=type(doc.get("task_id")).__name__,
            resume_ref=resume_ref,
        )
    if doc.get("task_id") != expected_task_id:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=str(expected_task_id),
            expected=expected_task_id,
            actual=doc.get("task_id"),
            resume_ref=resume_ref,
        )
    route = doc.get("route")
    if type(route) is not str or route not in ("B", "A", "explicit_not_enabled_a"):
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="baseline route in ('B', 'A', 'explicit_not_enabled_a')",
            actual=route,
            resume_ref=resume_ref,
        )
    uses_cand = doc.get("uses_candidate_binding")
    if type(uses_cand) is not bool:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="boolean uses_candidate_binding",
            actual=type(uses_cand).__name__,
            resume_ref=resume_ref,
        )
    claimed_digest = doc.get("input_set_digest")
    if type(claimed_digest) is not str or _DIGEST_RE.fullmatch(claimed_digest) is None:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="sha256:<64 hex> baseline input_set_digest",
            actual=claimed_digest,
            resume_ref=resume_ref,
        )
    items = doc.get("items")
    if type(items) is not list or not items:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=str(expected_task_id),
            expected="nonempty baseline items list",
            actual=type(items).__name__,
            resume_ref=resume_ref,
        )
    seen_keys: set[tuple[str, str]] = set()
    for row in items:
        if type(row) is not dict or not _ITEM_REQUIRED_KEYS <= set(row):
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=str(expected_task_id),
                expected=sorted(_ITEM_REQUIRED_KEYS),
                actual=sorted(row.keys()) if type(row) is dict else type(row).__name__,
                resume_ref=resume_ref,
            )
        for skey in ("category", "locator", "normalization_mode", "codec_version"):
            if type(row[skey]) is not str or not row[skey]:
                _fail(
                    codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                    stage=codec.Stage.SCHEMA,
                    entity_id=str(expected_task_id),
                    expected=f"nonempty string {skey}",
                    actual=type(row[skey]).__name__ if type(row[skey]) is not str else row[skey],
                    resume_ref=resume_ref,
                )
        if type(row["return_stage"]) is not str or row["return_stage"] not in STAGE_RANK:
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=str(expected_task_id),
                expected=list(STAGE_ORDER),
                actual=row["return_stage"],
                resume_ref=resume_ref,
            )
        for dkey in ("raw_digest", "normalized_digest"):
            if type(row[dkey]) is not str or _DIGEST_RE.fullmatch(row[dkey]) is None:
                _fail(
                    codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                    stage=codec.Stage.SCHEMA,
                    entity_id=str(expected_task_id),
                    expected=f"valid sha256 {dkey}",
                    actual=row[dkey],
                    resume_ref=resume_ref,
                )
        if type(row["committed"]) is not bool or type(row["sealed_log"]) is not bool:
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=str(expected_task_id),
                expected="boolean committed and sealed_log flags",
                actual={"committed": row["committed"], "sealed_log": row["sealed_log"]},
                resume_ref=resume_ref,
            )
        if type(row["details"]) is not dict:
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=str(expected_task_id),
                expected="object details field",
                actual=type(row["details"]).__name__,
                resume_ref=resume_ref,
            )
        ikey = (row["category"], row["locator"])
        if ikey in seen_keys:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.SCHEMA,
                entity_id=str(expected_task_id),
                expected="unique (category, locator) in baseline items",
                actual=list(ikey),
                resume_ref=resume_ref,
            )
        seen_keys.add(ikey)
    recomputed = compute_input_set_digest(
        task_id=expected_task_id,
        route=route,
        uses_candidate_binding=uses_cand,
        items=items,
    )
    if recomputed != claimed_digest:
        _fail(
            codec.ReasonCode.DIGEST_MISMATCH,
            stage=codec.Stage.CONTENT,
            entity_id=str(expected_task_id),
            expected=recomputed,
            actual=claimed_digest,
            resume_ref=resume_ref,
        )
    return doc


def compare_input_sets(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare two validated InputSet payloads and compute invalidated_items + return_stage."""
    if type(current) is not dict:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            expected="InputSet JSON object for current",
            actual=type(current).__name__,
        )
    if type(baseline) is not dict:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            expected="InputSet JSON object for baseline",
            actual=type(baseline).__name__,
        )
    raw_tid = current.get("task_id")
    if type(raw_tid) is not int or raw_tid < 1:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            expected="positive integer task_id in current InputSet",
            actual=raw_tid,
        )
    task_id = codec.validate_task_id(raw_tid)
    _validate_baseline_doc(baseline, expected_task_id=task_id, resume_ref=None)
    _validate_baseline_doc(current, expected_task_id=task_id, resume_ref=None)

    base_map = {(row["category"], row["locator"]): row for row in baseline["items"]}
    curr_map = {(row["category"], row["locator"]): row for row in current["items"]}

    invalidated: list[dict[str, Any]] = []
    for key in sorted(set(base_map) | set(curr_map)):
        cat, loc = key
        b_row = base_map.get(key)
        c_row = curr_map.get(key)
        if b_row is None and c_row is not None:
            invalidated.append(
                {
                    "category": cat,
                    "locator": loc,
                    "change_kind": "added",
                    "return_stage": c_row["return_stage"],
                    "baseline_digest": None,
                    "current_digest": c_row["normalized_digest"],
                }
            )
        elif b_row is not None and c_row is None:
            invalidated.append(
                {
                    "category": cat,
                    "locator": loc,
                    "change_kind": "removed",
                    "return_stage": b_row["return_stage"],
                    "baseline_digest": b_row["normalized_digest"],
                    "current_digest": None,
                }
            )
        elif b_row is not None and c_row is not None:
            b_sig = (
                b_row["normalization_mode"],
                b_row["codec_version"],
                b_row["normalized_digest"],
                b_row["committed"],
            )
            c_sig = (
                c_row["normalization_mode"],
                c_row["codec_version"],
                c_row["normalized_digest"],
                c_row["committed"],
            )
            if b_sig != c_sig:
                b_stage = b_row["return_stage"]
                c_stage = c_row["return_stage"]
                if (
                    cat in ("binding", "task_origins", "dependency_producer")
                    and STAGE_RANK[c_stage] > STAGE_RANK[b_stage]
                ):
                    stage = c_stage
                else:
                    stage = _earliest_stage([b_stage, c_stage]) or "5"
                invalidated.append(
                    {
                        "category": cat,
                        "locator": loc,
                        "change_kind": "changed",
                        "return_stage": stage,
                        "baseline_digest": b_row["normalized_digest"],
                        "current_digest": c_row["normalized_digest"],
                    }
                )

    if baseline["route"] != current["route"]:
        invalidated.append(
            {
                "category": "route",
                "locator": f"route:task:{task_id}",
                "change_kind": "changed",
                "return_stage": "3C",
                "baseline_digest": None,
                "current_digest": None,
            }
        )

    if baseline["uses_candidate_binding"] != current["uses_candidate_binding"]:
        cand_stages = [
            row["return_stage"]
            for row in (*baseline["items"], *current["items"])
            if row["category"] == "binding" and not row["committed"]
        ]
        invalidated.append(
            {
                "category": "candidate_binding",
                "locator": f"candidate_binding:task:{task_id}",
                "change_kind": "changed",
                "return_stage": _earliest_stage(cand_stages) or "4",
                "baseline_digest": None,
                "current_digest": None,
            }
        )

    b_digest = baseline["input_set_digest"]
    c_digest = current["input_set_digest"]
    is_fresh = (b_digest == c_digest) and not invalidated
    ret_stage: str | None = None
    diagnostics: list[dict[str, Any]] = []
    if not is_fresh:
        ret_stage = _earliest_stage([row["return_stage"] for row in invalidated]) or "5"
        diagnostics.append(
            _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(task_id),
                expected=b_digest,
                actual={
                    "current_digest": c_digest,
                    "return_stage": ret_stage,
                    "invalidated_count": len(invalidated),
                },
                resume_ref=invalidated[0]["locator"] if invalidated else None,
            )
        )
    return {
        "compared": True,
        "fresh": is_fresh,
        "status": "fresh" if is_fresh else "stale",
        "baseline_digest": b_digest,
        "current_digest": c_digest,
        "return_stage": ret_stage,
        "invalidated_items": invalidated,
        "diagnostics": diagnostics,
    }


def _build_receipt_seal_index(
    observations: preflight.Observations,
    catalog: dict[str, Any],
    applicable_scope_ids: list[str],
) -> dict[str, set[str]]:
    """Map normalized paths to receipt-sealed after_digests transitively across committed receipts."""
    sealed: dict[str, set[str]] = {}
    scope_set = set(applicable_scope_ids)
    seen_receipts: set[tuple[str, str]] = set()
    queue: deque[tuple[str, str, str]] = deque()
    for head in catalog.get("scope_heads", []):
        if scope_set and head["scope_id"] not in scope_set:
            continue
        rref = head["receipt_ref"]
        rpath = preflight.path(rref["path"])
        rdigest = rref["digest"]
        rmode = rref.get("verification_mode", "raw")
        rkey = (rpath, rdigest)
        if rkey not in seen_receipts:
            seen_receipts.add(rkey)
            queue.append((rpath, rdigest, rmode))

    while queue:
        rpath, expected_dg, mode = queue.popleft()
        raw = observations.read(rpath)
        receipt = codec.strict_json_loads(raw)
        actual_dg = codec.raw_digest(raw) if mode == "raw" else codec.canonical_digest(receipt)
        if actual_dg != expected_dg:
            _fail(
                codec.ReasonCode.DIGEST_MISMATCH,
                stage=codec.Stage.REFERENCE,
                expected=expected_dg,
                actual=actual_dg,
                resume_ref=rpath,
            )
        if type(receipt) is not dict:
            continue
        for pin in receipt.get("authority", []):
            if type(pin) is not dict:
                continue
            after_dg = pin.get("after_digest")
            if type(after_dg) is str and _DIGEST_RE.fullmatch(after_dg):
                rel = preflight.path(pin["path"])
                sealed.setdefault(rel, set()).add(after_dg)
                if rel.startswith("docs/planning/b-route/commits/") and rel.endswith(".json"):
                    ancestor_key = (rel, after_dg)
                    if ancestor_key not in seen_receipts:
                        seen_receipts.add(ancestor_key)
                        queue.append((rel, after_dg, "raw"))
    return sealed


def _validate_owned_ref_syntax(ref: Any, *, entity_id: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Validate OwnedRef owner, locator syntax/fragment, and declared files unconditionally."""
    if type(ref) is not dict or set(ref) != {"owner", "ref", "files"}:
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected="complete OwnedRef fields (owner, ref, files)",
            actual=ref,
        )
    owner = ref["owner"]
    ref_str = ref["ref"]
    files = ref["files"]
    if type(owner) is not str or owner not in record_owners.OWNERS:
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected="registered external owner",
            actual=owner,
        )
    if type(ref_str) is not str or not ref_str.strip():
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected="nonempty locator string",
            actual=ref_str,
        )
    if type(files) is not list or not files:
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected="nonempty OwnedRef files",
            actual=ref,
        )
    declared_rows: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for row in files:
        if type(row) is not dict or set(row) != {"path", "raw_digest"}:
            _fail(
                codec.ReasonCode.INVALID_REFERENCE,
                stage=codec.Stage.REFERENCE,
                entity_id=entity_id,
                expected="complete raw-file fields (path, raw_digest)",
                actual=row,
            )
        rel = preflight.path(codec.validate_reference_path(row["path"]))
        expected_dg = row["raw_digest"]
        if type(expected_dg) is not str or _DIGEST_RE.fullmatch(expected_dg) is None:
            _fail(
                codec.ReasonCode.INVALID_DIGEST,
                stage=codec.Stage.REFERENCE,
                entity_id=entity_id,
                expected="sha256:<64 lowercase hex digits>",
                actual=expected_dg,
                resume_ref=rel,
            )
        if rel in seen_paths:
            _fail(
                codec.ReasonCode.INVALID_REFERENCE,
                stage=codec.Stage.REFERENCE,
                entity_id=entity_id,
                expected="unique resolved file paths",
                actual=rel,
                resume_ref=rel,
            )
        seen_paths.add(rel)
        declared_rows.append((rel, expected_dg))

    if owner == "contract":
        if "#" in ref_str:
            _fail(
                codec.ReasonCode.UNSUPPORTED_LOCATOR,
                stage=codec.Stage.REFERENCE,
                entity_id=entity_id,
                expected="native contract symbol or file",
                actual=ref_str,
            )
    else:
        source, separator, fragment = ref_str.partition("#")
        ref_path = preflight.path(codec.validate_reference_path(source))
        if owner == "verification_record":
            if not fragment:
                _fail(
                    codec.ReasonCode.UNSUPPORTED_LOCATOR,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="#<evidence_id> fragment",
                    actual=ref_str,
                    resume_ref=ref_path,
                )
        elif separator:
            if fragment.startswith("/"):
                for part in fragment[1:].split("/"):
                    if re.search(r"~(?![01])", part):
                        _fail(
                            codec.ReasonCode.INVALID_REFERENCE,
                            stage=codec.Stage.REFERENCE,
                            entity_id=entity_id,
                            expected="RFC 6901 escape in JSON Pointer fragment",
                            actual=ref_str,
                            resume_ref=ref_path,
                        )
            else:
                lines = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", fragment)
                if lines is None:
                    _fail(
                        codec.ReasonCode.UNSUPPORTED_LOCATOR,
                        stage=codec.Stage.REFERENCE,
                        entity_id=entity_id,
                        expected="JSON Pointer or line range",
                        actual=fragment,
                        resume_ref=ref_path,
                    )
                first = int(lines.group(1))
                last = int(lines.group(2) or lines.group(1))
                if first > last:
                    _fail(
                        codec.ReasonCode.UNRESOLVED_REFERENCE,
                        stage=codec.Stage.REFERENCE,
                        entity_id=entity_id,
                        expected="existing ordered line range",
                        actual=fragment,
                        resume_ref=ref_path,
                    )
        if seen_paths != {ref_path}:
            _fail(
                codec.ReasonCode.INVALID_REFERENCE,
                stage=codec.Stage.REFERENCE,
                entity_id=entity_id,
                expected={"files": [ref_path]},
                actual={"files": sorted(seen_paths)},
                resume_ref=ref_path,
            )
    return owner, ref_str, declared_rows


def _observe_owned_ref_items(
    ref: dict[str, Any],
    *,
    observations: preflight.Observations,
    sealed_digests: dict[str, set[str]],
    allow_sealed_logs: bool,
    category: str,
    return_stage: str,
    committed: bool,
    items: dict[tuple[str, str], dict[str, Any]],
    sealed_log_paths: set[str],
    entity_id: str,
) -> list[tuple[str, bytes | None, str]]:
    """Verify an OwnedRef (live non-log bytes + receipt-sealed clean-clone logs) and emit InputSet items."""
    owner, ref_str, declared_rows = _validate_owned_ref_syntax(ref, entity_id=entity_id)

    def _put_item(
        rel: str,
        dg: str,
        *,
        sealed_log: bool,
        details: dict[str, Any],
    ) -> None:
        key = (category, rel)
        prev = items.get(key)
        eff_committed = (bool(prev["committed"]) and bool(committed)) if prev is not None else bool(committed)
        items[key] = _make_item(
            category=category,
            locator=rel,
            raw_digest=dg,
            normalization_mode="raw_bytes",
            codec_version=codec.CODEC_VERSION,
            normalized_digest=dg,
            return_stage=return_stage,
            sealed_log=sealed_log,
            committed=eff_committed,
            details=details,
        )

    if owner == "contract":
        preflight.owned(ref, observations)
        observed_files: list[tuple[str, bytes | None, str]] = []
        for rel, expected_dg in declared_rows:
            raw = observations.read(rel)
            actual_dg = codec.raw_digest(raw)
            if actual_dg != expected_dg:
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected=expected_dg,
                    actual=actual_dg,
                    resume_ref=rel,
                )
            observed_files.append((rel, raw, actual_dg))
            _put_item(rel, actual_dg, sealed_log=False, details={"owner": owner, "ref": ref_str})
        return observed_files

    raw_by_rel: dict[str, bytes | None] = {}
    for rel, _expected_dg in declared_rows:
        can_seal = allow_sealed_logs and rel.startswith("logs/")
        raw_by_rel[rel] = observations.read(rel, optional=can_seal)

    all_present = all(raw is not None for raw in raw_by_rel.values())
    if all_present:
        # Full resolve_owned_ref verification (including JSON Pointer / line-range / native record)
        # whenever all declared files exist on disk, even for logs/ references.
        preflight.owned(ref, observations)

    observed_files = []
    for rel, expected_dg in declared_rows:
        raw = raw_by_rel[rel]
        if raw is not None:
            actual_dg = codec.raw_digest(raw)
            if actual_dg != expected_dg:
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected=expected_dg,
                    actual=actual_dg,
                    resume_ref=rel,
                )
            observed_files.append((rel, raw, actual_dg))
            _put_item(rel, actual_dg, sealed_log=False, details={"owner": owner, "ref": ref_str})
        else:
            if expected_dg not in sealed_digests.get(rel, set()):
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="receipt-sealed historical log digest for absent clean-clone log",
                    actual={"path": rel, "raw_digest": expected_dg},
                    resume_ref=rel,
                )
            sealed_log_paths.add(rel)
            observed_files.append((rel, None, expected_dg))
            _put_item(
                rel,
                expected_dg,
                sealed_log=True,
                details={"owner": owner, "ref": ref_str, "clean_clone_sealed": True},
            )
    return observed_files


def _validate_mvg_manifest_decoupled(
    *,
    root: Path,
    manifest_rel: str,
    manifest_raw: bytes,
    observations: preflight.Observations,
    master_tasks: dict[int, dict[str, Any]],
    entity_id: str,
) -> tuple[dict[str, Any], str]:
    """Validate MVG manifest structure, flows, tests, files, and Task existence decoupled from live Task status."""
    doc = codec.strict_json_loads(manifest_raw)
    if type(doc) is not dict:
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected="MVG manifest JSON object",
            actual=type(doc).__name__,
            resume_ref=manifest_rel,
        )
    coverage = doc.get("coverage")
    declared_blockers: list[int] = []
    if type(coverage) is dict and "blocking_task_ids" in coverage:
        raw_blockers = coverage["blocking_task_ids"]
        if type(raw_blockers) is not list or any(type(item) is not int or item < 1 for item in raw_blockers):
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=entity_id,
                expected="list of positive integer Task IDs in coverage.blocking_task_ids",
                actual=raw_blockers,
                resume_ref=manifest_rel,
            )
        if len(raw_blockers) != len(set(raw_blockers)):
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.SCHEMA,
                entity_id=entity_id,
                expected="unique Task IDs in coverage.blocking_task_ids",
                actual=raw_blockers,
                resume_ref=manifest_rel,
            )
        declared_blockers = list(raw_blockers)

    # Synthesize a status-decoupled tasks.json view for native _mvg_manifest.validate_manifest
    # so advancing a sibling Flow Task's live status to "done" never invalidates the manifest,
    # while preserving exact Task existence, dedicated-owner, and non-scoped blocker checks.
    blocker_set = set(declared_blockers)
    decoupled_master = {
        "master": {
            "tasks": [
                {
                    "id": tid,
                    "status": "pending" if tid in blocker_set else "done",
                }
                for tid in sorted(master_tasks)
            ]
        }
    }
    decoupled_tasks_bytes = _json_raw_bytes(decoupled_master)

    def _observed_read(rel_path: str) -> bytes | None:
        norm = preflight.path(rel_path)
        if norm == resolver.TRIPLET["master"]:
            return decoupled_tasks_bytes
        return observations.read(norm, optional=True)

    errors = mvg_manifest.validate_manifest(root, doc, executable=False, read_bytes=_observed_read)
    if errors:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected="valid MVG integration manifest (schema/flows/tests/files/tasks)",
            actual={"manifest_path": manifest_rel, "errors": errors},
            resume_ref=manifest_rel,
        )

    m_sha = mvg_manifest.manifest_sha256(manifest_raw)
    return doc, m_sha


def _parse_dependency_id(
    raw: Any,
    *,
    master_tasks: dict[int, dict[str, Any]],
    views: dict[str, dict[str, int]],
    entity_id: str,
    source_path: str,
) -> int:
    if type(raw) is int:
        if raw < 1 or raw not in master_tasks:
            _fail(
                codec.ReasonCode.UNKNOWN_ENTITY,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="existing positive integer dependency Task ID",
                actual=raw,
                resume_ref=source_path,
            )
        return raw
    if type(raw) is str:
        if not raw or raw != raw.strip():
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected="unpadded dependency Task ID or business view ID",
                actual=raw,
                resume_ref=source_path,
            )
        if _POS_INT_STR_RE.fullmatch(raw):
            parsed = int(raw)
            if parsed not in master_tasks:
                _fail(
                    codec.ReasonCode.UNKNOWN_ENTITY,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="existing dependency master Task ID",
                    actual=parsed,
                    resume_ref=source_path,
                )
            return parsed
        if raw in views["back"]:
            return views["back"][raw]
        if raw in views["gameplay"]:
            return views["gameplay"][raw]
        _fail(
            codec.ReasonCode.UNKNOWN_ENTITY,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="existing dependency Task ID or business view ID",
            actual=raw,
            resume_ref=source_path,
        )
    _fail(
        codec.ReasonCode.INVALID_TYPE,
        stage=codec.Stage.CONTENT,
        entity_id=entity_id,
        expected="dependency Task ID (int or string)",
        actual=type(raw).__name__,
        resume_ref=source_path,
    )
    return -1


def _collect_direct_dependencies(
    tid: int,
    *,
    master_tasks: dict[int, dict[str, Any]],
    back_by_tid: dict[int, list[dict[str, Any]]],
    gameplay_by_tid: dict[int, list[dict[str, Any]]],
    views: dict[str, dict[str, int]],
    entity_id: str,
) -> list[int]:
    deps: list[int] = []
    seen: set[int] = set()
    master_row = master_tasks[tid]
    raw_master_deps = master_row.get("dependencies", [])
    if type(raw_master_deps) is not list:
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected="list in master task dependencies",
            actual=type(raw_master_deps).__name__,
            resume_ref=resolver.TRIPLET["master"],
        )
    for raw_dep in raw_master_deps:
        dep_tid = _parse_dependency_id(
            raw_dep,
            master_tasks=master_tasks,
            views=views,
            entity_id=entity_id,
            source_path=resolver.TRIPLET["master"],
        )
        if dep_tid not in seen:
            seen.add(dep_tid)
            deps.append(dep_tid)
    for view_name, rows in (("back", back_by_tid.get(tid, [])), ("gameplay", gameplay_by_tid.get(tid, []))):
        for row in rows:
            raw_view_deps = row.get("depends_on", [])
            if type(raw_view_deps) is not list:
                _fail(
                    codec.ReasonCode.INVALID_TYPE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected=f"list in {view_name} task depends_on",
                    actual=type(raw_view_deps).__name__,
                    resume_ref=resolver.TRIPLET[view_name],
                )
            for raw_dep in raw_view_deps:
                dep_tid = _parse_dependency_id(
                    raw_dep,
                    master_tasks=master_tasks,
                    views=views,
                    entity_id=entity_id,
                    source_path=resolver.TRIPLET[view_name],
                )
                if dep_tid not in seen:
                    seen.add(dep_tid)
                    deps.append(dep_tid)
    return sorted(deps)


def _compute_dependency_closure(
    root_tid: int,
    *,
    master_tasks: dict[int, dict[str, Any]],
    back_by_tid: dict[int, list[dict[str, Any]]],
    gameplay_by_tid: dict[int, list[dict[str, Any]]],
    views: dict[str, dict[str, int]],
) -> tuple[list[int], list[int]]:
    """Compute direct and transitive dependency Task IDs; fail closed on unknown or cyclic edges."""
    entity_id = str(root_tid)
    direct = _collect_direct_dependencies(
        root_tid,
        master_tasks=master_tasks,
        back_by_tid=back_by_tid,
        gameplay_by_tid=gameplay_by_tid,
        views=views,
        entity_id=entity_id,
    )
    transitive: set[int] = set()
    visited: set[int] = set()
    visiting: list[int] = [root_tid]
    visiting_set: set[int] = {root_tid}

    def _dfs(curr: int, children: list[int]) -> None:
        for nxt in children:
            if nxt in visiting_set:
                cycle_start = visiting.index(nxt)
                _fail(
                    codec.ReasonCode.DIGEST_CYCLE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="acyclic Task dependency closure",
                    actual={"cycle": [*visiting[cycle_start:], nxt]},
                    resume_ref=resolver.TRIPLET["master"],
                )
            transitive.add(nxt)
            if nxt in visited:
                continue
            visiting.append(nxt)
            visiting_set.add(nxt)
            nxt_children = _collect_direct_dependencies(
                nxt,
                master_tasks=master_tasks,
                back_by_tid=back_by_tid,
                gameplay_by_tid=gameplay_by_tid,
                views=views,
                entity_id=entity_id,
            )
            _dfs(nxt, nxt_children)
            visiting.pop()
            visiting_set.remove(nxt)
            visited.add(nxt)

    _dfs(root_tid, direct)
    return direct, sorted(transitive)


def _task_projection_bundle(
    tid: int,
    *,
    master_tasks: dict[int, dict[str, Any]],
    back_by_tid: dict[int, list[dict[str, Any]]],
    gameplay_by_tid: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    master_row = master_tasks[tid]
    back_rows = back_by_tid.get(tid, [])
    gameplay_rows = gameplay_by_tid.get(tid, [])
    protection._task_state(master_row, master=True)
    for row in (*back_rows, *gameplay_rows):
        protection._task_state(row, master=False)
    return {
        "master": protection.task_definition_projection(master_row),
        "back": [protection.task_definition_projection(row) for row in back_rows],
        "gameplay": [protection.task_definition_projection(row) for row in gameplay_rows],
    }


def _collect_task_adrs_overlays_contracts(
    *,
    root: Path,
    observations: preflight.Observations,
    task_rows: list[dict[str, Any]],
    extra_adr_refs: list[str],
    extra_overlay_refs: list[str],
    extra_contract_refs: list[str],
    items: dict[tuple[str, str], dict[str, Any]],
    entity_id: str,
) -> None:
    """Resolve and record ADRs, Overlays (with path checks), and Game.Core/Contracts/**."""
    adr_refs: list[str] = list(extra_adr_refs)
    overlay_refs: list[str] = list(extra_overlay_refs)
    contract_refs: list[str] = list(extra_contract_refs)

    for row in task_rows:
        for field in ("adr_refs", "adrRefs"):
            vals = row.get(field)
            if type(vals) is list:
                for val in vals:
                    if type(val) is str and val.strip():
                        adr_refs.append(val.strip())
        ov_single = row.get("overlay")
        if type(ov_single) is str and ov_single.strip():
            overlay_refs.append(ov_single.strip())
        ov_list = row.get("overlay_refs")
        if type(ov_list) is list:
            for val in ov_list:
                if type(val) is str and val.strip():
                    overlay_refs.append(val.strip())
        if "contractRefs" in row and row["contractRefs"] is not None:
            c_list = row["contractRefs"]
            if type(c_list) is not list:
                _fail(
                    codec.ReasonCode.INVALID_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="list of nonempty contract reference strings in contractRefs",
                    actual=c_list,
                    resume_ref="Game.Core/Contracts",
                )
            for val in c_list:
                if type(val) is not str or not val.strip() or val != val.strip():
                    _fail(
                        codec.ReasonCode.INVALID_REFERENCE,
                        stage=codec.Stage.REFERENCE,
                        entity_id=entity_id,
                        expected="nonempty unpadded contract reference string in contractRefs",
                        actual=val,
                        resume_ref="Game.Core/Contracts",
                    )
                contract_refs.append(val)

    # 1. Overlays (also harvest frontmatter ADRs and check concrete backtick paths).
    seen_overlays: set[str] = set()
    for ov_raw_ref in sorted(set(overlay_refs)):
        ov_rel = preflight.path(ov_raw_ref)
        if ov_rel in seen_overlays:
            continue
        seen_overlays.add(ov_rel)
        raw = observations.read(ov_rel)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(
                codec.ReasonCode.INVALID_UTF8,
                stage=codec.Stage.DECODE,
                entity_id=entity_id,
                expected="UTF-8 overlay markdown document",
                actual=ov_rel,
                resume_ref=ov_rel,
            )
        fm = overlay_exec.parse_front_matter(text)
        fm_adrs = fm.get("ADRs")
        if type(fm_adrs) is list:
            for item in fm_adrs:
                if type(item) is str and item.strip():
                    adr_refs.append(item.strip())
        elif type(fm_adrs) is str and fm_adrs.strip():
            adr_refs.append(fm_adrs.strip())
        # Check concrete backtick paths with contained safe_input observations.
        for bt_ref in overlay_exec.extract_backtick_paths(text):
            if not overlay_exec.should_check_path(bt_ref):
                continue
            bt_clean = bt_ref.rstrip("/")
            if not bt_clean:
                continue
            try:
                bt_norm = preflight.path(bt_clean)
                bt_path = inventory.safe_input(root, bt_norm, allow_logs=False)
            except (codec.CodecError, OSError, ValueError):
                _fail(
                    codec.ReasonCode.UNSAFE_PATH,
                    stage=codec.Stage.PATH,
                    entity_id=entity_id,
                    expected="safe contained path referenced from overlay",
                    actual=bt_ref,
                    resume_ref=ov_rel,
                )
            if not bt_path.exists():
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="existing path referenced by overlay document",
                    actual={"overlay": ov_rel, "missing_ref": bt_ref},
                    resume_ref=ov_rel,
                )
            if bt_path.is_dir():
                observations.scan(bt_norm)
            else:
                observations.read(bt_norm)
        dg = codec.raw_digest(raw)
        items[("overlay", ov_rel)] = _make_item(
            category="overlay",
            locator=ov_rel,
            raw_digest=dg,
            normalization_mode="raw_bytes",
            codec_version=codec.CODEC_VERSION,
            normalized_digest=dg,
            return_stage="4",
            details={"path": ov_rel},
        )

    # 2. ADRs (resolve both ADR-XXXX IDs and direct docs/adr/*.md paths).
    adr_dir_files: list[str] | None = None
    seen_adrs: set[str] = set()
    for adr_ref in sorted(set(adr_refs)):
        if _ADR_ID_RE.fullmatch(adr_ref):
            if adr_dir_files is None:
                adr_dir_files = [
                    p for p in observations.scan("docs/adr") if p.endswith(".md")
                ]
            prefix = f"docs/adr/{adr_ref}".casefold()
            matches = [
                p
                for p in adr_dir_files
                if p.casefold() == prefix + ".md" or p.casefold().startswith(prefix + "-")
            ]
            if not matches:
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected=f"existing ADR document for {adr_ref}",
                    actual=adr_ref,
                    resume_ref="docs/adr",
                )
            resolved_paths = matches
        else:
            resolved_paths = [preflight.path(adr_ref.partition("#")[0])]
        for adr_path in resolved_paths:
            if adr_path in seen_adrs:
                continue
            seen_adrs.add(adr_path)
            raw = observations.read(adr_path)
            dg = codec.raw_digest(raw)
            items[("adr", adr_path)] = _make_item(
                category="adr",
                locator=adr_path,
                raw_digest=dg,
                normalization_mode="raw_bytes",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=dg,
                return_stage="4",
                details={"path": adr_path},
            )

    # 3. Game.Core/Contracts/** (resolve via _chapter5_contract_bindings).
    if contract_refs:
        contract_files = [
            p for p in observations.scan("Game.Core/Contracts") if p.endswith(".cs")
        ]
        contract_sources = {p: observations.read(p) for p in contract_files}
        for cref in sorted(set(contract_refs)):
            if type(cref) is not str or not cref.strip() or cref != cref.strip():
                _fail(
                    codec.ReasonCode.INVALID_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="nonempty unpadded contract reference",
                    actual=cref,
                    resume_ref="Game.Core/Contracts",
                )
            resolver_ref = cref
            if "/" in cref or "\\" in cref:
                try:
                    resolver_ref = preflight.path(cref)
                except codec.CodecError:
                    _fail(
                        codec.ReasonCode.INVALID_REFERENCE,
                        stage=codec.Stage.REFERENCE,
                        entity_id=entity_id,
                        expected="safe canonical contract path under Game.Core/Contracts/**",
                        actual=cref,
                        resume_ref="Game.Core/Contracts",
                    )
            bound = contract_bindings.resolve_contract(root, resolver_ref, sources=contract_sources)
            if bound is None:
                _fail(
                    codec.ReasonCode.INVALID_REFERENCE,
                    stage=codec.Stage.REFERENCE,
                    entity_id=entity_id,
                    expected="existing contract declaration in Game.Core/Contracts/**",
                    actual=cref,
                    resume_ref="Game.Core/Contracts",
                )
            for row in bound["bindings"]:
                c_path = preflight.path(row["path"])
                raw = contract_sources[c_path]
                dg = codec.raw_digest(raw)
                items[("contract", c_path)] = _make_item(
                    category="contract",
                    locator=c_path,
                    raw_digest=dg,
                    normalization_mode="raw_bytes",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=dg,
                    return_stage="4",
                    details={"path": c_path, "resolved_from": cref},
                )


def _validate_and_load_candidate_binding(
    *,
    observations: preflight.Observations,
    candidate_binding_path: str,
    task_id: int,
    committed_plan_refs_by_id: dict[str, dict[str, Any]],
    loaded_plans: dict[str, dict[str, Any]],
    catalog: dict[str, Any],
    task_join: records.TaskJoinContext,
) -> tuple[str, bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Strictly validate an explicit uncommitted candidate binding and verify plan_ref + OwnedRefs."""
    entity_id = str(task_id)
    cand_rel = preflight.path(candidate_binding_path)
    cand_raw = observations.read(cand_rel)
    checked = records.validate_record(cand_raw, path=None)
    if not checked.ok:
        raise codec.CodecError(checked.diagnostic)
    cand_doc = codec.strict_json_loads(cand_raw)
    if cand_doc.get("schema_version") != "newrouge.b-route-binding.v1":
        _fail(
            codec.ReasonCode.SCHEMA_MISMATCH,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected="newrouge.b-route-binding.v1",
            actual=cand_doc.get("schema_version"),
            resume_ref=cand_rel,
        )
    cand_plan_id = cand_doc["plan_id"]
    if cand_plan_id not in committed_plan_refs_by_id:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=sorted(committed_plan_refs_by_id),
            actual=cand_plan_id,
            resume_ref=cand_rel,
        )
    expected_plan_ref = committed_plan_refs_by_id[cand_plan_id]
    cand_plan_ref = cand_doc["plan_ref"]
    if codec.canonical_digest(cand_plan_ref) != codec.canonical_digest(expected_plan_ref):
        _fail(
            codec.ReasonCode.REVISION_MISMATCH,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected=expected_plan_ref,
            actual=cand_plan_ref,
            resume_ref=cand_rel,
        )
    plan_doc = resolver._load_formal_json(observations, cand_plan_ref)
    if plan_doc.get("plan_id") != cand_plan_id or plan_doc.get("revision") != cand_plan_ref["revision"]:
        _fail(
            codec.ReasonCode.REVISION_MISMATCH,
            stage=codec.Stage.REFERENCE,
            entity_id=entity_id,
            expected=[cand_plan_id, cand_plan_ref["revision"]],
            actual=[plan_doc.get("plan_id"), plan_doc.get("revision")],
            resume_ref=cand_rel,
        )

    # Verify task_mappings, obligations, implementation_objects, and TaskJoinContext.
    master_tasks, views = task_join.indexes()
    plan_req_ids = {r["requirement_id"] for r in plan_doc["requirements"]}
    verif_by_req = {r["requirement_id"]: r for r in plan_doc["requirement_verification"]}
    catalog_flow_ids = {r["definition_id"] for r in catalog["definition_owners"] if r["kind"] == "flow"}
    obl_by_id = {r["id"]: r for r in cand_doc["obligations"]}
    obl_ids = set(obl_by_id)
    mapped_tids = {m["task_id"] for m in cand_doc["task_mappings"]}

    if task_id not in mapped_tids:
        _fail(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=f"candidate binding task_mappings containing task_id {task_id}",
            actual=sorted(mapped_tids),
            resume_ref=cand_rel,
        )
    for obj in cand_doc["implementation_objects"]:
        if not set(obj["responsible_task_ids"]) <= mapped_tids:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="responsible_task_ids mapped in candidate binding",
                actual=obj["responsible_task_ids"],
                resume_ref=cand_rel,
            )
    for obl in cand_doc["obligations"]:
        if not set(obl["requirement_ids"]) <= plan_req_ids or not set(obl["flow_ids"]) <= catalog_flow_ids:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="declared plan requirements and catalog flows in candidate obligation",
                actual=obl["id"],
                resume_ref=cand_rel,
            )
        for req_id in obl["requirement_ids"]:
            if verif_by_req.get(req_id, {}).get("disposition") == "source_gap":
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="resolved disposition (flow|other_verification|deferred); source_gap disallowed in candidate binding",
                    actual={"plan_id": cand_plan_id, "obligation_id": obl["id"], "requirement_id": req_id, "disposition": "source_gap"},
                    resume_ref=cand_rel,
                )
    target_mapping: dict[str, Any] | None = None
    for mapping in cand_doc["task_mappings"]:
        mtid = mapping["task_id"]
        if mtid not in master_tasks:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="existing master task_id in candidate binding",
                actual=mtid,
                resume_ref=cand_rel,
            )
        for vref in mapping["view_refs"]:
            if views[vref["view"]].get(vref["business_id"]) != mtid:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="exact master/view join for candidate binding view_ref",
                    actual=vref,
                    resume_ref=cand_rel,
                )
        if (
            not set(mapping["requirement_ids"]) <= plan_req_ids
            or not set(mapping["flow_ids"]) <= catalog_flow_ids
            or not set(mapping["obligation_ids"]) <= obl_ids
        ):
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="declared requirements, flows, and obligations in candidate task_mapping",
                actual=mtid,
                resume_ref=cand_rel,
            )
        if (
            not mapping["requirement_ids"]
            and not mapping["flow_ids"]
            and "integration_only_owner" not in mapping["roles"]
        ):
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="nonempty requirement_ids or flow_ids unless integration_only_owner role is declared",
                actual={"task_id": mtid, "roles": mapping["roles"]},
                resume_ref=cand_rel,
            )
        for req_id in mapping["requirement_ids"]:
            if verif_by_req.get(req_id, {}).get("disposition") == "source_gap":
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="resolved disposition (flow|other_verification|deferred); source_gap disallowed in candidate binding",
                    actual={"plan_id": cand_plan_id, "task_id": mtid, "requirement_id": req_id, "disposition": "source_gap"},
                    resume_ref=cand_rel,
                )
        if mtid == task_id:
            target_mapping = mapping

    # Empirically verify every OwnedRef inside the uncommitted candidate binding against live files
    # (allow_sealed_logs=False: absent clean-clone logs/ are strictly disallowed on candidates).
    for child in records._walk(cand_doc):
        if type(child) is dict and set(child) == {"owner", "ref", "files"}:
            preflight.owned(child, observations)

    cand_ref = {
        "path": cand_rel,
        "schema_version": "newrouge.b-route-binding.v1",
        "entity_id": cand_plan_id,
        "revision": cand_doc["binding_revision"],
        "digest": codec.raw_digest(cand_raw),
        "verification_mode": "raw",
        "codec_version": None,
    }
    return cand_rel, cand_raw, cand_ref, cand_doc, target_mapping


def _recompute_task_closure_for_effective_bindings(
    *,
    observations: preflight.Observations,
    catalog: dict[str, Any],
    task_id: int,
    effective_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any], bool]],
    all_plan_refs: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], set[str]]:
    """Recompute task-scoped resolved_definitions, dispositions, flows, reqs, and owning scopes."""
    entity_id = str(task_id)
    owners_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in catalog["definition_owners"]:
        owners_map[(row["kind"], row["definition_id"])] = deepcopy(row)

    plan_cache: dict[str, dict[str, Any]] = {}
    plan_indexes: dict[str, dict[str, Any]] = {}

    def _load_plan(pref: dict[str, Any]) -> dict[str, Any]:
        pkey = codec.canonical_digest(pref)
        if pkey not in plan_cache:
            pdoc = resolver._load_formal_json(observations, pref)
            if pdoc.get("plan_id") != pref["entity_id"] or pdoc.get("revision") != pref["revision"]:
                _fail(
                    codec.ReasonCode.REVISION_MISMATCH,
                    stage=codec.Stage.REFERENCE,
                    entity_id=pref["entity_id"],
                    expected=[pref["entity_id"], pref["revision"]],
                    actual=[pdoc.get("plan_id"), pdoc.get("revision")],
                    resume_ref=pref["path"],
                )
            plan_cache[pkey] = pdoc
            all_plan_refs.setdefault(pref["entity_id"], deepcopy(pref))
        return plan_cache[pkey]

    def _plan_index(pref: dict[str, Any], pdoc: dict[str, Any]) -> dict[str, Any]:
        pkey = codec.canonical_digest(pref)
        if pkey not in plan_indexes:
            route_memberships_by_req: dict[str, list[str]] = {}
            for row in pdoc["requirement_route_memberships"]:
                route_memberships_by_req.setdefault(row["requirement_id"], []).append(row["flow_id"])
            plan_indexes[pkey] = {
                "req_defs": {r["requirement_id"]: r for r in pdoc["requirements"]},
                "verif_map": {r["requirement_id"]: r for r in pdoc["requirement_verification"]},
                "evidence_refs": {(r["owner"], r["ref"]): r for r in pdoc["evidence_source_refs"]},
                "route_memberships_by_req": route_memberships_by_req,
                "req_evidence_by_id": {r["evidence_id"]: r for r in pdoc["requirement_evidence"]},
            }
        return plan_indexes[pkey]

    def _validate_flow_owner(fid: str, *, resume_ref: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        owner = owners_map.get(("flow", fid))
        if owner is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="catalog definition_owner for flow",
                actual=fid,
                resume_ref=resume_ref,
            )
        owner_plan = _load_plan(owner["plan_ref"])
        flow_def = next((f for f in owner_plan["definitions"]["flows"] if f["id"] == fid), None)
        if flow_def is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="flow definition in owner plan",
                actual=fid,
                resume_ref=owner["plan_ref"]["path"],
            )
        return owner, owner_plan, flow_def

    dispositions: list[dict[str, Any]] = []
    seen_dispositions: set[tuple[str, int, str]] = set()
    applicable_flow_ids: set[str] = set()
    applicable_req_ids: set[str] = set()
    task_binding_entries: list[Any] = []

    def _validate_req(target_plan_ref: dict[str, Any], target_plan_doc: dict[str, Any], req_id: str) -> None:
        t_plan_id = target_plan_doc["plan_id"]
        t_plan_rev = target_plan_doc["revision"]
        idx = _plan_index(target_plan_ref, target_plan_doc)
        applicable_req_ids.add(req_id)
        if req_id not in idx["req_defs"] or req_id not in idx["verif_map"]:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="committed requirement and requirement_verification disposition",
                actual={"plan_id": t_plan_id, "requirement_id": req_id},
                resume_ref=target_plan_ref["path"],
            )
        verif = idx["verif_map"][req_id]
        disp = verif["disposition"]
        if disp == "source_gap":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="resolved disposition (flow|other_verification|deferred); source_gap blocks execution",
                actual={"plan_id": t_plan_id, "requirement_id": req_id, "disposition": disp},
                resume_ref=target_plan_ref["path"],
            )
        if disp == "flow":
            fid = verif["flow_id"]
            _validate_flow_owner(fid, resume_ref=target_plan_ref["path"])
            applicable_flow_ids.add(fid)
        for route_fid in idx["route_memberships_by_req"].get(req_id, []):
            _validate_flow_owner(route_fid, resume_ref=target_plan_ref["path"])
            applicable_flow_ids.add(route_fid)
        disp_key = (t_plan_id, t_plan_rev, req_id)
        if disp_key not in seen_dispositions:
            seen_dispositions.add(disp_key)
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
                    "route_flow_ids": sorted(set(idx["route_memberships_by_req"].get(req_id, []))),
                }
            )

    direct_plan_refs: list[dict[str, Any]] = []
    for pid in sorted(effective_bindings):
        bref, _braw, bdoc, mapping, _is_comm = effective_bindings[pid]
        plan_ref = bdoc["plan_ref"]
        direct_plan_refs.append(plan_ref)
        plan_doc = _load_plan(plan_ref)
        plan_id = plan_doc["plan_id"]
        plan_rev = plan_doc["revision"]
        task_binding_entries.append(mapping)

        obl_map = {row["id"]: row for row in bdoc["obligations"]}
        mapped_reqs = list(mapping["requirement_ids"])
        mapped_flows = list(mapping["flow_ids"])
        for obl_id in mapping["obligation_ids"]:
            obl = obl_map[obl_id]
            task_binding_entries.append(obl)
            for req_id in obl["requirement_ids"]:
                if req_id not in mapped_reqs:
                    mapped_reqs.append(req_id)
            for flow_id in obl["flow_ids"]:
                if flow_id not in mapped_flows:
                    mapped_flows.append(flow_id)
        for obj in bdoc["implementation_objects"]:
            if task_id in obj["responsible_task_ids"]:
                task_binding_entries.append(obj)

        if not mapped_reqs and not mapped_flows and "integration_only_owner" not in mapping["roles"]:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="committed plan requirement disposition or flow definition",
                actual={"binding_path": bref["path"], "requirement_ids": mapped_reqs, "flow_ids": mapped_flows},
                resume_ref=bref["path"],
            )

        cross_plan_reqs: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for flow_id in mapped_flows:
            owner, owner_plan, flow_def = _validate_flow_owner(flow_id, resume_ref=bref["path"])
            applicable_flow_ids.add(flow_id)
            for freq_id in flow_def.get("requirement_ids", []):
                if owner_plan["plan_id"] == plan_id and owner_plan["revision"] == plan_rev:
                    if freq_id not in mapped_reqs:
                        mapped_reqs.append(freq_id)
                else:
                    cross_plan_reqs.append((owner["plan_ref"], owner_plan, freq_id))
        for req_id in mapped_reqs:
            _validate_req(plan_ref, plan_doc, req_id)
        for owner_pref, owner_pdoc, freq_id in cross_plan_reqs:
            _validate_req(owner_pref, owner_pdoc, freq_id)

    use_fields = {"kind", "definition_id", "owner_plan_id", "owner_revision"}

    def _collect_uses(obj: Any) -> list[dict[str, Any]]:
        return [child for child in records._walk(obj) if type(child) is dict and set(child) == use_fields]

    pending_uses: list[dict[str, Any]] = []
    resolved_def_map: dict[tuple[str, str], dict[str, Any]] = {}

    for flow_id in sorted(applicable_flow_ids):
        owner, _owner_plan, flow_def = _validate_flow_owner(flow_id, resume_ref=resolver.CATALOG_PATH)
        resolved_def_map[("flow", flow_id)] = owner
        pending_uses.extend(_collect_uses(flow_def))

    for pref in direct_plan_refs:
        plan_doc = _load_plan(pref)
        for kind, plural in (("command", "commands"), ("state", "states")):
            for defn in plan_doc["definitions"][plural]:
                if set(defn.get("requirement_ids", [])) & applicable_req_ids:
                    key = (kind, defn["id"])
                    owner = owners_map.get(key)
                    if owner is None:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            stage=codec.Stage.BUNDLE,
                            entity_id=entity_id,
                            expected="explicit catalog definition owner",
                            actual=list(key),
                            resume_ref=resolver.CATALOG_PATH,
                        )
                    resolved_def_map[key] = owner
                    pending_uses.extend(_collect_uses(defn))

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
                entity_id=entity_id,
                expected="explicit catalog definition owner",
                actual=list(key),
                resume_ref=resolver.CATALOG_PATH,
            )
        owner = owners_map[key]
        pref = owner["plan_ref"]
        if pref["entity_id"] != use["owner_plan_id"] or pref["revision"] != use["owner_revision"]:
            _fail(
                codec.ReasonCode.REVISION_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected=[use["owner_plan_id"], use["owner_revision"]],
                actual=[pref["entity_id"], pref["revision"]],
                resume_ref=resolver.CATALOG_PATH,
            )
        resolved_def_map[key] = owner
        visit_id = (key[0], key[1], codec.canonical_digest(pref))
        if visit_id in visited_defs:
            continue
        visited_defs.add(visit_id)
        owner_plan = _load_plan(pref)
        plural = {"flow": "flows", "command": "commands", "state": "states"}[key[0]]
        defn = next((r for r in owner_plan["definitions"][plural] if r["id"] == key[1]), None)
        if defn is None:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="declared owner definition in owner plan",
                actual=list(key),
                resume_ref=pref["path"],
            )
        if key[0] == "flow":
            applicable_flow_ids.add(key[1])
        pending_uses.extend(_collect_uses(defn))

    sorted_resolved_defs = sorted(resolved_def_map.values(), key=resolver._def_owner_sort_key)
    sorted_dispositions = sorted(dispositions, key=resolver._disposition_sort_key)
    applicable_flow_closure = sorted(
        applicable_flow_ids | {k[1] for k in resolved_def_map if k[0] == "flow"}
    )
    applicable_plan_keys = {codec.canonical_digest(pref) for pref in all_plan_refs.values()}
    owning_scope_ids: set[str] = set()
    for head in catalog["scope_heads"]:
        head_plan_keys = {codec.canonical_digest(ref) for ref in head["plan_refs"]}
        if head_plan_keys & applicable_plan_keys:
            owning_scope_ids.add(head["scope_id"])
    return (
        sorted_resolved_defs,
        sorted_dispositions,
        applicable_flow_closure,
        sorted(applicable_req_ids),
        owning_scope_ids,
    )


def _collect_environment_items(items: dict[tuple[str, str], dict[str, Any]]) -> None:
    """Record codec and policy/rules/environment identity items (return_stage='5')."""
    codec_payload = {
        "input_set_schema": SCHEMA,
        "content_codec": codec.CODEC_VERSION,
        "projection_codec": codec.PROJECTION_CODEC,
    }
    codec_raw_dg = codec.raw_digest(_json_raw_bytes(codec_payload))
    codec_norm_dg = codec.canonical_digest(codec_payload)
    items[("codec", "b-route:codec")] = _make_item(
        category="codec",
        locator="b-route:codec",
        raw_digest=codec_raw_dg,
        normalization_mode="canonical_json",
        codec_version=codec.CODEC_VERSION,
        normalized_digest=codec_norm_dg,
        return_stage="5",
        details=codec_payload,
    )

    rules_identity, _rule_files = adoption_review.policy_observations()
    env_payload = {
        "policy_rules_identity": rules_identity,
        "os_name": os.name,
        "platform": sys.platform,
        "python_version": sys.version,
    }
    env_raw_dg = codec.raw_digest(_json_raw_bytes(env_payload))
    env_norm_dg = codec.canonical_digest(env_payload)
    items[("environment", "b-route:environment")] = _make_item(
        category="environment",
        locator="b-route:environment",
        raw_digest=env_raw_dg,
        normalization_mode="environment_identity",
        codec_version=codec.CODEC_VERSION,
        normalized_digest=env_norm_dg,
        return_stage="5",
        details={
            "policy_rules_identity": rules_identity,
            "os_name": os.name,
            "platform": sys.platform,
        },
    )


def _resolve_once(
    *,
    root_path: Path,
    task_id: int,
    operation: str | None,
    candidate_binding: str | None,
    baseline_arg: dict[str, Any] | str | Path | None,
    lock_mode: str,
    before_reread: Callable[[], None] | None,
) -> tuple[dict[str, Any], bool]:
    """Run one pure read-only InputSet resolution pass. Returns (result, is_drift)."""
    result = _base_result(task_id, operation, lock_mode=lock_mode)
    observations = preflight.Observations(root_path)
    entity_id = str(task_id)
    initial_graph_bytes: dict[str, bytes | None] | None = None

    try:
        # 1. Always invoke Story 3.3 first to verify origin, pending, and applicable plan set.
        origin = resolver.resolve_task_origin(
            root_path,
            task_id,
            operation=operation,
        )
        result["origin_summary"] = {
            "route": origin["route"],
            "governance_state": origin["governance_state"],
            "applicable_set_digest": origin["applicable_set_digest"],
            "applicable_scope_ids": list(origin["applicable_scope_ids"]),
            "non_flow_summary": deepcopy(origin["non_flow_summary"]),
            "pending_summary": deepcopy(origin["pending_summary"]),
        }
        result["route"] = origin["route"]
        result["governance_state"] = origin["governance_state"]
        result["applicable_set_digest"] = origin["applicable_set_digest"]

        if not origin["ok"] or not origin["stable"] or origin["route"] == "blocked":
            diags = list(origin["diagnostics"])
            is_drift = (not origin["stable"]) or any(
                d.get("reason_code") == codec.ReasonCode.FILE_CHANGED.value for d in diags
            )
            result["diagnostics"] = diags
            result["stable"] = bool(origin["stable"]) and not is_drift
            inferred_stages = [_stage_for_diag(d) for d in diags]
            result["return_stage"] = _earliest_stage(inferred_stages)
            return result, is_drift

        # Record legacy pending markers/dirs, B-route operation store, and governance directory
        # into _resolve_once's own observations so observations.finish() catches mid-read drift.
        pending_summary_local: dict[str, Any] = {
            "legacy_pending_clear": False,
            "blocking_operations": [],
            "non_overlapping_unapplied_operations": [],
        }
        graph_bytes_holder: dict[str, Any] = {"bytes": None}
        _graph, unapplied_ops = resolver._inspect_pending(
            root_path,
            observations,
            task_id,
            pending_summary=pending_summary_local,
            graph_bytes_holder=graph_bytes_holder,
        )
        initial_graph_bytes = graph_bytes_holder["bytes"]
        for b_rel in observations.scan("docs/planning/b-route"):
            observations.read(b_rel)

        # 2. Read and join Taskmaster triplet through Observations.
        triplet_raw = {name: observations.read(rel) for name, rel in resolver.TRIPLET.items()}
        docs = {name: codec.strict_json_loads(raw) for name, raw in triplet_raw.items()}
        task_join = records.TaskJoinContext(**docs)
        master_tasks, views = task_join.indexes()

        back_by_tid: dict[int, list[dict[str, Any]]] = {}
        for row in docs["back"]:
            back_by_tid.setdefault(row["taskmaster_id"], []).append(row)
        gameplay_by_tid: dict[int, list[dict[str, Any]]] = {}
        for row in docs["gameplay"]:
            gameplay_by_tid.setdefault(row["taskmaster_id"], []).append(row)

        # 3. Compute transitive dependency closure (rejecting unknown or cyclic edges).
        direct_deps, transitive_deps = _compute_dependency_closure(
            task_id,
            master_tasks=master_tasks,
            back_by_tid=back_by_tid,
            gameplay_by_tid=gameplay_by_tid,
            views=views,
        )

        # Build live dependency eligibility OUTSIDE input_set_digest (never copied into authority).
        master_row = master_tasks[task_id]
        protection._task_state(master_row, master=True)
        for dep_tid in transitive_deps:
            protection._task_state(master_tasks[dep_tid], master=True)
        result["dependency_eligibility"] = {
            "status_authority": resolver.TRIPLET["master"],
            "self_task_id": task_id,
            "self_live_status": master_row["status"],
            "self_done_required": False,
            "direct_dependency_ids": direct_deps,
            "transitive_dependency_ids": transitive_deps,
            "dependencies": [
                {
                    "task_id": dep_tid,
                    "direct": dep_tid in direct_deps,
                    "live_status": master_tasks[dep_tid]["status"],
                    "done": master_tasks[dep_tid]["status"] == "done",
                }
                for dep_tid in transitive_deps
            ],
            "all_dependencies_done": all(
                master_tasks[dep_tid]["status"] == "done" for dep_tid in transitive_deps
            ),
            "non_done_dependency_ids": [
                dep_tid for dep_tid in transitive_deps if master_tasks[dep_tid]["status"] != "done"
            ],
            "unmet_dependencies_allowed": True,
        }

        items: dict[tuple[str, str], dict[str, Any]] = {}
        sealed_log_paths: set[str] = set()
        extra_adr_refs: list[str] = []
        extra_overlay_refs: list[str] = []
        extra_contract_refs: list[str] = []
        scope_ids_set: set[str] = set()
        owning_scope_ids: set[str] = set()

        # 4. Record Task definition projection (master + back + gameplay; excludes ONLY status and direct subtasks[].status).
        self_proj = _task_projection_bundle(
            task_id,
            master_tasks=master_tasks,
            back_by_tid=back_by_tid,
            gameplay_by_tid=gameplay_by_tid,
        )
        items[("task_definition", f"task:{task_id}:master")] = _make_item(
            category="task_definition",
            locator=f"task:{task_id}:master",
            raw_digest=codec.raw_digest(triplet_raw["master"]),
            normalization_mode="task_definition_projection",
            codec_version=codec.PROJECTION_CODEC,
            normalized_digest=codec.canonical_digest(self_proj["master"]),
            return_stage="3C",
            details={"path": resolver.TRIPLET["master"], "task_id": task_id},
        )
        for view_name, view_rows in (("back", back_by_tid.get(task_id, [])), ("gameplay", gameplay_by_tid.get(task_id, []))):
            for vrow in sorted(view_rows, key=lambda r: r["id"]):
                proj_v = protection.task_definition_projection(vrow)
                items[("task_definition", f"task:{task_id}:{view_name}:{vrow['id']}")] = _make_item(
                    category="task_definition",
                    locator=f"task:{task_id}:{view_name}:{vrow['id']}",
                    raw_digest=codec.raw_digest(triplet_raw[view_name]),
                    normalization_mode="task_definition_projection",
                    codec_version=codec.PROJECTION_CODEC,
                    normalized_digest=codec.canonical_digest(proj_v),
                    return_stage="3C",
                    details={"path": resolver.TRIPLET[view_name], "task_id": task_id, "business_id": vrow["id"]},
                )

        # 5. Record transitive dependency Task projections.
        for dep_tid in transitive_deps:
            dep_proj = _task_projection_bundle(
                dep_tid,
                master_tasks=master_tasks,
                back_by_tid=back_by_tid,
                gameplay_by_tid=gameplay_by_tid,
            )
            dep_norm = codec.canonical_digest(dep_proj)
            items[("dependency_task", f"dependency:task:{dep_tid}")] = _make_item(
                category="dependency_task",
                locator=f"dependency:task:{dep_tid}",
                raw_digest=codec.raw_digest(_json_raw_bytes(dep_proj)),
                normalization_mode="task_definition_projection",
                codec_version=codec.PROJECTION_CODEC,
                normalized_digest=dep_norm,
                return_stage="3C",
                details={"task_id": dep_tid, "direct": dep_tid in direct_deps},
            )

        route = origin["route"]
        if route != "B" and candidate_binding is not None:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="candidate_binding only permitted for route='B' Tasks",
                actual={"route": route, "candidate_binding": candidate_binding},
                resume_ref=candidate_binding,
            )

        if route == "B":
            policy_raw = observations.read(resolver.POLICY_PATH)
            catalog_raw = observations.read(resolver.CATALOG_PATH)
            origins_raw = observations.read(resolver.ORIGINS_PATH)
            policy = codec.strict_json_loads(policy_raw)
            catalog = codec.strict_json_loads(catalog_raw)
            origins = codec.strict_json_loads(origins_raw)

            # Policy projection item (return_stage="5").
            policy_proj = {
                "policy_id": policy["policy_id"],
                "policy_revision": policy["policy_revision"],
                "switch_boundary": policy["switch_boundary"],
                "frozen_a_refs": policy["frozen_a_refs"],
            }
            items[("policy", resolver.POLICY_PATH)] = _make_item(
                category="policy",
                locator=resolver.POLICY_PATH,
                raw_digest=codec.raw_digest(policy_raw),
                normalization_mode="policy_projection",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=codec.canonical_digest(policy_proj),
                return_stage="5",
                details={"policy_id": policy["policy_id"], "policy_revision": policy["policy_revision"]},
            )
            for auth_ref in policy["switch_boundary"]["authority_refs"]:
                if auth_ref["owner"] == "adr":
                    extra_adr_refs.append(auth_ref["ref"])

            # Gather committed applicable plan refs and committed bindings first.
            committed_plan_refs_by_id: dict[str, dict[str, Any]] = {}
            all_plan_refs: dict[str, dict[str, Any]] = {}
            for pref in origin["plan_refs"]:
                committed_plan_refs_by_id[pref["entity_id"]] = pref
                all_plan_refs[pref["entity_id"]] = pref
            for rdef in origin["resolved_definitions"]:
                pref = rdef["plan_ref"]
                all_plan_refs.setdefault(pref["entity_id"], pref)

            effective_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any], bool]] = {}
            for bref in origin["binding_refs"]:
                braw = observations.read(bref["path"])
                bdoc = resolver._load_formal_json(observations, bref)
                mapping = next(
                    (m for m in bdoc["task_mappings"] if m["task_id"] == task_id),
                    None,
                )
                if mapping is None:
                    _fail(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected="task_mapping for queried task_id in active binding",
                        actual=bref["path"],
                        resume_ref=bref["path"],
                    )
                effective_bindings[bdoc["plan_id"]] = (bref, braw, bdoc, mapping, True)

            # Optional explicit candidate binding: single-slot replacement ONLY + full closure recomputation!
            uses_cand = False
            cand_doc_active: dict[str, Any] | None = None
            cand_ref_active: dict[str, Any] | None = None
            if candidate_binding is not None:
                pre_loaded_plans = {
                    pid: resolver._load_formal_json(observations, pref)
                    for pid, pref in sorted(all_plan_refs.items())
                }
                cand_rel, cand_raw, cand_ref, cand_doc, cand_mapping = _validate_and_load_candidate_binding(
                    observations=observations,
                    candidate_binding_path=candidate_binding,
                    task_id=task_id,
                    committed_plan_refs_by_id=committed_plan_refs_by_id,
                    loaded_plans=pre_loaded_plans,
                    catalog=catalog,
                    task_join=task_join,
                )
                effective_bindings[cand_doc["plan_id"]] = (cand_ref, cand_raw, cand_doc, cand_mapping, False)
                uses_cand = True
                cand_doc_active = cand_doc
                cand_ref_active = cand_ref
                result["uses_candidate_binding"] = True
                result["candidate_binding"] = {
                    "path": cand_rel,
                    "plan_id": cand_doc["plan_id"],
                    "binding_revision": cand_doc["binding_revision"],
                    "stage": cand_doc["stage"],
                    "raw_digest": codec.raw_digest(cand_raw),
                    "committed": False,
                }
                (
                    effective_resolved_definitions,
                    effective_dispositions,
                    effective_flow_closure,
                    effective_requirements,
                    owning_scope_ids,
                ) = _recompute_task_closure_for_effective_bindings(
                    observations=observations,
                    catalog=catalog,
                    task_id=task_id,
                    effective_bindings=effective_bindings,
                    all_plan_refs=all_plan_refs,
                )
            else:
                effective_resolved_definitions = deepcopy(origin["resolved_definitions"])
                effective_dispositions = deepcopy(origin["dispositions"])
                effective_flow_closure = list(origin["applicable_flow_closure"])
                effective_requirements = list(origin["applicable_requirements"])
                owning_scope_ids = set(origin["applicable_scope_ids"])

            # Build transitive receipt seal index for clean-clone logs/ verification.
            sealed_digests = _build_receipt_seal_index(
                observations, catalog, sorted(owning_scope_ids)
            )

            # Load all applicable plans (direct + cross-plan owners, including any added by candidate binding).
            loaded_plans: dict[str, tuple[dict[str, Any], bytes, dict[str, Any]]] = {}
            for pid in sorted(all_plan_refs):
                pref = all_plan_refs[pid]
                praw = observations.read(pref["path"])
                pdoc = resolver._load_formal_json(observations, pref)
                loaded_plans[pid] = (pref, praw, pdoc)
                items[("plan", f"plan:{pid}")] = _make_item(
                    category="plan",
                    locator=f"plan:{pid}",
                    raw_digest=codec.raw_digest(praw),
                    normalization_mode="canonical_json",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=codec.canonical_digest(pdoc),
                    return_stage="3B",
                    details={"path": pref["path"], "plan_id": pid, "revision": pdoc["revision"]},
                )
                # Source identity (manifest_ref + ledger_ref + source_revision/source_manifest_digest).
                src_id = pdoc["source_identity"]
                _observe_owned_ref_items(
                    src_id["manifest_ref"],
                    observations=observations,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=True,
                    category="source_manifest",
                    return_stage="3A",
                    committed=True,
                    items=items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )
                _observe_owned_ref_items(
                    src_id["ledger_ref"],
                    observations=observations,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=True,
                    category="source_ledger",
                    return_stage="3A",
                    committed=True,
                    items=items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )
                src_meta = {
                    "plan_id": pid,
                    "source_revision": src_id["source_revision"],
                    "source_manifest_digest": src_id["source_manifest_digest"],
                }
                items[("source_identity", f"source_identity:{pid}")] = _make_item(
                    category="source_identity",
                    locator=f"source_identity:{pid}",
                    raw_digest=codec.raw_digest(_json_raw_bytes(src_meta)),
                    normalization_mode="canonical_json",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=codec.canonical_digest(src_meta),
                    return_stage="3A",
                    details=src_meta,
                )
                # Harvest plan adoption_proof_refs (clean-clone logs/ sealed by ancestor 3B receipts).
                for proof_ref in pdoc.get("adoption_proof_refs", []):
                    _observe_owned_ref_items(
                        proof_ref,
                        observations=observations,
                        sealed_digests=sealed_digests,
                        allow_sealed_logs=True,
                        category="adoption_proof",
                        return_stage="3B",
                        committed=True,
                        items=items,
                        sealed_log_paths=sealed_log_paths,
                        entity_id=entity_id,
                    )

            # Task source_refs from origins_row.
            for sref in origin["source_refs"]:
                _observe_owned_ref_items(
                    sref,
                    observations=observations,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=True,
                    category="source",
                    return_stage="3A",
                    committed=True,
                    items=items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )

            # Task-origins slice (verified full origins by 3.3, slice ONLY this Task, excluding origins.revision).
            origins_row = next((r for r in origins["tasks"] if r["task_id"] == task_id), None)
            if origins_row is None:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="task_id entry in task-origins.v1.json",
                    actual=task_id,
                    resume_ref=resolver.ORIGINS_PATH,
                )
            if uses_cand and cand_doc_active is not None and cand_ref_active is not None:
                slice_binding_refs = [
                    cand_ref_active if bref["entity_id"] == cand_doc_active["plan_id"] else bref
                    for bref in origins_row["binding_refs"]
                ]
            else:
                slice_binding_refs = list(origins_row["binding_refs"])
            origins_slice = {
                "task_id": task_id,
                "source_refs": sorted(origins_row["source_refs"], key=resolver._owned_ref_sort_key),
                "plan_refs": sorted(origins_row["plan_refs"], key=resolver._plan_ref_sort_key),
                "binding_refs": sorted(slice_binding_refs, key=resolver._plan_ref_sort_key),
            }
            binding_stages = [
                bdoc["stage"]
                for (_bref, _braw, bdoc, _mapping, _comm) in effective_bindings.values()
                if bdoc["stage"] in STAGE_RANK
            ]
            origins_stage = max(binding_stages, key=lambda s: STAGE_RANK[s]) if binding_stages else "3C"
            items[("task_origins", f"task_origins:task:{task_id}")] = _make_item(
                category="task_origins",
                locator=f"task_origins:task:{task_id}",
                raw_digest=codec.raw_digest(origins_raw),
                normalization_mode="task_origins_slice",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=codec.canonical_digest(origins_slice),
                return_stage=origins_stage,
                committed=(not uses_cand),
                details={"path": resolver.ORIGINS_PATH, "task_id": task_id, "stage": origins_stage},
            )

            # Recursive resolved_definitions item (return_stage="3B").
            resolved_defs_committed = (not uses_cand) or (
                effective_resolved_definitions == origin["resolved_definitions"]
            )
            items[("resolved_definitions", f"resolved_definitions:task:{task_id}")] = _make_item(
                category="resolved_definitions",
                locator=f"resolved_definitions:task:{task_id}",
                raw_digest=codec.raw_digest(_json_raw_bytes(effective_resolved_definitions)),
                normalization_mode="canonical_json",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=codec.canonical_digest(effective_resolved_definitions),
                return_stage="3B",
                committed=resolved_defs_committed,
                details={"count": len(effective_resolved_definitions)},
            )

            # Process every effective binding (committed + optional single-slot candidate),
            # 3C mappings projection, Stage-4 semantics, contracts/ADRs/overlays, MVG manifests, and other_verification.
            manifest_refs_collected: list[tuple[str, dict[str, Any], bool]] = []
            other_verif_refs_collected: list[tuple[dict[str, Any], bool]] = []
            applicable_flows_from_bindings: set[str] = set(effective_flow_closure)
            applicable_reqs_from_bindings: set[str] = set(effective_requirements)
            applicable_reqs_by_plan: dict[str, set[str]] = {}
            binding_flows_by_plan: dict[str, set[str]] = {}
            flow_peer_task_ids: set[int] = set()

            for disp in effective_dispositions:
                dpid = disp["plan_id"]
                applicable_reqs_by_plan.setdefault(dpid, set()).add(disp["requirement_id"])
                if disp["disposition"] == "flow" and disp.get("flow_id"):
                    binding_flows_by_plan.setdefault(dpid, set()).add(disp["flow_id"])
                for rfid in disp.get("route_flow_ids", []):
                    binding_flows_by_plan.setdefault(dpid, set()).add(rfid)

            for pid in sorted(effective_bindings):
                bref, braw, bdoc, mapping, is_committed = effective_bindings[pid]
                b_stage = bdoc["stage"]
                b_return_stage = b_stage if b_stage in ("3C", "4", "5") else "4"

                items[("binding", f"binding:{pid}")] = _make_item(
                    category="binding",
                    locator=f"binding:{pid}",
                    raw_digest=codec.raw_digest(braw),
                    normalization_mode="canonical_json",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=codec.canonical_digest(bdoc),
                    return_stage=b_return_stage,
                    committed=is_committed,
                    details={
                        "path": bref["path"],
                        "plan_id": pid,
                        "binding_revision": bdoc["binding_revision"],
                        "stage": b_stage,
                    },
                )

                # Dedicated 3C task_mappings structural projection (excludes Stage-5 obligation_ids)
                # so 3C mapping edits inside a Stage-4/5 binding still attribute to return_stage="3C".
                b3c_proj = [
                    {
                        "task_id": m["task_id"],
                        "view_refs": sorted(
                            m["view_refs"],
                            key=lambda v: (v["view"], v["business_id"]),
                        ),
                        "requirement_ids": sorted(m["requirement_ids"]),
                        "flow_ids": sorted(m["flow_ids"]),
                        "part_kinds": sorted(m["part_kinds"]),
                        "roles": sorted(m["roles"]),
                    }
                    for m in sorted(bdoc["task_mappings"], key=lambda r: r["task_id"])
                ]
                items[("binding_3c_mappings", f"binding_3c_mappings:{pid}")] = _make_item(
                    category="binding_3c_mappings",
                    locator=f"binding_3c_mappings:{pid}",
                    raw_digest=codec.raw_digest(_json_raw_bytes(b3c_proj)),
                    normalization_mode="binding_3c_mappings_projection",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=codec.canonical_digest(b3c_proj),
                    return_stage="3C",
                    committed=is_committed,
                    details={"plan_id": pid, "binding_revision": bdoc["binding_revision"]},
                )

                binding_flows_by_plan.setdefault(pid, set()).update(mapping["flow_ids"])
                applicable_flows_from_bindings.update(mapping["flow_ids"])
                applicable_reqs_from_bindings.update(mapping["requirement_ids"])
                applicable_reqs_by_plan.setdefault(pid, set()).update(mapping["requirement_ids"])

                # Stage-4 semantics (clean-clone safe, zero logs/ dependency).
                # Exclude binding_revision, stage, Stage-5 obligations, and task_mappings[].obligation_ids
                # so Stage-5 obligation/manifest changes report return_stage="5" instead of "4".
                if b_stage in ("4", "5"):
                    _pref, _praw, pdoc = loaded_plans[pid]
                    s4_sem = ch4_binding.extract_stage4_semantics(pdoc, bdoc)
                    s4_norm = {
                        k: v
                        for k, v in s4_sem.items()
                        if k not in ("binding_revision", "stage", "obligations", "task_mappings")
                    }
                    s4_norm["task_mappings"] = [
                        {k: v for k, v in m.items() if k != "obligation_ids"}
                        for m in s4_sem.get("task_mappings", [])
                    ]
                    obl_s4_meta = [
                        {"id": o["id"], "stage4_meta": o["stage4_meta"]}
                        for o in s4_sem.get("obligations", [])
                        if o.get("stage4_meta")
                    ]
                    if obl_s4_meta:
                        s4_norm["obligation_stage4_meta"] = obl_s4_meta
                    items[("stage4_semantics", f"stage4_semantics:{pid}")] = _make_item(
                        category="stage4_semantics",
                        locator=f"stage4_semantics:{pid}",
                        raw_digest=codec.raw_digest(_json_raw_bytes(s4_sem)),
                        normalization_mode="stage4_semantics_projection",
                        codec_version=codec.CODEC_VERSION,
                        normalized_digest=codec.canonical_digest(s4_norm),
                        return_stage="4",
                        committed=is_committed,
                        details={"plan_id": pid, "stage": b_stage, "binding_revision": bdoc["binding_revision"]},
                    )

                # Harvest OwnedRefs from implementation_objects, obligations, manifest_refs, other_verification_refs.
                for obj in bdoc["implementation_objects"]:
                    if task_id not in obj["responsible_task_ids"]:
                        continue
                    tref = obj.get("target_ref")
                    if type(tref) is dict:
                        owner = tref["owner"]
                        if owner == "contract":
                            extra_contract_refs.append(tref["ref"])
                        elif owner == "overlay":
                            extra_overlay_refs.append(tref["ref"])
                        elif owner == "adr":
                            extra_adr_refs.append(tref["ref"])
                        else:
                            _observe_owned_ref_items(
                                tref,
                                observations=observations,
                                sealed_digests=sealed_digests,
                                allow_sealed_logs=is_committed,
                                category=f"binding_target:{owner}",
                                return_stage="4",
                                committed=is_committed,
                                items=items,
                                sealed_log_paths=sealed_log_paths,
                                entity_id=entity_id,
                            )

                obl_by_id = {o["id"]: o for o in bdoc["obligations"]}
                for obl_id in mapping["obligation_ids"]:
                    obl = obl_by_id[obl_id]
                    binding_flows_by_plan.setdefault(pid, set()).update(obl["flow_ids"])
                    applicable_flows_from_bindings.update(obl["flow_ids"])
                    applicable_reqs_from_bindings.update(obl["requirement_ids"])
                    applicable_reqs_by_plan.setdefault(pid, set()).update(obl["requirement_ids"])
                    for vref in obl.get("verification_refs", []):
                        v_owner = vref["owner"]
                        if v_owner == "manifest":
                            manifest_refs_collected.append((pid, vref, is_committed))
                        elif v_owner == "other_verification":
                            other_verif_refs_collected.append((vref, is_committed))
                        elif v_owner == "contract":
                            extra_contract_refs.append(vref["ref"])
                        elif v_owner == "overlay":
                            extra_overlay_refs.append(vref["ref"])
                        elif v_owner == "adr":
                            extra_adr_refs.append(vref["ref"])
                        else:
                            _observe_owned_ref_items(
                                vref,
                                observations=observations,
                                sealed_digests=sealed_digests,
                                allow_sealed_logs=is_committed,
                                category="verification_evidence",
                                return_stage="5",
                                committed=is_committed,
                                items=items,
                                sealed_log_paths=sealed_log_paths,
                                entity_id=entity_id,
                            )

                for mref in bdoc.get("manifest_refs", []):
                    manifest_refs_collected.append((pid, mref, is_committed))
                for oref in bdoc.get("other_verification_refs", []):
                    other_verif_refs_collected.append((oref, is_committed))

            # Harvest plan-level dispositions, applicability[].other_verification_refs, and applicable requirement_evidence.
            plan_disp_ev_ids: dict[str, set[str]] = {}
            for disp in effective_dispositions:
                dpid = disp["plan_id"]
                plan_disp_ev_ids.setdefault(dpid, set()).update(disp.get("evidence_ids", []))
                if dpid not in loaded_plans:
                    continue
                _pref, _praw, pdoc = loaded_plans[dpid]
                ev_map = {(r["owner"], r["ref"]): r for r in pdoc["evidence_source_refs"]}
                if disp["disposition"] == "other_verification" and disp["verification_ref"]:
                    eref = ev_map.get(("other_verification", disp["verification_ref"]))
                    if eref is not None:
                        other_verif_refs_collected.append((eref, True))
                elif disp["disposition"] == "deferred" and disp["authority_ref"]:
                    aref = ev_map.get(("authority", disp["authority_ref"]))
                    if aref is not None:
                        _observe_owned_ref_items(
                            aref,
                            observations=observations,
                            sealed_digests=sealed_digests,
                            allow_sealed_logs=True,
                            category="deferred_authority",
                            return_stage="5",
                            committed=True,
                            items=items,
                            sealed_log_paths=sealed_log_paths,
                            entity_id=entity_id,
                        )

            for pid in sorted(loaded_plans):
                _pref, _praw, pdoc = loaded_plans[pid]
                ev_map = {(r["owner"], r["ref"]): r for r in pdoc["evidence_source_refs"]}
                plan_reqs = applicable_reqs_by_plan.get(pid, set())
                for app_row in pdoc.get("applicability", []):
                    if app_row["requirement_id"] in plan_reqs:
                        for oref in app_row.get("other_verification_refs", []):
                            other_verif_refs_collected.append((oref, True))
                req_ev_by_id = {r["evidence_id"]: r for r in pdoc.get("requirement_evidence", [])}
                app_ev_ids = plan_disp_ev_ids.get(pid, set())
                for ev_id in sorted(app_ev_ids):
                    if ev_id not in req_ev_by_id:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            stage=codec.Stage.BUNDLE,
                            entity_id=entity_id,
                            expected="declared requirement_evidence entry matching evidence_id",
                            actual={"plan_id": pid, "evidence_id": ev_id},
                            resume_ref=_pref["path"],
                        )
                for ev_row in pdoc.get("requirement_evidence", []):
                    ev_applicable = (
                        ev_row["evidence_id"] in app_ev_ids
                        or ev_row["requirement_id"] in plan_reqs
                        or bool(set(ev_row.get("flow_ids", [])) & applicable_flows_from_bindings)
                    )
                    if not ev_applicable:
                        continue
                    ev_owned = ev_map.get((ev_row["kind"], ev_row["source_ref"]))
                    if ev_owned is not None:
                        _observe_owned_ref_items(
                            ev_owned,
                            observations=observations,
                            sealed_digests=sealed_digests,
                            allow_sealed_logs=True,
                            category="requirement_evidence",
                            return_stage="5",
                            committed=True,
                            items=items,
                            sealed_log_paths=sealed_log_paths,
                            entity_id=entity_id,
                        )

            # Deduplicate and validate all collected MVG manifests AFTER all _observe_owned_ref_items calls
            # so duplicate manifest_refs never reset normalization_mode to raw_bytes or flip committed=False to True.
            manifest_temp_items: dict[tuple[str, str], dict[str, Any]] = {}
            manifest_obs_by_rel: dict[str, tuple[bytes, str]] = {}
            manifest_committed_by_rel: dict[str, list[bool]] = {}
            binding_manifest_paths_by_plan: dict[str, set[str]] = {}
            for m_pid, mref, is_committed in manifest_refs_collected:
                obs_list = _observe_owned_ref_items(
                    mref,
                    observations=observations,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=False,
                    category="mvg_manifest",
                    return_stage="5",
                    committed=is_committed,
                    items=manifest_temp_items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )
                for m_rel, m_raw, m_raw_dg in obs_list:
                    if m_raw is None:
                        continue
                    manifest_obs_by_rel.setdefault(m_rel, (m_raw, m_raw_dg))
                    manifest_committed_by_rel.setdefault(m_rel, []).append(bool(is_committed))
                    binding_manifest_paths_by_plan.setdefault(m_pid, set()).add(m_rel)

            covered_manifest_flows: set[str] = set()
            manifest_flows_by_rel: dict[str, set[str]] = {}
            for m_rel in sorted(manifest_obs_by_rel):
                m_raw, m_raw_dg = manifest_obs_by_rel[m_rel]
                combined_committed = all(manifest_committed_by_rel[m_rel])
                m_doc, m_sha = _validate_mvg_manifest_decoupled(
                    root=root_path,
                    manifest_rel=m_rel,
                    manifest_raw=m_raw,
                    observations=observations,
                    master_tasks=master_tasks,
                    entity_id=entity_id,
                )
                m_norm_payload = {
                    "manifest_sha256": m_sha,
                    "document": m_doc,
                }
                items[("mvg_manifest", m_rel)] = _make_item(
                    category="mvg_manifest",
                    locator=m_rel,
                    raw_digest=m_raw_dg,
                    normalization_mode="mvg_manifest_normalized",
                    codec_version=codec.CODEC_VERSION,
                    normalized_digest=codec.canonical_digest(m_norm_payload),
                    return_stage="5",
                    committed=combined_committed,
                    details={
                        "path": m_rel,
                        "mvg_id": m_doc["mvg_id"],
                        "manifest_sha256": m_sha,
                        "flow_ids": [f["id"] for f in m_doc["flows"]],
                    },
                )
                m_flow_set: set[str] = set()
                for flow in m_doc["flows"]:
                    m_flow_set.add(flow["id"])
                    covered_manifest_flows.add(flow["id"])
                    if flow["id"] in applicable_flows_from_bindings:
                        for ftid in flow["task_ids"]:
                            if ftid != task_id:
                                flow_peer_task_ids.add(ftid)
                        for edge in flow["handoffs"]:
                            extra_contract_refs.append(edge["contract_ref"])
                            for role_key in ("producer_task", "consumer_task", "owner_task"):
                                etid = edge[role_key]
                                if etid != task_id:
                                    flow_peer_task_ids.add(etid)
                manifest_flows_by_rel[m_rel] = m_flow_set

            # Per-binding Stage-5 Flow coverage check (multi-plan Stage-5 non-Flow + Stage-4 Flow allowed).
            for pid in sorted(effective_bindings):
                bref, _braw, bdoc, _mapping, _is_comm = effective_bindings[pid]
                b_stage = bdoc["stage"]
                b_flows = binding_flows_by_plan.get(pid, set())
                b_has_flow_disp = any(
                    d["plan_id"] == pid and d["disposition"] == "flow"
                    for d in effective_dispositions
                )
                b_mpaths = binding_manifest_paths_by_plan.get(pid, set())
                if b_stage == "5" and (b_has_flow_disp or b_flows) and not b_mpaths:
                    _fail(
                        codec.ReasonCode.UNRESOLVED_REFERENCE,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected="at least one valid MVG manifest_ref for Stage-5 Flow-disposed binding",
                        actual={"plan_id": pid, "applicable_flows": sorted(b_flows)},
                        resume_ref=bref["path"],
                    )
                if b_mpaths and b_flows:
                    b_covered = set().union(*(manifest_flows_by_rel.get(p, set()) for p in b_mpaths))
                    missing_flows = sorted(b_flows - b_covered)
                    if missing_flows:
                        _fail(
                            codec.ReasonCode.MAPPING_MISMATCH,
                            stage=codec.Stage.BUNDLE,
                            entity_id=entity_id,
                            expected="every applicable flow covered by bound MVG manifest(s)",
                            actual={
                                "plan_id": pid,
                                "missing_flows": missing_flows,
                                "covered_flows": sorted(b_covered),
                            },
                            resume_ref=sorted(b_mpaths)[0],
                        )

            # Validate all collected other_verification refs.
            for oref, is_committed in other_verif_refs_collected:
                _observe_owned_ref_items(
                    oref,
                    observations=observations,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=is_committed,
                    category="other_verification",
                    return_stage="5",
                    committed=is_committed,
                    items=items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )

            # Cross-plan dependency / producer projections for dependency tasks and Flow handoff peers.
            catalog_task_by_id = {r["task_id"]: r for r in catalog["task_index"]}
            related_peer_ids = sorted((set(transitive_deps) | flow_peer_task_ids) - {task_id})
            for peer_tid in related_peer_ids:
                if peer_tid not in transitive_deps:
                    peer_proj = _task_projection_bundle(
                        peer_tid,
                        master_tasks=master_tasks,
                        back_by_tid=back_by_tid,
                        gameplay_by_tid=gameplay_by_tid,
                    )
                    items[("flow_peer_task", f"flow_peer:task:{peer_tid}")] = _make_item(
                        category="flow_peer_task",
                        locator=f"flow_peer:task:{peer_tid}",
                        raw_digest=codec.raw_digest(_json_raw_bytes(peer_proj)),
                        normalization_mode="task_definition_projection",
                        codec_version=codec.PROJECTION_CODEC,
                        normalized_digest=codec.canonical_digest(peer_proj),
                        return_stage="3C",
                        details={"task_id": peer_tid},
                    )
                peer_cat = catalog_task_by_id.get(peer_tid)
                if peer_cat is not None:
                    peer_bindings_proj: list[dict[str, Any]] = []
                    peer_max_stage = "3C"
                    peer_uses_cand = False
                    seen_peer_plans: set[str] = set()
                    for pbref in sorted(peer_cat["binding_refs"], key=resolver._plan_ref_sort_key):
                        if cand_doc_active is not None and pbref["entity_id"] == cand_doc_active["plan_id"]:
                            pbdoc = cand_doc_active
                            peer_uses_cand = True
                            b_is_comm = False
                        else:
                            pbdoc = resolver._load_formal_json(observations, pbref)
                            b_is_comm = True
                        seen_peer_plans.add(pbdoc["plan_id"])
                        pmap = next((m for m in pbdoc["task_mappings"] if m["task_id"] == peer_tid), None)
                        pobjs = [o for o in pbdoc["implementation_objects"] if peer_tid in o["responsible_task_ids"]]
                        for obj in pobjs:
                            tref = obj.get("target_ref")
                            if type(tref) is dict:
                                owner = tref["owner"]
                                if owner == "contract":
                                    extra_contract_refs.append(tref["ref"])
                                elif owner == "overlay":
                                    extra_overlay_refs.append(tref["ref"])
                                elif owner == "adr":
                                    extra_adr_refs.append(tref["ref"])
                                else:
                                    _observe_owned_ref_items(
                                        tref,
                                        observations=observations,
                                        sealed_digests=sealed_digests,
                                        allow_sealed_logs=b_is_comm,
                                        category=f"binding_target:{owner}",
                                        return_stage="4",
                                        committed=b_is_comm,
                                        items=items,
                                        sealed_log_paths=sealed_log_paths,
                                        entity_id=entity_id,
                                    )
                        if pbdoc["stage"] in STAGE_RANK and STAGE_RANK[pbdoc["stage"]] > STAGE_RANK[peer_max_stage]:
                            peer_max_stage = pbdoc["stage"]
                        peer_bindings_proj.append(
                            {
                                "plan_ref": pbdoc["plan_ref"],
                                "task_mapping": pmap,
                                "implementation_objects": pobjs,
                            }
                        )
                    if (
                        cand_doc_active is not None
                        and cand_doc_active["plan_id"] not in seen_peer_plans
                        and any(m["task_id"] == peer_tid for m in cand_doc_active["task_mappings"])
                    ):
                        peer_uses_cand = True
                        pmap = next(m for m in cand_doc_active["task_mappings"] if m["task_id"] == peer_tid)
                        pobjs = [
                            o for o in cand_doc_active["implementation_objects"] if peer_tid in o["responsible_task_ids"]
                        ]
                        for obj in pobjs:
                            tref = obj.get("target_ref")
                            if type(tref) is dict:
                                owner = tref["owner"]
                                if owner == "contract":
                                    extra_contract_refs.append(tref["ref"])
                                elif owner == "overlay":
                                    extra_overlay_refs.append(tref["ref"])
                                elif owner == "adr":
                                    extra_adr_refs.append(tref["ref"])
                                else:
                                    _observe_owned_ref_items(
                                        tref,
                                        observations=observations,
                                        sealed_digests=sealed_digests,
                                        allow_sealed_logs=False,
                                        category=f"binding_target:{owner}",
                                        return_stage="4",
                                        committed=False,
                                        items=items,
                                        sealed_log_paths=sealed_log_paths,
                                        entity_id=entity_id,
                                    )
                        if (
                            cand_doc_active["stage"] in STAGE_RANK
                            and STAGE_RANK[cand_doc_active["stage"]] > STAGE_RANK[peer_max_stage]
                        ):
                            peer_max_stage = cand_doc_active["stage"]
                        peer_bindings_proj.append(
                            {
                                "plan_ref": cand_doc_active["plan_ref"],
                                "task_mapping": pmap,
                                "implementation_objects": pobjs,
                            }
                        )
                    prod_payload = {
                        "task_id": peer_tid,
                        "plan_refs": sorted(peer_cat["plan_refs"], key=resolver._plan_ref_sort_key),
                        "bindings": peer_bindings_proj,
                    }
                    items[("dependency_producer", f"dependency_producer:task:{peer_tid}")] = _make_item(
                        category="dependency_producer",
                        locator=f"dependency_producer:task:{peer_tid}",
                        raw_digest=codec.raw_digest(_json_raw_bytes(prod_payload)),
                        normalization_mode="dependency_producer_projection",
                        codec_version=codec.CODEC_VERSION,
                        normalized_digest=codec.canonical_digest(prod_payload),
                        return_stage=peer_max_stage,
                        committed=(not peer_uses_cand),
                        details={"task_id": peer_tid},
                    )

            # Compute normalized portable business scope IDs strictly via op_scope.resource_scopes(...)
            # (never passing raw uppercase plan_id strings into op_scope._scopes / business_guard).
            command_ids = sorted(
                r["definition_id"] for r in effective_resolved_definitions if r["kind"] == "command"
            )
            state_ids = sorted(
                r["definition_id"] for r in effective_resolved_definitions if r["kind"] == "state"
            )
            scope_ids_set.update(
                op_scope.resource_scopes(
                    task_ids=sorted({task_id, *transitive_deps, *flow_peer_task_ids}),
                    plan_ids=sorted(all_plan_refs),
                    requirement_ids=sorted(applicable_reqs_from_bindings),
                    flow_ids=sorted(applicable_flows_from_bindings),
                    command_ids=command_ids,
                    state_ids=state_ids,
                )
            )
        elif route == "A":
            policy_raw = observations.read(resolver.POLICY_PATH)
            policy = codec.strict_json_loads(policy_raw)
            origins_raw = observations.read(resolver.ORIGINS_PATH, optional=True)
            if origins_raw is not None:
                origins_doc = codec.strict_json_loads(origins_raw)
                if type(origins_doc) is dict:
                    for lref in origins_doc.get("frozen_legacy_refs", []):
                        preflight.owned(lref, observations)
            observations.read(resolver.CHAPTER3_TASK_SCOPE, optional=True)
            policy_proj = {
                "policy_id": policy["policy_id"],
                "policy_revision": policy["policy_revision"],
                "switch_boundary": policy["switch_boundary"],
                "frozen_a_refs": policy["frozen_a_refs"],
            }
            items[("policy", resolver.POLICY_PATH)] = _make_item(
                category="policy",
                locator=resolver.POLICY_PATH,
                raw_digest=codec.raw_digest(policy_raw),
                normalization_mode="policy_projection",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=codec.canonical_digest(policy_proj),
                return_stage="5",
                details={"policy_id": policy["policy_id"], "policy_revision": policy["policy_revision"]},
            )
            for fref in policy["frozen_a_refs"]:
                _observe_owned_ref_items(
                    fref,
                    observations=observations,
                    sealed_digests={},
                    allow_sealed_logs=False,
                    category="frozen_a",
                    return_stage="3B",
                    committed=True,
                    items=items,
                    sealed_log_paths=sealed_log_paths,
                    entity_id=entity_id,
                )
                ref_path = fref["ref"].partition("#")[0]
                if ref_path.endswith(".json"):
                    fdoc = codec.strict_json_loads(observations.read(ref_path))
                    snap_path = None
                    if type(fdoc) is dict and fdoc.get("schema_version") == protection.SCHEMA:
                        snap_path = ref_path
                    elif type(fdoc) is dict and fdoc.get("document_version") == preflight.PROTECTION_VERSION:
                        snap_ref = fdoc.get("snapshot_ref")
                        if type(snap_ref) is dict:
                            snap_path = snap_ref["ref"].partition("#")[0]
                    if snap_path is not None:
                        observations.read(snap_path)
                        snapshot, _rep, _raws = protection._load_snapshot(root_path, snap_path)
                        parent = snap_path.rsplit("/", 1)[0] + "/" if "/" in snap_path else ""
                        observations.read(parent + "inventory.json")
                        observations.read(parent + "report.json", optional=True)
                        for raw_row in snapshot["raw_files"]:
                            if raw_row.get("exists") is True and raw_row.get("artifact"):
                                observations.read(parent + raw_row["artifact"])
                        cand = next(
                            (c for c in snapshot["frozen_a"]["candidates"] if c["task_id"] == task_id),
                            None,
                        )
                        if cand is not None:
                            s_scope = cand.get("source_scope", {})
                            ss = s_scope.get("source_set", {})
                            if type(ss) is dict and ss.get("path"):
                                ss_raw = observations.read(ss["path"], optional=True)
                                if ss_raw is not None:
                                    ss_dg = codec.raw_digest(ss_raw)
                                    items[("source", ss["path"])] = _make_item(
                                        category="source",
                                        locator=ss["path"],
                                        raw_digest=ss_dg,
                                        normalization_mode="raw_bytes",
                                        codec_version=codec.CODEC_VERSION,
                                        normalized_digest=ss_dg,
                                        return_stage="3A",
                                        details={"path": ss["path"]},
                                    )
                            for sref in s_scope.get("task_source_references", []):
                                if type(sref) is dict and sref.get("path"):
                                    s_raw = observations.read(sref["path"])
                                    s_dg = codec.raw_digest(s_raw)
                                    items[("source", sref["path"])] = _make_item(
                                        category="source",
                                        locator=sref["path"],
                                        raw_digest=s_dg,
                                        normalization_mode="raw_bytes",
                                        codec_version=codec.CODEC_VERSION,
                                        normalized_digest=s_dg,
                                        return_stage="3A",
                                        details={"path": sref["path"]},
                                    )
            scope_ids_set.update(op_scope.resource_scopes(task_ids=sorted({task_id, *transitive_deps})))
        else:
            # explicit_not_enabled_a
            adr_raw = observations.read(resolver.ADR_0040)
            adr_dg = codec.raw_digest(adr_raw)
            items[("authority", resolver.ADR_0040)] = _make_item(
                category="authority",
                locator=resolver.ADR_0040,
                raw_digest=adr_dg,
                normalization_mode="raw_bytes",
                codec_version=codec.CODEC_VERSION,
                normalized_digest=adr_dg,
                return_stage="5",
                details={"path": resolver.ADR_0040},
            )
            scope_ids_set.update(op_scope.resource_scopes(task_ids=sorted({task_id, *transitive_deps})))

        # Verify unapplied pending operations against the FULL computed business_scopes
        # (including transitive_deps, flow_peer_task_ids, and any candidate-discovered scopes).
        resolver._check_unapplied_overlap(
            unapplied_ops,
            task_business_scopes=scope_ids_set,
            owning_scope_ids=owning_scope_ids,
        )

        # 6. Collect ADRs, Overlays, and Game.Core/Contracts/** from Task rows + transitive_deps + bindings + manifests.
        task_rows_for_refs = [
            master_row,
            *back_by_tid.get(task_id, []),
            *gameplay_by_tid.get(task_id, []),
        ]
        for dep_tid in transitive_deps:
            task_rows_for_refs.append(master_tasks[dep_tid])
            task_rows_for_refs.extend(back_by_tid.get(dep_tid, []))
            task_rows_for_refs.extend(gameplay_by_tid.get(dep_tid, []))
        _collect_task_adrs_overlays_contracts(
            root=root_path,
            observations=observations,
            task_rows=task_rows_for_refs,
            extra_adr_refs=extra_adr_refs,
            extra_overlay_refs=extra_overlay_refs,
            extra_contract_refs=extra_contract_refs,
            items=items,
            entity_id=entity_id,
        )

        # 7. Record codec & environment/rules items.
        _collect_environment_items(items)

        # Finalize sorted items and compute canonical input_set_digest.
        sorted_items = [items[key] for key in sorted(items)]
        digest = compute_input_set_digest(
            task_id=task_id,
            route=route,
            uses_candidate_binding=result["uses_candidate_binding"],
            items=sorted_items,
        )
        result["items"] = sorted_items
        result["input_set_digest"] = digest
        result["valid_input_set"] = True
        result["scope_ids"] = sorted(s for s in scope_ids_set if s != op_scope.WRITER_SCOPE)
        result["clean_clone_sealed_logs"] = sorted(sealed_log_paths)

        # 8. Optional baseline comparison.
        if baseline_arg is not None:
            if type(baseline_arg) is dict:
                baseline_doc = _validate_baseline_doc(
                    baseline_arg, expected_task_id=task_id, resume_ref=None
                )
            else:
                b_rel = preflight.path(str(baseline_arg))
                b_raw = observations.read(b_rel)
                baseline_doc = _validate_baseline_doc(
                    codec.strict_json_loads(b_raw),
                    expected_task_id=task_id,
                    resume_ref=b_rel,
                )
            cmp_res = compare_input_sets(baseline_doc, result)
            result["freshness"] = {
                "compared": True,
                "fresh": cmp_res["fresh"],
                "status": cmp_res["status"],
                "baseline_digest": cmp_res["baseline_digest"],
                "current_digest": cmp_res["current_digest"],
                "return_stage": cmp_res["return_stage"],
                "invalidated_items": cmp_res["invalidated_items"],
            }
            result["return_stage"] = cmp_res["return_stage"]
            if cmp_res["fresh"]:
                result["ok"] = True
            else:
                result["ok"] = False
                result["diagnostics"].extend(cmp_res["diagnostics"])
        else:
            result["ok"] = True

    except codec.CodecError as error:
        diag_dict = error.diagnostic.to_dict()
        if diag_dict.get("entity_id") is None:
            diag_dict["entity_id"] = entity_id
        result["ok"] = False
        result["valid_input_set"] = False
        result["input_set_digest"] = None
        result["diagnostics"].append(diag_dict)
        result["return_stage"] = _stage_for_diag(diag_dict)
        if diag_dict.get("reason_code") == codec.ReasonCode.DIGEST_CYCLE.value:
            result["return_stage"] = "3C"
        elif diag_dict.get("reason_code") == codec.ReasonCode.UNKNOWN_ENTITY.value:
            result["return_stage"] = "3C"
        if diag_dict.get("reason_code") == codec.ReasonCode.FILE_CHANGED.value:
            result["stable"] = False
            return result, True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        result["ok"] = False
        result["valid_input_set"] = False
        result["input_set_digest"] = None
        result["diagnostics"].append(
            _diag(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="complete readable InputSet inputs",
                actual=f"{type(error).__name__}: {error}",
            )
        )

    # Final double-read drift check without creating any lock or directory.
    if before_reread is not None:
        before_reread()
    drift = observations.finish()
    if initial_graph_bytes is not None:
        try:
            final_graph = journal.operation_state_graph(observations.root)
            if final_graph["local_bytes"] != initial_graph_bytes:
                drift.append(
                    _diag(
                        codec.ReasonCode.FILE_CHANGED,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected="unchanged operation_state_graph during read-only InputSet resolution",
                        actual="operation store changed during InputSet resolution",
                        resume_ref=resolver.OP_STORE,
                    )
                )
        except codec.CodecError as error:
            drift.append(error.diagnostic.to_dict())
        except (OSError, ValueError, RuntimeError) as error:
            drift.append(
                _diag(
                    codec.ReasonCode.FILE_CHANGED,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="stable operation_state_graph during InputSet resolution",
                    actual=type(error).__name__,
                    resume_ref=resolver.OP_STORE,
                )
            )

    if drift:
        old_diags = list(result["diagnostics"])
        result = _base_result(task_id, operation, lock_mode=lock_mode)
        result["diagnostics"] = [*old_diags, *drift]
        result["stable"] = False
        result["ok"] = False
        return result, True

    result["stable"] = True
    return result, False


def resolve_input_set(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    candidate_binding: str | Path | None = None,
    baseline: dict[str, Any] | str | Path | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    before_reread: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Pure read-only zero-write InputSet resolver with bounded re-read against transient drift."""
    validated_tid: int | None = None
    validated_op: str | None = None
    try:
        root_path = resolver._validate_root(Path(root))
        validated_tid = codec.validate_task_id(task_id)
        validated_op = resolver._validate_operation(operation)
        attempts_limit = _validate_max_attempts(max_attempts)
        cand_str: str | None = None
        if candidate_binding is not None:
            cand_raw_str = str(candidate_binding).replace("\\", "/")
            cand_str = preflight.path(cand_raw_str)
    except codec.CodecError as error:
        res = _base_result(validated_tid, validated_op, lock_mode="none")
        diag = error.diagnostic.to_dict()
        if diag.get("entity_id") is None and validated_tid is not None:
            diag["entity_id"] = str(validated_tid)
        res["diagnostics"].append(diag)
        return res

    last_result = _base_result(validated_tid, validated_op, lock_mode="none")
    for attempt in range(1, attempts_limit + 1):
        hook: Callable[[], None] | None = None
        if before_reread is not None:
            def _run_hook(_a: int = attempt) -> None:
                try:
                    before_reread(_a)
                except TypeError:
                    before_reread()
            hook = _run_hook

        res, is_drift = _resolve_once(
            root_path=root_path,
            task_id=validated_tid,
            operation=validated_op,
            candidate_binding=cand_str,
            baseline_arg=baseline,
            lock_mode="none",
            before_reread=hook,
        )
        res["read_attempts"] = attempt
        last_result = res
        if not is_drift:
            break

    # Re-assert mandatory non-authorization invariants.
    for key, val in AUTHORIZATION_FLAGS.items():
        last_result[key] = val
    last_result["authorization"] = dict(AUTHORIZATION_FLAGS)
    return last_result


def _apply_baseline_to_result(
    root_path: Path,
    task_id: int,
    result: dict[str, Any],
    baseline_arg: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    """Evaluate a user-supplied baseline against a verified InputSet result via compare_input_sets."""
    if type(baseline_arg) is dict:
        baseline_doc = _validate_baseline_doc(
            baseline_arg, expected_task_id=task_id, resume_ref=None
        )
    else:
        obs = preflight.Observations(root_path)
        b_rel = preflight.path(str(baseline_arg))
        b_raw = obs.read(b_rel)
        baseline_doc = _validate_baseline_doc(
            codec.strict_json_loads(b_raw),
            expected_task_id=task_id,
            resume_ref=b_rel,
        )
        drift = obs.finish()
        if drift:
            first = drift[0]
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode(first["reason_code"]),
                    codec.Stage(first["stage"]) if first.get("stage") else codec.Stage.BUNDLE,
                    first.get("entity_id") or str(task_id),
                    first.get("expected"),
                    first.get("actual"),
                    first.get("resume_ref"),
                )
            )
    cmp_res = compare_input_sets(baseline_doc, result)
    result["freshness"] = {
        "compared": True,
        "fresh": cmp_res["fresh"],
        "status": cmp_res["status"],
        "baseline_digest": cmp_res["baseline_digest"],
        "current_digest": cmp_res["current_digest"],
        "return_stage": cmp_res["return_stage"],
        "invalidated_items": cmp_res["invalidated_items"],
    }
    result["return_stage"] = cmp_res["return_stage"]
    if cmp_res["fresh"]:
        result["ok"] = True
    else:
        result["ok"] = False
        result["diagnostics"].extend(cmp_res["diagnostics"])
    return result


@dataclass
class GuardedInputSetHandle:
    """Active handle yielded by ``guarded_input_set`` holding only business scope leases."""

    root: Path
    task_id: int
    operation: str | None
    candidate_binding: str | None
    snapshot: dict[str, Any]
    scope_ids: tuple[str, ...]
    baseline: dict[str, Any] | str | Path | None = None
    lock_mode: str = "scope"
    uses_global_writer_lock: bool = False

    @property
    def input_set_digest(self) -> str:
        return self.snapshot["input_set_digest"]

    def revalidate(self) -> dict[str, Any]:
        """Revalidate under the active business-scope lease; fail closed on pending, drift, or staleness."""
        current = resolve_input_set(
            self.root,
            self.task_id,
            operation=self.operation,
            candidate_binding=self.candidate_binding,
            baseline=None,
            max_attempts=1,
        )
        current["lock_mode"] = self.lock_mode
        current["uses_global_writer_lock"] = False
        if not current["ok"] or not current["stable"]:
            first_diag = current["diagnostics"][0] if current["diagnostics"] else None
            if first_diag is not None:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode(first_diag["reason_code"]),
                        codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        first_diag.get("entity_id"),
                        first_diag.get("expected"),
                        first_diag.get("actual"),
                        first_diag.get("resume_ref"),
                    )
                )
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(self.task_id),
                expected=self.input_set_digest,
                actual=current.get("input_set_digest"),
            )
        if current["input_set_digest"] != self.input_set_digest:
            cmp_snap = compare_input_sets(self.snapshot, current)
            first_diag = cmp_snap["diagnostics"][0] if cmp_snap["diagnostics"] else None
            if first_diag is not None:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode(first_diag["reason_code"]),
                        codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        first_diag.get("entity_id"),
                        first_diag.get("expected"),
                        first_diag.get("actual"),
                        first_diag.get("resume_ref"),
                    )
                )
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(self.task_id),
                expected=self.input_set_digest,
                actual=current["input_set_digest"],
            )
        if tuple(current["scope_ids"]) != self.scope_ids:
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(self.task_id),
                expected=list(self.scope_ids),
                actual=current["scope_ids"],
            )
        if self.baseline is not None:
            _apply_baseline_to_result(self.root, self.task_id, current, self.baseline)
        return current


@contextmanager
def guarded_input_set(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    candidate_binding: str | Path | None = None,
    baseline: dict[str, Any] | str | Path | None = None,
    operation_id: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    before_enter_revalidate: Callable[[], None] | None = None,
) -> Iterator[GuardedInputSetHandle]:
    """Acquire ONLY business-scope leases (review_only=True, no global writer lock) and revalidate on entry."""
    root_path = resolver._validate_root(Path(root))
    validated_tid = codec.validate_task_id(task_id)
    validated_op = resolver._validate_operation(operation)
    attempts_limit = _validate_max_attempts(max_attempts)
    if operation_id is not None:
        codec.validate_business_id(operation_id)
    cand_str = (
        preflight.path(str(candidate_binding).replace("\\", "/"))
        if candidate_binding is not None
        else None
    )

    # 1. Resolve read-only with baseline=None before locking to discover exact business scopes.
    initial = resolve_input_set(
        root_path,
        validated_tid,
        operation=validated_op,
        candidate_binding=cand_str,
        baseline=None,
        max_attempts=attempts_limit,
    )
    if not initial["ok"] or not initial["stable"] or not initial["valid_input_set"]:
        first_diag = initial["diagnostics"][0] if initial["diagnostics"] else None
        if first_diag is not None:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode(first_diag["reason_code"]),
                    codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                    first_diag.get("entity_id"),
                    first_diag.get("expected"),
                    first_diag.get("actual"),
                    first_diag.get("resume_ref"),
                )
            )
        _fail(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            stage=codec.Stage.BUNDLE,
            entity_id=str(validated_tid),
            expected="valid InputSet prior to acquiring business scope guard",
            actual=initial.get("route"),
        )

    scope_ids = tuple(s for s in initial["scope_ids"] if s != op_scope.WRITER_SCOPE)
    if not scope_ids:
        scope_ids = op_scope.resource_scopes(task_ids=[validated_tid])

    # 2. Acquire ONLY business scope leases (operation_id=None, review_only=True; never acquires writer:planning).
    try:
        guard_cm = op_scope.business_guard(
            root_path,
            scope_ids,
            operation_id=None,
            review_only=True,
        )
        guard_cm.__enter__()
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(validated_tid),
            expected="available business scope lease",
            actual=f"{type(error).__name__}: {error}",
            resume_ref=resolver.OP_STORE,
        )

    exc_info: tuple[Any, Any, Any] = (None, None, None)
    try:
        if before_enter_revalidate is not None:
            before_enter_revalidate()
        # 3. Revalidate internal snapshot consistency immediately upon entering the lease (baseline=None).
        entered = resolve_input_set(
            root_path,
            validated_tid,
            operation=validated_op,
            candidate_binding=cand_str,
            baseline=None,
            max_attempts=1,
        )
        entered["lock_mode"] = "scope"
        entered["uses_global_writer_lock"] = False
        if not entered["ok"] or not entered["stable"]:
            first_diag = entered["diagnostics"][0] if entered["diagnostics"] else None
            if first_diag is not None:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode(first_diag["reason_code"]),
                        codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        first_diag.get("entity_id"),
                        first_diag.get("expected"),
                        first_diag.get("actual"),
                        first_diag.get("resume_ref"),
                    )
                )
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected=initial["input_set_digest"],
                actual=entered.get("input_set_digest"),
            )
        if entered["input_set_digest"] != initial["input_set_digest"]:
            cmp_entry = compare_input_sets(initial, entered)
            first_diag = cmp_entry["diagnostics"][0] if cmp_entry["diagnostics"] else None
            if first_diag is not None:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode(first_diag["reason_code"]),
                        codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        first_diag.get("entity_id"),
                        first_diag.get("expected"),
                        first_diag.get("actual"),
                        first_diag.get("resume_ref"),
                    )
                )
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected=initial["input_set_digest"],
                actual=entered["input_set_digest"],
            )
        if tuple(entered["scope_ids"]) != scope_ids:
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected={"digest": initial["input_set_digest"], "scope_ids": list(scope_ids)},
                actual={"digest": entered["input_set_digest"], "scope_ids": entered["scope_ids"]},
            )
        handle = GuardedInputSetHandle(
            root=root_path,
            task_id=validated_tid,
            operation=validated_op,
            candidate_binding=cand_str,
            snapshot=entered,
            scope_ids=scope_ids,
            baseline=baseline,
            lock_mode="scope",
            uses_global_writer_lock=False,
        )
        yield handle
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        try:
            guard_cm.__exit__(*exc_info)
        except codec.CodecError:
            if exc_info[0] is None:
                raise
        except (OSError, ValueError) as error:
            if exc_info[0] is None:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(validated_tid),
                    expected="clean business scope lease release",
                    actual=f"{type(error).__name__}: {error}",
                    resume_ref=resolver.OP_STORE,
                )


def write_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> str:
    """Explicit opt-in report writer under logs/ci/; never overwrites existing files."""
    return resolver.write_report(root, report_rel, payload)
