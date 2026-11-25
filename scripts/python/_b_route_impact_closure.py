"""Read-only B-route governed reverse impact closure (Story 4.1).

This module builds directed causal reverse impact edges from committed B-route
records (catalog, plans, Stage-3C/4/5 bindings, task origins), the Taskmaster
triplet, contract/scene/adapter/test-infrastructure paths, and cumulative MVG
manifests. It computes a cycle-safe, deduplicated transitive closure for
explicit change roots, expands conservatively on missing edges, unreadable
inputs, pending journals or unknown mappings, and seals a full typed impact
proof that can be selectively revalidated per partition.

Requirement and responsible-Task relations reached from a Flow are recorded as
accounting-only edges: they are reported as impacted but never feed back into
unrelated Flows that merely share a Requirement or Capability.

It only accounts for impact. It never runs tests, mutates Task status, moves a
publish pointer, retires Flows/tests, or enables the B route by default.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import copy
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable

import _b_route_codec as codec
import _b_route_inventory as inventory
from _b_route_flow_graph import components


SCHEMA = "newrouge.b-route-impact-closure.v1"
GRAPH_SCHEMA = "newrouge.b-route-impact-graph.v1"
MVG_SCHEMA = "newrouge.mvg-integration.v1"
CATALOG_SCHEMA = "newrouge.b-route-catalog.v1"
CATALOG_PATH = "docs/planning/b-route/catalog.v1.json"
ORIGINS_PATH = "docs/planning/b-route/task-origins.v1.json"
TASKS_PATH = ".taskmaster/tasks/tasks.json"
VIEW_PATHS = (("back", ".taskmaster/tasks/tasks_back.json"), ("gameplay", ".taskmaster/tasks/tasks_gameplay.json"))
MANIFEST_DIR = "docs/testing/mvg"
CONTRACTS_DIR = "Game.Core/Contracts"
OPERATIONS_STORE = "logs/ci/b-route-operations"
LEGACY_PLANNING_DIRS = ("logs/ci/mvg-planning", "logs/ci/capability-planning")
PENDING_MARKERS = ("docs/planning/b-route/capability-apply.pending.json",
                   "docs/planning/semantic-topology/capability-apply.pending.json")

INVARIANT_FLAGS = {
    "impact_accounting_only": True,
    "implementation_completed": False,
    "runtime_verified": False,
    "task_status_mutated": False,
    "publish_pointer_mutated": False,
    "retired_flows_or_tests": False,
    "default_b_enabled": False,
}

ENTITY_KINDS = (
    "path", "contract", "scene_resource", "adapter", "test_infra", "test", "rule", "state", "command",
    "implementation_object", "part", "obligation", "requirement", "task", "flow", "capability",
    "other_verification", "manifest", "plan", "source_block",
)
PATH_KINDS = frozenset({"path", "contract", "scene_resource", "adapter", "test_infra"})
DEFINITION_KINDS = frozenset({"rule", "state", "command"})
LOCAL_ID_KINDS = frozenset({"implementation_object", "obligation", "part"})
OWNED_DEFINITION_KINDS = frozenset({"flow"}) | DEFINITION_KINDS
PART_KINDS = ("domain_rules", "csharp_adapter", "binding", "scene")
ROOT_ALIASES = {
    "path": "path", "file": "path", "contract": "contract", "scene": "scene_resource",
    "scene_resource": "scene_resource", "resource": "scene_resource", "adapter": "adapter",
    "test_infra": "test_infra", "infra": "test_infra", "rule": "rule", "state": "state",
    "command": "command", "flow": "flow", "task": "task", "test": "test", "requirement": "requirement",
    "req": "requirement", "impl": "implementation_object", "implementation_object": "implementation_object",
    "obligation": "obligation", "capability": "capability", "manifest": "manifest", "plan": "plan",
    "source_block": "source_block", "other_verification": "other_verification", "part": "part",
}
REPORTED_LISTS = (
    ("flow", "impacted_flows"),
    ("task", "impacted_tasks"),
    ("obligation", "impacted_obligations"),
    ("test", "impacted_tests"),
    ("requirement", "impacted_requirements"),
    ("other_verification", "other_verification_sinks"),
    ("implementation_object", "impacted_implementation_objects"),
)
REPORTED_KINDS = frozenset(kind for kind, _ in REPORTED_LISTS)
NONEMPTY_LISTS = ("impacted_flows", "impacted_tasks", "impacted_tests", "impacted_requirements",
                  "impacted_obligations")
OBL_LINK_KINDS = frozenset({"flow", "task", "test", "requirement"})
TEST_INFRA_PREFIXES = ("Tests.Godot/", "Game.Core.Tests/")
SCENE_SUFFIXES = (".tscn", ".tres", ".res", ".scn")
TASK_VOLATILE_FIELDS = frozenset({"status", "updatedAt", "updated_at", "createdAt", "created_at",
                                  "completedAt", "completed_at", "lastUpdated", "last_updated"})
KNOWN_PARTITION_PREFIXES = ("plan:", "manifest:", "task:", "path:")
FILTER_PARTITION = "filter:manifest_paths"
IDENTITY_FIELDS = ("category", "locator", "partition_keys", "raw_digest", "normalized_digest",
                   "normalization_mode", "codec_version")
FILE_MODES = frozenset({"raw_bytes", "absent_path"})
PROOF_VOLATILE_FIELDS = frozenset({"impact_proof_id", "metrics", "report_path", "status", "operation", "reused",
                                   "invalidated_partitions", "recomputed_partitions", "reused_partitions",
                                   "previous_impact_proof_id", "diagnostics", "reason_code"})
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
IDENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,199}")
LOOSE_IDENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/\-]{0,399}")
TASK_ID_RE = re.compile(r"[1-9][0-9]{0,9}")
RES_RE = re.compile(r"res://([A-Za-z0-9_./\-]+)")
NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)
SYMBOL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,299}")
INVALID_ARGUMENT_CODES = frozenset({"invalid_argument", "invalid_type", "invalid_enum", "unsafe_path",
                                    "path_unprovable"})
IMPL_PART = {"scene": "scene", "resource": "scene", "adapter": "csharp_adapter", "binding": "binding"}
STAGE4_OBL_PREFIX = "stage4:obl:v1|"
STAGE5_OBL_PREFIX = "stage5:obl:v1|"
TERMINAL_JOURNAL_STATES = frozenset({"completed", "complete", "committed", "published", "succeeded", "success",
                                     "done", "resolved", "compensated", "aborted", "rolled_back", "superseded",
                                     "closed"})
MAX_IMPORT_SCAN = 512

# Accounting-only edges: the downstream entity is reported as impacted but is not traversed further,
# so a Flow never pollutes unrelated Flows through a shared Requirement or responsible Task.
ACCOUNTING_EDGES = frozenset({"flow_requirement", "task_requirement", "definition_requirement", "flow_task",
                              "obligation_task"})
# Edges still followed (one hop, as sinks) from an accounting-only node.
ACCOUNTING_FOLLOW = frozenset({"requirement_other_verification", "requirement_non_task_sink",
                               "requirement_verification_sink", "task_implementation_object"})


def _err(code: codec.ReasonCode, expected: Any, actual: Any = None, entity: str | None = None,
         stage: codec.Stage = codec.Stage.CONTENT) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(code, stage, entity, expected, actual, None))


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _elapsed(started: float) -> float:
    return round(max(0.0, time.monotonic() - started), 6)


# ---------------------------------------------------------------------------
# Path and argument validation
# ---------------------------------------------------------------------------

def _validate_root(root: Any) -> Path:
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "nonempty repository root", type(root).__name__,
                   stage=codec.Stage.PATH)
    try:
        resolved = Path(root).resolve(strict=True)
    except OSError as exc:
        raise _err(codec.ReasonCode.PATH_UNPROVABLE, "existing repository root directory", str(exc),
                   stage=codec.Stage.PATH) from exc
    if not resolved.is_dir():
        raise _err(codec.ReasonCode.PATH_UNPROVABLE, "repository root directory", "not a directory",
                   stage=codec.Stage.PATH)
    try:
        for ancestor in reversed((resolved, *resolved.parents)):
            inventory.no_reparse(ancestor)
    except ValueError as exc:
        raise _err(codec.ReasonCode.UNSAFE_PATH, "root without reparse ancestors", str(exc),
                   stage=codec.Stage.PATH) from exc
    return resolved


def _normalize_rel(value: Any, *, allow_logs: bool = False) -> str:
    path = codec.validate_reference_path(value)
    path = path.removeprefix("./")
    try:
        inventory.canonical_path(path, allow_logs=allow_logs)
    except ValueError as exc:
        raise _err(codec.ReasonCode.UNSAFE_PATH, "canonical repository-relative POSIX path", str(exc),
                   stage=codec.Stage.PATH) from exc
    return path


def _safe_target(root: Path, rel: str, *, allow_logs: bool = False) -> Path:
    try:
        return inventory.safe_input(root, rel, allow_logs=allow_logs)
    except ValueError as exc:
        raise _err(codec.ReasonCode.UNSAFE_PATH, "safe repository path without aliases or reparse points",
                   str(exc), entity=rel, stage=codec.Stage.PATH) from exc


def validate_output_path(root: Path, value: Any, *, suffix: str) -> tuple[Path, str]:
    """Validate an optional report/events path: canonical, under logs/, no reparse ancestors."""
    if type(value) is not str or not value.strip():
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"nonempty logs/**/*{suffix} path", value,
                   stage=codec.Stage.PATH)
    rel = _normalize_rel(value, allow_logs=True)
    if not rel.startswith("logs/") or not rel.endswith(suffix) or rel == "logs/" + suffix:
        raise _err(codec.ReasonCode.UNSAFE_PATH, f"repository-relative logs/**/*{suffix} path", rel,
                   stage=codec.Stage.PATH)
    target = _safe_target(root, rel, allow_logs=True)
    return target, rel


def _read_bytes(root: Path, rel: str, *, allow_logs: bool = False) -> bytes | None:
    target = _safe_target(root, rel, allow_logs=allow_logs)
    if not target.exists():
        return None
    if not target.is_file():
        raise _err(codec.ReasonCode.READ_ERROR, "regular file", "not a file", entity=rel, stage=codec.Stage.PATH)
    try:
        return target.read_bytes()
    except OSError as exc:
        raise _err(codec.ReasonCode.READ_ERROR, "readable file", str(exc), entity=rel, stage=codec.Stage.PATH) from exc


def _read_json(root: Path, rel: str, *, allow_logs: bool = False) -> tuple[Any, bytes] | None:
    raw = _read_bytes(root, rel, allow_logs=allow_logs)
    if raw is None:
        return None
    return codec.strict_json_loads(raw), raw


def _file_exists(root: Path, rel: str, *, allow_logs: bool = False) -> bool:
    """Leaf and ancestor reparse-safe existence check (never a raw Path.is_file bypass)."""
    try:
        rel = _normalize_rel(rel, allow_logs=allow_logs)
        target = _safe_target(root, rel, allow_logs=allow_logs)
        inventory.no_reparse(target)
    except (codec.CodecError, ValueError):
        return False
    try:
        return target.is_file()
    except OSError:
        return False


def _safe_listdir(root: Path, rel: str, *, allow_logs: bool = False) -> tuple[list[str], list[str], bool]:
    """Return (files, dirs, safe) for one directory level without following reparse points."""
    try:
        target = _safe_target(root, rel, allow_logs=allow_logs)
        if not target.exists():
            return [], [], True
        inventory.no_reparse(target)
        if not target.is_dir():
            return [], [], True
        files, dirs, safe = [], [], True
        with os.scandir(target) as entries:
            for entry in entries:
                if entry.is_symlink() or getattr(os.path, "isjunction", lambda _p: False)(entry.path):
                    safe = False
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry.name)
                elif entry.is_dir(follow_symlinks=False):
                    dirs.append(entry.name)
        return sorted(files), sorted(dirs), safe
    except (codec.CodecError, ValueError, OSError):
        return [], [], False


def _classify_path(rel: str) -> str:
    lower = rel.lower()
    if rel.startswith("Game.Core/Contracts/"):
        return "contract"
    if lower.endswith(SCENE_SUFFIXES):
        return "scene_resource"
    if rel.startswith(TEST_INFRA_PREFIXES):
        return "test_infra"
    if rel.startswith("Game.Godot/"):
        return "adapter"
    return "path"


def _try_path(value: Any) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        return _normalize_rel(value)
    except codec.CodecError:
        return None


def _owned_paths(ref: Any) -> tuple[list[str], bool]:
    """Return OwnedRef ``files[].path`` entries and whether every entry validated."""
    if type(ref) is not dict:
        return [], False
    items = ref.get("files")
    if type(items) is not list or not items:
        return [], False
    paths, valid = [], True
    for item in items:
        path = _try_path(item.get("path")) if type(item) is dict else None
        if path:
            paths.append(path)
        else:
            valid = False
    return paths, valid


def _walk_paths(value: Any) -> Iterable[str]:
    if type(value) is dict:
        for key, child in value.items():
            if key == "path":
                path = _try_path(child)
                if path:
                    yield path
            else:
                yield from _walk_paths(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_paths(child)


def _strip_volatile(value: Any) -> Any:
    if type(value) is dict:
        return {k: _strip_volatile(v) for k, v in value.items() if k not in TASK_VOLATILE_FIELDS}
    if type(value) is list:
        return [_strip_volatile(v) for v in value]
    return value


def _str_ids(values: Any) -> list[str]:
    return [v for v in (values or []) if type(v) is str and v.strip()] if type(values) is list else []


def _task_ids(values: Any) -> list[str]:
    result = []
    for value in values or [] if type(values) is list else []:
        if type(value) is int and type(value) is not bool and value > 0:
            result.append(str(value))
        elif type(value) is str and TASK_ID_RE.fullmatch(value.strip()):
            result.append(value.strip())
    return result


def _tag_payload(text: Any, prefix: str, others: Iterable[str]) -> dict[str, Any]:
    """Parse a ``<plain> | <prefix>{json}`` responsibility tag (Stage-4/5 binding metadata)."""
    if type(text) is not str:
        return {}
    marker = " | " + prefix
    index = text.find(marker)
    if index >= 0:
        start = index + len(marker)
    elif text.startswith(prefix):
        start = len(prefix)
    else:
        return {}
    end = len(text)
    for other in others:
        position = text.find(" | " + other, start)
        if position >= 0:
            end = min(end, position)
    try:
        parsed = codec.strict_json_loads(text[start:end].strip())
    except codec.CodecError:
        return {"__malformed__": True}
    return parsed if type(parsed) is dict else {"__malformed__": True}


def _meta_ids(meta: dict[str, Any], suffix: str) -> list[str]:
    result: list[str] = []
    for key in sorted(meta):
        if key.endswith(suffix):
            result.extend(v for v in _str_ids(meta[key]) if v not in result)
    return result


# ---------------------------------------------------------------------------
# Graph model
# ---------------------------------------------------------------------------

class _Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.adj: dict[str, dict[str, list[tuple[str, str, str]]]] = {}
        self.gaps: list[dict[str, Any]] = []
        self.inputs: list[dict[str, Any]] = []
        self.path_index: dict[str, str] = {}
        self.local_index: dict[tuple[str, str], set[str]] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, str] = {}
        self.pending: list[tuple[str, str, str, str, str]] = []
        self.topo: dict[str, set[str]] = {}
        self.file_cat: dict[str, str] = {}
        self.def_owners: dict[tuple[str, str], tuple[str, Any]] = {}
        self.obl_links: dict[str, set[str]] = {}
        self.contract_index: dict[str, set[str]] | None = None

    def node(self, kind: str, entity_id: str, *, partition: str | None = None, authority: str | None = None) -> str:
        key = f"{kind}:{entity_id}"
        rec = self.nodes.get(key)
        if rec is None:
            rec = {"kind": kind, "id": entity_id, "availability": None, "semantic_owner": None, "regression": False,
                   "authorities": set(), "partitions": set(), "flags": set(), "links": set()}
            self.nodes[key] = rec
            self.adj[key] = {}
            if kind == "task":
                rec["partitions"].add(f"task:{entity_id}")
            elif kind == "plan":
                rec["partitions"].add(f"plan:{entity_id}")
            elif kind == "manifest":
                rec["partitions"].add(f"manifest:{entity_id}")
            elif kind in PATH_KINDS:
                rec["partitions"].add(f"path:{entity_id}")
                self.path_index.setdefault(entity_id, key)
            if kind in LOCAL_ID_KINDS or kind in DEFINITION_KINDS:
                local = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
                self.local_index.setdefault((kind, local), set()).add(key)
        if partition:
            rec["partitions"].add(partition)
        if authority:
            rec["authorities"].add(authority)
        return key

    def path_node(self, rel: str, *, partition: str | None = None, authority: str | None = None,
                  category: str | None = None) -> str:
        if category:
            self.file_cat.setdefault(rel, category)
        existing = self.path_index.get(rel)
        if existing is not None:
            rec = self.nodes[existing]
            if partition:
                rec["partitions"].add(partition)
            if authority:
                rec["authorities"].add(authority)
            return existing
        return self.node(_classify_path(rel), rel, partition=partition, authority=authority)

    def owner(self, key: str, owner_plan_id: str | None, kind: str, entity_id: str, revision: Any) -> None:
        rec = self.nodes[key]
        if rec["semantic_owner"] is None:
            rec["semantic_owner"] = {"owner_plan_id": owner_plan_id, "kind": kind, "id": entity_id,
                                     "revision": revision}

    def edge(self, upstream: str, downstream: str, kind: str, authority: str, partition: str) -> None:
        if upstream == downstream:
            return
        bucket = self.adj[upstream].setdefault(downstream, [])
        entry = (kind, authority, partition)
        if entry not in bucket:
            bucket.append(entry)
        for key in (upstream, downstream):
            self.nodes[key]["partitions"].add(partition)
            self.nodes[key]["authorities"].add(authority)
        up_kind, down_kind = self.nodes[upstream]["kind"], self.nodes[downstream]["kind"]
        if up_kind == "obligation" and down_kind in OBL_LINK_KINDS:
            self.obl_links.setdefault(downstream, set()).add(upstream)
        elif down_kind == "obligation" and up_kind in OBL_LINK_KINDS:
            self.obl_links.setdefault(upstream, set()).add(downstream)

    def topo_edge(self, upstream: str, downstream: str) -> None:
        """Directed flow/task/requirement topology edge used only for genuine cycle witnesses."""
        self.topo.setdefault(upstream, set()).add(downstream)
        self.topo.setdefault(downstream, set())

    def gap(self, entity: str, reason: str, owning_stage: str, authority: str, partition: str,
            *, trigger: str = "reach") -> None:
        item = {"entity": entity, "reason": reason, "owning_stage": owning_stage, "authority_ref": authority,
                "partition_key": partition, "trigger": trigger}
        if item not in self.gaps:
            self.gaps.append(item)

    def add_input(self, category: str, locator: str, partitions: Iterable[str], raw: bytes, normalized: Any,
                  mode: str) -> None:
        self.inputs.append({
            "category": category,
            "locator": locator,
            "partition_keys": sorted(set(partitions)),
            "raw_digest": codec.raw_digest(raw),
            "normalized_digest": codec.canonical_digest(normalized),
            "normalization_mode": mode,
            "codec_version": codec.CODEC_VERSION,
        })


def _use_key(graph: _Graph, use: Any, default_plan: str, partition: str, authority: str,
             default_kind: str | None = None) -> str | None:
    if type(use) is str and use.strip() and default_kind:
        key = graph.node(default_kind, f"{default_plan}:{use}")
        graph.pending.append(("definition", key, partition, authority, default_plan))
        return key
    if type(use) is not dict:
        return None
    kind = use.get("kind") or default_kind
    definition_id = use.get("definition_id") or use.get("id")
    if type(kind) is not str or type(definition_id) is not str or not definition_id.strip():
        return None
    if kind == "flow":
        key = graph.node("flow", definition_id)
        graph.pending.append(("flow", key, partition, authority, default_plan))
        return key
    if kind not in DEFINITION_KINDS:
        return None
    owner_plan = use.get("owner_plan_id")
    if type(owner_plan) is not str or not owner_plan.strip():
        if "proposed_owner_key" in use:
            return None
        owner_plan = default_plan
    key = graph.node(kind, f"{owner_plan}:{definition_id}")
    graph.pending.append(("definition", key, partition, authority, default_plan))
    return key


def _link_owned(graph: _Graph, root: Path, ref: Any, downstream: str, kind: str, auth: str, part: str,
                stage: str, *, category: str | None = None, require_exists: bool = True) -> tuple[list[str], bool]:
    """Wire OwnedRef ``files[].path`` entries into the graph; invalid or missing refs expand conservatively."""
    paths, valid = _owned_paths(ref)
    exists = valid
    for path in paths:
        graph.edge(graph.path_node(path, category=category), downstream, kind, auth, part)
        if not _file_exists(root, path):
            exists = False
    if not valid or (require_exists and not exists):
        graph.gap(downstream, f"unresolved_{kind}", stage, auth, part, trigger="always")
    return paths, exists


def _topo_flow_node(end: Any, fid: str) -> str:
    flow_id = end.get("flow_id") if type(end) is dict else None
    node_id = end.get("node_id") if type(end) is dict else None
    flow_id = flow_id if type(flow_id) is str and flow_id.strip() else fid
    node_id = node_id if type(node_id) is str and node_id.strip() else "*"
    return f"flow:{flow_id}#{node_id}"


def _process_plan(graph: _Graph, root: Path, pid: str, rev: Any, doc: dict, rel: str) -> None:
    part = f"plan:{pid}"
    auth = f"plan:{pid}@{rev}"
    plan_key = graph.node("plan", pid, partition=part, authority=auth)
    graph.owner(plan_key, pid, "plan", pid, rev)

    def req(rid: str) -> str:
        return graph.node("requirement", rid)

    def flow_ref(fid: str) -> str:
        key = graph.node("flow", fid)
        graph.pending.append(("flow", key, part, auth, pid))
        return key

    def req_flow(rk: str, fk: str, kind: str) -> None:
        graph.edge(rk, fk, kind, auth, part)
        graph.edge(fk, rk, "flow_requirement", auth, part)
        graph.nodes[rk]["links"].add(fk)

    identity = doc.get("source_identity") if type(doc.get("source_identity")) is dict else {}
    for field, category in (("manifest_ref", "source_manifest"), ("ledger_ref", "source_ledger")):
        if identity.get(field) is not None:
            _link_owned(graph, root, identity[field], plan_key, f"{category}_ref", auth, part, "3A",
                        category=category)

    for item in doc.get("requirements") or []:
        if type(item) is not dict or type(item.get("requirement_id")) is not str:
            continue
        rid = item["requirement_id"]
        rk = req(rid)
        graph.owner(rk, pid, "requirement", rid, rev)
        graph.nodes[rk]["flags"].add("declared")
        graph.edge(rk, plan_key, "requirement_plan", auth, part)
        for sb in _str_ids(item.get("source_block_ids")):
            graph.edge(graph.node("source_block", sb), rk, "source_block_requirement", auth, part)
        for prior in _str_ids(item.get("prior_requirement_ids")):
            graph.edge(req(prior), rk, "prior_requirement", auth, part)
            graph.topo_edge(req(prior), rk)
        for sink in _str_ids(item.get("non_task_sinks")):
            ov = graph.node("other_verification", sink)
            graph.edge(rk, ov, "requirement_non_task_sink", auth, part)
            graph.nodes[rk]["links"].add(ov)

    definitions = doc.get("definitions") if type(doc.get("definitions")) is dict else {}
    for field, kind in (("commands", "command"), ("states", "state"), ("rules", "rule")):
        for item in definitions.get(field) or []:
            if type(item) is not dict or type(item.get("id")) is not str:
                continue
            did = item["id"]
            dk = graph.node(kind, f"{pid}:{did}", partition=part, authority=auth)
            graph.owner(dk, pid, kind, did, rev)
            graph.nodes[dk]["flags"].add("defined")
            graph.edge(dk, plan_key, "definition_plan", auth, part)
            for rid in _str_ids(item.get("requirement_ids")):
                graph.edge(dk, req(rid), "definition_requirement", auth, part)
            for use in item.get("uses") or []:
                used = _use_key(graph, use, pid, part, auth)
                if used:
                    graph.edge(used, dk, "definition_use", auth, part)
            for fid in _str_ids(item.get("flow_ids")):
                graph.edge(dk, flow_ref(fid), "definition_flow", auth, part)

    for flow in definitions.get("flows") or []:
        if type(flow) is not dict or type(flow.get("id")) is not str:
            continue
        fid = flow["id"]
        fk = graph.node("flow", fid, partition=part, authority=auth)
        graph.owner(fk, pid, "flow", fid, rev)
        rec = graph.nodes[fk]
        rec["flags"].add("plan_declared")
        if "planned" in (flow.get("availability"), flow.get("status"), flow.get("state")):
            rec["flags"].add("declared_planned")
        graph.edge(fk, plan_key, "flow_plan", auth, part)
        for sb in _str_ids(flow.get("source_block_ids")):
            graph.edge(graph.node("source_block", sb), fk, "source_block_flow", auth, part)
        for rid in _str_ids(flow.get("requirement_ids")):
            req_flow(req(rid), fk, "requirement_flow")
        for cap in _str_ids(flow.get("capability_ids")) + _str_ids(flow.get("capability_refs")):
            graph.edge(graph.node("capability", cap), fk, "capability_flow", auth, part)
        for use in flow.get("state_owners") or []:
            used = _use_key(graph, use, pid, part, auth)
            if used:
                graph.edge(used, fk, "state_owner_flow", auth, part)
        for rule in flow.get("rule_ids") or []:
            used = _use_key(graph, rule, pid, part, auth, default_kind="rule")
            if used:
                graph.edge(used, fk, "rule_flow", auth, part)
        for use in flow.get("rule_uses") or []:
            used = _use_key(graph, use, pid, part, auth, default_kind="rule")
            if used:
                graph.edge(used, fk, "rule_flow", auth, part)
        for block_name in ("ui", "human_verification"):
            block = flow.get(block_name)
            if type(block) is dict:
                used = _use_key(graph, block.get("owner"), pid, part, auth)
                if used and used != fk:
                    graph.edge(used, fk, f"{block_name}_owner_flow", auth, part)
        for item in flow.get("parts") or []:
            if type(item) is dict and item.get("kind") in PART_KINDS and item.get("applicability") == "applicable":
                pk = graph.node("part", f"{pid}:{fid}:{item['kind']}", partition=part, authority=auth)
                graph.edge(pk, fk, "part_flow", auth, part)
        for handoff in flow.get("handoffs") or []:
            _flow_link(graph, handoff, fid, pid, part, auth, "flow_handoff")
        graph_doc = flow.get("graph") if type(flow.get("graph")) is dict else {}
        for gnode in graph_doc.get("nodes") or []:
            if type(gnode) is not dict:
                continue
            graph.topo.setdefault(_topo_flow_node({"flow_id": fid, "node_id": gnode.get("id")}, fid), set())
            for use in [gnode.get("owner")] + list(gnode.get("command_uses") or []) + list(gnode.get("state_uses") or []):
                used = _use_key(graph, use, pid, part, auth)
                if used and used != fk:
                    graph.edge(used, fk, "graph_node_use", auth, part)
        for gedge in graph_doc.get("edges") or []:
            _flow_link(graph, gedge, fid, pid, part, auth, "flow_graph_edge")
        for loop in graph_doc.get("loops") or []:
            anchors = [a for a in (loop.get("anchors") or []) if type(a) is dict] if type(loop) is dict else []
            nodes = [_topo_flow_node(a, fid) for a in anchors]
            for index, node in enumerate(nodes):
                graph.topo_edge(node, nodes[(index + 1) % len(nodes)])
            for anchor in anchors:
                if type(anchor.get("flow_id")) is str and anchor["flow_id"] != fid:
                    graph.edge(fk, flow_ref(anchor["flow_id"]), "flow_loop", auth, part)

    for use in doc.get("logical_references") or []:
        used = _use_key(graph, use, pid, part, auth)
        if used:
            graph.edge(used, plan_key, "logical_reference_plan", auth, part)

    for item in doc.get("requirement_route_memberships") or []:
        if type(item) is dict and type(item.get("requirement_id")) is str and type(item.get("flow_id")) is str:
            req_flow(req(item["requirement_id"]), flow_ref(item["flow_id"]), "requirement_route_flow")

    for item in doc.get("requirement_verification") or []:
        if type(item) is not dict or type(item.get("requirement_id")) is not str:
            continue
        rk = req(item["requirement_id"])
        disposition = item.get("disposition")
        if disposition == "flow" and type(item.get("flow_id")) is str and item["flow_id"].strip():
            req_flow(rk, flow_ref(item["flow_id"]), "requirement_verification_flow")
        elif disposition == "other_verification":
            ident = item.get("verification_ref") or item.get("sink_id")
            if type(ident) is not str or not ident.strip():
                graph.gap(rk, "unresolved_other_verification", "5", auth, part, trigger="always")
                continue
            ov = graph.node("other_verification", ident, partition=part, authority=auth)
            graph.edge(rk, ov, "requirement_verification_sink", auth, part)
            graph.nodes[rk]["links"].add(ov)
            path = _try_path(ident) if "/" in ident else None
            if path:
                graph.edge(graph.path_node(path, category="other_verification"), ov, "path_other_verification",
                           auth, part)
                if _file_exists(root, path):
                    graph.nodes[ov]["flags"].add("files_exist")
                else:
                    graph.gap(ov, "unresolved_other_verification", "5", auth, part, trigger="always")
        elif disposition == "source_gap":
            graph.gap(rk, "requirement_source_gap", "3A", auth, part)

    for item in doc.get("applicability") or []:
        if type(item) is not dict or type(item.get("requirement_id")) is not str:
            continue
        rk = req(item["requirement_id"])
        if item.get("disposition") == "source_gap":
            graph.gap(rk, "requirement_source_gap", "3A", auth, part)
        for ref in item.get("other_verification_refs") or []:
            ov = _other_verification(graph, root, ref, part, auth)
            if ov:
                graph.edge(rk, ov, "requirement_other_verification", auth, part)
                graph.nodes[rk]["links"].add(ov)
            else:
                graph.gap(rk, "unresolved_other_verification_ref", "5", auth, part, trigger="always")

    evidence_files: dict[str, list[str]] = {}
    for ref in doc.get("evidence_source_refs") or []:
        if type(ref) is not dict or type(ref.get("ref")) is not str:
            graph.gap(plan_key, "unresolved_evidence_source_ref", "3B", auth, part, trigger="always")
            continue
        paths, _exists = _link_owned(graph, root, ref, plan_key, "evidence_source_ref", auth, part, "3B")
        evidence_files.setdefault(ref["ref"], []).extend(paths)
    for item in doc.get("requirement_evidence") or []:
        if type(item) is not dict or type(item.get("requirement_id")) is not str:
            continue
        rk = req(item["requirement_id"])
        source_ref = item.get("source_ref")
        linked = list(_walk_paths(item)) + (evidence_files.get(source_ref, []) if type(source_ref) is str else [])
        for path in linked:
            graph.edge(graph.path_node(path), rk, "requirement_evidence_path", auth, part)
        for fid in _str_ids(item.get("flow_ids")):
            req_flow(rk, flow_ref(fid), "requirement_evidence_flow")


def _flow_link(graph: _Graph, link: Any, fid: str, pid: str, part: str, auth: str, kind: str) -> None:
    if type(link) is not dict:
        return
    ends = []
    for side in ("from", "to"):
        end = link.get(side)
        flow_id = end.get("flow_id") if type(end) is dict else None
        ends.append(flow_id if type(flow_id) is str and flow_id.strip() else fid)
    upstream = graph.node("flow", ends[0])
    downstream = graph.node("flow", ends[1])
    for key in (upstream, downstream):
        graph.pending.append(("flow", key, part, auth, pid))
    graph.topo_edge(_topo_flow_node(link.get("from"), fid), _topo_flow_node(link.get("to"), fid))
    if upstream != downstream:
        graph.edge(upstream, downstream, kind, auth, part)
    for use in [link.get("owner")] + list(link.get("state_uses") or []) + list(link.get("command_uses") or []):
        used = _use_key(graph, use, pid, part, auth)
        if used:
            for key in sorted({upstream, downstream}):
                if used != key:
                    graph.edge(used, key, kind + "_owner", auth, part)


def _other_verification(graph: _Graph, root: Path, ref: Any, part: str, auth: str) -> str | None:
    if type(ref) is not dict or type(ref.get("ref")) is not str or not ref["ref"].strip():
        return None
    ov = graph.node("other_verification", ref["ref"], partition=part, authority=auth)
    _paths, exists = _link_owned(graph, root, ref, ov, "other_verification_ref", auth, part, "5",
                                 category="other_verification")
    if exists:
        graph.nodes[ov]["flags"].add("files_exist")
    return ov


def _process_binding(graph: _Graph, root: Path, pid: str, doc: dict, rel: str, manifest_set: set[str]) -> str:
    part = f"plan:{pid}"
    stage = doc.get("stage") if type(doc.get("stage")) is str else "unknown"
    brev = doc.get("binding_revision")
    auth = f"binding:{pid}:{stage}@{brev}"
    plan_key = graph.node("plan", pid, partition=part)

    def flow_ref(fid: str) -> str:
        key = graph.node("flow", fid)
        graph.pending.append(("flow", key, part, auth, pid))
        return key

    for mapping in doc.get("task_mappings") or []:
        if type(mapping) is not dict:
            continue
        tids = _task_ids([mapping.get("task_id")])
        if not tids:
            continue
        tk = graph.node("task", tids[0], partition=part, authority=auth)
        graph.edge(tk, plan_key, "task_plan", auth, part)
        for fid in _str_ids(mapping.get("flow_ids")):
            fk = flow_ref(fid)
            graph.edge(tk, fk, "task_flow", auth, part)
            graph.edge(fk, tk, "flow_task", auth, part)
            graph.nodes[tk]["links"].add(fk)
        for rid in _str_ids(mapping.get("requirement_ids")):
            rk = graph.node("requirement", rid)
            graph.edge(tk, rk, "task_requirement", auth, part)
            graph.edge(rk, tk, "requirement_task", auth, part)
        for oid in _str_ids(mapping.get("obligation_ids")):
            ok = graph.node("obligation", f"{pid}:{oid}", partition=part, authority=auth)
            graph.edge(tk, ok, "task_obligation", auth, part)
            graph.edge(ok, tk, "obligation_task", auth, part)
            graph.nodes[tk]["links"].add(ok)
        for kind in _str_ids(mapping.get("part_kinds")):
            graph.edge(graph.node("part", f"{pid}:{kind}", partition=part), tk, "part_task", auth, part)
    for item in doc.get("parts") or []:
        if type(item) is dict and type(item.get("kind")) is str:
            pk = graph.node("part", f"{pid}:{item['kind']}", partition=part, authority=auth)
            graph.edge(pk, plan_key, "part_plan", auth, part)
    for item in doc.get("implementation_objects") or []:
        if type(item) is not dict or type(item.get("id")) is not str:
            continue
        ik = graph.node("implementation_object", f"{pid}:{item['id']}", partition=part, authority=auth)
        graph.owner(ik, pid, "implementation_object", item["id"], brev)
        existing = item.get("availability") == "existing"
        graph.nodes[ik]["flags"].add("existing" if existing else "planned")
        for tid in _task_ids(item.get("responsible_task_ids")):
            tk = graph.node("task", tid)
            graph.edge(ik, tk, "implementation_task", auth, part)
            graph.edge(tk, ik, "task_implementation_object", auth, part)
        part_kind = IMPL_PART.get(item.get("kind"), "domain_rules")
        graph.edge(ik, graph.node("part", f"{pid}:{part_kind}", partition=part), "implementation_part", auth, part)
        target = item.get("target_ref")
        if target is not None:
            _link_owned(graph, root, target, ik, "target_ref", auth, part, "4", require_exists=existing)
        elif existing:
            graph.gap(ik, "unresolved_target_ref", "4", auth, part, trigger="always")
    for item in doc.get("obligations") or []:
        if type(item) is not dict or type(item.get("id")) is not str:
            continue
        ok = graph.node("obligation", f"{pid}:{item['id']}", partition=part, authority=auth)
        graph.owner(ok, pid, "obligation", item["id"], brev)
        responsibility = item.get("responsibility")
        stage5_meta = _tag_payload(responsibility, STAGE5_OBL_PREFIX, (STAGE4_OBL_PREFIX,))
        stage4_meta = _tag_payload(responsibility, STAGE4_OBL_PREFIX, (STAGE5_OBL_PREFIX,))
        for meta in (stage5_meta, stage4_meta):
            if meta.get("__malformed__"):
                graph.gap(ok, "malformed_obligation_metadata", stage, auth, part, trigger="always")
        if stage5_meta.get("category") == "out_of_scope_future":
            graph.nodes[ok]["flags"].add("out_of_scope_future")
        future = set(_str_ids(stage5_meta.get("out_of_scope_future_flow_ids")))
        flow_ids = list(dict.fromkeys(_str_ids(item.get("flow_ids")) + _meta_ids(stage5_meta, "flow_ids")
                                      + _meta_ids(stage4_meta, "flow_ids")))
        for fid in flow_ids:
            fk = flow_ref(fid)
            graph.edge(fk, ok, "flow_obligation", auth, part)
            graph.nodes[ok]["links"].add(fk)
            if fid in future or "out_of_scope_future" in graph.nodes[ok]["flags"]:
                graph.nodes[fk]["flags"].add("out_of_scope_future")
        for rid in _str_ids(item.get("requirement_ids")):
            graph.edge(graph.node("requirement", rid), ok, "requirement_obligation", auth, part)
        test_ids = list(dict.fromkeys(_str_ids(item.get("test_ids")) + _meta_ids(stage5_meta, "test_ids")
                                      + _meta_ids(stage4_meta, "test_ids")))
        for test_id in test_ids:
            tk = graph.node("test", test_id)
            graph.pending.append(("test", tk, part, auth, pid))
            graph.edge(ok, tk, "obligation_test", auth, part)
            graph.nodes[ok]["links"].add(tk)
        verified = False
        for ref in item.get("verification_refs") or []:
            _paths, exists = _link_owned(graph, root, ref, ok, "verification_ref", auth, part, "5")
            verified = verified or exists
        if verified:
            graph.nodes[ok]["flags"].add("verified_refs")
    for ref in doc.get("manifest_refs") or []:
        paths, valid = _owned_paths(ref)
        if not valid:
            graph.gap(plan_key, "unresolved_manifest_ref", "5", auth, part, trigger="always")
        manifest_set.update(paths)
    for ref in doc.get("other_verification_refs") or []:
        ov = _other_verification(graph, root, ref, part, auth)
        if ov:
            graph.edge(ov, plan_key, "other_verification_plan", auth, part)
        else:
            graph.gap(plan_key, "unresolved_other_verification_ref", "5", auth, part, trigger="always")
    return stage


def _scan_test_imports(root: Path, rel: str) -> list[str]:
    """Transitive Godot ``res://`` imports (preload/load) over shared test helpers, reparse-safe."""
    found: set[str] = set()
    seen = {rel}
    queue = deque([rel])
    while queue:
        current = queue.popleft()
        if not current.endswith((".gd", ".cs")):
            continue
        try:
            raw = _read_bytes(root, current)
        except codec.CodecError:
            continue
        if raw is None:
            continue
        for match in RES_RE.findall(raw.decode("utf-8", errors="replace")):
            for candidate in (match, "Tests.Godot/" + match):
                path = _try_path(candidate)
                if path and _file_exists(root, path):
                    if path not in seen:
                        seen.add(path)
                        found.add(path)
                        if path.startswith(TEST_INFRA_PREFIXES) and len(seen) < MAX_IMPORT_SCAN:
                            queue.append(path)
                    break
    found.discard(rel)
    return sorted(found)


