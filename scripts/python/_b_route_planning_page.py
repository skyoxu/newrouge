"""Stage-true B-route planning page service shared by CLI, HTTP and direct Python callers.

The service exposes two entrypoints:

* ``inspect_planning_page_state`` is strictly read-only. It consumes the Story 4.6 derived
  projection for identity/provenance/completeness, computes stage-true action gates
  (3A sources, 3B formal Task-free planning, 3C Task compilation, Chapter 6 via the Story 3.12
  unified gate) and summarizes coordinator progress (committed prefix, uncommitted candidates,
  budget, revoked runs and recoverable operations) from bounded one-level inspection.
* ``execute_planning_page_action`` validates a page request, refuses bypass fields, and
  delegates to the real owning entrypoints (``account_b_route_sources.py``,
  ``plan_capabilities.py``/``plan_mvg.py --input-stage 3b``, ``b_route_adoption.py``,
  ``preview_b_route_task_changes.py``, ``compile_b_route_tasks.py`` and
  ``_b_route_entrypoint_parity.handle_page_b_route_trigger``). It never creates a second state
  machine, never resets planner budgets, never writes Knowledge publication pointers and never
  performs an implicit global Knowledge refresh.

Automated page interactions only prove the UI contract; they never certify Godot gameplay or
Reward pilot acceptance (``ui_contract_only_not_godot_gameplay`` is always true and
``runtime_verified`` is always false).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_knowledge_projection as projection


SCHEMA_VERSION = "newrouge.b-route-planning-page.v1"
VALID_MODES = projection.VALID_MODES
ACTIONS = ("inspect", "3a_sources", "3b_capability", "3b_mvg", "3b_adoption",
           "3c_task_preview", "3c_task_compile", "chapter6")
INVOCATION_MODES = ("new", "resume")
SOURCE_STAGES = ("prepare", "account", "audit", "verify")
PLANNER_NEW_STAGES = ("prepare", "generate")
PLANNER_RESUME_STAGES = ("generate", "review", "status", "verify-selection")
ADOPTION_STAGES = ("inspect", "prepare", "reserve", "apply", "verify", "publish", "recover-inspect", "recover")
ADOPTION_READ_ONLY_STAGES = ("inspect", "recover-inspect")
COMPILE_STAGES = ("prepare", "reserve", "inspect", "apply", "verify", "publish", "recover-inspect", "recover")
COMPILE_READ_ONLY_STAGES = ("inspect", "recover-inspect")
CHAPTER6_SUB_ACTIONS = ("gate", "execute", "resume", "route")
RECOVERY_TARGETS = ("state", "chapter6_resume", "chapter6_route", "adoption")
CITATION_GUIDANCE_CHOICES = ("full-block",)

PAGE_FORBIDDEN_FIELDS = (
    "allow_unready", "allow_unready_draft", "draft", "skip_gate", "reset_budget", "switch_task_origin",
    "set_task_route", "delete_b_origin", "summary_override", "forged_resume_command",
)

ID_FIELDS = ("scope_id", "plan_id", "flow_id", "capability_id", "run_id", "operation_id", "attempt_id")
PATH_FIELDS = ("audit_ref", "source_set", "prepared", "candidate", "accounted", "manifest", "request_ref",
               "planning_contract", "prepared_ref", "protection_ref", "change_intents", "runner",
               "completed_extraction_ref")
STRING_FIELDS = ("action", "mode", "invocation_mode", "stage", "sub_action", "planning_profile", "recovery_target",
                 "schema_version", "expected_model", "citation_guidance")
POSITIVE_INT_FIELDS = ("request_budget", "active_budget_seconds", "timeout_seconds")
ALLOWED_FIELDS = frozenset(("recommendation_only", "task_id", *ID_FIELDS, *PATH_FIELDS, *STRING_FIELDS,
                            *POSITIVE_INT_FIELDS))

FAMILY_FOR_ACTION = {"3b_capability": "capability-planning", "3b_mvg": "mvg-planning"}
PLANNER_SCRIPT = {"3b_capability": "plan_capabilities.py", "3b_mvg": "plan_mvg.py"}
SOURCE_SET_PATH = projection.SOURCE_SET_PATH
CATALOG_PATH = projection.CATALOG_PATH
POINTER_PATHS = projection.PROTECTED_POINTERS
SOURCES_DIR_NAME = "b-route-sources"
SOURCE_AUDIT_DIR_NAME = "b-route-source-audit"
PLANNING_INPUT_DIR = "logs/ci/b-route-planning-input"
OPERATIONS_DIR = projection.OPERATIONS_STORE + "/operations"
REOPEN_ROOT = projection.REOPEN_ROOT
BUDGET_BLOCK_REASON = "run_blocked_budget_exhausted"

MAX_LOG_DATES = 60
MAX_RUN_DIRS = 200
MAX_ATTEMPTS = 20
MAX_REPORTS = 500
DELEGATE_TIMEOUT_SECONDS = 900
OUTPUT_TAIL = 200_000

SCRIPTS_DIR = Path(__file__).resolve().parent
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_TERMINAL_RUN_PHASES = frozenset({"completed", "complete", "applied", "done", "succeeded", "success", "published"})

HONEST_NOTICE = ("UI contract view: automated actions follow B-route gates; this page does not certify Godot "
                 "gameplay or Reward pilot acceptance.")

INVARIANTS = {
    "ui_contract_only_not_godot_gameplay": True,
    "runtime_verified": False,
    "default_b_enabled_by_page": False,
    "pointers_advanced": False,
    "implicit_global_refresh_performed": False,
    "second_state_machine": False,
    "budget_reset_performed": False,
    "task_origin_switch_allowed": False,
    "b_origin_delete_allowed": False,
    "allow_unready_permitted": False,
    "draft_permitted": False,
    "candidate_counts_as_adopted": False,
    "partial_planning_counts_as_complete": False,
}

CommandRunner = Callable[[list[str], Path, int], tuple[int, str, str]]


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _diag(code: codec.ReasonCode, stage: codec.Stage | None, entity: Any, expected: Any, actual: Any,
          resume_ref: str | None = None) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, None if entity is None else str(entity), expected, actual,
                            resume_ref).to_dict()


def _error(code: codec.ReasonCode, stage: codec.Stage, entity: Any, expected: Any, actual: Any,
           resume_ref: str | None = None) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(code, stage, None if entity is None else str(entity),
                                             expected, actual, resume_ref))


_REASON_VALUES = frozenset(item.value for item in codec.ReasonCode)
_STAGE_VALUES = frozenset(item.value for item in codec.Stage)
_DIAG_KEYS = ("reason_code", "stage", "entity_id", "expected", "actual", "resume_ref")


def normalize_diagnostic(value: Any, *, entity: Any = None, resume_ref: str | None = None) -> dict[str, Any]:
    """Keep a valid six-field Diagnostic verbatim; wrap anything else without reinterpreting it."""
    if (isinstance(value, dict) and all(key in value for key in _DIAG_KEYS)
            and value.get("reason_code") in _REASON_VALUES
            and (value.get("stage") is None or value.get("stage") in _STAGE_VALUES)
            and (value.get("entity_id") is None or type(value.get("entity_id")) is str)
            and (value.get("resume_ref") is None or type(value.get("resume_ref")) is str)):
        return {key: value[key] for key in _DIAG_KEYS}
    actual = value if isinstance(value, (str, int, float, bool)) or value is None else json.dumps(
        value, ensure_ascii=True, default=str)[:2000]
    return _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, entity,
                 "six-field codec Diagnostic from the owning service", actual, resume_ref)


def _normalize_all(values: Any, *, entity: Any = None, resume_ref: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [normalize_diagnostic(item, entity=entity, resume_ref=resume_ref) for item in values]


# ---------------------------------------------------------------------------
# Safe bounded reads (never rglob; one directory level at a time)
# ---------------------------------------------------------------------------

def _validate_root(root: Any) -> Path:
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                     "repository root directory", type(root).__name__)
    raw = Path(root)
    try:
        for ancestor in reversed((raw.absolute(), *raw.absolute().parents)):
            inventory.no_reparse(ancestor)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, None,
                     "repository root without reparse ancestors", str(exc)[:200]) from exc
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                     "existing repository root directory", str(resolved))
    return resolved


def _safe_path(root: Path, rel: str) -> Path | None:
    """Return a repository path only when every component is a non-reparse canonical path."""
    try:
        return inventory.safe_input(root, rel, allow_logs=True)
    except ValueError:
        return None


def _read_json(root: Path, rel: str) -> tuple[Any, dict[str, Any] | None]:
    """Strictly read one repository JSON file; return (value, diagnostic)."""
    path = _safe_path(root, rel)
    if path is None:
        return None, _diag(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                           "canonical non-reparse repository path", rel, rel)
    if not path.is_file():
        return None, None
    try:
        return codec.strict_json_loads(path.read_bytes()), None
    except codec.CodecError as err:
        diag = err.diagnostic
        return None, codec.Diagnostic(diag.reason_code, diag.stage or codec.Stage.DECODE, rel, diag.expected,
                                      diag.actual, rel).to_dict()
    except OSError as exc:
        return None, _diag(codec.ReasonCode.READ_ERROR, codec.Stage.CONTENT, rel, "readable JSON file",
                           str(exc)[:200], rel)


def _children(root: Path, rel: str, *, limit: int) -> tuple[list[str], list[str]]:
    base = _safe_path(root, rel)
    files: list[str] = []
    dirs: list[str] = []
    if base is None or not base.is_dir():
        return files, dirs
    try:
        entries = sorted(os.scandir(base), key=lambda entry: entry.name)
    except OSError:
        return files, dirs
    for entry in entries[: limit * 4]:
        try:
            inventory.no_reparse(Path(entry.path))
        except ValueError:
            continue
        if entry.is_dir(follow_symlinks=False):
            dirs.append(entry.name)
        elif entry.is_file(follow_symlinks=False):
            files.append(entry.name)
    return files[:limit], dirs[:limit]


def _sha_file(path: Path) -> str | None:
    if not os.path.lexists(path):
        return None
    try:
        inventory.no_reparse(path)
        if not path.is_file():
            return "non_regular"
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return "unreadable"


def _main_ref(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "refs/heads/main"],
                              capture_output=True, text=True, encoding="utf-8", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def snapshot_pointers(root: Path) -> dict[str, str | None]:
    snap = {rel: _sha_file(root.joinpath(*rel.split("/"))) for rel in POINTER_PATHS}
    snap["refs/heads/main"] = _main_ref(root)
    return snap


# ---------------------------------------------------------------------------
# Stage gates
# ---------------------------------------------------------------------------

def _gate(stage: str, allowed: bool, *, cli: str, cli_stages: tuple[str, ...], diagnostics: list[dict[str, Any]],
          evidence: Any = None, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "allowed": bool(allowed), "cli": cli, "cli_stages": list(cli_stages),
            "requires_tasks": False if stage in ("3A", "3B") else extra.pop("requires_tasks", True),
            "requires_chapter5_readiness": False if stage in ("3A", "3B", "3C")
            else extra.pop("requires_chapter5_readiness", True),
            "allow_unready_permitted": False, "draft_permitted": False,
            "diagnostics": diagnostics, "evidence": evidence, **extra}


def _read_main_snapshot(root: Path) -> Any | None:
    if not (root / ".git").exists() or _main_ref(root) is None:
        return None
    try:
        from _knowledge_catalog_builder import LocalMainSnapshot
        return LocalMainSnapshot(root, "refs/heads/main")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def gate_3a_sources(root: Path, *, mode: str = "workspace_preview") -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    sources: list[Any] = []
    snapshot = _read_main_snapshot(root) if mode == "main" else None
    if snapshot is not None:
        problem = None
        if SOURCE_SET_PATH not in snapshot.paths:
            value = None
        else:
            try:
                value = codec.strict_json_loads(snapshot.read_bytes(SOURCE_SET_PATH))
            except codec.CodecError as err:
                diag = err.diagnostic
                value = None
                problem = codec.Diagnostic(diag.reason_code, diag.stage or codec.Stage.DECODE, SOURCE_SET_PATH,
                                           diag.expected, diag.actual, SOURCE_SET_PATH).to_dict()
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                value = None
                problem = _diag(codec.ReasonCode.READ_ERROR, codec.Stage.CONTENT, SOURCE_SET_PATH,
                                "readable committed source-set JSON on refs/heads/main", str(exc)[:200],
                                SOURCE_SET_PATH)
    else:
        value, problem = _read_json(root, SOURCE_SET_PATH)
    if problem is not None:
        diagnostics.append(problem)
    elif value is None:
        diagnostics.append(_diag(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, SOURCE_SET_PATH,
                                 "versioned Chapter 3 source set with registered sources", None, SOURCE_SET_PATH))
    elif not isinstance(value, dict):
        diagnostics.append(_diag(codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, SOURCE_SET_PATH,
                                 "source-set JSON object", type(value).__name__, SOURCE_SET_PATH))
    else:
        for key in ("active_sources", "active_patterns", "sources"):
            if isinstance(value.get(key), list):
                sources.extend(value[key])
        if not sources:
            diagnostics.append(_diag(codec.ReasonCode.MISSING_REQUIRED_FIELD, codec.Stage.SCHEMA, SOURCE_SET_PATH,
                                     "nonempty active_sources/active_patterns/sources", sorted(value),
                                     SOURCE_SET_PATH))
        elif snapshot is not None:
            committed_paths = set(snapshot.paths)
            explicit_sources = [p for p in (value.get("active_sources") or []) if type(p) is str and p.strip()]
            missing = [p for p in explicit_sources if p not in committed_paths]
            if missing:
                diagnostics.append(_diag(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, missing[0],
                                         "registered source file committed on refs/heads/main", missing[:20],
                                         SOURCE_SET_PATH))
            elif not explicit_sources:
                patterns = [p for p in (value.get("active_patterns") or []) + (value.get("sources") or [])
                            if type(p) is str and p.strip()]
                if patterns and not any(fnmatch.fnmatchcase(path, pat) for pat in patterns for path in committed_paths):
                    diagnostics.append(_diag(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, patterns[0],
                                             "registered source pattern matching committed files on refs/heads/main",
                                             patterns[:20], SOURCE_SET_PATH))
    return _gate("3A", not diagnostics, cli="dev_cli.py b-route-sources", cli_stages=SOURCE_STAGES,
                 diagnostics=diagnostics,
                 evidence={"source_set": SOURCE_SET_PATH, "registered_sources": len(sources),
                           "snapshot_source": "refs/heads/main" if snapshot is not None else "workspace"},
                 action="3a_sources")


def _is_planning_eligible_3a_audit(value: dict[str, Any]) -> bool:
    """Match _b_route_source_audit.py and _b_route_planning_input.py:208-211 eligibility."""
    return (value.get("planning_eligible") is True
            and value.get("execution_complete") is not False
            and value.get("independent_audit") is not False
            and not value.get("semantic_blockers")
            and value.get("evidence_class") in (None, "real_model"))


def _three_a_reports(root: Path) -> list[dict[str, Any]]:
    """Bounded scan of real 3A independent source audit reports (and unaudited sources for visibility)."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def record(rel: str, run: str, attempt: str, stage: str, *, allow_accept: bool) -> bool:
        if rel in seen:
            return len(found) >= MAX_REPORTS
        seen.add(rel)
        value, _problem = _read_json(root, rel)
        if not isinstance(value, dict):
            return len(found) >= MAX_REPORTS
        accepted = bool(allow_accept and _is_planning_eligible_3a_audit(value))
        found.append({"path": rel, "run_id": run, "attempt_id": attempt, "stage": stage,
                      "accepted": accepted, "planning_eligible": value.get("planning_eligible") is True,
                      "formal_adoption": False})
        return len(found) >= MAX_REPORTS

    def scan_audit_root(base: str) -> bool:
        if _safe_path(root, base) is None or not (root / base).is_dir():
            return False
        for run in _children(root, base, limit=MAX_RUN_DIRS)[1]:
            files, attempts = _children(root, f"{base}/{run}", limit=MAX_ATTEMPTS)
            if "report.json" in files:
                if record(f"{base}/{run}/report.json", run, "default", "audit", allow_accept=True):
                    return True
            for attempt in attempts:
                if record(f"{base}/{run}/{attempt}/report.json", run, attempt, "audit", allow_accept=True):
                    return True
        return False

    _files, ci_dirs = _children(root, "logs/ci", limit=10_000)
    dated = sorted((name for name in ci_dirs if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name)), reverse=True)
    # 1. Real 3A independent source audit reports: logs/ci/<date>/b-route-source-audit/<run>/<attempt>/report.json
    for date in dated[:MAX_LOG_DATES]:
        if scan_audit_root(f"logs/ci/{date}/{SOURCE_AUDIT_DIR_NAME}"):
            return found
    # 2. Undated 3A independent source audit reports: logs/ci/b-route-source-audit/<run>/<attempt>/report.json
    if scan_audit_root(f"logs/ci/{SOURCE_AUDIT_DIR_NAME}"):
        return found
    # 3. 3A sources verify (only if planning_eligible is True) and account/audit for visibility.
    for date in dated[:MAX_LOG_DATES]:
        base = f"logs/ci/{date}/{SOURCES_DIR_NAME}"
        if _safe_path(root, base) is None or not (root / base).is_dir():
            continue
        for run in _children(root, base, limit=MAX_RUN_DIRS)[1]:
            for attempt in _children(root, f"{base}/{run}", limit=MAX_ATTEMPTS)[1]:
                for stage in ("verify", "audit", "account"):
                    rel = f"{base}/{run}/{attempt}/{stage}/report.json"
                    # Unaudited account reports NEVER unlock stage_3b_planning.
                    if record(rel, run, attempt, stage, allow_accept=stage == "verify"):
                        return found
    return found


