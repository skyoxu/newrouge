"""Live B-route revalidation, read-only recovery guard, drift stop, and anti-whitewash checks.

Responsibilities:
- Revalidate live Story 3.8 unified gate (InputSet, Chapter 5 readiness, Stage-5 obligations)
  and live Task/dependency eligibility before every recommendation, route, resume, or fork.
- Guarantee strictly zero writes on recommendation-only evaluation.
- Detect pending/damaged markers and journals (capability-apply.pending.json, legacy apply
  journals, unfinished B-route operation journals) and preserve user post-edits on pre-image
  / post-image mismatch without overwriting or auto-applying.
- Allow status-only advances in tasks.json and unrelated scope/HEAD/catalog changes without
  rewriting historical journal after-snapshots or rejecting non-done target Tasks.
- Freeze and compare per-run InputSet snapshots across resume/fork boundaries under public
  lock order (short metadata -> sorted union of business scope_ids; never writer:planning).
- Enforce durable failure budgets, rerun_guard/stop-loss signals across all date directories
  (even when active-task or latest.json is deleted or a new run_id is started or Knowledge
  is rebuilt), and honor Story 2.9 epoch/reopen revocations.
- Unconditionally maintain runtime_verified=False and default_b_enabled=False.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Iterator
import uuid

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _planning_apply_journal as journal
import _b_route_operation_scope as op_scope
import _b_route_preflight as preflight
import _b_route_task_resolver as task_resolver
import _mvg_capability_recovery as mvg_recovery


SCHEMA = "newrouge.b-route-chapter6-recovery.v1"
RECOVERY_INPUT_SET_SCHEMA = "newrouge.b-route-chapter6-recovery-input-set.v1"
RECOVERY_INPUT_SET_FILENAME = "recovery-input-set.json"
REOPEN_DIR = "logs/ci/b-route-reopen"

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

_STOP_LOSS_DIAG_KEYS = (
    "rerun_guard",
    "sc_test_retry_stop_loss",
    "llm_retry_stop_loss",
    "waste_signals",
)

_PRODUCT_ROOT_DIRS = (
    "Game.Core",
    "Game.Core.Tests",
    "Game.Godot",
    "Tests.Godot",
    "Scenes",
    "Scripts",
)

_PRODUCT_FILE_EXTENSIONS = frozenset(
    {
        ".cs",
        ".gd",
        ".tscn",
        ".tres",
        ".res",
        ".json",
        ".cfg",
        ".csproj",
        ".sln",
    }
)

_NON_PRODUCT_PREFIXES = (
    "scripts/python/",
    "scripts/sc/",
    "scripts/ci/",
    "logs/",
    "docs/knowledge/",
    ".taskmaster/",
    "_bmad-output/",
)

_EXCLUDED_DIR_PARTS = frozenset(
    {
        "__pycache__",
        "bin",
        "obj",
        ".godot",
        ".git",
        "node_modules",
    }
)

_READONLY_ROUTE_CONSUMERS = frozenset(
    {
        "resume_task",
        "chapter6_route",
        "inspect_run",
    }
)

_NEEDS_FIX_BLOCKING_STOP_LOSS = frozenset(
    {
        "sc_test_retry_stop_loss",
        "waste_signals",
        "failure_budget_exhausted",
        "repeat_deterministic_failure",
    }
)

_INELIGIBLE_TASK_STATUSES = frozenset(
    {
        "cancelled",
        "canceled",
        "retired",
        "deleted",
    }
)


class Chapter6RecoveryBlockedError(ch6_gate.Chapter6GateBlockedError):
    """Raised when Chapter 6 recovery validation or boundary revalidation blocks execution."""

    def __init__(self, recovery_result: dict[str, Any]):
        self.recovery_result = deepcopy(recovery_result)
        super().__init__(recovery_result)


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


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _safe_read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except OSError:
        return []
    return rows


def _repo_rel(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _extract_resume_ref(diags: list[dict[str, Any]]) -> str | None:
    for item in diags:
        if isinstance(item, dict):
            ref = item.get("resume_ref")
            if isinstance(ref, str) and ref.strip():
                return ref.strip()
    return None


def _file_raw_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return codec.raw_digest(path.read_bytes())
    except OSError:
        return None


def _normalize_digest_hex(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    val = raw.strip().lower()
    if val.startswith("sha256:"):
        val = val.split(":", 1)[1]
    return val if re.fullmatch(r"[0-9a-f]{64}", val) else None


def _check_journal_target_post_edits(
    root_path: Path,
    targets: list[dict[str, Any]],
    *,
    resume_ref: str,
    entity_id: str,
) -> dict[str, Any] | None:
    """Detect user post-edits on journal targets without touching disk."""
    for target in targets:
        if not isinstance(target, dict):
            continue
        rel = str(target.get("path") or target.get("target_path") or "").strip().replace("\\", "/")
        if not rel:
            continue
        try:
            target_file = inventory.safe_input(root_path, rel, allow_logs=True)
        except (codec.CodecError, ValueError, OSError) as exc:
            return _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected={"path": rel, "safe_contained_path": True},
                actual={"path": rel, "error": f"{type(exc).__name__}: {exc}", "post_edit_detected": True},
                resume_ref=resume_ref,
            )
        before_hex = _normalize_digest_hex(
            target.get("before_sha256")
            or target.get("before_digest")
            or target.get("before_raw_digest")
            or target.get("pre_image_sha256")
            or target.get("preimage_digest")
        )
        after_hex = _normalize_digest_hex(
            target.get("after_sha256")
            or target.get("after_digest")
            or target.get("after_raw_digest")
            or target.get("post_image_sha256")
            or target.get("postimage_digest")
        )
        before_exists = target.get("before_exists")
        has_before_field = any(
            k in target
            for k in ("before_sha256", "before_digest", "before_raw_digest", "pre_image_sha256", "preimage_digest")
        )
        if not os.path.lexists(target_file):
            if before_hex is not None or before_exists is True:
                return _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"path": rel, "before_sha256": before_hex, "after_sha256": after_hex},
                    actual={"path": rel, "exists": False, "post_edit_detected": True},
                    resume_ref=resume_ref,
                )
            continue
        try:
            inventory.no_reparse(target_file)
            if not target_file.is_file():
                return _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.PATH,
                    entity_id=entity_id,
                    expected={"path": rel, "regular_file": True},
                    actual={"path": rel, "regular_file": False, "post_edit_detected": True},
                    resume_ref=resume_ref,
                )
            live_digest = codec.raw_digest(target_file.read_bytes())
        except (codec.CodecError, OSError, ValueError) as exc:
            return _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected={"path": rel, "readable_regular_file": True},
                actual={"path": rel, "error": f"{type(exc).__name__}: {exc}", "post_edit_detected": True},
                resume_ref=resume_ref,
            )
        live_hex = _normalize_digest_hex(live_digest)
        allowed = {h for h in (before_hex, after_hex) if h is not None}
        if allowed and live_hex is not None and live_hex not in allowed:
            return _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"path": rel, "allowed_sha256": sorted(allowed)},
                actual={"path": rel, "live_sha256": live_hex, "post_edit_detected": True},
                resume_ref=resume_ref,
            )
        if not allowed and (before_exists is False or has_before_field) and live_hex is not None:
            return _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"path": rel, "before_exists": False, "after_sha256": None},
                actual={"path": rel, "live_sha256": live_hex, "post_edit_detected": True},
                resume_ref=resume_ref,
            )
    return None


_INCOMPLETE_EXTERNAL_STATES = frozenset(
    {
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
    }
)


def _extract_doc_task_ids(doc: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for key in ("task_id",):
        val = doc.get(key)
        if type(val) is int and not isinstance(val, bool) and val >= 1:
            out.add(val)
        elif type(val) is str and val.isdigit() and val.isascii() and int(val) >= 1:
            out.add(int(val))
    for key in ("task_ids",):
        vals = doc.get(key)
        if isinstance(vals, list):
            for v in vals:
                if type(v) is int and not isinstance(v, bool) and v >= 1:
                    out.add(v)
                elif type(v) is str and v.isdigit() and v.isascii() and int(v) >= 1:
                    out.add(int(v))
    frozen = doc.get("frozen")
    if isinstance(frozen, dict):
        alloc = frozen.get("allocations")
        if isinstance(alloc, dict):
            for trow in alloc.get("task_definitions") or []:
                if isinstance(trow, dict):
                    out.update(_extract_doc_task_ids(trow))
        req = frozen.get("request")
        if isinstance(req, dict):
            out.update(_extract_doc_task_ids(req))
    req_top = doc.get("request")
    if isinstance(req_top, dict):
        out.update(_extract_doc_task_ids(req_top))
    return out


def _operation_overlaps_scope(doc: dict[str, Any], tid: int, scope_set: set[str] | None) -> bool:
    if scope_set is None:
        return True
    doc_tids = _extract_doc_task_ids(doc)
    if tid >= 1 and tid in doc_tids:
        return True
    raw_scopes: list[Any] = []
    for src in (doc, doc.get("frozen") if isinstance(doc.get("frozen"), dict) else None):
        if isinstance(src, dict):
            for k in ("scope_ids", "scopes"):
                vals = src.get(k)
                if isinstance(vals, list):
                    raw_scopes.extend(vals)
            pid = src.get("plan_id")
            if isinstance(pid, str) and pid.strip():
                raw_scopes.extend(op_scope.resource_scopes(plan_ids=[pid.strip()]))
    op_scopes = {str(s).strip() for s in raw_scopes if isinstance(s, str) and str(s).strip()}
    for dtid in doc_tids:
        op_scopes.update(op_scope.resource_scopes(task_ids=[dtid]))
    if not op_scopes:
        return True
    return bool(op_scopes & scope_set)


def _inspect_pending_and_post_edits(
    root_path: Path,
    tid: int,
    *,
    scope_ids: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, Any]:
    """Read-only inspection of pending markers, legacy apply journals, and B-route operations."""
    entity_id = str(tid)
    scope_set = {str(s) for s in scope_ids if str(s).strip()} if scope_ids is not None else None
    legacy_routes: list[dict[str, Any]] = []
    pending_ops: list[dict[str, Any]] = []

    # 1. Check capability-apply.pending.json and top-level legacy apply-journal.json routes.
    try:
        legacy_routes = list(op_scope.legacy_recovery_routes(root_path))
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        if diag.get("entity_id") is None:
            diag["entity_id"] = entity_id
        rref = diag.get("resume_ref") or op_scope.CAP_PENDING
        raw_rc = str(diag.get("reason_code") or codec.ReasonCode.CONFLICT.value)
        mapped_rc = (
            codec.ReasonCode.CONFLICT.value
            if raw_rc in {codec.ReasonCode.INVALID_JSON.value, codec.ReasonCode.SCHEMA_VALIDATION_FAILED.value}
            else raw_rc
        )
        diag["reason_code"] = mapped_rc
        return {
            "ok": False,
            "blocked": True,
            "reason_code": mapped_rc,
            "reason": f"damaged_legacy_pending_journal:{mapped_rc}",
            "return_stage": "3C",
            "resume_ref": rref,
            "post_edit_preserved": True,
            "legacy_routes": [],
            "pending_operations": [],
            "diagnostics": [diag],
        }
    except (OSError, ValueError) as exc:
        diag = _diag(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="readable legacy pending markers and apply journals",
            actual=f"{type(exc).__name__}: {exc}",
            resume_ref=op_scope.CAP_PENDING,
        )
        return {
            "ok": False,
            "blocked": True,
            "reason_code": diag["reason_code"],
            "reason": "legacy_pending_read_error",
            "return_stage": "3C",
            "resume_ref": op_scope.CAP_PENDING,
            "post_edit_preserved": True,
            "legacy_routes": [],
            "pending_operations": [],
            "diagnostics": [diag],
        }

    if legacy_routes:
        for route_entry in legacy_routes:
            jrel = str(route_entry.get("journal_path") or route_entry.get("resume_ref") or op_scope.CAP_PENDING)
            jpath = root_path / jrel
            jdoc: dict[str, Any] | None = None
            if os.path.lexists(jpath):
                try:
                    inventory.no_reparse(jpath)
                    if not jpath.is_file():
                        raise ValueError("legacy journal path is not a regular file")
                    parsed_jdoc = codec.strict_json_loads(jpath.read_bytes())
                    if not isinstance(parsed_jdoc, dict):
                        raise ValueError("legacy journal JSON root must be an object")
                    jdoc = parsed_jdoc
                except (codec.CodecError, OSError, ValueError) as exc:
                    diag = _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.DECODE,
                        entity_id=entity_id,
                        expected="valid legacy apply journal JSON",
                        actual={"path": jrel, "error": f"{type(exc).__name__}: {exc}", "return_stage": "3C"},
                        resume_ref=jrel,
                    )
                    return {
                        "ok": False,
                        "blocked": True,
                        "reason_code": codec.ReasonCode.CONFLICT.value,
                        "reason": "damaged_legacy_apply_journal",
                        "return_stage": "3C",
                        "resume_ref": jrel,
                        "post_edit_preserved": True,
                        "legacy_routes": legacy_routes,
                        "pending_operations": [],
                        "diagnostics": [diag],
                    }
            targets = list((jdoc or {}).get("entries") or (jdoc or {}).get("targets") or (jdoc or {}).get("writes") or [])
            post_edit_diag = _check_journal_target_post_edits(
                root_path,
                targets,
                resume_ref=jrel,
                entity_id=entity_id,
            )
            if post_edit_diag is not None:
                return {
                    "ok": False,
                    "blocked": True,
                    "reason_code": codec.ReasonCode.CONFLICT.value,
                    "reason": "legacy_journal_post_edit_conflict",
                    "return_stage": "3C",
                    "resume_ref": jrel,
                    "post_edit_preserved": True,
                    "legacy_routes": legacy_routes,
                    "pending_operations": [],
                    "diagnostics": [post_edit_diag],
                }
        first = legacy_routes[0]
        jrel = str(first.get("journal_path") or first.get("resume_ref") or op_scope.CAP_PENDING)
        diag = _diag(
            codec.ReasonCode.PENDING,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected="resolved legacy apply journal via owning public apply contract",
            actual={
                "kind": first.get("kind"),
                "run_id": first.get("run_id"),
                "scope": first.get("scope") or "unknown",
                "owner_api": first.get("owner_api"),
                "requires_original_confirmation": True,
                "return_stage": "3C",
            },
            resume_ref=jrel,
        )
        return {
            "ok": False,
            "blocked": True,
            "reason_code": codec.ReasonCode.PENDING.value,
            "reason": f"legacy_pending_journal:{first.get('kind') or 'unknown'}",
            "return_stage": "3C",
            "resume_ref": jrel,
            "post_edit_preserved": True,
            "legacy_routes": legacy_routes,
            "pending_operations": [],
            "diagnostics": [diag],
        }

    # 2. Check hashed B-route operation store for unfinished or damaged operations and post-edits.
    ops_dir = root_path / op_scope.STORE / "operations"
    if ops_dir.is_dir():
        try:
            graph = journal.operation_state_graph(root_path)
        except codec.CodecError as err:
            diag = err.diagnostic.to_dict()
            if diag.get("entity_id") is None:
                diag["entity_id"] = entity_id
            rref = diag.get("resume_ref") or op_scope.STORE
            raw_rc = str(diag.get("reason_code") or codec.ReasonCode.CONFLICT.value)
            mapped_rc = (
                raw_rc
                if raw_rc == codec.ReasonCode.UNSAFE_PATH.value
                else codec.ReasonCode.CONFLICT.value
            )
            diag["reason_code"] = mapped_rc
            return {
                "ok": False,
                "blocked": True,
                "reason_code": mapped_rc,
                "reason": f"damaged_b_route_operation_store:{mapped_rc}",
                "return_stage": "3C",
                "resume_ref": rref,
                "post_edit_preserved": True,
                "legacy_routes": [],
                "pending_operations": [],
                "diagnostics": [diag],
            }
        terminals = graph.get("terminals") or {}
        resolved_by = graph.get("resolved_by") or {}
        intents = graph.get("intents") or {}
        local_bytes = graph.get("local_bytes") or {}
        for op in graph.get("operations") or []:
            op_id = op.get("operation_id")
            if op_id in terminals or op_id in resolved_by:
                continue
            op_ref = journal._operation_ref(op_id)
            op_dir = op_ref.rsplit("/", 1)[0]
            pub_sync_rel = op_dir + "/public-sync-journal.json"
            pub_sync_raw = local_bytes.get(pub_sync_rel)
            targets_to_check: list[dict[str, Any]] = []
            frozen_doc = op.get("frozen") if isinstance(op.get("frozen"), dict) else {}
            if isinstance(frozen_doc.get("targets"), list):
                targets_to_check.extend(r for r in frozen_doc["targets"] if isinstance(r, dict))
            if pub_sync_raw is not None:
                try:
                    pub_doc = codec.strict_json_loads(pub_sync_raw)
                    if not isinstance(pub_doc, dict):
                        raise ValueError("public-sync-journal.json root must be an object")
                    for key in ("targets", "writes", "files", "entries"):
                        rows = pub_doc.get(key)
                        if isinstance(rows, list):
                            targets_to_check.extend(r for r in rows if isinstance(r, dict))
                except (codec.CodecError, OSError, ValueError) as exc:
                    diag = _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.DECODE,
                        entity_id=entity_id,
                        expected="valid public-sync-journal.json",
                        actual={"path": pub_sync_rel, "error": f"{type(exc).__name__}: {exc}", "return_stage": "3C"},
                        resume_ref=pub_sync_rel,
                    )
                    return {
                        "ok": False,
                        "blocked": True,
                        "reason_code": codec.ReasonCode.CONFLICT.value,
                        "reason": f"damaged_public_sync_journal:{op_id}",
                        "return_stage": "3C",
                        "resume_ref": pub_sync_rel,
                        "post_edit_preserved": True,
                        "legacy_routes": [],
                        "pending_operations": [{"operation_id": op_id, "resume_ref": pub_sync_rel}],
                        "diagnostics": [diag],
                    }
            intent_doc = intents.get(op_id)
            if isinstance(intent_doc, dict):
                for key in ("targets", "writes", "files"):
                    rows = intent_doc.get(key)
                    if isinstance(rows, list):
                        targets_to_check.extend(r for r in rows if isinstance(r, dict))
            if not _operation_overlaps_scope(op, tid, scope_set):
                continue
            post_edit_diag = _check_journal_target_post_edits(
                root_path,
                targets_to_check,
                resume_ref=pub_sync_rel if pub_sync_raw is not None else op_ref,
                entity_id=entity_id,
            )
            if post_edit_diag is not None:
                return {
                    "ok": False,
                    "blocked": True,
                    "reason_code": codec.ReasonCode.CONFLICT.value,
                    "reason": f"b_route_journal_post_edit_conflict:{op_id}",
                    "return_stage": "3C",
                    "resume_ref": post_edit_diag["resume_ref"],
                    "post_edit_preserved": True,
                    "legacy_routes": [],
                    "pending_operations": [{"operation_id": op_id, "resume_ref": op_ref}],
                    "diagnostics": [post_edit_diag],
                }
            pending_ops.append(
                {
                    "operation_id": op_id,
                    "schema_version": op.get("schema_version"),
                    "resume_ref": pub_sync_rel if pub_sync_raw is not None else op_ref,
                    "scope_ids": list(op.get("scope_ids") or frozen_doc.get("scope_ids") or []),
                }
            )
        if pending_ops:
            first_op = pending_ops[0]
            op_schema = str(first_op.get("schema_version") or "")
            rstage = "5" if "stage5" in op_schema else ("4" if "chapter4" in op_schema else "3C")
            diag = _diag(
                codec.ReasonCode.PENDING,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected="resolved pending B-route operation journal",
                actual={
                    "operation_id": first_op["operation_id"],
                    "scope_ids": first_op["scope_ids"] or ["unknown"],
                    "return_stage": rstage,
                },
                resume_ref=first_op["resume_ref"],
            )
            return {
                "ok": False,
                "blocked": True,
                "reason_code": codec.ReasonCode.PENDING.value,
                "reason": f"b_route_pending_operation:{first_op['operation_id']}",
                "return_stage": rstage,
                "resume_ref": first_op["resume_ref"],
                "post_edit_preserved": True,
                "legacy_routes": [],
                "pending_operations": pending_ops,
                "diagnostics": [diag],
            }

    # 3. Scan explicit top-level B-route journal directories (never recursive rglob on planning candidate trees).
    for rel_dir, default_stage in (
        ("logs/ci/b-route-operations", "3C"),
        ("logs/ci/b-route-chapter4-binding", "4"),
        ("logs/ci/b-route-stage5-obligations", "5"),
    ):
        base = root_path / rel_dir
        if not os.path.lexists(base):
            continue
        try:
            inventory.no_reparse(base)
            if not base.is_dir():
                continue
            subdirs = sorted(base.iterdir())
        except (codec.CodecError, OSError, ValueError) as exc:
            diag = _diag(
                codec.ReasonCode.UNSAFE_PATH,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected=f"safe directory {rel_dir}",
                actual={"error": f"{type(exc).__name__}: {exc}", "return_stage": default_stage},
                resume_ref=rel_dir,
            )
            return {
                "ok": False,
                "blocked": True,
                "reason_code": codec.ReasonCode.UNSAFE_PATH.value,
                "reason": f"unsafe_journal_dir:{rel_dir}",
                "return_stage": default_stage,
                "resume_ref": rel_dir,
                "post_edit_preserved": True,
                "legacy_routes": [],
                "pending_operations": [],
                "diagnostics": [diag],
            }
        for sub in subdirs:
            if sub.name in {"operations", "locks"}:
                continue
            try:
                inventory.no_reparse(sub)
                if not sub.is_dir():
                    continue
            except (codec.CodecError, OSError, ValueError) as exc:
                sub_rel = _repo_rel(root_path, sub)
                diag = _diag(
                    codec.ReasonCode.UNSAFE_PATH,
                    stage=codec.Stage.PATH,
                    entity_id=entity_id,
                    expected="non-reparse journal directory",
                    actual={"path": sub_rel, "error": str(exc), "return_stage": default_stage},
                    resume_ref=sub_rel,
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "reason_code": codec.ReasonCode.UNSAFE_PATH.value,
                    "reason": f"unsafe_journal_subdir:{sub.name}",
                    "return_stage": default_stage,
                    "resume_ref": sub_rel,
                    "post_edit_preserved": True,
                    "legacy_routes": [],
                    "pending_operations": [],
                    "diagnostics": [diag],
                }
            for fname in ("apply-journal.json", "public-sync-journal.json", "operation.json"):
                jfile = sub / fname
                if not os.path.lexists(jfile):
                    continue
                jrel = _repo_rel(root_path, jfile)
                try:
                    inventory.no_reparse(jfile)
                    if not jfile.is_file():
                        raise ValueError("journal path is not a regular file")
                    parsed = codec.strict_json_loads(jfile.read_bytes())
                    if not isinstance(parsed, dict):
                        raise ValueError("journal root must be a JSON object")
                except (codec.CodecError, OSError, ValueError) as exc:
                    diag = _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.DECODE,
                        entity_id=entity_id,
                        expected="valid B-route journal JSON",
                        actual={"path": jrel, "error": f"{type(exc).__name__}: {exc}", "return_stage": default_stage},
                        resume_ref=jrel,
                    )
                    return {
                        "ok": False,
                        "blocked": True,
                        "reason_code": codec.ReasonCode.CONFLICT.value,
                        "reason": f"damaged_b_route_journal:{sub.name}",
                        "return_stage": default_stage,
                        "resume_ref": jrel,
                        "post_edit_preserved": True,
                        "legacy_routes": [],
                        "pending_operations": [{"operation_id": sub.name, "resume_ref": jrel}],
                        "diagnostics": [diag],
                    }
                state = str(parsed.get("state") or parsed.get("status") or "").strip().lower()
                if state not in _INCOMPLETE_EXTERNAL_STATES:
                    continue
                if not _operation_overlaps_scope(parsed, tid, scope_set):
                    continue
                ext_targets: list[dict[str, Any]] = []
                for key in ("targets", "writes", "files", "entries"):
                    rows = parsed.get(key)
                    if isinstance(rows, list):
                        ext_targets.extend(r for r in rows if isinstance(r, dict))
                post_edit_diag = _check_journal_target_post_edits(
                    root_path,
                    ext_targets,
                    resume_ref=jrel,
                    entity_id=entity_id,
                )
                if post_edit_diag is not None:
                    return {
                        "ok": False,
                        "blocked": True,
                        "reason_code": codec.ReasonCode.CONFLICT.value,
                        "reason": f"b_route_journal_post_edit_conflict:{sub.name}",
                        "return_stage": default_stage,
                        "resume_ref": jrel,
                        "post_edit_preserved": True,
                        "legacy_routes": [],
                        "pending_operations": [{"operation_id": sub.name, "resume_ref": jrel}],
                        "diagnostics": [post_edit_diag],
                    }
                diag = _diag(
                    codec.ReasonCode.PENDING,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="completed B-route journal before Chapter 6 execution",
                    actual={"operation_id": sub.name, "state": state, "return_stage": default_stage},
                    resume_ref=jrel,
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "reason_code": codec.ReasonCode.PENDING.value,
                    "reason": f"b_route_pending_operation:{sub.name}",
                    "return_stage": default_stage,
                    "resume_ref": jrel,
                    "post_edit_preserved": True,
                    "legacy_routes": [],
                    "pending_operations": [{"operation_id": sub.name, "resume_ref": jrel}],
                    "diagnostics": [diag],
                }

    return {
        "ok": True,
        "blocked": False,
        "reason_code": None,
        "reason": None,
        "return_stage": None,
        "resume_ref": None,
        "post_edit_preserved": True,
        "legacy_routes": [],
        "pending_operations": [],
        "diagnostics": [],
    }


def _effective_dependencies_for_task(
    root_path: Path,
    cur_tid: int,
    row: dict[str, Any],
) -> set[int]:
    deps: set[int] = set()
    for raw_dep in row.get("dependencies") or []:
        try:
            dep_int = int(raw_dep)
            if dep_int != cur_tid:
                deps.add(dep_int)
        except (TypeError, ValueError):
            continue
    rec_path = root_path / ch5_b.DEFAULT_RECONCILIATION_DIR / f"task-{cur_tid}.json"
    rec_doc = _safe_read_json(rec_path)
    if isinstance(rec_doc, dict):
        dep_rows = rec_doc.get("dependency_decisions")
        if not isinstance(dep_rows, list):
            dep_rows = (
                (rec_doc.get("decisions") or {}).get("dependency_decisions")
                if isinstance(rec_doc.get("decisions"), dict)
                else []
            )
        for drow in dep_rows or []:
            if not isinstance(drow, dict):
                continue
            action = str(drow.get("action") or "").strip().lower()
            raw_dep = drow.get("dependency_id")
            try:
                dep_int = int(raw_dep)
            except (TypeError, ValueError):
                continue
            if dep_int == cur_tid:
                continue
            if action == "keep":
                deps.add(dep_int)
            elif action in {"remove", "drop", "defer"}:
                deps.discard(dep_int)
    return deps


def _check_task_and_dependency_eligibility(
    root_path: Path,
    tid: int,
    *,
    gate_res: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute live Task and multi-hop transitive dependency eligibility from tasks.json without requiring self done."""
    entity_id = str(tid)
    master_rel = task_resolver.TRIPLET["master"]
    try:
        master_path = inventory.safe_input(root_path, master_rel, allow_logs=False)
    except (codec.CodecError, OSError, ValueError) as exc:
        diag = _diag(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=master_rel,
            actual={"error": str(exc), "return_stage": "3C"},
            resume_ref=master_rel,
        )
        return {
            "ok": False,
            "task_status": None,
            "self_done_required": False,
            "required_dependencies": [],
            "transitive_dependencies": [],
            "incomplete_dependencies": [],
            "reason_code": codec.ReasonCode.UNSAFE_PATH.value,
            "reason": "tasks_master_unsafe_path",
            "return_stage": "3C",
            "diagnostics": [diag],
        }
    master_doc = _safe_read_json(master_path)
    if master_doc is None:
        code = codec.ReasonCode.INVALID_JSON if master_path.is_file() else codec.ReasonCode.FILE_NOT_FOUND
        diag = _diag(
            code,
            stage=codec.Stage.DECODE if master_path.is_file() else codec.Stage.PATH,
            entity_id=entity_id,
            expected="readable .taskmaster/tasks/tasks.json",
            actual={"exists": master_path.exists(), "return_stage": "3C"},
            resume_ref=master_rel,
        )
        return {
            "ok": False,
            "task_status": None,
            "self_done_required": False,
            "required_dependencies": [],
            "transitive_dependencies": [],
            "incomplete_dependencies": [],
            "reason_code": code.value,
            "reason": "tasks_master_invalid_json" if master_path.is_file() else "tasks_master_missing",
            "return_stage": "3C",
            "diagnostics": [diag],
        }
    master_tasks = ((master_doc.get("master") or {}).get("tasks") or []) if isinstance(master_doc.get("master"), dict) else []
    by_id: dict[int, dict[str, Any]] = {}
    for row in master_tasks:
        if isinstance(row, dict) and row.get("id") is not None:
            try:
                by_id[int(row["id"])] = row
            except (TypeError, ValueError):
                continue
    target = by_id.get(tid)
    if target is None:
        diag = _diag(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=f"master task {tid} present in tasks.json",
            actual={"present": False, "return_stage": "3C"},
            resume_ref=master_rel,
        )
        return {
            "ok": False,
            "task_status": None,
            "self_done_required": False,
            "required_dependencies": [],
            "transitive_dependencies": [],
            "incomplete_dependencies": [],
            "reason_code": codec.ReasonCode.MAPPING_MISMATCH.value,
            "reason": "task_missing_from_master",
            "return_stage": "3C",
            "diagnostics": [diag],
        }

    task_status = str(target.get("status") or "").strip().lower()
    if task_status in _INELIGIBLE_TASK_STATUSES:
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"eligible_task_status": True, "return_stage": "3C"},
            actual={"task_status": task_status, "return_stage": "3C"},
            resume_ref=master_rel,
        )
        return {
            "ok": False,
            "task_status": task_status,
            "self_done_required": False,
            "required_dependencies": [],
            "transitive_dependencies": [],
            "incomplete_dependencies": [],
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "reason": f"task_status_ineligible:{task_status}",
            "return_stage": "3C",
            "diagnostics": [diag],
        }

    req_deps = _effective_dependencies_for_task(root_path, tid, target)
    visited: set[int] = set()
    queue: list[int] = sorted(req_deps)
    incomplete: list[dict[str, Any]] = []
    while queue:
        dep_id = queue.pop(0)
        if dep_id in visited or dep_id == tid:
            continue
        visited.add(dep_id)
        dep_row = by_id.get(dep_id)
        dep_status = str((dep_row or {}).get("status") or "missing").strip().lower()
        if dep_row is None or dep_status != "done":
            incomplete.append({"dependency_id": dep_id, "status": dep_status})
            continue
        for nxt_dep in sorted(_effective_dependencies_for_task(root_path, dep_id, dep_row)):
            if nxt_dep not in visited and nxt_dep != tid:
                queue.append(nxt_dep)

    if incomplete:
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"required_dependencies_status": "done", "return_stage": "3C"},
            actual={"incomplete_dependencies": incomplete, "task_status": task_status, "return_stage": "3C"},
            resume_ref=master_rel,
        )
        return {
            "ok": False,
            "task_status": task_status,
            "self_done_required": False,
            "required_dependencies": sorted(req_deps),
            "transitive_dependencies": sorted(visited),
            "incomplete_dependencies": incomplete,
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "reason": f"dependency_not_done:{incomplete[0]['dependency_id']}:{incomplete[0]['status']}",
            "return_stage": "3C",
            "diagnostics": [diag],
        }

    requires_reverify = bool((gate_res or {}).get("requires_chapter6_reverification"))
    return {
        "ok": True,
        "task_status": task_status,
        "self_done_required": False,
        "required_dependencies": sorted(req_deps),
        "transitive_dependencies": sorted(visited),
        "incomplete_dependencies": [],
        "requires_chapter6_reverification": requires_reverify,
        "old_done_covers_new_obligations": False,
        "reason_code": codec.ReasonCode.OK.value,
        "reason": "eligible",
        "return_stage": None,
        "diagnostics": [],
    }