def _process_manifest(graph: _Graph, root: Path, rel: str, doc: dict, raw: bytes) -> None:
    mvg_id = doc.get("mvg_id") if type(doc.get("mvg_id")) is str and doc.get("mvg_id").strip() else Path(rel).stem
    part = f"manifest:{mvg_id}"
    auth = f"manifest:{rel}"
    graph.manifests[mvg_id] = rel
    mk = graph.node("manifest", mvg_id, partition=part, authority=auth)
    graph.add_input("manifest", rel, [part], raw, doc, "canonical_json")
    tests = {}
    for test in doc.get("tests") or []:
        if type(test) is not dict or type(test.get("id")) is not str:
            continue
        tk = graph.node("test", test["id"], partition=part, authority=auth)
        graph.owner(tk, None, "test", test["id"], None)
        rec = graph.nodes[tk]
        rec["flags"].add("manifest_test")
        implemented = test.get("state", test.get("status")) == "implemented"
        rec["flags"].add("implemented" if implemented else "planned_test")
        tests[test["id"]] = implemented
        path = _try_path(test.get("path"))
        if path:
            graph.edge(graph.path_node(path, category="test"), tk, "test_path", auth, part)
            if implemented and not _file_exists(root, path):
                graph.gap(tk, "unresolved_test_path", "5", auth, part, trigger="always")
            for imported in _scan_test_imports(root, path):
                graph.edge(graph.path_node(imported), tk, "test_infra_import", auth, part)
        elif test.get("path") is not None:
            graph.gap(tk, "unresolved_test_path", "5", auth, part, trigger="always")
    for flow in doc.get("flows") or []:
        if type(flow) is not dict or type(flow.get("id")) is not str:
            continue
        fid = flow["id"]
        fk = graph.node("flow", fid, partition=part, authority=auth)
        rec = graph.nodes[fk]
        rec["flags"].add("manifest_declared")
        if "planned" in (flow.get("state"), flow.get("status"), flow.get("availability")):
            rec["flags"].add("declared_planned")
        graph.edge(mk, fk, "manifest_flow", auth, part)
        test_ids = _str_ids(flow.get("test_ids"))
        for handoff in flow.get("handoffs") or []:
            if type(handoff) is dict:
                test_ids.extend(t for t in _str_ids(handoff.get("test_ids")) if t not in test_ids)
        for test_id in test_ids:
            tk = graph.node("test", test_id)
            graph.edge(fk, tk, "flow_test", auth, part)
            graph.nodes[fk]["links"].add(tk)
            if test_id not in tests:
                graph.gap(tk, "unresolved_test_ref", "5", auth, part)
            elif tests[test_id] and "declared_planned" not in rec["flags"]:
                rec["flags"].add("implemented_test")
        for rid in _str_ids(flow.get("requirement_ids")):
            rk = graph.node("requirement", rid)
            graph.edge(rk, fk, "requirement_flow", auth, part)
            graph.edge(fk, rk, "flow_requirement", auth, part)
            graph.nodes[rk]["links"].add(fk)
        for cap in _str_ids(flow.get("capability_refs")) + _str_ids(flow.get("capability_ids")):
            graph.edge(graph.node("capability", cap), fk, "capability_flow", auth, part)
        for tid in _task_ids(flow.get("task_ids")):
            tk = graph.node("task", tid)
            graph.edge(tk, fk, "task_flow", auth, part)
            graph.edge(fk, tk, "flow_task", auth, part)
            graph.nodes[tk]["links"].add(fk)
        for value in flow.get("source_paths") or []:
            path = _try_path(value)
            if path is None or not _file_exists(root, path):
                graph.gap(fk, "unresolved_source_path", "5", auth, part, trigger="always")
            if path is None:
                continue
            pk = graph.path_node(path)
            graph.edge(pk, fk, "source_path_flow", auth, part)
            if graph.nodes[pk]["kind"] == "test_infra":
                for test_id in test_ids:
                    graph.edge(pk, graph.node("test", test_id), "test_infra_test", auth, part)
        for handoff in flow.get("handoffs") or []:
            if type(handoff) is not dict:
                continue
            producer = _task_ids([handoff.get("producer_task")])
            receivers = list(dict.fromkeys(_task_ids([handoff.get("consumer_task"), handoff.get("owner_task")])))
            for upstream in producer:
                for downstream in receivers:
                    if upstream != downstream:
                        graph.edge(graph.node("task", upstream), graph.node("task", downstream), "handoff_task",
                                   auth, part)
                    graph.topo_edge(f"task:{upstream}", f"task:{downstream}")
            contract = _try_path(handoff.get("contract_ref"))
            if contract:
                ck = graph.path_node(contract, category="contract")
                graph.edge(ck, fk, "handoff_contract_flow", auth, part)
                for downstream in receivers:
                    graph.edge(ck, graph.node("task", downstream), "handoff_contract_task", auth, part)
                if not _file_exists(root, contract):
                    graph.gap(ck, "unresolved_contract_ref", "4", auth, part, trigger="always")
            elif handoff.get("contract_ref") is not None:
                graph.gap(fk, "unresolved_contract_ref", "4", auth, part, trigger="always")


