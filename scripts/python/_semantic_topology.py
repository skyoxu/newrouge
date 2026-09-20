#!/usr/bin/env python3
"""Read-only semantic delivery topology projection helpers.

Repository source remains authority. This module never invents semantic nodes and
never mutates Taskmaster. It validates and projects registered topology artifacts
when they exist, otherwise it returns an explicit legacy/unavailable view.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

TOPOLOGY_DIR = "docs/planning/semantic-topology"
TOPOLOGY_ARTIFACTS = {
    "manifest": f"{TOPOLOGY_DIR}/topology-manifest.v1.json",
    "source_blocks": f"{TOPOLOGY_DIR}/source-blocks.v1.json",
    "requirements": f"{TOPOLOGY_DIR}/semantic-requirements.v1.json",
    "capabilities": f"{TOPOLOGY_DIR}/capabilities.v1.json",
    "edges": f"{TOPOLOGY_DIR}/topology-edges.v1.json",
}
WORKSPACE_TOPOLOGY = Path("logs/ci/project-health-knowledge/topology/workspace-latest.json")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rows(value: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in keys:
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _identity(kind: str, revision: str | None, authority_ref: str | None = None) -> dict[str, Any]:
    result = {"kind": kind, "revision": revision}
    if authority_ref:
        result["authority_ref"] = authority_ref
    return result


def unavailable_topology(kind: str, revision: str | None, reason: str,
                         authority_ref: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "newrouge.semantic-topology-view.v1",
        "available": False,
        "fresh": False,
        "identity": _identity(kind, revision, authority_ref),
        "status": "legacy_unmapped",
        "reason": reason,
        "nodes": {
            "source_blocks": [],
            "requirements": [],
            "capabilities": [],
            "tasks": [],
            "acceptance": [],
        },
        "edges": [],
        "task_trace": {},
        "summary": {
            "source_blocks": 0,
            "delivery_requirements": 0,
            "requirements_with_sink": 0,
            "tasks_with_semantic_refs": 0,
            "acceptance_with_semantic_origin": 0,
            "orphan_requirements": 0,
            "unresolved_requirements": 0,
        },
        "problems": [],
    }


def _node_id(kind: str, row: dict[str, Any]) -> str | None:
    candidates = {
        "source_block": ("block_id", "source_block_id", "id"),
        "requirement": ("requirement_id", "semantic_id", "id"),
        "capability": ("capability_id", "id"),
        "task": ("task_id", "taskmaster_id", "id"),
        "acceptance": ("acceptance_id", "anchor", "id"),
    }
    for key in candidates.get(kind, ("id",)):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _edge_endpoint(edge: dict[str, Any], side: str) -> tuple[str | None, str | None]:
    nested = edge.get(side)
    if isinstance(nested, dict):
        kind = nested.get("type") or nested.get("kind")
        value = nested.get("id")
        return (str(kind) if kind else None, str(value) if value is not None else None)
    kind = edge.get(f"{side}_type") or edge.get(f"{side}_kind")
    value = edge.get(f"{side}_id")
    if value is None:
        value = edge.get(side)
    return (str(kind) if kind else None, str(value) if value is not None else None)


def _task_rows(task_details: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for detail in task_details or []:
        task = detail.get("task") if isinstance(detail.get("task"), dict) else {}
        task_id = task.get("id")
        if task_id is None:
            continue
        rows.append({
            "task_id": str(task_id),
            "title": task.get("title"),
            "status": task.get("status"),
            "semantic_refs": task.get("semantic_refs", task.get("requirement_ids", [])),
            "capability_refs": task.get("capability_refs", []),
        })
    return rows


def _validate_artifact_hashes(snapshot: Any, manifest: dict[str, Any],
                              problems: list[dict[str, Any]]) -> None:
    bindings = manifest.get("artifacts")
    if not isinstance(bindings, dict):
        return
    for path, expected in bindings.items():
        if not isinstance(path, str) or not isinstance(expected, str):
            problems.append({"kind": "invalid_manifest_binding", "path": str(path)})
            continue
        if path not in getattr(snapshot, "paths", ()):
            problems.append({"kind": "missing_artifact", "path": path})
            continue
        actual = snapshot.digest(path)
        if expected.removeprefix("sha256:") != actual:
            problems.append({"kind": "artifact_hash_mismatch", "path": path,
                             "expected": expected, "actual": actual})


def build_topology_view(identity: dict[str, Any], manifest: dict[str, Any],
                        source_blocks_doc: Any, requirements_doc: Any,
                        capabilities_doc: Any, edges_doc: Any,
                        task_details: list[dict[str, Any]] | None = None,
                        problems: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    problems = list(problems or [])
    source_blocks = _rows(source_blocks_doc, "blocks", "source_blocks")
    requirements = _rows(requirements_doc, "requirements", "semantic_requirements", "atoms")
    capabilities = _rows(capabilities_doc, "capabilities")
    edges = _rows(edges_doc, "edges")
    tasks = _task_rows(task_details)

    block_ids = {node_id for row in source_blocks if (node_id := _node_id("source_block", row))}
    requirement_ids = {node_id for row in requirements if (node_id := _node_id("requirement", row))}
    task_ids = {row["task_id"] for row in tasks}

    for row in requirements:
        rid = _node_id("requirement", row)
        refs = row.get("source_block_ids", [])
        if not isinstance(refs, list):
            problems.append({"kind": "invalid_source_block_refs", "requirement_id": rid})
            continue
        for ref in refs:
            if str(ref) not in block_ids:
                problems.append({"kind": "missing_source_block_ref",
                                 "requirement_id": rid, "source_block_id": str(ref)})
    for row in capabilities:
        cid = _node_id("capability", row)
        refs = row.get("requirement_ids", row.get("covers", []))
        if isinstance(refs, list):
            for ref in refs:
                if str(ref) not in requirement_ids:
                    problems.append({"kind": "missing_requirement_ref",
                                     "capability_id": cid, "requirement_id": str(ref)})

    task_trace: dict[str, dict[str, set[str]]] = {
        task_id: {"requirements": set(), "capabilities": set(),
                  "source_blocks": set(), "acceptance": set()}
        for task_id in task_ids
    }
    sink_requirements: set[str] = set()
    acceptance_origins: set[str] = set()
    for edge in edges:
        left_kind, left_id = _edge_endpoint(edge, "source")
        right_kind, right_id = _edge_endpoint(edge, "target")
        if not left_id or not right_id:
            problems.append({"kind": "invalid_edge", "edge": edge})
            continue
        normalized = {(left_kind or "").casefold(): left_id,
                      (right_kind or "").casefold(): right_id}
        req = normalized.get("requirement") or normalized.get("semantic_requirement")
        task = normalized.get("task")
        cap = normalized.get("capability")
        acc = normalized.get("acceptance")
        block = normalized.get("source_block")
        if req and (task or cap or (right_kind or "").casefold()
                    in {"global_constraint", "quality_gate", "adr"}):
            sink_requirements.add(req)
        if acc and req:
            acceptance_origins.add(acc)
        if task and task in task_trace:
            if req:
                task_trace[task]["requirements"].add(req)
            if cap:
                task_trace[task]["capabilities"].add(cap)
            if block:
                task_trace[task]["source_blocks"].add(block)
            if acc:
                task_trace[task]["acceptance"].add(acc)

    req_by_id = {_node_id("requirement", row): row for row in requirements}
    cap_by_id = {_node_id("capability", row): row for row in capabilities}
    for task_id, trace in task_trace.items():
        for rid in list(trace["requirements"]):
            row = req_by_id.get(rid) or {}
            trace["source_blocks"].update(str(x) for x in row.get("source_block_ids", []) if x is not None)
            trace["capabilities"].update(str(x) for x in row.get("capability_ids", []) if x is not None)
        for cid in list(trace["capabilities"]):
            row = cap_by_id.get(cid) or {}
            refs = row.get("requirement_ids", row.get("covers", []))
            for rid in refs if isinstance(refs, list) else []:
                trace["requirements"].add(str(rid))
                req = req_by_id.get(str(rid)) or {}
                trace["source_blocks"].update(
                    str(x) for x in req.get("source_block_ids", []) if x is not None
                )

    delivery = [
        row for row in requirements
        if row.get("delivery_relevant", True) is True
        and str(row.get("status", "active")).casefold() == "active"
    ]
    unresolved = [
        row for row in requirements
        if str(row.get("status", "")).casefold() == "unresolved"
        or str(row.get("disposition", "")).casefold() == "unresolved"
    ]
    orphan = [
        row for row in delivery
        if (_node_id("requirement", row) or "") not in sink_requirements
        and str(row.get("sink_policy", "")).casefold()
        not in {"deferred", "excluded", "out_of_scope"}
    ]
    source_revision = manifest.get("source_revision")
    revision = identity.get("revision")
    fresh = not source_revision or not revision or source_revision == revision
    if not fresh:
        problems.append({"kind": "source_revision_mismatch",
                         "manifest_revision": source_revision,
                         "identity_revision": revision})

    serial_trace = {
        task_id: {key: sorted(values) for key, values in trace.items()}
        for task_id, trace in task_trace.items()
    }
    severe = {"artifact_hash_mismatch", "missing_artifact", "source_revision_mismatch"}
    return {
        "schema_version": "newrouge.semantic-topology-view.v1",
        "available": True,
        "fresh": fresh and not any(p.get("kind") in severe for p in problems),
        "identity": identity,
        "status": "fresh" if fresh and not problems else "stale_or_concern",
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "source_revision": source_revision,
            "schema_revision": manifest.get("schema_revision"),
            "generator_revision": manifest.get("generator_revision"),
        },
        "nodes": {
            "source_blocks": source_blocks,
            "requirements": requirements,
            "capabilities": capabilities,
            "tasks": tasks,
            "acceptance": [],
        },
        "edges": edges,
        "task_trace": serial_trace,
        "summary": {
            "source_blocks": len(source_blocks),
            "delivery_requirements": len(delivery),
            "requirements_with_sink": len([
                r for r in delivery
                if (_node_id("requirement", r) or "") in sink_requirements
            ]),
            "tasks_with_semantic_refs": len([
                t for t in tasks
                if serial_trace.get(t["task_id"], {}).get("requirements")
                or t.get("semantic_refs")
            ]),
            "acceptance_with_semantic_origin": len(acceptance_origins),
            "orphan_requirements": len(orphan),
            "unresolved_requirements": len(unresolved),
        },
        "problems": problems,
    }


def load_topology_from_snapshot(snapshot: Any,
                                task_details: list[dict[str, Any]] | None = None,
                                identity_kind: str = "main") -> dict[str, Any]:
    identity = _identity(identity_kind, getattr(snapshot, "commit", None),
                         getattr(snapshot, "authority_ref", None))
    missing = [
        path for path in TOPOLOGY_ARTIFACTS.values()
        if path not in getattr(snapshot, "paths", ())
    ]
    if missing:
        return unavailable_topology(
            identity_kind, identity.get("revision"),
            "topology artifacts are not present in this snapshot",
            identity.get("authority_ref"),
        )
    documents: dict[str, Any] = {}
    try:
        for key, path in TOPOLOGY_ARTIFACTS.items():
            documents[key] = json.loads(snapshot.read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result = unavailable_topology(
            identity_kind, identity.get("revision"),
            f"topology artifact read failed: {exc}", identity.get("authority_ref")
        )
        result["problems"] = [{"kind": "artifact_read_failed", "reason": str(exc)}]
        return result
    problems: list[dict[str, Any]] = []
    _validate_artifact_hashes(snapshot, documents["manifest"], problems)
    return build_topology_view(
        identity, documents["manifest"], documents["source_blocks"],
        documents["requirements"], documents["capabilities"], documents["edges"],
        task_details, problems
    )


def load_workspace_topology(root: Path) -> dict[str, Any]:
    path = root / WORKSPACE_TOPOLOGY
    if not path.is_file():
        return unavailable_topology(
            "workspace", None, "no workspace/chapter-run topology preview exists"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = unavailable_topology(
            "workspace", None, f"workspace topology preview is invalid: {exc}"
        )
        result["problems"] = [{"kind": "workspace_preview_invalid", "reason": str(exc)}]
        return result
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    if identity.get("kind") != "workspace":
        result = unavailable_topology(
            "workspace", identity.get("revision"),
            "workspace preview must declare identity.kind=workspace"
        )
        result["problems"] = [{"kind": "identity_mismatch"}]
        return result
    payload["schema_version"] = "newrouge.semantic-topology-view.v1"
    payload["available"] = bool(payload.get("available", True))
    payload["identity"] = identity
    return payload


def attach_scene_design_trace(scene_graph: dict[str, Any], topology: dict[str, Any],
                              task_details: list[dict[str, Any]]) -> None:
    traces: dict[str, dict[str, Any]] = {}
    task_trace = topology.get("task_trace", {}) if topology.get("available") else {}
    for detail in task_details:
        task = detail.get("task") if isinstance(detail.get("task"), dict) else {}
        task_id = str(task.get("id")) if task.get("id") is not None else None
        if not task_id:
            continue
        godot = detail.get("godot") if isinstance(detail.get("godot"), dict) else {}
        level = godot.get("status", "unmapped")
        scenes = godot.get("scenes", [])
        for scene in scenes if isinstance(scenes, list) else []:
            path = scene.get("scene") if isinstance(scene, dict) else scene
            if not isinstance(path, str) or not path:
                continue
            entry = traces.setdefault(path, {
                "tasks": [], "capabilities": set(), "requirements": set(),
                "source_blocks": set(), "evidence_levels": set(),
            })
            entry["tasks"].append({
                "task_id": task_id, "title": task.get("title"),
                "status": task.get("status")
            })
            entry["evidence_levels"].add(str(level))
            trace = task_trace.get(task_id, {})
            entry["capabilities"].update(trace.get("capabilities", []))
            entry["requirements"].update(trace.get("requirements", []))
            entry["source_blocks"].update(trace.get("source_blocks", []))
    scene_graph["design_trace"] = {
        path: {
            "tasks": value["tasks"],
            "capabilities": sorted(value["capabilities"]),
            "requirements": sorted(value["requirements"]),
            "source_blocks": sorted(value["source_blocks"]),
            "evidence_levels": sorted(value["evidence_levels"]),
            "semantic_claim": "navigation_only",
        }
        for path, value in traces.items()
    }
    scene_graph["topology_identity"] = topology.get("identity")
