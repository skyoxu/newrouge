"""Unified B-route page execution/recovery trigger, five-entrypoint parity, Windows concurrency checks, and Epic 3->4 handoff.

Responsibilities (Story 3.12):
- AC-1 (PAGE_SHARED_GATE): Shared page trigger service (`handle_page_b_route_trigger`) for
  `POST /api/knowledge/b-route` and pre-flight runtime/MVG gates (`enforce_runtime_task_gate`,
  `enforce_mvg_manifest_gate`) invoked before snapshot preparation or Godot execution.
  Always evaluates live Story 3.8 gate, live Story 3.9 recovery, live Story 3.10 defect
  routing, live `.taskmaster/tasks/tasks.json` Task + multi-hop transitive dependency
  eligibility, and acquires the exact same business-scope lease (`acquire_chapter6_gate_lease`
  / `acquire_runtime_scope_leases`) before any execution side effect. Rejects or ignores
  client-cached readiness/digest/status and snapshot summary authorization, and guarantees
  preview / recommendation_only / workspace triggers never create, mutate, or advance
  `current.json`, `last-known-good.json`, `logs/ci/project-health-knowledge/latest.json`,
  `runtime/latest.json`, or `refs/heads/main`.
- AC-2 (PARITY_APPLICABLE): Five-entrypoint normalized decision and side-effect parity across
  `cli`, `direct`, `resume`, `route`, and `page` for legal Flow B-tasks, legal non-Flow B-tasks
  (`other_verification_refs` without fabricated manifests/APIs), integration-only owner B-tasks,
  and frozen-A / explicit-not-enabled-A tasks.
- AC-3 (TAMPER_BEFORE_FX): Pre-effect rejection parity across all public and direct underlying
  entrypoints on deleted origin/manifest/non-Flow rationale, damaged journals, severed bindings,
  new committed plans joining a shared Task, and unprovable/unknown/blocked origins (never
  falling back to legacy A and covering pre-existing pending tasks).
- AC-4 (WIN_CONCURRENCY): Deterministic Windows state-advancement and recovery verifiers:
  completed-apply status advancement no-op preservation (via real `_b_route_commit.recover` /
  `journal.resume_journal` terminal replay), incomplete-apply raw preimage conflict stop,
  relevant Task projection drift vs irrelevant metadata reuse, and shared-Task multi-plan
  union scope verification plus unresolved-pending blocking even when ephemeral markers are
  deleted.
- AC-5 (EPIC3_HANDOFF): Honest Epic 3 -> Epic 4 handoff summary dynamically verifying real
  consumers, CLI entrypoints, Skills, AGENTS.md, and owning docs while explicitly listing
  unimplemented Epic 4 / Epic 5 capabilities (`flow_completed=False`, `runtime_verified=False`,
  `default_b_enabled=False`).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import ast
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from typing import Any, Callable, Iterator
import uuid

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_recovery
import _b_route_codec as codec
import _b_route_commit as b_commit
import _b_route_defect_routing as defect_routing
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _b_route_operation_scope as op_scope
import _b_route_records as records
import _b_route_task_resolver as task_resolver
import _planning_apply_journal as journal


SCHEMA = "newrouge.b-route-entrypoint-parity.v1"
PAGE_TRIGGER_SCHEMA = "newrouge.b-route-page-trigger.v1"
EPIC3_HANDOFF_SCHEMA = "newrouge.b-route-epic3-handoff.v1"
RUNTIME_GATE_SCHEMA = "newrouge.b-route-runtime-gate.v1"
WIN_CONCURRENCY_SCHEMA = "newrouge.b-route-win-concurrency.v1"

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

VALID_PAGE_ACTIONS = frozenset({"gate", "execute", "resume", "route"})
VALID_PAGE_MODES = frozenset({"main", "workspace"})

_PAGE_ACTION_TO_OPERATION = {
    "gate": "implement",
    "execute": "implement",
    "resume": "resume",
    "route": "route",
}

PUBLICATION_POINTER_PATHS = (
    "docs/knowledge/published/current.json",
    "docs/knowledge/published/last-known-good.json",
    "logs/ci/project-health-knowledge/latest.json",
    "logs/ci/project-health-knowledge/runtime/latest.json",
)

SPOOFED_CLIENT_CACHE_KEYS = (
    "cached_readiness",
    "cached_input_set_digest",
    "cached_status",
    "cached_gate",
    "cached_route",
    "precomputed_ready",
)

FORBIDDEN_BYPASS_KEYS = (
    "skip_live_gate",
    "trust_latest_json",
    "trust_scan_snapshot",
    "summary_authorization",
)

_INELIGIBLE_TASK_STATUSES = frozenset({"cancelled", "canceled", "retired", "deleted"})

EPIC3_CONSUMERS = (
    "scripts/python/_b_route_task_preview.py",
    "scripts/python/compile_b_route_tasks.py",
    "scripts/python/_b_route_task_resolver.py",
    "scripts/python/_b_route_chapter4_binding.py",
    "scripts/python/_b_route_input_set.py",
    "scripts/python/_b_route_stage5_obligations.py",
    "scripts/python/_b_route_chapter5_readiness.py",
    "scripts/python/_b_route_chapter6_gate.py",
    "scripts/python/_b_route_chapter6_recovery.py",
    "scripts/python/_b_route_defect_routing.py",
    "scripts/python/_b_route_chapter7_slice.py",
    "scripts/python/_b_route_entrypoint_parity.py",
    "scripts/python/check_b_route_entrypoint_parity.py",
    "scripts/python/_project_health_http.py",
    "scripts/python/project_health_runtime.py",
    "scripts/python/run_single_task_chapter6_lane.py",
    "scripts/sc/run_review_pipeline.py",
    "scripts/sc/llm_review_needs_fix_fast.py",
    "scripts/python/resume_task.py",
    "scripts/python/chapter6_route.py",
    "scripts/python/_mvg_obligations.py",
)

_CONSUMER_REQUIRED_SYMBOLS: dict[str, tuple[str, ...]] = {
    "scripts/python/_project_health_http.py": (
        "handle_page_b_route_trigger",
        "enforce_mvg_manifest_gate",
        "acquire_runtime_scope_leases",
    ),
    "scripts/python/project_health_runtime.py": (
        "enforce_runtime_task_gate",
        "acquire_runtime_scope_leases",
    ),
    "scripts/python/run_single_task_chapter6_lane.py": (
        "guarded_chapter6_execution",
    ),
    "scripts/sc/run_review_pipeline.py": (
        "enforce_internal_script_gate",
    ),
    "scripts/sc/llm_review_needs_fix_fast.py": (
        "enforce_internal_script_gate",
    ),
    "scripts/python/resume_task.py": (
        "evaluate_chapter6_recovery",
        "build_chapter6_handoff_summary",
    ),
    "scripts/python/chapter6_route.py": (
        "evaluate_chapter6_recovery",
        "build_chapter6_handoff_summary",
    ),
    "scripts/python/_mvg_obligations.py": (
        "enforce_internal_script_gate",
    ),
}

EPIC3_CLI_COMMANDS = (
    "b-route-task-preview",
    "b-route-task-compile",
    "b-route-task-origin",
    "b-route-chapter4-binding",
    "b-route-input-set",
    "b-route-stage5-obligations",
    "b-route-chapter5-readiness",
    "b-route-chapter6-gate",
    "b-route-defect-routing",
    "b-route-chapter7-slice",
    "b-route-entrypoint-parity",
)

EPIC3_OWNING_DOCS = (
    "docs/workflows/b-route-task-preview.md",
    "docs/workflows/b-route-task-compilation.md",
    "docs/workflows/b-route-task-origin-resolution.md",
    "docs/workflows/b-route-chapter4-binding.md",
    "docs/workflows/b-route-input-set-resolution.md",
    "docs/workflows/b-route-stage5-obligations.md",
    "docs/workflows/b-route-chapter5-readiness.md",
    "docs/workflows/b-route-chapter6-gate.md",
    "docs/workflows/b-route-chapter6-recovery.md",
    "docs/workflows/b-route-defect-routing.md",
    "docs/workflows/b-route-chapter7-slice.md",
    "docs/workflows/b-route-entrypoint-parity.md",
    "docs/workflows/project-health-knowledge.md",
    "docs/workflows/stable-public-entrypoints.md",
    "docs/workflows/script-entrypoints-index.md",
    "AGENTS.md",
    ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
)

_DOC_REQUIRED_ANCHORS: dict[str, tuple[str, ...]] = {
    "docs/workflows/b-route-entrypoint-parity.md": (
        "b-route-entrypoint-parity",
        "/api/knowledge/b-route",
        "--epic3-handoff",
        "--handoff-report",
    ),
    "docs/workflows/project-health-knowledge.md": (
        "/api/knowledge/b-route",
    ),
    "docs/workflows/stable-public-entrypoints.md": (
        "b-route-entrypoint-parity",
    ),
    "docs/workflows/script-entrypoints-index.md": (
        "check_b_route_entrypoint_parity.py",
    ),
    "AGENTS.md": (
        "b-route-entrypoint-parity",
        "/api/knowledge/b-route",
    ),
}

UNIMPLEMENTED_EPIC4_EPIC5_CAPABILITIES = {
    "selective_verification_scope_runner": False,
    "complete_b_route_knowledge_progress_display": False,
    "reward_slice_end_to_end_pilot_executed": False,
    "full_repository_b_migration_completed": False,
    "cumulative_full_mvg_runtime_verified": False,
}

_COMPLETED_JOURNAL_STATES = frozenset({"completed", "complete", "published", "committed", "done", "cleaned"})
_INCOMPLETE_JOURNAL_STATES = frozenset(
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


def _diag(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref).to_dict()


def _norm_rel(raw: str) -> str:
    s = str(raw or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s.removeprefix("./")
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _normalize_prefixed_digest(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    if len(s) == 64 and all(c in "0123456789abcdef" for c in s):
        return f"sha256:{s}"
    return None


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = codec.strict_json_loads(path.read_bytes())
        return loaded if isinstance(loaded, dict) else None
    except (OSError, ValueError, codec.CodecError):
        return None


def _file_sha256_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        inventory.no_reparse(path)
        if not path.is_file():
            return None
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, codec.CodecError):
        return "unreadable"


def _git_main_ref_or_none(root_path: Path) -> str | None:
    if not (root_path / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root_path), "rev-parse", "--verify", "refs/heads/main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _snapshot_publication_pointers(root_path: Path) -> dict[str, str | None]:
    snap: dict[str, str | None] = {}
    for rel in PUBLICATION_POINTER_PATHS:
        snap[rel] = _file_sha256_or_none(root_path / rel)
    snap["refs/heads/main"] = _git_main_ref_or_none(root_path)
    return snap


def _diff_publication_pointers(
    root_path: Path,
    before: dict[str, str | None],
) -> tuple[bool, list[str], dict[str, str | None]]:
    after = _snapshot_publication_pointers(root_path)
    mutated = [key for key in sorted(before) if before.get(key) != after.get(key)]
    return len(mutated) == 0, mutated, after


def validate_report_path(root: Path | str, report_rel: str) -> tuple[Path, str]:
    """Validate an explicit canonical new logs/ci/.../*.json report path without touching disk."""
    root_path = task_resolver._validate_root(Path(root))
    if type(report_rel) is not str or not report_rel.strip():
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "nonempty repository-relative logs/ci/.../*.json path",
                report_rel,
                None,
            )
        )
    raw_stripped = report_rel.strip()
    try:
        norm = inventory.canonical_path(raw_stripped, allow_logs=True)
    except (codec.CodecError, ValueError) as exc:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.UNSAFE_PATH,
                codec.Stage.PATH,
                None,
                "canonical POSIX repository-relative logs/ci/.../*.json path",
                report_rel,
                None,
            )
        ) from exc
    if not norm.startswith("logs/ci/") or not norm.endswith(".json"):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.UNSAFE_PATH,
                codec.Stage.PATH,
                None,
                "repository-relative path under logs/ci/ ending with .json",
                report_rel,
                None,
            )
        )
    target = inventory.safe_input(root_path, norm, allow_logs=True)
    logs_ci_root = (root_path / "logs" / "ci").resolve()
    cur = target.parent
    ancestors: list[Path] = []
    while True:
        ancestors.append(cur)
        if cur == root_path.resolve() or cur == cur.parent:
            break
        cur = cur.parent
    for anc in reversed(ancestors):
        if anc.exists():
            inventory.no_reparse(anc)
    try:
        target.resolve().relative_to(logs_ci_root)
    except ValueError as exc:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.UNSAFE_PATH,
                codec.Stage.PATH,
                None,
                "path strictly contained within logs/ci/",
                report_rel,
                None,
            )
        ) from exc
    if target.exists():
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.PATH,
                None,
                "non-existing report path (exclusive creation)",
                norm,
                norm,
            )
        )
    return target, norm


def write_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> str:
    """Exclusively write JSON report under logs/ci/ and stamp report_path BEFORE writing."""
    target, norm = validate_report_path(root, report_rel)
    payload["report_path"] = norm
    target.parent.mkdir(parents=True, exist_ok=True)
    for anc in (target.parent, *target.parent.parents):
        if anc.exists():
            inventory.no_reparse(anc)
        if anc == Path(root).resolve():
            break
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        with target.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.CONFLICT,
                codec.Stage.PATH,
                None,
                "non-existing report path (exclusive creation)",
                norm,
                norm,
            )
        ) from exc
    return norm


@contextmanager
def acquire_chapter6_gate_lease(
    root: Path | str,
    task_id: Any,
    *,
    operation: str | None = None,
    consumer: str = "page",
    out_dir: Path | str | None = None,
) -> Iterator[ch6_gate.Chapter6ExecutionHandle]:
    """Acquire the exact same Story 3.8 business-scope lease used by CLI and direct entrypoints."""
    with ch6_gate.guarded_chapter6_execution(
        root,
        task_id,
        operation=operation,
        consumer=consumer,
        out_dir=out_dir,
    ) as handle:
        yield handle


@contextmanager
def acquire_runtime_scope_leases(
    root: Path | str,
    gate_res: dict[str, Any],
    *,
    consumer: str = "project_health_runtime",
) -> Iterator[dict[str, Any]]:
    """Acquire business-scope leases for single- or multi-task runtime/MVG runs without self-deadlock."""
    if not isinstance(gate_res, dict) or gate_res.get("legacy_a_passthrough"):
        yield {
            "lease_acquired": False,
            "inherited_lease": False,
            "scope_ids": [],
            "uses_global_writer_lock": False,
        }
        return
    gated_ids = [ch6_gate.parse_strict_task_id(x) for x in (gate_res.get("gated_task_ids") or [])]
    scope_ids = sorted(set(str(s) for s in (gate_res.get("scope_ids") or []) if str(s).strip()))
    if not gated_ids or not scope_ids:
        yield {
            "lease_acquired": False,
            "inherited_lease": False,
            "scope_ids": [],
            "uses_global_writer_lock": False,
        }
        return

    root_path = task_resolver._validate_root(Path(root))
    mode = str(gate_res.get("mode") or "main")
    env_path = os.environ.get(ch6_gate.ENV_LEASE_PATH)
    env_secret = os.environ.get(ch6_gate.ENV_LEASE_SECRET)

    # Reentrant child / parent-lease verification path (prevents Windows msvcrt self-deadlock).
    if env_path is not None or env_secret is not None:
        verified_receipt: dict[str, Any] | None = None
        try:
            for tid in gated_ids:
                verified_receipt = ch6_gate._verify_inherited_lease_receipt(
                    root_path,
                    tid,
                    str(env_path or ""),
                    str(env_secret or ""),
                )
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            blocked = {
                "schema_version": RUNTIME_GATE_SCHEMA,
                "ok": False,
                "admitted": False,
                "legacy_a_passthrough": False,
                "route": "blocked",
                "mode": mode,
                "reason_code": d["reason_code"],
                "public_reason_code": d["reason_code"],
                "reason": f"invalid_parent_lease:{d['reason_code']}",
                "blocked_by": "b_route_chapter6_gate",
                "return_stage": "5",
                "diagnostics": [d],
                **INVARIANT_FLAGS,
            }
            raise ch6_gate.Chapter6GateBlockedError(blocked) from err

        recheck = enforce_runtime_task_gate(root_path, gated_ids, mode=mode, consumer=consumer)
        if not recheck.get("ok"):
            raise ch6_gate.Chapter6GateBlockedError(recheck)
        parent_scopes = set((verified_receipt or {}).get("scope_ids") or ())
        if not set(recheck.get("scope_ids") or ()).issubset(parent_scopes):
            d = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(gated_ids[0]),
                expected=sorted(parent_scopes),
                actual={"scope_ids": recheck.get("scope_ids"), "return_stage": "5"},
                resume_ref=(verified_receipt or {}).get("receipt_rel"),
            )
            raise ch6_gate.Chapter6GateBlockedError(
                {
                    "schema_version": RUNTIME_GATE_SCHEMA,
                    "ok": False,
                    "admitted": False,
                    "legacy_a_passthrough": False,
                    "route": "B",
                    "mode": mode,
                    "reason_code": codec.ReasonCode.INPUT_STALE.value,
                    "public_reason_code": codec.ReasonCode.INPUT_STALE.value,
                    "reason": "runtime_scope_ids_exceed_parent_lease",
                    "blocked_by": "b_route_chapter6_gate",
                    "return_stage": "5",
                    "diagnostics": [d],
                    **INVARIANT_FLAGS,
                }
            )
        yield {
            "lease_acquired": True,
            "inherited_lease": True,
            "scope_ids": sorted(parent_scopes),
            "uses_global_writer_lock": False,
        }
        return

    # Top-level holder path via Story 2.6 business_guard(review_only=True) + under-lease revalidation.
    try:
        bg_cm = op_scope.business_guard(root_path, scope_ids, review_only=True)
        bg_cm.__enter__()
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        raise ch6_gate.Chapter6GateBlockedError(
            {
                "schema_version": RUNTIME_GATE_SCHEMA,
                "ok": False,
                "admitted": False,
                "legacy_a_passthrough": False,
                "route": "blocked",
                "mode": mode,
                "reason_code": d["reason_code"],
                "public_reason_code": d["reason_code"],
                "reason": f"scope_lease_acquire_failed:{d['reason_code']}",
                "blocked_by": "b_route_chapter6_gate",
                "return_stage": "5",
                "diagnostics": [d],
                **INVARIANT_FLAGS,
            }
        ) from err

    receipt_file: Path | None = None
    prev_env_path = os.environ.get(ch6_gate.ENV_LEASE_PATH)
    prev_env_secret = os.environ.get(ch6_gate.ENV_LEASE_SECRET)
    exc_info: tuple[Any, Any, Any] = (None, None, None)
    try:
        recheck = enforce_runtime_task_gate(root_path, gated_ids, mode=mode, consumer=consumer)
        if not recheck.get("ok"):
            raise ch6_gate.Chapter6GateBlockedError(recheck)
        live_scopes = set(recheck.get("scope_ids") or ())
        if not live_scopes.issubset(set(scope_ids)):
            d = _diag(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.BUNDLE,
                entity_id=str(gated_ids[0]),
                expected=scope_ids,
                actual={"scope_ids": sorted(live_scopes), "return_stage": "5"},
            )
            raise ch6_gate.Chapter6GateBlockedError(
                {
                    "schema_version": RUNTIME_GATE_SCHEMA,
                    "ok": False,
                    "admitted": False,
                    "legacy_a_passthrough": False,
                    "route": "B",
                    "mode": mode,
                    "reason_code": codec.ReasonCode.INPUT_STALE.value,
                    "public_reason_code": codec.ReasonCode.INPUT_STALE.value,
                    "reason": "runtime_scope_ids_expanded_under_lease",
                    "blocked_by": "b_route_chapter6_gate",
                    "return_stage": "5",
                    "diagnostics": [d],
                    **INVARIANT_FLAGS,
                }
            )
        per_task_digests: dict[str, str] = {}
        first_digest: str | None = None
        for prow in recheck.get("per_task") or []:
            if isinstance(prow, dict) and prow.get("task_id") is not None and prow.get("input_set_digest"):
                dg = str(prow["input_set_digest"])
                per_task_digests[str(prow["task_id"])] = dg
                if first_digest is None:
                    first_digest = dg
        if first_digest is None:
            iset0 = input_set.resolve_input_set(root_path, gated_ids[0])
            first_digest = str(iset0.get("input_set_digest") or ("sha256:" + ("0" * 64)))

        lease_id = uuid.uuid4().hex[:16]
        secret = secrets.token_hex(32)
        receipt_rel = f"{ch6_gate.LEASE_DIR}/runtime-{lease_id}.json"
        receipt_file = root_path / receipt_rel
        receipt_payload = {
            "schema_version": ch6_gate.LEASE_RECEIPT_SCHEMA,
            "lease_id": lease_id,
            "owner_pid": os.getpid(),
            "owner_create_time": ch6_gate._get_process_create_time(os.getpid()),
            "root_resolved": str(root_path.resolve()),
            "task_id": gated_ids[0],
            "task_ids": gated_ids,
            "route": str(recheck.get("route") or "B"),
            "scope_ids": scope_ids,
            "input_set_digest": first_digest,
            "per_task_input_set_digests": per_task_digests,
            "secret_sha256": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            **INVARIANT_FLAGS,
        }
        ch6_gate._atomic_write_json(receipt_file, receipt_payload)
        os.environ[ch6_gate.ENV_LEASE_PATH] = receipt_rel
        os.environ[ch6_gate.ENV_LEASE_SECRET] = secret

        yield {
            "lease_acquired": True,
            "inherited_lease": False,
            "lease_receipt_path": receipt_rel,
            "scope_ids": scope_ids,
            "uses_global_writer_lock": False,
        }
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
        bg_cm.__exit__(*exc_info)


def _check_live_transitive_task_eligibility(
    root_path: Path,
    tid: int,
    *,
    gate_res: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check live .taskmaster/tasks/tasks.json target task + multi-hop transitive dependency eligibility."""
    return ch6_recovery._check_task_and_dependency_eligibility(root_path, tid, gate_res=gate_res)


def _normalize_public_reason(
    *,
    ok: bool,
    route: str,
    reason_code: str | None,
    return_stage: str | None,
    blocked_by: str | None = None,
) -> tuple[str, str | None, str | None, bool]:
    """Standardize public rejection mapping across all five entrypoints and underlying modules."""
    if ok:
        return codec.ReasonCode.OK.value, None, None, False
    rc = str(reason_code or codec.ReasonCode.CONFLICT.value).strip() or codec.ReasonCode.CONFLICT.value
    rstage = str(return_stage).strip() if return_stage else None
    if not rstage:
        if rc in (codec.ReasonCode.PENDING.value, codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value):
            rstage = "3C"
        else:
            rstage = "5"
    blk = str(blocked_by).strip() if blocked_by else "b_route_chapter6_gate"
    if route == "blocked" and blk not in {"b_route_chapter6_gate", "b_route_defect_routing"}:
        blk = "b_route_chapter6_gate"
    readiness_invalidated = rc in {
        codec.ReasonCode.INPUT_STALE.value,
        codec.ReasonCode.DIGEST_MISMATCH.value,
        codec.ReasonCode.MAPPING_MISMATCH.value,
        codec.ReasonCode.FILE_NOT_FOUND.value,
        codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
        codec.ReasonCode.CONFLICT.value,
        codec.ReasonCode.PENDING.value,
        codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value,
        codec.ReasonCode.SEMANTIC_ERROR.value,
        codec.ReasonCode.UNPUBLISHED.value,
        codec.ReasonCode.UNKNOWN_ENTITY.value,
        codec.ReasonCode.UNKNOWN_FIELD.value,
        codec.ReasonCode.INVALID_REFERENCE.value,
        codec.ReasonCode.UNRESOLVED_REFERENCE.value,
        codec.ReasonCode.IDENTITY_UNPROVABLE.value,
        codec.ReasonCode.REVISION_MISMATCH.value,
        codec.ReasonCode.FILE_CHANGED.value,
        codec.ReasonCode.PATH_UNPROVABLE.value,
        codec.ReasonCode.UNSAFE_PATH.value,
        codec.ReasonCode.DUPLICATE_OWNER.value,
        codec.ReasonCode.INVALID_JSON.value,
        codec.ReasonCode.SCHEMA_VALIDATION_FAILED.value,
        codec.ReasonCode.SCHEMA_MISMATCH.value,
        codec.ReasonCode.UNKNOWN_SCHEMA.value,
    }
    return rc, blk, rstage, readiness_invalidated


def _resolve_optional_run_dir(
    root_path: Path,
    *,
    task_id: int,
    latest: str | None = None,
    run_id: str | None = None,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Safely resolve an optional run directory inside root_path without trusting escape or reparse paths."""
    if latest and str(latest).strip():
        norm = _norm_rel(str(latest))
        try:
            target = inventory.safe_input(root_path, norm, allow_logs=True)
        except (codec.CodecError, ValueError, OSError) as exc:
            return None, _diag(
                codec.ReasonCode.UNSAFE_PATH,
                stage=codec.Stage.PATH,
                entity_id=str(task_id),
                expected="repository-contained latest.json path",
                actual=str(exc),
                resume_ref=norm,
            )
        doc = _safe_read_json(target)
        if isinstance(doc, dict):
            raw_out = str(doc.get("latest_out_dir") or "").strip()
            if raw_out:
                out_norm = _norm_rel(raw_out)
                try:
                    return inventory.safe_input(root_path, out_norm, allow_logs=True), None
                except (codec.CodecError, ValueError, OSError) as exc:
                    return None, _diag(
                        codec.ReasonCode.UNSAFE_PATH,
                        stage=codec.Stage.PATH,
                        entity_id=str(task_id),
                        expected="repository-contained latest_out_dir",
                        actual=str(exc),
                        resume_ref=out_norm,
                    )
        return target.parent, None
    if run_id and str(run_id).strip():
        rid = str(run_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", rid):
            return None, _diag(
                codec.ReasonCode.INVALID_ARGUMENT,
                stage=codec.Stage.CONTENT,
                entity_id=str(task_id),
                expected="portable run_id token",
                actual=rid,
            )
        logs_ci = root_path / "logs" / "ci"
        if os.path.lexists(logs_ci):
            try:
                inventory.no_reparse(logs_ci)
                if logs_ci.is_dir():
                    matches = sorted(logs_ci.glob(f"*/sc-review-pipeline-task-{task_id}-{rid}"))
                    if matches:
                        cand = matches[-1]
                        for anc in (logs_ci, cand.parent, cand):
                            inventory.no_reparse(anc)
                        if not cand.is_dir():
                            raise ValueError("matched run_dir is not a directory")
                        resolved_cand = cand.resolve()
                        resolved_cand.relative_to(logs_ci.resolve())
                        return resolved_cand, None
            except (codec.CodecError, ValueError, OSError) as exc:
                return None, _diag(
                    codec.ReasonCode.UNSAFE_PATH,
                    stage=codec.Stage.PATH,
                    entity_id=str(task_id),
                    expected="non-reparse run_dir strictly contained within logs/ci/",
                    actual=str(exc),
                    resume_ref="logs/ci",
                )
    return None, None