def _contract_index(graph: _Graph, root: Path) -> dict[str, set[str]]:
    if graph.contract_index is not None:
        return graph.contract_index
    index: dict[str, set[str]] = {}
    pending = [CONTRACTS_DIR]
    while pending:
        current = pending.pop()
        files, dirs, _safe = _safe_listdir(root, current)
        pending.extend(f"{current}/{name}" for name in reversed(dirs))
        for name in files:
            if not name.endswith(".cs"):
                continue
            rel = f"{current}/{name}"
            try:
                raw = _read_bytes(root, rel)
            except codec.CodecError:
                continue
            if raw is None:
                continue
            stem = name[:-3]
            index.setdefault(stem, set()).add(rel)
            match = NAMESPACE_RE.search(raw.decode("utf-8", errors="replace"))
            if match:
                index.setdefault(f"{match.group(1)}.{stem}", set()).add(rel)
    graph.contract_index = index
    return index


def _resolve_contract_symbol(graph: _Graph, root: Path, value: str) -> list[str]:
    symbol = value.strip()
    if symbol.endswith(".cs"):
        symbol = symbol[:-3]
    if not SYMBOL_RE.fullmatch(symbol):
        return []
    index = _contract_index(graph, root)
    hits = index.get(symbol)
    if not hits and "." in symbol:
        hits = index.get(symbol.rsplit(".", 1)[-1])
    return sorted(hits or [])