def _extract_binding_revisions(gate_res: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(gate_res, dict):
        return out
    for row in gate_res.get("binding_refs") or []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("entity_id") or row.get("path") or "").strip()
        if eid:
            out[eid] = {
                "revision": row.get("revision"),
                "digest": row.get("digest"),
                "path": row.get("path"),
            }
    stage5 = gate_res.get("stage5_summary")
    if isinstance(stage5, dict):
        for prow in stage5.get("plans") or []:
            if isinstance(prow, dict) and prow.get("plan_id"):
                pid = str(prow["plan_id"])
                out.setdefault(pid, {})
                out[pid]["binding_revision"] = prow.get("binding_revision")
                out[pid]["stage"] = prow.get("stage")
    return out


def _read_mvg_recovery_registry_readonly(root_path: Path) -> tuple[bool, dict[str, Any] | None, str | None]:
    store = mvg_recovery.store_root(root_path)
    reg_file = store / "registry.json"
    if not reg_file.exists():
        return True, {"schema_version": mvg_recovery.SCHEMA, "epoch": 0, "entries": [], "revoked": []}, None
    try:
        val = mvg_recovery.registry(root_path)
        return True, val, _repo_rel(root_path, reg_file)
    except Exception as exc:
        return False, {"error": str(exc)}, _repo_rel(root_path, reg_file)