def gate_3b_planning(root: Path, gate_3a: dict[str, Any]) -> dict[str, Any]:
    reports = _three_a_reports(root)
    accepted = [row for row in reports if row["accepted"]]
    diagnostics: list[dict[str, Any]] = []
    if not gate_3a["allowed"]:
        diagnostics.extend(gate_3a["diagnostics"])
    if not accepted:
        diagnostics.append(_diag(codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING, codec.Stage.TARGET,
                                 "3a-source-audit",
                                 "accepted 3A independent source audit report with planning_eligible=true for --input-stage 3b",
                                 {"reports_found": len(reports), "accepted": 0}, SOURCE_SET_PATH))
    return _gate("3B", not diagnostics, cli="plan_capabilities.py|plan_mvg.py --input-stage 3b; b-route-adoption",
                 cli_stages=PLANNER_NEW_STAGES + PLANNER_RESUME_STAGES, diagnostics=diagnostics,
                 evidence={"accepted_3a_reports": accepted[:20], "reports_found": len(reports)},
                 actions=["3b_capability", "3b_mvg", "3b_adoption"])


def gate_3c_tasks(proj: dict[str, Any]) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    plans = [r for r in proj.get("records", []) if r.get("kind") == "plan" and r.get("status") == "valid"]
    catalog = proj.get("catalog") or {}
    pending = proj.get("pending_operations") or []
    if pending:
        diagnostics.extend(normalize_diagnostic(p.get("diagnostic"), entity=p.get("path"), resume_ref=p.get("resume_ref"))
                           for p in pending[:20])
    if catalog.get("present") and catalog.get("status") != "valid":
        blocking = [i["diagnostic"] for i in proj.get("issues", []) if i.get("blocking")][:20]
        diagnostics.extend(normalize_diagnostic(d) for d in blocking)
    if proj.get("filters", {}).get("scope_id") and proj.get("target_found") is False:
        diagnostics.append(_diag(codec.ReasonCode.UNKNOWN_ENTITY, codec.Stage.TARGET,
                                 proj["filters"]["scope_id"], "scope_id present in catalog.v1.json",
                                 "absent", CATALOG_PATH))
    if not plans:
        diagnostics.append(_diag(codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING, codec.Stage.TARGET, CATALOG_PATH,
                                 "formally adopted 3B plan in catalog.v1.json",
                                 {"catalog_present": bool(catalog.get("present")),
                                  "catalog_status": catalog.get("status"), "valid_plans": 0}, CATALOG_PATH))
    return _gate("3C", not diagnostics, cli="dev_cli.py b-route-task-preview|b-route-task-compile",
                 cli_stages=COMPILE_STAGES, diagnostics=diagnostics, requires_tasks=False,
                 evidence={"valid_plans": [{"path": r["path"], "entity_id": r.get("entity_id"),
                                            "revision": r.get("revision")} for r in plans[:50]],
                           "pending_operations": len(pending)},
                 actions=["3c_task_preview", "3c_task_compile"])