def _process_triplet(graph: _Graph, root: Path) -> None:
    try:
        loaded = _read_json(root, TASKS_PATH)
    except codec.CodecError:
        loaded = None
        graph.gap(f"triplet:{TASKS_PATH}", "triplet_unreadable", "3C", TASKS_PATH, "governance", trigger="always")
    else:
        if loaded is None:
            graph.gap(f"triplet:{TASKS_PATH}", "triplet_missing", "3C", TASKS_PATH, "governance", trigger="always")
    if loaded is not None:
        doc, _raw = loaded
        tasks = None
        if type(doc) is dict:
            master = doc.get("master")
            tasks = master.get("tasks") if type(master) is dict else doc.get("tasks")
        elif type(doc) is list:
            tasks = doc
        if type(tasks) is not list:
            graph.gap(f"triplet:{TASKS_PATH}", "triplet_unreadable", "3C", TASKS_PATH, "governance", trigger="always")
            tasks = []
        for task in tasks:
            if type(task) is not dict:
                continue
            tids = _task_ids([task.get("id")])
            if not tids:
                continue
            tid = tids[0]
            part = f"task:{tid}"
            tk = graph.node("task", tid, partition=part, authority=f"triplet:{TASKS_PATH}")
            graph.nodes[tk]["flags"].add("in_triplet")
            graph.owner(tk, None, "task", tid, None)
            projection = _strip_volatile(task)
            graph.add_input("task_definition", f"{TASKS_PATH}#task:{tid}", [part], _canonical_bytes(projection),
                            projection, "task_definition_projection_no_status")
            for dep in _task_ids(task.get("dependencies")):
                graph.edge(graph.node("task", dep), tk, "task_dependency", f"triplet:{TASKS_PATH}", part)
                graph.topo_edge(f"task:{dep}", tk)
    for view, rel in VIEW_PATHS:
        try:
            loaded = _read_json(root, rel)
        except codec.CodecError:
            graph.gap(f"triplet:{rel}", "triplet_unreadable", "3C", rel, "governance", trigger="always")
            continue
        if loaded is None:
            continue
        if type(loaded[0]) is not list:
            graph.gap(f"triplet:{rel}", "triplet_unreadable", "3C", rel, "governance", trigger="always")
            continue
        for entry in loaded[0]:
            if type(entry) is not dict:
                continue
            tids = _task_ids([entry.get("taskmaster_id")])
            if not tids:
                continue
            tid = tids[0]
            part = f"task:{tid}"
            auth = f"triplet:{rel}"
            tk = graph.node("task", tid, partition=part)
            projection = _strip_volatile(entry)
            graph.add_input("task_view", f"{rel}#{view}:{tid}", [part], _canonical_bytes(projection), projection,
                            "task_definition_projection_no_status")
            for field, category in (("contractRefs", "contract"), ("overlay_refs", None), ("test_refs", "test")):
                values = entry.get(field) if type(entry.get(field)) is list else []
                for value in values:
                    if type(value) is not str or not value.strip():
                        continue
                    if "/" in value:
                        path = _try_path(value)
                        if path is None or not _file_exists(root, path):
                            graph.gap(tk, f"unresolved_triplet_{field}", "3C", auth, part, trigger="always")
                        if path:
                            graph.edge(graph.path_node(path, category=category), tk, "triplet_" + field, auth, part)
                    elif field == "contractRefs":
                        targets = _resolve_contract_symbol(graph, root, value)
                        if not targets:
                            graph.gap(tk, "unresolved_contract_ref", "4", auth, part, trigger="always")
                        for path in targets:
                            graph.edge(graph.path_node(path, category="contract"), tk, "triplet_contractRefs",
                                       auth, part)
            for dep in _task_ids(entry.get("depends_on")):
                graph.edge(graph.node("task", dep), tk, "task_dependency", auth, part)
                graph.topo_edge(f"task:{dep}", tk)


