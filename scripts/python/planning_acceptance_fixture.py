#!/usr/bin/env python3
"""Build a small isolated project that exercises the portable Chapter 3-5 planning contracts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, file_sha
from build_source_ledger import build_ledger, source_set_payload
from chapter5_semantic_reconciliation import (
    DEFAULT_EXTRACTION_CANDIDATE,
    DEFAULT_EXTRACTION_SNAPSHOT,
    DEFAULT_READINESS_DIR,
    DEFAULT_RECONCILIATION_DIR,
    compile_extraction_b,
    load_task_readiness,
    prepare_extraction_b,
    reconcile,
)

TASK_IDS = (7, 42)
GDD_PATH = Path("docs/gdd/GDD-HARBOR-RELAY-ACCEPTANCE.md")
CONTRACT_PATH = Path("Game.Core/Contracts/RelayHandoff.cs")
TEST_PATH = Path("Game.Core.Tests/Tasks/PlanningAcceptanceTests.cs")
MANIFEST_PATH = Path("logs/ci/task-generation/source-manifest.v1.json")
LEDGER_PATH = Path("logs/ci/task-generation/source-blocks.v1.json")
SEMANTICS_PATH = Path("logs/ci/task-generation/semantic-requirements.v1.json")


def _write_text(root: Path, rel: Path, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
    )


def _init_source_revision(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.email", "planning-acceptance@example.invalid")
    _git(root, "config", "user.name", "Planning Acceptance")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture: authoritative source baseline")
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()


def _base_files(root: Path) -> None:
    _write_text(
        root,
        GDD_PATH,
        """# Harbor Relay

## Launch relay
When the player presses Launch, the harbor console validates the selected relay route and starts one drone transfer. The selected route supplies RouteId and CargoUnits. For each accepted transfer in this scoped journey, the launcher constructs RelayHandoff from those values with RetryAllowed=true because recovery is required. A rejected route creates no transfer or handoff. The launch surface must show the accepted route or a visible rejection reason.

## Resolve delivery
After a valid launch, the relay service hands the transfer to the score terminal through the RelayHandoff contract. The relay service reports a completion or failure signal separately from the request data; the terminal consumes that signal with the original request. Completion displays the request's CargoUnits as delivered cargo. Failure displays a retryable failure state and permits retry of the same request. RetryAllowed=false is outside the accepted-transfer scope of this journey and must not weaken its required retryable failure outcome. The result/failure entrypoint remains an owned implementation obligation rather than an existing member of RelayHandoff.
""",
    )
    _write_text(
        root,
        CONTRACT_PATH,
        """namespace Game.Core.Contracts;

public sealed record RelayHandoff(
    int RouteId,
    int CargoUnits,
    bool RetryAllowed);
""",
    )
    _write_text(
        root,
        TEST_PATH,
        """namespace Game.Core.Tests.Tasks;