def _parity_mode(mode: str) -> str:
    return "main" if mode == "main" else "workspace"


def _chapter6_trigger(root: Path, sub_request: dict[str, Any]) -> dict[str, Any]:
    from _b_route_entrypoint_parity import handle_page_b_route_trigger
    return handle_page_b_route_trigger(root, sub_request)


def _strict_task_id(value: Any) -> int:
    if type(value) is int and value > 0:
        return value
    if type(value) is str and re.fullmatch(r"[1-9][0-9]{0,8}", value):
        return int(value)
    raise _error(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, "task_id", "positive integer Task ID",
                 type(value).__name__ if not isinstance(value, str) else value)


def gate_6_implement(root: Path, proj: dict[str, Any] | None, task_id: Any, mode: str) -> dict[str, Any]:
    tasks = (proj or {}).get("layers", {}).get("tasks", []) if proj else []
    summary = {"tasks_total": len(tasks),
               "b_governed": sum(1 for n in tasks if n.get("governed")),
               "a_or_unmapped": sum(1 for n in tasks if not n.get("governed")),
               "non_flow_governed_requirements": (proj or {}).get("summary", {}).get("non_flow_governed", 0),
               "non_flow_requires_flow_or_scene": False}
    if task_id is None:
        diag = _diag(codec.ReasonCode.MISSING_REQUIRED_FIELD, codec.Stage.TARGET, "task_id",
                     "explicit Taskmaster task_id evaluated by the Story 3.12 unified gate", None, None)
        return _gate("6", False, cli="dev_cli.py b-route-chapter6-gate|run-single-task-chapter6",
                     cli_stages=CHAPTER6_SUB_ACTIONS, diagnostics=[diag], evidence=summary,
                     action="chapter6", task_id=None, route=None, gate_result=None)
    tid = _strict_task_id(task_id)
    result = _chapter6_trigger(root, {"action": "gate", "task_id": tid, "mode": _parity_mode(mode),
                                      "preview": True, "recommendation_only": True})
    allowed = bool(result.get("ok")) and result.get("admitted", True) is not False
    diagnostics = _normalize_all(result.get("diagnostics"), entity=tid, resume_ref=result.get("resume_ref"))
    if not allowed and not diagnostics:
        diagnostics.append(_diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, tid, "admitted Story 3.12 gate",
                                 {"route": result.get("route"), "reason_code": result.get("reason_code")},
                                 result.get("resume_ref")))
    return _gate("6", allowed, cli="dev_cli.py b-route-chapter6-gate|run-single-task-chapter6",
                 cli_stages=CHAPTER6_SUB_ACTIONS, diagnostics=diagnostics, evidence=summary, action="chapter6",
                 task_id=tid, route=result.get("route"), reason_code=result.get("reason_code"),
                 legacy_a_passthrough=bool(result.get("legacy_a_passthrough")),
                 return_stage=result.get("return_stage"))


# ---------------------------------------------------------------------------
# Coordinator progress
# ---------------------------------------------------------------------------

