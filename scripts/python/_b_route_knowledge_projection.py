"""Read-only derived B-route Knowledge projection with planning/implementation/runtime identity.

The projection derives a ten-layer relation view (source -> Requirement -> Capability ->
Flow -> four-part -> Task -> contract -> scene -> obligation -> impact) from original
authorities and the committed B-route catalog chain. It keeps planning, implementation,
runtime and evidence-level dimensions separate, binds every result to an explicit
snapshot/branch/commit identity, and never writes any repository authority, Knowledge
publication pointer, Taskmaster file, or B-route record. Runtime reports under logs/**
are only resolved as explicit backlinks and are never indexed as repository truth.
The impact layer delegates to the Story 4.1 governed reverse impact closure.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import _b_route_codec as codec
import _b_route_inventory as inventory


SCHEMA_VERSION = "newrouge.b-route-knowledge-projection.v1"
VALID_MODES = ("workspace_preview", "attempt", "stable", "stabilized", "main")
WORKSPACE_TOPOLOGY_VIEWS = ("attempt", "stable", "stabilized")

EVIDENCE_LEVELS = (
    "real_engine_input",
    "scene_method",
    "static_tscn_wiring",
    "unit_deterministic",
    "other_verification",
    "manual_independent",
    "unverified",
)
PLANNING_STATES = (
    "legacy_unmapped",
    "3b_adopted_awaiting_3c",
    "partial_planning",
    "3c_compiled",
    "stage4_bound",
    "stage5_bound",
    "non_flow_governed",
    "planned_future",
    "stale",
    "blocked",
    "revoked",
)
IMPLEMENTATION_STATES = (
    "no_task_yet",
    "pending",
    "in_progress",
    "done_in_taskmaster",
    "planned_unimplemented",
    "not_applicable_non_flow",
)
RUNTIME_STATES = (
    "unverified",
    "passed_local_task",
    "passed_flow_scope",
    "passed_cumulative_mvg",
    "passed_other_verification",
    "failed",
    "stale_revision",
    "workspace_only",
)
OBLIGATION_CLASSES = ("existing_required", "current_new", "out_of_scope_future", "other_verification", "manual_checks")

B_ROUTE_BASE = "docs/planning/b-route/"
CATALOG_PATH = B_ROUTE_BASE + "catalog.v1.json"
ORIGINS_PATH = B_ROUTE_BASE + "task-origins.v1.json"
DEFAULT_ORIGINS_PATH = ORIGINS_PATH
RECORD_SCHEMAS = {
    "catalog": "newrouge.b-route-catalog.v1",
    "plan": codec.PLAN_SCHEMA,
    "binding": "newrouge.b-route-binding.v1",
    "commit": "newrouge.b-route-commit.v1",
    "policy": "newrouge.b-route-policy.v1",
    "origins": "newrouge.b-route-origins.v1",
}
MVG_SCHEMA = "newrouge.mvg-integration.v1"
RECEIPT_SCHEMA = "newrouge.b-route-execution-receipt.v1"
RECOVERY_SCHEMA = "newrouge.mvg-completed-registry.v1"
SOURCE_SET_PATH = "docs/workflows/chapter3-source-set.json"
TOPOLOGY_BASE = "docs/planning/semantic-topology/"
SOURCE_BLOCKS_PATH = TOPOLOGY_BASE + "source-blocks.v1.json"
REQUIREMENT_PATHS = (TOPOLOGY_BASE + "requirements.v1.json", TOPOLOGY_BASE + "semantic-requirements.v1.json")
CAPABILITIES_PATH = TOPOLOGY_BASE + "capabilities.v1.json"
TOPOLOGY_EDGES_PATH = TOPOLOGY_BASE + "topology-edges.v1.json"
TASK_FILES = (
    ".taskmaster/tasks/tasks.json",
    ".taskmaster/tasks/tasks_back.json",
    ".taskmaster/tasks/tasks_gameplay.json",
)
MVG_MANIFEST_DIR = "docs/testing/mvg"
SOURCE_EXCLUSIONS_PATH = "knowledge/policies/source-exclusions.v1.json"

PROTECTED_POINTERS = (
    "knowledge/indexes/current.json",
    "knowledge/indexes/last-known-good.json",
    "logs/ci/project-health-knowledge/latest.json",
    "logs/ci/project-health-knowledge/runtime/latest.json",
)
PROTECTED_TREES = ("docs/planning/b-route/", ".taskmaster/tasks/")

OPERATIONS_STORE = "logs/ci/b-route-operations"
PENDING_MARKERS = ("docs/planning/b-route/capability-apply.pending.json",
                   "docs/planning/semantic-topology/capability-apply.pending.json")
LEGACY_PLANNING_DIRS = ("logs/ci/mvg-planning", "logs/ci/capability-planning")
BOUNDED_JOURNAL_DIRS = ("logs/ci/b-route-chapter4-binding", "logs/ci/b-route-stage5-obligations")
REOPEN_ROOT = "logs/ci/b-route-reopen"
MVG_ACCEPTANCE_DIR = "logs/ci/mvg-acceptance"
RUNTIME_DIR = "logs/ci/project-health-knowledge/runtime"
KNOWLEDGE_PLANNING_DIR = "logs/ci/knowledge-planning"
MVG_PLANNING_DIR = "logs/ci/mvg-planning"
RECOVERY_DIR = "logs/ci/mvg-recovery"
RESERVED_REPORT_PREFIXES = (
    "logs/ci/mvg-recovery", "logs/ci/project-health-knowledge", "logs/ci/b-route-operations",
    "logs/ci/b-route-reopen", "logs/ci/mvg-acceptance", "logs/ci/mvg-planning", "logs/ci/capability-planning",
    "logs/ci/knowledge-planning", "logs/ci/b-route-chapter4-binding", "logs/ci/b-route-stage5-obligations",
)

MAX_SCAN_FILES = 500
MAX_RUNTIME_RUNS = 200
MAX_IMPACT_ROOTS = 200
MAX_MATERIALIZED_FILES = 6000
TERMINAL_JOURNAL_STATES = frozenset({
    "completed", "complete", "committed", "published", "succeeded", "success", "done", "resolved",
    "compensated", "aborted", "rolled_back", "superseded", "closed", "aborted_resolved",
})
PARTIAL_JOB_STATUSES = frozenset({"queued", "running", "paused", "failed", "partial", "recoverable", "cancelled", "canceled"})
NON_FLOW_DISPOSITIONS = frozenset({
    "non_flow", "other_verification", "deferred", "global_constraint", "quality_gate", "adr",
})
UNRESOLVED_DISPOSITIONS = frozenset({"source_gap", "unresolved"})
NON_FLOW_SINKS = frozenset({"deferred", "global_constraint", "quality_gate", "adr"})
LOGICAL_FOUR_PART = ("state_change", "action_or_handoff", "user_visible_feedback", "verification_entry")
CUMULATIVE_SCOPES = frozenset({"full", "cumulative", "full_mvg", "full-mvg"})
SCOPED_SCOPES = frozenset({"scoped", "partial", "critical", "flow", "selective"})
MATERIALIZE_PREFIXES = (
    "docs/planning/", ".taskmaster/tasks/", "docs/testing/mvg/", "Game.Core/Contracts/", "Game.Godot/",
    "Tests.Godot/", "Game.Core.Tests/", "docs/gdd/", "docs/adr/", "docs/verification/", "knowledge/policies/",
    "docs/workflows/chapter3-source-set.json",
)
MATERIALIZE_SUFFIXES = (".json", ".cs", ".tscn", ".tres", ".gd", ".md", ".txt", ".scn", ".csproj")
_FILTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_CONTRACT_RE = re.compile(r"Game\.Core/Contracts/[A-Za-z0-9_./-]+\.cs")
_SCENE_RE = re.compile(r"(?:res://)?((?:Game\.Godot|Scenes|scenes)/[A-Za-z0-9_./-]+\.tscn)")
_GODOT_TEST_RE = re.compile(r"Tests\.Godot/[A-Za-z0-9_./-]+")
_REVISION_RE = re.compile(r"[0-9a-f]{40}")

_EVIDENCE_ALIASES = {
    "real_engine_input": "real_engine_input", "real-engine-input": "real_engine_input",
    "engine-input": "real_engine_input", "engine_input": "real_engine_input",
    "scene_method": "scene_method", "scene-method": "scene_method", "godot-gdunit": "scene_method",
    "gdunit": "scene_method", "scene": "scene_method", "runtime": "scene_method",
    "static_tscn_wiring": "static_tscn_wiring", "static-wiring": "static_tscn_wiring",
    "static_wiring": "static_tscn_wiring", "static-tscn-wiring": "static_tscn_wiring",
    "unit_deterministic": "unit_deterministic", "domain-xunit": "unit_deterministic",
    "domain-integration": "unit_deterministic", "xunit": "unit_deterministic", "unit": "unit_deterministic",
    "dotnet": "unit_deterministic", "domain": "unit_deterministic",
    "other_verification": "other_verification", "other-verification": "other_verification",
    "manual_independent": "manual_independent", "manual": "manual_independent",
    "manual-independent": "manual_independent",
}

_TASKMASTER_STATUS = {
    "pending": "pending", "todo": "pending", "deferred": "pending", "blocked": "pending",
    "cancelled": "pending", "in-progress": "in_progress", "in_progress": "in_progress",
    "review": "in_progress", "done": "done_in_taskmaster", "completed": "done_in_taskmaster",
}

INVARIANTS = {
    "read_only": True,
    "writes_performed": False,
    "pointers_advanced": False,
    "tasks_mutated": False,
    "catalog_mutated": False,
    "sources_mutated": False,
    "implicit_global_refresh_performed": False,
    "relation_implies_implementation": False,
    "partial_planning_implies_runtime_verified": False,
    "planned_counts_as_resource": False,
    "logs_indexed_as_repository_truth": False,
}


def normalize_evidence_level(value: Any) -> str:
    if type(value) is not str:
        return "unverified"
    return _EVIDENCE_ALIASES.get(value.strip().lower(), "unverified")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _diag(code: codec.ReasonCode, stage: codec.Stage | None, entity: Any, expected: Any,
          actual: Any, resume_ref: str | None = None) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, None if entity is None else str(entity), expected, actual,
                            resume_ref).to_dict()


def _invalid_argument(expected: Any, actual: Any, stage: codec.Stage = codec.Stage.TARGET,
                      code: codec.ReasonCode = codec.ReasonCode.INVALID_ARGUMENT) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(code, stage, None, expected, actual, None))


def validate_mode(mode: Any) -> str:
    if type(mode) is not str or not mode.strip() or mode not in VALID_MODES:
        raise _invalid_argument("mode in " + "|".join(VALID_MODES),
                                mode if type(mode) is str else type(mode).__name__)
    return mode


def validate_filter(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not _FILTER_RE.fullmatch(value):
        raise _invalid_argument(f"{name} matching {_FILTER_RE.pattern}",
                                value if type(value) is str else type(value).__name__)
    return value


def _id(value: Any) -> str | None:
    """Portable identifier; bool/None/containers are rejected instead of being stringified."""
    if isinstance(value, bool) or value is None:
        return None
    if type(value) is int:
        return str(value)
    if type(value) is str and value.strip():
        return value
    return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ids(value: Any) -> list[str]:
    return [item for item in (_id(v) for v in _as_list(value)) if item is not None]


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _clean_rel(value: Any) -> str | None:
    if type(value) is not str or not value:
        return None
    return value.removeprefix("./") if value.startswith("./") else value


class _WorkspaceReader:
    """Bounded working-tree reader guarded by canonical path and reparse checks.

    Reparse points and case aliases are recorded in ``unsafe`` so the caller can raise a
    blocking six-field diagnostic instead of silently treating the path as missing.
    """

    kind = "workspace"

    def __init__(self, root: Path, record: bool = True):
        self.root = root
        self.record = record
        self.digests: dict[str, str] = {}
        self.unsafe: dict[str, str] = {}

    def _path(self, rel: str) -> Path | None:
        rel = _clean_rel(rel)
        if rel is None:
            return None
        allow_logs = rel.split("/", 1)[0] == "logs"
        try:
            inventory.canonical_path(rel, allow_logs=allow_logs)
        except ValueError:
            return None
        try:
            return inventory.safe_input(self.root, rel, allow_logs=allow_logs)
        except (ValueError, OSError) as exc:
            self.unsafe.setdefault(rel, str(exc)[:200])
            return None

    def exists(self, rel: str) -> bool:
        path = self._path(rel)
        return bool(path is not None and path.is_file())

    def read(self, rel: str) -> bytes | None:
        path = self._path(rel)
        if path is None or not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if self.record:
            self.digests[_clean_rel(rel)] = _sha256(data)
        return data

    def _entry_safe(self, rel: str, path: Path) -> bool:
        try:
            inventory.no_reparse(path)
        except ValueError as exc:
            self.unsafe.setdefault(rel, str(exc)[:200])
            return False
        return True

    def children(self, directory: str, limit: int = MAX_SCAN_FILES) -> tuple[list[str], list[str]]:
        """Return sorted (file names, directory names) of one level; reparse entries are recorded."""
        base = self._path(directory)
        if base is None or not base.is_dir():
            return [], []
        files: list[str] = []
        dirs: list[str] = []
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name)
        except OSError:
            return [], []
        for path in entries:
            rel = directory.rstrip("/") + "/" + path.name
            if not self._entry_safe(rel, path):
                continue
            if path.is_dir():
                dirs.append(path.name)
            elif path.is_file():
                files.append(path.name)
            if len(files) + len(dirs) >= limit:
                break
        return files, dirs

    def list(self, directory: str, pattern: str, limit: int = MAX_SCAN_FILES, *,
             newest_first: bool = False) -> list[str]:
        base = self._path(directory)
        if base is None or not base.is_dir():
            return []
        if "**" in pattern:
            raise ValueError("recursive glob patterns are not allowed")
        candidates = sorted(base.glob(pattern), key=lambda p: p.relative_to(base).as_posix(),
                            reverse=newest_first)
        result = []
        for path in candidates:
            rel = directory.rstrip("/") + "/" + path.relative_to(base).as_posix()
            current = path
            safe = True
            while current != base:
                if not self._entry_safe(rel, current):
                    safe = False
                    break
                current = current.parent
            if safe and path.is_file():
                result.append(rel)
            if len(result) >= limit:
                break
        return result


class _GitReader:
    """Committed-tree reader bound to refs/heads/main; dirty edits are never visible."""

    kind = "git"

    def __init__(self, snapshot: Any):
        self.snapshot = snapshot
        self.paths = set(snapshot.paths)
        self.digests: dict[str, str] = {}
        self.unsafe: dict[str, str] = {}

    def exists(self, rel: str) -> bool:
        rel = _clean_rel(rel)
        return rel is not None and rel in self.paths

    def read(self, rel: str) -> bytes | None:
        rel = _clean_rel(rel)
        if rel is None or rel not in self.paths:
            return None
        try:
            data = self.snapshot.read_bytes(rel)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        self.digests[rel] = _sha256(data)
        return data

    def list(self, directory: str, pattern: str, limit: int = MAX_SCAN_FILES, *,
             newest_first: bool = False) -> list[str]:
        prefix = directory.rstrip("/") + "/"
        result = [path for path in sorted(self.paths, reverse=newest_first)
                  if path.startswith(prefix) and fnmatch.fnmatchcase(path[len(prefix):], pattern)
                  and path[len(prefix):].count("/") == pattern.count("/")]
        return result[:limit]


class _Context:
    def __init__(self, root: Path, mode: str, reader: Any, logs_reader: _WorkspaceReader):
        self.root = root
        self.mode = mode
        self.reader = reader
        self.logs = logs_reader
        self.local = _WorkspaceReader(root, record=False)
        self.issues: list[dict[str, Any]] = []
        self.records: dict[str, dict[str, Any]] = {}
        self.values: dict[str, Any] = {}

    def issue(self, status: str, code: codec.ReasonCode, stage: codec.Stage | None, entity: Any,
              expected: Any, actual: Any, locator: str | None, *, resume_ref: str | None = None,
              blocking: bool = True, subject: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = {
            "status": status,
            "blocking": blocking,
            "subject": subject,
            "original_locator": locator,
            "diagnostic": _diag(code, stage, entity, expected, actual, resume_ref or locator),
        }
        self.issues.append(entry)
        return entry

    def read_any(self, rel: str) -> bytes | None:
        rel = _clean_rel(rel)
        if rel is None:
            return None
        if rel.split("/", 1)[0] == "logs":
            return self.logs.read(rel)
        return self.reader.read(rel)

    def exists_any(self, rel: str) -> bool:
        rel = _clean_rel(rel)
        if rel is None:
            return False
        if rel.split("/", 1)[0] == "logs":
            return self.logs.exists(rel)
        return self.reader.exists(rel)

    def flush_unsafe(self) -> None:
        seen = {issue["original_locator"] for issue in self.issues
                if issue["diagnostic"]["reason_code"] == codec.ReasonCode.UNSAFE_PATH.value}
        for reader in (self.reader, self.logs, self.local):
            for rel, message in sorted(getattr(reader, "unsafe", {}).items()):
                if rel in seen:
                    continue
                seen.add(rel)
                self.issue("blocked", codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                           "regular path without symlink, junction, reparse point or case alias", message, rel)


class _Corrupt:
    def __repr__(self) -> str:
        return "<corrupt>"


_CORRUPT = _Corrupt()


def _strict_parse(ctx: _Context, raw: bytes | None, rel: str, *, blocking: bool = True,
                  status: str = "blocked", subject: dict[str, Any] | None = None) -> Any:
    """Strict JSON (UTF-8, no duplicate keys, no NaN/Infinity); failures emit a diagnostic."""
    if raw is None:
        return None
    try:
        return codec.strict_json_loads(raw)
    except codec.CodecError as err:
        diag = err.diagnostic
        ctx.issue(status, diag.reason_code, diag.stage or codec.Stage.DECODE, rel, diag.expected,
                  diag.actual, rel, blocking=blocking, subject=subject)
        return _CORRUPT


def _load_document(ctx: _Context, rel: str, *, blocking: bool = True,
                   subject: dict[str, Any] | None = None) -> Any:
    return _strict_parse(ctx, ctx.read_any(rel), rel, blocking=blocking, subject=subject)


def _validate_record(ctx: _Context, raw: bytes, path: str, entity: Any) -> bool:
    try:
        import _b_route_records as records
        result = records.validate_record(raw, path=path)
    except Exception as exc:  # pragma: no cover - validator dependency must fail closed
        ctx.issue("blocked", codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.SCHEMA, entity or path,
                  "available FORMAL record validator", type(exc).__name__, path)
        return False
    if not result.ok:
        diag = result.diagnostic
        ctx.issue("blocked", diag.reason_code, diag.stage or codec.Stage.SCHEMA, entity or path,
                  diag.expected, diag.actual, path)
        return False
    return True


# ---------------------------------------------------------------------------
# Provenance and snapshot binding
# ---------------------------------------------------------------------------

def _git_identity(root: Path) -> dict[str, Any]:
    has_git = (root / ".git").exists()
    if not has_git:
        return {"has_git": False, "head_commit": None, "current_branch": None, "main_commit": None,
                "status_readable": True, "changed_paths": [], "head_matches_main": False}
    head = (_git(root, "rev-parse", "--verify", "HEAD") or "").strip() or None
    branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None
    main = (_git(root, "rev-parse", "--verify", "--quiet", "refs/heads/main") or "").strip() or None
    status = _git(root, "status", "--porcelain=v1", "-z", "-uall")
    changed: list[str] = []
    if status is not None:
        parts = status.split("\0")
        index = 0
        while index < len(parts):
            entry = parts[index]
            index += 1
            if len(entry) < 4:
                continue
            code, path = entry[:2], entry[3:]
            changed.append(path)
            if "R" in code or "C" in code:
                index += 1
    return {
        "has_git": True,
        "head_commit": head,
        "current_branch": branch,
        "main_commit": main,
        "status_readable": status is not None,
        "changed_paths": sorted(set(changed)),
        "head_matches_main": bool(head and main and head == main),
    }


def _exclusion_rules(raw: bytes | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    try:
        doc = codec.strict_json_loads(raw)
    except codec.CodecError:
        return []
    rules = doc.get("rules") if isinstance(doc, dict) else None
    return [rule for rule in _as_list(rules) if isinstance(rule, dict) and rule.get("disposition") == "excluded"]


def _excluded(path: str, rules: list[dict[str, Any]]) -> bool:
    for rule in rules:
        prefix = rule.get("path_prefix")
        pattern = rule.get("path_pattern")
        if type(prefix) is str and prefix and (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
            return True
        if type(pattern) is str and pattern and fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def _bind_provenance(root: Path, mode: str) -> tuple[Any, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    identity = _git_identity(root)
    warnings: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {
        "mode": mode,
        "has_git": identity["has_git"],
        "branch": identity["current_branch"],
        "head_commit": identity["head_commit"],
        "main_commit": identity["main_commit"],
        "head_matches_main": identity["head_matches_main"],
        "dirty_workspace": False,
        "dirty_tracked_sources": False,
        "dirty_tracked_paths": [],
        "dirty_untracked_paths": [],
        "authority_ref": "local-workspace",
        "snapshot_source": None,
        "snapshot_commit": None,
        "is_main_fact": False,
        "trusted_ref_eligible": False,
        "can_advance_canonical": False,
        "pointers_advanced": False,
        "workspace_view": mode if mode in WORKSPACE_TOPOLOGY_VIEWS else None,
        "workspace_topology_identity": None,
        "workspace_topology_available": None,
        "warnings": warnings,
    }
    reader: Any = None
    snapshot = None
    if mode == "main" and identity["has_git"] and identity["main_commit"]:
        try:
            from _knowledge_catalog_builder import LocalMainSnapshot
            snapshot = LocalMainSnapshot(root, "refs/heads/main")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            warnings.append(_diag(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.TARGET, "refs/heads/main",
                                  "readable committed refs/heads/main tree", str(exc)[:200]))
    if snapshot is not None:
        reader = _GitReader(snapshot)
    else:
        reader = _WorkspaceReader(root)
    # ADR-0035: the dirty check honors source exclusions read from the bound snapshot, so
    # dirty workspace exclusions never redefine what counts as main authority.
    rules = _exclusion_rules(reader.read(SOURCE_EXCLUSIONS_PATH))
    relevant = [path for path in identity["changed_paths"] if not _excluded(path, rules)]
    untracked: list[str] = []
    if identity["has_git"]:
        untracked_raw = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        untracked = sorted({p for p in (untracked_raw or "").split("\0") if p} & set(relevant))
    dirty = bool(relevant) or not identity["status_readable"]
    provenance.update(dirty_workspace=dirty, dirty_tracked_sources=dirty,
                      dirty_tracked_paths=sorted(set(relevant) - set(untracked))[:50],
                      dirty_untracked_paths=untracked[:50])
    trusted = bool(identity["has_git"] and identity["main_commit"] and identity["head_matches_main"] and not dirty)
    if mode == "main":
        if snapshot is not None:
            provenance.update({
                "authority_ref": "refs/heads/main",
                "snapshot_source": "refs/heads/main",
                "snapshot_commit": snapshot.commit,
                "is_main_fact": trusted,
                "trusted_ref_eligible": trusted,
                "can_advance_canonical": trusted,
            })
            if not trusted:
                warnings.append(_diag(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.TARGET, "trusted-ref",
                                      "HEAD equals refs/heads/main with clean tracked and untracked authority",
                                      {"head_matches_main": identity["head_matches_main"],
                                       "dirty_workspace": dirty,
                                       "dirty_paths": (sorted(relevant)[:10])}))
        else:
            provenance["authority_ref"] = "local-workspace-fallback"
            warnings.append(_diag(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.TARGET, "refs/heads/main",
                                  "committed refs/heads/main snapshot",
                                  "refs/heads/main unavailable; workspace bytes are not main facts"))
    else:
        provenance["snapshot_source"] = "local-workspace"
        provenance["snapshot_commit"] = identity["head_commit"]
        if mode in WORKSPACE_TOPOLOGY_VIEWS:
            try:
                from _semantic_topology import load_workspace_topology
                topology = load_workspace_topology(root, mode)
                provenance["workspace_topology_identity"] = topology.get("identity")
                provenance["workspace_topology_available"] = bool(topology.get("available"))
            except Exception as exc:  # pragma: no cover - defensive read-only boundary
                warnings.append(_diag(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.TARGET, mode,
                                      "workspace topology view", str(exc)[:200]))
    return reader, provenance, warnings, identity


# ---------------------------------------------------------------------------
# B-route catalog chain
# ---------------------------------------------------------------------------

def _resolve_ref(ctx: _Context, ref: Any, kind: str, owner: str, pointer: str) -> dict[str, Any] | None:
    locator = f"{owner}#{pointer}"
    if not isinstance(ref, dict) or type(ref.get("path")) is not str or type(ref.get("digest")) is not str:
        ctx.issue("blocked", codec.ReasonCode.INVALID_REFERENCE, codec.Stage.REFERENCE, owner,
                  f"typed {kind} reference with path and digest", type(ref).__name__, locator)
        return None
    path = ref["path"]
    try:
        inventory.canonical_path(path)
    except ValueError:
        path = None
    if path is None or not path.startswith(B_ROUTE_BASE) or not path.endswith(".json"):
        ctx.issue("blocked", codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, owner,
                  f"canonical {B_ROUTE_BASE}**/*.json path", ref.get("path"), locator)
        return None
    if path in ctx.records:
        cached = ctx.records[path]
        return ctx.values.get(path) if cached["status"] == "valid" else None
    entity = _id(ref.get("entity_id"))
    entry = {"path": path, "kind": kind, "status": "blocked", "digest": None, "schema_validated": False,
             "entity_id": entity, "revision": ref.get("revision"), "referenced_by": locator}
    ctx.records[path] = entry
    raw = ctx.reader.read(path)
    if raw is None:
        ctx.issue("blocked", codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.REFERENCE, entity or path,
                  "referenced record present in bound snapshot", None, path)
        return None
    entry["digest"] = _sha256(raw)
    value = _strict_parse(ctx, raw, path)
    if value is _CORRUPT:
        return None
    mode = ref.get("verification_mode", "raw")
    try:
        actual = codec.raw_digest(raw) if mode == "raw" else codec.canonical_digest(value)
    except codec.CodecError as err:
        ctx.issue("blocked", err.diagnostic.reason_code, codec.Stage.CONTENT, path, ref["digest"], None, path)
        return None
    if actual != ref["digest"]:
        ctx.issue("blocked", codec.ReasonCode.DIGEST_MISMATCH, codec.Stage.CONTENT, entity or path,
                  ref["digest"], actual, path)
        return None
    expected_schema = RECORD_SCHEMAS[kind]
    if not isinstance(value, dict) or value.get("schema_version") != expected_schema \
            or ref.get("schema_version", expected_schema) != expected_schema:
        ctx.issue("blocked", codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, path, expected_schema,
                  value.get("schema_version") if isinstance(value, dict) else type(value).__name__, path)
        return None
    if not _validate_record(ctx, raw, path, entity):
        return None
    entry["schema_validated"] = True
    entry["status"] = "valid"
    ctx.values[path] = value
    return value


def _owned_files(value: Any) -> list[dict[str, Any]]:
    files = []
    if isinstance(value, dict):
        for item in _as_list(value.get("files")):
            if isinstance(item, dict) and type(item.get("path")) is str:
                files.append(item)
    return files


def _check_freshness(ctx: _Context, owned: list[Any], entity: str, locator: str,
                     subject: dict[str, Any]) -> bool:
    fresh = True
    for ref in owned:
        for item in _owned_files(ref):
            expected = item.get("raw_digest") or item.get("sha256") or item.get("digest")
            raw = ctx.read_any(item["path"])
            actual = _sha256(raw) if raw is not None else None
            if expected and actual != expected:
                fresh = False
                ctx.issue("stale", codec.ReasonCode.INPUT_STALE, codec.Stage.TARGET, entity,
                          {"path": item["path"], "digest": expected},
                          {"path": item["path"], "digest": actual}, locator,
                          blocking=False, subject=subject)
    return fresh


def _load_catalog_chain(ctx: _Context, scope_filter: str | None) -> dict[str, Any]:
    chain: dict[str, Any] = {"present": False, "status": "absent", "scopes": [], "policy": None,
                             "policy_valid": False, "origins": None, "plans": {}, "bindings": {},
                             "task_index": [], "all_scope_ids": []}
    raw = ctx.reader.read(CATALOG_PATH)
    if raw is None:
        return chain
    chain["present"] = True

    def block() -> dict[str, Any]:
        chain["status"] = "blocked"
        return chain

    catalog = _strict_parse(ctx, raw, CATALOG_PATH)
    if catalog is _CORRUPT:
        return block()
    if not isinstance(catalog, dict) or catalog.get("schema_version") != RECORD_SCHEMAS["catalog"]:
        ctx.issue("blocked", codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, CATALOG_PATH,
                  RECORD_SCHEMAS["catalog"],
                  catalog.get("schema_version") if isinstance(catalog, dict) else type(catalog).__name__,
                  CATALOG_PATH)
        return block()
    heads = catalog.get("scope_heads")
    if not isinstance(heads, list):
        ctx.issue("blocked", codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, CATALOG_PATH,
                  "scope_heads list", type(heads).__name__, CATALOG_PATH + "#/scope_heads")
        return block()
    valid_catalog = _validate_record(ctx, raw, CATALOG_PATH, _id(catalog.get("catalog_id")))
    ctx.records[CATALOG_PATH] = {"path": CATALOG_PATH, "kind": "catalog",
                                 "status": "valid" if valid_catalog else "blocked",
                                 "digest": _sha256(raw), "schema_validated": valid_catalog,
                                 "entity_id": _id(catalog.get("catalog_id")), "revision": catalog.get("revision"),
                                 "referenced_by": None}
    if not valid_catalog:
        return block()
    chain["status"] = "valid"
    chain["revision"] = catalog.get("revision")
    chain["task_index"] = [row for row in _as_list(catalog.get("task_index")) if isinstance(row, dict)]
    if catalog.get("policy_ref") is not None:
        chain["policy"] = _resolve_ref(ctx, catalog.get("policy_ref"), "policy", CATALOG_PATH, "/policy_ref")
        chain["policy_valid"] = chain["policy"] is not None
        if chain["policy"] is None:
            chain["status"] = "blocked"
    if catalog.get("origins_ref") is not None:
        chain["origins"] = _resolve_ref(ctx, catalog.get("origins_ref"), "origins", CATALOG_PATH, "/origins_ref")
        if chain["origins"] is None:
            chain["status"] = "blocked"
    for index, head in enumerate(heads):
        pointer = f"/scope_heads/{index}"
        if not isinstance(head, dict) or _id(head.get("scope_id")) is None:
            ctx.issue("blocked", codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, CATALOG_PATH,
                      "scope head object with scope_id", type(head).__name__, CATALOG_PATH + "#" + pointer)
            chain["status"] = "blocked"
            continue
        scope_id = _id(head.get("scope_id"))
        chain["all_scope_ids"].append(scope_id)
        if scope_filter is not None and scope_id != scope_filter:
            continue
        scope = {"scope_id": scope_id, "status": "valid", "plans": [], "bindings": [], "receipt": None,
                 "plan_ids": []}
        receipt = None
        if head.get("receipt_ref") is not None:
            receipt = _resolve_ref(ctx, head.get("receipt_ref"), "commit", CATALOG_PATH, pointer + "/receipt_ref")
            receipt_ref = head.get("receipt_ref")
            scope["receipt"] = receipt_ref.get("path") if isinstance(receipt_ref, dict) else None
            if receipt is None:
                scope["status"] = "blocked"
        else:
            scope["status"] = "blocked"
            ctx.issue("blocked", codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING, codec.Stage.REFERENCE, scope_id,
                      "committed receipt_ref for scope head", None, CATALOG_PATH + "#" + pointer)
        for list_name in ("plan_refs", "binding_refs"):
            if not isinstance(head.get(list_name, []), list):
                scope["status"] = "blocked"
                ctx.issue("blocked", codec.ReasonCode.INVALID_TYPE, codec.Stage.SCHEMA, scope_id,
                          f"{list_name} list", type(head.get(list_name)).__name__,
                          CATALOG_PATH + f"#{pointer}/{list_name}")
        for p_index, ref in enumerate(_as_list(head.get("plan_refs"))):
            plan = _resolve_ref(ctx, ref, "plan", CATALOG_PATH, f"{pointer}/plan_refs/{p_index}")
            path = ref.get("path") if isinstance(ref, dict) else None
            scope["plans"].append(path)
            if plan is None:
                scope["status"] = "blocked"
                continue
            scope["plan_ids"].append(_id(plan.get("plan_id")))
            chain["plans"][path] = {"plan": plan, "scope_id": scope_id, "path": path,
                                    "scope_blocked": receipt is None}
        for b_index, ref in enumerate(_as_list(head.get("binding_refs"))):
            binding = _resolve_ref(ctx, ref, "binding", CATALOG_PATH, f"{pointer}/binding_refs/{b_index}")
            path = ref.get("path") if isinstance(ref, dict) else None
            scope["bindings"].append(path)
            if binding is None:
                scope["status"] = "blocked"
                continue
            plan_ref = binding.get("plan_ref")
            if plan_ref is not None and _resolve_ref(ctx, plan_ref, "plan", path, "/plan_ref") is None:
                scope["status"] = "blocked"
            chain["bindings"][path] = {"binding": binding, "scope_id": scope_id, "path": path}
        chain["scopes"].append(scope)
    if scope_filter is not None and not chain["scopes"]:
        chain["scope_found"] = False
    if any(scope["status"] == "blocked" for scope in chain["scopes"]):
        chain["status"] = "blocked"
    return chain


# ---------------------------------------------------------------------------
# Local recovery, pending journals and Chapter 6 reopen markers
# ---------------------------------------------------------------------------

def _pending_operations(ctx: _Context) -> list[dict[str, Any]]:
    """Scan the real pending locations (bounded, never a recursive rglob)."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    def flag(rel: str, reason: str, *, doc: Any = None, damaged: dict[str, Any] | None = None) -> None:
        if rel in seen:
            return
        seen.add(rel)
        if damaged is not None:
            result.append({"path": rel, "status": "blocked", "pending_status": "damaged",
                           "resume_ref": rel, "diagnostic": damaged["diagnostic"]})
            return
        doc = doc if isinstance(doc, dict) else {}
        operation = _id(doc.get("operation_id")) or _id(doc.get("run_id"))
        resume_ref = _id(doc.get("resume_ref")) or _id(doc.get("journal_path")) or rel
        entry = ctx.issue("blocked", codec.ReasonCode.PENDING, codec.Stage.TARGET, operation or rel,
                          "resolved pending operation or journal", reason, rel, resume_ref=resume_ref)
        result.append({"path": rel, "status": "blocked", "operation_id": operation, "pending_status": reason,
                       "resume_ref": resume_ref, "diagnostic": entry["diagnostic"]})

    def check(rel: str, *, require_status: bool, local: bool = False) -> None:
        reader = ctx.local if local else ctx.logs
        raw = reader.read(rel)
        if raw is None:
            return
        doc = _strict_parse(ctx, raw, rel)
        if doc is _CORRUPT or not isinstance(doc, dict):
            if doc is not _CORRUPT:
                ctx.issue("blocked", codec.ReasonCode.INVALID_TYPE, codec.Stage.DECODE, rel,
                          "pending journal JSON object", type(doc).__name__, rel)
            flag(rel, "damaged", damaged=ctx.issues[-1])
            return
        state = doc.get("status", doc.get("state", doc.get("phase")))
        if state is None:
            if require_status:
                flag(rel, "status_missing", doc=doc)
            return
        normalized = str(state).strip().lower()
        if normalized not in TERMINAL_JOURNAL_STATES:
            flag(rel, normalized or "pending", doc=doc)

    files, _dirs = ctx.logs.children(OPERATIONS_STORE)
    for name in files:
        if name.endswith(".json"):
            check(f"{OPERATIONS_STORE}/{name}", require_status=False)
    _files, op_dirs = ctx.logs.children(f"{OPERATIONS_STORE}/operations")
    for directory in op_dirs:
        files, _sub = ctx.logs.children(f"{OPERATIONS_STORE}/operations/{directory}")
        for name in files:
            if name.endswith(".json"):
                check(f"{OPERATIONS_STORE}/operations/{directory}/{name}", require_status=False)
    for marker in PENDING_MARKERS:
        if ctx.local.exists(marker):
            raw = ctx.local.read(marker)
            doc = _strict_parse(ctx, raw, marker)
            if doc is _CORRUPT or not isinstance(doc, dict):
                if doc is not _CORRUPT:
                    ctx.issue("blocked", codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.DECODE, marker,
                              "original Capability pending marker object", type(doc).__name__, marker)
                flag(marker, "damaged", damaged=ctx.issues[-1])
            else:
                flag(marker, "capability_apply_pending", doc=doc)
        elif os.path.lexists(ctx.root.joinpath(*marker.split("/"))):
            ctx.issue("blocked", codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, marker,
                      "regular pending marker file", "non-regular or unsafe marker", marker)
            flag(marker, "damaged", damaged=ctx.issues[-1])
    for base in LEGACY_PLANNING_DIRS:
        _files, dirs = ctx.logs.children(base)
        for directory in dirs:
            check(f"{base}/{directory}/apply-journal.json", require_status=True)
    for base in BOUNDED_JOURNAL_DIRS:
        level1, dirs = ctx.logs.children(base)
        candidates = [f"{base}/{name}" for name in level1]
        for directory in dirs:
            names, _sub = ctx.logs.children(f"{base}/{directory}")
            candidates.extend(f"{base}/{directory}/{name}" for name in names)
        for rel in candidates:
            name = rel.rsplit("/", 1)[-1]
            if not name.endswith(".json"):
                continue
            if name.endswith(".pending.json"):
                doc = _strict_parse(ctx, ctx.logs.read(rel), rel)
                if doc is _CORRUPT:
                    flag(rel, "damaged", damaged=ctx.issues[-1])
                else:
                    flag(rel, "public_sync_pending", doc=doc)
            elif "journal" in name:
                check(rel, require_status=False)
    return result


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