def _evaluate_unified_live_decision(
    root_path: Path,
    tid: int,
    *,
    operation: str | None = None,
    run_dir: Path | None = None,
    consumer: str = "page",
    recommendation_only: bool = True,
    enforce_durable_stop_loss: bool = False,
) -> dict[str, Any]:
    """Run live Story 3.9 recovery (which invokes live Story 3.8 gate + pending + eligibility) once."""
    rec_res = ch6_recovery.evaluate_chapter6_recovery(
        root_path,
        tid,
        run_dir=run_dir,
        operation=operation or "implement",
        recommendation_only=recommendation_only,
        consumer=consumer,
        enforce_durable_stop_loss=enforce_durable_stop_loss,
    )
    gate_res = rec_res.get("gate_result") if isinstance(rec_res.get("gate_result"), dict) else None
    route = str(rec_res.get("route") or (gate_res or {}).get("route") or "blocked")

    if not rec_res.get("ok"):
        pub_rc, blk, norm_stage, inv = _normalize_public_reason(
            ok=False,
            route=route,
            reason_code=rec_res.get("reason_code"),
            return_stage=rec_res.get("return_stage"),
        )
        return {
            "ok": False,
            "admitted": False,
            "route": route,
            "reason_code": pub_rc,
            "public_reason_code": pub_rc,
            "reason": str(rec_res.get("reason") or "b_route_gate_blocked"),
            "blocked_by": blk,
            "return_stage": norm_stage,
            "resume_ref": rec_res.get("resume_ref")
            or ch6_recovery._extract_resume_ref(list(rec_res.get("diagnostics") or [])),
            "applicable_set_digest": rec_res.get("applicable_set_digest")
            or (gate_res or {}).get("applicable_set_digest"),
            "input_set_digest": rec_res.get("input_set_digest") or (gate_res or {}).get("input_set_digest"),
            "scope_ids": sorted(set(rec_res.get("scope_ids") or (gate_res or {}).get("scope_ids") or [])),
            "readiness_invalidated": inv,
            "legacy_a_passthrough": False,
            "diagnostics": list(rec_res.get("diagnostics") or []),
            "gate_result": gate_res,
            "recovery_result": rec_res,
            "task_eligibility": rec_res.get("eligibility") or rec_res.get("task_eligibility"),
        }

    if rec_res.get("legacy_a_passthrough") or route == "explicit_not_enabled_a":
        return {
            "ok": True,
            "admitted": True,
            "route": "explicit_not_enabled_a",
            "reason_code": codec.ReasonCode.OK.value,
            "public_reason_code": codec.ReasonCode.OK.value,
            "reason": "explicit_not_enabled_a",
            "blocked_by": None,
            "return_stage": None,
            "resume_ref": None,
            "applicable_set_digest": None,
            "input_set_digest": None,
            "scope_ids": [],
            "readiness_invalidated": False,
            "legacy_a_passthrough": True,
            "diagnostics": [],
            "gate_result": gate_res,
            "recovery_result": rec_res,
            "task_eligibility": rec_res.get("eligibility") or rec_res.get("task_eligibility"),
        }

    eligibility = _check_live_transitive_task_eligibility(root_path, tid, gate_res=gate_res)
    if not eligibility.get("ok"):
        pub_rc, blk, norm_stage, inv = _normalize_public_reason(
            ok=False,
            route=route,
            reason_code=eligibility.get("reason_code"),
            return_stage=eligibility.get("return_stage"),
        )
        return {
            "ok": False,
            "admitted": False,
            "route": route,
            "reason_code": pub_rc,
            "public_reason_code": pub_rc,
            "reason": str(eligibility.get("reason") or "task_ineligible"),
            "blocked_by": blk,
            "return_stage": norm_stage,
            "resume_ref": task_resolver.TRIPLET["master"],
            "applicable_set_digest": (gate_res or {}).get("applicable_set_digest")
            or rec_res.get("applicable_set_digest"),
            "input_set_digest": (gate_res or {}).get("input_set_digest") or rec_res.get("input_set_digest"),
            "scope_ids": sorted(set((gate_res or {}).get("scope_ids") or rec_res.get("scope_ids") or [])),
            "readiness_invalidated": inv,
            "legacy_a_passthrough": False,
            "diagnostics": list(eligibility.get("diagnostics") or []),
            "gate_result": gate_res,
            "recovery_result": rec_res,
            "task_eligibility": eligibility,
        }

    return {
        "ok": True,
        "admitted": True,
        "route": route,
        "reason_code": codec.ReasonCode.OK.value,
        "public_reason_code": codec.ReasonCode.OK.value,
        "reason": str((gate_res or {}).get("reason") or rec_res.get("reason") or "admitted"),
        "blocked_by": None,
        "return_stage": None,
        "resume_ref": None,
        "applicable_set_digest": (gate_res or {}).get("applicable_set_digest")
        or rec_res.get("applicable_set_digest"),
        "input_set_digest": (gate_res or {}).get("input_set_digest") or rec_res.get("input_set_digest"),
        "scope_ids": sorted(set((gate_res or {}).get("scope_ids") or rec_res.get("scope_ids") or [])),
        "readiness_invalidated": False,
        "legacy_a_passthrough": False,
        "diagnostics": [],
        "gate_result": gate_res,
        "recovery_result": rec_res,
        "task_eligibility": eligibility,
    }


