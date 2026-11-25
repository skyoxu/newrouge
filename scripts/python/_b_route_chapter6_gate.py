"""Unified B-route Chapter 6 execution gate, verified scope leases, and write guards.

Responsibilities:
- Strict ASCII positive-integer task_id validation (rejects non-ASCII digits such as "¹").
- Reuse Story 3.7 detect_repo_b_route_presence (excluding docs/planning/b-route/schemas/**).
- Unified gate decision across CLI, direct Chapter 6 orchestrator, _mvg_obligations, and
  Code Map internal scripts:
  - Story 3.3 resolve_task_origin (B | A | explicit_not_enabled_a | blocked)
  - Story 3.5 resolve_input_set + guarded_input_set (business-scope leases only; never
    holding writer:planning during long model/test runs)
  - Story 3.6 committed stage="5" bindings (Flow with valid manifest & three obligation
    categories, OR zero-MVG-impact non-Flow with 3B applicability rationale,
    adoption_proof_refs, and live other_verification_refs; surfaces
    requires_chapter6_reverification=True for old done Tasks with new obligations/planned
    tests; rejects mvg:N/A labels or missing/stale manifests with return_stage="5")
  - Story 3.7 verify_b_route_chapter5_readiness (ok, fresh, closure_allowed,
    input_set_digest, applicable_set_digest, scope_ids)
  - Frozen A verification against policy.frozen_a_refs + original A Chapter 5 readiness +
    legacy _mvg_obligations; clean explicit_not_enabled_a passthrough.
- Parent-to-child lease reentrancy without Windows msvcrt.locking self-deadlock AND
  without trusting spoofed environment variables (cryptographic secret SHA-256 + safe
  contained receipt path + live owner_pid + OS non-blocking coordinator_lock probe on
  every claimed scope_id).
- Protected Taskmaster status writes (short scope_guard over tasks.json sole authority,
  verifying protection.task_definition_projection before == after) and test_refs sync guard.
- Deterministic JSONL observability events under logs/ci/.../chapter6-gate-events.jsonl.
- Invariants: runtime_verified=False and default_b_enabled=False unconditionally.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Iterator
import uuid

import _b_route_chapter5_readiness as ch5_b
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _planning_apply_journal as journal
import _b_route_operation_leases as op_leases
import _b_route_operation_scope as op_scope
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_stage5_obligations as stage5_obls
import _b_route_task_resolver as task_resolver
from _mvg_capability_checkpoint import coordinator_lock


SCHEMA = "newrouge.b-route-chapter6-execution-gate.v1"
EVENT_SCHEMA = "newrouge.b-route-chapter6-gate-event.v1"
LEASE_RECEIPT_SCHEMA = "newrouge.b-route-chapter6-lease-receipt.v1"
LEASE_DIR = "logs/ci/b-route-chapter6-leases"
DEFAULT_EVENTS_DIR = "logs/ci/b-route-chapter6-gate"

ENV_LEASE_PATH = "NEWROGUE_B_ROUTE_CH6_LEASE_PATH"
ENV_LEASE_SECRET = "NEWROGUE_B_ROUTE_CH6_LEASE_SECRET"

STRICT_TASK_ID_RE = re.compile(r"^[1-9][0-9]*$", re.ASCII)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.ASCII)

VALID_EVENT_KINDS = frozenset(
    {
        "execution",
        "reuse",
        "rework",
        "blocked_gate",
        "boundary_drift_stopped",
    }
)

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

STAGE_RANK = input_set.STAGE_RANK


class Chapter6GateBlockedError(codec.CodecError):
    """Raised when the unified Chapter 6 execution gate blocks execution or detects drift."""

    def __init__(self, gate_result: dict[str, Any]):
        self.gate_result = deepcopy(gate_result)
        diags = gate_result.get("diagnostics") or []
        if diags and isinstance(diags[0], dict):
            first = diags[0]
            try:
                rc = codec.ReasonCode(first["reason_code"])
            except Exception:
                rc = codec.ReasonCode.CONFLICT
            try:
                st = codec.Stage(first["stage"]) if first.get("stage") else codec.Stage.BUNDLE
            except Exception:
                st = codec.Stage.BUNDLE
            diag = codec.Diagnostic(
                rc,
                st,
                first.get("entity_id"),
                first.get("expected"),
                first.get("actual"),
                first.get("resume_ref"),
            )
        else:
            rstage = gate_result.get("return_stage") or "5"
            diag = codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                str(gate_result.get("task_id")) if gate_result.get("task_id") is not None else None,
                "valid Chapter 6 execution gate",
                {"reason": gate_result.get("reason") or "blocked", "return_stage": rstage},
                None,
            )
        super().__init__(diag)


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


def _extract_return_stage_from_diag(diag: dict[str, Any], default: str = "5") -> str:
    extracted = ch5_b._extract_return_stage_from_diag(diag)
    if extracted in STAGE_RANK:
        return extracted
    resume = str(diag.get("resume_ref") or "").replace("\\", "/").casefold()
    if "source" in resume or "ledger" in resume or "b-route-source-audit" in resume:
        return "3A"
    if "docs/planning/b-route/plans/" in resume:
        return "3B"
    if ".taskmaster/tasks/" in resume or "task-origins.v1.json" in resume:
        return "3C"
    if "game.core/contracts/" in resume or "docs/adr/" in resume or "docs/architecture/overlays/" in resume:
        return "4"
    if "docs/testing/mvg/" in resume or "docs/planning/b-route/bindings/" in resume or "chapter5/" in resume:
        return "5"
    code = str(diag.get("reason_code") or "")
    if code in (codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value, codec.ReasonCode.PENDING.value):
        return "3C"
    return default


def parse_strict_task_id(raw: Any) -> int:
    """Validate strictly ASCII positive integer task_id (rejects non-ASCII digits like superscript 1)."""
    if type(raw) is int and not isinstance(raw, bool):
        if raw >= 1:
            return codec.validate_task_id(raw)
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            stage=codec.Stage.CONTENT,
            expected="ASCII positive integer task_id",
            actual=raw,
        )
    if type(raw) is str:
        if STRICT_TASK_ID_RE.fullmatch(raw) is not None:
            return codec.validate_task_id(int(raw))
    _fail(
        codec.ReasonCode.INVALID_ARGUMENT,
        stage=codec.Stage.CONTENT,
        expected="ASCII positive integer task_id matching ^[1-9][0-9]*$",
        actual=raw,
    )
    raise AssertionError("unreachable")


def _preview_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = codec.strict_json_loads(path.read_bytes())
        return loaded if type(loaded) is dict else None
    except (codec.CodecError, OSError):
        return None


def _detect_task_na_labels(root: Path, tid: int | None) -> list[str]:
    triplet_docs: dict[str, Any] = {}
    for name, rel in task_resolver.TRIPLET.items():
        p = root / rel
        if not p.is_file():
            return []
        try:
            triplet_docs[name] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    try:
        _global_b, per_task = task_resolver._scan_triplet_traces(triplet_docs)
    except Exception:
        return []
    if tid is not None:
        return list(per_task.get(tid, ([], []))[1])
    found: list[str] = []
    for _t, (_b, na) in sorted(per_task.items()):
        found.extend(na)
    return sorted(set(found))


def _has_legacy_pending_journals(root: Path) -> bool:
    try:
        routes = op_scope.legacy_recovery_routes(root)
        return bool(routes)
    except (codec.CodecError, OSError, ValueError):
        return True


def _has_pending_b_route_operations(root: Path) -> bool:
    ops_dir = root / op_scope.STORE / "operations"
    if ops_dir.is_dir():
        try:
            graph = journal.operation_state_graph(root)
        except (codec.CodecError, OSError, ValueError):
            return True
        terminals = graph.get("terminals") or {}
        resolved_by = graph.get("resolved_by") or {}
        for op in graph.get("operations") or []:
            op_id = op.get("operation_id")
            if op_id not in terminals and op_id not in resolved_by:
                return True
    for rel_dir in (
        "logs/ci/b-route-operations",
        "logs/ci/b-route-chapter4-binding",
        "logs/ci/b-route-stage5-obligations",
    ):
        base = root / rel_dir
        if not os.path.lexists(base):
            continue
        try:
            inventory.no_reparse(base)
            if not base.is_dir():
                continue
            for sub in base.iterdir():
                if sub.name in {"operations", "locks"}:
                    continue
                inventory.no_reparse(sub)
                if not sub.is_dir():
                    continue
                for fname in ("apply-journal.json", "public-sync-journal.json", "operation.json"):
                    jfile = sub / fname
                    if not os.path.lexists(jfile):
                        continue
                    inventory.no_reparse(jfile)
                    if not jfile.is_file():
                        return True
                    doc = codec.strict_json_loads(jfile.read_bytes())
                    if not isinstance(doc, dict):
                        return True
                    st = str(doc.get("state") or doc.get("status") or "").strip().lower()
                    if st in {
                        "pending",
                        "in_progress",
                        "in-progress",
                        "prepared",
                        "reserved",
                        "applying",
                        "applied",
                        "verifying",
                        "verified",
                        "publishing",
                        "interrupted",
                        "partial",
                    }:
                        return True
        except (codec.CodecError, OSError, ValueError):
            return True
    return False


def detect_b_route_presence(root: Path | str, task_id: Any = None) -> dict[str, Any]:
    """Read-only zero-write detector of B-route governance, artifacts, pending markers, and lease env."""
    root_path = Path(root).resolve()
    tid_int: int | None = None
    if task_id is not None:
        try:
            tid_int = parse_strict_task_id(task_id)
        except codec.CodecError:
            tid_int = None

    rdy_preview: dict[str, Any] | None = None
    rec_preview: dict[str, Any] | None = None
    if tid_int is not None:
        rdy_preview = _preview_json(root_path / ch5_b.DEFAULT_READINESS_DIR / f"task-{tid_int}.json")
        rec_preview = _preview_json(root_path / ch5_b.DEFAULT_RECONCILIATION_DIR / f"task-{tid_int}.json")
    if rdy_preview is None:
        latest_rdy = _preview_json(root_path / ch5_b.DEFAULT_READINESS_DIR / "latest.json")
        if latest_rdy is not None and (tid_int is None or str(latest_rdy.get("task_id") or "") == str(tid_int)):
            rdy_preview = latest_rdy
    if rec_preview is None:
        latest_rec = _preview_json(root_path / ch5_b.DEFAULT_RECONCILIATION_DIR / "latest.json")
        if latest_rec is not None and (tid_int is None or str(latest_rec.get("task_id") or "") == str(tid_int)):
            rec_preview = latest_rec

    base = ch5_b.detect_repo_b_route_presence(
        root_path,
        tid_int,
        reconciliation=rec_preview,
        readiness=rdy_preview,
    )
    reasons = list(base.get("reasons") or [])
    cap_pending = (root_path / op_scope.CAP_PENDING).exists()
    if cap_pending:
        reasons.append("capability_apply_pending_present")
    legacy_pending_journal = _has_legacy_pending_journals(root_path)
    if legacy_pending_journal:
        reasons.append("legacy_apply_journal_present")
    b_route_pending_ops = _has_pending_b_route_operations(root_path)
    if b_route_pending_ops:
        reasons.append("b_route_operation_journal_pending")
    pending_journals = bool(legacy_pending_journal or b_route_pending_ops)
    na_labels = _detect_task_na_labels(root_path, tid_int)
    if na_labels:
        reasons.append("non_authoritative_na_labels_present")
    has_lease_env = bool(os.environ.get(ENV_LEASE_PATH) or os.environ.get(ENV_LEASE_SECRET))
    if has_lease_env:
        reasons.append("chapter6_lease_env_present")
    has_adr_0040 = (root_path / task_resolver.ADR_0040).exists()

    should_enforce = bool(
        base["has_b_traces"]
        or cap_pending
        or pending_journals
        or na_labels
        or has_lease_env
        or has_adr_0040
    )
    return {
        **base,
        "capability_apply_pending": cap_pending,
        "legacy_apply_journal_present": legacy_pending_journal,
        "pending_journals": pending_journals,
        "na_labels": na_labels,
        "has_lease_env": has_lease_env,
        "has_adr_0040": has_adr_0040,
        "should_enforce_gate": should_enforce,
        "reasons": reasons,
    }


def _blocked_result(
    *,
    task_id: int | None,
    operation: str | None,
    consumer: str,
    lock_mode: str,
    route: str,
    reason_code: str,
    reason: str,
    return_stage: str,
    diagnostics: list[dict[str, Any]],
    started: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed = round(max(0.0, time.monotonic() - started), 6)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "ok": False,
        "stable": True,
        "execution_allowed": False,
        "task_id": task_id,
        "operation": operation,
        "consumer": consumer,
        "route": route,
        "legacy_a_passthrough": False,
        "reason_code": reason_code,
        "reason": reason,
        "return_stage": return_stage if return_stage in STAGE_RANK else "5",
        "lock_mode": lock_mode,
        "uses_global_writer_lock": False,
        "input_set_digest": None,
        "applicable_set_digest": None,
        "scope_ids": [],
        "plan_refs": [],
        "binding_refs": [],
        "readiness": None,
        "closure_allowed": False,
        "requires_chapter6_reverification": False,
        "old_done_covers_new_obligations": False,
        "self_done_required": False,
        "stage5_summary": None,
        "readiness_path": None,
        "reconciliation_path": None,
        "reconciliation_sha256": None,
        "milestone_handoff_paths": [],
        "metrics": {
            "active_elapsed_seconds": elapsed,
            "model_invocation_count": 0,
            "reused": False,
        },
        "diagnostics": diagnostics,
        "report_path": None,
        **INVARIANT_FLAGS,
    }
    if extra:
        payload.update(extra)
    payload["runtime_verified"] = False
    payload["default_b_enabled"] = False
    payload["uses_global_writer_lock"] = False
    return payload


def _check_orphan_b_readiness_markers(root_path: Path, tid: int) -> dict[str, Any] | None:
    """Return a Diagnostic dict if orphan B-route readiness/reconciliation markers exist for tid."""
    checks = [
        root_path / ch5_b.DEFAULT_READINESS_DIR / f"task-{tid}.json",
        root_path / ch5_b.DEFAULT_RECONCILIATION_DIR / f"task-{tid}.json",
    ]
    for path in checks:
        if not path.is_file():
            continue
        doc = _preview_json(path)
        if ch5_b._artifact_has_b_route_marker(doc):
            rel = path.relative_to(root_path).as_posix()
            return _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected="zero orphan B-route readiness/reconciliation markers on A route",
                actual={"orphan_b_marker": rel, "return_stage": "5"},
                resume_ref=rel,
            )
    return None


def _validate_stage5_bindings_for_gate(
    root_path: Path,
    tid: int,
    origin: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify all committed Stage-5 bindings, manifests or legal non-Flow other_verification_refs."""
    entity_id = str(tid)
    # Reject freeform N/A labels unconditionally.
    detected_na = list((origin.get("non_flow_summary") or {}).get("detected_non_authoritative_labels") or [])
    if detected_na:
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"non_authoritative_labels": [], "return_stage": "5"},
            actual={"detected_non_authoritative_labels": detected_na, "return_stage": "5"},
            resume_ref=task_resolver.TRIPLET["back"],
        )

    (
        loaded_plans,
        loaded_bindings,
        sealed_digests,
        _views,
        master_tasks,
        _back_by_tid,
        _gameplay_by_tid,
    ) = ch5_b._load_plan_and_binding_bundle(root_path, origin)

    if not loaded_bindings:
        _fail(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"committed_stage5_bindings": "nonempty", "return_stage": "5"},
            actual={"binding_count": 0, "return_stage": "5"},
            resume_ref=task_resolver.ORIGINS_PATH,
        )

    for pid, (bref, _braw, bdoc, _mapping) in sorted(loaded_bindings.items()):
        bstage = str(bdoc.get("stage") or "")
        if bstage != "5":
            rstage = "4" if bstage == "3C" else "5"
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"plan_id": pid, "binding_stage": "5", "return_stage": rstage},
                actual={"plan_id": pid, "binding_stage": bstage, "return_stage": rstage},
                resume_ref=bref["path"],
            )

    bound_manifests = ch5_b._load_bound_manifests(root_path, loaded_bindings, entity_id=entity_id)

    per_plan: list[dict[str, Any]] = []
    any_flow = False
    any_non_flow = False
    for pid, (bref, _braw, bdoc, _mapping) in sorted(loaded_bindings.items()):
        _pref, _praw, pdoc = loaded_plans[pid]
        sem = stage5_obls.extract_stage5_semantics(
            pdoc,
            bdoc,
            master_tasks=master_tasks,
            manifests=bound_manifests,
        )
        # Validate dispositions for requirements covered by this plan.
        disps = {
            row["requirement_id"]: row
            for row in (pdoc.get("requirement_verification") or [])
            if type(row) is dict and row.get("requirement_id")
        }
        app_by_req = {
            row["requirement_id"]: row
            for row in (pdoc.get("applicability") or [])
            if type(row) is dict and row.get("requirement_id")
        }
        has_flow_disp = any(row.get("disposition") == "flow" for row in disps.values())
        has_source_gap = any(row.get("disposition") == "source_gap" for row in disps.values())
        if has_source_gap:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected={"source_gap": False, "return_stage": "3B"},
                actual={"plan_id": pid, "has_source_gap": True, "return_stage": "3B"},
                resume_ref=_pref["path"],
            )

        manifest_refs_for_plan = list(sem.get("manifest_refs") or [])
        other_verif_refs_for_plan = list(sem.get("other_verification_refs") or [])

        is_flow_plan = bool(has_flow_disp or manifest_refs_for_plan)
        if is_flow_plan:
            any_flow = True
            if not manifest_refs_for_plan:
                _fail(
                    codec.ReasonCode.MISSING_REQUIRED_FIELD,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"bound_mvg_manifests": "nonempty", "return_stage": "5"},
                    actual={"plan_id": pid, "manifest_refs": 0, "return_stage": "5"},
                    resume_ref=bref["path"],
                )
            for mref in manifest_refs_for_plan:
                mpath = preflight.path(mref["ref"])
                if mpath not in bound_manifests:
                    _fail(
                        codec.ReasonCode.FILE_NOT_FOUND,
                        stage=codec.Stage.PATH,
                        entity_id=entity_id,
                        expected={"manifest_path": mpath, "return_stage": "5"},
                        actual={"exists": False, "return_stage": "5"},
                        resume_ref=mpath,
                    )

        other_rows = [
            (rid, vrow)
            for rid, vrow in sorted(disps.items())
            if vrow.get("disposition") == "other_verification"
        ]
        deferred_rows = [
            (rid, vrow)
            for rid, vrow in sorted(disps.items())
            if vrow.get("disposition") == "deferred"
        ]

        if other_rows:
            any_non_flow = True
            for rid, vrow in other_rows:
                arow = app_by_req.get(rid) or {}
                rationale = arow.get("rationale") or vrow.get("rationale")
                if not stage5_obls._is_substantive_text(rationale):
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"non_flow_applicability_rationale": "substantive", "return_stage": "3B"},
                        actual={"requirement_id": rid, "rationale": rationale, "return_stage": "3B"},
                        resume_ref=_pref["path"],
                    )
                ov_refs = list(arow.get("other_verification_refs") or []) or other_verif_refs_for_plan
                if not ov_refs:
                    _fail(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected={"other_verification_refs": "nonempty live files", "return_stage": "5"},
                        actual={"requirement_id": rid, "other_verification_refs": 0, "return_stage": "5"},
                        resume_ref=bref["path"],
                    )
                for oref in ov_refs:
                    ch5_b._read_owned_ref_bytes(
                        root_path,
                        oref,
                        sealed_digests=sealed_digests,
                        allow_sealed_logs=False,
                        entity_id=entity_id,
                        return_stage="5",
                    )

        if not is_flow_plan:
            # Legal zero-MVG-impact non-Flow path:
            # MUST have adoption_proof_refs, nonempty disps in {"other_verification", "deferred"},
            # substantive rationale on every deferred row, and nonempty other_rows or deferred_rows.
            any_non_flow = True
            adoption_proofs = list(pdoc.get("adoption_proof_refs") or [])
            if not adoption_proofs:
                _fail(
                    codec.ReasonCode.MISSING_REQUIRED_FIELD,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"adoption_proof_refs": "nonempty for non-Flow", "return_stage": "3B"},
                    actual={"plan_id": pid, "adoption_proof_refs": 0, "return_stage": "3B"},
                    resume_ref=_pref["path"],
                )
            for proof_ref in adoption_proofs:
                ch5_b._read_owned_ref_bytes(
                    root_path,
                    proof_ref,
                    sealed_digests=sealed_digests,
                    allow_sealed_logs=True,
                    entity_id=entity_id,
                    return_stage="3B",
                )
            allowed_non_flow = {"other_verification", "deferred"}
            if (
                not disps
                or any(vrow.get("disposition") not in allowed_non_flow for vrow in disps.values())
                or not (other_rows or deferred_rows)
            ):
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"valid_non_flow_dispositions": sorted(allowed_non_flow), "return_stage": "5"},
                    actual={"plan_id": pid, "dispositions": sorted(str(v.get("disposition")) for v in disps.values()), "return_stage": "5"},
                    resume_ref=bref["path"],
                )
            for rid, vrow in deferred_rows:
                arow = app_by_req.get(rid) or {}
                rationale = arow.get("rationale") or vrow.get("rationale")
                if not stage5_obls._is_substantive_text(rationale):
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"deferred_applicability_rationale": "substantive", "return_stage": "3B"},
                        actual={"requirement_id": rid, "rationale": rationale, "return_stage": "3B"},
                        resume_ref=_pref["path"],
                    )

        per_plan.append(
            {
                "plan_id": pid,
                "binding_revision": bdoc.get("binding_revision"),
                "stage": bdoc.get("stage"),
                "is_flow": is_flow_plan,
                "manifest_paths": sorted(preflight.path(m["ref"]) for m in manifest_refs_for_plan),
                "other_verification_paths": sorted(
                    preflight.path(f["path"])
                    for oref in other_verif_refs_for_plan
                    for f in (oref.get("files") or [])
                ),
                "obligations_by_category": deepcopy(sem.get("obligations_by_category") or {}),
                "deduplication": deepcopy(sem.get("deduplication") or {}),
            }
        )

    live_reverification = ch5_b._compute_live_reverification(
        tid,
        master_tasks=master_tasks,
        loaded_plans=loaded_plans,
        loaded_bindings=loaded_bindings,
        manifests=bound_manifests,
    )
    stage5_summary = {
        "mode": "mixed" if (any_flow and any_non_flow) else ("flow" if any_flow else ("non_flow" if any_non_flow else "unknown")),
        "has_flow_obligations": any_flow,
        "has_non_flow_obligations": any_non_flow,
        "plans": per_plan,
        "reverification": live_reverification,
    }
    return stage5_summary, live_reverification