def _valid_registry(doc: Any) -> bool:
    return (isinstance(doc, dict) and doc.get("schema_version") == RECOVERY_SCHEMA
            and type(doc.get("epoch")) is int and doc["epoch"] >= 0
            and isinstance(doc.get("entries"), list) and isinstance(doc.get("revoked"), list))


def _read_outside(path: Path) -> bytes | None:
    try:
        inventory.no_reparse(path)
    except ValueError:
        raise
    if not path.is_file():
        return None
    return path.read_bytes()


def _local_recovery(ctx: _Context) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status: dict[str, Any] = {"current_epoch": None, "revoked_transactions": 0, "active_entries": 0,
                              "jobs": [], "status": "valid"}
    clears: list[dict[str, Any]] = []
    try:
        from _mvg_capability_recovery import store_root
        store = store_root(ctx.root)
    except (ValueError, OSError, ImportError) as exc:  # pragma: no cover - defensive dependency boundary
        entry = ctx.issue("blocked", codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.TARGET,
                          "mvg-recovery-registry", "readable local recovery store", str(exc)[:200],
                          RECOVERY_DIR + "/registry.json")
        status.update(status="blocked", diagnostic=entry["diagnostic"])
        return status, clears
    registry_locator = RECOVERY_DIR + "/registry.json"

    def blocked(code: codec.ReasonCode, locator: str, expected: Any, actual: Any) -> dict[str, Any]:
        entry = ctx.issue("blocked", code, codec.Stage.SCHEMA, locator, expected, actual, locator)
        status.update(status="blocked", diagnostic=entry["diagnostic"])
        return entry

    value: dict[str, Any] = {"schema_version": RECOVERY_SCHEMA, "epoch": 0, "entries": [], "revoked": []}
    try:
        raw = _read_outside(store / "registry.json")
    except (ValueError, OSError) as exc:
        blocked(codec.ReasonCode.UNSAFE_PATH, registry_locator, "regular readable registry.json", str(exc)[:200])
        raw = None
    if raw is not None:
        doc = _strict_parse(ctx, raw, registry_locator)
        if doc is _CORRUPT:
            status.update(status="blocked", diagnostic=ctx.issues[-1]["diagnostic"])
        elif not _valid_registry(doc):
            blocked(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, registry_locator,
                    {"schema_version": RECOVERY_SCHEMA, "epoch": "int>=0", "entries": "list", "revoked": "list"},
                    sorted(doc) if isinstance(doc, dict) else type(doc).__name__)
        else:
            value = doc
    epoch = value["epoch"] if status["status"] == "valid" else None
    revoked = {str(item) for item in value.get("revoked", []) if type(item) is str}
    entry_tids: set[str] = set()
    _transaction_ids(value.get("entries"), entry_tids)
    archived: set[str] = set()
    clears_dir = store / "clears"
    try:
        clear_paths = sorted(clears_dir.glob("epoch-*.json"))[:MAX_SCAN_FILES] if clears_dir.is_dir() else []
    except OSError:
        clear_paths = []
    for path in clear_paths:
        locator = f"{RECOVERY_DIR}/clears/{path.name}"
        try:
            raw = _read_outside(path)
        except (ValueError, OSError) as exc:
            blocked(codec.ReasonCode.UNSAFE_PATH, locator, "regular readable clear audit", str(exc)[:200])
            continue
        if raw is None:
            continue
        doc = _strict_parse(ctx, raw, locator)
        if doc is _CORRUPT:
            status.update(status="blocked", diagnostic=ctx.issues[-1]["diagnostic"])
            clears.append({"path": path.name, "sha256": _sha256(raw), "status": "corrupt"})
            continue
        if not _valid_registry(doc):
            blocked(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, locator, "archived recovery registry",
                    sorted(doc) if isinstance(doc, dict) else type(doc).__name__)
            clears.append({"path": path.name, "sha256": _sha256(raw), "status": "invalid"})
            continue
        tids: set[str] = set()
        _transaction_ids(doc, tids)
        archived |= tids
        clears.append({"path": path.name, "sha256": _sha256(raw), "archived_epoch": doc.get("epoch"),
                       "archived_transactions": len(tids), "status": "intact_audit"})
    status.update(current_epoch=epoch, revoked_transactions=len(revoked), archived_transactions=len(archived),
                  active_entries=len(_as_list(value.get("entries"))),
                  revoked_active_entries=sorted(entry_tids & revoked)[:50])
    if entry_tids & revoked:
        ctx.issue("revoked", codec.ReasonCode.CONFLICT, codec.Stage.TARGET, "mvg-recovery-registry",
                  "no completed entry for a revoked transaction", sorted(entry_tids & revoked)[:20],
                  registry_locator, blocking=False, subject={"kind": "local_registry", "id": "registry"})

    job_ids: list[tuple[str, str]] = []
    for name in ctx.logs.children(KNOWLEDGE_PLANNING_DIR, limit=200)[0]:
        if not name.endswith(".json"):
            continue
        rel = f"{KNOWLEDGE_PLANNING_DIR}/{name}"
        pointer = _strict_parse(ctx, ctx.logs.read(rel), rel, blocking=False, status="invalid_evidence")
        job_id = _id(pointer.get("job_id")) if isinstance(pointer, dict) else None
        if job_id is not None and _FILTER_RE.fullmatch(job_id):
            job_ids.append((job_id, rel))
    for directory in ctx.logs.children(KNOWLEDGE_PLANNING_DIR, limit=200)[1]:
        if directory.startswith("planning-") and _FILTER_RE.fullmatch(directory):
            job_ids.append((directory, f"{KNOWLEDGE_PLANNING_DIR}/{directory}/job.json"))
    seen: set[str] = set()
    for job_id, locator in job_ids:
        if job_id in seen:
            continue
        seen.add(job_id)
        job_rel = f"{KNOWLEDGE_PLANNING_DIR}/{job_id}/job.json"
        job = _strict_parse(ctx, ctx.logs.read(job_rel), job_rel, blocking=False, status="invalid_evidence")
        if not isinstance(job, dict):
            continue
        job_epoch = job.get("mvg_epoch", 0) if job.get("action") == "mvg" else job.get("mvg_epoch")
        run_rel = f"{MVG_PLANNING_DIR}/{job_id}/run.json"
        run_state = _strict_parse(ctx, ctx.logs.read(run_rel), run_rel, blocking=False, status="invalid_evidence")
        tids: set[str] = set()
        if isinstance(run_state, dict):
            selection = run_state.get("capability_selection")
            _transaction_ids(selection.get("selected") if isinstance(selection, dict) else None, tids)
            recovery = run_state.get("recovery") if isinstance(run_state.get("recovery"), dict) else {}
            if type(recovery.get("epoch")) is int:
                job_epoch = recovery["epoch"]
        reasons = []
        if epoch is None:
            reasons.append("registry_unverifiable")
        elif job_epoch is not None and job_epoch != epoch:
            reasons.append("epoch_invalidated")
        if tids & revoked:
            reasons.append("transaction_revoked")
        if tids & archived:
            reasons.append("transaction_archived_by_clear")
        item = {"job_id": job_id, "action": job.get("action"), "job_status": job.get("status"),
                "job_epoch": job_epoch, "original_locator": locator}
        if reasons:
            entry = ctx.issue("revoked", codec.ReasonCode.CONFLICT, codec.Stage.TARGET, job_id,
                              {"epoch": epoch, "transactions": "not revoked or archived"},
                              {"epoch": job_epoch, "reasons": reasons}, locator, blocking=False,
                              subject={"kind": "local_job", "id": job_id})
            item.update(local_status="revoked", reasons=reasons, recoverable=False,
                        diagnostic=entry["diagnostic"])
        else:
            active = str(job.get("status")) in PARTIAL_JOB_STATUSES
            item.update(local_status="active" if active else "local_only", recoverable=active)
        status["jobs"].append(item)
    return status, clears