def _extract_proof_paths(doc: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("adoption_proof_refs", "proof_refs", "source_run_refs"):
        val = doc.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip().replace("\\", "/"))
                elif isinstance(item, dict):
                    for pk in ("path", "ref", "run_path", "resume_ref"):
                        pv = item.get(pk)
                        if isinstance(pv, str) and pv.strip():
                            paths.append(pv.strip().replace("\\", "/"))
        elif isinstance(val, dict):
            for pv in val.values():
                if isinstance(pv, str) and pv.strip():
                    paths.append(pv.strip().replace("\\", "/"))
    for key in ("source_run_ref", "run_ref", "adoption_proof_ref"):
        pv = doc.get(key)
        if isinstance(pv, str) and pv.strip():
            paths.append(pv.strip().replace("\\", "/"))
    return paths


def _is_doc_revoked_or_reopened(doc: dict[str, Any]) -> bool:
    status_val = str(doc.get("status") or "").strip().lower()
    return bool(
        doc.get("revoked") is True
        or doc.get("reopened") is True
        or doc.get("superseded") is True
        or doc.get("epoch_revoked") is True
        or status_val in {"revoked", "reopened", "invalidated"}
    )


def _check_proof_ref_revocation(
    root_path: Path,
    proof_rel: str,
    *,
    entity_id: str,
    live_epoch: int,
) -> dict[str, Any] | None:
    rel = proof_rel.strip().replace("\\", "/").lstrip("./")
    if not rel:
        return None
    candidates: list[str] = [rel]
    for prefix in ("logs/ci/capability-planning/", "logs/ci/mvg-planning/"):
        if rel.startswith(prefix):
            rest = rel[len(prefix):]
            run_name = rest.split("/", 1)[0].strip()
            if run_name:
                run_json_rel = f"{prefix}{run_name}/run.json"
                if run_json_rel not in candidates:
                    candidates.append(run_json_rel)
    for cand_rel in candidates:
        cand_path = root_path / cand_rel
        if not cand_path.is_file():
            continue
        pdoc = _safe_read_json(cand_path)
        if not isinstance(pdoc, dict):
            continue
        if _is_doc_revoked_or_reopened(pdoc):
            diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"adoption_proof_revoked_or_reopened": False, "return_stage": "3B"},
                actual={
                    "proof_path": cand_rel,
                    "status": pdoc.get("status"),
                    "reopened": pdoc.get("reopened"),
                    "revoked": pdoc.get("revoked"),
                    "superseded": pdoc.get("superseded"),
                    "return_stage": "3B",
                },
                resume_ref=cand_rel,
            )
            return {
                "ok": False,
                "reason_code": codec.ReasonCode.CONFLICT.value,
                "reason": f"adoption_proof_revoked_or_reopened:{cand_rel}",
                "return_stage": "3B",
                "resume_ref": cand_rel,
                "live_epoch": live_epoch,
                "diagnostics": [diag],
            }
    return None