def _evaluate_gate_core(
    root_path: Path,
    tid: int,
    *,
    operation: str | None,
    expected_input_set_digest: str | None,
    expected_input_set_snapshot: dict[str, Any] | None,
    consumer: str,
    lock_mode: str,
    check_legacy_a_obligations: bool,
    started: float,
    enforce_eligibility: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Core read-only gate evaluator returning (gate_result, live_input_set_or_None)."""
    entity_id = str(tid)
    import _b_route_chapter6_recovery as ch6_recovery

    # 0. Pre-flight inspection of pending markers, damaged journals, and overlapping B-route ops.
    cand_scopes = ch6_recovery._resolve_candidate_task_scopes(root_path, tid, operation)
    pending_chk = ch6_recovery._inspect_pending_and_post_edits(root_path, tid, scope_ids=cand_scopes)
    if pending_chk.get("blocked"):
        p_diags = list(pending_chk.get("diagnostics") or [])
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="blocked",
                reason_code=str(pending_chk.get("reason_code") or codec.ReasonCode.PENDING.value),
                reason=str(pending_chk.get("reason") or "pending_journal"),
                return_stage=str(pending_chk.get("return_stage") or "3C"),
                diagnostics=p_diags,
                started=started,
            ),
            None,
        )

    # 1. Story 3.3 unified origin classification.
    origin = task_resolver.resolve_task_origin(root_path, tid, operation=operation)
    if origin.get("route") == "blocked" or not origin.get("ok") or not origin.get("stable"):
        diags = list(origin.get("diagnostics") or [])
        if not diags:
            diags = [
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="valid Task origin classification",
                    actual={"route": origin.get("route"), "return_stage": "3C"},
                    resume_ref=task_resolver.ORIGINS_PATH,
                )
            ]
        first_code = str(diags[0].get("reason_code") or codec.ReasonCode.CONFLICT.value)
        rstage = _earliest_stage([_extract_return_stage_from_diag(d, default="3C") for d in diags]) or "3C"
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="blocked",
                reason_code=first_code,
                reason=f"origin_blocked:{first_code}",
                return_stage=rstage,
                diagnostics=diags,
                started=started,
            ),
            None,
        )

    route = str(origin["route"])

    # 2. Pure explicit_not_enabled_a path.
    if route == "explicit_not_enabled_a":
        orphan_diag = _check_orphan_b_readiness_markers(root_path, tid)
        if orphan_diag is not None:
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="blocked",
                    reason_code=orphan_diag["reason_code"],
                    reason="orphan_b_route_readiness_marker",
                    return_stage="5",
                    diagnostics=[orphan_diag],
                    started=started,
                ),
                None,
            )
        presence = ch5_b.detect_repo_b_route_presence(root_path, tid)
        if presence["has_b_traces"]:
            d = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="zero B-route traces under explicit_not_enabled_a",
                actual={"reasons": presence["reasons"], "return_stage": "3C"},
                resume_ref=task_resolver.ADR_0040,
            )
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="blocked",
                    reason_code=d["reason_code"],
                    reason="unexpected_b_route_traces_under_explicit_a",
                    return_stage="3C",
                    diagnostics=[d],
                    started=started,
                ),
                None,
            )
        live_iset_a: dict[str, Any] | None = None
        if expected_input_set_digest is not None:
            live_iset_a = input_set.resolve_input_set(root_path, tid, operation=operation)
            if not live_iset_a["ok"] or not live_iset_a["stable"]:
                diags = list(live_iset_a.get("diagnostics") or [])
                first_code = str(diags[0]["reason_code"]) if diags else codec.ReasonCode.INPUT_STALE.value
                rstage = live_iset_a.get("return_stage") or "3C"
                return (
                    _blocked_result(
                        task_id=tid,
                        operation=operation,
                        consumer=consumer,
                        lock_mode=lock_mode,
                        route="blocked",
                        reason_code=first_code,
                        reason=f"input_set_blocked:{first_code}",
                        return_stage=rstage,
                        diagnostics=diags,
                        started=started,
                    ),
                    None,
                )
            if live_iset_a["input_set_digest"] != expected_input_set_digest:
                if expected_input_set_snapshot is not None:
                    cmp_res = input_set.compare_input_sets(expected_input_set_snapshot, live_iset_a)
                    diags = list(cmp_res.get("diagnostics") or [])
                    rstage = cmp_res.get("return_stage") or "3C"
                else:
                    rstage = "3C"
                    diags = [
                        _diag(
                            codec.ReasonCode.INPUT_STALE,
                            stage=codec.Stage.BUNDLE,
                            entity_id=entity_id,
                            expected=expected_input_set_digest,
                            actual={"input_set_digest": live_iset_a["input_set_digest"], "return_stage": rstage},
                        )
                    ]
                return (
                    _blocked_result(
                        task_id=tid,
                        operation=operation,
                        consumer=consumer,
                        lock_mode=lock_mode,
                        route="explicit_not_enabled_a",
                        reason_code=codec.ReasonCode.INPUT_STALE.value,
                        reason="input_set_digest_drift",
                        return_stage=rstage,
                        diagnostics=diags,
                        started=started,
                    ),
                    live_iset_a,
                )
        elapsed = round(max(0.0, time.monotonic() - started), 6)
        return (
            {
                "schema_version": SCHEMA,
                "ok": True,
                "stable": True,
                "execution_allowed": True,
                "task_id": tid,
                "operation": operation,
                "consumer": consumer,
                "route": "explicit_not_enabled_a",
                "legacy_a_passthrough": True,
                "reason_code": codec.ReasonCode.OK.value,
                "reason": "explicit_not_enabled_a",
                "return_stage": None,
                "lock_mode": lock_mode,
                "uses_global_writer_lock": False,
                "input_set_digest": live_iset_a["input_set_digest"] if live_iset_a else None,
                "applicable_set_digest": None,
                "scope_ids": list(live_iset_a["scope_ids"]) if live_iset_a else list(op_scope.resource_scopes(task_ids=[tid])),
                "plan_refs": [],
                "binding_refs": [],
                "readiness": None,
                "closure_allowed": True,
                "requires_chapter6_reverification": False,
                "old_done_covers_new_obligations": False,
                "self_done_required": False,
                "stage5_summary": None,
                "readiness_path": None,
                "reconciliation_path": None,
                "reconciliation_sha256": None,
                "milestone_handoff_paths": [],
                "metrics": {
                    "active_elapsed_seconds": elapsed,
                    "model_invocation_count": 0,
                    "reused": False,
                },
                "diagnostics": [],
                "report_path": None,
                **INVARIANT_FLAGS,
            },
            live_iset_a,
        )

    # 3. Frozen A path (in a repo with B governance).
    if route == "A":
        orphan_diag = _check_orphan_b_readiness_markers(root_path, tid)
        if orphan_diag is not None:
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="blocked",
                    reason_code=orphan_diag["reason_code"],
                    reason="orphan_b_route_readiness_marker",
                    return_stage="5",
                    diagnostics=[orphan_diag],
                    started=started,
                ),
                None,
            )
        live_iset = input_set.resolve_input_set(root_path, tid, operation=operation)
        if not live_iset["ok"] or not live_iset["stable"] or not live_iset["valid_input_set"] or live_iset["route"] != "A":
            diags = list(live_iset.get("diagnostics") or [])
            if not diags:
                diags = [
                    _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected="valid frozen A InputSet",
                        actual={"route": live_iset.get("route"), "return_stage": "3C"},
                    )
                ]
            first_code = str(diags[0]["reason_code"])
            rstage = live_iset.get("return_stage") or _extract_return_stage_from_diag(diags[0], default="3C")
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="blocked",
                    reason_code=first_code,
                    reason=f"frozen_a_input_set_blocked:{first_code}",
                    return_stage=rstage,
                    diagnostics=diags,
                    started=started,
                ),
                None,
            )
        if expected_input_set_digest is not None and live_iset["input_set_digest"] != expected_input_set_digest:
            if expected_input_set_snapshot is not None:
                cmp_res = input_set.compare_input_sets(expected_input_set_snapshot, live_iset)
                diags = list(cmp_res.get("diagnostics") or [])
                rstage = cmp_res.get("return_stage") or "3C"
            else:
                rstage = "3C"
                diags = [
                    _diag(
                        codec.ReasonCode.INPUT_STALE,
                        stage=codec.Stage.BUNDLE,
                        entity_id=entity_id,
                        expected=expected_input_set_digest,
                        actual={"input_set_digest": live_iset["input_set_digest"], "return_stage": rstage},
                    )
                ]
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="A",
                    reason_code=codec.ReasonCode.INPUT_STALE.value,
                    reason="frozen_a_input_set_drift",
                    return_stage=rstage,
                    diagnostics=diags,
                    started=started,
                ),
                live_iset,
            )

        # Verify original A Chapter 5 readiness within frozen boundary.
        import chapter5_semantic_reconciliation as ch5

        rdy_ok, rdy_payload, rdy_reason = ch5.load_task_readiness(root_path, entity_id)
        if not rdy_ok:
            code = (
                codec.ReasonCode.FILE_NOT_FOUND
                if "missing" in str(rdy_reason)
                else (
                    codec.ReasonCode.INPUT_STALE
                    if "stale" in str(rdy_reason)
                    else codec.ReasonCode.SEMANTIC_ERROR
                )
            )
            d = _diag(
                code,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="valid original A Chapter 5 readiness within frozen boundary",
                actual={"reason": rdy_reason, "return_stage": "5"},
                resume_ref=(ch5_b.DEFAULT_READINESS_DIR / f"task-{tid}.json").as_posix(),
            )
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="A",
                    reason_code=code.value,
                    reason=f"frozen_a_readiness_blocked:{rdy_reason}",
                    return_stage="5",
                    diagnostics=[d],
                    started=started,
                    extra={
                        "input_set_digest": live_iset["input_set_digest"],
                        "scope_ids": list(live_iset["scope_ids"]),
                        "frozen_a_boundary": origin.get("frozen_a_boundary"),
                    },
                ),
                live_iset,
            )

        legacy_handoffs: list[str] = []
        if check_legacy_a_obligations:
            import _mvg_obligations as mvg_obl

            leg_ok, leg_reason, leg_detail = mvg_obl._check_legacy_task_obligations(root_path, entity_id)
            if not leg_ok:
                code = codec.ReasonCode.INPUT_STALE if "stale" in str(leg_reason) or "drift" in str(leg_reason) else codec.ReasonCode.CONFLICT
                d = _diag(
                    code,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="valid legacy MVG obligations within frozen A boundary",
                    actual={"reason": leg_reason, "return_stage": "5"},
                    resume_ref=mvg_obl.TRACE_ROOT.as_posix(),
                )
                return (
                    _blocked_result(
                        task_id=tid,
                        operation=operation,
                        consumer=consumer,
                        lock_mode=lock_mode,
                        route="A",
                        reason_code=code.value,
                        reason=f"frozen_a_mvg_obligations_blocked:{leg_reason}",
                        return_stage="5",
                        diagnostics=[d],
                        started=started,
                        extra={
                            "input_set_digest": live_iset["input_set_digest"],
                            "scope_ids": list(live_iset["scope_ids"]),
                            "frozen_a_boundary": origin.get("frozen_a_boundary"),
                        },
                    ),
                    live_iset,
                )
            legacy_handoffs = list(leg_detail.get("milestone_handoff_paths") or [])

        elig_a = ch6_recovery._check_task_and_dependency_eligibility(root_path, tid)
        if not elig_a["ok"] and (
            enforce_eligibility or str(elig_a.get("reason") or "").startswith("task_status_ineligible:")
        ):
            return (
                _blocked_result(
                    task_id=tid,
                    operation=operation,
                    consumer=consumer,
                    lock_mode=lock_mode,
                    route="A",
                    reason_code=str(elig_a["reason_code"]),
                    reason=str(elig_a["reason"]),
                    return_stage=str(elig_a.get("return_stage") or "3C"),
                    diagnostics=list(elig_a.get("diagnostics") or []),
                    started=started,
                    extra={
                        "input_set_digest": live_iset["input_set_digest"],
                        "scope_ids": list(live_iset["scope_ids"]),
                        "frozen_a_boundary": origin.get("frozen_a_boundary"),
                    },
                ),
                live_iset,
            )

        elapsed = round(max(0.0, time.monotonic() - started), 6)
        return (
            {
                "schema_version": SCHEMA,
                "ok": True,
                "stable": True,
                "execution_allowed": True,
                "task_id": tid,
                "operation": operation,
                "consumer": consumer,
                "route": "A",
                "legacy_a_passthrough": False,
                "reason_code": codec.ReasonCode.OK.value,
                "reason": "frozen_a_ready",
                "return_stage": None,
                "lock_mode": lock_mode,
                "uses_global_writer_lock": False,
                "input_set_digest": live_iset["input_set_digest"],
                "applicable_set_digest": None,
                "scope_ids": list(live_iset["scope_ids"]),
                "plan_refs": [],
                "binding_refs": [],
                "frozen_a_boundary": deepcopy(origin.get("frozen_a_boundary")),
                "readiness": rdy_payload.get("readiness"),
                "closure_allowed": True,
                "requires_chapter6_reverification": False,
                "old_done_covers_new_obligations": False,
                "self_done_required": False,
                "stage5_summary": None,
                "readiness_path": (ch5_b.DEFAULT_READINESS_DIR / f"task-{tid}.json").as_posix(),
                "reconciliation_path": (ch5_b.DEFAULT_RECONCILIATION_DIR / f"task-{tid}.json").as_posix(),
                "reconciliation_sha256": rdy_payload.get("reconciliation_sha256"),
                "milestone_handoff_paths": legacy_handoffs,
                "metrics": {
                    "active_elapsed_seconds": elapsed,
                    "model_invocation_count": 0,
                    "reused": False,
                },
                "diagnostics": [],
                "report_path": None,
                **INVARIANT_FLAGS,
            },
            live_iset,
        )

    # 4. Governed B-route full chain: 3.3 -> 3.5 -> 3.6 -> 3.7.
    live_iset = input_set.resolve_input_set(root_path, tid, operation=operation)
    if not live_iset["ok"] or not live_iset["stable"] or not live_iset["valid_input_set"] or live_iset["route"] != "B":
        diags = list(live_iset.get("diagnostics") or [])
        if not diags:
            diags = [
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="valid B-route InputSet",
                    actual={"route": live_iset.get("route"), "return_stage": "5"},
                )
            ]
        first_code = str(diags[0]["reason_code"])
        rstage = live_iset.get("return_stage") or _extract_return_stage_from_diag(diags[0], default="5")
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=first_code,
                reason=f"input_set_blocked:{first_code}",
                return_stage=rstage,
                diagnostics=diags,
                started=started,
                extra={
                    "applicable_set_digest": origin["applicable_set_digest"],
                    "plan_refs": deepcopy(origin["plan_refs"]),
                    "binding_refs": deepcopy(origin["binding_refs"]),
                },
            ),
            None,
        )

    if expected_input_set_digest is not None and live_iset["input_set_digest"] != expected_input_set_digest:
        if expected_input_set_snapshot is not None:
            cmp_res = input_set.compare_input_sets(expected_input_set_snapshot, live_iset)
            diags = list(cmp_res.get("diagnostics") or [])
            rstage = cmp_res.get("return_stage") or "5"
            invalidated = list(cmp_res.get("invalidated_items") or [])
        else:
            rstage = "5"
            invalidated = []
            diags = [
                _diag(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected=expected_input_set_digest,
                    actual={"input_set_digest": live_iset["input_set_digest"], "return_stage": rstage},
                )
            ]
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="input_set_digest_drift",
                return_stage=rstage,
                diagnostics=diags,
                started=started,
                extra={
                    "input_set_digest": live_iset["input_set_digest"],
                    "expected_input_set_digest": expected_input_set_digest,
                    "invalidated_items": invalidated,
                    "applicable_set_digest": origin["applicable_set_digest"],
                    "scope_ids": list(live_iset["scope_ids"]),
                    "plan_refs": deepcopy(origin["plan_refs"]),
                    "binding_refs": deepcopy(origin["binding_refs"]),
                },
            ),
            live_iset,
        )

    # 4b. Story 3.6 Stage-5 obligations & verification basis validation.
    try:
        stage5_summary, live_reverification = _validate_stage5_bindings_for_gate(root_path, tid, origin)
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None:
            d["entity_id"] = entity_id
        rstage = _extract_return_stage_from_diag(d, default="5")
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=d["reason_code"],
                reason=f"stage5_obligations_blocked:{d['reason_code']}",
                return_stage=rstage,
                diagnostics=[d],
                started=started,
                extra={
                    "input_set_digest": live_iset["input_set_digest"],
                    "applicable_set_digest": origin["applicable_set_digest"],
                    "scope_ids": list(live_iset["scope_ids"]),
                    "plan_refs": deepcopy(origin["plan_refs"]),
                    "binding_refs": deepcopy(origin["binding_refs"]),
                },
            ),
            live_iset,
        )

    # 4c. Story 3.7 Chapter 5 readiness verification.
    readiness_res = ch5_b.verify_b_route_chapter5_readiness(
        root_path,
        task_id=tid,
        operation=operation,
        lock_mode="none",
    )
    if (
        not readiness_res.get("ok")
        or not readiness_res.get("fresh")
        or not readiness_res.get("closure_allowed")
    ):
        diags = list(readiness_res.get("diagnostics") or [])
        if not diags:
            rstage_fb = readiness_res.get("return_stage") or "5"
            diags = [
                _diag(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="fresh valid B-route Chapter 5 readiness",
                    actual={"reason": readiness_res.get("reason"), "return_stage": rstage_fb},
                    resume_ref=readiness_res.get("readiness_path"),
                )
            ]
        first_code = str(diags[0]["reason_code"])
        rstage = readiness_res.get("return_stage") or _extract_return_stage_from_diag(diags[0], default="5")
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=first_code,
                reason=str(readiness_res.get("reason") or f"chapter5_readiness_blocked:{first_code}"),
                return_stage=rstage,
                diagnostics=diags,
                started=started,
                extra={
                    "input_set_digest": live_iset["input_set_digest"],
                    "applicable_set_digest": origin["applicable_set_digest"],
                    "scope_ids": list(live_iset["scope_ids"]),
                    "plan_refs": deepcopy(origin["plan_refs"]),
                    "binding_refs": deepcopy(origin["binding_refs"]),
                    "stage5_summary": stage5_summary,
                    "readiness_path": readiness_res.get("readiness_path"),
                    "reconciliation_path": readiness_res.get("reconciliation_path"),
                    "invalidated_items": list(readiness_res.get("invalidated_items") or []),
                },
            ),
            live_iset,
        )

    # Double-check cross-stage identity bindings between 3.3, 3.5, and 3.7.
    if readiness_res.get("input_set_digest") != live_iset["input_set_digest"]:
        d = _diag(
            codec.ReasonCode.INPUT_STALE,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=readiness_res.get("input_set_digest"),
            actual={"input_set_digest": live_iset["input_set_digest"], "return_stage": "5"},
            resume_ref=readiness_res.get("readiness_path"),
        )
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="readiness_input_set_digest_mismatch",
                return_stage="5",
                diagnostics=[d],
                started=started,
            ),
            live_iset,
        )
    if readiness_res.get("applicable_set_digest") != origin["applicable_set_digest"]:
        d = _diag(
            codec.ReasonCode.INPUT_STALE,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=readiness_res.get("applicable_set_digest"),
            actual={"applicable_set_digest": origin["applicable_set_digest"], "return_stage": "3B"},
            resume_ref=readiness_res.get("readiness_path"),
        )
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="readiness_applicable_set_digest_mismatch",
                return_stage="3B",
                diagnostics=[d],
                started=started,
            ),
            live_iset,
        )
    if list(readiness_res.get("scope_ids") or []) != list(live_iset["scope_ids"]):
        d = _diag(
            codec.ReasonCode.INPUT_STALE,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=readiness_res.get("scope_ids"),
            actual={"scope_ids": live_iset["scope_ids"], "return_stage": "5"},
            resume_ref=readiness_res.get("readiness_path"),
        )
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="readiness_scope_ids_mismatch",
                return_stage="5",
                diagnostics=[d],
                started=started,
            ),
            live_iset,
        )

    elig_b = ch6_recovery._check_task_and_dependency_eligibility(root_path, tid)
    if not elig_b["ok"] and (
        enforce_eligibility or str(elig_b.get("reason") or "").startswith("task_status_ineligible:")
    ):
        return (
            _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode=lock_mode,
                route="B",
                reason_code=str(elig_b["reason_code"]),
                reason=str(elig_b["reason"]),
                return_stage=str(elig_b.get("return_stage") or "3C"),
                diagnostics=list(elig_b.get("diagnostics") or []),
                started=started,
                extra={
                    "input_set_digest": live_iset["input_set_digest"],
                    "applicable_set_digest": origin["applicable_set_digest"],
                    "scope_ids": list(live_iset["scope_ids"]),
                    "plan_refs": deepcopy(origin["plan_refs"]),
                    "binding_refs": deepcopy(origin["binding_refs"]),
                    "stage5_summary": stage5_summary,
                },
            ),
            live_iset,
        )

    elapsed = round(max(0.0, time.monotonic() - started), 6)
    requires_reverify = bool(
        live_reverification["requires_chapter6_reverification"]
        or readiness_res.get("requires_chapter6_reverification")
    )
    return (
        {
            "schema_version": SCHEMA,
            "ok": True,
            "stable": True,
            "execution_allowed": True,
            "task_id": tid,
            "operation": operation,
            "consumer": consumer,
            "route": "B",
            "legacy_a_passthrough": False,
            "reason_code": codec.ReasonCode.OK.value,
            "reason": "ready",
            "return_stage": None,
            "lock_mode": lock_mode,
            "uses_global_writer_lock": False,
            "input_set_digest": live_iset["input_set_digest"],
            "applicable_set_digest": origin["applicable_set_digest"],
            "scope_ids": list(live_iset["scope_ids"]),
            "plan_refs": deepcopy(origin["plan_refs"]),
            "binding_refs": deepcopy(origin["binding_refs"]),
            "readiness": readiness_res.get("readiness"),
            "closure_allowed": True,
            "requires_chapter6_reverification": requires_reverify,
            "old_done_covers_new_obligations": False,
            "self_done_required": False,
            "stage5_summary": stage5_summary,
            "readiness_path": readiness_res.get("readiness_path"),
            "reconciliation_path": readiness_res.get("reconciliation_path"),
            "reconciliation_sha256": readiness_res.get("reconciliation_sha256"),
            "milestone_handoff_paths": [],
            "metrics": {
                "active_elapsed_seconds": elapsed,
                "model_invocation_count": 0,
                "reused": bool((readiness_res.get("source_audit_reuse") or {}).get("reused")),
            },
            "diagnostics": [],
            "report_path": None,
            **INVARIANT_FLAGS,
        },
        live_iset,
    )


def evaluate_chapter6_gate(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    expected_input_set_digest: str | None = None,
    expected_input_set_snapshot: dict[str, Any] | None = None,
    consumer: str = "chapter6",
    lock_mode: str = "none",
    check_legacy_a_obligations: bool = True,
    enforce_eligibility: bool = False,
) -> dict[str, Any]:
    """Evaluate the unified Chapter 6 execution gate for one master Task ID."""
    started = time.monotonic()
    validated_tid: int | None = None
    validated_op: str | None = None
    validated_lock = "none"
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = parse_strict_task_id(task_id)
        validated_op = task_resolver._validate_operation(operation)
        validated_lock = input_set._validate_lock_mode(lock_mode)
        if expected_input_set_digest is not None:
            if type(expected_input_set_digest) is not str or _DIGEST_RE.fullmatch(expected_input_set_digest) is None:
                _fail(
                    codec.ReasonCode.INVALID_DIGEST,
                    stage=codec.Stage.CONTENT,
                    entity_id=str(validated_tid),
                    expected="sha256:<64 lowercase hex digits>",
                    actual=expected_input_set_digest,
                )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None and validated_tid is not None:
            d["entity_id"] = str(validated_tid)
        return _blocked_result(
            task_id=validated_tid,
            operation=validated_op,
            consumer=consumer,
            lock_mode=validated_lock,
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_arguments:{d['reason_code']}",
            return_stage=_extract_return_stage_from_diag(d, default="5"),
            diagnostics=[d],
            started=started,
        )

    if validated_lock == "scope":
        env_path = os.environ.get(ENV_LEASE_PATH)
        env_secret = os.environ.get(ENV_LEASE_SECRET)
        if env_path is not None or env_secret is not None:
            try:
                receipt = _verify_inherited_lease_receipt(
                    root_path,
                    validated_tid,
                    str(env_path or ""),
                    str(env_secret or ""),
                )
            except codec.CodecError as err:
                d = err.diagnostic.to_dict()
                if d.get("entity_id") is None:
                    d["entity_id"] = str(validated_tid)
                return _blocked_result(
                    task_id=validated_tid,
                    operation=validated_op,
                    consumer=consumer,
                    lock_mode="scope",
                    route="blocked",
                    reason_code=d["reason_code"],
                    reason=f"invalid_parent_lease:{d['reason_code']}",
                    return_stage=_extract_return_stage_from_diag(d, default="5"),
                    diagnostics=[d],
                    started=started,
                )
            res, _iset = _evaluate_gate_core(
                root_path,
                validated_tid,
                operation=validated_op,
                expected_input_set_digest=expected_input_set_digest or receipt["input_set_digest"],
                expected_input_set_snapshot=expected_input_set_snapshot,
                consumer=consumer,
                lock_mode="scope",
                check_legacy_a_obligations=check_legacy_a_obligations,
                started=started,
                enforce_eligibility=enforce_eligibility,
            )
            if res["ok"] and not set(res.get("scope_ids") or ()).issubset(set(receipt["scope_ids"])):
                d = _diag(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(validated_tid),
                    expected=receipt["scope_ids"],
                    actual={"scope_ids": res.get("scope_ids"), "return_stage": "5"},
                    resume_ref=receipt["receipt_rel"],
                )
                return _blocked_result(
                    task_id=validated_tid,
                    operation=validated_op,
                    consumer=consumer,
                    lock_mode="scope",
                    route=str(res.get("route") or "B"),
                    reason_code=codec.ReasonCode.INPUT_STALE.value,
                    reason="child_scope_ids_exceed_parent_lease",
                    return_stage="5",
                    diagnostics=[d],
                    started=started,
                )
            res["lock_mode"] = "scope"
            res["uses_global_writer_lock"] = False
            return res

        pre_res, _pre_iset = _evaluate_gate_core(
            root_path,
            validated_tid,
            operation=validated_op,
            expected_input_set_digest=expected_input_set_digest,
            expected_input_set_snapshot=expected_input_set_snapshot,
            consumer=consumer,
            lock_mode="none",
            check_legacy_a_obligations=check_legacy_a_obligations,
            started=started,
            enforce_eligibility=enforce_eligibility,
        )
        if not pre_res["ok"] or pre_res["route"] == "explicit_not_enabled_a":
            pre_res["lock_mode"] = "scope"
            pre_res["uses_global_writer_lock"] = False
            return pre_res

        try:
            with input_set.guarded_input_set(root_path, validated_tid, operation=validated_op) as iset_handle:
                res, _iset = _evaluate_gate_core(
                    root_path,
                    validated_tid,
                    operation=validated_op,
                    expected_input_set_digest=expected_input_set_digest or iset_handle.input_set_digest,
                    expected_input_set_snapshot=expected_input_set_snapshot or iset_handle.snapshot,
                    consumer=consumer,
                    lock_mode="scope",
                    check_legacy_a_obligations=check_legacy_a_obligations,
                    started=started,
                    enforce_eligibility=enforce_eligibility,
                )
                res["lock_mode"] = "scope"
                res["uses_global_writer_lock"] = False
                return res
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            if d.get("entity_id") is None:
                d["entity_id"] = str(validated_tid)
            return _blocked_result(
                task_id=validated_tid,
                operation=validated_op,
                consumer=consumer,
                lock_mode="scope",
                route="blocked",
                reason_code=d["reason_code"],
                reason=f"scope_lease_blocked:{d['reason_code']}",
                return_stage=_extract_return_stage_from_diag(d, default="5"),
                diagnostics=[d],
                started=started,
            )

    res, _iset = _evaluate_gate_core(
        root_path,
        validated_tid,
        operation=validated_op,
        expected_input_set_digest=expected_input_set_digest,
        expected_input_set_snapshot=expected_input_set_snapshot,
        consumer=consumer,
        lock_mode="none",
        check_legacy_a_obligations=check_legacy_a_obligations,
        started=started,
        enforce_eligibility=enforce_eligibility,
    )
    return res


# ---------------------------------------------------------------------------
# Parent-to-Child Verified Business-Scope Leases
# ---------------------------------------------------------------------------


def _get_process_create_time(pid: int) -> int | None:
    if type(pid) is not int or pid <= 0 or os.name != "nt":
        return None
    import ctypes

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = _FILETIME()
        exit_time = _FILETIME()
        kernel_time = _FILETIME()
        user_time = _FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def _is_pid_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _probe_scope_lock_is_held(root_path: Path, scope_id: str) -> bool:
    """Return True iff the OS byte lock for scope_id is actively held right now (zero mutations if unlocked)."""
    scope_dir_rel = op_scope.STORE + "/locks/scopes/" + op_scope._hash(scope_id)
    try:
        scope_dir = op_scope._safe(root_path, scope_dir_rel)
        lock_file = scope_dir / "capability-coordinator.lock"
        if not scope_dir.is_dir() or not lock_file.is_file():
            return False
        op_leases._directory(scope_dir)
        op_leases._lock_file(scope_dir)
    except (codec.CodecError, ValueError, OSError):
        return False
    try:
        with coordinator_lock(scope_dir):
            # Lock succeeded non-blocking -> NOT currently held by any parent!
            return False
    except ValueError as exc:
        return str(exc) == "capability_coordinator_busy"
    except OSError:
        return False


def _verify_inherited_lease_receipt(
    root_path: Path,
    tid: int,
    raw_path: str,
    raw_secret: str,
) -> dict[str, Any]:
    """Verify parent lease receipt via path containment, SHA-256 secret, live PID, and OS lock probe."""
    entity_id = str(tid)
    if not raw_path or not raw_secret:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="complete parent lease path and secret pair",
            actual={"has_path": bool(raw_path), "has_secret": bool(raw_secret), "return_stage": "5"},
        )
    rel_norm = raw_path.replace("\\", "/").strip()
    try:
        if Path(rel_norm).is_absolute():
            candidate = Path(rel_norm)
            for ancestor in reversed((candidate, *candidate.parents)):
                inventory.no_reparse(ancestor)
            resolved = candidate.resolve()
            rel_norm = resolved.relative_to(root_path.resolve()).as_posix()
        rel_clean = preflight.path(rel_norm)
    except (codec.CodecError, ValueError, OSError) as exc:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=f"contained lease receipt under {LEASE_DIR}/",
            actual={"path": raw_path, "error": type(exc).__name__, "return_stage": "5"},
        )
    if not rel_clean.startswith(LEASE_DIR + "/") or rel_clean.count("/") != LEASE_DIR.count("/") + 1:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=f"direct receipt file under {LEASE_DIR}/",
            actual={"path": rel_clean, "return_stage": "5"},
            resume_ref=rel_clean,
        )
    try:
        receipt_file = inventory.safe_input(root_path.resolve(), rel_clean, allow_logs=True)
    except (ValueError, OSError) as exc:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected="non-reparse contained lease receipt",
            actual={"path": rel_clean, "error": type(exc).__name__, "return_stage": "5"},
            resume_ref=rel_clean,
        )
    if not receipt_file.is_file():
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="existing parent lease receipt",
            actual={"path": rel_clean, "exists": False, "return_stage": "5"},
            resume_ref=rel_clean,
        )
    try:
        inventory.no_reparse(receipt_file)
        info = receipt_file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail(
                codec.ReasonCode.UNSAFE_PATH,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected="regular non-hardlinked lease receipt file",
                actual={"path": rel_clean, "return_stage": "5"},
                resume_ref=rel_clean,
            )
        receipt = codec.strict_json_loads(receipt_file.read_bytes())
    except codec.CodecError:
        raise
    except OSError as exc:
        _fail(
            codec.ReasonCode.READ_ERROR,
            stage=codec.Stage.DECODE,
            entity_id=entity_id,
            expected="readable parent lease receipt JSON",
            actual={"error": str(exc), "return_stage": "5"},
            resume_ref=rel_clean,
        )

    if type(receipt) is not dict or receipt.get("schema_version") != LEASE_RECEIPT_SCHEMA:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected=LEASE_RECEIPT_SCHEMA,
            actual={"schema_version": receipt.get("schema_version") if type(receipt) is dict else type(receipt).__name__, "return_stage": "5"},
            resume_ref=rel_clean,
        )

    expected_secret_hash = receipt.get("secret_sha256")
    actual_secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    if type(expected_secret_hash) is not str or not hmac.compare_digest(expected_secret_hash, actual_secret_hash):
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="matching parent lease secret SHA-256",
            actual={"spoofed_secret": True, "return_stage": "5"},
            resume_ref=rel_clean,
        )

    receipt_tids = receipt.get("task_ids")
    tid_matched = (receipt.get("task_id") == tid) or (
        isinstance(receipt_tids, list)
        and all(type(x) is int and not isinstance(x, bool) for x in receipt_tids)
        and tid in receipt_tids
    )
    if not tid_matched:
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"task_id": tid},
            actual={"task_id": receipt.get("task_id"), "task_ids": receipt_tids, "return_stage": "5"},
            resume_ref=rel_clean,
        )

    try:
        receipt_root = Path(str(receipt.get("root_resolved") or "")).resolve()
    except OSError:
        receipt_root = None
    if receipt_root != root_path.resolve():
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=str(root_path.resolve()),
            actual={"root_resolved": receipt.get("root_resolved"), "return_stage": "5"},
            resume_ref=rel_clean,
        )

    owner_pid = receipt.get("owner_pid")
    if type(owner_pid) is not int or not _is_pid_alive(owner_pid):
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="live parent owner_pid",
            actual={"owner_pid": owner_pid, "alive": False, "return_stage": "5"},
            resume_ref=rel_clean,
        )
    expected_create_time = receipt.get("owner_create_time")
    if expected_create_time is not None:
        actual_create_time = _get_process_create_time(owner_pid)
        if type(expected_create_time) is not int or actual_create_time != expected_create_time:
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="matching parent owner_create_time",
                actual={"owner_pid": owner_pid, "owner_create_time_match": False, "return_stage": "5"},
                resume_ref=rel_clean,
            )

    scope_ids = receipt.get("scope_ids")
    if type(scope_ids) is not list or not scope_ids or any(type(s) is not str or s == op_scope.WRITER_SCOPE for s in scope_ids):
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="nonempty business scope_ids without writer:planning",
            actual={"scope_ids": scope_ids, "return_stage": "5"},
            resume_ref=rel_clean,
        )

    # Probe OS byte lock non-blocking on EVERY claimed scope_id!
    for sid in scope_ids:
        if not _probe_scope_lock_is_held(root_path, sid):
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected=f"active OS byte lock held for scope {sid}",
                actual={"scope_id": sid, "os_lock_held": False, "return_stage": "5"},
                resume_ref=rel_clean,
            )

    per_task_digests = receipt.get("per_task_input_set_digests")
    digest = (
        per_task_digests.get(str(tid))
        if isinstance(per_task_digests, dict) and str(tid) in per_task_digests
        else receipt.get("input_set_digest")
    )
    if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
        _fail(
            codec.ReasonCode.INVALID_DIGEST,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected="sha256:<64 hex> input_set_digest in lease receipt",
            actual=digest,
            resume_ref=rel_clean,
        )

    return {**receipt, "input_set_digest": digest, "receipt_rel": rel_clean}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


@dataclass
class Chapter6ExecutionHandle:
    """Active handle yielded by guarded_chapter6_execution."""

    root: Path
    task_id: int
    operation: str | None
    consumer: str
    gate_result: dict[str, Any]
    input_set_snapshot: dict[str, Any] | None
    scope_ids: tuple[str, ...]
    inherited_lease: bool = False
    lease_receipt_path: str | None = None
    out_dir: Path | None = None
    uses_global_writer_lock: bool = False
    _events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def route(self) -> str:
        return str(self.gate_result.get("route") or "blocked")

    @property
    def input_set_digest(self) -> str | None:
        return self.gate_result.get("input_set_digest")

    @property
    def legacy_a_passthrough(self) -> bool:
        return bool(self.gate_result.get("legacy_a_passthrough"))

    def revalidate_boundary(
        self,
        step_name: str = "",
        *,
        model_invocation: bool = False,
        file_write: bool = False,
    ) -> dict[str, Any]:
        """Re-verify the gate & InputSet before model calls, file writes, or test steps."""
        started = time.monotonic()
        expected_digest = self.input_set_digest
        res, _live_iset = _evaluate_gate_core(
            self.root,
            self.task_id,
            operation=self.operation,
            expected_input_set_digest=expected_digest,
            expected_input_set_snapshot=self.input_set_snapshot,
            consumer=self.consumer,
            lock_mode="scope" if not self.legacy_a_passthrough else "none",
            check_legacy_a_obligations=True,
            started=started,
        )
        if not res["ok"]:
            record_chapter6_gate_event(
                self.root,
                task_id=self.task_id,
                consumer=self.consumer,
                event_kind="boundary_drift_stopped",
                gate_result=res,
                out_dir=self.out_dir,
                extra={
                    "step_name": step_name,
                    "model_invocation_blocked": bool(model_invocation),
                    "file_write_blocked": bool(file_write),
                },
            )
            raise Chapter6GateBlockedError(res)

        if not self.legacy_a_passthrough:
            live_scopes = tuple(res.get("scope_ids") or ())
            if self.inherited_lease:
                if not set(live_scopes).issubset(set(self.scope_ids)):
                    d = _diag(
                        codec.ReasonCode.INPUT_STALE,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(self.task_id),
                        expected=list(self.scope_ids),
                        actual={"scope_ids": list(live_scopes), "return_stage": "5"},
                    )
                    blocked = _blocked_result(
                        task_id=self.task_id,
                        operation=self.operation,
                        consumer=self.consumer,
                        lock_mode="scope",
                        route=str(res.get("route") or "B"),
                        reason_code=codec.ReasonCode.INPUT_STALE.value,
                        reason="scope_ids_expanded_beyond_parent_lease",
                        return_stage="5",
                        diagnostics=[d],
                        started=started,
                    )
                    record_chapter6_gate_event(
                        self.root,
                        task_id=self.task_id,
                        consumer=self.consumer,
                        event_kind="boundary_drift_stopped",
                        gate_result=blocked,
                        out_dir=self.out_dir,
                        extra={"step_name": step_name},
                    )
                    raise Chapter6GateBlockedError(blocked)
            elif live_scopes != self.scope_ids:
                d = _diag(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(self.task_id),
                    expected=list(self.scope_ids),
                    actual={"scope_ids": list(live_scopes), "return_stage": "5"},
                )
                blocked = _blocked_result(
                    task_id=self.task_id,
                    operation=self.operation,
                    consumer=self.consumer,
                    lock_mode="scope",
                    route=str(res.get("route") or "B"),
                    reason_code=codec.ReasonCode.INPUT_STALE.value,
                    reason="scope_ids_drifted",
                    return_stage="5",
                    diagnostics=[d],
                    started=started,
                )
                record_chapter6_gate_event(
                    self.root,
                    task_id=self.task_id,
                    consumer=self.consumer,
                    event_kind="boundary_drift_stopped",
                    gate_result=blocked,
                    out_dir=self.out_dir,
                    extra={"step_name": step_name},
                )
                raise Chapter6GateBlockedError(blocked)
        self.gate_result = res
        return res


@contextmanager
def guarded_chapter6_execution(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    consumer: str = "chapter6",
    out_dir: Path | str | None = None,
) -> Iterator[Chapter6ExecutionHandle]:
    """Acquire business-scope lease (or verify parent lease) and enforce unified Chapter 6 gate."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))
    tid = parse_strict_task_id(task_id)
    validated_op = task_resolver._validate_operation(operation)
    out_dir_path = Path(out_dir).resolve() if out_dir is not None else None

    env_path = os.environ.get(ENV_LEASE_PATH)
    env_secret = os.environ.get(ENV_LEASE_SECRET)

    # Child reentrancy path when parent lease env vars are present.
    if env_path is not None or env_secret is not None:
        try:
            receipt = _verify_inherited_lease_receipt(
                root_path,
                tid,
                str(env_path or ""),
                str(env_secret or ""),
            )
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            if d.get("entity_id") is None:
                d["entity_id"] = str(tid)
            blocked = _blocked_result(
                task_id=tid,
                operation=validated_op,
                consumer=consumer,
                lock_mode="scope",
                route="blocked",
                reason_code=d["reason_code"],
                reason=f"invalid_parent_lease:{d['reason_code']}",
                return_stage=_extract_return_stage_from_diag(d, default="5"),
                diagnostics=[d],
                started=started,
            )
            if out_dir_path is not None:
                record_chapter6_gate_event(
                    root_path,
                    task_id=tid,
                    consumer=consumer,
                    event_kind="blocked_gate",
                    gate_result=blocked,
                    out_dir=out_dir_path,
                )
            raise Chapter6GateBlockedError(blocked) from err

        res, live_iset = _evaluate_gate_core(
            root_path,
            tid,
            operation=validated_op,
            expected_input_set_digest=receipt["input_set_digest"],
            expected_input_set_snapshot=None,
            consumer=consumer,
            lock_mode="scope",
            check_legacy_a_obligations=True,
            started=started,
        )
        if not res["ok"]:
            if out_dir_path is not None:
                record_chapter6_gate_event(
                    root_path,
                    task_id=tid,
                    consumer=consumer,
                    event_kind="blocked_gate",
                    gate_result=res,
                    out_dir=out_dir_path,
                )
            raise Chapter6GateBlockedError(res)

        if not set(res.get("scope_ids") or ()).issubset(set(receipt["scope_ids"])):
            d = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected=receipt["scope_ids"],
                actual={"scope_ids": res.get("scope_ids"), "return_stage": "5"},
                resume_ref=receipt["receipt_rel"],
            )
            blocked = _blocked_result(
                task_id=tid,
                operation=validated_op,
                consumer=consumer,
                lock_mode="scope",
                route=str(res.get("route") or "B"),
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="child_scope_ids_exceed_parent_lease",
                return_stage="5",
                diagnostics=[d],
                started=started,
            )
            raise Chapter6GateBlockedError(blocked)

        handle = Chapter6ExecutionHandle(
            root=root_path,
            task_id=tid,
            operation=validated_op,
            consumer=consumer,
            gate_result=res,
            input_set_snapshot=live_iset,
            scope_ids=tuple(receipt["scope_ids"]),
            inherited_lease=True,
            lease_receipt_path=receipt["receipt_rel"],
            out_dir=out_dir_path,
            uses_global_writer_lock=False,
        )
        yield handle
        return

    # Top-level holder path: run read-only gate first to discover route and fail fast if blocked.
    pre_res, pre_iset = _evaluate_gate_core(
        root_path,
        tid,
        operation=validated_op,
        expected_input_set_digest=None,
        expected_input_set_snapshot=None,
        consumer=consumer,
        lock_mode="none",
        check_legacy_a_obligations=True,
        started=started,
    )
    if not pre_res["ok"]:
        if out_dir_path is not None:
            record_chapter6_gate_event(
                root_path,
                task_id=tid,
                consumer=consumer,
                event_kind="blocked_gate",
                gate_result=pre_res,
                out_dir=out_dir_path,
            )
        raise Chapter6GateBlockedError(pre_res)

    # Clean explicit_not_enabled_a: do NOT create B-route lock files in pure A repo!
    if pre_res["route"] == "explicit_not_enabled_a":
        handle = Chapter6ExecutionHandle(
            root=root_path,
            task_id=tid,
            operation=validated_op,
            consumer=consumer,
            gate_result=pre_res,
            input_set_snapshot=pre_iset,
            scope_ids=tuple(pre_res.get("scope_ids") or ()),
            inherited_lease=False,
            lease_receipt_path=None,
            out_dir=out_dir_path,
            uses_global_writer_lock=False,
        )
        yield handle
        return

    # Route B or frozen A: acquire business-scope lease via Story 3.5 guarded_input_set (NEVER writer:planning).
    try:
        iset_cm = input_set.guarded_input_set(root_path, tid, operation=validated_op)
        iset_handle = iset_cm.__enter__()
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None:
            d["entity_id"] = str(tid)
        blocked = _blocked_result(
            task_id=tid,
            operation=validated_op,
            consumer=consumer,
            lock_mode="scope",
            route=pre_res["route"],
            reason_code=d["reason_code"],
            reason=f"scope_lease_acquire_failed:{d['reason_code']}",
            return_stage=_extract_return_stage_from_diag(d, default="5"),
            diagnostics=[d],
            started=started,
        )
        if out_dir_path is not None:
            record_chapter6_gate_event(
                root_path,
                task_id=tid,
                consumer=consumer,
                event_kind="blocked_gate",
                gate_result=blocked,
                out_dir=out_dir_path,
            )
        raise Chapter6GateBlockedError(blocked) from err

    receipt_file: Path | None = None
    prev_env_path = os.environ.get(ENV_LEASE_PATH)
    prev_env_secret = os.environ.get(ENV_LEASE_SECRET)
    exc_info: tuple[Any, Any, Any] = (None, None, None)
    try:
        # Full gate evaluation INSIDE the active business-scope lease.
        entered_res, entered_iset = _evaluate_gate_core(
            root_path,
            tid,
            operation=validated_op,
            expected_input_set_digest=iset_handle.input_set_digest,
            expected_input_set_snapshot=iset_handle.snapshot,
            consumer=consumer,
            lock_mode="scope",
            check_legacy_a_obligations=True,
            started=started,
        )
        if not entered_res["ok"]:
            if out_dir_path is not None:
                record_chapter6_gate_event(
                    root_path,
                    task_id=tid,
                    consumer=consumer,
                    event_kind="blocked_gate",
                    gate_result=entered_res,
                    out_dir=out_dir_path,
                )
            raise Chapter6GateBlockedError(entered_res)

        lease_id = uuid.uuid4().hex[:16]
        secret = secrets.token_hex(32)
        receipt_rel = f"{LEASE_DIR}/task-{tid}-{lease_id}.json"
        lease_dir = root_path / LEASE_DIR
        lease_dir.mkdir(parents=True, exist_ok=True)
        receipt_file = root_path / receipt_rel
        receipt_payload = {
            "schema_version": LEASE_RECEIPT_SCHEMA,
            "lease_id": lease_id,
            "owner_pid": os.getpid(),
            "owner_create_time": _get_process_create_time(os.getpid()),
            "root_resolved": str(root_path.resolve()),
            "task_id": tid,
            "route": entered_res["route"],
            "scope_ids": list(iset_handle.scope_ids),
            "input_set_digest": iset_handle.input_set_digest,
            "applicable_set_digest": entered_res.get("applicable_set_digest"),
            "secret_sha256": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            **INVARIANT_FLAGS,
        }
        _atomic_write_json(receipt_file, receipt_payload)

        os.environ[ENV_LEASE_PATH] = receipt_rel
        os.environ[ENV_LEASE_SECRET] = secret

        handle = Chapter6ExecutionHandle(
            root=root_path,
            task_id=tid,
            operation=validated_op,
            consumer=consumer,
            gate_result=entered_res,
            input_set_snapshot=entered_iset or iset_handle.snapshot,
            scope_ids=tuple(iset_handle.scope_ids),
            inherited_lease=False,
            lease_receipt_path=receipt_rel,
            out_dir=out_dir_path,
            uses_global_writer_lock=False,
        )
        yield handle
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        if prev_env_path is None:
            os.environ.pop(ENV_LEASE_PATH, None)
        else:
            os.environ[ENV_LEASE_PATH] = prev_env_path
        if prev_env_secret is None:
            os.environ.pop(ENV_LEASE_SECRET, None)
        else:
            os.environ[ENV_LEASE_SECRET] = prev_env_secret
        if receipt_file is not None and receipt_file.exists():
            try:
                receipt_file.unlink()
            except OSError:
                pass
        iset_cm.__exit__(*exc_info)