def _reopen_markers(ctx: _Context) -> dict[str, Any]:
    """Persistent reopen/revocation markers, aligned with Chapter 6 recovery parsing."""
    result: dict[str, Any] = {"tasks": {}, "plans": {}, "scopes": {}, "global": [], "damaged": []}
    paths = ctx.logs.list(REOPEN_ROOT, "*.json") + ctx.logs.list(REOPEN_ROOT, "*/*.json")
    for rel in sorted(set(paths)):
        doc = _strict_parse(ctx, ctx.logs.read(rel), rel)
        if doc is _CORRUPT or not isinstance(doc, dict):
            if doc is not _CORRUPT:
                ctx.issue("blocked", codec.ReasonCode.CONFLICT, codec.Stage.DECODE, rel,
                          "valid reopen/revocation record JSON object", type(doc).__name__, rel)
            result["damaged"].append({"path": rel, "diagnostic": ctx.issues[-1]["diagnostic"]})
            continue
        state = str(doc.get("status") or "").strip().lower()
        revoking = (doc.get("revoked") is True or doc.get("reopened") is True or doc.get("superseded") is True
                    or doc.get("epoch_revoked") is True
                    or state in {"revoked", "reopened", "invalidated", "active"})
        if not revoking:
            continue
        tasks = set(_ids(doc.get("task_ids")))
        plans = set(_ids(doc.get("plan_ids")))
        scopes = set(_ids(doc.get("scope_ids")))
        for key, sink in (("task_id", tasks), ("plan_id", plans), ("scope_id", scopes)):
            if _id(doc.get(key)) is not None:
                sink.add(_id(doc.get(key)))
        code = codec.ReasonCode.INPUT_STALE if doc.get("epoch_revoked") is True else codec.ReasonCode.CONFLICT
        marker = {"path": rel, "status": state or "revoked", "resume_ref": _id(doc.get("resume_ref")) or rel,
                  "reason_code": code.value, "epoch": doc.get("epoch")}
        if doc.get("global") is True or not (tasks or plans or scopes):
            result["global"].append(marker)
        for key, ids in (("tasks", tasks), ("plans", plans), ("scopes", scopes)):
            for ident in ids:
                result[key].setdefault(ident, []).append(marker)
    return result