def _process_origins(graph: _Graph, root: Path) -> None:
    try:
        loaded = _read_json(root, ORIGINS_PATH)
    except codec.CodecError:
        graph.gap(f"origins:{ORIGINS_PATH}", "origins_unreadable", "3C", ORIGINS_PATH, "governance", trigger="always")
        return
    if loaded is None:
        return
    if type(loaded[0]) is not dict:
        graph.gap(f"origins:{ORIGINS_PATH}", "origins_unreadable", "3C", ORIGINS_PATH, "governance", trigger="always")
        return
    header = {k: loaded[0].get(k) for k in ("schema_version", "origins_id", "frozen_legacy_refs")}
    graph.add_input("origins_header", f"{ORIGINS_PATH}#governance", ["governance"], _canonical_bytes(header), header,
                    "origins_structure_without_revision")
    for entry in loaded[0].get("tasks") or []:
        if type(entry) is not dict:
            continue
        tids = _task_ids([entry.get("task_id")])
        if not tids:
            continue
        part = f"task:{tids[0]}"
        auth = f"origins:{ORIGINS_PATH}"
        tk = graph.node("task", tids[0], partition=part, authority=auth)
        graph.add_input("task_origin", f"{ORIGINS_PATH}#task:{tids[0]}", [part], _canonical_bytes(entry), entry,
                        "canonical_json")
        for ref in entry.get("source_refs") or []:
            _link_owned(graph, root, ref, tk, "origin_source_ref", auth, part, "3C")
        for ref in entry.get("plan_refs") or []:
            if type(ref) is dict and type(ref.get("entity_id")) is str:
                graph.edge(tk, graph.node("plan", ref["entity_id"]), "task_origin_plan", auth, part)


def _pending_journals(root: Path) -> list[str]:
    """Top-level pending B-route/legacy planning journals and markers (never a recursive rglob)."""
    found: list[str] = []

    def check(rel: str, *, require_status: bool) -> None:
        try:
            loaded = _read_json(root, rel, allow_logs=True)
        except codec.CodecError:
            found.append(rel)
            return
        if loaded is None:
            return
        doc = loaded[0]
        if type(doc) is not dict:
            found.append(rel)
            return
        state = doc.get("status", doc.get("state"))
        if state is None:
            if require_status:
                found.append(rel)
            return
        if str(state).strip().lower() not in TERMINAL_JOURNAL_STATES:
            found.append(rel)

    def listing(rel: str) -> tuple[list[str], list[str]]:
        files, dirs, safe = _safe_listdir(root, rel, allow_logs=True)
        if not safe:
            found.append(rel)
        return files, dirs

    files, _dirs = listing(OPERATIONS_STORE)
    for name in files:
        if name.endswith(".json"):
            check(f"{OPERATIONS_STORE}/{name}", require_status=False)
    _files, op_dirs = listing(f"{OPERATIONS_STORE}/operations")
    for directory in op_dirs:
        files, _sub = listing(f"{OPERATIONS_STORE}/operations/{directory}")
        for name in files:
            if name.endswith(".json"):
                check(f"{OPERATIONS_STORE}/operations/{directory}/{name}", require_status=False)
    for marker in PENDING_MARKERS:
        if _file_exists(root, marker) or os.path.lexists(root.joinpath(*marker.split("/"))):
            found.append(marker)
    for base in LEGACY_PLANNING_DIRS:
        _files, dirs = listing(base)
        for directory in dirs:
            check(f"{base}/{directory}/apply-journal.json", require_status=True)
    return sorted(set(found))


def _ref_sort_key(ref: dict) -> tuple:
    revision = ref.get("revision") if type(ref.get("revision")) is int else 0
    return (revision, str(ref.get("path")))


def _load_catalog(graph: _Graph, root: Path) -> dict | None:
    try:
        loaded = _read_json(root, CATALOG_PATH)
    except codec.CodecError:
        graph.gap(f"catalog:{CATALOG_PATH}", "catalog_unreadable", "3B", CATALOG_PATH, "governance", trigger="always")
        return None
    if loaded is None:
        graph.gap(f"catalog:{CATALOG_PATH}", "catalog_missing", "3B", CATALOG_PATH, "governance", trigger="always")
        return None
    catalog = loaded[0]
    if type(catalog) is not dict or catalog.get("schema_version") != CATALOG_SCHEMA:
        graph.gap(f"catalog:{CATALOG_PATH}", "catalog_unreadable", "3B", CATALOG_PATH, "governance", trigger="always")
        return None
    return catalog


def _build(root: Path, manifest_paths: list[str], plan_ids: list[str] | None) -> _Graph:
    graph = _Graph()
    catalog_plans: dict[str, dict[str, list]] = {}
    catalog = _load_catalog(graph, root)
    if catalog is not None:
        for head in catalog.get("scope_heads") or []:
            if type(head) is not dict:
                continue
            for field in ("plan_refs", "binding_refs"):
                for ref in head.get(field) or []:
                    if type(ref) is dict and type(ref.get("entity_id")) is str:
                        slot = catalog_plans.setdefault(ref["entity_id"], {"plan_refs": [], "binding_refs": [],
                                                                           "definition_owners": [], "task_index": []})
                        if ref not in slot[field]:
                            slot[field].append(ref)
        for row in catalog.get("definition_owners") or []:
            pref = row.get("plan_ref") if type(row) is dict else None
            if type(pref) is not dict or type(pref.get("entity_id")) is not str:
                continue
            if type(row.get("kind")) is str and type(row.get("definition_id")) is str:
                graph.def_owners[(row["kind"], row["definition_id"])] = (pref["entity_id"], pref.get("revision"))
            if pref["entity_id"] in catalog_plans:
                catalog_plans[pref["entity_id"]]["definition_owners"].append(row)
        for row in catalog.get("task_index") or []:
            if type(row) is not dict:
                continue
            for pref in row.get("plan_refs") or []:
                if type(pref) is dict and pref.get("entity_id") in catalog_plans:
                    catalog_plans[pref["entity_id"]]["task_index"].append(row)
        header = {k: catalog.get(k) for k in ("schema_version", "catalog_id", "policy_ref", "origins_ref")}
    else:
        header = {"unavailable": CATALOG_PATH}
    graph.add_input("catalog_header", f"{CATALOG_PATH}#governance", ["governance"], _canonical_bytes(header),
                    header, "catalog_structure_without_revision")
    for pid in sorted(catalog_plans):
        fragment = catalog_plans[pid]
        normalized = {key: sorted(value, key=_dumps) for key, value in fragment.items()}
        graph.add_input("catalog_entry", f"{CATALOG_PATH}#plan:{pid}", [f"plan:{pid}"],
                        _canonical_bytes(normalized), normalized, "catalog_plan_entry")

    selected = sorted(catalog_plans)
    if plan_ids:
        for pid in plan_ids:
            if pid not in catalog_plans:
                graph.gap(f"plan:{pid}", "unknown_plan_filter", "3B", CATALOG_PATH, "governance", trigger="always")
        selected = [pid for pid in selected if pid in set(plan_ids)]

    manifest_set: set[str] = set(manifest_paths)
    for pid in selected:
        info = catalog_plans[pid]
        part = f"plan:{pid}"
        graph.plans[pid] = {"stages": set(), "revision": None, "path": None}
        refs = sorted(info["plan_refs"], key=_ref_sort_key)
        plan_rel = _try_path(refs[-1].get("path")) if refs else None
        plan_doc = None
        if plan_rel:
            try:
                plan_loaded = _read_json(root, plan_rel)
            except codec.CodecError:
                plan_loaded = None
            if plan_loaded is not None and type(plan_loaded[0]) is dict:
                plan_doc, plan_raw = plan_loaded
                graph.add_input("plan", plan_rel, [part], plan_raw, plan_doc, "canonical_json")
        if plan_doc is None:
            graph.node("plan", pid, partition=part)
            graph.gap(f"plan:{pid}", "plan_unreadable", "3B", plan_rel or CATALOG_PATH, part, trigger="always")
        else:
            rev = plan_doc.get("revision")
            graph.plans[pid].update(revision=rev, path=plan_rel)
            _process_plan(graph, root, pid, rev, plan_doc, plan_rel)
        for ref in sorted(info["binding_refs"], key=_ref_sort_key):
            binding_rel = _try_path(ref.get("path"))
            binding_loaded = None
            if binding_rel:
                try:
                    binding_loaded = _read_json(root, binding_rel)
                except codec.CodecError:
                    binding_loaded = None
            if binding_loaded is None or type(binding_loaded[0]) is not dict:
                graph.gap(f"plan:{pid}", "binding_unreadable", "4", binding_rel or CATALOG_PATH, part, trigger="always")
                continue
            binding_doc, binding_raw = binding_loaded
            graph.add_input("binding", binding_rel, [part], binding_raw, binding_doc, "canonical_json")
            stage = _process_binding(graph, root, pid, binding_doc, binding_rel, manifest_set)
            graph.plans[pid]["stages"].add(stage)
        if "5" not in graph.plans[pid]["stages"]:
            graph.gap(f"plan:{pid}", "missing_stage5_binding", "5", CATALOG_PATH, part, trigger="always")

    discovered, _dirs, safe = _safe_listdir(root, MANIFEST_DIR)
    if not safe:
        graph.gap(f"manifest_dir:{MANIFEST_DIR}", "manifest_dir_unsafe", "5", MANIFEST_DIR, "governance",
                  trigger="always")
    candidates = {f"{MANIFEST_DIR}/{name}" for name in discovered if name.endswith(".json")} | manifest_set
    for rel in sorted(candidates):
        try:
            manifest_loaded = _read_json(root, rel)
        except codec.CodecError:
            manifest_loaded = None
        if manifest_loaded is None or type(manifest_loaded[0]) is not dict \
                or manifest_loaded[0].get("schema_version") != MVG_SCHEMA:
            graph.gap(f"manifest:{rel}", "manifest_unreadable", "5", rel, "governance", trigger="always")
            continue
        _process_manifest(graph, root, rel, manifest_loaded[0], manifest_loaded[1])

    for rel in _pending_journals(root):
        graph.gap(f"journal:{rel}", "pending_journal", "3B", rel, "governance", trigger="always")
    _process_triplet(graph, root)
    _process_origins(graph, root)
    _finalize(graph)
    return graph