def _registry(root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        from _mvg_capability_recovery import registry
        return registry(root), None
    except (ValueError, OSError, ImportError) as exc:
        return None, _diag(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, codec.Stage.SCHEMA, "mvg-recovery-registry",
                           "valid local recovery registry", str(exc)[:200], "logs/ci/mvg-recovery/registry.json")


def _transaction_ids(value: Any, sink: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "transaction_id" and type(child) is str and child:
                sink.add(child)
            else:
                _transaction_ids(child, sink)
    elif isinstance(value, list):
        for child in value:
            _transaction_ids(child, sink)


def _archived_clear_transactions(root: Path) -> set[str]:
    archived: set[str] = set()
    try:
        from _mvg_capability_recovery import store_root
        store = store_root(root)
    except (ValueError, OSError, ImportError):
        return archived
    clears_dir = store / "clears"
    try:
        inventory.no_reparse(clears_dir)
        if not clears_dir.is_dir():
            return archived
        paths = sorted(clears_dir.glob("epoch-*.json"))[:MAX_RUN_DIRS]
    except (OSError, ValueError):
        return archived
    for path in paths:
        try:
            inventory.no_reparse(path)
            if not path.is_file():
                continue
            doc = codec.strict_json_loads(path.read_bytes())
        except (OSError, ValueError, codec.CodecError):
            continue
        if isinstance(doc, dict):
            _transaction_ids(doc, archived)
            for item in doc.get("revoked", []) if isinstance(doc.get("revoked"), list) else []:
                if type(item) is str and item:
                    archived.add(item)
    return archived


def _load_reopen_markers(root: Path, proj: dict[str, Any] | None = None) -> dict[str, Any]:
    if proj is not None and isinstance(proj.get("chapter6_reopen"), dict):
        return proj["chapter6_reopen"]
    result: dict[str, Any] = {"tasks": {}, "plans": {}, "scopes": {}, "global": [], "damaged": []}
    files, dirs = _children(root, REOPEN_ROOT, limit=MAX_RUN_DIRS)
    rels = [f"{REOPEN_ROOT}/{name}" for name in files if name.endswith(".json")]
    for sub in dirs:
        sub_files, _ = _children(root, f"{REOPEN_ROOT}/{sub}", limit=MAX_ATTEMPTS)
        rels.extend(f"{REOPEN_ROOT}/{sub}/{name}" for name in sub_files if name.endswith(".json"))
    for rel in sorted(set(rels))[:MAX_REPORTS]:
        doc, problem = _read_json(root, rel)
        if problem is not None or not isinstance(doc, dict):
            diag = problem or _diag(codec.ReasonCode.CONFLICT, codec.Stage.DECODE, rel,
                                    "valid reopen/revocation record JSON object", type(doc).__name__, rel)
            result["damaged"].append({"path": rel, "diagnostic": diag})
            continue
        state = str(doc.get("status") or "").strip().lower()
        revoking = (doc.get("revoked") is True or doc.get("reopened") is True or doc.get("superseded") is True
                    or doc.get("epoch_revoked") is True
                    or state in {"revoked", "reopened", "invalidated", "active"})
        if not revoking:
            continue
        tasks: set[str] = set()
        plans: set[str] = set()
        scopes: set[str] = set()
        for plural, sink in (("task_ids", tasks), ("plan_ids", plans), ("scope_ids", scopes)):
            if isinstance(doc.get(plural), list):
                for item in doc[plural]:
                    if type(item) is str and item.strip():
                        sink.add(item.strip())
                    elif type(item) is int and item > 0:
                        sink.add(str(item))
        for singular, sink in (("task_id", tasks), ("plan_id", plans), ("scope_id", scopes)):
            val = doc.get(singular)
            if type(val) is str and val.strip():
                sink.add(val.strip())
            elif type(val) is int and val > 0:
                sink.add(str(val))
        code = codec.ReasonCode.INPUT_STALE if doc.get("epoch_revoked") is True else codec.ReasonCode.CONFLICT
        resume_ref = doc.get("resume_ref") if type(doc.get("resume_ref")) is str and doc.get("resume_ref").strip() else rel
        marker = {"path": rel, "status": state or "revoked", "resume_ref": resume_ref,
                  "reason_code": code.value, "epoch": doc.get("epoch")}
        if doc.get("global") is True or not (tasks or plans or scopes):
            result["global"].append(marker)
        for key, ids in (("tasks", tasks), ("plans", plans), ("scopes", scopes)):
            for ident in ids:
                result[key].setdefault(ident, []).append(marker)
    return result


def _run_reopen_transactions(root: Path, family: str, run_id: str, state: dict[str, Any]) -> list[str]:
    found: list[str] = []
    raw = state.get("reopen_transactions")
    if isinstance(raw, list) and raw:
        found.extend(str(item) for item in raw[:20])
    elif isinstance(raw, dict) and raw:
        found.extend(str(key) for key in list(raw)[:20])
    reopen_file_rel = f"logs/ci/{family}/{run_id}/reopen-transactions.json"
    doc, _ = _read_json(root, reopen_file_rel)
    if isinstance(doc, list) and doc:
        found.append(reopen_file_rel)
    elif isinstance(doc, dict) and doc:
        found.append(reopen_file_rel)
    reopen_dir_rel = f"logs/ci/{family}/{run_id}/reopen-transactions"
    rfiles, _rdirs = _children(root, reopen_dir_rel, limit=20)
    for name in rfiles:
        if name.endswith(".json"):
            found.append(f"{reopen_dir_rel}/{name}")
    return found


def _budget(state: dict[str, Any]) -> dict[str, Any]:
    raw_budget = state.get("request_budget")
    runtime = state.get("planning_runtime") if isinstance(state.get("planning_runtime"), dict) else {}
    runtime_limits = runtime.get("limits") if isinstance(runtime.get("limits"), dict) else {}
    mvg_section = state.get("mvg") if isinstance(state.get("mvg"), dict) else {}
    selection = state.get("capability_selection") if isinstance(state.get("capability_selection"), dict) else {}
    legacy_budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    limit_candidates = [
        raw_budget.get("limit") if isinstance(raw_budget, dict) else raw_budget,
        state.get("request_limit"),
        state.get("mvg.run_invocation_limit"),
        mvg_section.get("run_invocation_limit"),
        runtime_limits.get("request_limit"),
        runtime.get("request_limit"),
        legacy_budget.get("request_limit"),
        legacy_budget.get("max_requests"),
    ]
    limit = next((v for v in limit_candidates if type(v) is int), None)
    used_candidates = [
        state.get("dispatches_used"),
        selection.get("total_invocations"),
        state.get("total_invocations"),
        state.get("lineage_calls"),
        raw_budget.get("used") if isinstance(raw_budget, dict) else None,
        raw_budget.get("observed") if isinstance(raw_budget, dict) else None,
        runtime.get("dispatches_used"),
        runtime.get("total_invocations"),
        legacy_budget.get("used"),
    ]
    used = next((v for v in used_candidates if type(v) is int), None)
    reserved = raw_budget.get("reserved") if isinstance(raw_budget, dict) and type(raw_budget.get("reserved")) is int else None
    repairs = state.get("repair_attempts")
    repair_count = len(repairs) if isinstance(repairs, (list, dict)) else repairs if type(repairs) is int else 0
    candidates = state.get("candidate_attempts")
    exhausted = (state.get("request_budget_exhausted") is True
                 or selection.get("request_budget_exhausted") is True
                 or runtime.get("request_budget_exhausted") is True
                 or state.get("selection_block_reason") == BUDGET_BLOCK_REASON
                 or selection.get("block_reason") == BUDGET_BLOCK_REASON
                 or state.get("phase") == BUDGET_BLOCK_REASON
                 or (limit is not None and used is not None and used >= limit))
    return {"request_budget": raw_budget, "request_limit": limit, "dispatches_used": used, "reserved": reserved,
            "repair_attempts": repair_count,
            "candidate_attempts": len(candidates) if isinstance(candidates, (dict, list)) else 0,
            "legacy_budget": legacy_budget or None,
            "budget_exhausted": bool(exhausted), "budget_is_billing": False}


def _match_reopen_marker(state: dict[str, Any], reopen_markers: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(reopen_markers, dict):
        return None
    if reopen_markers.get("global"):
        return reopen_markers["global"][0]
    if reopen_markers.get("damaged"):
        damaged = reopen_markers["damaged"][0]
        return {"path": damaged.get("path"), "resume_ref": damaged.get("path"), "reason_code": "conflict",
                "status": "damaged", "diagnostic": damaged.get("diagnostic")}
    runtime = state.get("planning_runtime") if isinstance(state.get("planning_runtime"), dict) else {}
    contract = state.get("contract") if isinstance(state.get("contract"), dict) else {}
    contract_scope = contract.get("scope") if isinstance(contract.get("scope"), dict) else {}
    scope_ids = [v for v in (state.get("scope_id"), runtime.get("scope_id"), contract_scope.get("scope_id"))
                 if type(v) is str and v]
    for sid in scope_ids:
        matches = (reopen_markers.get("scopes") or {}).get(sid)
        if matches:
            return matches[0]
    plan_ids = [v for v in (state.get("plan_id"), runtime.get("plan_id")) if type(v) is str and v]
    for pid in plan_ids:
        matches = (reopen_markers.get("plans") or {}).get(pid)
        if matches:
            return matches[0]
    task_ids: list[str] = []
    if state.get("task_id") is not None and type(state.get("task_id")) is not bool:
        task_ids.append(str(state["task_id"]))
    if isinstance(state.get("task_ids"), list):
        task_ids.extend(str(t) for t in state["task_ids"] if t is not None and type(t) is not bool)
    for tid in task_ids:
        matches = (reopen_markers.get("tasks") or {}).get(tid)
        if matches:
            return matches[0]
    return None


def _run_record(root: Path, family: str, run_id: str, registry_value: dict[str, Any] | None,
                registry_problem: dict[str, Any] | None, *, archived_tids: set[str] | None = None,
                reopen_markers: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rel = f"logs/ci/{family}/{run_id}/run.json"
    state, problem = _read_json(root, rel)
    if problem is not None:
        return {"kind": "planner_run", "family": family, "run_id": run_id, "original_locator": rel,
                "resume_ref": rel, "recoverable": False, "revoked": False, "budget_exhausted": False,
                "status": "corrupt", "diagnostic": problem}
    if not isinstance(state, dict):
        return None
    selection = state.get("capability_selection") if isinstance(state.get("capability_selection"), dict) else {}
    selected = selection.get("selected") if isinstance(selection.get("selected"), list) else []
    generated = (selection.get("generated") if isinstance(selection.get("generated"), list)
                 else state.get("generated") if isinstance(state.get("generated"), list) else [])
    completed_count = len(selected) if selected else len(generated)
    order = (selection.get("order") if isinstance(selection.get("order"), list)
             else state.get("order") if isinstance(state.get("order"), list) else None)
    scopes = selection.get("scopes") if isinstance(selection.get("scopes"), list) else None
    total = (selection.get("total") if type(selection.get("total")) is int
             else len(order) if order is not None
             else len(scopes) if scopes is not None else None)
    tids: set[str] = set()
    _transaction_ids(selected, tids)
    _transaction_ids(generated, tids)
    recovery = state.get("recovery") if isinstance(state.get("recovery"), dict) else {}
    reasons: list[str] = []
    diagnostic = None
    if registry_value is None:
        if family == "mvg-planning" and recovery:
            reasons.append("registry_unverifiable")
            diagnostic = registry_problem
    else:
        epoch = registry_value.get("epoch")
        if type(recovery.get("epoch")) is int and recovery["epoch"] != epoch:
            reasons.append("epoch_invalidated")
            diagnostic = _diag(codec.ReasonCode.INPUT_STALE, codec.Stage.TARGET, run_id,
                               {"epoch": epoch}, {"epoch": recovery["epoch"], "reasons": ["epoch_invalidated"]}, rel)
        revoked = tids & {str(v) for v in registry_value.get("revoked", []) if type(v) is str}
        if revoked:
            reasons.append("transaction_revoked")
            diagnostic = _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id,
                               "no revoked committed transaction", sorted(revoked)[:20], rel)
    if archived_tids and (tids & archived_tids):
        reasons.append("transaction_archived_by_clear")
        if diagnostic is None:
            diagnostic = _diag(codec.ReasonCode.INPUT_STALE, codec.Stage.TARGET, run_id,
                               "no transaction archived by mvg-clear", sorted(tids & archived_tids)[:20], rel)
    run_reopens = _run_reopen_transactions(root, family, run_id, state)
    if run_reopens:
        reasons.append("run_reopen_transactions")
        if diagnostic is None:
            diagnostic = _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id,
                               "no pending run reopen transactions", run_reopens[:20], rel)
    reopen_marker = _match_reopen_marker(state, reopen_markers)
    if reopen_marker is not None:
        reasons.append("reopen_revoked")
        if diagnostic is None:
            if isinstance(reopen_marker.get("diagnostic"), dict):
                diagnostic = normalize_diagnostic(reopen_marker["diagnostic"], entity=run_id,
                                                  resume_ref=reopen_marker.get("resume_ref") or rel)
            else:
                code = (codec.ReasonCode.INPUT_STALE if reopen_marker.get("reason_code") == "input_stale"
                        else codec.ReasonCode.CONFLICT)
                diagnostic = _diag(code, codec.Stage.TARGET, run_id, "no active reopen/revocation marker",
                                   {"path": reopen_marker.get("path"), "status": reopen_marker.get("status")},
                                   reopen_marker.get("resume_ref") or rel)
    budget = _budget(state)
    phase = str(state.get("phase") or state.get("status") or "").strip().lower()
    selection_status = str(state.get("selection_status") or selection.get("status") or "").strip().lower() or None
    complete = (selection_status == "selected" and (total is None or completed_count >= total)) or phase in _TERMINAL_RUN_PHASES
    terminal = (state.get("terminal") is True or selection.get("terminal") is True
                or selection_status in ("selected", "blocked") or phase in _TERMINAL_RUN_PHASES)
    candidates = []
    attempts = state.get("candidate_attempts")
    if isinstance(attempts, dict):
        for key, row in list(attempts.items())[:100]:
            final = isinstance(row, dict) and bool(row.get("final_meta"))
            candidates.append({"candidate_id": str(key), "run_id": run_id, "family": family,
                               "status": "candidate_uncommitted" if final else "candidate_in_progress",
                               "adopted": False, "planning_complete": False, "original_locator": rel})
    if budget["budget_exhausted"] and diagnostic is None:
        diagnostic = _diag(codec.ReasonCode.BUDGET_EXHAUSTED, codec.Stage.TARGET, run_id,
                           "remaining planner request budget", {"selection_block_reason":
                                                                state.get("selection_block_reason"),
                                                                "dispatches_used": budget["dispatches_used"],
                                                                "request_limit": budget["request_limit"]}, rel)
    revoked_flag = bool(reasons)
    partial_flag = bool((completed_count > 0 and not complete)
                        or (not complete and not terminal and (total is None or completed_count < total)))
    return {"kind": "planner_run", "family": family, "run_id": run_id, "input_stage": state.get("input_stage"),
            "phase": phase or None, "selection_status": selection_status, "terminal": bool(terminal),
            "complete": bool(complete), "selected": completed_count, "total": total,
            "partial_planning": partial_flag,
            "planning_complete": False, "runtime_verified": False, "candidates": candidates, "budget": budget,
            "revoked": revoked_flag, "revocation_reasons": reasons,
            "budget_exhausted": budget["budget_exhausted"],
            "recoverable": not revoked_flag and not budget["budget_exhausted"] and not terminal,
            "original_locator": rel, "resume_ref": rel, "diagnostic": diagnostic}


def _adoption_operation(root: Path, operation_id: str, pending: list[dict[str, Any]]) -> dict[str, Any]:
    op_hash = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    hashed_base = f"{OPERATIONS_DIR}/{op_hash}"
    raw_base = f"{OPERATIONS_DIR}/{operation_id}"
    hashed_path = _safe_path(root, hashed_base)
    raw_path = _safe_path(root, raw_base)
    if hashed_path is not None and hashed_path.is_dir():
        base = hashed_base
    elif raw_path is not None and raw_path.is_dir():
        base = raw_base
    else:
        base = hashed_base
    files, _dirs = _children(root, base, limit=50)
    journals = []
    for name in files:
        if name.endswith(".json"):
            value, problem = _read_json(root, f"{base}/{name}")
            status = value.get("status", value.get("state", value.get("phase"))) if isinstance(value, dict) else None
            journals.append({"path": f"{base}/{name}", "status": status, "diagnostic": problem})
    related = [p for p in pending if p.get("operation_id") == operation_id
               or str(p.get("path", "")).startswith(hashed_base) or str(p.get("path", "")).startswith(raw_base)]
    diagnostic = None
    if related:
        diagnostic = normalize_diagnostic(related[0].get("diagnostic"), entity=operation_id,
                                          resume_ref=related[0].get("resume_ref"))
    elif not journals:
        diagnostic = _diag(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, operation_id,
                           "original adoption operation journal", None, base)
    return {"kind": "adoption_operation", "operation_id": operation_id, "journals": journals,
            "pending": bool(related), "recoverable": bool(journals) or bool(related),
            "resume_ref": (related[0].get("resume_ref") if related else base), "original_locator": base,
            "read_only_inspection": {"command": "b-route-adoption", "stage": "inspect", "context": True,
                                     "recommendation_only": True},
            "diagnostic": diagnostic}


def coordinator_progress(root: Path, proj: dict[str, Any], *, run_id: str | None = None,
                         operation_id: str | None = None) -> dict[str, Any]:
    registry_value, registry_problem = _registry(root)
    archived_tids = _archived_clear_transactions(root)
    reopen_markers = _load_reopen_markers(root, proj)
    runs: list[dict[str, Any]] = []
    for family in ("capability-planning", "mvg-planning"):
        if run_id is not None:
            names = [run_id]
        else:
            names = _children(root, f"logs/ci/{family}", limit=MAX_RUN_DIRS)[1]
        for name in names:
            if not _RUN_ID_RE.fullmatch(name):
                continue
            record = _run_record(root, family, name, registry_value, registry_problem,
                                 archived_tids=archived_tids, reopen_markers=reopen_markers)
            if record is not None:
                runs.append(record)
    local = proj.get("local_recovery_status") or {}
    jobs = local.get("jobs") if isinstance(local.get("jobs"), list) else []
    candidate_states = [c for r in runs for c in r.get("candidates", [])]
    revoked_runs = [{"kind": r["kind"], "family": r["family"], "run_id": r["run_id"], "revoked": True,
                     "recoverable": False, "reasons": r["revocation_reasons"], "original_locator": r["original_locator"],
                     "diagnostic": r["diagnostic"]} for r in runs if r.get("revoked")]
    revoked_runs += [{"kind": "page_job", "job_id": j.get("job_id"), "revoked": True, "recoverable": False,
                      "reasons": j.get("reasons", []), "original_locator": j.get("original_locator"),
                      "diagnostic": normalize_diagnostic(j.get("diagnostic"), entity=j.get("job_id"))}
                     for j in jobs if j.get("local_status") == "revoked"]
    recoverable: list[dict[str, Any]] = []
    for r in runs:
        if r.get("recoverable"):
            recoverable.append({k: r[k] for k in ("kind", "family", "run_id", "recoverable", "revoked",
                                                  "budget_exhausted", "resume_ref", "original_locator",
                                                  "diagnostic")})
    for j in jobs:
        if j.get("recoverable") and j.get("local_status") != "revoked":
            recoverable.append({"kind": "page_job", "job_id": j.get("job_id"), "recoverable": True,
                                "revoked": False, "budget_exhausted": False,
                                "resume_ref": j.get("original_locator"), "original_locator": j.get("original_locator"),
                                "diagnostic": None})
    pending = proj.get("pending_operations") or []
    if operation_id is not None:
        recoverable.append(_adoption_operation(root, operation_id, pending))
    for p in pending[:50]:
        if operation_id is not None and p.get("operation_id") == operation_id:
            continue
        recoverable.append({"kind": "pending_operation", "operation_id": p.get("operation_id"), "path": p.get("path"),
                            "recoverable": p.get("pending_status") != "damaged", "revoked": False,
                            "budget_exhausted": False, "resume_ref": p.get("resume_ref"),
                            "original_locator": p.get("path"),
                            "diagnostic": normalize_diagnostic(p.get("diagnostic"), entity=p.get("path"),
                                                               resume_ref=p.get("resume_ref"))})
    progress = proj.get("planning_progress") or {}
    partial = (bool(progress.get("partial"))
               or any(not r.get("revoked") and r.get("partial_planning") and r.get("selected") for r in runs)
               or bool(candidate_states))
    exhausted = [r for r in runs if r.get("budget_exhausted")]
    return {
        "committed_prefix": {
            "partial_planning": partial, "planning_complete": False, "runtime_verified": False,
            "workspace_local_progress": progress.get("workspace_local_progress"),
            "runs": [{"family": r["family"], "run_id": r["run_id"], "selected": r.get("selected"),
                      "total": r.get("total"), "partial_planning": r.get("partial_planning", False),
                      "planning_complete": False, "original_locator": r["original_locator"]} for r in runs
                     if r.get("status") != "corrupt"],
        },
        "candidate_states": candidate_states,
        "budget_summary": {
            "runs": [{"family": r["family"], "run_id": r["run_id"], **r["budget"]} for r in runs if r.get("budget")],
            "budget_exhausted": bool(exhausted),
            "exhausted_runs": [r["run_id"] for r in exhausted],
            "recoverable": not exhausted,
            "budget_is_billing": False,
        },
        "revoked_runs": revoked_runs,
        "recoverable_operations": recoverable,
        "planner_runs": runs,
        "registry_epoch": registry_value.get("epoch") if registry_value else None,
        "registry_diagnostic": registry_problem,
        "bounded_scan": {"max_run_dirs": MAX_RUN_DIRS, "recursive_glob": False},
    }


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

def _validate_id(name: str, value: Any, pattern: re.Pattern[str] = _ID_RE) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not pattern.fullmatch(value):
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.TARGET, name,
                     f"{name} matching {pattern.pattern}", value if type(value) is str else type(value).__name__)
    return value


def inspect_planning_page_state(root: Path, *, mode: str = "workspace_preview", scope_id: str | None = None,
                                flow_id: str | None = None, capability_id: str | None = None,
                                task_id: str | None = None, run_id: str | None = None,
                                operation_id: str | None = None) -> dict[str, Any]:
    """Read-only stage-true page state; raises CodecError only for invalid arguments."""
    mode = projection.validate_mode(mode)
    run_id = _validate_id("run_id", run_id, _RUN_ID_RE)
    operation_id = _validate_id("operation_id", operation_id)
    task_filter = None if task_id is None else str(task_id) if type(task_id) is int and type(task_id) is not bool else task_id
    root_path = _validate_root(root)
    proj = projection.build_b_route_knowledge_projection(root_path, mode=mode, scope_id=scope_id, flow_id=flow_id,
                                                         capability_id=capability_id, task_id=task_filter)
    gate3a = gate_3a_sources(root_path, mode=mode)
    gate3b = gate_3b_planning(root_path, gate3a)
    gate3c = gate_3c_tasks(proj)
    gate6 = gate_6_implement(root_path, proj, task_filter, mode)
    progress = coordinator_progress(root_path, proj, run_id=run_id, operation_id=operation_id)
    has_partial_prefix = any(not r.get("revoked") and r.get("status") != "corrupt"
                             and (r.get("selected") or 0) > 0 and not r.get("complete")
                             for r in progress["planner_runs"])
    completeness = ("partial_planning" if has_partial_prefix and proj["planning_completeness"] != "blocked"
                    else proj["planning_completeness"])
    partial = progress["committed_prefix"]["partial_planning"] or completeness == "partial_planning"
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(proj["ok"]),
        "status": proj["status"],
        "action": "inspect",
        "mode": mode,
        "filters": {**proj["filters"], "run_id": run_id, "operation_id": operation_id},
        "recommendation_only": True,
        "provenance": proj["provenance"],
        "planning_completeness": completeness,
        "planning_complete": bool(proj["planning_complete"]) and not partial,
        "partial_planning": bool(partial),
        "planning_progress": proj["planning_progress"],
        "catalog": proj["catalog"],
        "pending_operations": proj["pending_operations"],
        "local_recovery_status": proj["local_recovery_status"],
        "chapter6_reopen": proj["chapter6_reopen"],
        "stage_gates": {"stage_3a_sources": gate3a, "stage_3b_planning": gate3b, "stage_3c_tasks": gate3c,
                        "stage_6_implement": gate6},
        "coordinator_progress": progress,
        "diagnostics": [normalize_diagnostic(d) for d in proj["diagnostics"]],
        "projection_schema_version": projection.SCHEMA_VERSION,
        "projection_summary": proj["summary"],
        "projection_runtime_verified": proj["runtime_verified"],
        "default_b_enabled": proj["default_b_enabled"],
        "runtime_verified": False,
        "ui_contract_only_not_godot_gameplay": True,
        "honest_notice": HONEST_NOTICE,
        "invariants": dict(INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def _forbidden_keys() -> tuple[str, ...]:
    from _b_route_entrypoint_parity import FORBIDDEN_BYPASS_KEYS, SPOOFED_CLIENT_CACHE_KEYS
    return PAGE_FORBIDDEN_FIELDS + tuple(SPOOFED_CLIENT_CACHE_KEYS) + tuple(FORBIDDEN_BYPASS_KEYS)


def _validated_path(root: Path, name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, name,
                     "nonempty unpadded repository-relative POSIX path",
                     value if type(value) is str else type(value).__name__)
    try:
        path = inventory.safe_input(root, value, allow_logs=True)
        inventory.no_reparse(path)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, name,
                     "canonical repository path without traversal, symlink or reparse point",
                     str(exc)[:200]) from exc
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, name, "path contained in repository root",
                     value) from exc
    return value.removeprefix("./")


