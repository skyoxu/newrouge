#!/usr/bin/env python3
"""Apply the reviewed six-batch semantic decisions for the frozen task GDD."""

from __future__ import annotations

import json
import re
from pathlib import Path

from build_gdd_from_task_baseline import render
from chapter3_task_scope import load_scope, validate_master

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "logs/ci/task-generation"
TASK_ROW = re.compile(r"^\| T(\d+) \|")
GOVERNANCE_IDS = {1, 2, 38, 44, 49, 53, 54, 55, 56, 57, 58, 65, 68, 92, 93, 94, 102, 103, 104, 108, 109, 112}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def reviewed_candidate(root: Path) -> tuple[dict, dict]:
    scope = load_scope(root)
    if scope is None:
        raise ValueError("Frozen task scope is required")
    expected_ids = validate_master(root, scope)
    gdd_path = root / scope["gdd_path"]
    if gdd_path.read_text(encoding="utf-8") != render(root):
        raise ValueError("GDD no longer matches the frozen triplet")
    master = {
        task["id"]: task
        for task in load(root / scope["master_path"])["master"]["tasks"]
    }
    view_rows: dict[int, list[dict]] = {task_id: [] for task_id in expected_ids}
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        for row in load(root / ".taskmaster/tasks" / name):
            if row.get("taskmaster_id") in view_rows:
                view_rows[row["taskmaster_id"]].append(row)
    ledger = load(ARTIFACTS / "source-blocks.v1.json")
    batches = load(ARTIFACTS / "semantic-projection.batches.v1.json")
    candidate = load(ARTIFACTS / "semantic-projection.candidate.json")
    if candidate.get("source_revision") != ledger.get("source_revision"):
        raise ValueError("Candidate source revision drift")
    if batches.get("batch_count") != 6 or ledger.get("blocks") is None:
        raise ValueError("The reviewed six-batch source set has changed")
    by_block = {row["block_id"]: row for row in ledger["blocks"]}
    results = {row["block_id"]: row for row in candidate["block_results"]}
    seen_tasks: set[int] = set()
    batch_counts: dict[str, int] = {row["batch_id"]: 0 for row in batches["batches"]}
    for batch in batches["batches"]:
        source = load(ARTIFACTS / "semantic-batches" / (batch["batch_id"].lower() + ".json"))
        if [row["block_id"] for row in source["blocks"]] != batch["block_ids"]:
            raise ValueError("Prepared batch content changed")
        for block in source["blocks"]:
            block_id = block["block_id"]
            if block != by_block[block_id]:
                raise ValueError(f"Ledger block drift: {block_id}")
            result = results[block_id]
            if result.get("review_status") != "review_required":
                raise ValueError(f"Unexpected pre-reviewed block: {block_id}")
            match = TASK_ROW.match(block["raw_text"])
            if match:
                task_id = int(match.group(1))
                if task_id not in expected_ids or task_id in seen_tasks:
                    raise ValueError(f"Unknown or repeated task row: {task_id}")
                seen_tasks.add(task_id)
                task = master[task_id]
                if task["status"] == "cancelled":
                    result.update({
                        "atoms": [], "disposition": "superseded", "delivery_potential": False,
                        "decision": {"owner": "Taskmaster", "reason": f"T{task_id} is cancelled in the master task SSoT; retain its source row for history."},
                        "review_status": "reviewed",
                    })
                else:
                    kind = "non_functional" if task_id in GOVERNANCE_IDS else "functional"
                    prefix = "NFR" if kind == "non_functional" else "FR"
                    statement = str(task.get("description") or task.get("title") or "").strip()
                    view_detail = list(dict.fromkeys(
                        str(row.get("description") or "").strip()
                        for row in view_rows[task_id]
                        if str(row.get("description") or "").strip() != statement
                    ))
                    if view_detail:
                        statement += " View-specific detail: " + " / ".join(view_detail)
                    result.update({
                        "atoms": [{
                            "requirement_id": f"{prefix}-T{task_id:04d}",
                            "kind": kind,
                            "statement": statement,
                            "source_block_ids": [block_id],
                            "delivery_relevant": True,
                            "sink_policy": "task_required",
                            "priority": "P1" if task.get("priority") == "high" else "P2",
                            "owner_hint": "gameplay" if any(row.get("owner") == "gameplay" for row in view_rows[task_id]) else "architecture",
                            "rationale": f"Existing frozen Taskmaster identity T{task_id}; no new task is authorized.",
                        }],
                        "disposition": "atomized", "delivery_potential": True,
                        "decision": {"owner": f"T{task_id}", "reason": "Reviewed task-scope row with an explicit frozen Taskmaster identity."},
                        "review_status": "reviewed",
                    })
            else:
                if block["block_type"] not in {"heading", "paragraph", "table_row", "table_separator"}:
                    raise ValueError(f"Unexpected non-task block type: {block_id}")
                result.update({
                    "atoms": [], "disposition": "context", "delivery_potential": False,
                    "decision": {"owner": "Chapter 3", "reason": "Document identity, table header, or task-scope governance context; no standalone delivery requirement."},
                    "review_status": "reviewed",
                })
            batch_counts[batch["batch_id"]] += 1
    if seen_tasks != expected_ids or len(results) != len(by_block):
        raise ValueError("Reviewed task rows or source blocks are incomplete")
    for summary in candidate["batch_summaries"]:
        summary["output_accounted_count"] = batch_counts[summary["batch_id"]]
    report = {
        "schema_version": "chapter3.frozen-task-projection-review.v1",
        "source_revision": ledger["source_revision"],
        "source_manifest_sha256": ledger["source_manifest_sha256"],
        "batch_count": len(batches["batches"]),
        "reviewed_source_blocks": len(results),
        "task_rows": len(seen_tasks),
        "active_task_requirements": sum(master[task_id]["status"] != "cancelled" for task_id in seen_tasks),
        "retired_task_rows": sorted(task_id for task_id in seen_tasks if master[task_id]["status"] == "cancelled"),
        "created_tasks": 0,
    }
    return candidate, report


def main() -> int:
    candidate, report = reviewed_candidate(ROOT)
    save(ARTIFACTS / "semantic-projection.candidate.json", candidate)
    save(ARTIFACTS / "frozen-task-projection-review.v1.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
