#!/usr/bin/env python3
"""Map reviewed frozen-task requirements to existing Taskmaster view rows."""

from __future__ import annotations

import json
import re
from pathlib import Path

from chapter3_task_scope import load_scope, validate_master

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "logs/ci/task-generation"
REQUIREMENT_ID = re.compile(r"^(?:FR|NFR)-T(\d{4})$")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def reconcile(root: Path, artifacts: Path | None = None) -> dict:
    scope = load_scope(root)
    if scope is None:
        raise ValueError("Frozen task scope is required")
    allowed = validate_master(root, scope)
    master = {row["id"]: row for row in read(root / scope["master_path"])["master"]["tasks"]}
    artifact_root = artifacts or ARTIFACTS
    semantics = read(artifact_root / "semantic-requirements.v1.json")
    capabilities = read(artifact_root / "capabilities.v1.json")
    capability_refs_by_requirement: dict[str, list[str]] = {}
    for capability in capabilities.get("capabilities", []):
        capability_id = str(capability.get("capability_id") or "").strip()
        if not capability_id:
            raise ValueError("Capability is missing capability_id")
        for requirement_id in capability.get("requirement_ids", []):
            capability_refs_by_requirement.setdefault(str(requirement_id), []).append(capability_id)
    ledger = read(artifact_root / "source-blocks.v1.json")
    blocks = {row["block_id"]: row for row in ledger["blocks"]}
    active = {}
    for requirement in semantics["requirements"]:
        match = REQUIREMENT_ID.fullmatch(str(requirement.get("requirement_id") or ""))
        if not match:
            raise ValueError(f"Unexpected requirement identity: {requirement.get('requirement_id')}")
        numeric_id = int(match.group(1))
        if numeric_id not in allowed or numeric_id in active:
            raise ValueError(f"Unknown or repeated task requirement: {numeric_id}")
        if master[numeric_id]["status"] == "cancelled" or requirement.get("status") != "active":
            raise ValueError(f"Inactive task has an active requirement: {numeric_id}")
        if requirement.get("delivery_relevant") is not True:
            raise ValueError(f"Task requirement is not delivery relevant: {numeric_id}")
        active[numeric_id] = requirement
    expected = {task_id for task_id in allowed if master[task_id]["status"] != "cancelled"}
    if set(active) != expected:
        raise ValueError(f"Active requirement identity mismatch: {sorted(expected - set(active))}")
    candidates = []
    for filename, owner in (("tasks_back.json", "architecture"), ("tasks_gameplay.json", "gameplay")):
        for row in read(root / ".taskmaster/tasks" / filename):
            numeric_id = row.get("taskmaster_id")
            if numeric_id is None:
                continue
            if numeric_id not in allowed:
                raise ValueError(f"View row outside frozen scope: {row.get('id')}")
            if numeric_id not in active:
                continue
            requirement = active[numeric_id]
            refs = [requirement["requirement_id"]]
            capability_refs = sorted(set(capability_refs_by_requirement.get(refs[0], [])))
            if not capability_refs:
                raise ValueError(f"Active requirement has no Capability mapping: {numeric_id}")
            source_refs = []
            for block_id in requirement["source_block_ids"]:
                block = blocks[block_id]
                source_refs.append(f"{block['source_path']}:{block['line_start']}")
            updates = {
                "semantic_refs": refs,
                "requirement_ids": refs,
                "source_refs": sorted(set(source_refs)),
                "complexity_score": 1,
                "capability_refs": capability_refs,
            }
            candidates.append({
                "id": row["id"],
                "taskmaster_id": numeric_id,
                "taskmaster_status": master[numeric_id]["status"],
                "owner": owner,
                "change_action": "update",
                "semantic_refs": refs,
                "requirement_ids": refs,
                "source_refs": updates["source_refs"],
                "complexity_score": 1,
                "capability_refs": capability_refs,
                "field_updates": updates,
            })
    if {row["taskmaster_id"] for row in candidates} != expected:
        raise ValueError("Active tasks missing from existing views")
    if len({row["id"] for row in candidates}) != len(candidates):
        raise ValueError("Repeated view ID in frozen candidates")
    return {
        "schema_version": "chapter3.frozen-task-candidates.v1",
        "source_revision": semantics["source_revision"],
        "source_manifest_sha256": semantics["source_manifest_sha256"],
        "candidates": candidates,
    }


def main() -> int:
    result = reconcile(ROOT)
    path = ARTIFACTS / "task-candidates.enriched.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"candidate_count": len(result["candidates"]), "numeric_task_count": len({row["taskmaster_id"] for row in result["candidates"]})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