def _check_epoch_and_reopen_revocations(
    root_path: Path,
    tid: int,
    *,
    gate_res: dict[str, Any] | None = None,
    run_baseline: dict[str, Any] | None = None,
    durable_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Honor Story 2.9 epoch clears and reopen revocations independently of marker deletion or run_dir."""
    entity_id = str(tid)
    reg_ok, reg_val, reg_rel = _read_mvg_recovery_registry_readonly(root_path)
    if not reg_ok:
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected="valid mvg-recovery registry.json",
            actual={"error": (reg_val or {}).get("error"), "return_stage": "3B"},
            resume_ref=reg_rel or "logs/ci/mvg-recovery/registry.json",
        )
        return {
            "ok": False,
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "reason": "recovery_registry_invalid",
            "return_stage": "3B",
            "resume_ref": diag["resume_ref"],
            "live_epoch": None,
            "diagnostics": [diag],
        }

    live_epoch = int((reg_val or {}).get("epoch") or 0)
    revoked_txs = {str(x) for x in list((reg_val or {}).get("revoked") or []) if str(x).strip()}

    # 1. Collect active plan IDs, scope IDs, transaction IDs, and check committed plan/proof revocations.
    active_plan_ids: set[str] = set()
    active_scope_ids: set[str] = set()
    active_tx_ids: set[str] = set()
    proof_refs_to_check: list[str] = []
    if isinstance(gate_res, dict):
        for ref_key in ("plan_refs", "binding_refs"):
            for ref in gate_res.get(ref_key) or []:
                if not isinstance(ref, dict):
                    continue
                for k in ("entity_id", "plan_id"):
                    if ref.get(k):
                        active_plan_ids.add(str(ref[k]))
                ppath = ref.get("path")
                if isinstance(ppath, str) and ppath:
                    pdoc = _safe_read_json(root_path / ppath)
                    if isinstance(pdoc, dict):
                        if pdoc.get("plan_id"):
                            active_plan_ids.add(str(pdoc["plan_id"]))
                        if _is_doc_revoked_or_reopened(pdoc):
                            diag = _diag(
                                codec.ReasonCode.CONFLICT,
                                stage=codec.Stage.BUNDLE,
                                entity_id=entity_id,
                                expected={"plan_revoked_or_reopened": False, "return_stage": "3B"},
                                actual={"plan_path": ppath, "status": pdoc.get("status"), "return_stage": "3B"},
                                resume_ref=ppath,
                            )
                            return {
                                "ok": False,
                                "reason_code": codec.ReasonCode.CONFLICT.value,
                                "reason": f"plan_revoked_or_reopened:{ppath}",
                                "return_stage": "3B",
                                "resume_ref": ppath,
                                "live_epoch": live_epoch,
                                "diagnostics": [diag],
                            }
                        for txk in ("transaction_id", "source_transaction_id"):
                            if pdoc.get(txk):
                                active_tx_ids.add(str(pdoc[txk]))
                        proof_refs_to_check.extend(_extract_proof_paths(pdoc))
        for sid in gate_res.get("scope_ids") or []:
            if isinstance(sid, str) and sid:
                active_scope_ids.add(sid)
    if isinstance(run_baseline, dict):
        for pid in run_baseline.get("plan_ids") or []:
            if pid:
                active_plan_ids.add(str(pid))
        for sid in run_baseline.get("scope_ids") or []:
            if sid:
                active_scope_ids.add(str(sid))
        for tx in run_baseline.get("transaction_ids") or []:
            if tx:
                active_tx_ids.add(str(tx))

    seen_proofs: set[str] = set()
    for pref in proof_refs_to_check:
        if pref in seen_proofs:
            continue
        seen_proofs.add(pref)
        proof_blocked = _check_proof_ref_revocation(
            root_path,
            pref,
            entity_id=entity_id,
            live_epoch=live_epoch,
        )
        if proof_blocked is not None:
            return proof_blocked

    revoked_hits = sorted(revoked_txs & (active_tx_ids | active_plan_ids))
    if revoked_hits:
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"revoked_transactions": [], "return_stage": "3B"},
            actual={"revoked_hits": revoked_hits, "return_stage": "3B"},
            resume_ref=reg_rel or "logs/ci/mvg-recovery/registry.json",
        )
        return {
            "ok": False,
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "reason": f"recovery_source_revoked:{revoked_hits[0]}",
            "return_stage": "3B",
            "resume_ref": diag["resume_ref"],
            "live_epoch": live_epoch,
            "diagnostics": [diag],
        }

    # Check registry entries for revoked/reopened matches even when run_dir=None.
    for entry in list((reg_val or {}).get("entries") or []):
        if not isinstance(entry, dict) or not _is_doc_revoked_or_reopened(entry):
            continue
        e_ids = {
            str(entry.get(k))
            for k in ("plan_id", "scope_id", "transaction_id", "task_id")
            if entry.get(k) is not None and str(entry.get(k)).strip()
        }
        if not e_ids or entity_id in e_ids or bool(e_ids & (active_plan_ids | active_scope_ids | active_tx_ids)):
            diag = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"registry_entry_revoked": False, "return_stage": "3B"},
                actual={"entry_ids": sorted(e_ids), "status": entry.get("status"), "return_stage": "3B"},
                resume_ref=reg_rel or "logs/ci/mvg-recovery/registry.json",
            )
            return {
                "ok": False,
                "reason_code": codec.ReasonCode.CONFLICT.value,
                "reason": "recovery_registry_entry_revoked",
                "return_stage": "3B",
                "resume_ref": diag["resume_ref"],
                "live_epoch": live_epoch,
                "diagnostics": [diag],
            }

    # 2. Scan durable reopen/revocation records under logs/ci/b-route-reopen/** (always, even when run_dir=None).
    reopen_root = root_path / REOPEN_DIR
    if reopen_root.is_dir():
        for rec_file in sorted(reopen_root.rglob("*.json")):
            if not rec_file.is_file():
                continue
            rel = _repo_rel(root_path, rec_file)
            doc = _safe_read_json(rec_file)
            if doc is None:
                diag = _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.DECODE,
                    entity_id=entity_id,
                    expected="valid reopen/revocation record JSON",
                    actual={"path": rel, "return_stage": "3B"},
                    resume_ref=rel,
                )
                return {
                    "ok": False,
                    "reason_code": codec.ReasonCode.CONFLICT.value,
                    "reason": "damaged_reopen_record",
                    "return_stage": "3B",
                    "resume_ref": rel,
                    "live_epoch": live_epoch,
                    "diagnostics": [diag],
                }
            status_val = str(doc.get("status") or "").strip().lower()
            is_revoking = bool(
                doc.get("revoked") is True
                or doc.get("reopened") is True
                or doc.get("superseded") is True
                or doc.get("epoch_revoked") is True
                or status_val in {"revoked", "reopened", "invalidated", "active"}
            )
            if not is_revoking:
                continue
            doc_tids = {str(x) for x in (doc.get("task_ids") or []) if x is not None}
            if doc.get("task_id") is not None:
                doc_tids.add(str(doc["task_id"]))
            doc_plans = {str(x) for x in (doc.get("plan_ids") or []) if x}
            if doc.get("plan_id"):
                doc_plans.add(str(doc["plan_id"]))
            doc_scopes = {str(x) for x in (doc.get("scope_ids") or []) if x}
            if doc.get("scope_id"):
                doc_scopes.add(str(doc["scope_id"]))
            is_global = bool(doc.get("global") is True or (not doc_tids and not doc_plans and not doc_scopes))
            matches = (
                is_global
                or entity_id in doc_tids
                or bool(active_plan_ids & doc_plans)
                or bool(active_scope_ids & doc_scopes)
            )
            if matches:
                rc = codec.ReasonCode.INPUT_STALE if doc.get("epoch_revoked") is True else codec.ReasonCode.CONFLICT
                diag = _diag(
                    rc,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"reopen_revoked": False, "return_stage": "3B"},
                    actual={
                        "reopen_record": rel,
                        "status": status_val or "revoked",
                        "epoch": doc.get("epoch"),
                        "return_stage": "3B",
                    },
                    resume_ref=rel,
                )
                return {
                    "ok": False,
                    "reason_code": rc.value,
                    "reason": f"reopen_or_epoch_revoked:{rel}",
                    "return_stage": "3B",
                    "resume_ref": rel,
                    "live_epoch": live_epoch,
                    "diagnostics": [diag],
                }

    # 3. Compare live epoch against run baseline's frozen recovery_epoch (or durable prior baseline when run_dir=None).
    baseline_epoch: int | None = None
    if isinstance(run_baseline, dict) and run_baseline.get("recovery_epoch") is not None:
        try:
            baseline_epoch = int(run_baseline["recovery_epoch"])
        except (TypeError, ValueError):
            baseline_epoch = -1
    elif run_baseline is None and live_epoch > 0 and isinstance(durable_signals, dict):
        prior_ep = durable_signals.get("latest_frozen_recovery_epoch")
        if prior_ep is not None:
            try:
                baseline_epoch = int(prior_ep)
            except (TypeError, ValueError):
                baseline_epoch = -1

    if baseline_epoch is not None and baseline_epoch != live_epoch:
        diag = _diag(
            codec.ReasonCode.INPUT_STALE,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"recovery_epoch": baseline_epoch, "return_stage": "3B"},
            actual={"recovery_epoch": live_epoch, "return_stage": "3B"},
            resume_ref=reg_rel or "logs/ci/mvg-recovery/registry.json",
        )
        return {
            "ok": False,
            "reason_code": codec.ReasonCode.INPUT_STALE.value,
            "reason": f"recovery_epoch_invalidated:{baseline_epoch}->{live_epoch}",
            "return_stage": "3B",
            "resume_ref": diag["resume_ref"],
            "live_epoch": live_epoch,
            "diagnostics": [diag],
        }

    return {
        "ok": True,
        "reason_code": codec.ReasonCode.OK.value,
        "reason": "clean",
        "return_stage": None,
        "resume_ref": None,
        "live_epoch": live_epoch,
        "diagnostics": [],
    }


def _product_tree_fingerprint(root_path: Path) -> dict[str, Any]:
    """Compute a deterministic fingerprint of product & test sources (excluding harness scripts, logs, knowledge, tasks)."""
    entries_by_rel: dict[str, str] = {}
    latest_mtime_ns = 0

    def _record_file(item: Path) -> None:
        nonlocal latest_mtime_ns
        rel = _repo_rel(root_path, item)
        rel_lower = rel.lower()
        if any(rel_lower.startswith(p) for p in _NON_PRODUCT_PREFIXES):
            return
        if any(part.lower() in _EXCLUDED_DIR_PARTS for part in item.parts):
            return
        if item.suffix.lower() == ".pyc":
            return
        try:
            st = item.stat()
            if st.st_mtime_ns > latest_mtime_ns:
                latest_mtime_ns = st.st_mtime_ns
            raw = item.read_bytes()
            entries_by_rel[rel] = f"{rel}:{hashlib.sha256(raw).hexdigest()}"
        except OSError:
            return

    for dirname in _PRODUCT_ROOT_DIRS:
        base = root_path / dirname
        if not base.is_dir():
            continue
        for item in sorted(base.rglob("*")):
            if not item.is_file():
                continue
            if item.suffix.lower() not in _PRODUCT_FILE_EXTENSIONS:
                continue
            _record_file(item)

    try:
        for item in sorted(root_path.iterdir()):
            if not item.is_file():
                continue
            name_lower = item.name.lower()
            if name_lower == "project.godot" or item.suffix.lower() in {".csproj", ".sln"}:
                _record_file(item)
    except OSError:
        pass

    ordered = [entries_by_rel[k] for k in sorted(entries_by_rel)]
    digest = "sha256:" + hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()
    return {
        "digest": digest,
        "file_count": len(ordered),
        "latest_mtime_ns": latest_mtime_ns,
    }


def load_run_recovery_baseline(root_path: Path, run_dir: Path | None) -> dict[str, Any] | None:
    """Load frozen recovery-input-set.json strictly (fail-closed on corrupt file) or gate event fallback."""
    if run_dir is None or not run_dir.is_dir():
        return None
    frozen_file = run_dir / RECOVERY_INPUT_SET_FILENAME
    frozen_rel = _repo_rel(root_path, frozen_file)
    if os.path.lexists(frozen_file):
        try:
            inventory.no_reparse(frozen_file)
            if not frozen_file.is_file():
                return {"_corrupt": True, "_path": frozen_rel, "_error": "not_a_regular_file"}
            doc = codec.strict_json_loads(frozen_file.read_bytes())
        except (codec.CodecError, OSError, ValueError) as exc:
            return {"_corrupt": True, "_path": frozen_rel, "_error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(doc, dict):
            return {"_corrupt": True, "_path": frozen_rel, "_error": "root_not_object"}
        if doc.get("schema_version") != RECOVERY_INPUT_SET_SCHEMA:
            return {"_corrupt": True, "_path": frozen_rel, "_error": f"invalid_schema_version:{doc.get('schema_version')}"}
        raw_digest = doc.get("input_set_digest")
        if not isinstance(raw_digest, str) or ch6_gate._DIGEST_RE.fullmatch(raw_digest) is None:
            return {"_corrupt": True, "_path": frozen_rel, "_error": "missing_or_invalid_input_set_digest"}
        return {**doc, "_path": frozen_rel}
    for ev_name in ("chapter6-gate-events.jsonl", "b_route_gate_events.jsonl"):
        rows = _safe_read_jsonl(run_dir / ev_name)
        for row in reversed(rows):
            if row.get("input_set_digest"):
                return {
                    "schema_version": RECOVERY_INPUT_SET_SCHEMA,
                    "task_id": row.get("task_id"),
                    "input_set_digest": row.get("input_set_digest"),
                    "applicable_set_digest": row.get("applicable_set_digest"),
                    "scope_ids": list(row.get("scope_ids") or []),
                    "binding_revisions": dict(row.get("binding_revisions") or {}),
                    "plan_ids": list(row.get("plan_ids") or []),
                    "recovery_epoch": row.get("recovery_epoch"),
                    "_path": _repo_rel(root_path, run_dir / ev_name),
                }
    return None


def _compare_run_baseline_to_live(
    *,
    tid: int,
    run_baseline: dict[str, Any],
    gate_res: dict[str, Any],
    live_iset: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare a prior run's frozen InputSet baseline strictly against live gate/InputSet state."""
    entity_id = str(tid)
    base_digest = run_baseline.get("input_set_digest") or None
    live_digest = gate_res.get("input_set_digest") or None
    base_app = run_baseline.get("applicable_set_digest") or None
    live_app = gate_res.get("applicable_set_digest") or None
    base_scopes = sorted(str(s) for s in list(run_baseline.get("scope_ids") or []) if s)
    live_scopes = sorted(str(s) for s in list(gate_res.get("scope_ids") or []) if s)
    base_bindings = run_baseline.get("binding_revisions") if isinstance(run_baseline.get("binding_revisions"), dict) else {}
    live_bindings = _extract_binding_revisions(gate_res)
    base_ref = str(run_baseline.get("_path") or RECOVERY_INPUT_SET_FILENAME)

    digest_mismatch = (base_digest != live_digest)
    app_mismatch = (base_app != live_app)
    scope_mismatch = (base_scopes != live_scopes)
    binding_mismatch = (base_bindings != live_bindings)

    if not (digest_mismatch or app_mismatch or scope_mismatch or binding_mismatch):
        return {
            "ok": True,
            "reason_code": codec.ReasonCode.OK.value,
            "reason": "baseline_matches_live",
            "return_stage": None,
            "diagnostics": [],
        }

    diags: list[dict[str, Any]] = []
    rstage: str | None = None
    if isinstance(run_baseline.get("input_set_snapshot"), dict) and isinstance(live_iset, dict):
        cmp_res = input_set.compare_input_sets(run_baseline["input_set_snapshot"], live_iset)
        diags = list(cmp_res.get("diagnostics") or [])
        rstage = cmp_res.get("return_stage")

    if not rstage:
        if app_mismatch or scope_mismatch or (set(base_bindings) != set(live_bindings)):
            rstage = "3C"
        elif binding_mismatch:
            rstage = "4"
        else:
            rstage = "5"

    if not diags:
        diags = [
            _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={
                    "input_set_digest": base_digest,
                    "applicable_set_digest": base_app,
                    "scope_ids": base_scopes,
                    "binding_revisions": base_bindings,
                    "return_stage": rstage,
                },
                actual={
                    "input_set_digest": live_digest,
                    "applicable_set_digest": live_app,
                    "scope_ids": live_scopes,
                    "binding_revisions": live_bindings,
                    "return_stage": rstage,
                },
                resume_ref=base_ref,
            )
        ]

    reason_code = str(diags[0].get("reason_code") or codec.ReasonCode.INPUT_STALE.value)
    return {
        "ok": False,
        "reason_code": reason_code,
        "reason": "run_baseline_input_set_drifted",
        "return_stage": rstage,
        "diagnostics": diags,
    }