def _finalize(graph: _Graph) -> None:
    for kind, key, part, auth, _pid in graph.pending:
        flags = graph.nodes[key]["flags"]
        if kind == "flow" and not flags & {"plan_declared", "manifest_declared"}:
            graph.gap(key, "unresolved_flow_ref", "4", auth, part)
        elif kind == "test" and "manifest_test" not in flags:
            graph.gap(key, "unresolved_test_ref", "5", auth, part)
        elif kind == "definition" and "defined" not in flags:
            graph.gap(key, "unresolved_definition_owner", "3B", auth, part)
    for key in sorted(graph.nodes):
        rec = graph.nodes[key]
        if rec["kind"] not in OWNED_DEFINITION_KINDS:
            continue
        local = rec["id"] if rec["kind"] == "flow" else rec["id"].split(":", 1)[-1]
        owner = graph.def_owners.get((rec["kind"], local))
        if owner is None:
            continue
        owner_pid, owner_rev = owner
        declared = rec["semantic_owner"]["owner_plan_id"] if rec["semantic_owner"] else None
        if declared is not None and declared != owner_pid:
            graph.gap(key, "definition_owner_conflict", "3B", CATALOG_PATH, f"plan:{declared}")
        rec["semantic_owner"] = {"owner_plan_id": owner_pid, "kind": rec["kind"], "id": local, "revision": owner_rev}
    for rec in graph.nodes.values():
        kind, flags = rec["kind"], rec["flags"]
        if kind == "flow":
            # Monotonic: an active Flow with implemented tests stays current regardless of new planned objects.
            current = "implemented_test" in flags and "declared_planned" not in flags
        elif kind == "test":
            current = "implemented" in flags
        elif kind == "task":
            current = "in_triplet" in flags
        elif kind == "implementation_object":
            current = "existing" in flags
        elif kind == "other_verification":
            current = "files_exist" in flags
        else:
            current = True
        rec["availability"] = "current" if current else "planned"
    for kind in ("obligation", "requirement"):
        for rec in graph.nodes.values():
            if rec["kind"] != kind:
                continue
            linked = [graph.nodes[k]["availability"] for k in rec["links"] if k in graph.nodes]
            if kind == "obligation" and "out_of_scope_future" in rec["flags"]:
                current = False
            else:
                current = "current" in linked or "verified_refs" in rec["flags"]
            rec["availability"] = "current" if current else "planned"
    for rec in graph.nodes.values():
        if rec["kind"] == "task":
            backs = [graph.nodes[k] for k in rec["links"] if k in graph.nodes
                     and graph.nodes[k]["kind"] in ("flow", "obligation", "test")]
            rec["regression"] = rec["availability"] == "current" and any(
                b["availability"] == "current" for b in backs)
        else:
            rec["regression"] = rec["availability"] == "current"
        if rec["semantic_owner"] is None:
            rec["semantic_owner"] = {"owner_plan_id": None, "kind": rec["kind"], "id": rec["id"], "revision": None}
    graph.gaps.sort(key=lambda g: (g["partition_key"], g["entity"], g["reason"]))


# ---------------------------------------------------------------------------
# Change roots
# ---------------------------------------------------------------------------

def _parse_root(root: Path, raw: Any) -> dict[str, str]:
    if type(raw) is dict:
        if set(raw) - {"kind", "id"} or type(raw.get("kind")) is not str or type(raw.get("id")) is not str:
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "change root object with exactly kind and id", raw)
        prefix, rest = raw["kind"], raw["id"]
        if prefix not in ROOT_ALIASES:
            raise _err(codec.ReasonCode.INVALID_ENUM, sorted(ROOT_ALIASES), prefix)
    elif type(raw) is str and raw.strip():
        if raw != raw.strip():
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "unpadded change root", raw)
        prefix, sep, rest = raw.partition(":")
        if not sep or prefix not in ROOT_ALIASES:
            prefix, rest = "path", raw
    else:
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "nonempty change root string or object", type(raw).__name__)
    kind = ROOT_ALIASES[prefix]
    if kind in PATH_KINDS:
        rel = _normalize_rel(rest)
        _safe_target(root, rel)
        if kind != "path" and _classify_path(rel) != kind:
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"{kind} change root matching path classification",
                       {"path": rel, "classified_as": _classify_path(rel)})
        return {"kind": kind, "id": rel}
    if kind == "task":
        if type(rest) is not str or not TASK_ID_RE.fullmatch(rest):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "strict ASCII positive integer task id", rest)
        return {"kind": kind, "id": str(codec.validate_task_id(int(rest)))}
    if kind in DEFINITION_KINDS or kind in LOCAL_ID_KINDS:
        parts = rest.split(":")
        if len(parts) > 2 or not all(IDENT_RE.fullmatch(p) for p in parts):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "<id> or <plan_id>:<id> reference", rest)
        return {"kind": kind, "id": rest}
    codec.validate_business_id(rest)
    if not LOOSE_IDENT_RE.fullmatch(rest) or ".." in rest.split("/"):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"portable {kind} identifier", rest)
    return {"kind": kind, "id": rest}


def _resolve_root(graph: _Graph, root: Path, parsed: dict[str, str]) -> tuple[list[str], dict | None]:
    kind, ident = parsed["kind"], parsed["id"]
    display = f"{kind}:{ident}"
    keys: list[str] = []
    if kind in PATH_KINDS:
        key = graph.path_index.get(ident)
        if key is not None and graph.adj.get(key):
            keys = [key]
    elif kind in DEFINITION_KINDS or kind in LOCAL_ID_KINDS:
        if ":" in ident:
            key = f"{kind}:{ident}"
            if key in graph.nodes:
                keys = [key]
        else:
            keys = sorted(graph.local_index.get((kind, ident), set()))
        keys = [k for k in keys if kind not in DEFINITION_KINDS or "defined" in graph.nodes[k]["flags"]]
    else:
        key = f"{kind}:{ident}"
        if key in graph.nodes:
            keys = [key]
    if keys:
        return keys, None
    if kind in PATH_KINDS:
        reason = "unmapped_change_root" if _file_exists(root, ident) else "unresolvable_change_root"
        stage = "4"
    else:
        reason = "unresolvable_change_root"
        stage = {"task": "3C", "test": "5", "obligation": "5", "implementation_object": "4", "part": "4"}.get(kind, "3B")
    return [], {"entity": display, "reason": reason, "owning_stage": stage, "authority_ref": None,
                "partition_key": "governance", "scope": "global"}


# ---------------------------------------------------------------------------
# Closure
# ---------------------------------------------------------------------------

def _bfs(graph: _Graph, seeds: list[str]) -> dict[str, tuple[str | None, str | None, str | None]]:
    """Cycle-safe BFS: accounting-only nodes are reported but only follow sink edges one hop."""
    parents: dict[str, tuple[str | None, str | None, str | None]] = {}
    mode: dict[str, str] = {}
    queue: deque[str] = deque()
    for seed in seeds:
        if seed not in parents:
            parents[seed] = (None, None, None)
            mode[seed] = "full"
            queue.append(seed)
    while queue:
        node = queue.popleft()
        current = mode[node]
        if current == "sink":
            continue
        for target in sorted(graph.adj[node]):
            entries = sorted(graph.adj[node][target])
            if current == "accounting":
                entries = [e for e in entries if e[0] in ACCOUNTING_FOLLOW]
                if not entries:
                    continue
                new_mode, chosen = "sink", entries[0]
            else:
                full = [e for e in entries if e[0] not in ACCOUNTING_EDGES]
                new_mode, chosen = ("full", full[0]) if full else ("accounting", entries[0])
            previous = mode.get(target)
            rank = {"sink": 0, "accounting": 1, "full": 2}
            if previous is None or rank[new_mode] > rank[previous]:
                if previous is None:
                    parents[target] = (node, chosen[0], chosen[1])
                mode[target] = new_mode
                queue.append(target)
    return parents


def _path_to(parents: dict, key: str) -> list[dict[str, Any]]:
    chain = []
    seen: set[str] = set()
    current: str | None = key
    while current is not None and current not in seen:
        seen.add(current)
        parent, edge_kind, authority = parents[current]
        chain.append({"node": current, "via_edge": edge_kind, "authority": authority})
        current = parent
    chain.reverse()
    return chain


def _expansion_seeds(graph: _Graph, scope: str) -> list[str]:
    if scope == "global":
        return sorted(k for k, rec in graph.nodes.items() if rec["kind"] in REPORTED_KINDS)
    return sorted(k for k, rec in graph.nodes.items()
                  if scope in rec["partitions"] and (rec["kind"] in REPORTED_KINDS or rec["kind"] in DEFINITION_KINDS))


def _cycle_witnesses(graph: _Graph, reached: dict[str, Any]) -> list[dict[str, Any]]:
    """Genuine directed cycles over Flow node topology, cross-Flow handoffs, Task and prior-Requirement edges."""
    topo = {key: set(value) for key, value in graph.topo.items()}
    result = []
    for component in components(topo):
        nodes = sorted(component)
        if len(nodes) == 1 and nodes[0] not in topo[nodes[0]]:
            continue
        entities = sorted({node.split("#", 1)[0] for node in nodes})
        if not any(entity in reached for entity in entities):
            continue
        result.append({"nodes": entities, "topology_nodes": nodes, "size": len(nodes),
                       "kinds": sorted({entity.split(":", 1)[0] for entity in entities}),
                       "classification": "governed_cycle_terminated"})
    result.sort(key=lambda c: (c["nodes"], c["topology_nodes"]))
    return result


