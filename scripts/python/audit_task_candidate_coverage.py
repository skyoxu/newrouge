#!/usr/bin/env python3
"""Audit semantic Requirement to Task sink coverage.

Legacy P0/P1 anchor coverage remains available as a downstream packaging gate.
When validated semantic requirements are present, active delivery requirements
must have a Task or explicit non-Task sink.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

BLOCKING_PRIORITIES = {"P0", "P1"}
NON_TASK_SINK_TYPES = {"global_constraint", "quality_gate", "adr", "deferred", "exclusion"}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_coverage(candidates: dict[str, Any]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    by_req: dict[str, list[str]] = {}
    rows = [row for row in candidates.get("candidates", []) if isinstance(row, dict)]
    for task in rows:
        tid = str(task.get("id", ""))
        refs = task.get("semantic_refs", task.get("requirement_ids", []))
        if not isinstance(refs, list):
            continue
        for rid in refs:
            by_req.setdefault(str(rid), []).append(tid)
    return by_req, rows


def audit_legacy(requirements: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    by_req, _tasks = candidate_coverage(candidates)
    rows = []
    missing_blocking = []
    for anchor in requirements.get("anchors", []):
        rid = str(anchor.get("requirement_id"))
        covered = sorted(set(by_req.get(rid, [])))
        priority = str(anchor.get("priority", "P2")).upper()
        status = "covered" if covered else "missing"
        row = {
            "requirement_id": rid,
            "priority": priority,
            "kind": anchor.get("kind"),
            "source": f"{anchor.get('source_path')}:{anchor.get('line')}",
            "coverage_status": status,
            "covered_by_tasks": covered,
        }
        rows.append(row)
        if status == "missing" and priority in BLOCKING_PRIORITIES:
            missing_blocking.append(row)
    return {
        "schema": "task-generation.coverage-report.v1",
        "coverage_model": "legacy-p0-p1-packaging",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requirement_count": len(rows),
        "candidate_count": len(candidates.get("candidates", [])),
        "missing_count": sum(1 for row in rows if row["coverage_status"] == "missing"),
        "missing_blocking_count": len(missing_blocking),
        "status": "ok" if not missing_blocking else "blocked",
        "coverage": rows,
        "missing_blocking": missing_blocking,
        "invalid_task_semantic_refs": [],
    }


def audit_semantic(semantics: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    by_req, tasks = candidate_coverage(candidates)
    requirements = {
        str(row.get("requirement_id")): row
        for row in semantics.get("requirements", [])
        if isinstance(row, dict) and row.get("requirement_id")
    }
    invalid_refs = []
    for task in tasks:
        task_id = str(task.get("id", ""))
        refs = task.get("semantic_refs", task.get("requirement_ids", []))
        if not isinstance(refs, list):
            invalid_refs.append({"task_id": task_id, "reason": "invalid_ref_shape"})
            continue
        for rid in refs:
            if str(rid) not in requirements:
                invalid_refs.append({
                    "task_id": task_id,
                    "requirement_id": str(rid),
                    "reason": "unknown_requirement",
                })
    rows = []
    missing = []
    for rid, requirement in sorted(requirements.items()):
        if str(requirement.get("status", "active")).casefold() != "active":
            continue
        if requirement.get("delivery_relevant") is not True:
            continue
        tasks_for_requirement = sorted(set(by_req.get(rid, [])))
        non_task_sinks = [
            sink for sink in requirement.get("non_task_sinks", [])
            if isinstance(sink, dict)
            and str(sink.get("type") or "") in NON_TASK_SINK_TYPES
            and str(sink.get("id") or "").strip()
        ]
        covered = bool(tasks_for_requirement or non_task_sinks)
        row = {
            "requirement_id": rid,
            "priority": str(requirement.get("priority") or "P2").upper(),
            "kind": requirement.get("kind"),
            "source_block_ids": list(requirement.get("source_block_ids", [])),
            "coverage_status": "covered" if covered else "missing",
            "covered_by_tasks": tasks_for_requirement,
            "non_task_sinks": non_task_sinks,
        }
        rows.append(row)
        if not covered:
            missing.append(row)
    blocked = bool(missing or invalid_refs)
    return {
        "schema": "task-generation.coverage-report.v2",
        "coverage_model": "semantic-sink",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requirement_count": len(rows),
        "candidate_count": len(tasks),
        "missing_count": len(missing),
        "missing_blocking_count": len(missing),
        "status": "blocked" if blocked else "ok",
        "coverage": rows,
        "missing_blocking": missing,
        "invalid_task_semantic_refs": invalid_refs,
        "source_coverage": semantics.get("source_accounting", []),
    }


def audit(requirements: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    if requirements.get("schema_version") == "newrouge.semantic-requirements.v1":
        return audit_semantic(requirements, candidates)
    return audit_legacy(requirements, candidates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--requirements", default="logs/ci/task-generation/requirements.index.json")
    parser.add_argument("--semantics", default="logs/ci/task-generation/semantic-requirements.v1.json")
    parser.add_argument("--candidates", default="logs/ci/task-generation/task-candidates.enriched.json")
    parser.add_argument("--out", default="logs/ci/task-generation/coverage-report.json")
    parser.add_argument("--allow-missing-p1", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    semantics_path = root / args.semantics
    source = load_json(semantics_path) if semantics_path.is_file() else load_json(root / args.requirements, {})
    result = audit(source, load_json(root / args.candidates, {"candidates": []}))
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"coverage_report={out} model={result['coverage_model']} "
        f"status={result['status']} missing_blocking={result['missing_blocking_count']}"
    )
    if result["status"] != "ok" and not args.allow_missing_p1:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