def scan_durable_recovery_signals(
    root: Path | str,
    task_id: Any,
    *,
    current_run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Scan all durable task run directories across all date folders; immune to deleted markers or rebuilt Knowledge."""
    root_path = Path(root).resolve()
    tid_str = str(task_id or "").strip()
    current_resolved = Path(current_run_dir).resolve() if current_run_dir is not None else None
    ci_root = root_path / "logs" / "ci"

    run_records: list[dict[str, Any]] = []
    if tid_str and ci_root.is_dir():
        patterns = (
            f"*/sc-review-pipeline-task-{tid_str}-*",
            f"*/sc-review-pipeline-task-{tid_str}",
            f"*/sc-needs-fix-fast-task-{tid_str}-*",
            f"*/sc-needs-fix-fast-task-{tid_str}",
        )
        seen_dirs: set[Path] = set()
        for pat in patterns:
            for cand in ci_root.glob(pat):
                if not cand.is_dir():
                    continue
                resolved = cand.resolve()
                if resolved in seen_dirs:
                    continue
                seen_dirs.add(resolved)
                summary_path = resolved / "summary.json"
                marathon_path = resolved / "marathon-state.json"
                ctx_path = resolved / "execution-context.json"
                events_path = resolved / "run-events.jsonl"
                frozen_path = resolved / RECOVERY_INPUT_SET_FILENAME
                if not any(p.is_file() for p in (summary_path, marathon_path, ctx_path, events_path, frozen_path)):
                    continue
                summary = _safe_read_json(summary_path) or {}
                marathon = _safe_read_json(marathon_path) or {}
                ctx = _safe_read_json(ctx_path) or {}
                frozen = _safe_read_json(frozen_path) or {}
                mtime_ns = max(
                    (p.stat().st_mtime_ns for p in (summary_path, marathon_path, ctx_path, events_path, frozen_path) if p.is_file()),
                    default=0,
                )
                date_folder = resolved.parent.name
                run_id = str(
                    summary.get("run_id")
                    or marathon.get("run_id")
                    or ctx.get("run_id")
                    or ""
                ).strip()
                status = str(summary.get("status") or marathon.get("status") or ctx.get("status") or "").strip().lower()
                reason = str(summary.get("reason") or marathon.get("stop_reason") or "").strip()
                diagnostics: dict[str, Any] = {}
                for src in (ctx, marathon, summary):
                    d = src.get("diagnostics")
                    if isinstance(d, dict):
                        diagnostics.update(d)
                run_records.append(
                    {
                        "dir": resolved,
                        "rel_dir": _repo_rel(root_path, resolved),
                        "date_folder": date_folder,
                        "mtime_ns": mtime_ns,
                        "run_id": run_id,
                        "cmd": str(summary.get("cmd") or ctx.get("cmd") or "").strip(),
                        "status": status,
                        "reason": reason,
                        "failed_step": str(summary.get("failed_step") or ctx.get("failed_step") or "").strip(),
                        "diagnostics": diagnostics,
                        "marathon": marathon,
                        "execution_context": ctx,
                        "summary": summary,
                        "frozen_baseline": frozen if frozen.get("schema_version") == RECOVERY_INPUT_SET_SCHEMA else None,
                    }
                )

    run_records.sort(key=lambda r: (r["date_folder"], r["mtime_ns"], r["rel_dir"]))

    prior_records = [r for r in run_records if current_resolved is None or r["dir"] != current_resolved]
    active_signals: list[str] = []
    blocking_signal = ""
    blocking_reason = ""
    blocking_run_rel = ""
    failed_runs = 0
    consecutive_failures = 0
    total_step_retries = 0
    total_resume_count = 0
    failure_families: list[str] = []
    latest_stopped_record: dict[str, Any] | None = None
    latest_frozen_recovery_epoch: int | None = None

    for rec in prior_records:
        st = rec["status"]
        rsn = rec["reason"]
        diag = rec["diagnostics"]
        marathon = rec["marathon"]
        total_resume_count += int(marathon.get("resume_count") or 0)
        steps_map = marathon.get("steps") if isinstance(marathon.get("steps"), dict) else {}
        for sinfo in steps_map.values():
            if isinstance(sinfo, dict):
                total_step_retries += int(sinfo.get("attempt_count") or 0)

        fb = rec.get("frozen_baseline")
        if isinstance(fb, dict) and fb.get("recovery_epoch") is not None:
            try:
                latest_frozen_recovery_epoch = int(fb["recovery_epoch"])
            except (TypeError, ValueError):
                pass

        is_fail = st in {"fail", "stopped", "indeterminate"} or rsn.startswith("rerun_blocked:")
        rg = diag.get("rerun_guard") if isinstance(diag.get("rerun_guard"), dict) else None
        has_rerun_guard = rsn.startswith("rerun_blocked:") or (rg is not None and bool(rg.get("blocked")))
        rec_stop_keys = [
            key for key in ("sc_test_retry_stop_loss", "llm_retry_stop_loss", "waste_signals")
            if key in diag and diag[key]
        ]
        has_budget_exhausted = False
        max_retries = marathon.get("max_step_retries")
        if isinstance(max_retries, int) and max_retries >= 0 and is_fail:
            for sinfo in steps_map.values():
                if isinstance(sinfo, dict) and int(sinfo.get("attempt_count") or 0) > max_retries:
                    has_budget_exhausted = True
                    break
        has_rec_stop_loss = has_rerun_guard or bool(rec_stop_keys) or has_budget_exhausted

        if st == "ok" and not rsn.startswith("rerun_blocked:") and not has_rec_stop_loss:
            consecutive_failures = 0
            active_signals.clear()
            failure_families.clear()
            latest_stopped_record = None
            continue

        if is_fail:
            failed_runs += 1
            consecutive_failures += 1
            fam = f"{rec['failed_step'] or 'unknown'}|{rsn or st}"
            failure_families.append(fam)

        if has_rerun_guard:
            if "rerun_guard" not in active_signals:
                active_signals.append("rerun_guard")
            latest_stopped_record = rec
        for key in rec_stop_keys:
            if key not in active_signals:
                active_signals.append(key)
            latest_stopped_record = rec
        if has_budget_exhausted:
            if "failure_budget_exhausted" not in active_signals:
                active_signals.append("failure_budget_exhausted")
            latest_stopped_record = rec

    same_family_streak = 0
    if failure_families:
        last_fam = failure_families[-1]
        for fam in reversed(failure_families):
            if fam == last_fam:
                same_family_streak += 1
            else:
                break
        if same_family_streak >= 2:
            if "repeat_deterministic_failure" not in active_signals:
                active_signals.append("repeat_deterministic_failure")
            latest_stopped_record = prior_records[-1]

    # Check if product/test sources actually changed since the stopped run.
    source_changed = False
    if latest_stopped_record is not None:
        live_fp = _product_tree_fingerprint(root_path)
        frozen_b = latest_stopped_record.get("frozen_baseline")
        if isinstance(frozen_b, dict) and frozen_b.get("product_tree_digest"):
            source_changed = bool(live_fp["digest"] != frozen_b["product_tree_digest"])
        elif live_fp["file_count"] > 0 and latest_stopped_record["mtime_ns"] > 0:
            source_changed = bool(live_fp["latest_mtime_ns"] > latest_stopped_record["mtime_ns"])
        else:
            source_changed = False

    if active_signals and not source_changed and latest_stopped_record is not None:
        priority = (
            "rerun_guard",
            "sc_test_retry_stop_loss",
            "llm_retry_stop_loss",
            "waste_signals",
            "failure_budget_exhausted",
            "repeat_deterministic_failure",
        )
        for sig in priority:
            if sig in active_signals:
                blocking_signal = sig
                break
        blocking_reason = latest_stopped_record["reason"] or blocking_signal
        blocking_run_rel = latest_stopped_record["rel_dir"]

    latest_any = run_records[-1] if run_records else None
    latest_prior = prior_records[-1] if prior_records else None
    return {
        "task_id": tid_str,
        "durable_run_count": len(run_records),
        "prior_run_count": len(prior_records),
        "durable_run_dirs": [r["rel_dir"] for r in run_records],
        "latest_durable_run_dir": latest_any["rel_dir"] if latest_any else "",
        "latest_durable_run_id": latest_any["run_id"] if latest_any else "",
        "latest_prior_run_dir": latest_prior["rel_dir"] if latest_prior else "",
        "latest_frozen_recovery_epoch": latest_frozen_recovery_epoch,
        "failed_runs": failed_runs,
        "consecutive_failures": consecutive_failures,
        "same_family_streak": same_family_streak,
        "total_step_retries": total_step_retries,
        "total_resume_count": total_resume_count,
        "active_stop_loss_signals": active_signals,
        "source_changed_since_last_stop": source_changed,
        "blocked_by": blocking_signal,
        "blocking_reason": blocking_reason,
        "blocking_run_dir": blocking_run_rel,
        "has_active_stop_loss": bool(blocking_signal),
    }


def _blocked_recovery_result(
    *,
    task_id: int | None,
    operation: str | None,
    consumer: str,
    recommendation_only: bool,
    route: str,
    reason_code: str,
    reason: str,
    return_stage: str | None,
    resume_ref: str | None,
    diagnostics: list[dict[str, Any]],
    started: float,
    durable_signals: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed = round(max(0.0, time.monotonic() - started), 6)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "ok": False,
        "execution_allowed": False,
        "task_id": task_id,
        "operation": operation,
        "consumer": consumer,
        "recommendation_only": bool(recommendation_only),
        "route": route,
        "legacy_a_passthrough": False,
        "reason_code": reason_code,
        "reason": reason,
        "return_stage": return_stage if return_stage in ch6_gate.STAGE_RANK else "5",
        "resume_ref": resume_ref or _extract_resume_ref(diagnostics),
        "input_set_digest": None,
        "applicable_set_digest": None,
        "scope_ids": [],
        "plan_refs": [],
        "binding_refs": [],
        "requires_chapter6_reverification": False,
        "old_done_covers_new_obligations": False,
        "self_done_required": False,
        "post_edit_preserved": True,
        "stop_loss_active": False,
        "stop_loss_blocked_by": "",
        "stop_loss_reason": "",
        "durable_signals": durable_signals or {},
        "diagnostics": diagnostics,
        "metrics": {"active_elapsed_seconds": elapsed},
        **INVARIANT_FLAGS,
    }
    if extra:
        payload.update(extra)
    payload["runtime_verified"] = False
    payload["default_b_enabled"] = False
    return payload


def _resolve_candidate_task_scopes(root_path: Path, tid: int, operation: str | None) -> set[str] | None:
    _ = operation
    has_any_journal_dir = False
    for rel_dir in (
        f"{op_scope.STORE}/operations",
        "logs/ci/b-route-operations",
        "logs/ci/b-route-chapter4-binding",
        "logs/ci/b-route-stage5-obligations",
    ):
        if os.path.lexists(root_path / rel_dir):
            has_any_journal_dir = True
            break
    if not has_any_journal_dir:
        return None
    origins_doc = _safe_read_json(root_path / task_resolver.ORIGINS_PATH)
    if not isinstance(origins_doc, dict) or not isinstance(origins_doc.get("tasks"), list):
        return None
    matched_row: dict[str, Any] | None = None
    for row in origins_doc["tasks"]:
        if isinstance(row, dict) and str(row.get("task_id")) == str(tid):
            matched_row = row
            break
    if matched_row is None:
        return None
    raw_origin = matched_row.get("origin")
    if raw_origin is not None and str(raw_origin) not in {"B", "A", "b_route", "compiled"}:
        return None
    plan_ids: list[str] = []
    for k in ("plan_ids",):
        vals = matched_row.get(k)
        if isinstance(vals, list):
            plan_ids.extend(str(v) for v in vals if str(v).strip())
    for pref in matched_row.get("plan_refs") or []:
        if isinstance(pref, dict) and pref.get("entity_id"):
            plan_ids.append(str(pref["entity_id"]))
    cat_doc = _safe_read_json(root_path / "docs/planning/b-route/catalog.v1.json")
    scopes = set(op_scope.resource_scopes(plan_ids=plan_ids, task_ids=[tid]))
    if isinstance(cat_doc, dict):
        pset = set(plan_ids)
        for sh in cat_doc.get("scope_heads") or []:
            if not isinstance(sh, dict):
                continue
            sh_plans = {
                str(pr.get("entity_id"))
                for pr in (sh.get("plan_refs") or [])
                if isinstance(pr, dict) and pr.get("entity_id")
            }
            sh_binds = [
                str(br.get("path"))
                for br in (sh.get("binding_refs") or [])
                if isinstance(br, dict) and br.get("path")
            ]
            overlaps_tid = bool(sh_plans & pset)
            if not overlaps_tid:
                for bpath in sh_binds:
                    bdoc = _safe_read_json(root_path / bpath)
                    if not isinstance(bdoc, dict):
                        continue
                    for trow in list(bdoc.get("task_mappings") or []) + list(bdoc.get("task_bindings") or bdoc.get("tasks") or []):
                        if isinstance(trow, dict) and str(trow.get("task_id")) == str(tid):
                            overlaps_tid = True
                            if bdoc.get("plan_id"):
                                scopes.update(op_scope.resource_scopes(plan_ids=[str(bdoc["plan_id"])]))
                            break
                    if overlaps_tid:
                        break
            if overlaps_tid:
                if sh.get("scope_id"):
                    scopes.add(str(sh["scope_id"]))
                if sh_plans:
                    scopes.update(op_scope.resource_scopes(plan_ids=sorted(sh_plans)))
    return scopes or None


def evaluate_chapter6_recovery(
    root: Path | str,
    task_id: Any,
    *,
    run_dir: Path | str | None = None,
    operation: str = "resume",
    recommendation_only: bool = True,
    consumer: str = "resume_task",
    lock_mode: str = "none",
    enforce_durable_stop_loss: bool = True,
    current_run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Read-only zero-write live recovery revalidator across gate, pending, eligibility, baseline, reopen, and stop-loss."""
    started = time.monotonic()
    validated_tid: int | None = None
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = ch6_gate.parse_strict_task_id(task_id)
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        if diag.get("entity_id") is None and validated_tid is not None:
            diag["entity_id"] = str(validated_tid)
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=diag["reason_code"],
            reason=f"invalid_arguments:{diag['reason_code']}",
            return_stage="3C",
            resume_ref=diag.get("resume_ref"),
            diagnostics=[diag],
            started=started,
        )

    run_dir_path: Path | None = None
    if run_dir is not None and str(run_dir).strip():
        cand = Path(run_dir)
        run_dir_path = cand.resolve() if cand.is_absolute() else (root_path / cand).resolve()

    current_run_path: Path | None = None
    if current_run_dir is not None and str(current_run_dir).strip():
        ccand = Path(current_run_dir)
        current_run_path = ccand.resolve() if ccand.is_absolute() else (root_path / ccand).resolve()
    elif operation in {"fresh", "implement"} and run_dir_path is not None:
        current_run_path = run_dir_path

    durable_signals = scan_durable_recovery_signals(
        root_path,
        validated_tid,
        current_run_dir=current_run_path,
    )
    run_baseline = load_run_recovery_baseline(root_path, run_dir_path)

    # 1. Inspect pending markers, legacy apply journals, B-route ops, and post-edit conflicts first.
    candidate_scopes = _resolve_candidate_task_scopes(root_path, validated_tid, operation)
    pending_check = _inspect_pending_and_post_edits(root_path, validated_tid, scope_ids=candidate_scopes)
    if pending_check["blocked"]:
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=str(pending_check["reason_code"] or codec.ReasonCode.PENDING.value),
            reason=str(pending_check["reason"] or "pending_journal"),
            return_stage=pending_check.get("return_stage") or "3C",
            resume_ref=pending_check.get("resume_ref"),
            diagnostics=list(pending_check.get("diagnostics") or []),
            started=started,
            durable_signals=durable_signals,
            extra={
                "post_edit_preserved": bool(pending_check.get("post_edit_preserved", True)),
                "pending_check": pending_check,
            },
        )

    # 1b. Fail closed if recovery-input-set.json exists on disk in run_dir but is corrupt / reparse / invalid.
    if isinstance(run_baseline, dict) and run_baseline.get("_corrupt") is True:
        corrupt_path = str(run_baseline.get("_path") or RECOVERY_INPUT_SET_FILENAME)
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.DECODE,
            entity_id=str(validated_tid),
            expected="valid recovery-input-set.json",
            actual={"path": corrupt_path, "error": run_baseline.get("_error"), "return_stage": "5"},
            resume_ref=corrupt_path,
        )
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=codec.ReasonCode.CONFLICT.value,
            reason="corrupt_recovery_input_set_baseline",
            return_stage="5",
            resume_ref=corrupt_path,
            diagnostics=[diag],
            started=started,
            durable_signals=durable_signals,
        )

    # 2. Detect B-route presence; clean explicit_not_enabled_a passthrough when zero B traces/pending/N/A labels.
    presence = ch6_gate.detect_b_route_presence(root_path, validated_tid)
    has_b_or_markers = bool(
        presence.get("has_b_traces")
        or presence.get("capability_apply_pending")
        or presence.get("pending_journals")
        or presence.get("na_labels")
        or presence.get("has_lease_env")
    )
    if not has_b_or_markers:
        reopen_check_a = _check_epoch_and_reopen_revocations(
            root_path,
            validated_tid,
            gate_res=None,
            run_baseline=run_baseline,
            durable_signals=durable_signals,
        )
        if not reopen_check_a["ok"]:
            return _blocked_recovery_result(
                task_id=validated_tid,
                operation=operation,
                consumer=consumer,
                recommendation_only=recommendation_only,
                route="blocked",
                reason_code=reopen_check_a["reason_code"],
                reason=reopen_check_a["reason"],
                return_stage=reopen_check_a["return_stage"],
                resume_ref=reopen_check_a.get("resume_ref"),
                diagnostics=list(reopen_check_a.get("diagnostics") or []),
                started=started,
                durable_signals=durable_signals,
                extra={"reopen_check": reopen_check_a},
            )
        if presence.get("has_adr_0040") and (root_path / task_resolver.TRIPLET["master"]).is_file():
            gate_a = ch6_gate.evaluate_chapter6_gate(
                root_path,
                validated_tid,
                operation=operation,
                consumer=consumer,
                lock_mode="none",
            )
            if not gate_a.get("ok"):
                diags = list(gate_a.get("diagnostics") or [])
                return _blocked_recovery_result(
                    task_id=validated_tid,
                    operation=operation,
                    consumer=consumer,
                    recommendation_only=recommendation_only,
                    route=str(gate_a.get("route") or "blocked"),
                    reason_code=str(gate_a.get("reason_code") or codec.ReasonCode.CONFLICT.value),
                    reason=str(gate_a.get("reason") or "gate_blocked"),
                    return_stage=gate_a.get("return_stage") or "5",
                    resume_ref=_extract_resume_ref(diags),
                    diagnostics=diags,
                    started=started,
                    durable_signals=durable_signals,
                    extra={"gate_result": gate_a},
                )
        elapsed = round(max(0.0, time.monotonic() - started), 6)
        return {
            "schema_version": SCHEMA,
            "ok": True,
            "execution_allowed": True,
            "task_id": validated_tid,
            "operation": operation,
            "consumer": consumer,
            "recommendation_only": bool(recommendation_only),
            "route": "explicit_not_enabled_a",
            "legacy_a_passthrough": True,
            "reason_code": codec.ReasonCode.OK.value,
            "reason": "explicit_not_enabled_a",
            "return_stage": None,
            "resume_ref": None,
            "input_set_digest": None,
            "applicable_set_digest": None,
            "scope_ids": list(op_scope.resource_scopes(task_ids=[validated_tid])),
            "plan_refs": [],
            "binding_refs": [],
            "requires_chapter6_reverification": False,
            "old_done_covers_new_obligations": False,
            "self_done_required": False,
            "post_edit_preserved": True,
            "stop_loss_active": bool(durable_signals.get("has_active_stop_loss")),
            "stop_loss_blocked_by": str(durable_signals.get("blocked_by") or ""),
            "stop_loss_reason": str(durable_signals.get("blocking_reason") or ""),
            "durable_signals": durable_signals,
            "reopen_check": reopen_check_a,
            "diagnostics": [],
            "metrics": {"active_elapsed_seconds": elapsed},
            **INVARIANT_FLAGS,
        }

    # 3. Live Story 3.8 unified gate evaluation (never trusts cached ready/ok).
    gate_res = ch6_gate.evaluate_chapter6_gate(
        root_path,
        validated_tid,
        operation=operation,
        consumer=consumer,
        lock_mode=lock_mode,
    )
    if not gate_res.get("ok"):
        diags = list(gate_res.get("diagnostics") or [])
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route=str(gate_res.get("route") or "blocked"),
            reason_code=str(gate_res.get("reason_code") or codec.ReasonCode.CONFLICT.value),
            reason=str(gate_res.get("reason") or "chapter6_gate_blocked"),
            return_stage=gate_res.get("return_stage") or "5",
            resume_ref=_extract_resume_ref(diags),
            diagnostics=diags,
            started=started,
            durable_signals=durable_signals,
            extra={
                "input_set_digest": gate_res.get("input_set_digest"),
                "applicable_set_digest": gate_res.get("applicable_set_digest"),
                "scope_ids": list(gate_res.get("scope_ids") or []),
                "plan_refs": list(gate_res.get("plan_refs") or []),
                "binding_refs": list(gate_res.get("binding_refs") or []),
                "gate_result": gate_res,
            },
        )

    # 4. Live Task and dependency eligibility (recomputed from live tasks.json; never requires self done).
    elig = _check_task_and_dependency_eligibility(root_path, validated_tid, gate_res=gate_res)
    if not elig["ok"]:
        diags = list(elig.get("diagnostics") or [])
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route=str(gate_res.get("route") or "B"),
            reason_code=str(elig["reason_code"]),
            reason=str(elig["reason"]),
            return_stage=elig.get("return_stage") or "3C",
            resume_ref=_extract_resume_ref(diags),
            diagnostics=diags,
            started=started,
            durable_signals=durable_signals,
            extra={
                "input_set_digest": gate_res.get("input_set_digest"),
                "applicable_set_digest": gate_res.get("applicable_set_digest"),
                "scope_ids": list(gate_res.get("scope_ids") or []),
                "eligibility": elig,
                "gate_result": gate_res,
            },
        )

    # 5. Story 2.9 epoch & reopen revocation check.
    reopen_check = _check_epoch_and_reopen_revocations(
        root_path,
        validated_tid,
        gate_res=gate_res,
        run_baseline=run_baseline,
        durable_signals=durable_signals,
    )
    if not reopen_check["ok"]:
        diags = list(reopen_check.get("diagnostics") or [])
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route=str(gate_res.get("route") or "B"),
            reason_code=str(reopen_check["reason_code"]),
            reason=str(reopen_check["reason"]),
            return_stage=reopen_check.get("return_stage") or "3B",
            resume_ref=reopen_check.get("resume_ref"),
            diagnostics=diags,
            started=started,
            durable_signals=durable_signals,
            extra={
                "input_set_digest": gate_res.get("input_set_digest"),
                "applicable_set_digest": gate_res.get("applicable_set_digest"),
                "scope_ids": list(gate_res.get("scope_ids") or []),
                "reopen_check": reopen_check,
                "eligibility": elig,
                "gate_result": gate_res,
            },
        )

    # 6. Compare prior run's frozen InputSet baseline (binding replacement / new plan join / drift).
    baseline_cmp: dict[str, Any] = {"ok": True, "reason": "no_prior_baseline"}
    live_iset_snapshot: dict[str, Any] | None = None
    if run_baseline is not None:
        if isinstance(run_baseline.get("input_set_snapshot"), dict):
            live_iset_snapshot = input_set.resolve_input_set(root_path, validated_tid, operation=operation)
        baseline_cmp = _compare_run_baseline_to_live(
            tid=validated_tid,
            run_baseline=run_baseline,
            gate_res=gate_res,
            live_iset=live_iset_snapshot,
        )
        if not baseline_cmp["ok"]:
            diags = list(baseline_cmp.get("diagnostics") or [])
            return _blocked_recovery_result(
                task_id=validated_tid,
                operation=operation,
                consumer=consumer,
                recommendation_only=recommendation_only,
                route=str(gate_res.get("route") or "B"),
                reason_code=str(baseline_cmp["reason_code"]),
                reason=str(baseline_cmp["reason"]),
                return_stage=baseline_cmp.get("return_stage") or "5",
                resume_ref=_extract_resume_ref(diags),
                diagnostics=diags,
                started=started,
                durable_signals=durable_signals,
                extra={
                    "input_set_digest": gate_res.get("input_set_digest"),
                    "applicable_set_digest": gate_res.get("applicable_set_digest"),
                    "scope_ids": list(gate_res.get("scope_ids") or []),
                    "baseline_comparison": baseline_cmp,
                    "reopen_check": reopen_check,
                    "eligibility": elig,
                    "gate_result": gate_res,
                },
            )

    stop_loss_active = bool(durable_signals.get("has_active_stop_loss"))
    stop_loss_blocked_by = str(durable_signals.get("blocked_by") or "")
    stop_loss_reason = str(durable_signals.get("blocking_reason") or "")
    active_sig_set = set(durable_signals.get("active_stop_loss_signals") or [])
    elapsed = round(max(0.0, time.monotonic() - started), 6)

    should_block_stop_loss = False
    if (
        enforce_durable_stop_loss
        and stop_loss_active
        and not recommendation_only
        and consumer not in _READONLY_ROUTE_CONSUMERS
    ):
        if consumer == "llm_review_needs_fix_fast":
            # 6.8 targeted closure is allowed for llm_retry_stop_loss / review-only rerun guards,
            # but MUST block when deterministic stop-loss or failure budget signals are active.
            det_rerun_reason = stop_loss_reason.startswith(
                (
                    "rerun_blocked:repeat_deterministic_failure",
                    "rerun_blocked:chapter6_route_fix_deterministic",
                    "rerun_blocked:chapter6_route_repo_noise_stop",
                )
            )
            should_block_stop_loss = bool(active_sig_set & _NEEDS_FIX_BLOCKING_STOP_LOSS) or det_rerun_reason
        else:
            should_block_stop_loss = True

    if should_block_stop_loss:
        diag = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(validated_tid),
            expected={"stop_loss_cleared_by_source_fix": True},
            actual={
                "blocked_by": stop_loss_blocked_by,
                "blocking_reason": stop_loss_reason,
                "blocking_run_dir": durable_signals.get("blocking_run_dir"),
                "failed_runs": durable_signals.get("failed_runs"),
                "consecutive_failures": durable_signals.get("consecutive_failures"),
                "source_changed_since_last_stop": False,
            },
            resume_ref=str(durable_signals.get("blocking_run_dir") or "") or None,
        )
        return _blocked_recovery_result(
            task_id=validated_tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=recommendation_only,
            route=str(gate_res.get("route") or "B"),
            reason_code=codec.ReasonCode.CONFLICT.value,
            reason=f"durable_stop_loss:{stop_loss_blocked_by}",
            return_stage="5",
            resume_ref=diag["resume_ref"],
            diagnostics=[diag],
            started=started,
            durable_signals=durable_signals,
            extra={
                "input_set_digest": gate_res.get("input_set_digest"),
                "applicable_set_digest": gate_res.get("applicable_set_digest"),
                "scope_ids": list(gate_res.get("scope_ids") or []),
                "stop_loss_active": True,
                "stop_loss_blocked_by": stop_loss_blocked_by,
                "stop_loss_reason": stop_loss_reason,
                "reopen_check": reopen_check,
                "eligibility": elig,
                "baseline_comparison": baseline_cmp,
                "gate_result": gate_res,
            },
        )

    return {
        "schema_version": SCHEMA,
        "ok": True,
        "execution_allowed": True,
        "task_id": validated_tid,
        "operation": operation,
        "consumer": consumer,
        "recommendation_only": bool(recommendation_only),
        "route": str(gate_res.get("route") or "B"),
        "legacy_a_passthrough": bool(gate_res.get("legacy_a_passthrough")),
        "reason_code": codec.ReasonCode.OK.value,
        "reason": "ready",
        "return_stage": None,
        "resume_ref": None,
        "input_set_digest": gate_res.get("input_set_digest"),
        "applicable_set_digest": gate_res.get("applicable_set_digest"),
        "scope_ids": list(gate_res.get("scope_ids") or []),
        "plan_refs": deepcopy(gate_res.get("plan_refs") or []),
        "binding_refs": deepcopy(gate_res.get("binding_refs") or []),
        "binding_revisions": _extract_binding_revisions(gate_res),
        "requires_chapter6_reverification": bool(gate_res.get("requires_chapter6_reverification")),
        "old_done_covers_new_obligations": False,
        "self_done_required": False,
        "post_edit_preserved": True,
        "stop_loss_active": stop_loss_active,
        "stop_loss_blocked_by": stop_loss_blocked_by,
        "stop_loss_reason": stop_loss_reason,
        "durable_signals": durable_signals,
        "reopen_check": reopen_check,
        "eligibility": elig,
        "baseline_comparison": baseline_cmp,
        "gate_result": gate_res,
        "diagnostics": [],
        "metrics": {"active_elapsed_seconds": elapsed},
        **INVARIANT_FLAGS,
    }