def validate_request(root: Path, request: Any) -> dict[str, Any]:
    """Strict page request validation; raises CodecError with a six-field Diagnostic."""
    if not isinstance(request, dict):
        raise _error(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, None, "JSON object request",
                     type(request).__name__)
    codec.validate_json_value(request)
    forbidden = sorted(key for key in _forbidden_keys() if key in request)
    if forbidden:
        raise _error(codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, forbidden[0],
                     "no gate bypass, budget reset, origin switch, summary or forged recovery fields", forbidden)
    unknown = sorted(set(request) - ALLOWED_FIELDS)
    if unknown:
        raise _error(codec.ReasonCode.UNKNOWN_FIELD, codec.Stage.CONTENT, unknown[0], sorted(ALLOWED_FIELDS), unknown)
    if "schema_version" in request and request["schema_version"] != SCHEMA_VERSION:
        raise _error(codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, "schema_version", SCHEMA_VERSION,
                     request["schema_version"])
    clean: dict[str, Any] = {}
    for key, value in request.items():
        if key == "recommendation_only":
            if type(value) is not bool:
                raise _error(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, key, "boolean",
                             type(value).__name__)
            clean[key] = value
        elif key == "task_id":
            clean[key] = _strict_task_id(value)
        elif key in POSITIVE_INT_FIELDS:
            if type(value) is not int:
                raise _error(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, key, "positive integer",
                             type(value).__name__)
            if value <= 0:
                raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT, key, "positive integer (> 0)",
                             value)
            clean[key] = value
        elif key in PATH_FIELDS:
            clean[key] = _validated_path(root, key, value)
        elif key in ID_FIELDS:
            if type(value) is not str or not value.strip():
                raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT, key, "nonempty string",
                             value if type(value) is str else type(value).__name__)
            clean[key] = _validate_id(key, value, _RUN_ID_RE if key in ("run_id", "attempt_id") else _ID_RE)
        else:
            if type(value) is not str or not value.strip() or value != value.strip():
                raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT, key, "nonempty unpadded string",
                             value if type(value) is str else type(value).__name__)
            clean[key] = value
    action = clean.get("action")
    if action not in ACTIONS:
        raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "action", list(ACTIONS), action)
    if action != "3a_sources":
        for key in POSITIVE_INT_FIELDS:
            if key in clean:
                raise _error(codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, key,
                             f"{key} is permitted only on action 3a_sources (never as a 3B budget override)",
                             {"action": action, key: clean[key]})
    if clean.get("citation_guidance") is not None and clean["citation_guidance"] not in CITATION_GUIDANCE_CHOICES:
        raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "citation_guidance",
                     list(CITATION_GUIDANCE_CHOICES), clean["citation_guidance"])
    mode = clean.setdefault("mode", "workspace_preview")
    if mode not in VALID_MODES:
        raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "mode", list(VALID_MODES), mode)
    return clean