def _blocked_page_payload(
    *,
    started: float,
    action: str | None,
    task_id: int | None,
    mode: str,
    preview: bool,
    recommendation_only: bool,
    route: str,
    reason_code: str,
    reason: str,
    return_stage: str | None,
    diagnostics: list[dict[str, Any]],
    blocked_by: str = "b_route_chapter6_gate",
    resume_ref: str | None = None,
    applicable_set_digest: str | None = None,
    input_set_digest: str | None = None,
    scope_ids: list[str] | None = None,
    ignored_cache_fields: list[str] | None = None,
    publication_pointers_preserved: bool = True,
    mutated_publication_pointers: list[str] | None = None,
    gate_result: dict[str, Any] | None = None,
    recovery_result: dict[str, Any] | None = None,
    defect_routing_result: dict[str, Any] | None = None,
    task_eligibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pub_rc, blk, norm_stage, inv = _normalize_public_reason(
        ok=False,
        route=route,
        reason_code=reason_code,
        return_stage=return_stage,
        blocked_by=blocked_by,
    )
    return {
        "schema_version": PAGE_TRIGGER_SCHEMA,
        "ok": False,
        "admitted": False,
        "action": action,
        "task_id": task_id,
        "mode": mode,
        "preview": preview,
        "recommendation_only": recommendation_only,
        "route": route,
        "reason_code": pub_rc,
        "public_reason_code": pub_rc,
        "reason": reason,
        "blocked_by": blk,
        "return_stage": norm_stage,
        "resume_ref": resume_ref or ch6_recovery._extract_resume_ref(diagnostics),
        "applicable_set_digest": applicable_set_digest,
        "input_set_digest": input_set_digest,
        "scope_ids": sorted(set(scope_ids or [])),
        "readiness_invalidated": inv,
        "lease_acquired": False,
        "uses_global_writer_lock": False,
        "live_authority_enforced": True,
        "cache_authorization_rejected": True,
        "ignored_cache_fields": sorted(set(ignored_cache_fields or [])),
        "publication_pointers_preserved": publication_pointers_preserved,
        "mutated_publication_pointers": list(mutated_publication_pointers or []),
        "task_eligibility": task_eligibility,
        "gate_result": gate_result,
        "recovery_result": recovery_result,
        "defect_routing_result": defect_routing_result,
        "execution_result": None,
        "flow_completed": False,
        "self_done_required": False,
        "diagnostics": list(diagnostics),
        "metrics": {
            "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
            "model_invocation_count": 0,
        },
        **INVARIANT_FLAGS,
    }


def _resolve_defect_routing_for_page(
    root_path: Path,
    tid: int,
    *,
    run_dir: Path | None,
    recovery_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    effective_run_dir = run_dir
    if effective_run_dir is None and isinstance(recovery_result, dict):
        latest_durable = str((recovery_result.get("durable_signals") or {}).get("latest_durable_run_dir") or "").strip()
        if latest_durable:
            try:
                cand = inventory.safe_input(root_path, _norm_rel(latest_durable), allow_logs=True)
                if cand.is_dir():
                    effective_run_dir = cand
            except (codec.CodecError, ValueError, OSError):
                effective_run_dir = None
    try:
        return defect_routing.build_chapter6_handoff_summary(
            root_path,
            tid,
            run_dir=effective_run_dir,
            recovery_result=recovery_result,
        )
    except Exception:
        return None


def handle_page_b_route_trigger(
    root: Path | str,
    request: dict[str, Any],
    *,
    execute_runner: Callable[[dict[str, Any], ch6_gate.Chapter6ExecutionHandle], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Shared page execution / recovery / route service invoked by POST /api/knowledge/b-route."""
    started = time.monotonic()
    if not isinstance(request, dict):
        diag = _diag(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.CONTENT,
            expected="JSON object request",
            actual=type(request).__name__,
        )
        return _blocked_page_payload(
            started=started,
            action=None,
            task_id=None,
            mode="main",
            preview=True,
            recommendation_only=True,
            route="blocked",
            reason_code=diag["reason_code"],
            reason="invalid_page_request_type",
            return_stage="5",
            diagnostics=[diag],
        )

    action = str(request.get("action") or "").strip().lower()
    mode = str(request.get("mode") or "main").strip().lower()
    ignored_cache_fields = [k for k in SPOOFED_CLIENT_CACHE_KEYS if k in request]
    forbidden_bypass = [k for k in FORBIDDEN_BYPASS_KEYS if k in request and request.get(k) is not False]

    if "preview" in request and type(request["preview"]) is not bool:
        d = _diag(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.CONTENT,
            expected="boolean 'preview'",
            actual={"type": type(request["preview"]).__name__, "value": request["preview"]},
        )
        return _blocked_page_payload(
            started=started,
            action=action or None,
            task_id=None,
            mode=mode if mode in VALID_PAGE_MODES else "main",
            preview=True,
            recommendation_only=True,
            route="blocked",
            reason_code=d["reason_code"],
            reason="invalid_preview_type",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )
    preview = request["preview"] if "preview" in request else False

    rec_only_default = action != "execute"
    if "recommendation_only" in request and type(request["recommendation_only"]) is not bool:
        d = _diag(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.CONTENT,
            expected="boolean 'recommendation_only'",
            actual={"type": type(request["recommendation_only"]).__name__, "value": request["recommendation_only"]},
        )
        return _blocked_page_payload(
            started=started,
            action=action or None,
            task_id=None,
            mode=mode if mode in VALID_PAGE_MODES else "main",
            preview=preview,
            recommendation_only=True,
            route="blocked",
            reason_code=d["reason_code"],
            reason="invalid_recommendation_only_type",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )
    recommendation_only = request["recommendation_only"] if "recommendation_only" in request else rec_only_default
    if preview:
        recommendation_only = True

    try:
        root_path = task_resolver._validate_root(Path(root))
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        return _blocked_page_payload(
            started=started,
            action=action or None,
            task_id=None,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_root:{d['reason_code']}",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )

    if action not in VALID_PAGE_ACTIONS:
        d = _diag(
            codec.ReasonCode.INVALID_ENUM,
            stage=codec.Stage.CONTENT,
            expected=sorted(VALID_PAGE_ACTIONS),
            actual=action,
        )
        return _blocked_page_payload(
            started=started,
            action=action or None,
            task_id=None,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_page_action:{action}",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )

    if mode not in VALID_PAGE_MODES:
        d = _diag(
            codec.ReasonCode.INVALID_ENUM,
            stage=codec.Stage.CONTENT,
            expected=sorted(VALID_PAGE_MODES),
            actual=mode,
        )
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=None,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_page_mode:{mode}",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )

    try:
        tid = ch6_gate.parse_strict_task_id(request.get("task_id"))
        operation = task_resolver._validate_operation(request.get("operation"))
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=None,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_page_arguments:{d['reason_code']}",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields,
        )

    if forbidden_bypass:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(tid),
            expected="live gate authorization without snapshot/cache bypass",
            actual={"forbidden_bypass_keys": forbidden_bypass, "return_stage": "5"},
            resume_ref="docs/workflows/b-route-entrypoint-parity.md",
        )
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=tid,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=codec.ReasonCode.CONFLICT.value,
            reason="page_cache_or_summary_authorization_forbidden",
            return_stage="5",
            diagnostics=[d],
            ignored_cache_fields=ignored_cache_fields + forbidden_bypass,
        )

    before_pointers = _snapshot_publication_pointers(root_path)
    run_dir, run_dir_diag = _resolve_optional_run_dir(
        root_path,
        task_id=tid,
        latest=request.get("latest"),
        run_id=request.get("run_id"),
    )
    if run_dir_diag is not None:
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=tid,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route="blocked",
            reason_code=run_dir_diag["reason_code"],
            reason="invalid_run_reference",
            return_stage="5",
            diagnostics=[run_dir_diag],
            ignored_cache_fields=ignored_cache_fields,
        )

    effective_operation = operation or _PAGE_ACTION_TO_OPERATION.get(action, "implement")
    enforce_stop_loss = action in {"execute", "resume", "route"}
    should_acquire_lease = (
        action in {"execute", "resume", "route"}
        and (not preview)
        and (not recommendation_only)
    )

    # Pre-lease live evaluation (guarantees zero lock/receipt side effects when blocked).
    decision = _evaluate_unified_live_decision(
        root_path,
        tid,
        operation=effective_operation,
        run_dir=run_dir,
        consumer=f"page:{action}",
        recommendation_only=recommendation_only,
        enforce_durable_stop_loss=enforce_stop_loss,
    )

    defect_res: dict[str, Any] | None = None
    if action in {"execute", "resume", "route"} and not decision.get("legacy_a_passthrough"):
        defect_res = _resolve_defect_routing_for_page(
            root_path,
            tid,
            run_dir=run_dir,
            recovery_result=decision.get("recovery_result"),
        )

    def _is_defect_blocked(dres: dict[str, Any] | None, rec_ok: bool) -> bool:
        if not isinstance(dres, dict):
            return False
        if dres.get("defect_class") == "disguised_definition_change":
            return True
        if rec_ok and dres.get("local_repair_allowed") is False:
            return True
        return False

    if _is_defect_blocked(defect_res, bool(decision.get("ok"))):
        assert isinstance(defect_res, dict)
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=tid,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route=decision["route"],
            reason_code=str(defect_res.get("reason_code") or codec.ReasonCode.CONFLICT.value),
            reason=str(defect_res.get("reason") or "disguised_definition_change"),
            return_stage=str(defect_res.get("return_stage") or "5"),
            diagnostics=list(defect_res.get("diagnostics") or []),
            blocked_by="b_route_defect_routing",
            resume_ref=defect_res.get("resume_ref"),
            applicable_set_digest=decision["applicable_set_digest"],
            input_set_digest=decision["input_set_digest"],
            scope_ids=decision["scope_ids"],
            ignored_cache_fields=ignored_cache_fields,
            gate_result=decision["gate_result"],
            recovery_result=decision["recovery_result"],
            defect_routing_result=defect_res,
            task_eligibility=decision["task_eligibility"],
        )

    if not decision["ok"]:
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=tid,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route=decision["route"],
            reason_code=decision["reason_code"],
            reason=decision["reason"],
            return_stage=decision["return_stage"],
            diagnostics=decision["diagnostics"],
            blocked_by=decision["blocked_by"] or "b_route_chapter6_gate",
            resume_ref=decision["resume_ref"],
            applicable_set_digest=decision["applicable_set_digest"],
            input_set_digest=decision["input_set_digest"],
            scope_ids=decision["scope_ids"],
            ignored_cache_fields=ignored_cache_fields,
            gate_result=decision["gate_result"],
            recovery_result=decision["recovery_result"],
            defect_routing_result=defect_res,
            task_eligibility=decision["task_eligibility"],
        )

    lease_acquired = False
    locked_scope_ids = list(decision["scope_ids"])
    execution_result: dict[str, Any] | None = None

    if should_acquire_lease:
        try:
            with acquire_chapter6_gate_lease(
                root_path,
                tid,
                operation=effective_operation,
                consumer=f"page:{action}",
            ) as handle:
                # Re-verify recovery, durable stop-loss, eligibility, and defect routing INSIDE the held lease!
                under_lease = _evaluate_unified_live_decision(
                    root_path,
                    tid,
                    operation=effective_operation,
                    run_dir=run_dir,
                    consumer=f"page:{action}",
                    recommendation_only=recommendation_only,
                    enforce_durable_stop_loss=enforce_stop_loss,
                )
                under_defect: dict[str, Any] | None = None
                if not under_lease.get("legacy_a_passthrough"):
                    under_defect = _resolve_defect_routing_for_page(
                        root_path,
                        tid,
                        run_dir=run_dir,
                        recovery_result=under_lease.get("recovery_result"),
                    )
                if _is_defect_blocked(under_defect, bool(under_lease.get("ok"))):
                    assert isinstance(under_defect, dict)
                    return _blocked_page_payload(
                        started=started,
                        action=action,
                        task_id=tid,
                        mode=mode,
                        preview=preview,
                        recommendation_only=recommendation_only,
                        route=under_lease["route"],
                        reason_code=str(under_defect.get("reason_code") or codec.ReasonCode.CONFLICT.value),
                        reason=str(under_defect.get("reason") or "disguised_definition_change"),
                        return_stage=str(under_defect.get("return_stage") or "5"),
                        diagnostics=list(under_defect.get("diagnostics") or []),
                        blocked_by="b_route_defect_routing",
                        resume_ref=under_defect.get("resume_ref"),
                        applicable_set_digest=under_lease["applicable_set_digest"],
                        input_set_digest=under_lease["input_set_digest"],
                        scope_ids=list(handle.scope_ids),
                        ignored_cache_fields=ignored_cache_fields,
                        gate_result=under_lease["gate_result"],
                        recovery_result=under_lease["recovery_result"],
                        defect_routing_result=under_defect,
                        task_eligibility=under_lease["task_eligibility"],
                    )
                if not under_lease["ok"]:
                    return _blocked_page_payload(
                        started=started,
                        action=action,
                        task_id=tid,
                        mode=mode,
                        preview=preview,
                        recommendation_only=recommendation_only,
                        route=under_lease["route"],
                        reason_code=under_lease["reason_code"],
                        reason=under_lease["reason"],
                        return_stage=under_lease["return_stage"],
                        diagnostics=under_lease["diagnostics"],
                        blocked_by=under_lease["blocked_by"] or "b_route_chapter6_gate",
                        resume_ref=under_lease["resume_ref"],
                        applicable_set_digest=under_lease["applicable_set_digest"],
                        input_set_digest=under_lease["input_set_digest"],
                        scope_ids=list(handle.scope_ids),
                        ignored_cache_fields=ignored_cache_fields,
                        gate_result=under_lease["gate_result"],
                        recovery_result=under_lease["recovery_result"],
                        defect_routing_result=under_defect,
                        task_eligibility=under_lease["task_eligibility"],
                    )

                decision = under_lease
                defect_res = under_defect
                lease_acquired = True
                locked_scope_ids = sorted(set(handle.scope_ids))
                if execute_runner is not None:
                    execution_result = execute_runner(
                        {
                            "action": action,
                            "task_id": tid,
                            "mode": mode,
                            "preview": preview,
                            "recommendation_only": recommendation_only,
                            "delivery_profile": request.get("delivery_profile"),
                            "godot_bin": request.get("godot_bin"),
                            "input_set_digest": decision["input_set_digest"],
                            "applicable_set_digest": decision["applicable_set_digest"],
                            "scope_ids": locked_scope_ids,
                        },
                        handle,
                    )
                else:
                    execution_result = {
                        "status": f"admitted_ready_to_{action}",
                        "task_id": tid,
                        "action": action,
                        "mode": mode,
                        "scope_ids": locked_scope_ids,
                        "input_set_digest": decision["input_set_digest"],
                        "applicable_set_digest": decision["applicable_set_digest"],
                        **INVARIANT_FLAGS,
                    }
        except ch6_gate.Chapter6GateBlockedError as err:
            gr = err.gate_result
            return _blocked_page_payload(
                started=started,
                action=action,
                task_id=tid,
                mode=mode,
                preview=preview,
                recommendation_only=recommendation_only,
                route=str(gr.get("route") or "blocked"),
                reason_code=str(gr.get("reason_code") or codec.ReasonCode.CONFLICT.value),
                reason=str(gr.get("reason") or "lease_or_gate_blocked"),
                return_stage=gr.get("return_stage") or "5",
                diagnostics=list(gr.get("diagnostics") or []),
                applicable_set_digest=gr.get("applicable_set_digest"),
                input_set_digest=gr.get("input_set_digest"),
                scope_ids=list(gr.get("scope_ids") or []),
                ignored_cache_fields=ignored_cache_fields,
                gate_result=gr,
                recovery_result=decision["recovery_result"],
                defect_routing_result=defect_res,
                task_eligibility=decision["task_eligibility"],
            )

    pointers_ok, mutated_pointers, _after_pointers = _diff_publication_pointers(root_path, before_pointers)
    if (preview or recommendation_only or mode == "workspace") and not pointers_ok:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(tid),
            expected="zero mutation of current/last-known-good/latest.json/main in preview or workspace mode",
            actual={"mutated_pointers": mutated_pointers, "mode": mode, "preview": preview},
            resume_ref="docs/workflows/project-health-knowledge.md",
        )
        return _blocked_page_payload(
            started=started,
            action=action,
            task_id=tid,
            mode=mode,
            preview=preview,
            recommendation_only=recommendation_only,
            route=decision["route"],
            reason_code=codec.ReasonCode.CONFLICT.value,
            reason="publication_pointer_mutated_in_preview_or_workspace",
            return_stage="5",
            diagnostics=[d],
            applicable_set_digest=decision["applicable_set_digest"],
            input_set_digest=decision["input_set_digest"],
            scope_ids=locked_scope_ids,
            ignored_cache_fields=ignored_cache_fields,
            publication_pointers_preserved=False,
            mutated_publication_pointers=mutated_pointers,
            gate_result=decision["gate_result"],
            recovery_result=decision["recovery_result"],
            defect_routing_result=defect_res,
            task_eligibility=decision["task_eligibility"],
        )

    return {
        "schema_version": PAGE_TRIGGER_SCHEMA,
        "ok": True,
        "admitted": True,
        "action": action,
        "task_id": tid,
        "mode": mode,
        "preview": preview,
        "recommendation_only": recommendation_only,
        "route": decision["route"],
        "reason_code": codec.ReasonCode.OK.value,
        "public_reason_code": codec.ReasonCode.OK.value,
        "reason": decision["reason"],
        "blocked_by": None,
        "return_stage": None,
        "resume_ref": None,
        "applicable_set_digest": decision["applicable_set_digest"],
        "input_set_digest": decision["input_set_digest"],
        "scope_ids": locked_scope_ids,
        "readiness_invalidated": False,
        "lease_acquired": lease_acquired,
        "uses_global_writer_lock": False,
        "live_authority_enforced": True,
        "cache_authorization_rejected": True,
        "ignored_cache_fields": sorted(set(ignored_cache_fields)),
        "publication_pointers_preserved": pointers_ok,
        "mutated_publication_pointers": mutated_pointers,
        "task_eligibility": decision["task_eligibility"],
        "gate_result": decision["gate_result"],
        "recovery_result": decision["recovery_result"],
        "defect_routing_result": defect_res,
        "execution_result": execution_result,
        "flow_completed": False,
        "self_done_required": False,
        "diagnostics": [],
        "metrics": {
            "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
            "model_invocation_count": 0,
        },
        **INVARIANT_FLAGS,
    }


def enforce_runtime_task_gate(
    root: Path | str,
    task_ids: list[int | str] | tuple[int | str, ...],
    *,
    mode: str = "main",
    consumer: str = "project_health_runtime",
) -> dict[str, Any]:
    """Live pre-flight gate invoked by project_health_runtime.py BEFORE snapshot or Godot launch."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))
    try:
        parsed_tids = [ch6_gate.parse_strict_task_id(raw_id) for raw_id in task_ids]
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "mode": mode,
            "reason_code": d["reason_code"],
            "public_reason_code": d["reason_code"],
            "reason": f"invalid_task_id:{d['reason_code']}",
            "blocked_by": "b_route_chapter6_gate",
            "return_stage": "3C",
            "gated_task_ids": [],
            "scope_ids": [],
            "per_task": [],
            "diagnostics": [d],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    # Always inspect pending markers / damaged journals BEFORE iterating task_ids (even if parsed_tids == []).
    cand_scopes: set[str] | None = None
    if parsed_tids:
        union_cand: set[str] = set()
        all_resolved = True
        for ptid in parsed_tids:
            ts = ch6_recovery._resolve_candidate_task_scopes(root_path, ptid, "implement")
            if ts is None:
                all_resolved = False
                break
            union_cand.update(ts)
        if all_resolved:
            cand_scopes = union_cand
    pending_pre = ch6_recovery._inspect_pending_and_post_edits(
        root_path,
        parsed_tids[0] if len(parsed_tids) == 1 else 0,
        scope_ids=cand_scopes,
    )
    if pending_pre.get("blocked"):
        pub_rc, blk, norm_stage, inv = _normalize_public_reason(
            ok=False,
            route="blocked",
            reason_code=pending_pre.get("reason_code"),
            return_stage=pending_pre.get("return_stage") or "3C",
        )
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "mode": mode,
            "reason_code": pub_rc,
            "public_reason_code": pub_rc,
            "reason": str(pending_pre.get("reason") or "pending_journal"),
            "blocked_by": blk,
            "return_stage": norm_stage,
            "resume_ref": pending_pre.get("resume_ref"),
            "readiness_invalidated": inv,
            "gated_task_ids": [],
            "scope_ids": [],
            "per_task": [],
            "diagnostics": list(pending_pre.get("diagnostics") or []),
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    presence = ch6_gate.detect_b_route_presence(root_path, None)
    per_task_presences = [ch6_gate.detect_b_route_presence(root_path, tid) for tid in parsed_tids]
    should_enforce = bool(presence.get("should_enforce_gate")) or any(
        bool(p.get("should_enforce_gate")) for p in per_task_presences
    )
    has_b_markers = bool(
        presence.get("has_b_traces")
        or presence.get("capability_apply_pending")
        or presence.get("pending_journals")
        or presence.get("na_labels")
        or presence.get("has_lease_env")
        or any(
            p.get("has_b_traces") or p.get("na_labels") or p.get("pending_journals") or p.get("capability_apply_pending")
            for p in per_task_presences
        )
    )
    if not should_enforce:
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": True,
            "admitted": True,
            "legacy_a_passthrough": True,
            "route": "explicit_not_enabled_a",
            "mode": mode,
            "reason_code": codec.ReasonCode.OK.value,
            "public_reason_code": codec.ReasonCode.OK.value,
            "reason": "explicit_not_enabled_a",
            "blocked_by": None,
            "return_stage": None,
            "gated_task_ids": [],
            "scope_ids": [],
            "per_task": [],
            "diagnostics": [],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    if not parsed_tids:
        if has_b_markers:
            d = _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id="runtime_task_selection",
                expected="at least one governed Task ID for runtime verification under B governance",
                actual={"task_ids": [], "return_stage": "3C"},
                resume_ref=task_resolver.ORIGINS_PATH,
            )
            return {
                "schema_version": RUNTIME_GATE_SCHEMA,
                "ok": False,
                "admitted": False,
                "legacy_a_passthrough": False,
                "route": "blocked",
                "mode": mode,
                "reason_code": codec.ReasonCode.CONFLICT.value,
                "public_reason_code": codec.ReasonCode.CONFLICT.value,
                "reason": "empty_runtime_task_selection_under_b_governance",
                "blocked_by": "b_route_chapter6_gate",
                "return_stage": "3C",
                "resume_ref": task_resolver.ORIGINS_PATH,
                "readiness_invalidated": True,
                "gated_task_ids": [],
                "scope_ids": [],
                "per_task": [],
                "diagnostics": [d],
                "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
                **INVARIANT_FLAGS,
            }
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": True,
            "admitted": True,
            "legacy_a_passthrough": True,
            "route": "explicit_not_enabled_a",
            "mode": mode,
            "reason_code": codec.ReasonCode.OK.value,
            "public_reason_code": codec.ReasonCode.OK.value,
            "reason": "explicit_not_enabled_a",
            "blocked_by": None,
            "return_stage": None,
            "gated_task_ids": [],
            "scope_ids": [],
            "per_task": [],
            "diagnostics": [],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    per_task: list[dict[str, Any]] = []
    gated_ids: list[int] = []
    union_scopes: set[str] = set()
    for tid in parsed_tids:
        decision = _evaluate_unified_live_decision(
            root_path,
            tid,
            operation="implement",
            consumer=consumer,
            enforce_durable_stop_loss=False,
        )
        per_task.append(
            {
                "task_id": tid,
                "ok": decision["ok"],
                "route": decision["route"],
                "reason_code": decision["public_reason_code"],
                "blocked_by": decision["blocked_by"],
                "return_stage": decision["return_stage"],
                "applicable_set_digest": decision["applicable_set_digest"],
                "input_set_digest": decision["input_set_digest"],
                "scope_ids": decision["scope_ids"],
                "readiness_invalidated": decision["readiness_invalidated"],
            }
        )
        if not decision["ok"]:
            return {
                "schema_version": RUNTIME_GATE_SCHEMA,
                "ok": False,
                "admitted": False,
                "legacy_a_passthrough": False,
                "route": decision["route"],
                "mode": mode,
                "task_id": tid,
                "reason_code": decision["public_reason_code"],
                "public_reason_code": decision["public_reason_code"],
                "reason": decision["reason"],
                "blocked_by": decision["blocked_by"] or "b_route_chapter6_gate",
                "return_stage": decision["return_stage"],
                "resume_ref": decision["resume_ref"],
                "applicable_set_digest": decision["applicable_set_digest"],
                "input_set_digest": decision["input_set_digest"],
                "readiness_invalidated": decision["readiness_invalidated"],
                "gated_task_ids": gated_ids,
                "scope_ids": sorted(union_scopes),
                "per_task": per_task,
                "diagnostics": decision["diagnostics"],
                "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
                **INVARIANT_FLAGS,
            }
        if decision["route"] in ("B", "A"):
            gated_ids.append(tid)
            union_scopes.update(decision["scope_ids"])

    is_legacy_passthrough = (len(gated_ids) == 0) and (not has_b_markers)
    return {
        "schema_version": RUNTIME_GATE_SCHEMA,
        "ok": True,
        "admitted": True,
        "legacy_a_passthrough": is_legacy_passthrough,
        "route": "B" if any(r["route"] == "B" for r in per_task) else ("A" if gated_ids else "explicit_not_enabled_a"),
        "mode": mode,
        "reason_code": codec.ReasonCode.OK.value,
        "public_reason_code": codec.ReasonCode.OK.value,
        "reason": "explicit_not_enabled_a" if is_legacy_passthrough else "admitted",
        "blocked_by": None,
        "return_stage": None,
        "resume_ref": None,
        "gated_task_ids": gated_ids,
        "scope_ids": sorted(union_scopes),
        "per_task": per_task,
        "diagnostics": [],
        "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
        **INVARIANT_FLAGS,
    }


def _json_contains_exact_path(node: Any, target_norm: str) -> bool:
    if isinstance(node, str):
        return _norm_rel(node) == target_norm
    if isinstance(node, dict):
        return any(_json_contains_exact_path(v, target_norm) for v in node.values())
    if isinstance(node, list):
        return any(_json_contains_exact_path(item, target_norm) for item in node)
    return False


def _collect_b_route_tasks_for_manifest(root_path: Path, manifest_rel: str) -> tuple[list[int], dict[str, Any] | None]:
    """Find master task IDs bound to a manifest (failing closed on tampered origins/bindings or empty matches)."""
    origins_rel = task_resolver.ORIGINS_PATH
    try:
        origins_path = inventory.safe_input(root_path, origins_rel, allow_logs=False)
    except (codec.CodecError, ValueError, OSError) as exc:
        return [], _diag(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=manifest_rel,
            expected=origins_rel,
            actual={"error": str(exc), "return_stage": "3C"},
            resume_ref=origins_rel,
        )
    if not origins_path.is_file():
        return [], _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=manifest_rel,
            expected=origins_rel,
            actual={"exists": False, "return_stage": "3C"},
            resume_ref=origins_rel,
        )
    try:
        origins_doc = codec.strict_json_loads(origins_path.read_bytes())
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        d["resume_ref"] = origins_rel
        return [], d
    if not isinstance(origins_doc, dict) or not isinstance(origins_doc.get("tasks"), list):
        return [], _diag(
            codec.ReasonCode.INVALID_JSON,
            stage=codec.Stage.DECODE,
            entity_id=manifest_rel,
            expected="valid task-origins.v1.json object with tasks array",
            actual={"path": origins_rel, "return_stage": "3C"},
            resume_ref=origins_rel,
        )
    norm_manifest = _norm_rel(manifest_rel)
    matched: list[int] = []
    for row in origins_doc.get("tasks") or []:
        if not isinstance(row, dict):
            return [], _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=manifest_rel,
                expected="object row in task-origins.v1.json",
                actual={"row_type": type(row).__name__, "return_stage": "3C"},
                resume_ref=origins_rel,
            )
        try:
            tid = ch6_gate.parse_strict_task_id(row.get("task_id"))
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            d["resume_ref"] = origins_rel
            return [], d
        row_origin = str(row.get("origin") or "").strip()
        if row_origin not in {"B", "A"}:
            return [], _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected="provable origin ('B' or 'A') in task-origins.v1.json",
                actual={"task_id": tid, "origin": row_origin, "return_stage": "3C"},
                resume_ref=origins_rel,
            )
        if row_origin == "A":
            continue
        brefs = row.get("binding_refs")
        if not isinstance(brefs, list) or not brefs:
            return [], _diag(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected="non-empty binding_refs for B-origin task",
                actual={"task_id": tid, "binding_refs": brefs, "return_stage": "5"},
                resume_ref=origins_rel,
            )
        for bref in brefs:
            if not isinstance(bref, dict) or not isinstance(bref.get("path"), str) or not bref["path"].strip():
                return [], _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=str(tid),
                    expected="valid typed binding_ref with path",
                    actual={"binding_ref": bref, "return_stage": "5"},
                    resume_ref=origins_rel,
                )
            brel = _norm_rel(bref["path"])
            try:
                bpath = inventory.safe_input(root_path, brel, allow_logs=False)
            except (codec.CodecError, ValueError, OSError) as exc:
                return [], _diag(
                    codec.ReasonCode.UNSAFE_PATH,
                    stage=codec.Stage.PATH,
                    entity_id=str(tid),
                    expected=brel,
                    actual={"error": str(exc), "return_stage": "5"},
                    resume_ref=brel,
                )
            if not bpath.is_file():
                return [], _diag(
                    codec.ReasonCode.FILE_NOT_FOUND,
                    stage=codec.Stage.PATH,
                    entity_id=str(tid),
                    expected=brel,
                    actual={"exists": False, "return_stage": "5"},
                    resume_ref=brel,
                )
            try:
                bdoc = codec.strict_json_loads(bpath.read_bytes())
            except codec.CodecError as err:
                d = err.diagnostic.to_dict()
                d["resume_ref"] = brel
                return [], d
            if not isinstance(bdoc, dict):
                return [], _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.DECODE,
                    entity_id=str(tid),
                    expected="binding JSON object",
                    actual={"path": brel, "return_stage": "5"},
                    resume_ref=brel,
                )
            if _json_contains_exact_path(bdoc, norm_manifest):
                matched.append(tid)

    if not matched:
        return [], _diag(
            codec.ReasonCode.MAPPING_MISMATCH,
            stage=codec.Stage.BUNDLE,
            entity_id=norm_manifest,
            expected="at least one B-origin Task Stage-5 binding referencing the selected MVG manifest",
            actual={"manifest_path": norm_manifest, "matched_tasks": [], "return_stage": "5"},
            resume_ref=origins_rel,
        )
    return sorted(set(matched)), None