def write_recovery_input_set(
    root: Path | str,
    out_dir: Path | str,
    recovery_result: dict[str, Any],
    *,
    input_set_snapshot: dict[str, Any] | None = None,
) -> Path:
    """Persist frozen recovery-input-set.json in out_dir during explicit recovery execution (never in recommendation-only)."""
    root_path = Path(root).resolve()
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    reg_ok, reg_val, _ = _read_mvg_recovery_registry_readonly(root_path)
    live_epoch = int((reg_val or {}).get("epoch") or 0) if reg_ok else 0
    fp = _product_tree_fingerprint(root_path)
    plan_ids = sorted(
        {
            str(ref.get("entity_id") or ref.get("plan_id") or "").strip()
            for ref in (recovery_result.get("plan_refs") or [])
            if isinstance(ref, dict) and str(ref.get("entity_id") or ref.get("plan_id") or "").strip()
        }
    )
    payload = {
        "schema_version": RECOVERY_INPUT_SET_SCHEMA,
        "task_id": recovery_result.get("task_id"),
        "route": recovery_result.get("route"),
        "input_set_digest": recovery_result.get("input_set_digest"),
        "applicable_set_digest": recovery_result.get("applicable_set_digest"),
        "scope_ids": sorted(str(s) for s in list(recovery_result.get("scope_ids") or []) if s),
        "plan_ids": plan_ids,
        "binding_revisions": deepcopy(recovery_result.get("binding_revisions") or _extract_binding_revisions(recovery_result.get("gate_result"))),
        "recovery_epoch": live_epoch,
        "product_tree_digest": fp["digest"],
        "requires_chapter6_reverification": bool(recovery_result.get("requires_chapter6_reverification")),
        "input_set_snapshot": deepcopy(input_set_snapshot) if isinstance(input_set_snapshot, dict) else None,
        **INVARIANT_FLAGS,
    }
    target = out_path / RECOVERY_INPUT_SET_FILENAME
    ch6_gate._atomic_write_json(target, payload)
    return target