def _read_only(clean: dict[str, Any]) -> bool:
    action = clean["action"]
    stage = clean.get("stage")
    if action == "inspect":
        return True
    if action == "3b_adoption":
        return stage in ADOPTION_READ_ONLY_STAGES
    if action == "3c_task_compile":
        return stage in COMPILE_READ_ONLY_STAGES
    if action == "chapter6":
        default = clean.get("sub_action") != "execute"
        return clean.get("recommendation_only", default) is True
    return False


def is_read_only_request(root: Path, request: Any) -> bool:
    """Lock classification for the HTTP host; invalid requests are rejected without side effects."""
    try:
        return _read_only(validate_request(_validate_root(root), request))
    except (codec.CodecError, ValueError):
        return True


def _default_runner(argv: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", env=env)
    except OSError as exc:
        return 127, "", f"delegate failed to start: {exc}"
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            proc.kill()
        try:
            proc.communicate(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return 124, "", f"delegate timed out after {timeout}s: {exc}"
    return proc.returncode, (stdout or "")[-OUTPUT_TAIL:], (stderr or "")[-OUTPUT_TAIL:]


def _parse_payload(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _require(clean: dict[str, Any], *names: str) -> None:
    for name in names:
        if clean.get(name) is None:
            raise _error(codec.ReasonCode.MISSING_REQUIRED_FIELD, codec.Stage.CONTENT, name,
                         f"{name} for action {clean['action']}", None)


def _python(script: str) -> list[str]:
    return [sys.executable, "-B", str(SCRIPTS_DIR / script)]


def _blocked(clean: dict[str, Any], diagnostics: list[dict[str, Any]], *, status: str = "blocked",
             **extra: Any) -> dict[str, Any]:
    return {"ok": False, "status": status, "diagnostics": diagnostics, **extra}


def _planner_resume_check(root: Path, family: str, run_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    registry_value, registry_problem = _registry(root)
    archived_tids = _archived_clear_transactions(root)
    reopen_markers = _load_reopen_markers(root)
    rel = f"logs/ci/{family}/{run_id}/run.json"
    safe = _safe_path(root, rel)
    if safe is None:
        return _diag(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, run_id,
                     "canonical non-reparse planner run.json path", rel, rel), None
    if not safe.is_file():
        return _diag(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, run_id,
                     "existing planner run.json for resume", None, rel), None
    state, read_problem = _read_json(root, rel)
    if read_problem is not None:
        return read_problem, None
    if not isinstance(state, dict):
        return _diag(codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, run_id, "run.json object", None, rel), None
    record = _run_record(root, family, run_id, registry_value, registry_problem,
                         archived_tids=archived_tids, reopen_markers=reopen_markers)
    if record is None:
        return _diag(codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, run_id, "run.json object", None, rel), None
    if record.get("status") == "corrupt" or record.get("revoked") or record.get("budget_exhausted"):
        return record["diagnostic"], None
    if not record.get("recoverable"):
        return _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id, "nonterminal recoverable planner run",
                     {"phase": record.get("phase"), "selection_status": record.get("selection_status"),
                      "terminal": record.get("terminal")}, rel), None
    return None, state


def _hydrate_resume_bindings(root: Path, family: str, run_id: str, clean: dict[str, Any],
                             state: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
    rel = f"logs/ci/{family}/{run_id}/run.json"
    runtime = state.get("planning_runtime") if isinstance(state.get("planning_runtime"), dict) else {}
    stored_prepared = (state.get("prepared_ref") if type(state.get("prepared_ref")) is str and state.get("prepared_ref")
                       else runtime.get("prepared_ref") if type(runtime.get("prepared_ref")) is str and runtime.get("prepared_ref")
                       else None)
    stored_profile = (state.get("planning_profile") if type(state.get("planning_profile")) is str and state.get("planning_profile")
                      else runtime.get("profile") if type(runtime.get("profile")) is str and runtime.get("profile")
                      else runtime.get("planning_profile") if type(runtime.get("planning_profile")) is str and runtime.get("planning_profile")
                      else None)
    if clean.get("prepared_ref") and stored_prepared and clean["prepared_ref"] != stored_prepared:
        return None, None, _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id,
                                 stored_prepared, clean["prepared_ref"], rel)
    if clean.get("planning_profile") and stored_profile and clean["planning_profile"] != stored_profile:
        return None, None, _diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id,
                                 stored_profile, clean["planning_profile"], rel)
    prepared_ref = clean.get("prepared_ref") or stored_prepared
    if prepared_ref is not None and not clean.get("prepared_ref"):
        prepared_ref = _validated_path(root, "prepared_ref", prepared_ref)
    planning_profile = clean.get("planning_profile") or stored_profile
    return prepared_ref, planning_profile, None


def _build_delegate(root: Path, clean: dict[str, Any]) -> tuple[list[str] | None, dict[str, Any]]:
    """Return (argv, info) for subprocess delegates, or (None, blocked-result) when gated."""
    action = clean["action"]
    stage = clean.get("stage")
    info: dict[str, Any] = {}
    if action == "3a_sources":
        stage = stage or "prepare"
        if stage not in SOURCE_STAGES:
            raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "stage", list(SOURCE_STAGES), stage)
        _require(clean, "run_id", "scope_id")
        if stage == "prepare":
            gate = gate_3a_sources(root, mode=clean["mode"])
            if not gate["allowed"]:
                return None, _blocked(clean, gate["diagnostics"], gate=gate)
        argv = _python("account_b_route_sources.py") + [
            "--stage", stage, "--root", str(root), "--run-id", clean["run_id"], "--scope-id", clean["scope_id"],
            "--attempt-id", clean.get("attempt_id") or "attempt-1"]
        audit_opts = ("accounted", "audit_ref", "completed_extraction_ref", "runner", "expected_model",
                      "request_budget", "active_budget_seconds", "timeout_seconds", "citation_guidance")
        options = {"prepare": ("source_set",), "account": ("prepared", "candidate"),
                   "audit": audit_opts, "verify": audit_opts}[stage]
        if stage == "prepare" and "source_set" not in clean:
            clean["source_set"] = SOURCE_SET_PATH
        for name in options:
            if clean.get(name) is not None:
                argv += ["--" + name.replace("_", "-"), str(clean[name])]
        info.update(stage=stage, cli="dev_cli.py b-route-sources")
        return argv, info
    if action in FAMILY_FOR_ACTION:
        family = FAMILY_FOR_ACTION[action]
        invocation = clean.get("invocation_mode", "new")
        if invocation not in INVOCATION_MODES:
            raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "invocation_mode",
                         list(INVOCATION_MODES), invocation)
        if invocation == "new":
            stage = stage or "prepare"
            if stage not in PLANNER_NEW_STAGES:
                raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "stage", list(PLANNER_NEW_STAGES),
                             stage)
            run_id = clean.get("run_id") or "page-3b-" + uuid.uuid4().hex[:16]
            if stage == "prepare":
                check_rels = (f"{PLANNING_INPUT_DIR}/{run_id}",
                              f"logs/ci/capability-planning/{run_id}",
                              f"logs/ci/mvg-planning/{run_id}")
            else:
                check_rels = (f"logs/ci/{family}/{run_id}",
                              f"logs/ci/{family}/{run_id}/run.json")
            for rel in check_rels:
                safe = _safe_path(root, rel)
                if safe is None:
                    raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, "run_id",
                                 "canonical non-reparse 3B run path", rel)
                if os.path.lexists(safe):
                    return None, _blocked(clean, [_diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, run_id,
                                                        "fresh run_id for a new 3B run (never reuse a prior slot)",
                                                        "existing run directory", rel)],
                                          run_id=run_id, invocation_mode=invocation)
            gate = gate_3b_planning(root, gate_3a_sources(root, mode=clean["mode"]))
            if not gate["allowed"]:
                return None, _blocked(clean, gate["diagnostics"], gate=gate, run_id=run_id,
                                      invocation_mode=invocation)
            if stage == "prepare":
                _require(clean, "planning_contract")
                argv = _python(PLANNER_SCRIPT[action]) + ["--repo-root", str(root), "prepare", "--run-id", run_id,
                                                          "--input-stage", "3b", "--planning-contract",
                                                          clean["planning_contract"]]
            else:
                _require(clean, "prepared_ref", "planning_profile")
                argv = _python(PLANNER_SCRIPT[action]) + ["--repo-root", str(root), "generate", "--run-id", run_id,
                                                          "--input-stage", "3b", "--prepared-ref",
                                                          clean["prepared_ref"], "--planning-profile",
                                                          clean["planning_profile"]]
                if clean.get("runner"):
                    argv += ["--runner", clean["runner"]]
        else:
            stage = stage or "status"
            if stage not in PLANNER_RESUME_STAGES:
                raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "stage",
                             list(PLANNER_RESUME_STAGES), stage)
            _require(clean, "run_id")
            run_id = clean["run_id"]
            problem, run_state = _planner_resume_check(root, family, run_id)
            if problem is not None or run_state is None:
                return None, _blocked(clean, [problem] if problem else [], run_id=run_id, invocation_mode=invocation)
            prepared_ref, planning_profile, bind_problem = _hydrate_resume_bindings(root, family, run_id, clean,
                                                                                    run_state)
            if bind_problem is not None:
                return None, _blocked(clean, [bind_problem], run_id=run_id, invocation_mode=invocation)
            argv = _python(PLANNER_SCRIPT[action]) + ["--repo-root", str(root), stage, "--run-id", run_id,
                                                      "--input-stage", "3b"]
            if prepared_ref:
                argv += ["--prepared-ref", prepared_ref]
            if planning_profile:
                argv += ["--planning-profile", planning_profile]
            if clean.get("runner") and stage in ("generate", "review"):
                argv += ["--runner", clean["runner"]]
        info.update(stage=stage, run_id=run_id, invocation_mode=invocation, family=family,
                    budget_preserved=invocation == "resume",
                    cli=f"{PLANNER_SCRIPT[action]} --input-stage 3b")
        return argv, info
    if action == "3b_adoption":
        if stage not in ADOPTION_STAGES:
            raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "stage", list(ADOPTION_STAGES), stage)
        _require(clean, "operation_id")
        argv = _python("b_route_adoption.py") + ["--root", str(root), "--stage", stage,
                                                 "--operation-id", clean["operation_id"]]
        if stage == "inspect":
            argv.append("--context")
        if stage == "prepare" and clean.get("request_ref"):
            argv += ["--request", clean["request_ref"]]
        info.update(stage=stage, operation_id=clean["operation_id"], cli="dev_cli.py b-route-adoption")
        return argv, info
    if action in ("3c_task_preview", "3c_task_compile"):
        proj = projection.build_b_route_knowledge_projection(root, mode=clean["mode"], scope_id=clean.get("scope_id"),
                                                             compute_impact=False)
        gate = gate_3c_tasks(proj)
        if not gate["allowed"]:
            return None, _blocked(clean, gate["diagnostics"], gate=gate)
        if action == "3c_task_preview":
            _require(clean, "plan_id", "run_id", "audit_ref", "scope_id")
            argv = _python("preview_b_route_task_changes.py") + [
                "--root", str(root), "--plan-id", clean["plan_id"], "--run-id", clean["run_id"],
                "--audit-ref", clean["audit_ref"], "--scope-id", clean["scope_id"]]
            for name in ("protection_ref", "manifest", "change_intents"):
                if clean.get(name):
                    argv += ["--" + name.replace("_", "-"), clean[name]]
            info.update(cli="dev_cli.py b-route-task-preview")
            return argv, info
        stage = stage or "prepare"
        if stage not in COMPILE_STAGES:
            raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "stage", list(COMPILE_STAGES), stage)
        _require(clean, "operation_id")
        if stage == "prepare":
            _require(clean, "request_ref")
        argv = _python("compile_b_route_tasks.py") + ["--root", str(root), "--stage", stage,
                                                      "--operation-id", clean["operation_id"]]
        if stage == "prepare":
            argv += ["--request", clean["request_ref"]]
        info.update(stage=stage, cli="dev_cli.py b-route-task-compile")
        return argv, info
    raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "action", list(ACTIONS), action)