# ---------------------------------------------------------------------------
# Protected State Writers & test_refs Sync Guard
# ---------------------------------------------------------------------------


def validate_taskmaster_status_write_guard(
    root: Path | str,
    task_id: Any,
    to_status: str,
    *,
    sync_views: bool = False,
    target_views: tuple[str, ...] | list[str] = ("back", "gameplay"),
) -> tuple[Path, int, tuple[str, ...], tuple[str, ...]]:
    """Validate status enum, view subset, B-route presence/origin, and pending markers before writing."""
    root_path = task_resolver._validate_root(Path(root))
    tid = parse_strict_task_id(task_id)
    if type(to_status) is not str or to_status not in inventory.MASTER_STATES:
        _fail(
            codec.ReasonCode.INVALID_ENUM,
            stage=codec.Stage.CONTENT,
            entity_id=str(tid),
            expected=sorted(inventory.MASTER_STATES),
            actual=to_status,
        )

    selected_views: tuple[str, ...] = ()
    if sync_views:
        if isinstance(target_views, (str, bytes)):
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected="nonempty subset of ('back', 'gameplay')",
                actual=target_views,
            )
        selected_views = tuple(dict.fromkeys(str(v) for v in target_views))
        if not selected_views or any(v not in ("back", "gameplay") for v in selected_views):
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected="nonempty subset of ('back', 'gameplay')",
                actual=target_views,
            )
        if to_status not in inventory.VIEW_STATES:
            _fail(
                codec.ReasonCode.INVALID_ENUM,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected=sorted(inventory.VIEW_STATES),
                actual=to_status,
            )

    presence = detect_b_route_presence(root_path, tid)
    if (
        presence["capability_apply_pending"]
        or presence["pending_journals"]
        or presence["na_labels"]
    ):
        _fail(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(tid),
            expected="zero pending apply markers, journals, or non-authoritative N/A labels before status write",
            actual={
                "capability_apply_pending": presence["capability_apply_pending"],
                "pending_journals": presence["pending_journals"],
                "na_labels": presence["na_labels"],
                "return_stage": "5",
            },
            resume_ref=op_scope.CAP_PENDING if presence["capability_apply_pending"] else task_resolver.TRIPLET["master"],
        )
    if presence["has_b_traces"]:
        origin = task_resolver.resolve_task_origin(root_path, tid)
        if (
            origin.get("route") == "blocked"
            or not origin.get("ok")
            or not origin.get("stable")
            or (origin.get("route") == "A" and not origin.get("a_write_allowed", True))
        ):
            diags = list(origin.get("diagnostics") or [])
            resume_ref = diags[0].get("resume_ref") if diags and isinstance(diags[0], dict) else task_resolver.ORIGINS_PATH
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected="unblocked task origin with write permission before status write",
                actual={
                    "route": origin.get("route"),
                    "ok": origin.get("ok"),
                    "a_write_allowed": origin.get("a_write_allowed", True),
                    "return_stage": "3C",
                },
                resume_ref=resume_ref,
            )

    master_rel = task_resolver.TRIPLET["master"]
    target_paths = [master_rel] + [task_resolver.TRIPLET[v] for v in selected_views]
    scopes = op_scope.resource_scopes(target_paths=target_paths, task_ids=[tid])
    return root_path, tid, selected_views, scopes