def _planning_progress(ctx: _Context, recovery: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {"partial": False, "mvg": None, "capability_jobs": [], "registry_active_entries": 0}
    try:
        from _project_health_planning import mvg_progress
        progress = mvg_progress(ctx.root)
    except Exception as exc:
        progress = {"available": False, "reason": str(exc)[:200]}
    mvg = {key: progress.get(key) for key in ("epoch", "completed", "total", "status", "job_status",
                                               "manifest", "reason", "runtime_verified") if key in progress}
    info["mvg"] = mvg
    total = progress.get("total") if type(progress.get("total")) is int else 0
    completed = progress.get("completed") if type(progress.get("completed")) is int else 0
    job_status = str(progress.get("job_status") or "").lower()
    if (total > 0 and completed < total) or job_status in PARTIAL_JOB_STATUSES:
        info["partial"] = True
    active_entries = recovery.get("active_entries") if type(recovery.get("active_entries")) is int else 0
    info["registry_active_entries"] = active_entries
    if active_entries > 0 and not (total > 0 and completed >= total):
        info["partial"] = True
    rel = f"{KNOWLEDGE_PLANNING_DIR}/capability-attempt.json"
    pointer = _strict_parse(ctx, ctx.logs.read(rel), rel, blocking=False, status="invalid_evidence")
    job_id = _id(pointer.get("job_id")) if isinstance(pointer, dict) else None
    if job_id is not None and _FILTER_RE.fullmatch(job_id):
        job_rel = f"{KNOWLEDGE_PLANNING_DIR}/{job_id}/job.json"
        job = _strict_parse(ctx, ctx.logs.read(job_rel), job_rel, blocking=False, status="invalid_evidence")
        if isinstance(job, dict):
            state = str(job.get("status") or "").lower()
            info["capability_jobs"].append({"job_id": job_id, "status": state})
            if state in PARTIAL_JOB_STATUSES:
                info["partial"] = True
    return info


# ---------------------------------------------------------------------------
# Runtime evidence backlinks
# ---------------------------------------------------------------------------

def verify_receipt_seal(receipt: Any) -> bool:
    """Story 4.3/4.4 coverage-receipt.json canonical receipt_id seal."""
    try:
        from _b_route_evidence_reuse import verify_receipt_seal as verify
    except Exception:  # pragma: no cover - fall back to the identical canonical seal
        if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
            return False
        expected = receipt.get("receipt_id")
        body = {k: v for k, v in receipt.items() if k not in {"receipt_id", "generated_at", "finished_at"}}
        return isinstance(expected, str) and bool(expected) and codec.canonical_digest(body) == expected
    return bool(verify(receipt))


def _receipt_levels(receipt: Any) -> list[str]:
    levels: set[str] = set()
    if isinstance(receipt, dict):
        tiers = receipt.get("evidence_tiers")
        if isinstance(tiers, dict):
            for name, bucket in tiers.items():
                if isinstance(bucket, dict) and type(bucket.get("passed")) is int and bucket["passed"] > 0:
                    levels.add(normalize_evidence_level(name))
        for item in _as_list(receipt.get("executed_tests")):
            if isinstance(item, dict) and item.get("status") == "passed":
                levels.add(normalize_evidence_level(item.get("evidence_level")))
        for name in _as_list(receipt.get("evidence_levels")):
            levels.add(normalize_evidence_level(name))
    levels.discard("unverified")
    return sorted(levels, key=EVIDENCE_LEVELS.index)


def _receipt_scope_kind(receipt: dict[str, Any]) -> str:
    verified = str(receipt.get("verified_scope") or "").strip().lower()
    strategy = str(receipt.get("execution_strategy_used") or receipt.get("execution_strategy") or "").strip().lower()
    if verified in CUMULATIVE_SCOPES:
        return "cumulative" if not _as_list(receipt.get("not_run")) else "scoped"
    if verified in SCOPED_SCOPES or strategy in SCOPED_SCOPES or _as_list(receipt.get("not_run")):
        return "scoped"
    if strategy in CUMULATIVE_SCOPES:
        return "cumulative"
    return "scoped"


def _load_receipt(ctx: _Context, rel: str) -> tuple[str, Any, bytes | None]:
    """Return (state, receipt, raw) where state is absent|valid|invalid; invalid emits a diagnostic."""
    raw = ctx.logs.read(rel)
    if raw is None:
        return "absent", None, None
    receipt = _strict_parse(ctx, raw, rel, blocking=False, status="invalid_evidence",
                            subject={"kind": "runtime_receipt", "id": rel})
    if receipt is _CORRUPT:
        return "invalid", None, raw
    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        ctx.issue("invalid_evidence", codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, rel, RECEIPT_SCHEMA,
                  receipt.get("schema_version") if isinstance(receipt, dict) else type(receipt).__name__, rel,
                  blocking=False, subject={"kind": "runtime_receipt", "id": rel})
        return "invalid", None, raw
    if not verify_receipt_seal(receipt):
        ctx.issue("invalid_evidence", codec.ReasonCode.DIGEST_MISMATCH, codec.Stage.CONTENT, rel,
                  "sealed coverage-receipt.json receipt_id", receipt.get("receipt_id"), rel,
                  blocking=False, subject={"kind": "runtime_receipt", "id": rel})
        return "invalid", None, raw
    return "valid", receipt, raw


def _runtime_backlinks(ctx: _Context) -> list[dict[str, Any]]:
    backlinks: list[dict[str, Any]] = []
    run_dirs = [d for d in ctx.logs.children(MVG_ACCEPTANCE_DIR, limit=100000)[1]]
    run_dirs = sorted(run_dirs, reverse=True)[:MAX_RUNTIME_RUNS]
    for run in run_dirs:
        rel = f"{MVG_ACCEPTANCE_DIR}/{run}/summary.json"
        raw = ctx.logs.read(rel)
        if raw is None:
            continue
        summary = _strict_parse(ctx, raw, rel, blocking=False, status="invalid_evidence",
                                subject={"kind": "runtime_summary", "id": rel})
        if not isinstance(summary, dict):
            backlinks.append({"kind": "mvg_summary", "path": rel, "sha256": _sha256(raw),
                              "status": "unreadable", "runtime_verified": False, "credited": False})
            continue
        receipt_rel = f"{MVG_ACCEPTANCE_DIR}/{run}/coverage-receipt.json"
        receipt_state, receipt, receipt_raw = _load_receipt(ctx, receipt_rel)
        fixture = bool(summary.get("protocol_fixture_only") is True
                       or ((receipt or {}).get("environment") or {}).get("protocol_fixture_only") is True)
        coverage = summary.get("coverage")
        link = {
            "kind": "mvg_summary", "path": rel, "sha256": _sha256(raw),
            "run_id": summary.get("run_id"), "source_revision": summary.get("source_revision"),
            "snapshot_digest": summary.get("snapshot_digest"),
            "original_executed_at": summary.get("original_executed_at") or summary.get("finished_at"),
            "runtime_verified": summary.get("runtime_verified") is True and not fixture,
            "evidence_levels": _receipt_levels(receipt) if receipt else [],
            "manifest": summary.get("manifest"), "manifest_sha256": summary.get("manifest_sha256"),
            "status": summary.get("status"), "mode": summary.get("mode"),
            "protocol_fixture_only": fixture,
            "coverage_mode": coverage.get("mode") if isinstance(coverage, dict) else summary.get("coverage_mode"),
            "workspace_dirty": bool(summary.get("workspace_dirty")), "credited": False,
            "receipt_state": receipt_state,
        }
        if receipt_state != "absent":
            link["coverage_receipt"] = {
                "kind": "coverage_receipt", "path": receipt_rel,
                "sha256": _sha256(receipt_raw) if receipt_raw is not None else None,
                "status": receipt_state,
            }
        if receipt is not None:
            link["coverage_receipt"].update({
                "run_id": receipt.get("run_id"), "source_revision": receipt.get("source_revision"),
                "snapshot_digest": receipt.get("snapshot_digest"), "receipt_id": receipt.get("receipt_id"),
                "original_executed_at": receipt.get("original_executed_at") or receipt.get("finished_at"),
                "runtime_verified": receipt.get("runtime_verified") is True and not fixture,
                "evidence_levels": _receipt_levels(receipt), "scope_id": receipt.get("scope_id"),
                "scope_kind": _receipt_scope_kind(receipt),
            })
            ctx.values["receipt:" + rel] = receipt
        backlinks.append(link)
    for name, kind in (("latest.json", "runtime_latest"), ("workspace-latest.json", "runtime_workspace_latest")):
        rel = f"{RUNTIME_DIR}/{name}"
        raw = ctx.logs.read(rel)
        if raw is None:
            continue
        doc = _strict_parse(ctx, raw, rel, blocking=False, status="invalid_evidence",
                            subject={"kind": "runtime_index", "id": rel})
        if not isinstance(doc, dict):
            backlinks.append({"kind": kind, "path": rel, "sha256": _sha256(raw), "status": "unreadable",
                              "runtime_verified": False, "credited": False})
            continue
        rows = []
        for row in _as_list(doc.get("tasks")):
            if not isinstance(row, dict) or _id(row.get("task_id")) is None:
                continue
            rows.append({"task_id": _id(row.get("task_id")), "status": row.get("status"),
                         "source_revision": row.get("source_revision"),
                         "original_executed_at": row.get("finished_at"),
                         "verification_mode": row.get("verification_mode", "main"),
                         "integrity": _runtime_row_integrity(ctx, row),
                         "evidence_level": _runtime_row_level(ctx, row)})
        backlinks.append({
            "kind": kind, "path": rel, "sha256": _sha256(raw), "run_id": doc.get("run_id"),
            "source_revision": doc.get("source_revision"), "snapshot_digest": doc.get("snapshot_digest"),
            "original_executed_at": doc.get("finished_at") or doc.get("original_executed_at"),
            "runtime_verified": False, "evidence_levels": [],
            "verification_mode": doc.get("verification_mode", "main" if kind == "runtime_latest" else "workspace"),
            "tasks": rows, "credited": False,
        })
    return backlinks


def _runtime_row_integrity(ctx: _Context, row: dict[str, Any]) -> bool:
    """Mirror project_health_knowledge.apply_runtime_results row integrity rules."""
    required = {"task_id", "source_revision", "test_refs", "scenes", "status", "started_at", "finished_at",
                "evidence_path"}
    if not required <= set(row) or row.get("verification_mode", "main") != "main":
        return False
    refs = row.get("test_refs")
    if not isinstance(refs, list) or not refs:
        return False
    for ref in refs:
        if type(ref) is not str or not _GODOT_TEST_RE.fullmatch(ref) or ".." in PurePosixPath(ref).parts:
            return False
    evidence_path = row.get("evidence_path")
    if type(evidence_path) is not str or not evidence_path.startswith(RUNTIME_DIR + "/"):
        return False
    evidence = _strict_parse(ctx, ctx.logs.read(evidence_path), evidence_path, blocking=False,
                             status="invalid_evidence")
    return isinstance(evidence, dict) and evidence == row


def _runtime_row_level(ctx: _Context, row: dict[str, Any]) -> str:
    """real_engine_input only when attested by a sealed receipt; else scene_method for verified GdUnit."""
    receipt_rel = row.get("coverage_receipt_path")
    if type(receipt_rel) is str and receipt_rel.startswith("logs/"):
        state, receipt, _raw = _load_receipt(ctx, receipt_rel)
        if state == "valid" and receipt.get("runtime_verified") is True \
                and "real_engine_input" in _receipt_levels(receipt):
            return "real_engine_input"
    refs = row.get("test_refs")
    if isinstance(refs, list) and refs and all(type(r) is str and _GODOT_TEST_RE.fullmatch(r) for r in refs):
        return "scene_method"
    return "unverified"


# ---------------------------------------------------------------------------
# Layer construction
# ---------------------------------------------------------------------------

def _node(kind: str, node_id: str, **extra: Any) -> dict[str, Any]:
    node = {
        "kind": kind, "id": node_id,
        "planning_state": "legacy_unmapped",
        "implementation_state": "no_task_yet",
        "runtime_state": "unverified",
        "evidence_level": "unverified",
        "evidence_levels": [],
        "original_locator": None,
        "diagnostics": [],
    }
    node.update(extra)
    return node


def _rows(document: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(document, dict) and isinstance(document.get(key), list):
        return [row for row in document[key] if isinstance(row, dict)]
    return []


def _task_rows(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, dict):
        master = document.get("master")
        if isinstance(master, dict) and isinstance(master.get("tasks"), list):
            return [row for row in master["tasks"] if isinstance(row, dict)]
        if isinstance(document.get("tasks"), list):
            return [row for row in document["tasks"] if isinstance(row, dict)]
    if isinstance(document, list):
        return [row for row in document if isinstance(row, dict)]
    return []


def _walk_strings(value: Any, sink: list[str], depth: int = 0) -> None:
    if depth > 12:
        return
    if type(value) is str:
        sink.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            _walk_strings(child, sink, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _walk_strings(child, sink, depth + 1)


def _resource_refs(value: Any) -> tuple[set[str], set[str]]:
    strings: list[str] = []
    _walk_strings(value, strings)
    contracts: set[str] = set()
    scenes: set[str] = set()
    for text in strings:
        contracts.update(match.group(0) for match in _CONTRACT_RE.finditer(text))
        scenes.update(match.group(1) for match in _SCENE_RE.finditer(text))
    return contracts, scenes


def _aggregate_implementation(states: list[str]) -> str:
    if not states:
        return "no_task_yet"
    if all(state == "done_in_taskmaster" for state in states):
        return "done_in_taskmaster"
    if any(state in ("in_progress", "done_in_taskmaster") for state in states):
        return "in_progress"
    return "pending"


def _binding_planning_state(stages: set[str]) -> str | None:
    if "5" in stages:
        return "stage5_bound"
    if "4" in stages:
        return "stage4_bound"
    if "3C" in stages:
        return "3c_compiled"
    return None


def _logical_four_part(flow: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_change": {"entry_condition": flow.get("entry_condition"), "success_end": flow.get("success_end"),
                         "state_owners": _as_list(flow.get("state_owners"))},
        "action_or_handoff": {"entry": flow.get("entry"), "handoffs": _as_list(flow.get("handoffs"))},
        "user_visible_feedback": {"observable_result": flow.get("observable_result") or flow.get("outcome")},
        "verification_entry": {"verification_targets": _as_list(flow.get("verification_targets"))
                               or _as_list(flow.get("test_ids"))},
    }


def _origin_tasks(chain: dict[str, Any]) -> set[str]:
    tasks: set[str] = set()
    origins = chain.get("origins") if isinstance(chain.get("origins"), dict) else None
    for key in ("tasks", "entries", "origins"):
        for row in _rows(origins, key):
            if _id(row.get("task_id")) is not None:
                tasks.add(_id(row.get("task_id")))
    for row in chain.get("task_index") or []:
        if _id(row.get("task_id")) is not None:
            tasks.add(_id(row.get("task_id")))
    return tasks


def _build_layers(ctx: _Context, chain: dict[str, Any], provenance: dict[str, Any],
                  backlinks: list[dict[str, Any]]) -> dict[str, Any]:
    layers: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "sources", "requirements", "capabilities", "flows", "four_parts", "tasks",
        "contracts", "scenes", "obligations")}
    edges: list[dict[str, str]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}

    def add(node: dict[str, Any]) -> dict[str, Any]:
        key = (node["kind"], node["id"])
        if key in index:
            return index[key]
        index[key] = node
        layers[{"source": "sources", "requirement": "requirements", "capability": "capabilities",
                "flow": "flows", "four_part": "four_parts", "task": "tasks", "contract": "contracts",
                "scene": "scenes", "obligation": "obligations"}[node["kind"]]].append(node)
        return node

    def edge(src: tuple[str, str], dst: tuple[str, str], relation: str) -> None:
        edges.append({"from": f"{src[0]}:{src[1]}", "to": f"{dst[0]}:{dst[1]}", "relation": relation})

    # Layer 1: sources (Chapter 3 source set + source blocks + plan source identity).
    source_set = _load_document(ctx, SOURCE_SET_PATH)
    source_digests: dict[str, set[str]] = {}

    def source_digest(path: str) -> set[str]:
        # Accept raw bytes and LF-normalized bytes so Windows CRLF checkouts of
        # an unchanged committed source are not misreported as stale.
        if path not in source_digests:
            raw = ctx.read_any(path)
            source_digests[path] = set() if raw is None else {
                hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        return source_digests[path]

    if isinstance(source_set, dict):
        strings: list[str] = []
        _walk_strings(source_set.get("sources", source_set), strings)
        for text in sorted({s for s in strings if s.endswith((".md", ".txt", ".json")) and "/" in s})[:200]:
            node = add(_node("source", text, source_path=text, original_locator=SOURCE_SET_PATH,
                             resource_exists=ctx.exists_any(text)))
            node["implementation_state"] = "not_applicable_non_flow"
    blocks_doc = _load_document(ctx, SOURCE_BLOCKS_PATH)
    for block in _rows(blocks_doc, "blocks"):
        block_id = _id(block.get("block_id"))
        if block_id is None:
            continue
        path = block.get("source_path")
        node = add(_node("source", block_id, source_path=path, original_locator=SOURCE_BLOCKS_PATH,
                         implementation_state="not_applicable_non_flow"))
        expected = str(block.get("source_sha256") or "").removeprefix("sha256:")
        if type(path) is str and expected:
            actual = source_digest(path)
            if expected not in actual:
                node["planning_state"] = "stale"
                entry = ctx.issue("stale", codec.ReasonCode.INPUT_STALE, codec.Stage.TARGET, block_id,
                                  {"path": path, "sha256": expected}, {"path": path, "sha256": sorted(actual) or None},
                                  SOURCE_BLOCKS_PATH, blocking=False, subject={"kind": "source", "id": block_id})
                node["diagnostics"].append(entry["diagnostic"])

    # Layer 2/3: topology requirements and capabilities.
    requirements_doc = None
    requirements_path = None
    for candidate in REQUIREMENT_PATHS:
        if ctx.exists_any(candidate):
            requirements_path = candidate
            requirements_doc = _load_document(ctx, candidate)
            break
    for row in _rows(requirements_doc, "requirements"):
        rid = _id(row.get("requirement_id")) or _id(row.get("id"))
        if rid is None:
            continue
        sink = row.get("sink_policy") if type(row.get("sink_policy")) is str else ""
        node = add(_node("requirement", rid, original_locator=requirements_path, statement=row.get("statement"),
                         sink_policy=sink or None))
        if sink in NON_FLOW_SINKS:
            node.update(planning_state="non_flow_governed", implementation_state="not_applicable_non_flow",
                        verification_destination={"sink_kind": sink})
        for block_id in _ids(row.get("source_block_ids")):
            edge(("source", block_id), ("requirement", rid), "projects_to")
        for cap in _ids(row.get("capability_ids")):
            edge(("requirement", rid), ("capability", cap), "grouped_by")
    capabilities_doc = _load_document(ctx, CAPABILITIES_PATH)
    for row in _rows(capabilities_doc, "capabilities"):
        cid = _id(row.get("capability_id"))
        if cid is None:
            continue
        add(_node("capability", cid, title=row.get("title"), original_locator=CAPABILITIES_PATH))
        for rid in _ids(row.get("requirement_ids")):
            edge(("requirement", rid), ("capability", cid), "grouped_by")
    edges_doc = _load_document(ctx, TOPOLOGY_EDGES_PATH)
    topology_edge_count = len(_rows(edges_doc, "edges"))

    # Layer 6 (read early): Taskmaster tasks and views.
    tasks_doc = _load_document(ctx, TASK_FILES[0])
    task_rows = _task_rows(tasks_doc)
    views: dict[str, set[str]] = {}
    for rel, view in ((TASK_FILES[1], "back"), (TASK_FILES[2], "gameplay")):
        for row in _task_rows(_load_document(ctx, rel)):
            tid = _id(row.get("taskmaster_id"))
            if tid is not None:
                views.setdefault(tid, set()).add(view)
    task_index: dict[str, dict[str, Any]] = {}
    for row in task_rows:
        tid = _id(row.get("id"))
        if tid is None:
            continue
        raw_status = str(row.get("status") or "pending").strip().lower() if type(row.get("status")) in (str, type(None)) \
            else "pending"
        node = add(_node("task", tid, title=row.get("title"), taskmaster_status=raw_status,
                         implementation_state=_TASKMASTER_STATUS.get(raw_status, "pending"),
                         views=sorted(views.get(tid, set())), original_locator=TASK_FILES[0] + f"#id={tid}",
                         local_qualification="not_evaluated", task_readiness_blocking=False,
                         dependencies=_ids(row.get("dependencies"))))
        task_index[tid] = {"node": node, "row": row}

    # B-route plans: requirements, flows, four-parts, non-Flow governance.
    task_bindings: dict[str, set[str]] = {}
    task_plans: dict[str, set[str]] = {}
    task_scopes: dict[str, set[str]] = {}
    flow_bindings: dict[str, set[str]] = {}
    flow_tasks: dict[str, set[str]] = {}
    requirement_tasks: dict[str, set[str]] = {}
    binding_obligations: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    implementation_objects: list[tuple[dict[str, Any], str]] = []
    stale_plans: set[str] = set()
    for path, info in sorted(chain["bindings"].items()):
        binding = info["binding"]
        stage = str(binding.get("stage") or "")
        plan_id = _id(binding.get("plan_id"))
        subject = {"kind": "binding", "id": path}
        owned = _as_list(binding.get("manifest_refs")) + _as_list(binding.get("other_verification_refs"))
        if not _check_freshness(ctx, owned, path, path, subject) and plan_id is not None:
            stale_plans.add(plan_id)
        for mapping in _as_list(binding.get("task_mappings")):
            tid = _id(mapping.get("task_id")) if isinstance(mapping, dict) else None
            if tid is None:
                continue
            task_bindings.setdefault(tid, set()).add(stage)
            if plan_id is not None:
                task_plans.setdefault(tid, set()).add(plan_id)
            task_scopes.setdefault(tid, set()).add(info["scope_id"])
            for fid in _ids(mapping.get("flow_ids")):
                flow_bindings.setdefault(fid, set()).add(stage)
                flow_tasks.setdefault(fid, set()).add(tid)
            for rid in _ids(mapping.get("requirement_ids")):
                requirement_tasks.setdefault(rid, set()).add(tid)
        for obligation in _as_list(binding.get("obligations")):
            if isinstance(obligation, dict):
                binding_obligations.append((obligation, binding, path))
        for obj in _as_list(binding.get("implementation_objects")):
            if isinstance(obj, dict):
                implementation_objects.append((obj, path))

    origin_tasks = _origin_tasks(chain)

    for path, info in sorted(chain["plans"].items()):
        plan = info["plan"]
        plan_id = _id(plan.get("plan_id")) or path
        subject = {"kind": "plan", "id": plan_id}
        source_identity = plan.get("source_identity") if isinstance(plan.get("source_identity"), dict) else {}
        owned = [source_identity.get("manifest_ref"), source_identity.get("ledger_ref")]
        owned += _as_list(plan.get("adoption_proof_refs")) + _as_list(plan.get("evidence_source_refs"))
        fresh = _check_freshness(ctx, owned, plan_id, path, subject) and plan_id not in stale_plans
        blocked = bool(info.get("scope_blocked"))
        for ref in owned:
            for item in _owned_files(ref):
                src = add(_node("source", item["path"], source_path=item["path"], original_locator=path,
                                implementation_state="not_applicable_non_flow",
                                planning_state="stale" if not fresh else "legacy_unmapped"))
                if src["planning_state"] != "stale" and fresh:
                    src["planning_state"] = "3b_adopted_awaiting_3c"
                src.setdefault("plan_id", plan_id)
        verification = {_id(row.get("requirement_id")): row for row in _as_list(plan.get("requirement_verification"))
                        if isinstance(row, dict) and _id(row.get("requirement_id")) is not None}
        applicability = {_id(row.get("requirement_id")): row for row in _as_list(plan.get("applicability"))
                         if isinstance(row, dict) and _id(row.get("requirement_id")) is not None}
        for row in _as_list(plan.get("requirements")):
            rid = _id(row.get("requirement_id")) if isinstance(row, dict) else None
            if rid is None:
                continue
            node = add(_node("requirement", rid))
            node.update(original_locator=f"{path}#/requirements/{rid}", plan_id=plan_id,
                        acceptance_intent=row.get("acceptance_intent"), scope_id=info["scope_id"])
            for block_id in _ids(row.get("source_block_ids")):
                edge(("source", block_id), ("requirement", rid), "projects_to")
            ver = verification.get(rid, {})
            app = applicability.get(rid, {})
            disposition = str(ver.get("disposition") or app.get("disposition") or "")
            other_refs = [ref for ref in _as_list(app.get("other_verification_refs")) if isinstance(ref, dict)]
            sinks = _ids(row.get("non_task_sinks"))
            if disposition in UNRESOLVED_DISPOSITIONS or (not disposition and not other_refs and not sinks
                                                          and not app.get("non_flow_reason")
                                                          and rid not in requirement_tasks
                                                          and not _flow_for(plan, rid)):
                entry = ctx.issue("blocked", codec.ReasonCode.UNRESOLVED_REFERENCE, codec.Stage.REFERENCE, rid,
                                  "resolved Flow or legal non-Flow verification destination",
                                  disposition or "unresolved", f"{path}#/requirement_verification/{rid}",
                                  subject={"kind": "requirement", "id": rid})
                node.update(planning_state="blocked", implementation_state="no_task_yet",
                            verification_destination={"disposition": disposition or "unresolved",
                                                      "rationale": ver.get("rationale") or app.get("rationale")},
                            task_readiness_blocking=False)
                node["diagnostics"].append(entry["diagnostic"])
                continue
            non_flow = (disposition in NON_FLOW_DISPOSITIONS or bool(app.get("non_flow_reason"))
                        or (disposition != "flow" and (other_refs or sinks)))
            if non_flow:
                destination = {
                    "disposition": disposition or "non_flow",
                    "other_verification_refs": [ref.get("ref") for ref in other_refs],
                    "sink_id": ver.get("sink_id"), "verification_ref": ver.get("verification_ref"),
                    "authority_ref": ver.get("authority_ref"), "non_task_sinks": sinks,
                    "non_flow_reason": app.get("non_flow_reason") or ver.get("rationale") or app.get("rationale"),
                }
                node.update(planning_state="non_flow_governed", implementation_state="not_applicable_non_flow",
                            verification_destination=destination, task_readiness_blocking=False)
                four = add(_node("four_part", f"requirement:{rid}", plan_id=plan_id,
                                 original_locator=f"{path}#/requirement_verification/{rid}",
                                 planning_state="non_flow_governed",
                                 implementation_state="not_applicable_non_flow",
                                 logical_four_part={
                                     "state_change": "not_applicable_non_flow",
                                     "action_or_handoff": "not_applicable_non_flow",
                                     "user_visible_feedback": "not_applicable_non_flow",
                                     "verification_entry": destination,
                                 }, verification_destination=destination, task_readiness_blocking=False))
                edge(("requirement", rid), ("four_part", four["id"]), "governed_by")
                if other_refs:
                    add(_node("obligation", f"other:{rid}", obligation_class="other_verification",
                              planning_state="non_flow_governed", implementation_state="not_applicable_non_flow",
                              verification_refs=destination["other_verification_refs"], plan_id=plan_id,
                              requirement_ids=[rid], original_locator=f"{path}#/applicability/{rid}"))
                    edge(("four_part", four["id"]), ("obligation", f"other:{rid}"), "verified_by")
            else:
                tasks_for = sorted(requirement_tasks.get(rid, set()))
                node["implementation_state"] = _aggregate_implementation(
                    [task_index[t]["node"]["implementation_state"] for t in tasks_for if t in task_index])
                node["planning_state"] = "3b_adopted_awaiting_3c" if not tasks_for else "3c_compiled"
                node["verification_destination"] = ({"flow_id": ver.get("flow_id")} if ver.get("flow_id")
                                                    else "awaiting_3c_task_compilation")
            if not fresh:
                node["planning_state"] = "stale"
            if blocked:
                node["planning_state"] = "blocked"
        definitions = plan.get("definitions") if isinstance(plan.get("definitions"), dict) else {}
        for cap in _as_list(definitions.get("capabilities")):
            cid = (_id(cap.get("capability_id")) or _id(cap.get("id"))) if isinstance(cap, dict) else None
            if cid is None:
                continue
            cnode = add(_node("capability", cid, title=cap.get("title")))
            cnode.update(plan_id=plan_id, original_locator=f"{path}#/definitions/capabilities/{cid}",
                         planning_state="3b_adopted_awaiting_3c" if fresh else "stale")
            for rid in _ids(cap.get("requirement_ids")):
                edge(("requirement", rid), ("capability", cid), "grouped_by")
        for flow in _as_list(definitions.get("flows")):
            fid = _id(flow.get("id")) if isinstance(flow, dict) else None
            if fid is None:
                continue
            stages = flow_bindings.get(fid, set())
            tasks_for = sorted(flow_tasks.get(fid, set()))
            fnode = add(_node("flow", fid))
            fnode.update(plan_id=plan_id, scope_id=info["scope_id"], original_locator=f"{path}#/definitions/flows/{fid}",
                         requirement_ids=_ids(flow.get("requirement_ids")), task_ids=tasks_for,
                         task_readiness_blocking=False, source="b_route_plan")
            bound = _binding_planning_state(stages)
            if bound:
                fnode["planning_state"] = bound
                fnode["implementation_state"] = _aggregate_implementation(
                    [task_index[t]["node"]["implementation_state"] for t in tasks_for if t in task_index])
                fnode["verification_destination"] = {"verification_targets": _as_list(flow.get("verification_targets"))}
            else:
                fnode.update(planning_state="3b_adopted_awaiting_3c", implementation_state="no_task_yet",
                             verification_destination="awaiting_3c_task_compilation")
            if not fresh:
                fnode["planning_state"] = "stale"
            if blocked:
                fnode["planning_state"] = "blocked"
            for rid in _ids(flow.get("requirement_ids")):
                edge(("requirement", rid), ("flow", fid), "realized_by")
                for cap_edge in [e for e in edges if e["from"] == f"requirement:{rid}" and e["relation"] == "grouped_by"]:
                    edges.append({"from": cap_edge["to"], "to": f"flow:{fid}", "relation": "delivered_by"})
            four = add(_node("four_part", f"flow:{fid}", plan_id=plan_id,
                             original_locator=f"{path}#/definitions/flows/{fid}",
                             logical_four_part=_logical_four_part(flow),
                             implementation_parts=[part.get("kind") for part in _as_list(flow.get("parts"))
                                                   if isinstance(part, dict)],
                             planning_state=fnode["planning_state"],
                             implementation_state=fnode["implementation_state"],
                             verification_destination=fnode.get("verification_destination"),
                             task_readiness_blocking=False))
            edge(("flow", fid), ("four_part", four["id"]), "defined_by")
            for tid in tasks_for:
                edge(("four_part", four["id"]), ("task", tid), "compiled_to")

    for tid, entry in task_index.items():
        node = entry["node"]
        bound = _binding_planning_state(task_bindings.get(tid, set()))
        if bound:
            node["planning_state"] = bound
        elif tid in origin_tasks:
            node["planning_state"] = "3c_compiled"
        node["governed"] = bool(bound or tid in origin_tasks)
        node["plan_ids"] = sorted(task_plans.get(tid, set()))
        node["scope_ids"] = sorted(task_scopes.get(tid, set()))
        if bound:
            node["local_qualification"] = "governed_by_chapter6_gate"
        for dep in node.get("dependencies") or []:
            edge(("task", tid), ("task", dep), "depends_on")

    # MVG manifests: flows, obligations, contracts and scenes.
    manifests: list[dict[str, Any]] = []
    for rel in ctx.reader.list(MVG_MANIFEST_DIR, "*.json"):
        raw = ctx.reader.read(rel)
        doc = _load_document(ctx, rel)
        if not isinstance(doc, dict):
            continue
        coverage = doc.get("coverage")
        manifest = {"path": rel, "sha256": _sha256(raw) if raw else None, "mvg_id": doc.get("mvg_id"),
                    "schema_version": doc.get("schema_version"),
                    "coverage_mode": coverage.get("mode") if isinstance(coverage, dict) else None,
                    "flow_ids": [], "planned_flow_ids": [], "flow_tests": {}, "status": "valid"}
        if doc.get("schema_version") != MVG_SCHEMA:
            manifest["status"] = "unsupported_schema"
            ctx.issue("invalid_evidence", codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, rel, MVG_SCHEMA,
                      doc.get("schema_version"), rel, blocking=False, subject={"kind": "manifest", "id": rel})
        tests = {_id(test.get("id")): test for test in _rows(doc, "tests") if _id(test.get("id")) is not None}
        for flow in _rows(doc, "flows"):
            fid = _id(flow.get("id"))
            if fid is None:
                continue
            planned = str(flow.get("status") or flow.get("state") or "").lower() == "planned"
            (manifest["planned_flow_ids"] if planned else manifest["flow_ids"]).append(fid)
            task_ids = _ids(flow.get("task_ids"))
            fnode = add(_node("flow", fid, source="mvg_manifest", original_locator=f"{rel}#/flows/{fid}",
                              task_ids=task_ids))
            fnode.setdefault("manifests", []).append(rel)
            if fnode.get("source") == "mvg_manifest":
                if planned:
                    fnode.update(planning_state="planned_future", implementation_state="planned_unimplemented",
                                 planned_only=True)
                else:
                    fnode["implementation_state"] = _aggregate_implementation(
                        [task_index[t]["node"]["implementation_state"] for t in task_ids if t in task_index])
                for tid in task_ids:
                    edge(("flow", fid), ("task", tid), "owned_by")
            required: list[str] = []
            for test_id in _ids(flow.get("test_ids")):
                test = tests.get(test_id, {})
                test_path = test.get("path")
                exists = bool(type(test_path) is str and ctx.exists_any(test_path))
                state = str(test.get("state") or "").lower()
                if planned or state == "planned":
                    klass = "out_of_scope_future"
                elif test.get("kind") == "manual" or normalize_evidence_level(test.get("evidence_level")) == "manual_independent":
                    klass = "manual_checks"
                else:
                    klass = "existing_required"
                    required.append(test_id)
                oid = f"{fid}:{test_id}"
                add(_node("obligation", oid, obligation_class=klass, flow_id=fid, test_id=test_id,
                          test_path=test_path, resource_exists=exists, planned_only=not exists,
                          declared_evidence_level=normalize_evidence_level(test.get("evidence_level")),
                          planning_state="planned_future" if klass == "out_of_scope_future" else fnode["planning_state"],
                          implementation_state="planned_unimplemented" if not exists else fnode["implementation_state"],
                          manifest=rel, original_locator=f"{rel}#/tests/{test_id}"))
                edge(("flow", fid), ("obligation", oid), "verified_by")
            manifest["flow_tests"][fid] = required
            contracts, scenes = _resource_refs({"source_paths": flow.get("source_paths"),
                                                "handoffs": flow.get("handoffs")})
            for path in sorted(contracts):
                edge(("flow", fid), ("contract", path), "uses_contract")
            for path in sorted(scenes):
                edge(("flow", fid), ("scene", path), "uses_scene")
        manifests.append(manifest)

    for obligation, binding, path in binding_obligations:
        oid = _id(obligation.get("id"))
        if oid is None:
            continue
        test_ids = _ids(obligation.get("test_ids"))
        known = {n["test_id"] for n in layers["obligations"] if n.get("test_id")}
        klass = "existing_required" if test_ids and all(t in known for t in test_ids) else "current_new"
        if obligation.get("verification_refs") and not test_ids:
            klass = "other_verification"
        onode = add(_node("obligation", f"binding:{oid}", obligation_class=klass, test_ids=test_ids,
                          requirement_ids=_ids(obligation.get("requirement_ids")),
                          flow_ids=_ids(obligation.get("flow_ids")), plan_id=_id(binding.get("plan_id")),
                          planning_state=_binding_planning_state({str(binding.get("stage"))}) or "3c_compiled",
                          implementation_state="pending", original_locator=f"{path}#/obligations/{oid}"))
        for fid in onode["flow_ids"]:
            edge(("flow", fid), ("obligation", onode["id"]), "verified_by")

    # Contracts and scenes from bindings, tasks and manifests.
    resource_owners: dict[tuple[str, str], set[str]] = {}
    resource_planned: set[tuple[str, str]] = set()
    for obj, path in implementation_objects:
        files = _owned_files(obj.get("target_ref"))
        refs = [item["path"] for item in files]
        contracts, scenes = _resource_refs(refs + [obj.get("expected_type") if type(obj.get("expected_type")) is str else ""])
        if obj.get("kind") == "scene":
            scenes.update(ref for ref in refs if ref.endswith(".tscn"))
        for kind, collection in (("contract", contracts), ("scene", scenes)):
            for ref in collection:
                key = (kind, ref)
                resource_owners.setdefault(key, set()).update(_ids(obj.get("responsible_task_ids")))
                if obj.get("availability") == "planned":
                    resource_planned.add(key)
    for tid, entry in task_index.items():
        contracts, scenes = _resource_refs(entry["row"])
        for kind, collection in (("contract", contracts), ("scene", scenes)):
            for ref in collection:
                resource_owners.setdefault((kind, ref), set()).add(tid)
    for item in list(edges):
        kind, _, ref = item["to"].partition(":")
        if kind in ("contract", "scene"):
            resource_owners.setdefault((kind, ref), set())
    for (kind, ref), owners in sorted(resource_owners.items()):
        exists = ctx.exists_any(ref)
        states = [task_index[t]["node"]["implementation_state"] for t in owners if t in task_index]
        add(_node(kind, ref, path=ref, resource_exists=exists, planned_only=not exists,
                  declared_planned=(kind, ref) in resource_planned, owner_task_ids=sorted(owners),
                  implementation_state=("planned_unimplemented" if not exists else _aggregate_implementation(states)),
                  planning_state="3c_compiled" if (kind, ref) in resource_planned else "legacy_unmapped"))
        for tid in sorted(owners):
            edge(("task", tid), (kind, ref), "implements")

    _credit_runtime(ctx, layers, manifests, backlinks, provenance, task_index)
    return {"layers": layers, "edges": edges, "manifests": manifests, "index": index,
            "topology_edge_count": topology_edge_count, "task_index": task_index}


def _flow_for(plan: dict[str, Any], rid: str) -> bool:
    definitions = plan.get("definitions") if isinstance(plan.get("definitions"), dict) else {}
    return any(isinstance(flow, dict) and rid in _ids(flow.get("requirement_ids"))
               for flow in _as_list(definitions.get("flows")))


_RANK = {"passed_cumulative_mvg": 6, "passed_flow_scope": 5, "passed_other_verification": 5, "workspace_only": 3,
         "failed": 2, "stale_revision": 1}


def _credit_runtime(ctx: _Context, layers: dict[str, list[dict[str, Any]]], manifests: list[dict[str, Any]],
                    backlinks: list[dict[str, Any]], provenance: dict[str, Any],
                    task_index: dict[str, dict[str, Any]]) -> None:
    """Runtime crediting from explicit backlinks: exact identity, sealed receipts, scoped attribution."""
    bound_revision = provenance.get("snapshot_commit")
    main_fact = bool(provenance.get("is_main_fact"))
    manifest_by_path = {m["path"]: m for m in manifests}
    flow_runtime: dict[str, tuple[str, list[str], str]] = {}
    other_runtime: dict[str, tuple[str, str]] = {}

    def offer(fid: str, state: str, levels: list[str], path: str) -> None:
        previous = flow_runtime.get(fid)
        if previous is None or _RANK[state] > _RANK[previous[0]]:
            flow_runtime[fid] = (state, levels, path)

    for link in backlinks:
        if link.get("kind") != "mvg_summary" or link.get("manifest") not in manifest_by_path:
            continue
        manifest = manifest_by_path[link["manifest"]]
        if manifest.get("schema_version") != MVG_SCHEMA:
            link["credit_rejected"] = "manifest_schema_unsupported"
            continue
        receipt = ctx.values.get("receipt:" + link["path"])
        same_manifest = link.get("manifest_sha256") == manifest["sha256"]
        same_revision = bool(bound_revision) and link.get("source_revision") == bound_revision
        passed = link.get("status") == "passed" and link.get("runtime_verified") is True
        if link.get("receipt_state") == "invalid":
            state, reason = "failed", "coverage_receipt_invalid_or_unsealed"
        elif not same_manifest or not same_revision:
            state, reason = "stale_revision", "identity_mismatch"
        elif link.get("protocol_fixture_only") or link.get("mode") != "run" or not passed:
            state, reason = "failed", "not_a_passing_real_run"
        elif link.get("workspace_dirty"):
            state, reason = "workspace_only", "workspace_dirty_run"
        elif not main_fact:
            state, reason = "workspace_only", "not_main_fact"
        else:
            state, reason = "passed", None
        link["credit_state"] = state if state != "passed" else "credited"
        if reason:
            link["credit_rejected"] = reason
        if state != "passed":
            manifest.setdefault("runtime_state", state)
            if _RANK[state] > _RANK.get(manifest["runtime_state"], 0):
                manifest["runtime_state"] = state
            for fid in manifest["flow_ids"]:
                offer(fid, state, [], link["path"])
            continue
        receipt_levels = _receipt_levels(receipt) if receipt else []
        if receipt is None:
            credited = list(manifest["flow_ids"])
            cumulative = manifest.get("coverage_mode") == "full"
            per_flow_levels = {fid: receipt_levels for fid in credited}
        else:
            passed_tests: dict[str, dict[str, Any]] = {}
            failed_tests: set[str] = set()
            explicit = set(_ids(receipt.get("executed_flow_ids")))
            for item in _as_list(receipt.get("executed_tests")):
                if not isinstance(item, dict):
                    continue
                test_id = _id(item.get("test_id")) or _id(item.get("id"))
                if test_id is None:
                    continue
                if item.get("status") == "passed":
                    passed_tests[test_id] = item
                else:
                    failed_tests.add(test_id)
            credited = []
            per_flow_levels = {}
            for fid in manifest["flow_ids"]:
                required = manifest["flow_tests"].get(fid) or []
                if any(t in failed_tests for t in required):
                    continue
                by_tests = bool(required) and all(t in passed_tests for t in required)
                if by_tests or (fid in explicit and not required):
                    credited.append(fid)
                    levels = {normalize_evidence_level(passed_tests[t].get("evidence_level")) for t in required
                              if t in passed_tests}
                    levels.discard("unverified")
                    per_flow_levels[fid] = sorted(levels, key=EVIDENCE_LEVELS.index) or receipt_levels
            cumulative = (_receipt_scope_kind(receipt) == "cumulative" and manifest.get("coverage_mode") == "full"
                          and set(credited) >= set(manifest["flow_ids"]))
            for item in passed_tests.values():
                if item.get("kind") == "other_verification" \
                        or normalize_evidence_level(item.get("evidence_level")) == "other_verification":
                    for rid in _ids(item.get("requirement_ids")):
                        other_runtime[rid] = ("passed_other_verification", link["path"])
            for item in _as_list(receipt.get("other_verification_results")):
                if isinstance(item, dict) and item.get("status") == "passed":
                    for rid in _ids(item.get("requirement_ids")) + _ids([item.get("requirement_id")]):
                        other_runtime[rid] = ("passed_other_verification", link["path"])
        flow_state = "passed_cumulative_mvg" if cumulative else "passed_flow_scope"
        link["credited"] = bool(credited) or bool(other_runtime)
        link["credited_flow_ids"] = sorted(credited)
        link["attribution"] = "cumulative_mvg" if cumulative else "flow_scope"
        manifest_state = flow_state if credited else "failed"
        manifest.setdefault("runtime_state", manifest_state)
        if _RANK[manifest_state] > _RANK.get(manifest["runtime_state"], 0):
            manifest["runtime_state"] = manifest_state
        for fid in credited:
            offer(fid, flow_state, per_flow_levels.get(fid) or [], link["path"])
    for node in layers["flows"]:
        if node.get("planned_only"):
            continue
        if node["id"] in flow_runtime:
            state, levels, path = flow_runtime[node["id"]]
            node["runtime_state"] = state
            node["runtime_backlink"] = path
            if state.startswith("passed_"):
                node["evidence_levels"] = list(levels)
                node["evidence_level"] = sorted(levels, key=EVIDENCE_LEVELS.index)[0] if levels else "unverified"
    for kind in ("requirements", "obligations"):
        for node in layers[kind]:
            if node.get("planning_state") != "non_flow_governed":
                continue
            rids = [node["id"]] if kind == "requirements" else list(node.get("requirement_ids") or [])
            hit = next((other_runtime[rid] for rid in rids if rid in other_runtime), None)
            if hit is not None and (kind == "requirements" or node.get("obligation_class") == "other_verification"):
                node["runtime_state"] = hit[0]
                node["runtime_backlink"] = hit[1]
                node["evidence_level"] = "other_verification"
                node["evidence_levels"] = ["other_verification"]
    for link in backlinks:
        if link.get("kind") not in ("runtime_latest", "runtime_workspace_latest"):
            continue
        for row in link.get("tasks") or []:
            entry = task_index.get(row["task_id"])
            if entry is None:
                continue
            node = entry["node"]
            if link["kind"] == "runtime_workspace_latest" or row.get("verification_mode") == "workspace":
                if node["runtime_state"] == "unverified":
                    node["runtime_state"] = "workspace_only"
                continue
            if link.get("verification_mode") != "main":
                node["runtime_state"] = "workspace_only"
            elif row.get("source_revision") != bound_revision or link.get("source_revision") != bound_revision:
                node["runtime_state"] = "stale_revision"
            elif row.get("status") != "passed" or not row.get("integrity"):
                node["runtime_state"] = "failed"
            elif main_fact:
                node["runtime_state"] = "passed_local_task"
                level = row.get("evidence_level") or "unverified"
                node["evidence_level"] = level
                node["evidence_levels"] = [level] if level != "unverified" else []
                link["credited"] = True
            else:
                node["runtime_state"] = "workspace_only"
            node["runtime_backlink"] = link["path"]


# ---------------------------------------------------------------------------
# Revocation (Chapter 6 reopen / durable stop-loss)
# ---------------------------------------------------------------------------

def _durable_signals(ctx: _Context, task_ids: list[str]) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    if not task_ids:
        return signals
    try:
        from _b_route_chapter6_recovery import scan_durable_recovery_signals
    except Exception as exc:  # pragma: no cover - fail closed on unavailable recovery scanner
        ctx.issue("blocked", codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.TARGET, "chapter6-recovery",
                  "durable Chapter 6 stop-loss scanner", type(exc).__name__, "logs/ci")
        return signals
    for tid in task_ids[:MAX_IMPACT_ROOTS]:
        try:
            scan = scan_durable_recovery_signals(ctx.root, tid)
        except Exception as exc:  # pragma: no cover - defensive read-only boundary
            ctx.issue("blocked", codec.ReasonCode.READ_ERROR, codec.Stage.TARGET, tid,
                      "readable durable Chapter 6 recovery signals", type(exc).__name__, "logs/ci",
                      subject={"kind": "task", "id": tid})
            continue
        if isinstance(scan, dict) and scan.get("has_active_stop_loss"):
            signals[tid] = {"path": scan.get("blocking_run_dir") or "logs/ci",
                            "status": str(scan.get("blocked_by") or "stop_loss"),
                            "resume_ref": scan.get("blocking_run_dir") or f"resume-task:{tid}",
                            "reason_code": codec.ReasonCode.CONFLICT.value,
                            "blocking_reason": scan.get("blocking_reason")}
    return signals


def _apply_revocations(ctx: _Context, built: dict[str, Any], chain: dict[str, Any], reopen: dict[str, Any],
                       durable: dict[str, dict[str, Any]], filter_task: str | None) -> list[dict[str, Any]]:
    revocations: list[dict[str, Any]] = []
    layers = built["layers"]
    governed_chain = chain["present"]

    def revoke(node: dict[str, Any], markers: list[dict[str, Any]], kind: str) -> None:
        first = markers[0]
        code = codec.ReasonCode(first.get("reason_code") or codec.ReasonCode.CONFLICT.value)
        entry = ctx.issue("revoked", code, codec.Stage.TARGET, node["id"],
                          "no active persistent reopen/stop-loss/epoch revocation",
                          [marker["status"] for marker in markers], first["path"],
                          resume_ref=str(first["resume_ref"]), blocking=False,
                          subject={"kind": kind, "id": node["id"]})
        node["planning_state"] = "revoked"
        node["revocation_markers"] = [marker["path"] for marker in markers]
        node["diagnostics"].append(entry["diagnostic"])
        revocations.append(entry)

    for node in layers["tasks"]:
        tid = node["id"]
        governed = node.get("governed") or tid == filter_task
        markers = list(reopen["tasks"].get(tid, []))
        if governed:
            markers += list(reopen["global"])
            for plan_id in node.get("plan_ids") or []:
                markers += reopen["plans"].get(plan_id, [])
            for scope_id in node.get("scope_ids") or []:
                markers += reopen["scopes"].get(scope_id, [])
        if tid in durable:
            markers.append(durable[tid])
        if markers:
            node["local_qualification"] = "revoked"
            revoke(node, markers, "task")
    for layer in ("requirements", "capabilities", "flows", "four_parts", "obligations", "sources"):
        for node in layers[layer]:
            plan_id = node.get("plan_id")
            if plan_id is None:
                continue
            markers = list(reopen["plans"].get(plan_id, []))
            scope_id = node.get("scope_id")
            if scope_id is not None:
                markers += reopen["scopes"].get(scope_id, [])
            if governed_chain:
                markers += reopen["global"]
            if markers:
                revoke(node, markers, node["kind"])
    for scope in chain["scopes"]:
        markers = list(reopen["scopes"].get(scope["scope_id"], []))
        for plan_id in scope.get("plan_ids") or []:
            markers += reopen["plans"].get(plan_id, [])
        if governed_chain:
            markers += reopen["global"]
        if markers:
            scope["status"] = "revoked"
            scope["revocation_markers"] = sorted({marker["path"] for marker in markers})
    return revocations


# ---------------------------------------------------------------------------
# Impact (Story 4.1 delegation)
# ---------------------------------------------------------------------------

def _materialize_main(root: Path, snapshot: Any, dest: Path) -> int:
    """Copy selected committed refs/heads/main blobs into a clean temp tree via git cat-file --batch."""
    paths = [p for p in sorted(snapshot.paths)
             if p.startswith(MATERIALIZE_PREFIXES) and (p.endswith(MATERIALIZE_SUFFIXES) or p in MATERIALIZE_PREFIXES)]
    paths = paths[:MAX_MATERIALIZED_FILES]
    if not paths:
        return 0
    request = "".join(f"{snapshot.commit}:{p}\n" for p in paths).encode("utf-8")
    proc = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"], input=request, capture_output=True,
                          timeout=300, check=True)
    data = proc.stdout
    offset = 0
    count = 0
    for path in paths:
        newline = data.index(b"\n", offset)
        header = data[offset:newline].decode("utf-8", "replace").split()
        offset = newline + 1
        if len(header) < 3 or header[1] != "blob":
            continue
        size = int(header[2])
        blob = data[offset:offset + size]
        offset += size + 1
        target = dest.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        count += 1
    return count