def enforce_mvg_manifest_gate(
    root: Path | str,
    manifest_path: str,
    *,
    consumer: str = "project_health_http_mvg",
) -> dict[str, Any]:
    """Pre-effect B-route gate for POST /api/knowledge/mvg-run before latest.json or Godot launch."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))
    norm_manifest = _norm_rel(manifest_path)

    pending_pre = ch6_recovery._inspect_pending_and_post_edits(root_path, 0)
    if pending_pre.get("blocked"):
        pub_rc, blk, norm_stage, inv = _normalize_public_reason(
            ok=False,
            route="blocked",
            reason_code=pending_pre.get("reason_code"),
            return_stage=pending_pre.get("return_stage") or "3C",
        )
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "manifest_path": norm_manifest,
            "reason_code": pub_rc,
            "public_reason_code": pub_rc,
            "reason": str(pending_pre.get("reason") or "pending_journal"),
            "blocked_by": blk,
            "return_stage": norm_stage,
            "resume_ref": pending_pre.get("resume_ref"),
            "readiness_invalidated": inv,
            "gated_task_ids": [],
            "scope_ids": [],
            "diagnostics": list(pending_pre.get("diagnostics") or []),
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    presence = ch6_gate.detect_b_route_presence(root_path, None)
    has_b_markers = bool(
        presence.get("has_b_traces")
        or presence.get("capability_apply_pending")
        or presence.get("pending_journals")
        or presence.get("na_labels")
        or presence.get("has_lease_env")
    )
    if not has_b_markers:
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": True,
            "admitted": True,
            "legacy_a_passthrough": True,
            "route": "explicit_not_enabled_a",
            "manifest_path": norm_manifest,
            "reason_code": codec.ReasonCode.OK.value,
            "public_reason_code": codec.ReasonCode.OK.value,
            "reason": "explicit_not_enabled_a",
            "blocked_by": None,
            "return_stage": None,
            "gated_task_ids": [],
            "scope_ids": [],
            "diagnostics": [],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    try:
        if not norm_manifest:
            raise ValueError("empty manifest_path")
        mfile = inventory.safe_input(root_path, norm_manifest, allow_logs=False)
    except (codec.CodecError, OSError, ValueError) as exc:
        d = _diag(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=norm_manifest or "manifest",
            expected="repository-contained MVG manifest path",
            actual=str(exc),
            resume_ref=norm_manifest or None,
        )
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "manifest_path": norm_manifest,
            "reason_code": d["reason_code"],
            "public_reason_code": d["reason_code"],
            "reason": "unsafe_manifest_path",
            "blocked_by": "b_route_chapter6_gate",
            "return_stage": "5",
            "resume_ref": norm_manifest or None,
            "gated_task_ids": [],
            "scope_ids": [],
            "diagnostics": [d],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }
    if not mfile.is_file():
        d = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=norm_manifest,
            expected=norm_manifest,
            actual={"exists": False, "return_stage": "5"},
            resume_ref=norm_manifest,
        )
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "manifest_path": norm_manifest,
            "reason_code": d["reason_code"],
            "public_reason_code": d["reason_code"],
            "reason": "bound_mvg_manifest_missing",
            "blocked_by": "b_route_chapter6_gate",
            "return_stage": "5",
            "resume_ref": norm_manifest,
            "gated_task_ids": [],
            "scope_ids": [],
            "diagnostics": [d],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    tids, origin_diag = _collect_b_route_tasks_for_manifest(root_path, norm_manifest)
    if origin_diag is not None:
        rstage = ch6_gate._extract_return_stage_from_diag(origin_diag, default="3C")
        return {
            "schema_version": RUNTIME_GATE_SCHEMA,
            "ok": False,
            "admitted": False,
            "legacy_a_passthrough": False,
            "route": "blocked",
            "manifest_path": norm_manifest,
            "reason_code": origin_diag["reason_code"],
            "public_reason_code": origin_diag["reason_code"],
            "reason": "origins_or_manifest_binding_invalid",
            "blocked_by": "b_route_chapter6_gate",
            "return_stage": rstage,
            "resume_ref": origin_diag.get("resume_ref"),
            "gated_task_ids": [],
            "scope_ids": [],
            "diagnostics": [origin_diag],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    gate_check = enforce_runtime_task_gate(root_path, tids, mode="main", consumer=consumer)
    gate_check["manifest_path"] = norm_manifest
    return gate_check


def _inspect_live_fabrication_and_self_done_flags(
    root_path: Path,
    tid: int,
    gate_res: dict[str, Any] | None,
) -> dict[str, bool]:
    """Derive fabricated_manifest, fabricated_business_api, and self_done_required from live disk artifacts."""
    self_done_req = bool((gate_res or {}).get("self_done_required", False))
    fabricated_manifest = False
    fabricated_business_api = False

    if not isinstance(gate_res, dict) or gate_res.get("route") != "B":
        return {
            "self_done_required": self_done_req,
            "fabricated_manifest": False,
            "fabricated_business_api": False,
        }

    stage5 = gate_res.get("stage5_summary") if isinstance(gate_res.get("stage5_summary"), dict) else {}
    is_pure_nonflow = stage5.get("mode") == "non_flow" and not bool(stage5.get("has_flow_obligations"))

    for bref in gate_res.get("binding_refs") or []:
        if not isinstance(bref, dict) or not isinstance(bref.get("path"), str):
            continue
        try:
            bpath = inventory.safe_input(root_path, _norm_rel(bref["path"]), allow_logs=False)
        except (codec.CodecError, ValueError, OSError):
            continue
        bdoc = _safe_read_json(bpath)
        if not isinstance(bdoc, dict):
            continue
        if bdoc.get("fabricated_manifest") is True:
            fabricated_manifest = True
        if bdoc.get("fabricated_business_api") is True:
            fabricated_business_api = True
        mrefs = bdoc.get("manifest_refs")
        if is_pure_nonflow and isinstance(mrefs, list) and len(mrefs) > 0:
            fabricated_manifest = True
        for mref in mrefs or []:
            mrel = mref.get("path") if isinstance(mref, dict) else (mref if isinstance(mref, str) else None)
            if isinstance(mrel, str) and mrel.strip():
                try:
                    mp = inventory.safe_input(root_path, _norm_rel(mrel), allow_logs=False)
                    mdoc = _safe_read_json(mp)
                    if isinstance(mdoc, dict) and mdoc.get("fabricated") is True:
                        fabricated_manifest = True
                except (codec.CodecError, ValueError, OSError):
                    pass
        for crefs_key in ("contract_refs", "part_bindings"):
            for row in bdoc.get(crefs_key) or []:
                if isinstance(row, dict) and (
                    row.get("fabricated") is True or row.get("fabricated_business_api") is True
                ):
                    fabricated_business_api = True

    return {
        "self_done_required": self_done_req,
        "fabricated_manifest": fabricated_manifest,
        "fabricated_business_api": fabricated_business_api,
    }


def _entrypoint_record(
    entrypoint: str,
    *,
    route: str,
    admitted: bool,
    reason_code: str | None,
    blocked_by: str | None,
    return_stage: str | None,
    applicable_set_digest: str | None,
    input_set_digest: str | None,
    scope_ids: list[str] | tuple[str, ...],
    live_flags: dict[str, bool] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pub_rc, norm_blk, norm_stage, inv = _normalize_public_reason(
        ok=admitted,
        route=route,
        reason_code=reason_code,
        return_stage=return_stage,
        blocked_by=blocked_by,
    )
    flags = live_flags or {}
    row = {
        "entrypoint": entrypoint,
        "route": route,
        "admitted": bool(admitted),
        "public_reason_code": pub_rc,
        "blocked_by": norm_blk,
        "return_stage": norm_stage,
        "applicable_set_digest": applicable_set_digest,
        "input_set_digest": input_set_digest,
        "scope_ids": sorted(set(str(s) for s in (scope_ids or []) if str(s).strip())),
        "readiness_invalidated": inv,
        "flow_completed": False,
        "default_b_enabled": False,
        "self_done_required": bool(flags.get("self_done_required", False)),
        "fabricated_manifest": bool(flags.get("fabricated_manifest", False)),
        "fabricated_business_api": bool(flags.get("fabricated_business_api", False)),
        **INVARIANT_FLAGS,
    }
    if extra:
        row.update(extra)
    return row


def _eval_cli_entrypoint(root_path: Path, tid: int, *, operation: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke real check_b_route_chapter6_gate.main CLI entrypoint."""
    import check_b_route_chapter6_gate as gate_cli

    argv = ["--root", str(root_path), "--task-id", str(tid), "--enforce-eligibility"]
    if operation is not None:
        argv.extend(["--operation", operation])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = gate_cli.main(argv)
    raw_out = buf.getvalue().strip()
    cli_payload = json.loads(raw_out.splitlines()[-1]) if raw_out else {"ok": False, "route": "blocked"}
    admitted = (rc == 0) and bool(cli_payload.get("ok"))
    route = str(cli_payload.get("route") or "blocked")
    is_legacy = bool(cli_payload.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
    scopes = [] if is_legacy else list(cli_payload.get("scope_ids") or [])
    live_flags = _inspect_live_fabrication_and_self_done_flags(root_path, tid, cli_payload)
    row = _entrypoint_record(
        "cli",
        route=route,
        admitted=admitted,
        reason_code=codec.ReasonCode.OK.value if admitted else cli_payload.get("reason_code"),
        blocked_by=None if admitted else "b_route_chapter6_gate",
        return_stage=None if admitted else cli_payload.get("return_stage"),
        applicable_set_digest=None if is_legacy else cli_payload.get("applicable_set_digest"),
        input_set_digest=None if is_legacy else cli_payload.get("input_set_digest"),
        scope_ids=scopes,
        live_flags=live_flags,
        extra={"cli_exit_code": rc},
    )
    return row, cli_payload


def _eval_direct_entrypoint(root_path: Path, tid: int, *, operation: str | None) -> dict[str, Any]:
    """Invoke real direct underlying Chapter 6 consumers (lane + review pipeline + needs-fix-fast)."""
    lane_gate = ch6_gate.enforce_internal_script_gate(
        root_path,
        tid,
        consumer="run_single_task_chapter6_lane",
        operation=operation,
    )
    review_gate = ch6_gate.enforce_internal_script_gate(
        root_path,
        tid,
        consumer="sc-review-pipeline",
        operation=operation,
    )
    nf_gate = ch6_gate.enforce_internal_script_gate(
        root_path,
        tid,
        consumer="llm_review_needs_fix_fast",
        operation=operation,
    )
    direct_consumers = {
        "run_single_task_chapter6_lane": bool(lane_gate.get("ok")),
        "sc_review_pipeline": bool(review_gate.get("ok")),
        "llm_review_needs_fix_fast": bool(nf_gate.get("ok")),
    }
    admitted = all(direct_consumers.values())
    primary = lane_gate if not lane_gate.get("ok") else (review_gate if not review_gate.get("ok") else nf_gate)
    route = str(primary.get("route") or "blocked")
    is_legacy = bool(primary.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
    scopes = [] if is_legacy else list(primary.get("scope_ids") or [])
    live_flags = _inspect_live_fabrication_and_self_done_flags(root_path, tid, primary)
    return _entrypoint_record(
        "direct",
        route=route,
        admitted=admitted,
        reason_code=codec.ReasonCode.OK.value if admitted else primary.get("reason_code"),
        blocked_by=None if admitted else "b_route_chapter6_gate",
        return_stage=None if admitted else primary.get("return_stage"),
        applicable_set_digest=None if is_legacy else primary.get("applicable_set_digest"),
        input_set_digest=None if is_legacy else primary.get("input_set_digest"),
        scope_ids=scopes,
        live_flags=live_flags,
        extra={"direct_consumers": direct_consumers},
    )


def _eval_resume_entrypoint(
    root_path: Path,
    tid: int,
    *,
    operation: str | None,
) -> dict[str, Any]:
    """Evaluate real resume_task.build_resume_payload without ever copying cli_live."""
    import resume_task as resume_mod

    op_rec: dict[str, Any] | None = None
    if operation is not None:
        op_rec = ch6_recovery.evaluate_chapter6_recovery(
            root_path,
            tid,
            operation=operation,
            recommendation_only=True,
            consumer="resume_task",
            enforce_durable_stop_loss=False,
        )
        if not op_rec.get("ok"):
            is_leg = bool(op_rec.get("legacy_a_passthrough")) or op_rec.get("route") == "explicit_not_enabled_a"
            return _entrypoint_record(
                "resume",
                route=str(op_rec.get("route") or "blocked"),
                admitted=False,
                reason_code=op_rec.get("reason_code"),
                blocked_by="b_route_chapter6_gate",
                return_stage=op_rec.get("return_stage"),
                applicable_set_digest=None if is_leg else op_rec.get("applicable_set_digest"),
                input_set_digest=None if is_leg else op_rec.get("input_set_digest"),
                scope_ids=[] if is_leg else (op_rec.get("scope_ids") or []),
                live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, op_rec.get("gate_result")),
                extra={"resume_exit_code": 2, "prior_run_found": False},
            )

    try:
        rc, payload = resume_mod.build_resume_payload(
            repo_root=root_path,
            task_id=str(tid),
            latest="",
            run_id="",
            recommendation_only=True,
        )
        b_rec = payload.get("b_route_recovery") if isinstance(payload.get("b_route_recovery"), dict) else None
        if isinstance(b_rec, dict):
            admitted = bool(b_rec.get("ok")) and bool(payload.get("execution_allowed", True))
            route = str(b_rec.get("route") or "blocked")
            is_leg = bool(b_rec.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
            reason_code = (
                codec.ReasonCode.OK.value
                if admitted
                else str(payload.get("reason_code") or b_rec.get("reason_code") or codec.ReasonCode.CONFLICT.value)
            )
            return_stage = None if admitted else (payload.get("return_stage") or b_rec.get("return_stage"))
            blocked_by = None if admitted else str(payload.get("blocked_by") or "b_route_chapter6_gate")
            return _entrypoint_record(
                "resume",
                route=route,
                admitted=admitted,
                reason_code=reason_code,
                blocked_by=blocked_by,
                return_stage=return_stage,
                applicable_set_digest=None if is_leg else b_rec.get("applicable_set_digest"),
                input_set_digest=None if is_leg else b_rec.get("input_set_digest"),
                scope_ids=[] if is_leg else (b_rec.get("scope_ids") or []),
                live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, b_rec.get("gate_result")),
                extra={"resume_exit_code": rc, "prior_run_found": True},
            )
    except FileNotFoundError:
        pass

    rec_live = op_rec or ch6_recovery.evaluate_chapter6_recovery(
        root_path,
        tid,
        operation=operation or "resume",
        recommendation_only=True,
        consumer="resume_task",
        enforce_durable_stop_loss=False,
    )
    admitted = bool(rec_live.get("ok"))
    route = str(rec_live.get("route") or "blocked")
    is_leg = bool(rec_live.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
    return _entrypoint_record(
        "resume",
        route=route,
        admitted=admitted,
        reason_code=codec.ReasonCode.OK.value if admitted else rec_live.get("reason_code"),
        blocked_by=None if admitted else "b_route_chapter6_gate",
        return_stage=None if admitted else rec_live.get("return_stage"),
        applicable_set_digest=None if is_leg else rec_live.get("applicable_set_digest"),
        input_set_digest=None if is_leg else rec_live.get("input_set_digest"),
        scope_ids=[] if is_leg else (rec_live.get("scope_ids") or []),
        live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, rec_live.get("gate_result")),
        extra={"resume_exit_code": 0 if admitted else 2, "prior_run_found": False},
    )


def _eval_route_entrypoint(
    root_path: Path,
    tid: int,
    *,
    operation: str | None,
) -> dict[str, Any]:
    """Evaluate real chapter6_route.route_chapter6 honoring rc != 0 without ever copying cli_live."""
    import chapter6_route as route_mod

    op_rec: dict[str, Any] | None = None
    if operation is not None:
        op_rec = ch6_recovery.evaluate_chapter6_recovery(
            root_path,
            tid,
            operation=operation,
            recommendation_only=True,
            consumer="chapter6_route",
            enforce_durable_stop_loss=False,
        )
        if not op_rec.get("ok"):
            is_leg = bool(op_rec.get("legacy_a_passthrough")) or op_rec.get("route") == "explicit_not_enabled_a"
            return _entrypoint_record(
                "route",
                route=str(op_rec.get("route") or "blocked"),
                admitted=False,
                reason_code=op_rec.get("reason_code"),
                blocked_by="b_route_chapter6_gate",
                return_stage=op_rec.get("return_stage"),
                applicable_set_digest=None if is_leg else op_rec.get("applicable_set_digest"),
                input_set_digest=None if is_leg else op_rec.get("input_set_digest"),
                scope_ids=[] if is_leg else (op_rec.get("scope_ids") or []),
                live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, op_rec.get("gate_result")),
                extra={"route_exit_code": 3, "prior_run_found": False},
            )

    try:
        rc, payload = route_mod.route_chapter6(
            repo_root=root_path,
            task_id=str(tid),
            recommendation_only=True,
        )
        b_rec = payload.get("b_route_recovery") if isinstance(payload.get("b_route_recovery"), dict) else None
        if isinstance(b_rec, dict):
            admitted = (rc == 0) and bool(b_rec.get("ok")) and bool(payload.get("execution_allowed", True))
            route = str(b_rec.get("route") or "blocked")
            is_leg = bool(b_rec.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
            reason_code = (
                codec.ReasonCode.OK.value
                if admitted
                else str(payload.get("reason_code") or b_rec.get("reason_code") or codec.ReasonCode.CONFLICT.value)
            )
            return_stage = None if admitted else (payload.get("return_stage") or b_rec.get("return_stage"))
            blocked_by = None if admitted else str(payload.get("blocked_by") or "b_route_chapter6_gate")
            return _entrypoint_record(
                "route",
                route=route,
                admitted=admitted,
                reason_code=reason_code,
                blocked_by=blocked_by,
                return_stage=return_stage,
                applicable_set_digest=None if is_leg else b_rec.get("applicable_set_digest"),
                input_set_digest=None if is_leg else b_rec.get("input_set_digest"),
                scope_ids=[] if is_leg else (b_rec.get("scope_ids") or []),
                live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, b_rec.get("gate_result")),
                extra={"route_exit_code": rc, "prior_run_found": True},
            )
        if rc != 0 or not payload.get("execution_allowed", True):
            rec_fb = op_rec or ch6_recovery.evaluate_chapter6_recovery(
                root_path,
                tid,
                operation=operation or "route",
                recommendation_only=True,
                consumer="chapter6_route",
                enforce_durable_stop_loss=False,
            )
            if not rec_fb.get("legacy_a_passthrough") and not rec_fb.get("ok"):
                return _entrypoint_record(
                    "route",
                    route=str(rec_fb.get("route") or "blocked"),
                    admitted=False,
                    reason_code=rec_fb.get("reason_code"),
                    blocked_by="b_route_chapter6_gate",
                    return_stage=rec_fb.get("return_stage"),
                    applicable_set_digest=rec_fb.get("applicable_set_digest"),
                    input_set_digest=rec_fb.get("input_set_digest"),
                    scope_ids=rec_fb.get("scope_ids") or [],
                    live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, rec_fb.get("gate_result")),
                    extra={"route_exit_code": rc, "prior_run_found": False},
                )
            if rec_fb.get("legacy_a_passthrough") and str(payload.get("blocked_by") or "") == "chapter5_readiness":
                # Pure explicit_not_enabled_a repo without legacy Chapter 5 readiness artifact:
                # evaluate B-route gate parity consistently as explicit_not_enabled_a passthrough.
                return _entrypoint_record(
                    "route",
                    route="explicit_not_enabled_a",
                    admitted=True,
                    reason_code=codec.ReasonCode.OK.value,
                    blocked_by=None,
                    return_stage=None,
                    applicable_set_digest=None,
                    input_set_digest=None,
                    scope_ids=[],
                    live_flags={"self_done_required": False, "fabricated_manifest": False, "fabricated_business_api": False},
                    extra={"route_exit_code": rc, "prior_run_found": False},
                )
            return _entrypoint_record(
                "route",
                route="blocked",
                admitted=False,
                reason_code=str(payload.get("reason_code") or codec.ReasonCode.CONFLICT.value),
                blocked_by=str(payload.get("blocked_by") or "b_route_chapter6_gate"),
                return_stage=str(payload.get("return_stage") or "5"),
                applicable_set_digest=None,
                input_set_digest=None,
                scope_ids=[],
                extra={"route_exit_code": rc, "prior_run_found": True},
            )
    except FileNotFoundError:
        pass

    rec_live = op_rec or ch6_recovery.evaluate_chapter6_recovery(
        root_path,
        tid,
        operation=operation or "route",
        recommendation_only=True,
        consumer="chapter6_route",
        enforce_durable_stop_loss=False,
    )
    admitted = bool(rec_live.get("ok"))
    route = str(rec_live.get("route") or "blocked")
    is_leg = bool(rec_live.get("legacy_a_passthrough")) or route == "explicit_not_enabled_a"
    return _entrypoint_record(
        "route",
        route=route,
        admitted=admitted,
        reason_code=codec.ReasonCode.OK.value if admitted else rec_live.get("reason_code"),
        blocked_by=None if admitted else "b_route_chapter6_gate",
        return_stage=None if admitted else rec_live.get("return_stage"),
        applicable_set_digest=None if is_leg else rec_live.get("applicable_set_digest"),
        input_set_digest=None if is_leg else rec_live.get("input_set_digest"),
        scope_ids=[] if is_leg else (rec_live.get("scope_ids") or []),
        live_flags=_inspect_live_fabrication_and_self_done_flags(root_path, tid, rec_live.get("gate_result")),
        extra={"route_exit_code": 0 if admitted else 3, "prior_run_found": False},
    )