def _compute(graph: _Graph, root: Path, parsed_roots: list[dict[str, str]], *, plan_ids: list[str],
             manifest_paths: list[str], operation: str,
             extra_expansions: Iterable[tuple[str, str]] = ()) -> dict[str, Any]:
    reached: dict[str, dict[str, Any]] = {}
    unknown_items: list[dict[str, Any]] = []
    expansion_reasons: list[str] = []
    root_displays = []

    def record(key: str, display: str, witness: list[dict], via: str, flag: str | None = None) -> None:
        item = reached.setdefault(key, {"roots": set(), "witness": None, "via": via, "flags": set()})
        item["roots"].add(display)
        if item["witness"] is None or (item["via"] != "reverse_edge" and via == "reverse_edge"):
            item["witness"] = witness
            item["via"] = via
        if flag:
            item["flags"].add(flag)

    pending_expansions: list[tuple[str, str, str, list[str]]] = []
    ordered_roots = sorted(parsed_roots, key=lambda r: (r["kind"], r["id"]))
    for parsed in ordered_roots:
        display = f"{parsed['kind']}:{parsed['id']}"
        root_displays.append(display)
        keys, unknown = _resolve_root(graph, root, parsed)
        if parsed["kind"] == "plan" and keys:
            keys = sorted(set(keys) | set(_expansion_seeds(graph, f"plan:{parsed['id']}")))
        if unknown is not None:
            unknown_items.append({k: unknown[k] for k in ("entity", "reason", "owning_stage", "authority_ref", "partition_key")})
            pending_expansions.append(("global", unknown["reason"], display, [display]))
            continue
        for key in keys:
            parents = _bfs(graph, [key])
            for target in parents:
                witness = _path_to(parents, target)
                witness[0] = {"node": witness[0]["node"], "via_edge": "change_root", "authority": display}
                record(target, display, witness, "reverse_edge")
    for reason, entity in extra_expansions:
        unknown_items.append({"entity": entity, "reason": reason, "owning_stage": "3B", "authority_ref": None,
                              "partition_key": "governance"})
        pending_expansions.append(("global", reason, entity, sorted(root_displays)))

    triggered: set[int] = set()
    expanded_scopes: set[str] = set()
    while True:
        for index, gap in enumerate(graph.gaps):
            if index in triggered:
                continue
            hit = gap["trigger"] == "always" or gap["entity"] in reached or any(
                gap["partition_key"] in graph.nodes[k]["partitions"] for k in reached if k in graph.nodes)
            if not hit:
                continue
            triggered.add(index)
            unknown_items.append({k: gap[k] for k in ("entity", "reason", "owning_stage", "authority_ref", "partition_key")})
            always = gap["trigger"] == "always" or gap["partition_key"] == "governance"
            scope = "global" if always else gap["partition_key"]
            pending_expansions.append((scope, gap["reason"], gap["entity"], sorted(root_displays)))
        if not pending_expansions:
            break
        scope, reason, entity, causes = pending_expansions.pop(0)
        expansion_reasons.append(f"{reason}:{entity}->{scope}")
        if scope in expanded_scopes:
            continue
        expanded_scopes.add(scope)
        parents = _bfs(graph, _expansion_seeds(graph, scope))
        for target in parents:
            chain = _path_to(parents, target)
            witness = [{"node": causes[0], "via_edge": "change_root", "authority": causes[0]},
                       {"node": chain[0]["node"], "via_edge": "conservative_expansion", "authority": reason}] + chain[1:]
            for cause in causes:
                record(target, cause, witness, "conservative_expansion", reason)

    conservative = bool(unknown_items)
    lists: dict[str, list[dict[str, Any]]] = {name: [] for _, name in REPORTED_LISTS}
    list_by_kind = dict(REPORTED_LISTS)
    shared_rules = []
    covered: set[str] = {"governance"}
    for key in sorted(reached):
        rec = graph.nodes.get(key)
        if rec is None:
            continue
        covered |= rec["partitions"]
        info = reached[key]
        authorities = sorted(rec["authorities"])
        base = {
            "entity_kind": rec["kind"],
            "entity_id": rec["id"],
            "availability": rec["availability"],
            "immediate_regression_required": rec["regression"],
            "semantic_owner": rec["semantic_owner"],
            "source_refs": authorities,
            "plan_revisions": [a for a in authorities if a.startswith("plan:")],
            "binding_revisions": [a for a in authorities if a.startswith("binding:")],
            "manifest_refs": sorted({a.split(":", 1)[1] for a in authorities if a.startswith("manifest:")}),
            "partition_keys": sorted(rec["partitions"]),
            "root_causes": sorted(info["roots"]),
            "witness_path": info["witness"],
            "reached_by": info["via"],
            "unknown_flags": sorted(info["flags"]),
        }
        if rec["kind"] in OBL_LINK_KINDS:
            base["obligation_ids"] = sorted(graph.nodes[o]["id"] for o in graph.obl_links.get(key, ()))
        if rec["kind"] in list_by_kind:
            lists[list_by_kind[rec["kind"]]].append(base)
        elif rec["kind"] in DEFINITION_KINDS:
            shared_rules.append({k: base[k] for k in ("entity_kind", "entity_id", "semantic_owner", "root_causes",
                                                       "witness_path", "source_refs")})

    if not any(lists[name] for name in NONEMPTY_LISTS):
        raise _err(codec.ReasonCode.UNRESOLVED_REFERENCE,
                   "provable nonempty impact boundary (never an empty closure)",
                   {"change_roots": root_displays, "unknown_items": [u["reason"] for u in unknown_items]})

    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "ok": True,
        "status": "computed",
        "operation": operation,
        "reason_code": codec.ReasonCode.OK.value,
        "change_roots": [{"kind": r["kind"], "id": r["id"]} for r in ordered_roots],
        "plan_ids_filter": list(plan_ids),
        "manifest_paths_filter": list(manifest_paths),
        **lists,
        "shared_rules": shared_rules,
        "unique_requirement_count": len(lists["impacted_requirements"]),
        "cycle_witnesses": _cycle_witnesses(graph, reached),
        "conservative_expanded": conservative,
        "unknown_items": unknown_items,
        "expansion_reasons": expansion_reasons,
        "covered_partitions": sorted(covered),
        "reused": False,
        "invalidated_partitions": [],
        "recomputed_partitions": [],
        "reused_partitions": [],
        "diagnostics": [],
        "report_path": None,
        **INVARIANT_FLAGS,
    }
    _attach_identities(payload, _identities(graph, root, set(covered)))
    _seal(payload)
    return payload


def _identities(graph: _Graph, root: Path, covered: set[str], extra_locators: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Typed input identities: records, every referenced file of covered partitions, and governance gaps."""
    result = [dict(item) for item in graph.inputs if covered & set(item["partition_keys"])]
    locators = set(extra_locators)
    for rec in graph.nodes.values():
        if rec["kind"] in PATH_KINDS and covered & rec["partitions"]:
            locators.add(rec["id"])
    for rel in sorted(locators):
        key = graph.path_index.get(rel)
        partitions = sorted(graph.nodes[key]["partitions"]) if key else [f"path:{rel}"]
        category = graph.file_cat.get(rel) or (graph.nodes[key]["kind"] if key else _classify_path(rel))
        raw = None
        if _file_exists(root, rel):
            try:
                raw = _read_bytes(root, rel)
            except codec.CodecError:
                raw = None
        if raw is None:
            marker = {"absent": rel}
            result.append({"category": category, "locator": rel, "partition_keys": partitions,
                           "raw_digest": codec.raw_digest(_canonical_bytes(marker)),
                           "normalized_digest": codec.canonical_digest(marker), "normalization_mode": "absent_path",
                           "codec_version": codec.CODEC_VERSION})
        else:
            result.append({"category": category, "locator": rel, "partition_keys": partitions,
                           "raw_digest": codec.raw_digest(raw), "normalized_digest": codec.raw_digest(raw),
                           "normalization_mode": "raw_bytes", "codec_version": codec.CODEC_VERSION})
    relevant = [g for g in graph.gaps
                if g["partition_key"] in covered or g["partition_key"] == "governance" or g["trigger"] == "always"]
    result.append({"category": "governance_gaps", "locator": "graph.gaps", "partition_keys": ["governance"],
                   "raw_digest": codec.raw_digest(_canonical_bytes(relevant)),
                   "normalized_digest": codec.canonical_digest(relevant), "normalization_mode": "canonical_json",
                   "codec_version": codec.CODEC_VERSION})
    result.sort(key=lambda i: (i["category"], i["locator"]))
    return result


def _partition_digests(identities: list[dict[str, Any]], covered: Iterable[str]) -> dict[str, str]:
    result = {}
    for key in sorted(set(covered)):
        rows = sorted([i["category"], i["locator"], i["normalized_digest"], i["normalization_mode"]]
                      for i in identities if key in i["partition_keys"])
        result[key] = codec.canonical_digest(rows)
    return result


def _attach_identities(payload: dict[str, Any], identities: list[dict[str, Any]]) -> None:
    payload["input_identities"] = identities
    payload["partition_digests"] = _partition_digests(identities, payload["covered_partitions"])
    payload["impact_input_digest"] = codec.canonical_digest({"partition_digests": payload["partition_digests"]})


def _proof_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Full canonical proof content: every field except volatile status/metrics/report bookkeeping."""
    return {key: value for key, value in payload.items() if key not in PROOF_VOLATILE_FIELDS}


def _seal(payload: dict[str, Any]) -> None:
    payload["impact_proof_id"] = codec.canonical_digest(_proof_body(payload))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _blocked(diag: dict[str, Any], operation: Any, started: float) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "ok": False,
        "status": "blocked",
        "operation": operation if type(operation) is str else None,
        "reason_code": diag["reason_code"],
        "reused": False,
        "conservative_expanded": False,
        **{name: [] for _, name in REPORTED_LISTS},
        "shared_rules": [],
        "unknown_items": [],
        "expansion_reasons": [],
        "invalidated_partitions": [],
        "recomputed_partitions": [],
        "reused_partitions": [],
        "impact_proof_id": None,
        "diagnostics": [diag],
        "report_path": None,
        "metrics": {"active_elapsed_seconds": _elapsed(started)},
        **INVARIANT_FLAGS,
    }


def _io_diag(exc: Exception) -> dict[str, Any]:
    code = codec.ReasonCode.UNSAFE_PATH if isinstance(exc, ValueError) else codec.ReasonCode.READ_ERROR
    return codec.Diagnostic(code, codec.Stage.PATH, None, "safe readable repository inputs",
                            type(exc).__name__, None).to_dict()


def _write_report(target: Path, rel: str, payload: dict[str, Any]) -> None:
    if os.path.lexists(target):
        raise _err(codec.ReasonCode.CONFLICT, "new non-existing report path", rel, entity=rel, stage=codec.Stage.PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    inventory.no_reparse(target.parent)
    payload["report_path"] = rel
    text = _dumps(payload) + "\n"
    try:
        with open(target, "xb") as handle:
            handle.write(text.encode("utf-8"))
    except FileExistsError as exc:
        payload["report_path"] = None
        raise _err(codec.ReasonCode.CONFLICT, "new non-existing report path", rel, entity=rel,
                   stage=codec.Stage.PATH) from exc


def _append_event(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    inventory.no_reparse(target.parent)
    inventory.no_reparse(target)
    record = {
        "event": "b_route_impact_closure",
        "schema_version": SCHEMA,
        "operation": payload.get("operation"),
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "reason_code": payload.get("reason_code"),
        "conservative_expanded": payload.get("conservative_expanded"),
        "impact_proof_id": payload.get("impact_proof_id"),
        "report_path": payload.get("report_path"),
        "active_elapsed_seconds": (payload.get("metrics") or {}).get("active_elapsed_seconds"),
    }
    with open(target, "ab") as handle:
        handle.write((_dumps(record) + "\n").encode("utf-8"))


def _finish(root_path: Path | None, payload: dict[str, Any], report: tuple[Path, str] | None,
            events: tuple[Path, str] | None, started: float) -> dict[str, Any]:
    payload["metrics"] = {"active_elapsed_seconds": _elapsed(started)}
    if report is not None and payload.get("ok"):
        try:
            _write_report(report[0], report[1], payload)
        except codec.CodecError as err:
            payload = _blocked(err.diagnostic.to_dict(), payload.get("operation"), started)
    if events is not None:
        _append_event(events[0], payload)
    return payload


def _finish_blocked(root_path: Path | None, payload: dict[str, Any], events: tuple[Path, str] | None,
                    started: float) -> dict[str, Any]:
    try:
        return _finish(root_path, payload, None, events, started)
    except (codec.CodecError, ValueError, OSError):
        payload["metrics"] = {"active_elapsed_seconds": _elapsed(started)}
        return payload


def _validate_operation(operation: Any) -> str:
    if type(operation) is not str or not IDENT_RE.fullmatch(operation):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "portable operation identifier", operation)
    return operation


def _validate_outputs(root_path: Path, report_path: Any, events_log_path: Any):
    report = events = None
    if report_path is not None:
        report = validate_output_path(root_path, report_path, suffix=".json")
        if os.path.lexists(report[0]):
            raise _err(codec.ReasonCode.CONFLICT, "new non-existing report path", report[1], entity=report[1],
                       stage=codec.Stage.PATH)
    if events_log_path is not None:
        events = validate_output_path(root_path, events_log_path, suffix=".jsonl")
    if report and events and os.path.normcase(str(report[0])) == os.path.normcase(str(events[0])):
        raise _err(codec.ReasonCode.CONFLICT, "distinct report and events paths", report[1], stage=codec.Stage.PATH)
    return report, events


def _validate_lists(root_path: Path, manifest_paths: Any, plan_ids: Any) -> tuple[list[str], list[str]]:
    manifests: list[str] = []
    for value in manifest_paths or []:
        rel = _normalize_rel(value)
        if not rel.endswith(".json"):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "manifest *.json path", rel, stage=codec.Stage.PATH)
        _safe_target(root_path, rel)
        if rel not in manifests:
            manifests.append(rel)
    plans: list[str] = []
    for value in plan_ids or []:
        if type(value) is not str or not IDENT_RE.fullmatch(value):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "portable plan id", value)
        if value not in plans:
            plans.append(value)
    return sorted(manifests), sorted(plans)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_governed_reverse_graph(root: Any, *, manifest_paths: list[str] | None = None,
                                 plan_ids: list[str] | None = None) -> dict[str, Any]:
    """Return the governed reverse impact graph (typed nodes, edges, gaps) without any disk writes."""
    started = time.monotonic()
    try:
        root_path = _validate_root(root)
        manifests, plans = _validate_lists(root_path, manifest_paths, plan_ids)
        graph = _build(root_path, manifests, plans or None)
    except codec.CodecError as err:
        return _blocked(err.diagnostic.to_dict(), "build_graph", started)
    except (ValueError, OSError) as exc:
        return _blocked(_io_diag(exc), "build_graph", started)
    nodes = [{"key": key, "entity_kind": rec["kind"], "entity_id": rec["id"], "availability": rec["availability"],
              "immediate_regression_required": rec["regression"], "semantic_owner": rec["semantic_owner"],
              "partition_keys": sorted(rec["partitions"]), "source_refs": sorted(rec["authorities"])}
             for key, rec in sorted(graph.nodes.items())]
    edges = [{"from": upstream, "to": downstream, "edge_kind": kind, "authority": authority, "partition_key": part,
              "accounting_only": kind in ACCOUNTING_EDGES}
             for upstream in sorted(graph.adj) for downstream in sorted(graph.adj[upstream])
             for kind, authority, part in sorted(graph.adj[upstream][downstream])]
    return {
        "schema_version": GRAPH_SCHEMA,
        "ok": True,
        "nodes": nodes,
        "edges": edges,
        "gaps": [dict(g) for g in graph.gaps],
        "plans": sorted(graph.plans),
        "manifests": dict(sorted(graph.manifests.items())),
        "entity_kinds": list(ENTITY_KINDS),
        "metrics": {"active_elapsed_seconds": _elapsed(started), "node_count": len(nodes), "edge_count": len(edges)},
        **INVARIANT_FLAGS,
    }