public sealed class PlanningAcceptanceTests
{
    // Planning fixture only. Runtime verification remains outside planning acceptance.
}
""",
    )


def _requirement_statement(block: dict[str, Any]) -> str:
    raw = " ".join(str(block.get("raw_text") or "").split())
    return raw.removeprefix("# ").removeprefix("## ").strip()


def _build_semantics(ledger: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    requirements = []
    requirement_by_block: dict[str, str] = {}
    index = 1
    for block in ledger.get("blocks", []):
        if not isinstance(block, dict) or block.get("block_type") != "paragraph":
            continue
        block_id = str(block["block_id"])
        rid = f"RQ-HARBOR-{index:03d}"
        index += 1
        requirement_by_block[block_id] = rid
        requirements.append({
            "requirement_id": rid,
            "statement": _requirement_statement(block),
            "kind": "functional",
            "priority": "P1",
            "delivery_relevant": True,
            "status": "active",
            "source_block_ids": [block_id],
            "sink_policy": "task",
            "non_task_sinks": [],
        })
    if len(requirements) < 2:
        raise ValueError("Harbor fixture must produce at least two delivery Requirements")
    return {
        "schema_version": "newrouge.semantic-requirements.v1",
        "source_revision": ledger.get("source_revision"),
        "requirements": requirements,
    }, requirement_by_block


def _write_task_triplet(root: Path, semantics: dict[str, Any]) -> dict[str, list[str]]:
    reqs = [str(row["requirement_id"]) for row in semantics["requirements"]]
    split = max(1, len(reqs) // 2)
    by_task = {
        "7": reqs[:split],
        "42": reqs[split:],
    }
    if not by_task["42"]:
        by_task["42"] = [by_task["7"].pop()]
    master = {
        "master": {
            "tasks": [
                {"id": 7, "title": "Launch harbor relay", "status": "done"},
                {"id": 42, "title": "Resolve relay delivery", "status": "done"},
            ]
        }
    }
    common = {
        "priority": "P1",
        "layer": "feature",
        "depends_on": [],
        "dependency_status": "reviewed",
        "dependency_reason": "Independent fixture tasks are linked by MVG handoff rather than Taskmaster dependency.",
        "adr_refs": [],
        "chapter_refs": ["Chapter 5"],
        "overlay_refs": [],
        "labels": ["gameplay", "planning-acceptance"],
        "owner": "gameplay",
        "test_refs": [TEST_PATH.as_posix()],
        "test_strategy": ["Validate the planned player journey before runtime evidence is claimed."],
        "contractRefs": [CONTRACT_PATH.as_posix()],
        "capability_refs": [],
        "implementation_overlap_candidates": [],
    }
    rows = []
    for task_id, title in ((7, "Launch harbor relay"), (42, "Resolve relay delivery")):
        rid_values = by_task[str(task_id)]
        acceptance = (
            f"Task {task_id} satisfies {', '.join(rid_values)} with traceable planning evidence. "
            f"Refs: {TEST_PATH.as_posix()}"
        )
        row = {
            **common,
            "id": f"GM-{task_id:04d}",
            "taskmaster_id": task_id,
            "story_id": "PRD-HARBOR-RELAY-v1",
            "title": title,
            "description": title,
            "status": "done",
            "acceptance": [acceptance],
            "requirement_ids": rid_values,
            "semantic_refs": rid_values,
        }
        rows.append(row)
    atomic_json(root / ".taskmaster/tasks/tasks.json", master)
    atomic_json(root / ".taskmaster/tasks/tasks_back.json", [])
    atomic_json(root / ".taskmaster/tasks/tasks_gameplay.json", rows)
    return by_task


def _compile_extraction_b(
    root: Path,
    ledger: dict[str, Any],
    requirement_by_block: dict[str, str],
    semantics: dict[str, Any],
) -> dict[str, Any]:
    candidate_path = root / DEFAULT_EXTRACTION_CANDIDATE
    snapshot_path = root / DEFAULT_EXTRACTION_SNAPSHOT
    result = prepare_extraction_b(
        root,
        manifest_path=root / MANIFEST_PATH,
        ledger_path=root / LEDGER_PATH,
        candidate_path=candidate_path,
        snapshot_path=snapshot_path,
    )
    if result["status"] not in {"review_required", "cache_hit"}:
        raise ValueError(f"Chapter 5 fixture prepare failed: {result}")
    if result["status"] == "review_required":
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        statement_by_rid = {
            str(row["requirement_id"]): str(row["statement"])
            for row in semantics["requirements"]
        }
        for row in candidate.get("block_results", []):
            block_id = str(row.get("block_id") or "")
            rid = requirement_by_block.get(block_id)
            row["review_status"] = "reviewed"
            if rid:
                row["delivery_potential"] = True
                row["disposition"] = ""
                row["obligations"] = [{
                    "statement": statement_by_rid[rid],
                    "kind": "functional",
                    "priority": "P1",
                    "delivery_relevant": True,
                    "source_block_ids": [block_id],
                    "authority_refs": [],
                }]
            else:
                row["delivery_potential"] = False
                row["disposition"] = "context"
                row["obligations"] = []
        atomic_json(candidate_path, candidate)
    snapshot = compile_extraction_b(
        root,
        manifest_path=root / MANIFEST_PATH,
        ledger_path=root / LEDGER_PATH,
        candidate_path=candidate_path,
        snapshot_path=snapshot_path,
    )
    if snapshot.get("status") != "complete":
        raise ValueError(f"Chapter 5 fixture compile failed: {snapshot.get('errors')}")
    return snapshot


def _write_readiness(
    root: Path,
    snapshot: dict[str, Any],
    semantics: dict[str, Any],
    requirement_by_block: dict[str, str],
    by_task: dict[str, list[str]],
) -> None:
    obligation_to_req: dict[str, str] = {}
    for obligation in snapshot.get("semantic_inventory", []):
        if not isinstance(obligation, dict):
            continue
        block_ids = [str(value) for value in obligation.get("source_block_ids", [])]
        rid = next((requirement_by_block.get(value) for value in block_ids if requirement_by_block.get(value)), None)
        if rid:
            obligation_to_req[str(obligation["obligation_id"])] = rid

    for task_id in map(str, TASK_IDS):
        decisions = {
            "match_decisions": [
                {
                    "obligation_id": oid,
                    "status": "equivalent",
                    "rationale": "The reviewed Chapter 5 obligation is identical to the fixture Requirement.",
                    "chapter3_requirement_ids": [rid],
                    "action": "keep",
                }
                for oid, rid in sorted(obligation_to_req.items())
            ],
            "acceptance_links": [{
                "acceptance_index": 1,
                "requirement_ids": by_task[task_id],
                "test_refs": [TEST_PATH.as_posix()],
                "authority_refs": [],
            }],
            "authority_decisions": [{
                "authority_ref": CONTRACT_PATH.as_posix(),
                "status": "compatible",
                "rationale": "The RelayHandoff contract is the reviewed cross-task transfer authority for the fixture.",
            }],
            "dependency_decisions": [],
            "overlap_decisions": [],
            "allow_concerns": False,
        }
        decisions_path = root / f"logs/ci/chapter5/decisions/task-{task_id}.json"
        atomic_json(decisions_path, decisions)
        reconciliation, readiness = reconcile(
            root,
            task_id=task_id,
            snapshot_path=root / DEFAULT_EXTRACTION_SNAPSHOT,
            semantics_path=root / SEMANTICS_PATH,
            decisions_path=decisions_path,
            out_path=root / DEFAULT_RECONCILIATION_DIR / f"task-{task_id}.json",
            readiness_path=root / DEFAULT_READINESS_DIR / f"task-{task_id}.json",
            manifest_path=root / MANIFEST_PATH,
            ledger_path=root / LEDGER_PATH,
        )
        if readiness.get("closure_allowed") is not True:
            raise ValueError(
                f"Chapter 5 fixture readiness blocked for task {task_id}: "
                f"{reconciliation.get('summary')}"
            )
        ok, _payload, reason = load_task_readiness(root, task_id)
        if not ok:
            raise ValueError(f"Chapter 5 fixture readiness is not fresh for task {task_id}: {reason}")


def _write_topology_seed(root: Path, ledger: dict[str, Any], semantics: dict[str, Any], by_task: dict[str, list[str]]) -> None:
    topology_root = root / "docs/planning/semantic-topology"
    atomic_json(topology_root / "source-blocks.v1.json", ledger)
    atomic_json(topology_root / "semantic-requirements.v1.json", semantics)
    edges = []
    for task_id, requirement_ids in by_task.items():
        for rid in requirement_ids:
            edges.append({
                "source_type": "requirement",
                "source_id": rid,
                "target_type": "task",
                "target_id": task_id,
                "relation": "implemented_by",
                "contribution": "chapter5_stabilized",
            })
    atomic_json(topology_root / "topology-edges.v1.json", {
        "schema_version": "newrouge.topology-edges.v1",
        "source_revision": ledger.get("source_revision"),
        "edges": edges,
    })
    artifacts = {}
    for rel in (
        "docs/planning/semantic-topology/source-blocks.v1.json",
        "docs/planning/semantic-topology/semantic-requirements.v1.json",
        "docs/planning/semantic-topology/topology-edges.v1.json",
    ):
        artifacts[rel] = file_sha(root / rel)
    atomic_json(topology_root / "topology-manifest.v1.json", {
        "schema_version": "newrouge.semantic-topology-manifest.v1",
        "source_revision": ledger.get("source_revision"),
        "source_manifest_sha256": file_sha(root / MANIFEST_PATH),
        "schema_revision": "v1",
        "generator_revision": "planning-acceptance-fixture-v1",
        "artifacts": artifacts,
    })


def build_fixture(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _base_files(root)
    source_revision_commit = _init_source_revision(root)

    manifest, ledger = build_ledger(
        root,
        [GDD_PATH.as_posix()],
        "init",
        explicit=True,
    )
    atomic_json(root / MANIFEST_PATH, manifest)
    atomic_json(root / LEDGER_PATH, ledger)
    atomic_json(
        root / "docs/workflows/chapter3-source-set.json",
        source_set_payload([GDD_PATH.as_posix()], [], [GDD_PATH.as_posix()]),
    )
    semantics, requirement_by_block = _build_semantics(ledger)
    atomic_json(root / SEMANTICS_PATH, semantics)
    by_task = _write_task_triplet(root, semantics)
    snapshot = _compile_extraction_b(root, ledger, requirement_by_block, semantics)
    _write_readiness(root, snapshot, semantics, requirement_by_block, by_task)
    _write_topology_seed(root, ledger, semantics, by_task)

    return {
        "schema_version": "newrouge.planning-acceptance-fixture.v1",
        "fixture": "harbor-relay",
        "root": root.as_posix(),
        "source_revision_commit": source_revision_commit,
        "task_ids": list(TASK_IDS),
        "non_contiguous_task_ids": TASK_IDS[1] - TASK_IDS[0] > 1,
        "requirement_ids": [str(row["requirement_id"]) for row in semantics["requirements"]],
        "source_block_count": len(ledger.get("blocks", [])),
        "delivery_requirement_count": len(semantics["requirements"]),
        "chapter5_ready": {
            str(task_id): load_task_readiness(root, str(task_id))[0]
            for task_id in TASK_IDS
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = build_fixture(Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