def write_taskmaster_status_guarded(
    root: Path | str,
    task_id: Any,
    to_status: str,
    *,
    sync_views: bool = False,
    target_views: tuple[str, ...] | list[str] = ("back", "gameplay"),
) -> dict[str, Any]:
    """Update Task status under a short scope_guard, keeping tasks.json sole authority and projection invariant."""
    root_path, tid, selected_views, scopes = validate_taskmaster_status_write_guard(
        root,
        task_id,
        to_status,
        sync_views=sync_views,
        target_views=target_views,
    )
    master_rel = task_resolver.TRIPLET["master"]

    def _prepare_status_update() -> dict[str, Any]:
        master_path = inventory.safe_input(root_path, master_rel, allow_logs=False)
        master_doc = codec.strict_json_loads(master_path.read_bytes())
        tasks_list = ((master_doc.get("master") or {}).get("tasks")) if type(master_doc) is dict else None
        if type(tasks_list) is not list:
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected="master.tasks list in tasks.json",
                actual=type(tasks_list).__name__,
                resume_ref=master_rel,
            )
        target_row = next((row for row in tasks_list if type(row) is dict and row.get("id") == tid), None)
        if target_row is None:
            _fail(
                codec.ReasonCode.UNKNOWN_ENTITY,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected=f"master task id {tid} in {master_rel}",
                actual="not found",
                resume_ref=master_rel,
            )

        before_proj = protection.task_definition_projection(target_row)
        from_status = target_row.get("status")
        updated_master = deepcopy(master_doc)
        updated_row = next(row for row in updated_master["master"]["tasks"] if row.get("id") == tid)
        updated_row["status"] = to_status
        after_proj = protection.task_definition_projection(updated_row)
        if codec.canonical_digest(before_proj) != codec.canonical_digest(after_proj):
            _fail(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.CONTENT,
                entity_id=str(tid),
                expected="invariant task_definition_projection across status write",
                actual="definition projection changed",
                resume_ref=master_rel,
            )

        view_updates: list[tuple[Path, Any]] = []
        if sync_views:
            for view_name in selected_views:
                vrel = task_resolver.TRIPLET[view_name]
                vpath = inventory.safe_input(root_path, vrel, allow_logs=False)
                if not vpath.is_file():
                    continue
                vdoc = codec.strict_json_loads(vpath.read_bytes())
                if type(vdoc) is not list:
                    continue
                v_updated = deepcopy(vdoc)
                changed_v = False
                for vrow in v_updated:
                    if type(vrow) is dict and vrow.get("taskmaster_id") == tid:
                        vb = protection.task_definition_projection(vrow)
                        vrow["status"] = to_status
                        va = protection.task_definition_projection(vrow)
                        if codec.canonical_digest(vb) != codec.canonical_digest(va):
                            _fail(
                                codec.ReasonCode.CONFLICT,
                                stage=codec.Stage.CONTENT,
                                entity_id=str(tid),
                                expected="invariant view task_definition_projection",
                                actual="view definition projection changed",
                                resume_ref=vrel,
                            )
                        changed_v = True
                if changed_v:
                    view_updates.append((vpath, v_updated))

        return {
            "master_path": master_path,
            "updated_master": updated_master,
            "view_updates": view_updates,
            "from_status": from_status,
            "to_status": to_status,
            "definition_digest": codec.canonical_digest(after_proj),
        }

    env_path = os.environ.get(ENV_LEASE_PATH)
    env_secret = os.environ.get(ENV_LEASE_SECRET)
    if env_path is not None or env_secret is not None:
        receipt = _verify_inherited_lease_receipt(
            root_path,
            tid,
            str(env_path or ""),
            str(env_secret or ""),
        )
        held_scopes = set(receipt["scope_ids"])
        unheld_scopes = tuple(s for s in scopes if s not in held_scopes)
        if not unheld_scopes:
            prepared = _prepare_status_update()
            _atomic_write_json(prepared["master_path"], prepared["updated_master"])
            for vpath, vdoc in prepared["view_updates"]:
                _atomic_write_json(vpath, vdoc)
        else:
            with op_scope.scope_guard(root_path, unheld_scopes, prepare_under_lease=_prepare_status_update) as prepared:
                _atomic_write_json(prepared["master_path"], prepared["updated_master"])
                for vpath, vdoc in prepared["view_updates"]:
                    _atomic_write_json(vpath, vdoc)
    else:
        with op_scope.scope_guard(root_path, scopes, prepare_under_lease=_prepare_status_update) as prepared:
            _atomic_write_json(prepared["master_path"], prepared["updated_master"])
            for vpath, vdoc in prepared["view_updates"]:
                _atomic_write_json(vpath, vdoc)

    return {
        "ok": True,
        "task_id": tid,
        "authority_path": master_rel,
        "from_status": prepared["from_status"],
        "to_status": prepared["to_status"],
        "sync_views": bool(sync_views),
        "target_views": list(selected_views),
        "definition_projection_preserved": True,
        "task_definition_digest": prepared["definition_digest"],
        **INVARIANT_FLAGS,
    }


