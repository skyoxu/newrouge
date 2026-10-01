"""Stable Capability alignment and complete projected-topology preflight."""
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import re

from _planning_skill_common import load_json


def slug(value: str) -> str:
    return "-".join(re.findall(r"[A-Za-z0-9]+", value.upper()))[:72] or "UNNAMED"


def build_alignment(candidate: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    old_rows = [r for r in existing.get("capabilities", []) if isinstance(r, dict) and r.get("capability_id")]
    old_by_members = defaultdict(list)
    for row in old_rows:
        old_by_members[tuple(sorted(map(str, row.get("requirement_ids", []))))].append(row)
    counts = Counter(tuple(sorted(map(str, r.get("requirement_ids", [])))) for r in candidate.get("capabilities", []))
    decisions, used_old, allocated = [], set(), set()
    for row in candidate.get("capabilities", []):
        temp = str(row.get("capability_id") or "")
        members = tuple(sorted(map(str, row.get("requirement_ids", []))))
        matches = old_by_members.get(members, [])
        stable, action, reason, resolved = None, "unresolved", "Explicit identity decision required.", False
        if len(matches) == 1 and counts[members] == 1:
            stable = str(matches[0]["capability_id"])
            used_old.add(stable)
            action, reason, resolved = "reuse", "Unique exact Requirement membership match.", True
        elif not old_rows:
            base = "CAP-" + slug(str(row.get("title") or temp))
            stable, suffix = base, 2
            while stable in allocated:
                stable, suffix = f"{base}-{suffix}", suffix + 1
            action, reason, resolved = "add", "First formal Capability baseline.", True
        elif matches:
            reason = "Ambiguous identical membership; explicitly select reuse/add/split/merge/rename."
        if stable:
            allocated.add(stable)
        decisions.append({"candidate_id": temp, "action": action, "stable_id": stable,
            "reason": reason, "resolved": resolved})
    for row in old_rows:
        stable = str(row["capability_id"])
        if stable not in used_old:
            decisions.append({"candidate_id": None, "action": "unresolved-retirement", "stable_id": stable,
                "reason": "Existing identity needs explicit retention or retirement.", "resolved": False})
    return {"schema_version": "newrouge.capability-alignment.v1", "decisions": decisions,
        "resolved": all(r["resolved"] for r in decisions)}


def apply_alignment_override(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    def key(row):
        if not isinstance(row, dict):
            raise ValueError("Capability alignment decision must be an object")
        return ("candidate", str(row["candidate_id"])) if row.get("candidate_id") is not None else (
            "historical", str(row.get("stable_id") or ""))

    rows = base["decisions"]
    known = {key(row) for row in rows}
    replacements = {}
    for row in override.get("decisions", []):
        identity = key(row)
        if identity not in known or identity in replacements:
            raise ValueError("Capability alignment override has unknown or duplicate decision")
        replacements[identity] = dict(row)
    result = [replacements.get(key(row), dict(row)) for row in rows]
    return {"schema_version": "newrouge.capability-alignment.v1", "decisions": result,
        "resolved": all(row.get("resolved") is True for row in result)}


def validate_alignment(candidate: dict[str, Any], existing: dict[str, Any], alignment: dict[str, Any]) -> None:
    rows = alignment.get("decisions", [])
    candidate_ids = [str(c["capability_id"]) for c in candidate["capabilities"]]
    old_ids = {str(c["capability_id"]) for c in existing.get("capabilities", [])}
    mapped = [r for r in rows if isinstance(r, dict) and r.get("candidate_id") is not None]
    if Counter(str(r["candidate_id"]) for r in mapped) != Counter(candidate_ids):
        raise ValueError("Capability alignment must map each candidate exactly once")
    stable_ids = [str(r.get("stable_id") or "").strip() for r in mapped]
    if not all(stable_ids) or len(set(stable_ids)) != len(stable_ids):
        raise ValueError("Capability alignment stable IDs must be nonempty and unique; duplicate collision")
    for row in rows:
        if not isinstance(row, dict) or row.get("resolved") is not True or not str(row.get("reason") or "").strip():
            raise ValueError("Capability alignment requires complete reviewed decisions and reasons")
        action, stable = row.get("action"), str(row.get("stable_id") or "")
        if row.get("candidate_id") is not None:
            if action not in {"reuse", "add", "split", "merge", "rename"}:
                raise ValueError("Unsupported Capability alignment action")
            if action in {"reuse", "rename"} and stable not in old_ids:
                raise ValueError("Capability reuse/rename must reference an existing stable ID")
            if action == "add" and stable in old_ids:
                raise ValueError("Capability add cannot overwrite an existing stable ID")
        elif stable not in old_ids or (action == "retire" and stable in stable_ids) or (
            action == "retain" and stable not in stable_ids) or action not in {"retire", "retain"}:
            raise ValueError("Capability historical retention/retirement conflicts with final mapping")
    dispositions = {str(r.get("stable_id")) for r in rows if r.get("candidate_id") is None}
    if len(dispositions) != sum(r.get("candidate_id") is None for r in rows):
        raise ValueError("Capability historical decisions must be unique")
    if old_ids - set(stable_ids) - dispositions:
        raise ValueError("Capability historical IDs cannot disappear without reviewed retirement")


def validate_formal_projection(root: Path, formal: dict[str, Any], edges: dict[str, Any],
                              back: list[dict[str, Any]], gameplay: list[dict[str, Any]]) -> dict[str, Any]:
    from _semantic_topology import build_topology_view, _edge_endpoint, _validate_minimum_shapes
    prefix = root / "docs/planning/semantic-topology"
    blocks = load_json(prefix / "source-blocks.v1.json", {})
    semantics = load_json(prefix / "semantic-requirements.v1.json", {})
    master = load_json(root / ".taskmaster/tasks/tasks.json", {})["master"]["tasks"]
    details = []
    for task in master:
        task = dict(task)
        matches = [r for r in back + gameplay if str(r.get("taskmaster_id")) == str(task["id"])]
        for field, fallback in (("semantic_refs", "requirement_ids"), ("capability_refs", "capability_refs")):
            task[field] = sorted({str(v) for r in [task] + matches for v in r.get(field, r.get(fallback, []))})
        details.append({"task": task, "mappings": {"tasks_back": [r for r in back if str(r.get("taskmaster_id")) == str(task["id"])],
            "tasks_gameplay": [r for r in gameplay if str(r.get("taskmaster_id")) == str(task["id"])]}})
    problems = []
    _validate_minimum_shapes({"source_blocks": blocks, "requirements": semantics,
        "capabilities": formal, "edges": edges, "manifest": load_json(prefix / "topology-manifest.v1.json", {})}, problems)
    view = build_topology_view({"kind": "projection"}, {}, blocks, semantics, formal, edges, details, problems)
    known = {"source_block": {str(r["block_id"]) for r in blocks.get("blocks", [])},
        "requirement": {str(r["requirement_id"]) for r in semantics.get("requirements", [])},
        "capability": {str(r["capability_id"]) for r in formal["capabilities"]},
        "task": {str(t["id"]) for t in master},
        "acceptance": {r["acceptance_id"] for r in view["nodes"]["acceptance"]}}
    known["semantic_requirement"] = known["requirement"]
    for edge in view["edges"]:
        for side in ("source", "target"):
            kind, value = _edge_endpoint(edge, side)
            if kind in known and value not in known[kind]:
                view["problems"].append({"kind": "unknown_projected_edge_endpoint", "endpoint": [kind, value]})
    if view["problems"]:
        raise ValueError("Capability formal topology projection invalid: " + str(view["problems"]))
    return {"status": "passed", "summary": view["summary"], "problems": []}