def _impact_roots(chain: dict[str, Any], built: dict[str, Any], filters: dict[str, Any]) -> list[str]:
    roots: list[str] = []
    if filters["flow_id"] is not None:
        roots.append(f"flow:{filters['flow_id']}")
    if filters["capability_id"] is not None:
        roots.append(f"capability:{filters['capability_id']}")
    if filters["task_id"] is not None:
        roots.append(f"task:{filters['task_id']}")
    if filters["scope_id"] is not None:
        for scope in chain["scopes"]:
            roots.extend(f"plan:{pid}" for pid in scope.get("plan_ids") or [] if pid)
    if any(filters.values()):
        return roots
    plan_ids = sorted({_id(info["plan"].get("plan_id")) for info in chain["plans"].values()} - {None})
    roots.extend(f"plan:{pid}" for pid in plan_ids)
    for node in built["layers"]["flows"]:
        if node.get("source") == "b_route_plan" or (node.get("manifests") and not node.get("planned_only")):
            roots.append(f"flow:{node['id']}")
    for node in built["layers"]["tasks"]:
        if node.get("governed"):
            roots.append(f"task:{node['id']}")
    return list(dict.fromkeys(roots))[:MAX_IMPACT_ROOTS]


def _impact(ctx: _Context, identity: dict[str, Any], provenance: dict[str, Any], roots: list[str],
            enabled: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "computed_by": "_b_route_impact_closure.compute_impact_closure",
        "authoritative_entrypoint": "py -3 scripts/python/dev_cli.py b-route-impact-closure",
        "targets": roots,
        "status": "skipped" if not enabled else "empty",
        "impacted": [],
        "impacted_count": 0,
        "impacted_lists": {},
        "conservative": False,
        "conservative_expansions": [],
        "impact_proof_id": None,
        "closure_root": None,
        "diagnostics": [],
        "impact_accounting_only": True,
        "runtime_verified": False,
    }
    if not enabled or not roots:
        return result
    import _b_route_impact_closure as closure
    temp: tempfile.TemporaryDirectory | None = None
    closure_root: Path = ctx.root
    try:
        if ctx.mode == "main" and isinstance(ctx.reader, _GitReader) \
                and not (identity["head_matches_main"] and not provenance["dirty_workspace"]):
            temp = tempfile.TemporaryDirectory(prefix="br-projection-main-")
            closure_root = Path(temp.name) / "snapshot"
            closure_root.mkdir()
            _materialize_main(ctx.root, ctx.reader.snapshot, closure_root)
            result["closure_root"] = "materialized:refs/heads/main@" + str(provenance.get("snapshot_commit"))
        else:
            result["closure_root"] = "repository_root"
        payload = closure.compute_impact_closure(closure_root, change_roots=roots)
    except (OSError, ValueError, subprocess.SubprocessError, codec.CodecError) as exc:
        result.update(status="blocked", diagnostics=[_diag(codec.ReasonCode.DEPENDENCY_UNAVAILABLE,
                                                           codec.Stage.TARGET, "impact",
                                                           "governed impact closure input", str(exc)[:200])])
        return result
    finally:
        if temp is not None:
            temp.cleanup()
    lists = {name: sorted(f"{kind}:{item.get('entity_id')}" for item in _as_list(payload.get(name))
                          if isinstance(item, dict))
             for kind, name in closure.REPORTED_LISTS}
    impacted = sorted({key for keys in lists.values() for key in keys}
                      | {f"{item.get('entity_kind')}:{item.get('entity_id')}"
                         for item in _as_list(payload.get("shared_rules")) if isinstance(item, dict)})
    result.update(
        status="computed" if payload.get("ok") else "blocked",
        impacted=impacted[:2000],
        impacted_count=len(impacted),
        impacted_lists=lists,
        conservative=bool(payload.get("conservative_expanded")),
        conservative_expansions=list(_as_list(payload.get("expansion_reasons")))[:200],
        unknown_items=len(_as_list(payload.get("unknown_items"))),
        impact_proof_id=payload.get("impact_proof_id"),
        diagnostics=list(_as_list(payload.get("diagnostics"))),
    )
    return result