def format_recovery_block_message(consumer: str, res: dict[str, Any]) -> str:
    rc = str(res.get("reason_code") or "conflict")
    rsn = str(res.get("reason") or "blocked")
    rstage = str(res.get("return_stage") or "5")
    rref = str(res.get("resume_ref") or "n/a")
    return (
        f"[{consumer}] BLOCKED by b-route-chapter6-recovery: "
        f"reason_code={rc} reason={rsn} return_stage={rstage} resume_ref={rref}"
    )


@dataclass
class Chapter6RecoveryHandle:
    """Active handle yielded by guarded_chapter6_recovery."""

    root: Path
    task_id: int
    operation: str
    consumer: str
    recovery_result: dict[str, Any]
    input_set_snapshot: dict[str, Any] | None
    scope_ids: tuple[str, ...]
    inherited_lease: bool = False
    lease_receipt_path: str | None = None
    out_dir: Path | None = None
    frozen_baseline_path: Path | None = None
    uses_global_writer_lock: bool = False

    @property
    def legacy_a_passthrough(self) -> bool:
        return bool(self.recovery_result.get("legacy_a_passthrough"))

    @property
    def input_set_digest(self) -> str | None:
        return self.recovery_result.get("input_set_digest")

    def revalidate_boundary(
        self,
        step_name: str = "",
        *,
        model_invocation: bool = False,
        file_write: bool = False,
    ) -> dict[str, Any]:
        """Re-check gate, frozen InputSet, pending/post-edits, eligibility, and reopen before model calls or writes."""
        if self.legacy_a_passthrough:
            return self.recovery_result
        res = evaluate_chapter6_recovery(
            self.root,
            self.task_id,
            run_dir=self.out_dir,
            operation=self.operation,
            recommendation_only=False,
            consumer=self.consumer,
            lock_mode="none",
            enforce_durable_stop_loss=False,
        )
        if not res.get("ok"):
            if self.out_dir is not None:
                ch6_gate.record_chapter6_gate_event(
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
            raise Chapter6RecoveryBlockedError(res)
        if self.input_set_digest and res.get("input_set_digest") != self.input_set_digest:
            diags: list[dict[str, Any]] = []
            rstage = "5"
            if isinstance(self.input_set_snapshot, dict):
                live_iset = input_set.resolve_input_set(self.root, self.task_id, operation=self.operation)
                cmp_res = input_set.compare_input_sets(self.input_set_snapshot, live_iset)
                diags = list(cmp_res.get("diagnostics") or [])
                if cmp_res.get("return_stage") in ch6_gate.STAGE_RANK:
                    rstage = str(cmp_res["return_stage"])
            if not diags:
                diags = [
                    _diag(
                        codec.ReasonCode.INPUT_STALE,
                        stage=codec.Stage.BUNDLE,
                        entity_id=str(self.task_id),
                        expected=self.input_set_digest,
                        actual={"input_set_digest": res.get("input_set_digest"), "return_stage": rstage},
                        resume_ref=_repo_rel(self.root, self.frozen_baseline_path) if self.frozen_baseline_path else None,
                    )
                ]
            blocked = _blocked_recovery_result(
                task_id=self.task_id,
                operation=self.operation,
                consumer=self.consumer,
                recommendation_only=False,
                route=str(res.get("route") or "B"),
                reason_code=str(diags[0].get("reason_code") or codec.ReasonCode.INPUT_STALE.value),
                reason="mid_recovery_input_set_drift",
                return_stage=rstage,
                resume_ref=_extract_resume_ref(diags) or (_repo_rel(self.root, self.frozen_baseline_path) if self.frozen_baseline_path else None),
                diagnostics=diags,
                started=time.monotonic(),
            )
            raise Chapter6RecoveryBlockedError(blocked)
        live_scopes = tuple(sorted(str(s) for s in list(res.get("scope_ids") or []) if s))
        if not set(live_scopes).issubset(set(self.scope_ids)):
            diag = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(self.task_id),
                expected=list(self.scope_ids),
                actual={"scope_ids": list(live_scopes), "return_stage": "3C"},
            )
            blocked = _blocked_recovery_result(
                task_id=self.task_id,
                operation=self.operation,
                consumer=self.consumer,
                recommendation_only=False,
                route=str(res.get("route") or "B"),
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="mid_recovery_scope_expanded",
                return_stage="3C",
                resume_ref=None,
                diagnostics=[diag],
                started=time.monotonic(),
            )
            raise Chapter6RecoveryBlockedError(blocked)
        self.recovery_result = res
        return res