def evaluate_entrypoint_parity(
    root: Path | str,
    *,
    task_id: Any,
    operation: str | None = None,
) -> dict[str, Any]:
    """Evaluate normalized decision and pre-effect rejection parity across all 5 real entrypoints."""
    started = time.monotonic()
    validated_tid: int | None = None
    validated_op: str | None = None
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = ch6_gate.parse_strict_task_id(task_id)
        validated_op = task_resolver._validate_operation(operation)
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None and validated_tid is not None:
            d["entity_id"] = str(validated_tid)
        return {
            "schema_version": SCHEMA,
            "ok": False,
            "parity_ok": False,
            "task_id": validated_tid,
            "operation": validated_op,
            "route": "blocked",
            "admitted": False,
            "public_reason_code": d["reason_code"],
            "reason_code": d["reason_code"],
            "blocked_by": "b_route_chapter6_gate",
            "return_stage": "5",
            "applicable_set_digest": None,
            "input_set_digest": None,
            "scope_ids": [],
            "readiness_invalidated": True,
            "entrypoints": {},
            "mismatches": [],
            "flow_completed": False,
            "self_done_required": False,
            "report_path": None,
            "diagnostics": [d],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **INVARIANT_FLAGS,
        }

    before_pointers = _snapshot_publication_pointers(root_path)

    # 1. CLI entrypoint (real check_b_route_chapter6_gate.main)
    cli_row, cli_payload = _eval_cli_entrypoint(root_path, validated_tid, operation=validated_op)

    # 2. Direct underlying entrypoint (real enforce_internal_script_gate across lane + sc consumers)
    direct_row = _eval_direct_entrypoint(root_path, validated_tid, operation=validated_op)

    # 3. Resume entrypoint (real resume_task.build_resume_payload)
    resume_row = _eval_resume_entrypoint(root_path, validated_tid, operation=validated_op)

    # 4. Route entrypoint (real chapter6_route.route_chapter6)
    route_row = _eval_route_entrypoint(root_path, validated_tid, operation=validated_op)

    # 5. Page entrypoint (real handle_page_b_route_trigger in preview/read-only gate mode)
    page_res = handle_page_b_route_trigger(
        root_path,
        {
            "action": "gate",
            "task_id": validated_tid,
            "mode": "main",
            "preview": True,
            "operation": validated_op,
        },
    )
    page_flags = _inspect_live_fabrication_and_self_done_flags(
        root_path,
        validated_tid,
        page_res.get("gate_result"),
    )
    page_row = _entrypoint_record(
        "page",
        route=str(page_res.get("route") or "blocked"),
        admitted=bool(page_res.get("admitted")),
        reason_code=page_res.get("public_reason_code"),
        blocked_by=page_res.get("blocked_by"),
        return_stage=page_res.get("return_stage"),
        applicable_set_digest=page_res.get("applicable_set_digest"),
        input_set_digest=page_res.get("input_set_digest"),
        scope_ids=page_res.get("scope_ids") or [],
        live_flags=page_flags,
        extra={
            "page_trigger_admitted": bool(page_res.get("admitted")),
            "publication_pointers_preserved": bool(page_res.get("publication_pointers_preserved")),
        },
    )

    entrypoints = {
        "cli": cli_row,
        "direct": direct_row,
        "resume": resume_row,
        "route": route_row,
        "page": page_row,
    }

    parity_fields = (
        "route",
        "admitted",
        "public_reason_code",
        "blocked_by",
        "return_stage",
        "applicable_set_digest",
        "input_set_digest",
        "scope_ids",
        "flow_completed",
        "default_b_enabled",
        "self_done_required",
        "fabricated_manifest",
        "fabricated_business_api",
    )
    mismatches: list[dict[str, Any]] = []
    for field in parity_fields:
        expected_val = cli_row[field]
        for ep_name in ("direct", "resume", "route", "page"):
            actual_val = entrypoints[ep_name][field]
            if actual_val != expected_val:
                mismatches.append(
                    {
                        "field": field,
                        "reference_entrypoint": "cli",
                        "expected": expected_val,
                        "entrypoint": ep_name,
                        "actual": actual_val,
                    }
                )

    pointers_ok, mutated_pointers, _after = _diff_publication_pointers(root_path, before_pointers)
    diags: list[dict[str, Any]] = list(cli_payload.get("diagnostics") or [])
    if mismatches:
        diags.append(
            _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected="identical normalized decision across cli/direct/resume/route/page",
                actual={"mismatches": mismatches},
                resume_ref="docs/workflows/b-route-entrypoint-parity.md",
            )
        )
    if not pointers_ok:
        diags.append(
            _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=str(validated_tid),
                expected="zero publication pointer mutation during parity inspection",
                actual={"mutated_pointers": mutated_pointers},
                resume_ref="docs/workflows/project-health-knowledge.md",
            )
        )

    parity_ok = len(mismatches) == 0 and pointers_ok
    return {
        "schema_version": SCHEMA,
        "ok": parity_ok,
        "parity_ok": parity_ok,
        "task_id": validated_tid,
        "operation": validated_op,
        "route": cli_row["route"],
        "admitted": cli_row["admitted"],
        "public_reason_code": cli_row["public_reason_code"],
        "reason_code": cli_row["public_reason_code"],
        "blocked_by": cli_row["blocked_by"],
        "return_stage": cli_row["return_stage"],
        "applicable_set_digest": cli_row["applicable_set_digest"],
        "input_set_digest": cli_row["input_set_digest"],
        "scope_ids": cli_row["scope_ids"],
        "readiness_invalidated": cli_row["readiness_invalidated"],
        "entrypoints": entrypoints,
        "mismatches": mismatches,
        "publication_pointers_preserved": pointers_ok,
        "flow_completed": False,
        "self_done_required": cli_row["self_done_required"],
        "report_path": None,
        "diagnostics": diags,
        "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
        **INVARIANT_FLAGS,
    }