def _knowledge_boundary(ctx: _Context) -> dict[str, Any]:
    reader = ctx.reader if ctx.mode == "main" else _WorkspaceReader(ctx.root, record=False)
    raw = reader.read(SOURCE_EXCLUSIONS_PATH)
    prefixes = {rule["path_prefix"] for rule in _exclusion_rules(raw) if type(rule.get("path_prefix")) is str}
    checked = {prefix: prefix in prefixes for prefix in ("logs", "backup", "docs/migration")}
    return {
        "source_exclusions_path": SOURCE_EXCLUSIONS_PATH,
        "source_exclusions_source": "refs/heads/main" if isinstance(reader, _GitReader) else "local-workspace",
        "source_exclusions_sha256": _sha256(raw) if raw is not None else None,
        "excluded_prefixes_checked": checked,
        "logs_excluded_from_global_search": all(checked.values()),
        "logs_role": "explicit_backlink_only",
        "registered_closure_sources": ["chapter3", "chapter5"],
        "workspace_views": list(WORKSPACE_TOPOLOGY_VIEWS),
        "canonical_requires_trusted_ref": True,
        "implicit_global_refresh_performed": False,
        "control_plane_modified": False,
    }


def _snapshot_digest(mode: str, provenance: dict[str, Any], reader: Any) -> str:
    inputs = sorted([path, digest] for path, digest in reader.digests.items()
                    if not path.startswith("logs/"))
    return codec.canonical_digest({"mode": mode, "authority_ref": provenance["authority_ref"],
                                   "snapshot_commit": provenance.get("snapshot_commit"), "inputs": inputs})