@contextmanager
def guarded_chapter6_recovery(
    root: Path | str,
    task_id: Any,
    *,
    run_dir: Path | str | None = None,
    out_dir: Path | str | None = None,
    operation: str = "resume",
    consumer: str = "recovery",
    enforce_durable_stop_loss: bool = True,
) -> Iterator[Chapter6RecoveryHandle]:
    """Acquire business-scope locks in public lock order (short metadata -> sorted union scopes) and freeze recovery InputSet."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))
    tid = ch6_gate.parse_strict_task_id(task_id)
    run_dir_path = (
        (Path(run_dir).resolve() if Path(run_dir).is_absolute() else (root_path / run_dir).resolve())
        if run_dir is not None and str(run_dir).strip()
        else None
    )
    out_dir_path = (
        (Path(out_dir).resolve() if Path(out_dir).is_absolute() else (root_path / out_dir).resolve())
        if out_dir is not None and str(out_dir).strip()
        else None
    )

    exclude_current = out_dir_path if (out_dir_path is not None and out_dir_path != run_dir_path) else None
    pre_res = evaluate_chapter6_recovery(
        root_path,
        tid,
        run_dir=run_dir_path,
        operation=operation,
        recommendation_only=False,
        consumer=consumer,
        lock_mode="none",
        enforce_durable_stop_loss=enforce_durable_stop_loss,
        current_run_dir=exclude_current,
    )
    if not pre_res.get("ok"):
        raise Chapter6RecoveryBlockedError(pre_res)

    if pre_res.get("legacy_a_passthrough"):
        yield Chapter6RecoveryHandle(
            root=root_path,
            task_id=tid,
            operation=operation,
            consumer=consumer,
            recovery_result=pre_res,
            input_set_snapshot=None,
            scope_ids=tuple(pre_res.get("scope_ids") or ()),
            inherited_lease=False,
            lease_receipt_path=None,
            out_dir=out_dir_path,
            frozen_baseline_path=None,
            uses_global_writer_lock=False,
        )
        return

    prior_baseline = load_run_recovery_baseline(root_path, run_dir_path)
    union_scopes_set = {str(s) for s in list(pre_res.get("scope_ids") or []) if isinstance(s, str) and s}
    if isinstance(prior_baseline, dict):
        union_scopes_set.update(str(s) for s in list(prior_baseline.get("scope_ids") or []) if isinstance(s, str) and s)
    union_scopes_set.discard(op_scope.WRITER_SCOPE)
    union_scopes = tuple(sorted(union_scopes_set))

    env_path = os.environ.get(ch6_gate.ENV_LEASE_PATH)
    env_secret = os.environ.get(ch6_gate.ENV_LEASE_SECRET)
    if env_path is not None or env_secret is not None:
        try:
            receipt = ch6_gate._verify_inherited_lease_receipt(
                root_path,
                tid,
                str(env_path or ""),
                str(env_secret or ""),
            )
        except codec.CodecError as err:
            diag = err.diagnostic.to_dict()
            if diag.get("entity_id") is None:
                diag["entity_id"] = str(tid)
            blocked = _blocked_recovery_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                recommendation_only=False,
                route="blocked",
                reason_code=diag["reason_code"],
                reason=f"invalid_parent_lease:{diag['reason_code']}",
                return_stage="5",
                resume_ref=diag.get("resume_ref"),
                diagnostics=[diag],
                started=started,
            )
            raise Chapter6RecoveryBlockedError(blocked) from err
        if not set(union_scopes).issubset(set(receipt["scope_ids"])):
            diag = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected=receipt["scope_ids"],
                actual={"union_scopes": list(union_scopes), "return_stage": "5"},
                resume_ref=receipt["receipt_rel"],
            )
            blocked = _blocked_recovery_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                recommendation_only=False,
                route=str(pre_res.get("route") or "B"),
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="recovery_scope_exceeds_parent_lease",
                return_stage="5",
                resume_ref=receipt["receipt_rel"],
                diagnostics=[diag],
                started=started,
            )
            raise Chapter6RecoveryBlockedError(blocked)
        live_iset = input_set.resolve_input_set(root_path, tid, operation=operation)
        frozen_path = (
            write_recovery_input_set(root_path, out_dir_path, pre_res, input_set_snapshot=live_iset)
            if out_dir_path is not None
            else None
        )
        yield Chapter6RecoveryHandle(
            root=root_path,
            task_id=tid,
            operation=operation,
            consumer=consumer,
            recovery_result=pre_res,
            input_set_snapshot=live_iset,
            scope_ids=tuple(receipt["scope_ids"]),
            inherited_lease=True,
            lease_receipt_path=receipt["receipt_rel"],
            out_dir=out_dir_path,
            frozen_baseline_path=frozen_path,
            uses_global_writer_lock=False,
        )
        return

    # Acquire business-scope locks in strict public lock order (short metadata -> sorted union scopes; NEVER writer:planning).
    try:
        guard_cm = op_scope.business_guard(root_path, list(union_scopes), review_only=True)
        guard_cm.__enter__()
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        if diag.get("entity_id") is None:
            diag["entity_id"] = str(tid)
        blocked = _blocked_recovery_result(
            task_id=tid,
            operation=operation,
            consumer=consumer,
            recommendation_only=False,
            route=str(pre_res.get("route") or "B"),
            reason_code=diag["reason_code"],
            reason=f"recovery_scope_lease_failed:{diag['reason_code']}",
            return_stage="5",
            resume_ref=diag.get("resume_ref"),
            diagnostics=[diag],
            started=started,
        )
        raise Chapter6RecoveryBlockedError(blocked) from err

    receipt_file: Path | None = None
    prev_env_path = os.environ.get(ch6_gate.ENV_LEASE_PATH)
    prev_env_secret = os.environ.get(ch6_gate.ENV_LEASE_SECRET)
    exc_info: tuple[Any, Any, Any] = (None, None, None)
    try:
        entered_res = evaluate_chapter6_recovery(
            root_path,
            tid,
            run_dir=run_dir_path,
            operation=operation,
            recommendation_only=False,
            consumer=consumer,
            lock_mode="none",
            enforce_durable_stop_loss=enforce_durable_stop_loss,
            current_run_dir=exclude_current,
        )
        if not entered_res.get("ok"):
            raise Chapter6RecoveryBlockedError(entered_res)
        live_iset = input_set.resolve_input_set(root_path, tid, operation=operation)
        if not live_iset.get("ok") or live_iset.get("input_set_digest") != entered_res.get("input_set_digest"):
            diag = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected=entered_res.get("input_set_digest"),
                actual={"input_set_digest": live_iset.get("input_set_digest"), "return_stage": "5"},
            )
            blocked = _blocked_recovery_result(
                task_id=tid,
                operation=operation,
                consumer=consumer,
                recommendation_only=False,
                route=str(entered_res.get("route") or "B"),
                reason_code=codec.ReasonCode.INPUT_STALE.value,
                reason="input_set_drifted_under_lease",
                return_stage="5",
                resume_ref=None,
                diagnostics=[diag],
                started=started,
            )
            raise Chapter6RecoveryBlockedError(blocked)

        lease_id = uuid.uuid4().hex[:16]
        secret = secrets.token_hex(32)
        receipt_rel = f"{ch6_gate.LEASE_DIR}/task-{tid}-{lease_id}.json"
        lease_dir = root_path / ch6_gate.LEASE_DIR
        lease_dir.mkdir(parents=True, exist_ok=True)
        receipt_file = root_path / receipt_rel
        receipt_payload = {
            "schema_version": ch6_gate.LEASE_RECEIPT_SCHEMA,
            "lease_id": lease_id,
            "owner_pid": os.getpid(),
            "owner_create_time": ch6_gate._get_process_create_time(os.getpid()),
            "root_resolved": str(root_path.resolve()),
            "task_id": tid,
            "route": entered_res["route"],
            "scope_ids": list(union_scopes),
            "input_set_digest": entered_res["input_set_digest"],
            "applicable_set_digest": entered_res.get("applicable_set_digest"),
            "secret_sha256": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            **INVARIANT_FLAGS,
        }
        ch6_gate._atomic_write_json(receipt_file, receipt_payload)
        os.environ[ch6_gate.ENV_LEASE_PATH] = receipt_rel
        os.environ[ch6_gate.ENV_LEASE_SECRET] = secret

        frozen_path = (
            write_recovery_input_set(root_path, out_dir_path, entered_res, input_set_snapshot=live_iset)
            if out_dir_path is not None
            else None
        )
        yield Chapter6RecoveryHandle(
            root=root_path,
            task_id=tid,
            operation=operation,
            consumer=consumer,
            recovery_result=entered_res,
            input_set_snapshot=live_iset,
            scope_ids=union_scopes,
            inherited_lease=False,
            lease_receipt_path=receipt_rel,
            out_dir=out_dir_path,
            frozen_baseline_path=frozen_path,
            uses_global_writer_lock=False,
        )
    except BaseException:
        exc_info = sys.exc_info()
        raise
    finally:
        if prev_env_path is None:
            os.environ.pop(ch6_gate.ENV_LEASE_PATH, None)
        else:
            os.environ[ch6_gate.ENV_LEASE_PATH] = prev_env_path
        if prev_env_secret is None:
            os.environ.pop(ch6_gate.ENV_LEASE_SECRET, None)
        else:
            os.environ[ch6_gate.ENV_LEASE_SECRET] = prev_env_secret
        if receipt_file is not None and receipt_file.exists():
            try:
                receipt_file.unlink()
            except OSError:
                pass
        guard_cm.__exit__(*exc_info)