def _finish(clean: dict[str, Any] | None, result: dict[str, Any], *, recommendation_only: bool,
            before: dict[str, Any] | None, root: Path | None) -> dict[str, Any]:
    diagnostics = [normalize_diagnostic(d) for d in result.pop("diagnostics", [])]
    guard: dict[str, Any] = {"checked": before is not None, "mutated": []}
    if before is not None and root is not None:
        after = snapshot_pointers(root)
        guard["mutated"] = [key for key in sorted(before) if before.get(key) != after.get(key)]
        if guard["mutated"]:
            diagnostics.append(_diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, "knowledge-pointers",
                                     "zero mutation of Knowledge publication pointers and refs/heads/main",
                                     guard["mutated"], guard["mutated"][0]))
            result["ok"] = False
            result["status"] = "blocked"
    first = diagnostics[0] if diagnostics else None
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(result.pop("ok")),
        "status": result.pop("status"),
        "action": (clean or {}).get("action"),
        "mode": (clean or {}).get("mode"),
        "recommendation_only": bool(recommendation_only),
        **result,
        "diagnostics": diagnostics,
        "reason_code": first["reason_code"] if first else codec.ReasonCode.OK.value,
        "resume_ref": result.get("resume_ref") or (first["resume_ref"] if first else None),
        "original_locator": result.get("original_locator") or (first["resume_ref"] if first else None),
        "pointer_guard": guard,
        "implicit_global_refresh_performed": False,
        "runtime_verified": False,
        "ui_contract_only_not_godot_gameplay": True,
        "honest_notice": HONEST_NOTICE,
        "invariants": dict(INVARIANTS),
    }
    return payload


def _validate_events_log_path(root: Path, events_log: str) -> tuple[Path, str]:
    from _b_route_observability import validate_reserved_log_write_path
    target, cleaned, _root_path = validate_reserved_log_write_path(
        root, events_log, suffix=".jsonl", field="events_log",
    )
    return target, cleaned