def _local_clear_boundary(ctx: _Context, chain: dict[str, Any], manifests: list[dict[str, Any]],
                          clears: list[dict[str, Any]], recovery: dict[str, Any]) -> dict[str, Any]:
    return {
        "formal_git_adoptions": {"path": CATALOG_PATH, "status": chain["status"] if chain["present"] else "absent",
                                 "records_valid": sum(1 for r in ctx.records.values() if r["status"] == "valid"),
                                 "validated_by": "own catalog/receipt/source chain"},
        "cumulative_mvg_baselines": [{"path": m["path"], "sha256": m["sha256"], "status": m["status"]}
                                     for m in manifests],
        "clear_audit_trail": clears,
        "current_local_epoch": recovery.get("current_epoch"),
        "formal_adoptions_independent_of_local_epoch": True,
        "local_clear_removes_formal_records": False,
    }


def build_b_route_knowledge_projection(root: Path, *, mode: str = "main", scope_id: str | None = None,
                                       flow_id: str | None = None, capability_id: str | None = None,
                                       task_id: str | None = None, compute_impact: bool = True) -> dict[str, Any]:
    """Build the read-only derived projection; raises CodecError only for invalid arguments."""
    mode = validate_mode(mode)
    filters = {
        "scope_id": validate_filter("scope_id", scope_id),
        "flow_id": validate_filter("flow_id", flow_id),
        "capability_id": validate_filter("capability_id", capability_id),
        "task_id": validate_filter("task_id", task_id),
    }
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise _invalid_argument("repository root directory", type(root).__name__)
    raw_root = Path(root)
    try:
        for ancestor in reversed((raw_root.absolute(), *raw_root.absolute().parents)):
            inventory.no_reparse(ancestor)
    except ValueError as exc:
        raise _invalid_argument("repository root without reparse ancestors", str(exc)[:200],
                                codec.Stage.PATH, codec.ReasonCode.UNSAFE_PATH) from exc
    root = raw_root.resolve()
    if not root.is_dir():
        raise _invalid_argument("existing repository root directory", str(root))
    reader, provenance, warnings, identity = _bind_provenance(root, mode)
    logs_reader = _WorkspaceReader(root, record=False)
    ctx = _Context(root, mode, reader, logs_reader)

    chain = _load_catalog_chain(ctx, filters["scope_id"])
    pending = _pending_operations(ctx)
    recovery, clears = _local_recovery(ctx)
    reopen = _reopen_markers(ctx)
    progress = _planning_progress(ctx, recovery)
    backlinks = _runtime_backlinks(ctx)
    built = _build_layers(ctx, chain, provenance, backlinks)
    layers = built["layers"]
    governed_tasks = sorted({n["id"] for n in layers["tasks"] if n.get("governed")}
                            | ({filters["task_id"]} if filters["task_id"] in built["task_index"] else set()))
    durable = _durable_signals(ctx, governed_tasks)
    revocations = _apply_revocations(ctx, built, chain, reopen, durable, filters["task_id"])

    topology_present = any(ctx.exists_any(path) for path in
                           (SOURCE_BLOCKS_PATH, CAPABILITIES_PATH) + REQUIREMENT_PATHS)
    found = True
    for kind, key in (("flow", "flow_id"), ("capability", "capability_id"), ("task", "task_id")):
        if filters[key] is not None:
            layer = {"flow": "flows", "capability": "capabilities", "task": "tasks"}[kind]
            found = found and any(node["id"] == filters[key] for node in layers[layer])
    if filters["scope_id"] is not None and chain.get("scope_found") is False:
        found = False
    legacy = not chain["present"] and not pending and not topology_present
    roots = [] if legacy and not any(filters.values()) else _impact_roots(chain, built, filters)
    impact = _impact(ctx, identity, provenance, roots, compute_impact)
    knowledge_boundary = _knowledge_boundary(ctx)
    ctx.flush_unsafe()

    def targeted(issue: dict[str, Any]) -> bool:
        subject = issue.get("subject")
        if subject is None:
            return True
        if subject.get("kind") == "task" and filters["task_id"] is not None:
            return subject.get("id") == filters["task_id"]
        return subject.get("kind") not in ("local_job", "local_registry", "runtime_receipt", "runtime_summary",
                                           "runtime_index", "manifest")

    blocking = [issue for issue in ctx.issues if issue["blocking"] and targeted(issue)]
    revoked = [issue for issue in revocations if targeted(issue)]
    if filters["task_id"] is not None:
        entry = built["task_index"].get(filters["task_id"])
        if entry and entry["node"].get("local_qualification") == "revoked":
            entry["node"]["planning_state"] = "revoked"

    committed_partial = False
    local_partial = bool(progress["partial"])
    partial = local_partial if mode != "main" else committed_partial
    awaiting_3c = sum(1 for n in layers["flows"] if n["planning_state"] == "3b_adopted_awaiting_3c")
    orphans = sorted(n["id"] for n in layers["requirements"]
                     if n["planning_state"] in ("legacy_unmapped", "blocked") and chain["present"])
    if blocking:
        status = "blocked"
    elif revoked:
        status = "revoked"
    elif partial:
        status = "partial_planning"
    elif legacy:
        status = "legacy_unmapped"
    else:
        status = "ok"

    policy = chain.get("policy") if isinstance(chain.get("policy"), dict) else {}
    switch = policy.get("switch_boundary") if isinstance(policy.get("switch_boundary"), dict) else {}
    default_route = switch.get("default_route") if policy else None
    manifests = built["manifests"]
    runtime_verified = bool(
        provenance["is_main_fact"] and not partial and status == "ok" and manifests
        and all(m.get("runtime_state") == "passed_cumulative_mvg" for m in manifests))
    provenance["snapshot_digest"] = _snapshot_digest(mode, provenance, reader)
    for link in backlinks:
        link["matches_snapshot"] = bool(provenance.get("snapshot_commit")
                                        and link.get("source_revision") == provenance.get("snapshot_commit"))

    planning_complete = bool(
        status == "ok" and not local_partial and awaiting_3c == 0 and not orphans
        and chain["status"] in ("valid", "absent"))
    if partial:
        completeness = "partial_planning"
    elif status == "legacy_unmapped":
        completeness = "legacy_unmapped"
    elif status in ("blocked", "revoked"):
        completeness = status
    else:
        completeness = "complete_for_committed_scope" if planning_complete else "incomplete_for_committed_scope"
    default_b_enabled = bool(provenance["is_main_fact"] and default_route == "B" and status == "ok"
                             and chain.get("policy_valid") and chain["status"] == "valid")

    issues = ctx.issues
    summary = {name: len(nodes) for name, nodes in layers.items()}
    summary.update(edges=len(built["edges"]), topology_edges=built["topology_edge_count"],
                   blocked=sum(1 for i in issues if i["status"] == "blocked"),
                   stale=sum(1 for i in issues if i["status"] == "stale"),
                   revoked=sum(1 for i in issues if i["status"] == "revoked"),
                   invalid_evidence=sum(1 for i in issues if i["status"] == "invalid_evidence"),
                   awaiting_3c=awaiting_3c, orphan_requirements=len(orphans),
                   non_flow_governed=sum(1 for n in layers["requirements"] if n["planning_state"] == "non_flow_governed"))
    layers_out = dict(layers)
    layers_out["impact"] = impact
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": status not in ("blocked", "revoked"),
        "status": status,
        "mode": mode,
        "filters": filters,
        "target_found": found,
        "provenance": provenance,
        "planning_completeness": completeness,
        "planning_complete": planning_complete,
        "planning_progress": {"committed_partial": committed_partial, "partial": partial,
                              "workspace_local_progress": progress},
        "runtime_verified": runtime_verified,
        "default_b_enabled": default_b_enabled,
        "policy_default_route": default_route,
        "catalog": {key: chain.get(key) for key in ("present", "status", "revision", "scopes")},
        "records": sorted(ctx.records.values(), key=lambda r: r["path"]),
        "layers": layers_out,
        "edges": built["edges"],
        "manifests": manifests,
        "backlinks": backlinks,
        "pending_operations": pending,
        "local_recovery_status": recovery,
        "local_clear_boundary": _local_clear_boundary(ctx, chain, manifests, clears, recovery),
        "chapter6_reopen": {"tasks": reopen["tasks"], "plans": reopen["plans"], "scopes": reopen["scopes"],
                            "global": reopen["global"], "damaged": reopen["damaged"],
                            "durable_stop_loss": durable},
        "issues": issues,
        "diagnostics": [issue["diagnostic"] for issue in issues],
        "warnings": warnings,
        "summary": summary,
        "knowledge_boundary": knowledge_boundary,
        "vocabulary": {"planning_states": list(PLANNING_STATES), "implementation_states": list(IMPLEMENTATION_STATES),
                       "runtime_states": list(RUNTIME_STATES), "evidence_levels": list(EVIDENCE_LEVELS),
                       "obligation_classes": list(OBLIGATION_CLASSES)},
        "invariants": dict(INVARIANTS),
    }