def _find_operation_journal(root_path: Path, operation_id: str) -> dict[str, Any]:
    """Locate hashed B-route operations, top-level legacy apply journals, CAP_PENDING, or explicit journals."""
    op_id_clean = str(operation_id or "").strip()
    if not op_id_clean:
        return {"path": None, "doc": None, "kind": None, "extra_targets": []}

    # 1. Hashed B-route operation store: logs/ci/b-route-operations/operations/<sha256>/
    try:
        hashed_op_rel = journal._operation_ref(op_id_clean)
        hashed_dir_rel = hashed_op_rel.rsplit("/", 1)[0]
        for primary_rel, kind in (
            (hashed_op_rel, "hashed_b_route_op"),
            (f"{hashed_dir_rel}/public-sync-journal.json", "hashed_public_sync"),
            (f"{hashed_dir_rel}/commit.json", "hashed_commit_intent"),
        ):
            p = inventory.safe_input(root_path, primary_rel, allow_logs=True)
            if p.is_file():
                doc = _safe_read_json(p)
                commit_doc = _safe_read_json(root_path / f"{hashed_dir_rel}/commit.json")
                pub_sync_doc = _safe_read_json(root_path / f"{hashed_dir_rel}/public-sync-journal.json")
                commit_pending_exists = (root_path / f"{hashed_dir_rel}/commit.pending.json").exists()
                pub_pending_exists = (root_path / f"{hashed_dir_rel}/public-sync.pending.json").exists()
                receipt_exists = (root_path / f"docs/planning/b-route/commits/{op_id_clean}.json").is_file()
                extra_targets: list[dict[str, Any]] = []
                for aux in (doc, commit_doc, pub_sync_doc):
                    if isinstance(aux, dict):
                        frozen = aux.get("frozen") if isinstance(aux.get("frozen"), dict) else {}
                        if isinstance(frozen.get("targets"), list):
                            extra_targets.extend(r for r in frozen["targets"] if isinstance(r, dict))
                        for k in ("targets", "writes", "files", "entries"):
                            if isinstance(aux.get(k), list):
                                extra_targets.extend(r for r in aux[k] if isinstance(r, dict))
                derived_state = ""
                if commit_pending_exists or pub_pending_exists:
                    derived_state = "in_progress"
                elif isinstance(commit_doc, dict) and commit_doc.get("phase") == "complete":
                    derived_state = "completed"
                elif receipt_exists:
                    derived_state = "completed"
                elif isinstance(commit_doc, dict) and commit_doc.get("phase"):
                    derived_state = str(commit_doc["phase"]).strip().lower()
                elif isinstance(doc, dict):
                    derived_state = str(doc.get("state") or doc.get("status") or "").strip().lower()
                if not derived_state:
                    derived_state = "prepared"
                return {
                    "path": p,
                    "doc": doc,
                    "kind": kind,
                    "derived_state": derived_state,
                    "commit_doc": commit_doc,
                    "extra_targets": extra_targets,
                }
    except (codec.CodecError, ValueError, OSError):
        pass

    # 2. CAP_PENDING marker (docs/planning/semantic-topology/capability-apply.pending.json)
    try:
        cap_p = inventory.safe_input(root_path, op_scope.CAP_PENDING, allow_logs=False)
        if cap_p.is_file():
            cap_doc = _safe_read_json(cap_p)
            if op_id_clean == "capability-apply.pending" or (
                isinstance(cap_doc, dict) and str(cap_doc.get("run_id") or "") == op_id_clean
            ):
                j_rel = cap_doc.get("journal_path") if isinstance(cap_doc, dict) else None
                if isinstance(j_rel, str) and j_rel.strip():
                    jp = inventory.safe_input(root_path, _norm_rel(j_rel), allow_logs=True)
                    if jp.is_file():
                        jdoc = _safe_read_json(jp)
                        return {
                            "path": jp,
                            "doc": jdoc,
                            "kind": "legacy_planning_journal",
                            "derived_state": "pending",
                            "extra_targets": list((jdoc or {}).get("entries") or []),
                        }
                return {
                    "path": cap_p,
                    "doc": cap_doc,
                    "kind": "cap_pending_marker",
                    "derived_state": "pending",
                    "extra_targets": [],
                }
    except (codec.CodecError, ValueError, OSError):
        pass

    # 3. Top-level legacy planning journals & explicit B-route journals (NEVER recursive rglob on planning dirs!).
    candidates = [
        (f"logs/ci/capability-planning/{op_id_clean}/apply-journal.json", "legacy_planning_journal"),
        (f"logs/ci/mvg-planning/{op_id_clean}/apply-journal.json", "legacy_planning_journal"),
        (f"logs/ci/b-route-operations/{op_id_clean}/apply-journal.json", "explicit_journal"),
        (f"logs/ci/b-route-operations/{op_id_clean}/public-sync-journal.json", "explicit_journal"),
        (f"logs/ci/b-route-operations/{op_id_clean}/operation.json", "explicit_journal"),
        (f"logs/ci/b-route-chapter4-binding/{op_id_clean}/public-sync-journal.json", "explicit_journal"),
        (f"logs/ci/b-route-stage5-obligations/{op_id_clean}/public-sync-journal.json", "explicit_journal"),
    ]
    for rel, kind in candidates:
        try:
            path = inventory.safe_input(root_path, rel, allow_logs=True)
        except (codec.CodecError, ValueError, OSError):
            continue
        if path.is_file():
            doc = _safe_read_json(path)
            st = str((doc or {}).get("state") or (doc or {}).get("status") or "").strip().lower()
            extra: list[dict[str, Any]] = []
            if isinstance(doc, dict):
                frozen = doc.get("frozen") if isinstance(doc.get("frozen"), dict) else {}
                if isinstance(frozen.get("targets"), list):
                    extra.extend(r for r in frozen["targets"] if isinstance(r, dict))
                for k in ("targets", "writes", "files", "entries"):
                    if isinstance(doc.get(k), list):
                        extra.extend(r for r in doc[k] if isinstance(r, dict))
            return {"path": path, "doc": doc, "kind": kind, "derived_state": st, "extra_targets": extra}

    return {"path": None, "doc": None, "kind": None, "extra_targets": []}


def verify_completed_apply_status_preservation(
    root: Path | str,
    *,
    operation_id: str,
    task_id: Any,
) -> dict[str, Any]:
    """Verify completed 3C/Stage-4/Stage-5 journal replay is a terminal no-op preserving newer live Task status."""
    root_path = task_resolver._validate_root(Path(root))
    tid = ch6_gate.parse_strict_task_id(task_id)
    found = _find_operation_journal(root_path, operation_id)
    jpath: Path | None = found["path"]
    jdoc: dict[str, Any] | None = found["doc"]
    if jpath is None or jdoc is None:
        d = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=operation_id,
            expected="readable completed operation/apply-journal.json/public-sync-journal.json",
            actual={"found": jpath is not None},
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "noop": False,
            "preserves_live_status": False,
            "overwrites_status": False,
            "operation_id": operation_id,
            "task_id": tid,
            "reason_code": d["reason_code"],
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    jrel = jpath.relative_to(root_path).as_posix()
    state = str(found.get("derived_state") or jdoc.get("state") or jdoc.get("status") or "").strip().lower()
    if state not in _COMPLETED_JOURNAL_STATES:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=operation_id,
            expected=sorted(_COMPLETED_JOURNAL_STATES),
            actual=state,
            resume_ref=jrel,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "noop": False,
            "preserves_live_status": False,
            "overwrites_status": False,
            "operation_id": operation_id,
            "task_id": tid,
            "journal_state": state,
            "reason_code": d["reason_code"],
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    master_rel = task_resolver.TRIPLET["master"]
    master_path = inventory.safe_input(root_path, master_rel, allow_logs=False)
    master_before_raw = master_path.read_bytes()
    master_doc = _safe_read_json(master_path) or {}
    live_status = None
    for row in ((master_doc.get("master") or {}).get("tasks") or []):
        if isinstance(row, dict) and str(row.get("id")) == str(tid):
            live_status = str(row.get("status") or "").strip().lower()
            break

    replay_mode = "verified_completed_journal_noop"
    replay_noop = True
    try:
        if found["kind"] == "hashed_b_route_op" and isinstance(found.get("commit_doc"), dict):
            rec_out = b_commit.recover(root_path, operation_id=operation_id)
            replay_mode = "b_route_commit.recover"
            replay_noop = bool(rec_out.get("noop")) and bool(rec_out.get("published"))
        elif found["kind"] == "legacy_planning_journal" and jdoc.get("schema_version") == "newrouge.planning-apply-journal.v1":
            journal.resume_journal(
                root_path,
                jpath,
                lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("completed journal must not invoke writer")),
            )
            replay_mode = "planning_apply_journal.resume_journal"
            replay_noop = True
    except (codec.CodecError, ValueError, OSError) as exc:
        d = (
            exc.diagnostic.to_dict()
            if isinstance(exc, codec.CodecError)
            else _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=operation_id,
                expected="terminal no-op replay on completed journal",
                actual=str(exc),
                resume_ref=jrel,
            )
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "noop": False,
            "preserves_live_status": False,
            "overwrites_status": False,
            "operation_id": operation_id,
            "task_id": tid,
            "journal_path": jrel,
            "journal_state": state,
            "replay_mode": replay_mode,
            "reason_code": d["reason_code"],
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    master_after_raw = master_path.read_bytes()
    after_doc = _safe_read_json(master_path) or {}
    after_status = None
    for row in ((after_doc.get("master") or {}).get("tasks") or []):
        if isinstance(row, dict) and str(row.get("id")) == str(tid):
            after_status = str(row.get("status") or "").strip().lower()
            break
    unchanged = (master_before_raw == master_after_raw) and (after_status == live_status) and (live_status is not None)
    ok = replay_noop and unchanged
    return {
        "schema_version": WIN_CONCURRENCY_SCHEMA,
        "ok": ok,
        "noop": replay_noop,
        "preserves_live_status": unchanged,
        "overwrites_status": after_status != live_status,
        "operation_id": operation_id,
        "task_id": tid,
        "journal_path": jrel,
        "journal_state": state,
        "replay_mode": replay_mode,
        "live_status": after_status,
        "reason_code": codec.ReasonCode.OK.value if ok else codec.ReasonCode.CONFLICT.value,
        "diagnostics": [],
        **INVARIANT_FLAGS,
    }