def guard_task_test_refs_sync(
    root: Path | str,
    task_id: Any,
    *,
    changed: bool,
) -> dict[str, Any]:
    """Guard test_refs sync helpers: zero write if unchanged; block B-route and frozen-A mutation."""
    try:
        root_path = task_resolver._validate_root(Path(root))
        tid = parse_strict_task_id(task_id)
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        return {
            "ok": False,
            "allow_write": False,
            "changed": bool(changed),
            "task_id": None,
            "route": "blocked",
            "reason_code": d["reason_code"],
            "return_stage": _extract_return_stage_from_diag(d, default="5"),
            "message": f"invalid_arguments:{d['reason_code']}",
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }
    if not changed:
        return {
            "ok": True,
            "allow_write": False,
            "changed": False,
            "task_id": tid,
            "reason_code": codec.ReasonCode.OK.value,
            "return_stage": None,
            "message": "unchanged_zero_write",
            "diagnostics": [],
            **INVARIANT_FLAGS,
        }

    presence = detect_b_route_presence(root_path, tid)
    if (
        presence["has_b_traces"]
        or presence["capability_apply_pending"]
        or presence["pending_journals"]
        or presence["na_labels"]
    ):
        origin = task_resolver.resolve_task_origin(root_path, tid)
        route = str(origin.get("route") or "blocked")
        if route in ("B", "A", "blocked") or not origin.get("ok") or not origin.get("stable"):
            expected_msg = (
                "governed Story 1.5/3C update for frozen-A task test_refs (no Chapter 6 mutation)"
                if route == "A"
                else "governed 3C/Chapter 4-5 update for B-route task test_refs (no Chapter 6 mutation)"
            )
            d = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected=expected_msg,
                actual={"route": route, "changed": True, "return_stage": "3C"},
                resume_ref=task_resolver.TRIPLET["back"],
            )
            return {
                "ok": False,
                "allow_write": False,
                "changed": True,
                "task_id": tid,
                "route": route,
                "reason_code": codec.ReasonCode.CONFLICT.value,
                "return_stage": "3C",
                "message": (
                    "frozen_a_test_refs_mutation_blocked_in_chapter6"
                    if route == "A"
                    else "b_route_test_refs_mutation_blocked_in_chapter6"
                ),
                "diagnostics": [d],
                **INVARIANT_FLAGS,
            }

    return {
        "ok": True,
        "allow_write": True,
        "changed": True,
        "task_id": tid,
        "reason_code": codec.ReasonCode.OK.value,
        "return_stage": None,
        "message": "write_allowed",
        "diagnostics": [],
        **INVARIANT_FLAGS,
    }


