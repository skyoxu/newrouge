#!/usr/bin/env python3
"""Validate Chapter 3 source, semantic, and task conservation gates."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

VALID_KINDS = {
    "functional", "non_functional", "invariant", "failure", "scope", "metric",
    "constraint", "risk", "context", "rationale",
}
NON_TASK_SINK_TYPES = {"global_constraint", "quality_gate", "adr", "deferred", "exclusion"}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def projection_checks(root: Path, ledger: dict[str, Any], semantics: dict[str, Any]) -> dict[str, Any]:
    blocks = {
        str(row.get("block_id")): row
        for row in ledger.get("blocks", [])
        if isinstance(row, dict) and row.get("block_id")
    }
    accounting = {
        str(row.get("block_id")): row
        for row in semantics.get("source_accounting", [])
        if isinstance(row, dict) and row.get("block_id")
    }
    unaccounted = sorted(set(blocks) - set(accounting))
    unknown_accounting = sorted(set(accounting) - set(blocks))
    invalid_semantics = []
    requirements = [row for row in semantics.get("requirements", []) if isinstance(row, dict)]
    ids = set()
    for row in requirements:
        rid = str(row.get("requirement_id") or "")
        issues = []
        if not rid or rid in ids:
            issues.append("missing_or_duplicate_id")
        ids.add(rid)
        if row.get("kind") not in VALID_KINDS:
            issues.append("invalid_kind")
        if not str(row.get("statement") or "").strip():
            issues.append("missing_statement")
        refs = row.get("source_block_ids")
        if not isinstance(refs, list) or not refs or any(str(ref) not in blocks for ref in refs):
            issues.append("invalid_source_block_ids")
        if not isinstance(row.get("delivery_relevant"), bool):
            issues.append("invalid_delivery_relevant")
        if not str(row.get("sink_policy") or "").strip():
            issues.append("missing_sink_policy")
        if not str(row.get("status") or "").strip():
            issues.append("missing_status")
        if issues:
            invalid_semantics.append({"requirement_id": rid, "issues": issues})

    source_hash_drift = []
    seen_paths = set()
    for block in blocks.values():
        source_path = str(block.get("source_path") or "")
        if not source_path or source_path in seen_paths:
            continue
        seen_paths.add(source_path)
        path = root / source_path
        if not path.is_file():
            source_hash_drift.append({"path": source_path, "reason": "missing"})
            continue
        actual = sha256_file(path)
        expected = str(block.get("source_sha256") or "").removeprefix("sha256:")
        if actual != expected:
            source_hash_drift.append({
                "path": source_path,
                "reason": "hash_mismatch",
                "expected": expected,
                "actual": actual,
            })

    unresolved_delivery = []
    for block_id, row in accounting.items():
        if str(row.get("disposition")) != "unresolved" or not bool(row.get("delivery_potential")):
            continue
        decision = row.get("decision")
        resolved = (
            isinstance(decision, dict)
            and str(decision.get("owner") or "").strip()
            and str(decision.get("reason") or "").strip()
            and str(decision.get("resolved_disposition") or "") in {
                "deferred", "out_of_scope", "adr_owned", "context", "rationale",
            }
        )
        if not resolved:
            unresolved_delivery.append(block_id)

    return {
        "unaccounted_source_blocks": unaccounted,
        "unknown_accounting_blocks": unknown_accounting,
        "invalid_semantics": invalid_semantics,
        "source_hash_drift": source_hash_drift,
        "unresolved_delivery_potential": sorted(unresolved_delivery),
        "source_block_count": len(blocks),
        "semantic_requirement_count": len(requirements),
    }


def closure_checks(
    semantics: dict[str, Any],
    candidates: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requirements = {
        str(row.get("requirement_id")): row
        for row in semantics.get("requirements", [])
        if isinstance(row, dict) and row.get("requirement_id")
    }
    task_sinks = {}
    invalid_task_refs = []
    complexity_violations = []
    edges = []
    edge_keys = set()

    def add_edge(source_type: str, source_id: str, target_type: str, target_id: str, relation: str, **extra: Any) -> None:
        key = (source_type, source_id, target_type, target_id, relation)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation": relation,
            **extra,
        })

    candidate_rows = [
        row for row in (candidates or {}).get("candidates", []) if isinstance(row, dict)
    ]
    for task in candidate_rows:
        task_id = str(task.get("id") or "")
        try:
            score = int(task.get("complexity_score") or 0)
        except (TypeError, ValueError):
            score = 99
        if score > 7:
            complexity_violations.append({"task_id": task_id, "complexity_score": score})
        refs = task.get("semantic_refs", task.get("requirement_ids", []))
        if not isinstance(refs, list):
            invalid_task_refs.append({"task_id": task_id, "reason": "invalid_ref_shape"})
            continue
        for value in refs:
            rid = str(value)
            requirement = requirements.get(rid)
            if requirement is None:
                invalid_task_refs.append({"task_id": task_id, "requirement_id": rid, "reason": "unknown"})
                continue
            if str(requirement.get("status", "active")).casefold() in {"removed", "superseded"}:
                invalid_task_refs.append({"task_id": task_id, "requirement_id": rid, "reason": "stale"})
                continue
            task_sinks.setdefault(rid, []).append(task_id)
            add_edge(
                "requirement", rid, "task", task_id, "implemented_by",
                contribution=str(task.get("contribution") or "implementation"),
            )
        for capability_id in task.get("capability_refs", []):
            add_edge("capability", str(capability_id), "task", task_id, "implemented_by")

    orphan = []
    coverage = []
    for rid, requirement in requirements.items():
        if str(requirement.get("status", "active")).casefold() != "active":
            continue
        if requirement.get("delivery_relevant") is not True:
            continue
        non_task_sinks = [
            sink for sink in requirement.get("non_task_sinks", [])
            if isinstance(sink, dict)
            and str(sink.get("type") or "") in NON_TASK_SINK_TYPES
            and str(sink.get("id") or "").strip()
        ]
        task_ids = sorted(set(task_sinks.get(rid, [])))
        has_sink = bool(task_ids or non_task_sinks)
        row = {
            "requirement_id": rid,
            "task_ids": task_ids,
            "non_task_sinks": non_task_sinks,
            "coverage_status": "covered" if has_sink else "orphan",
        }
        coverage.append(row)
        if not has_sink:
            orphan.append(row)

    return {
        "delivery_requirement_count": len(coverage),
        "orphan_delivery_requirements": orphan,
        "invalid_task_semantic_refs": invalid_task_refs,
        "complexity_violations": complexity_violations,
        "task_coverage": coverage,
    }, edges


def validate(
    root: Path,
    ledger: dict[str, Any],
    semantics: dict[str, Any],
    stage: str,
    candidates: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    projection = projection_checks(root, ledger, semantics)
    closure = {
        "delivery_requirement_count": 0,
        "orphan_delivery_requirements": [],
        "invalid_task_semantic_refs": [],
        "complexity_violations": [],
        "task_coverage": [],
    }
    task_edges = []
    if stage == "closure":
        closure, task_edges = closure_checks(semantics, candidates)
    blocking_counts = {
        "unaccounted_source_blocks": len(projection["unaccounted_source_blocks"]),
        "unknown_accounting_blocks": len(projection["unknown_accounting_blocks"]),
        "invalid_semantics": len(projection["invalid_semantics"]),
        "source_hash_drift": len(projection["source_hash_drift"]),
        "unresolved_delivery_potential": len(projection["unresolved_delivery_potential"]),
        "orphan_delivery_requirements": len(closure["orphan_delivery_requirements"]),
        "invalid_task_semantic_refs": len(closure["invalid_task_semantic_refs"]),
        "complexity_violations": len(closure["complexity_violations"]),
    }
    blocked = any(value > 0 for value in blocking_counts.values())
    report = {
        "schema_version": "chapter3.semantic-conservation-report.v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stage": stage,
        "source_revision": ledger.get("source_revision"),
        "status": "blocked" if blocked else "passed",
        "blocking_counts": blocking_counts,
        "source_coverage": {
            "source_block_count": projection["source_block_count"],
            "accounted_count": projection["source_block_count"] - len(projection["unaccounted_source_blocks"]),
            "unaccounted_count": len(projection["unaccounted_source_blocks"]),
        },
        "semantic_coverage": {
            "semantic_requirement_count": projection["semantic_requirement_count"],
            "invalid_count": len(projection["invalid_semantics"]),
            "unresolved_delivery_potential_count": len(projection["unresolved_delivery_potential"]),
        },
        "task_coverage": {
            "delivery_requirement_count": closure["delivery_requirement_count"],
            "orphan_count": len(closure["orphan_delivery_requirements"]),
            "invalid_task_ref_count": len(closure["invalid_task_semantic_refs"]),
        },
        "details": {**projection, **closure},
    }
    return report, task_edges


def merge_edges(base_edges: dict[str, Any] | None, task_edges: list[dict[str, Any]], source_revision: Any) -> dict[str, Any]:
    rows = []
    seen = set()
    for edge in list((base_edges or {}).get("edges", [])) + task_edges:
        if not isinstance(edge, dict):
            continue
        key = (
            edge.get("source_type"),
            edge.get("source_id"),
            edge.get("target_type"),
            edge.get("target_id"),
            edge.get("relation"),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(edge)
    return {
        "schema_version": "newrouge.topology-edges.v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": source_revision,
        "edges": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stage", choices=["projection", "closure"], default="projection")
    parser.add_argument("--ledger", default="logs/ci/task-generation/source-blocks.v1.json")
    parser.add_argument("--semantics", default="logs/ci/task-generation/semantic-requirements.v1.json")
    parser.add_argument("--candidates", default="logs/ci/task-generation/task-candidates.enriched.json")
    parser.add_argument("--base-edges", default="logs/ci/task-generation/topology-edges.base.v1.json")
    parser.add_argument("--edges-out", default="logs/ci/task-generation/topology-edges.v1.json")
    parser.add_argument("--out", default="logs/ci/task-generation/semantic-conservation-report.json")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    ledger = load_json(root / args.ledger, {})
    semantics = load_json(root / args.semantics, {})
    candidates = load_json(root / args.candidates, {"candidates": []}) if args.stage == "closure" else None
    report, task_edges = validate(root, ledger, semantics, args.stage, candidates)
    write_json(root / args.out, report)
    if args.stage == "closure":
        write_json(
            root / args.edges_out,
            merge_edges(
                load_json(root / args.base_edges, {"edges": []}),
                task_edges,
                ledger.get("source_revision"),
            ),
        )
    print(
        f"semantic_conservation={root / args.out} stage={args.stage} "
        f"status={report['status']} blocking={sum(report['blocking_counts'].values())}"
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