def verify_incomplete_apply_raw_preimage_guard(
    root: Path | str,
    *,
    operation_id: str,
) -> dict[str, Any]:
    """Verify interrupted/in_progress journal checks exact raw preimage digest and halts with CONFLICT on drift."""
    root_path = task_resolver._validate_root(Path(root))
    found = _find_operation_journal(root_path, operation_id)
    jpath: Path | None = found["path"]
    jdoc: dict[str, Any] | None = found["doc"]
    if jpath is None:
        d = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=operation_id,
            expected="incomplete journal or operation path",
            actual=None,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "conflict_detected": False,
            "mutated": False,
            "post_edit_preserved": True,
            "operation_id": operation_id,
            "reason_code": d["reason_code"],
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }
    jrel = jpath.relative_to(root_path).as_posix()
    if jdoc is None:
        d = _diag(
            codec.ReasonCode.INVALID_JSON,
            stage=codec.Stage.DECODE,
            entity_id=operation_id,
            expected="valid JSON journal",
            actual={"corrupt_journal": jrel},
            resume_ref=jrel,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "conflict_detected": True,
            "mutated": False,
            "post_edit_preserved": True,
            "operation_id": operation_id,
            "journal_path": jrel,
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    state = str(found.get("derived_state") or jdoc.get("state") or jdoc.get("status") or "").strip().lower()
    if state not in _INCOMPLETE_JOURNAL_STATES:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=operation_id,
            expected=sorted(_INCOMPLETE_JOURNAL_STATES),
            actual={"journal_state": state},
            resume_ref=jrel,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "conflict_detected": False,
            "mutated": False,
            "post_edit_preserved": True,
            "operation_id": operation_id,
            "journal_path": jrel,
            "journal_state": state,
            "conflicts": [],
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    targets: list[dict[str, Any]] = list(found.get("extra_targets") or [])
    conflicts: list[dict[str, Any]] = []
    before_bytes_map: dict[str, bytes | None] = {}
    seen_target_keys: set[tuple[str, str | None, str | None]] = set()

    for tgt in targets:
        if not isinstance(tgt, dict):
            continue
        rel = _norm_rel(str(tgt.get("path") or tgt.get("target_path") or ""))
        if not rel:
            continue
        expected_pre = _normalize_prefixed_digest(
            tgt.get("before_raw_digest")
            or tgt.get("before_digest")
            or tgt.get("before_sha256")
            or tgt.get("preimage_digest")
            or tgt.get("pre_image_sha256")
        )
        expected_post = _normalize_prefixed_digest(
            tgt.get("after_raw_digest")
            or tgt.get("after_digest")
            or tgt.get("after_sha256")
            or tgt.get("postimage_digest")
            or tgt.get("post_image_sha256")
        )
        dedup_k = (rel, expected_pre, expected_post)
        if dedup_k in seen_target_keys:
            continue
        seen_target_keys.add(dedup_k)

        try:
            tfile = inventory.safe_input(root_path, rel, allow_logs=True)
        except (codec.CodecError, ValueError, OSError) as exc:
            conflicts.append({"path": rel, "error": str(exc)})
            continue
        raw_now = tfile.read_bytes() if tfile.is_file() else None
        before_bytes_map[rel] = raw_now
        live_digest = codec.raw_digest(raw_now) if raw_now is not None else None

        has_pre_key = any(
            k in tgt
            for k in (
                "before_raw_digest",
                "before_digest",
                "before_sha256",
                "preimage_digest",
                "pre_image_sha256",
                "before_exists",
            )
        )
        if expected_pre is not None:
            if live_digest != expected_pre and (expected_post is None or live_digest != expected_post):
                conflicts.append(
                    {
                        "path": rel,
                        "expected_preimage": expected_pre,
                        "expected_postimage": expected_post,
                        "actual_digest": live_digest,
                    }
                )
        elif has_pre_key and live_digest is not None:
            # Newly-created target file: preimage was None (did not exist before operation).
            if expected_post is None or live_digest != expected_post:
                conflicts.append(
                    {
                        "path": rel,
                        "expected_preimage": None,
                        "expected_postimage": expected_post,
                        "actual_digest": live_digest,
                    }
                )

    mutated = any(
        ((root_path / rel).read_bytes() if (root_path / rel).is_file() else None) != prev_raw
        for rel, prev_raw in before_bytes_map.items()
    )

    if conflicts:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=operation_id,
            expected="raw preimage digest match before resuming incomplete apply",
            actual={"journal_state": state, "conflicts": conflicts},
            resume_ref=jrel,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "conflict_detected": True,
            "mutated": mutated,
            "post_edit_preserved": not mutated,
            "operation_id": operation_id,
            "journal_path": jrel,
            "journal_state": state,
            "conflicts": conflicts,
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    return {
        "schema_version": WIN_CONCURRENCY_SCHEMA,
        "ok": True,
        "conflict_detected": False,
        "mutated": mutated,
        "post_edit_preserved": not mutated,
        "operation_id": operation_id,
        "journal_path": jrel,
        "journal_state": state,
        "conflicts": [],
        "reason_code": codec.ReasonCode.OK.value,
        "diagnostics": [],
        **INVARIANT_FLAGS,
    }


def verify_projection_vs_irrelevant_change(
    root: Path | str,
    *,
    task_id: Any,
    baseline_input_set: dict[str, Any],
) -> dict[str, Any]:
    """Compare baseline InputSet against live InputSet to separate projection drift from irrelevant changes."""
    root_path = task_resolver._validate_root(Path(root))
    tid = ch6_gate.parse_strict_task_id(task_id)
    live = input_set.resolve_input_set(root_path, tid, baseline=baseline_input_set)
    freshness = live.get("freshness") if isinstance(live.get("freshness"), dict) else {}
    invalidated_items = [it for it in (freshness.get("invalidated_items") or []) if isinstance(it, dict)]
    if freshness.get("compared"):
        same = bool(freshness.get("fresh"))
    else:
        same = bool(live.get("ok")) and (
            live.get("input_set_digest") == baseline_input_set.get("input_set_digest")
        )
    projection_categories = {"task_definition", "task_projection", "dependency_task", "flow_peer_task"}
    projection_changed = (not same) and any(
        str(it.get("category") or "") in projection_categories for it in invalidated_items
    )
    if not same and not projection_changed:
        base_proj_map = {
            (str(it.get("category") or ""), str(it.get("locator") or "")): it.get("normalized_digest")
            for it in (baseline_input_set.get("items") or [])
            if isinstance(it, dict) and str(it.get("category") or "") in projection_categories
        }
        live_proj_map = {
            (str(it.get("category") or ""), str(it.get("locator") or "")): it.get("normalized_digest")
            for it in (live.get("items") or [])
            if isinstance(it, dict) and str(it.get("category") or "") in projection_categories
        }
        if base_proj_map != live_proj_map:
            projection_changed = True
    changed_reasons = [
        f"{it.get('category')}:{it.get('locator')}:{it.get('change_kind')}"
        for it in invalidated_items
    ]
    rstage = freshness.get("return_stage") if not same else None
    if not same and rstage is None:
        rstage = "3C" if projection_changed else (live.get("return_stage") or "5")
    return {
        "schema_version": WIN_CONCURRENCY_SCHEMA,
        "ok": bool(live.get("ok")),
        "task_id": tid,
        "input_set_reusable": same,
        "projection_changed": projection_changed,
        "baseline_input_set_digest": baseline_input_set.get("input_set_digest"),
        "live_input_set_digest": live.get("input_set_digest"),
        "return_stage": rstage,
        "changed_components": changed_reasons,
        "reason_code": codec.ReasonCode.OK.value if same else codec.ReasonCode.INPUT_STALE.value,
        "diagnostics": list(live.get("diagnostics") or []),
        **INVARIANT_FLAGS,
    }


def _artifact_matches_task_or_scopes(
    doc: dict[str, Any],
    *,
    scope_set: set[str],
    plan_set: set[str],
    task_id: int,
) -> bool:
    """Structured scope_ids / plan_id / task_id matching (never substring str(task_id) in JSON blob)."""
    doc_tids = ch6_recovery._extract_doc_task_ids(doc)
    doc_scopes: set[str] = set()
    doc_plans: set[str] = set()
    for src in (doc, doc.get("frozen") if isinstance(doc.get("frozen"), dict) else None):
        if not isinstance(src, dict):
            continue
        for k in ("scope_ids", "scopes"):
            vals = src.get(k)
            if isinstance(vals, list):
                doc_scopes.update(str(v).strip() for v in vals if isinstance(v, str) and str(v).strip())
        pid = src.get("plan_id")
        if isinstance(pid, str) and pid.strip():
            doc_plans.add(pid.strip())
            doc_scopes.update(op_scope.resource_scopes(plan_ids=[pid.strip()]))
        pids = src.get("plan_ids")
        if isinstance(pids, list):
            for p in pids:
                if isinstance(p, str) and p.strip():
                    doc_plans.add(p.strip())
                    doc_scopes.update(op_scope.resource_scopes(plan_ids=[p.strip()]))
        prefs = src.get("plan_refs")
        if isinstance(prefs, list):
            for pref in prefs:
                if isinstance(pref, dict) and isinstance(pref.get("entity_id"), str) and pref["entity_id"].strip():
                    ep = pref["entity_id"].strip()
                    doc_plans.add(ep)
                    doc_scopes.update(op_scope.resource_scopes(plan_ids=[ep]))
    for dtid in doc_tids:
        doc_scopes.update(op_scope.resource_scopes(task_ids=[dtid]))

    if task_id in doc_tids:
        return True
    if doc_plans and (doc_plans & plan_set):
        return True
    if doc_scopes and (doc_scopes & scope_set):
        return True
    # Conservative only when the artifact declares zero structured task/plan/scope metadata at all.
    if not doc_tids and not doc_plans and not doc_scopes:
        return True
    return False


def _scan_unresolved_relevant_pending_artifacts(
    root_path: Path,
    *,
    scope_ids: list[str],
    plan_ids: list[str],
    task_id: int,
) -> list[dict[str, Any]]:
    """Detect unresolved pending/in_progress journals or candidates even if ephemeral marker files are deleted."""
    unresolved: list[dict[str, Any]] = []
    scope_set = {str(s).strip() for s in scope_ids if str(s).strip()} | set(op_scope.resource_scopes(task_ids=[task_id]))
    plan_set = {str(p).strip() for p in plan_ids if str(p).strip()}

    # 1. CAP_PENDING & top-level legacy apply-journal.json routes (NEVER recursive rglob on planning dirs!).
    try:
        for lroute in op_scope.legacy_recovery_routes(root_path):
            jrel = str(lroute.get("journal_path") or lroute.get("resume_ref") or op_scope.CAP_PENDING)
            unresolved.append({"kind": "legacy_pending_journal", "path": jrel, "state": "pending"})
    except (codec.CodecError, OSError, ValueError):
        unresolved.append({"kind": "corrupt_legacy_pending", "path": op_scope.CAP_PENDING, "state": "corrupt"})

    # 2. Hashed B-route operation store (operations/<sha256>/*)
    ops_dir = root_path / op_scope.STORE / "operations"
    if ops_dir.is_dir():
        try:
            graph = journal.operation_state_graph(root_path)
            terminals = graph.get("terminals") or {}
            resolved_by = graph.get("resolved_by") or {}
            for op in graph.get("operations") or []:
                op_id = op.get("operation_id")
                if op_id in terminals or op_id in resolved_by:
                    continue
                if _artifact_matches_task_or_scopes(op, scope_set=scope_set, plan_set=plan_set, task_id=task_id):
                    unresolved.append(
                        {
                            "kind": "hashed_pending_operation",
                            "path": journal._operation_ref(op_id),
                            "state": "pending",
                        }
                    )
        except (codec.CodecError, OSError, ValueError):
            unresolved.append({"kind": "corrupt_operation_store", "path": op_scope.STORE, "state": "corrupt"})

    # 3. Explicit top-level B-route journals (*/*.json excluding operations/ and locks/)
    for rel_dir in (
        "logs/ci/b-route-operations",
        "logs/ci/b-route-chapter4-binding",
        "logs/ci/b-route-stage5-obligations",
    ):
        base = root_path / rel_dir
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir() or sub.name in {"operations", "locks"}:
                continue
            for fname in ("apply-journal.json", "public-sync-journal.json", "operation.json"):
                jfile = sub / fname
                if not jfile.exists():
                    continue
                jdoc = _safe_read_json(jfile)
                rel = jfile.relative_to(root_path).as_posix()
                if jdoc is None:
                    unresolved.append({"kind": "corrupt_journal", "path": rel, "state": "corrupt"})
                    continue
                state = str(jdoc.get("state") or jdoc.get("status") or "").strip().lower()
                if state in _INCOMPLETE_JOURNAL_STATES:
                    if _artifact_matches_task_or_scopes(jdoc, scope_set=scope_set, plan_set=plan_set, task_id=task_id):
                        unresolved.append({"kind": "incomplete_journal", "path": rel, "state": state})

    # 4. Scan docs/planning/b-route/candidates for unapplied pending candidates matching relevant plans/scopes
    cand_dir = root_path / "docs/planning/b-route/candidates"
    if cand_dir.is_dir():
        for cfile in sorted(cand_dir.rglob("*.json")):
            cdoc = _safe_read_json(cfile)
            rel = cfile.relative_to(root_path).as_posix()
            if cdoc is None:
                unresolved.append({"kind": "corrupt_candidate", "path": rel, "state": "corrupt"})
                continue
            cstate = str(cdoc.get("status") or cdoc.get("state") or "pending").strip().lower()
            if cstate not in _COMPLETED_JOURNAL_STATES and cstate not in {"superseded", "rejected", "retired"}:
                if _artifact_matches_task_or_scopes(cdoc, scope_set=scope_set, plan_set=plan_set, task_id=task_id):
                    unresolved.append({"kind": "unresolved_candidate", "path": rel, "state": cstate})

    return unresolved


def verify_shared_task_union_scope_and_pending_guard(
    root: Path | str,
    *,
    task_id: Any,
    operation: str | None = None,
) -> dict[str, Any]:
    """Read-only zero-write verifier that shared Task covers union scope_ids and blocks on unresolved pending/contention."""
    root_path = task_resolver._validate_root(Path(root))
    tid = ch6_gate.parse_strict_task_id(task_id)
    cand_scopes = ch6_recovery._resolve_candidate_task_scopes(root_path, tid, operation) or set(
        op_scope.resource_scopes(task_ids=[tid])
    )
    origins_doc = _safe_read_json(root_path / task_resolver.ORIGINS_PATH)
    fast_plan_ids: list[str] = []
    if isinstance(origins_doc, dict) and isinstance(origins_doc.get("tasks"), list):
        for row in origins_doc["tasks"]:
            if isinstance(row, dict) and str(row.get("task_id")) == str(tid):
                for pref in row.get("plan_refs") or []:
                    if isinstance(pref, dict) and pref.get("entity_id"):
                        fast_plan_ids.append(str(pref["entity_id"]))
    fast_plan_ids = sorted(set(fast_plan_ids))
    catalog_scope_ids: list[str] = []
    cat_doc = _safe_read_json(root_path / records.CATALOG_PATH)
    if isinstance(cat_doc, dict) and fast_plan_ids:
        for sh in cat_doc.get("scope_heads") or []:
            if not isinstance(sh, dict):
                continue
            sh_plans = {
                str(pr.get("entity_id"))
                for pr in (sh.get("plan_refs") or [])
                if isinstance(pr, dict) and pr.get("entity_id")
            }
            if sh_plans & set(fast_plan_ids) and sh.get("scope_id"):
                catalog_scope_ids.append(str(sh["scope_id"]))

    unresolved = _scan_unresolved_relevant_pending_artifacts(
        root_path,
        scope_ids=sorted(set(cand_scopes) | set(catalog_scope_ids)),
        plan_ids=fast_plan_ids,
        task_id=tid,
    )
    if unresolved:
        is_corrupt = any("corrupt" in str(u.get("kind") or "") for u in unresolved)
        rc_val = codec.ReasonCode.CONFLICT.value if is_corrupt else codec.ReasonCode.PENDING.value
        d = _diag(
            codec.ReasonCode.CONFLICT if is_corrupt else codec.ReasonCode.PENDING,
            stage=codec.Stage.BUNDLE,
            entity_id=str(tid),
            expected="all relevant pending journals and candidates resolved before execution",
            actual={"unresolved": unresolved, "scope_ids": sorted(cand_scopes), "plan_ids": fast_plan_ids},
            resume_ref=unresolved[0]["path"],
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "task_id": tid,
            "plan_ids": fast_plan_ids,
            "expected_union_scope_ids": sorted(cand_scopes),
            "locked_scope_ids": [],
            "union_scope_fully_locked": False,
            "marker_deletion_bypass_blocked": True,
            "unresolved_pending": unresolved,
            "reason_code": rc_val,
            "return_stage": "3C",
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    gate_res = ch6_gate.evaluate_chapter6_gate(
        root_path,
        tid,
        operation=operation,
        consumer="win_concurrency_check",
        lock_mode="none",
    )
    plan_ids = sorted(
        {
            str(ref.get("entity_id"))
            for ref in (gate_res.get("plan_refs") or [])
            if isinstance(ref, dict) and ref.get("entity_id")
        }
        or set(fast_plan_ids)
    )
    expected_scopes = sorted(
        set(op_scope.resource_scopes(plan_ids=plan_ids, task_ids=[tid]))
        | set(gate_res.get("scope_ids") or [])
    )
    if not gate_res.get("ok"):
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "task_id": tid,
            "plan_ids": plan_ids,
            "expected_union_scope_ids": expected_scopes,
            "locked_scope_ids": [],
            "union_scope_fully_locked": False,
            "marker_deletion_bypass_blocked": True,
            "unresolved_pending": [],
            "reason_code": str(gate_res.get("reason_code") or codec.ReasonCode.CONFLICT.value),
            "return_stage": gate_res.get("return_stage") or "5",
            "diagnostics": list(gate_res.get("diagnostics") or []),
            **INVARIANT_FLAGS,
        }

    locked = sorted(set(gate_res.get("scope_ids") or []))
    # Probe OS byte locks non-destructively (zero mkdir/writes) to detect active cross-process contention.
    inherited_scopes: set[str] = set()
    env_p = os.environ.get(ch6_gate.ENV_LEASE_PATH)
    env_s = os.environ.get(ch6_gate.ENV_LEASE_SECRET)
    if env_p is not None or env_s is not None:
        try:
            rec = ch6_gate._verify_inherited_lease_receipt(root_path, tid, str(env_p or ""), str(env_s or ""))
            inherited_scopes = set(rec.get("scope_ids") or [])
        except codec.CodecError as err:
            d = err.diagnostic.to_dict()
            return {
                "schema_version": WIN_CONCURRENCY_SCHEMA,
                "ok": False,
                "task_id": tid,
                "plan_ids": plan_ids,
                "expected_union_scope_ids": expected_scopes,
                "locked_scope_ids": [],
                "union_scope_fully_locked": False,
                "marker_deletion_bypass_blocked": True,
                "unresolved_pending": [],
                "reason_code": d["reason_code"],
                "return_stage": "5",
                "diagnostics": [d],
                **INVARIANT_FLAGS,
            }

    contended = [
        sid
        for sid in sorted(set(expected_scopes) | set(locked))
        if sid not in inherited_scopes and ch6_gate._probe_scope_lock_is_held(root_path, sid)
    ]
    if contended:
        d = _diag(
            codec.ReasonCode.CONFLICT,
            stage=codec.Stage.BUNDLE,
            entity_id=str(tid),
            expected="all union business scopes available (unlocked by competing processes)",
            actual={"contended_scopes": contended, "return_stage": "5"},
            resume_ref=op_scope.STORE,
        )
        return {
            "schema_version": WIN_CONCURRENCY_SCHEMA,
            "ok": False,
            "task_id": tid,
            "plan_ids": plan_ids,
            "expected_union_scope_ids": expected_scopes,
            "locked_scope_ids": [],
            "contended_scope_ids": contended,
            "union_scope_fully_locked": False,
            "marker_deletion_bypass_blocked": True,
            "unresolved_pending": [],
            "reason_code": codec.ReasonCode.CONFLICT.value,
            "return_stage": "5",
            "diagnostics": [d],
            **INVARIANT_FLAGS,
        }

    covers_all = bool(locked) and set(expected_scopes).issubset(set(locked))
    return {
        "schema_version": WIN_CONCURRENCY_SCHEMA,
        "ok": covers_all,
        "task_id": tid,
        "plan_ids": plan_ids,
        "expected_union_scope_ids": expected_scopes,
        "locked_scope_ids": locked,
        "union_scope_fully_locked": covers_all,
        "marker_deletion_bypass_blocked": True,
        "unresolved_pending": [],
        "uses_global_writer_lock": bool(gate_res.get("uses_global_writer_lock")),
        "reason_code": codec.ReasonCode.OK.value if covers_all else codec.ReasonCode.CONFLICT.value,
        "return_stage": None if covers_all else "5",
        "diagnostics": [],
        **INVARIANT_FLAGS,
    }


def _extract_dev_cli_subcommands(dev_cli_path: Path) -> set[str]:
    if not dev_cli_path.is_file():
        return set()
    try:
        tree = ast.parse(dev_cli_path.read_text(encoding="utf-8"), filename=str(dev_cli_path))
    except (OSError, SyntaxError):
        return set()
    cmds: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_parser" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    cmds.add(first.value)
    return cmds


def _verify_consumer_wiring(path: Path, required_symbols: tuple[str, ...]) -> tuple[bool, list[str]]:
    if not path.is_file():
        return False, list(required_symbols)
    try:
        src = path.read_text(encoding="utf-8")
        ast.parse(src, filename=str(path))
    except (OSError, SyntaxError):
        return False, list(required_symbols) or ["syntax_valid"]
    missing = [sym for sym in required_symbols if sym not in src]
    return len(missing) == 0, missing


def build_epic3_to_epic4_handoff(
    root: Path | str,
    *,
    task_ids: list[int | str] | None = None,
) -> dict[str, Any]:
    """Build an honest Epic 3 -> Epic 4 handoff summary dynamically verifying consumers, CLI, Skills, and docs."""
    started = time.monotonic()
    root_path = task_resolver._validate_root(Path(root))

    consumers_status: list[dict[str, Any]] = []
    missing_consumers: list[str] = []
    consumer_ok_map: dict[str, bool] = {}
    for rel in EPIC3_CONSUMERS:
        p = root_path / rel
        exists = p.is_file()
        req_syms = _CONSUMER_REQUIRED_SYMBOLS.get(rel, ())
        wired, missing_syms = _verify_consumer_wiring(p, req_syms) if exists else (False, list(req_syms))
        row_ok = exists and wired
        consumer_ok_map[rel] = row_ok
        consumers_status.append(
            {
                "path": rel,
                "exists": exists,
                "wired": wired,
                "missing_symbols": missing_syms,
                "sha256": _file_sha256_or_none(p) if exists else None,
            }
        )
        if not row_ok:
            missing_consumers.append(rel if not exists else f"{rel}:missing({','.join(missing_syms)})")

    dev_cli_path = root_path / "scripts/python/dev_cli.py"
    ast_subcommands = _extract_dev_cli_subcommands(dev_cli_path)
    cli_status: list[dict[str, Any]] = []
    missing_cli: list[str] = []
    cli_ok_map: dict[str, bool] = {}
    for cmd_name in EPIC3_CLI_COMMANDS:
        registered = cmd_name in ast_subcommands
        cli_ok_map[cmd_name] = registered
        cli_status.append({"command": cmd_name, "registered_in_dev_cli": registered})
        if not registered:
            missing_cli.append(cmd_name)

    docs_status: list[dict[str, Any]] = []
    missing_docs: list[str] = []
    doc_ok_map: dict[str, bool] = {}
    for rel in EPIC3_OWNING_DOCS:
        p = root_path / rel
        exists = p.is_file()
        req_anchors = _DOC_REQUIRED_ANCHORS.get(rel, ())
        missing_anchors: list[str] = []
        if exists and req_anchors:
            text = p.read_text(encoding="utf-8")
            missing_anchors = [anc for anc in req_anchors if anc not in text]
        row_ok = exists and not missing_anchors
        doc_ok_map[rel] = row_ok
        docs_status.append(
            {
                "path": rel,
                "exists": exists,
                "anchors_verified": row_ok,
                "missing_anchors": missing_anchors,
                "sha256": _file_sha256_or_none(p) if exists else None,
            }
        )
        if not row_ok:
            missing_docs.append(rel if not exists else f"{rel}:missing_anchor({','.join(missing_anchors)})")

    per_task_parity: list[dict[str, Any]] = []
    traceable_event_refs: list[dict[str, Any]] = []
    for raw_id in task_ids or []:
        p_res = evaluate_entrypoint_parity(root_path, task_id=raw_id)
        per_task_parity.append(p_res)
        tid_val = p_res.get("task_id")
        if tid_val is not None:
            rdy_rel = f"logs/ci/chapter5/readiness/task-{tid_val}.json"
            rdy_p = root_path / rdy_rel
            if rdy_p.is_file():
                traceable_event_refs.append(
                    {"task_id": tid_val, "kind": "chapter5_readiness", "path": rdy_rel, "sha256": _file_sha256_or_none(rdy_p)}
                )
            ev_rel = f"{ch6_gate.DEFAULT_EVENTS_DIR}/task-{tid_val}/chapter6-gate-events.jsonl"
            ev_p = root_path / ev_rel
            if ev_p.is_file():
                traceable_event_refs.append(
                    {"task_id": tid_val, "kind": "chapter6_gate_events", "path": ev_rel, "sha256": _file_sha256_or_none(ev_p)}
                )

    live_artifact_digests: dict[str, str | None] = {}
    for gov_rel in (
        records.CATALOG_PATH,
        task_resolver.ORIGINS_PATH,
        f"{records.BASE}/policy.v1.json",
    ):
        gp = root_path / gov_rel
        if gp.is_file():
            live_artifact_digests[gov_rel] = _file_sha256_or_none(gp)

    parity_all_ok = all(bool(item.get("parity_ok")) for item in per_task_parity)

    delivered_capabilities = {
        "task_change_preview_3c": (
            consumer_ok_map.get("scripts/python/_b_route_task_preview.py", False)
            and cli_ok_map.get("b-route-task-preview", False)
            and doc_ok_map.get("docs/workflows/b-route-task-preview.md", False)
        ),
        "governed_triplet_compilation_and_3c_binding": (
            consumer_ok_map.get("scripts/python/compile_b_route_tasks.py", False)
            and cli_ok_map.get("b-route-task-compile", False)
            and doc_ok_map.get("docs/workflows/b-route-task-compilation.md", False)
        ),
        "unified_task_origin_resolution": (
            consumer_ok_map.get("scripts/python/_b_route_task_resolver.py", False)
            and cli_ok_map.get("b-route-task-origin", False)
            and doc_ok_map.get("docs/workflows/b-route-task-origin-resolution.md", False)
        ),
        "chapter4_contract_and_four_part_binding": (
            consumer_ok_map.get("scripts/python/_b_route_chapter4_binding.py", False)
            and cli_ok_map.get("b-route-chapter4-binding", False)
            and doc_ok_map.get("docs/workflows/b-route-chapter4-binding.md", False)
        ),
        "shared_input_set_and_freshness": (
            consumer_ok_map.get("scripts/python/_b_route_input_set.py", False)
            and cli_ok_map.get("b-route-input-set", False)
            and doc_ok_map.get("docs/workflows/b-route-input-set-resolution.md", False)
        ),
        "stage5_mvg_and_nonflow_obligations": (
            consumer_ok_map.get("scripts/python/_b_route_stage5_obligations.py", False)
            and cli_ok_map.get("b-route-stage5-obligations", False)
            and doc_ok_map.get("docs/workflows/b-route-stage5-obligations.md", False)
        ),
        "chapter5_same_source_readiness": (
            consumer_ok_map.get("scripts/python/_b_route_chapter5_readiness.py", False)
            and cli_ok_map.get("b-route-chapter5-readiness", False)
            and doc_ok_map.get("docs/workflows/b-route-chapter5-readiness.md", False)
        ),
        "chapter6_unified_execution_gate_and_scope_leases": (
            consumer_ok_map.get("scripts/python/_b_route_chapter6_gate.py", False)
            and consumer_ok_map.get("scripts/python/run_single_task_chapter6_lane.py", False)
            and consumer_ok_map.get("scripts/sc/run_review_pipeline.py", False)
            and consumer_ok_map.get("scripts/sc/llm_review_needs_fix_fast.py", False)
            and consumer_ok_map.get("scripts/python/_mvg_obligations.py", False)
            and cli_ok_map.get("b-route-chapter6-gate", False)
            and doc_ok_map.get("docs/workflows/b-route-chapter6-gate.md", False)
        ),
        "chapter6_live_recovery_and_route_revalidation": (
            consumer_ok_map.get("scripts/python/_b_route_chapter6_recovery.py", False)
            and consumer_ok_map.get("scripts/python/resume_task.py", False)
            and consumer_ok_map.get("scripts/python/chapter6_route.py", False)
            and doc_ok_map.get("docs/workflows/b-route-chapter6-recovery.md", False)
        ),
        "defect_classification_and_stage_routing": (
            consumer_ok_map.get("scripts/python/_b_route_defect_routing.py", False)
            and cli_ok_map.get("b-route-defect-routing", False)
            and doc_ok_map.get("docs/workflows/b-route-defect-routing.md", False)
        ),
        "target_slice_chapter7_ui_closure": (
            consumer_ok_map.get("scripts/python/_b_route_chapter7_slice.py", False)
            and cli_ok_map.get("b-route-chapter7-slice", False)
            and doc_ok_map.get("docs/workflows/b-route-chapter7-slice.md", False)
        ),
        "page_and_five_entrypoint_parity": (
            consumer_ok_map.get("scripts/python/_b_route_entrypoint_parity.py", False)
            and consumer_ok_map.get("scripts/python/check_b_route_entrypoint_parity.py", False)
            and consumer_ok_map.get("scripts/python/_project_health_http.py", False)
            and consumer_ok_map.get("scripts/python/project_health_runtime.py", False)
            and cli_ok_map.get("b-route-entrypoint-parity", False)
            and doc_ok_map.get("docs/workflows/b-route-entrypoint-parity.md", False)
            and doc_ok_map.get("docs/workflows/project-health-knowledge.md", False)
            and doc_ok_map.get("docs/workflows/stable-public-entrypoints.md", False)
            and doc_ok_map.get("docs/workflows/script-entrypoints-index.md", False)
            and doc_ok_map.get("AGENTS.md", False)
            and parity_all_ok
        ),
    }

    diags: list[dict[str, Any]] = []
    if missing_consumers:
        diags.append(
            _diag(
                codec.ReasonCode.FILE_NOT_FOUND,
                stage=codec.Stage.PATH,
                entity_id="epic3_consumers",
                expected=list(EPIC3_CONSUMERS),
                actual={"missing_consumers": missing_consumers},
            )
        )
    if missing_cli:
        diags.append(
            _diag(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                stage=codec.Stage.BUNDLE,
                entity_id="epic3_cli_commands",
                expected=list(EPIC3_CLI_COMMANDS),
                actual={"missing_cli": missing_cli},
                resume_ref="scripts/python/dev_cli.py",
            )
        )
    if missing_docs:
        diags.append(
            _diag(
                codec.ReasonCode.FILE_NOT_FOUND,
                stage=codec.Stage.PATH,
                entity_id="epic3_owning_docs",
                expected=list(EPIC3_OWNING_DOCS),
                actual={"missing_docs": missing_docs},
            )
        )
    if not parity_all_ok:
        diags.append(
            _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id="epic3_per_task_parity",
                expected="parity_ok=True across all supplied task_ids",
                actual={"failed_tasks": [p.get("task_id") for p in per_task_parity if not p.get("parity_ok")]},
            )
        )

    ok = (
        not missing_consumers
        and not missing_cli
        and not missing_docs
        and parity_all_ok
        and all(delivered_capabilities.values())
    )

    return {
        "schema_version": EPIC3_HANDOFF_SCHEMA,
        "ok": ok,
        "epic": "epic-3",
        "next_epic": "epic-4",
        "delivered_epic3_capabilities": delivered_capabilities,
        "unimplemented_epic4_epic5_capabilities": deepcopy(UNIMPLEMENTED_EPIC4_EPIC5_CAPABILITIES),
        "consumers": consumers_status,
        "cli_commands": cli_status,
        "owning_docs": docs_status,
        "missing_consumers": missing_consumers,
        "missing_cli": missing_cli,
        "missing_docs": missing_docs,
        "live_artifact_digests": live_artifact_digests,
        "traceable_event_refs": traceable_event_refs,
        "per_task_parity": per_task_parity,
        "claims_full_migration": False,
        "claims_cumulative_full_mvg": False,
        "flow_completed": False,
        "report_path": None,
        "diagnostics": diags,
        "metrics": {
            "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
            "consumer_count": len(consumers_status),
            "cli_command_count": len(cli_status),
            "owning_doc_count": len(docs_status),
            "evaluated_task_count": len(per_task_parity),
        },
        **INVARIANT_FLAGS,
    }