# ---------------------------------------------------------------------------
# Observability Events & Report Writer
# ---------------------------------------------------------------------------


def record_chapter6_gate_event(
    root: Path | str,
    *,
    task_id: int | str | None,
    consumer: str,
    event_kind: str,
    gate_result: dict[str, Any] | None = None,
    out_dir: Path | str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Append one deterministic JSONL event under logs/ci/.../chapter6-gate-events.jsonl."""
    root_path = Path(root).resolve()
    kind = event_kind if event_kind in VALID_EVENT_KINDS else "execution"
    tid_label = str(task_id) if task_id is not None else "unknown"
    if out_dir is not None:
        base_dir = Path(out_dir)
        if not base_dir.is_absolute():
            base_dir = (root_path / base_dir).resolve()
    else:
        base_dir = (root_path / DEFAULT_EVENTS_DIR / f"task-{tid_label}").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    events_file = base_dir / "chapter6-gate-events.jsonl"
    gate = gate_result if isinstance(gate_result, dict) else {}
    metrics = gate.get("metrics") if isinstance(gate.get("metrics"), dict) else {}
    record = {
        "schema_version": EVENT_SCHEMA,
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "task_id": gate.get("task_id", task_id),
        "consumer": str(consumer or "chapter6"),
        "event_kind": kind,
        "route": gate.get("route"),
        "ok": bool(gate.get("ok")),
        "reason_code": gate.get("reason_code"),
        "return_stage": gate.get("return_stage"),
        "input_set_digest": gate.get("input_set_digest"),
        "active_elapsed_seconds": float(metrics.get("active_elapsed_seconds") or 0.0),
        "model_invocation_count": int(metrics.get("model_invocation_count") or 0),
        "reused": bool(metrics.get("reused") or kind == "reuse"),
        "extra": dict(extra or {}),
        **INVARIANT_FLAGS,
    }
    line = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    with events_file.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line)
        stream.flush()
    try:
        return events_file.relative_to(root_path).as_posix()
    except ValueError:
        return str(events_file).replace("\\", "/")


def write_report(root: Path | str, report_path: str | Path, payload: dict[str, Any]) -> str:
    """Write a read-only gate report strictly under logs/ci/ with reparse protection."""
    root_path = task_resolver._validate_root(Path(root))
    target, rel = ch5_b._validate_log_path(root_path, report_path, require_logs=True)
    if not rel.startswith("logs/ci/") or not rel.endswith(".json"):
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="repository-relative JSON path under logs/ci/",
            actual=rel,
        )
    out = deepcopy(payload)
    out["report_path"] = rel
    out["runtime_verified"] = False
    out["default_b_enabled"] = False
    _atomic_write_json(target, out)
    return rel


# ---------------------------------------------------------------------------
# Lightweight Helper for Code Map Internal Scripts & Public CLI Consumers
# ---------------------------------------------------------------------------


def enforce_internal_script_gate(
    root: Path | str,
    task_id: Any,
    *,
    consumer: str,
    operation: str | None = None,
) -> dict[str, Any]:
    """Enforce the unified Chapter 6 gate on internal scripts and CLI subcommands.

    - Always validates strict ASCII positive integer task_id.
    - When the repo has any B-route trace, B readiness/reconciliation marker,
      pending apply marker/journal, non-authoritative N/A label, lease env var,
      or ADR-0040, runs the full unified gate (including parent lease
      verification when ENV_LEASE_* is set).
    - On synthetic legacy-only unit-test temp repos with zero B traces and no
      ADR-0040, returns a clean legacy passthrough without writing any files.
    """
    started = time.monotonic()
    try:
        root_path = task_resolver._validate_root(Path(root))
        tid = parse_strict_task_id(task_id)
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        return _blocked_result(
            task_id=None,
            operation=operation,
            consumer=consumer,
            lock_mode="none",
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_arguments:{d['reason_code']}",
            return_stage=_extract_return_stage_from_diag(d, default="5"),
            diagnostics=[d],
            started=started,
        )

    presence = detect_b_route_presence(root_path, tid)
    if not presence["should_enforce_gate"]:
        elapsed = round(max(0.0, time.monotonic() - started), 6)
        return {
            "schema_version": SCHEMA,
            "ok": True,
            "stable": True,
            "execution_allowed": True,
            "task_id": tid,
            "operation": operation,
            "consumer": consumer,
            "route": "explicit_not_enabled_a",
            "legacy_a_passthrough": True,
            "reason_code": codec.ReasonCode.OK.value,
            "reason": "legacy_synthetic_passthrough",
            "return_stage": None,
            "lock_mode": "none",
            "uses_global_writer_lock": False,
            "input_set_digest": None,
            "applicable_set_digest": None,
            "scope_ids": [],
            "plan_refs": [],
            "binding_refs": [],
            "readiness": None,
            "closure_allowed": True,
            "requires_chapter6_reverification": False,
            "old_done_covers_new_obligations": False,
            "self_done_required": False,
            "stage5_summary": None,
            "readiness_path": None,
            "reconciliation_path": None,
            "reconciliation_sha256": None,
            "milestone_handoff_paths": [],
            "metrics": {
                "active_elapsed_seconds": elapsed,
                "model_invocation_count": 0,
                "reused": False,
            },
            "diagnostics": [],
            "report_path": None,
            **INVARIANT_FLAGS,
        }

    # If parent lease env vars are present, verify them strictly (rejecting forged env vars!).
    env_path = os.environ.get(ENV_LEASE_PATH)
    env_secret = os.environ.get(ENV_LEASE_SECRET)
    expected_digest: str | None = None
    if env_path is not None or env_secret is not None:
        try:
            receipt = _verify_inherited_lease_receipt(
                root_path,
                tid,
                str(env_path or ""),
                str(env_secret or ""),
            )
            expected_digest = receipt["input_set_digest"]
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            if d.get("entity_id") is None:
                d["entity_id"] = str(tid)
            return _blocked_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                lock_mode="scope",
                route="blocked",
                reason_code=d["reason_code"],
                reason=f"invalid_parent_lease:{d['reason_code']}",
                return_stage=_extract_return_stage_from_diag(d, default="5"),
                diagnostics=[d],
                started=started,
            )

    return evaluate_chapter6_gate(
        root_path,
        tid,
        operation=operation,
        expected_input_set_digest=expected_digest,
        consumer=consumer,
        lock_mode="none",
        check_legacy_a_obligations=True,
        enforce_eligibility=(consumer != "mvg_obligations"),
    )


def format_gate_block_message(consumer: str, gate_result: dict[str, Any]) -> str:
    """Format a uniform machine-parseable block message for CLI and internal scripts."""
    reason_code = gate_result.get("reason_code") or "conflict"
    return_stage = gate_result.get("return_stage") or "5"
    reason = gate_result.get("reason") or "blocked"
    return (
        f"[{consumer}] BLOCKED by b-route-chapter6-gate: "
        f"reason_code={reason_code} return_stage={return_stage} reason={reason}"
    )