def _emit_page_stage_event(
    events_target: tuple[Path, str] | None,
    clean: dict[str, Any] | None,
    payload: dict[str, Any],
    started_mono: float,
) -> dict[str, Any]:
    if events_target is None:
        return payload
    ev_path, ev_rel = events_target
    from _b_route_evidence_reuse import append_deduplicated_event
    elapsed = round(max(0.0, time.monotonic() - started_mono), 4)
    clean_req = clean or {}
    event_record = {
        "event_type": "b_route_page_stage_action",
        "action": payload.get("action") or clean_req.get("action"),
        "stage": clean_req.get("stage") or (payload.get("delegate") or {}).get("stage") or clean_req.get("sub_action") or "inspect",
        "mode": payload.get("mode") or clean_req.get("mode"),
        "run_id": payload.get("run_id") or clean_req.get("run_id"),
        "operation_id": clean_req.get("operation_id"),
        "scope_id": clean_req.get("scope_id"),
        "flow_id": clean_req.get("flow_id"),
        "task_id": clean_req.get("task_id"),
        "invocation_mode": payload.get("invocation_mode") or clean_req.get("invocation_mode"),
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "reason_code": payload.get("reason_code"),
        "active_elapsed_seconds": elapsed,
        "recommendation_only": bool(payload.get("recommendation_only")),
    }
    try:
        append_deduplicated_event(ev_path, event_record)
    except (OSError, ValueError) as exc:
        diag = _diag(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            ev_rel,
            "writable non-reserved logs/**/*.jsonl without symlink or reparse point",
            str(exc)[:200],
            ev_rel,
        )
        diags = list(payload.get("diagnostics") or [])
        diags.append(diag)
        payload["diagnostics"] = diags
        payload["ok"] = False
        payload["status"] = "blocked"
        payload["reason_code"] = diag["reason_code"]
        return payload
    payload["events_log_path"] = ev_rel
    return payload


def execute_planning_page_action(root: Path, request: dict[str, Any], *,
                                 command_runner: CommandRunner | None = None,
                                 timeout: int = DELEGATE_TIMEOUT_SECONDS,
                                 events_log: str | None = None) -> dict[str, Any]:
    """Validate and delegate one page action to its real owning entrypoint."""
    started_mono = time.monotonic()
    try:
        root_path = _validate_root(root)
    except codec.CodecError as err:
        return _finish(None, _blocked({}, [err.diagnostic.to_dict()], status="invalid_arguments"),
                       recommendation_only=True, before=None, root=None)
    events_target: tuple[Path, str] | None = None
    if events_log is not None:
        try:
            events_target = _validate_events_log_path(root_path, events_log)
        except codec.CodecError as err:
            return _finish(None, _blocked({}, [err.diagnostic.to_dict()], status="invalid_arguments"),
                           recommendation_only=True, before=None, root=None)
    try:
        clean = validate_request(root_path, request)
    except codec.CodecError as err:
        action = request.get("action") if isinstance(request, dict) and type(request.get("action")) is str else None
        return _emit_page_stage_event(
            events_target, {"action": action},
            _finish({"action": action}, _blocked({}, [err.diagnostic.to_dict()], status="invalid_arguments"),
                    recommendation_only=True, before=None, root=None),
            started_mono,
        )
    read_only = _read_only(clean)
    if clean.get("recommendation_only") is False and clean["action"] == "inspect":
        return _finish(clean, _blocked(clean, [_diag(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT,
                                                     "recommendation_only", True, False)],
                                       status="invalid_arguments"),
                       recommendation_only=True, before=None, root=None)
    if clean.get("recommendation_only") is True and not read_only:
        return _finish(clean, _blocked(clean, [_diag(codec.ReasonCode.CONFLICT, codec.Stage.CONTENT,
                                                     "recommendation_only",
                                                     "read-only stage for recommendation_only requests",
                                                     {"action": clean["action"], "stage": clean.get("stage")})],
                                       status="invalid_arguments"),
                       recommendation_only=True, before=None, root=None)
    before = snapshot_pointers(root_path)
    try:
        if clean["action"] == "inspect":
            target = clean.get("recovery_target", "state")
            if target not in RECOVERY_TARGETS:
                raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "recovery_target",
                             list(RECOVERY_TARGETS), target)
            if target == "state":
                state = inspect_planning_page_state(
                    root_path, mode=clean["mode"], scope_id=clean.get("scope_id"), flow_id=clean.get("flow_id"),
                    capability_id=clean.get("capability_id"),
                    task_id=str(clean["task_id"]) if clean.get("task_id") is not None else None,
                    run_id=clean.get("run_id"), operation_id=clean.get("operation_id"))
                result = {"ok": state["ok"], "status": state["status"], "state": state,
                          "diagnostics": list(state["diagnostics"])}
            elif target in ("chapter6_resume", "chapter6_route"):
                _require(clean, "task_id")
                sub = {"action": target.split("_", 1)[1], "task_id": clean["task_id"],
                       "mode": _parity_mode(clean["mode"]), "recommendation_only": True}
                res = _chapter6_trigger(root_path, sub)
                result = {"ok": bool(res.get("ok")), "status": "ok" if res.get("ok") else "blocked",
                          "delegate": {"service": "_b_route_entrypoint_parity.handle_page_b_route_trigger",
                                       "request": sub}, "delegate_result": res, "route": res.get("route"),
                          "resume_ref": res.get("resume_ref"),
                          "diagnostics": _normalize_all(res.get("diagnostics"), entity=clean["task_id"])}
            else:
                _require(clean, "operation_id")
                argv = _python("b_route_adoption.py") + ["--root", str(root_path), "--stage", "inspect",
                                                         "--operation-id", clean["operation_id"], "--context"]
                result = _run_delegate(root_path, clean, argv, {"stage": "inspect", "cli": "dev_cli.py b-route-adoption"},
                                       command_runner, timeout)
            return _emit_page_stage_event(
                events_target, clean,
                _finish(clean, result, recommendation_only=True, before=before, root=root_path),
                started_mono,
            )
        if clean["action"] == "chapter6":
            sub_action = clean.get("sub_action")
            if sub_action not in CHAPTER6_SUB_ACTIONS:
                raise _error(codec.ReasonCode.INVALID_ENUM, codec.Stage.CONTENT, "sub_action",
                             list(CHAPTER6_SUB_ACTIONS), sub_action)
            _require(clean, "task_id")
            sub = {"action": sub_action, "task_id": clean["task_id"], "mode": _parity_mode(clean["mode"]),
                   "recommendation_only": read_only}
            res = _chapter6_trigger(root_path, sub)
            result = {"ok": bool(res.get("ok")), "status": "ok" if res.get("ok") else "blocked",
                      "delegate": {"service": "_b_route_entrypoint_parity.handle_page_b_route_trigger",
                                   "request": sub},
                      "delegate_result": res, "route": res.get("route"), "admitted": res.get("admitted"),
                      "legacy_a_passthrough": bool(res.get("legacy_a_passthrough")),
                      "resume_ref": res.get("resume_ref"),
                      "diagnostics": _normalize_all(res.get("diagnostics"), entity=clean["task_id"],
                                                    resume_ref=res.get("resume_ref"))}
            if not result["ok"] and not result["diagnostics"]:
                result["diagnostics"].append(_diag(codec.ReasonCode.CONFLICT, codec.Stage.TARGET, clean["task_id"],
                                                   "admitted Story 3.12 unified gate",
                                                   {"route": res.get("route"), "reason_code": res.get("reason_code")},
                                                   res.get("resume_ref")))
            return _emit_page_stage_event(
                events_target, clean,
                _finish(clean, result, recommendation_only=read_only, before=before, root=root_path),
                started_mono,
            )
        argv, info = _build_delegate(root_path, clean)
        if argv is None:
            return _emit_page_stage_event(
                events_target, clean,
                _finish(clean, info, recommendation_only=read_only, before=before, root=root_path),
                started_mono,
            )
        result = _run_delegate(root_path, clean, argv, info, command_runner, timeout)
        return _emit_page_stage_event(
            events_target, clean,
            _finish(clean, result, recommendation_only=read_only, before=before, root=root_path),
            started_mono,
        )
    except codec.CodecError as err:
        return _emit_page_stage_event(
            events_target, clean,
            _finish(clean, _blocked(clean, [err.diagnostic.to_dict()], status="invalid_arguments"),
                    recommendation_only=read_only, before=before, root=root_path),
            started_mono,
        )


def _run_delegate(root: Path, clean: dict[str, Any], argv: list[str], info: dict[str, Any],
                  command_runner: CommandRunner | None, timeout: int) -> dict[str, Any]:
    runner = command_runner or _default_runner
    code, stdout, stderr = runner(list(argv), root, timeout)
    payload = _parse_payload(stdout)
    entity = info.get("run_id") or info.get("operation_id") or clean.get("run_id") or clean.get("operation_id")
    diagnostics = _normalize_all(payload.get("diagnostics") if isinstance(payload, dict) else None, entity=entity)
    if code != 0 and not diagnostics:
        actual: dict[str, Any] = {"exit_code": code, "stderr_tail": stderr[-1000:] if stderr else None}
        if isinstance(payload, dict):
            for key in ("reason", "message", "errors"):
                if payload.get(key) is not None:
                    actual[key] = payload[key]
        diagnostics.append(_diag(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.TARGET, entity,
                                 "owning entrypoint exit code 0", actual, info.get("resume_ref")))
    display = [Path(argv[2]).name if len(argv) > 2 else None, *argv[3:]]
    return {"ok": code == 0, "status": "ok" if code == 0 else "blocked", "delegate": {**info, "argv": display},
            "delegate_exit_code": code, "delegate_result": payload, "run_id": info.get("run_id"),
            "invocation_mode": info.get("invocation_mode"), "diagnostics": diagnostics}


def write_page_report(root: Path, report_rel: str, payload: dict[str, Any]) -> Path:
    """Optional CLI report strictly under non-reserved logs/**/*.json."""
    from _b_route_observability import write_observability_report
    return write_observability_report(root, report_rel, payload)