def identity_summary(root: Path, task_id: str | None = None) -> dict[str, Any]:
    """Cheap additive Knowledge identity; full projection only when B-route records exist."""
    root = Path(root).resolve()
    catalog = (root / CATALOG_PATH).is_file()
    summary: dict[str, Any] = {
        "b_route_projection_available": catalog,
        "catalog_present": catalog,
        "endpoint": "/api/knowledge/b-route-projection",
        "cli": "py -3 scripts/python/dev_cli.py b-route-knowledge-projection",
        "read_only": True,
        "implicit_global_refresh_performed": False,
    }
    if not catalog:
        summary["status"] = "legacy_unmapped"
        return summary
    projection = build_b_route_knowledge_projection(
        root, mode="workspace_preview", task_id=task_id if task_id and _FILTER_RE.fullmatch(str(task_id)) else None,
        compute_impact=False)
    summary.update(status=projection["status"], ok=projection["ok"],
                   provenance={key: projection["provenance"].get(key) for key in (
                       "mode", "authority_ref", "branch", "head_commit", "is_main_fact",
                       "trusted_ref_eligible", "snapshot_digest")},
                   planning_completeness=projection["planning_completeness"],
                   diagnostics=len(projection["diagnostics"]), summary=projection["summary"])
    if task_id is not None:
        node = next((n for n in projection["layers"]["tasks"] if n["id"] == str(task_id)), None)
        summary["task"] = node
    return summary


def _unsafe_report(expected: Any, actual: Any) -> codec.CodecError:
    return _invalid_argument(expected, actual, codec.Stage.PATH, codec.ReasonCode.UNSAFE_PATH)


def write_projection_report(root: Path, report_rel: str, payload: dict[str, Any]) -> Path:
    """Write an optional report strictly under logs/** without touching publication pointers or live state."""
    root = Path(root).resolve()
    if type(report_rel) is not str or not report_rel.startswith("logs/") or not report_rel.endswith(".json"):
        raise _invalid_argument("repository-relative logs/**/*.json report path", report_rel)
    if report_rel in PROTECTED_POINTERS:
        raise _invalid_argument("report path distinct from Knowledge publication pointers", report_rel)
    if any(report_rel == prefix or report_rel.startswith(prefix + "/") for prefix in RESERVED_REPORT_PREFIXES):
        raise _invalid_argument("report path outside operational state directories", report_rel)
    try:
        inventory.canonical_path(report_rel, allow_logs=True)
    except ValueError as exc:
        raise _invalid_argument("canonical logs/** report path", str(exc)[:200]) from exc
    try:
        path = inventory.safe_input(root, report_rel, allow_logs=True)
        tmp = path.with_name(path.name + ".tmp")
        inventory.no_reparse(tmp)
    except ValueError as exc:
        raise _unsafe_report("report path and .tmp sibling without symlink or reparse point", str(exc)[:200]) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = path.parent
        while current != root and root in current.parents:
            inventory.no_reparse(current)
            current = current.parent
    except ValueError as exc:
        raise _unsafe_report("report parent without symlink or reparse point", str(exc)[:200]) from exc
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=False) + "\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
    os.replace(tmp, path)
    return path