def compute_impact_closure(root: Any, *, change_roots: Any, manifest_paths: list[str] | None = None,
                           plan_ids: list[str] | None = None, operation: str = "impact_closure",
                           report_path: str | None = None, events_log_path: str | None = None) -> dict[str, Any]:
    """Compute the governed transitive reverse impact closure for explicit change roots."""
    started = time.monotonic()
    root_path = None
    report = events = None
    try:
        root_path = _validate_root(root)
        operation = _validate_operation(operation)
        report, events = _validate_outputs(root_path, report_path, events_log_path)
        if type(change_roots) not in (list, tuple) or not change_roots:
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "nonempty change_roots list", change_roots)
        parsed = []
        for raw in change_roots:
            item = _parse_root(root_path, raw)
            if item not in parsed:
                parsed.append(item)
        manifests, plans = _validate_lists(root_path, manifest_paths, plan_ids)
        graph = _build(root_path, manifests, plans or None)
        payload = _compute(graph, root_path, parsed, plan_ids=plans, manifest_paths=manifests, operation=operation)
        return _finish(root_path, payload, report, events, started)
    except codec.CodecError as err:
        payload = _blocked(err.diagnostic.to_dict(), operation, started)
    except (ValueError, OSError) as exc:
        payload = _blocked(_io_diag(exc), operation, started)
    return _finish_blocked(root_path, payload, events, started)


def _require(condition: bool, code: codec.ReasonCode, expected: Any, actual: Any = None) -> None:
    if not condition:
        raise _err(code, expected, actual, stage=codec.Stage.SCHEMA)


def _validate_proof(proof: Any) -> None:
    failed = codec.ReasonCode.SCHEMA_VALIDATION_FAILED
    _require(type(proof) is dict, failed, "impact proof object", type(proof).__name__)
    _require("schema_version" in proof, failed, "schema_version field")
    _require(proof.get("schema_version") == SCHEMA, codec.ReasonCode.UNKNOWN_SCHEMA, SCHEMA, proof.get("schema_version"))
    _require(proof.get("ok") is True, failed, "sealed ok proof", proof.get("ok"))
    for flag, value in INVARIANT_FLAGS.items():
        _require(proof.get(flag) is value, failed, f"{flag}={value}", proof.get(flag))
    roots = proof.get("change_roots")
    _require(type(roots) is list and bool(roots) and all(
        type(r) is dict and set(r) == {"kind", "id"} and all(type(v) is str for v in r.values()) for r in roots),
        failed, "nonempty typed change_roots")
    for field in ("plan_ids_filter", "manifest_paths_filter", "covered_partitions", "unknown_items", "shared_rules",
                  "cycle_witnesses", "expansion_reasons"):
        _require(type(proof.get(field)) is list, failed, f"{field} list")
    for field in ("plan_ids_filter", "manifest_paths_filter"):
        _require(all(type(v) is str for v in proof[field]), failed, f"{field} strings")
    for _, name in REPORTED_LISTS:
        _require(type(proof.get(name)) is list and all(type(i) is dict for i in proof[name]), failed, f"{name} list")
    _require(type(proof.get("conservative_expanded")) is bool, failed, "conservative_expanded bool")
    covered = proof["covered_partitions"]
    _require(bool(covered) and all(type(k) is str and k for k in covered), failed, "nonempty covered_partitions")
    identities = proof.get("input_identities")
    _require(type(identities) is list and bool(identities), failed, "typed input_identities records",
             type(identities).__name__)
    for item in identities:
        _require(type(item) is dict and set(item) == set(IDENTITY_FIELDS), failed, list(IDENTITY_FIELDS),
                 sorted(item) if type(item) is dict else type(item).__name__)
        for field in ("category", "locator", "normalization_mode"):
            _require(type(item[field]) is str and bool(item[field]), failed, f"{field} string")
        _require(type(item["partition_keys"]) is list and bool(item["partition_keys"])
                 and all(type(k) is str and k for k in item["partition_keys"]), failed, "partition_keys list")
        for field in ("raw_digest", "normalized_digest"):
            _require(type(item[field]) is str and bool(DIGEST_RE.fullmatch(item[field])),
                     codec.ReasonCode.INVALID_DIGEST, "sha256 digest", item[field])
        _require(item["codec_version"] == codec.CODEC_VERSION, codec.ReasonCode.UNKNOWN_CODEC_VERSION,
                 codec.CODEC_VERSION, item["codec_version"])
    digests = proof.get("partition_digests")
    _require(type(digests) is dict and set(digests) == set(covered), failed, "partition_digests for covered partitions")
    for field in ("impact_input_digest", "impact_proof_id"):
        _require(type(proof.get(field)) is str and bool(DIGEST_RE.fullmatch(proof[field])),
                 codec.ReasonCode.INVALID_DIGEST, f"{field} sha256 digest", proof.get(field))
    mismatch = codec.ReasonCode.DIGEST_MISMATCH
    _require(_partition_digests(identities, covered) == digests, mismatch, "partition digests match input identities")
    _require(codec.canonical_digest({"partition_digests": digests}) == proof["impact_input_digest"], mismatch,
             "impact_input_digest matches partition digests")
    try:
        body_digest = codec.canonical_digest(_proof_body(proof))
    except (TypeError, KeyError, AttributeError, ValueError, codec.CodecError) as exc:
        raise _err(failed, "well-formed impact proof body", str(exc), stage=codec.Stage.SCHEMA) from exc
    _require(body_digest == proof["impact_proof_id"], mismatch, "impact_proof_id seals the full proof body")


def _load_proof(root_path: Path, proof_or_path: Any) -> dict[str, Any]:
    if type(proof_or_path) is dict:
        codec.validate_json_value(proof_or_path)
        return copy.deepcopy(proof_or_path)
    if type(proof_or_path) is str and proof_or_path.strip():
        rel = _normalize_rel(proof_or_path, allow_logs=True)
        raw = _read_bytes(root_path, rel, allow_logs=True)
        if raw is None:
            raise _err(codec.ReasonCode.FILE_NOT_FOUND, "existing impact proof file", rel, entity=rel,
                       stage=codec.Stage.PATH)
        return codec.strict_json_loads(raw)
    raise _err(codec.ReasonCode.INVALID_ARGUMENT, "impact proof object or repository-relative path",
               type(proof_or_path).__name__)


def _proof_keys(proof: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for item in [i for _, name in REPORTED_LISTS for i in proof[name]] + list(proof["shared_rules"]):
        keys.add(f"{item.get('entity_kind')}:{item.get('entity_id')}")
        for step in item.get("witness_path") or []:
            if type(step) is dict and type(step.get("node")) is str:
                keys.add(step["node"])
    return keys


def revalidate_impact_proof(root: Any, proof_or_path: Any, *, manifest_paths: list[str] | None = None,
                            operation: str = "impact_revalidation", report_path: str | None = None,
                            events_log_path: str | None = None) -> dict[str, Any]:
    """Revalidate a sealed impact proof per partition; reuse it or recompute invalidated/joined partitions."""
    started = time.monotonic()
    root_path = None
    report = events = None
    try:
        root_path = _validate_root(root)
        operation = _validate_operation(operation)
        report, events = _validate_outputs(root_path, report_path, events_log_path)
        proof = _load_proof(root_path, proof_or_path)
        _validate_proof(proof)
        requested = proof["manifest_paths_filter"] if manifest_paths is None else manifest_paths
        manifests, plans = _validate_lists(root_path, requested, proof["plan_ids_filter"])
        graph = _build(root_path, manifests, plans or None)
        covered = list(proof["covered_partitions"])
        prior = sorted({i["locator"] for i in proof["input_identities"] if i["normalization_mode"] in FILE_MODES})
        live_digests = _partition_digests(_identities(graph, root_path, set(covered), prior), covered)
        changed = {key for key in covered if live_digests.get(key) != proof["partition_digests"].get(key)}
        if manifests != proof["manifest_paths_filter"]:
            changed.add(FILTER_PARTITION)
        parsed = [_parse_root(root_path, {"kind": r["kind"], "id": r["id"]}) for r in proof["change_roots"]]
        proof_keys = _proof_keys(proof)
        unknown_entities = {u.get("entity") for u in proof["unknown_items"] if type(u) is dict}
        for item in parsed:
            display = f"{item['kind']}:{item['id']}"
            keys, unresolved = _resolve_root(graph, root_path, item)
            if (unresolved is None) == (display in unknown_entities):
                changed.add("governance")
            proof_keys.discard(display)
            proof_keys |= set(keys)
        joined: set[str] = set()
        for key in sorted(proof_keys):
            rec = graph.nodes.get(key)
            if rec is None:
                changed.add("governance")
                continue
            joined |= {p for p in rec["partitions"] if p not in covered}
        invalidated = sorted(changed | joined)
        if not invalidated:
            payload = copy.deepcopy(proof)
            payload.update(status="valid_reused", operation=operation, reused=True, invalidated_partitions=[],
                           recomputed_partitions=[], reused_partitions=sorted(covered), diagnostics=[],
                           report_path=None, reason_code=codec.ReasonCode.OK.value)
            payload.pop("previous_impact_proof_id", None)
        else:
            unknown = [key for key in invalidated
                       if not key.startswith(KNOWN_PARTITION_PREFIXES) and key != FILTER_PARTITION]
            payload = _compute(graph, root_path, parsed, plan_ids=plans, manifest_paths=manifests, operation=operation,
                               extra_expansions=[("unknown_partition_relevance", key) for key in unknown])
            payload.update(
                status="recomputed",
                reused=False,
                invalidated_partitions=invalidated,
                recomputed_partitions=sorted(set(invalidated) & set(payload["covered_partitions"])) or invalidated,
                reused_partitions=sorted(set(covered) - set(invalidated)),
                previous_impact_proof_id=proof["impact_proof_id"],
            )
        return _finish(root_path, payload, report, events, started)
    except codec.CodecError as err:
        payload = _blocked(err.diagnostic.to_dict(), operation, started)
    except (ValueError, OSError) as exc:
        payload = _blocked(_io_diag(exc), operation, started)
    return _finish_blocked(root_path, payload, events, started)
