"""Resolve the current source round's existing task and non-task sinks."""
from pathlib import Path
from typing import Any

from _planning_skill_common import load_json


def round_scope(root: Path, task_ids: list[str], ledger_path: Path, semantics_path: Path) -> dict[str, Any]:
    ledger = load_json(ledger_path, {})
    semantics = load_json(semantics_path, {})
    blocks = {str(b["block_id"]): b for b in ledger.get("blocks", []) if isinstance(b, dict)}
    delta = ledger.get("delta") or {}
    changed = set(map(str, delta.get("added", []) + delta.get("changed", [])))
    paths = {str(blocks[b].get("source_path")) for b in changed if b in blocks}
    # A cumulative re-plan with no changed blocks still needs its declared sinks.
    if not paths:
        paths = {str(b.get("source_path")) for b in blocks.values()}
    scoped_blocks = {bid for bid, b in blocks.items() if str(b.get("source_path")) in paths}
    requirements = [r for r in semantics.get("requirements", []) if isinstance(r, dict)
        and r.get("status", "active") == "active" and r.get("delivery_relevant") is True
        and scoped_blocks.intersection(map(str, r.get("source_block_ids", [])))]
    sinks: dict[str, set[str]] = {}
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        for row in load_json(root / ".taskmaster/tasks" / name, []):
            if not isinstance(row, dict) or row.get("taskmaster_id") is None:
                continue
            for rid in row.get("semantic_refs", row.get("requirement_ids", [])):
                sinks.setdefault(str(rid), set()).add(str(row["taskmaster_id"]))
    required: set[str] = set()
    non_task = []
    errors = []
    for req in requirements:
        rid = str(req["requirement_id"])
        required.update(sinks.get(rid, set()))
        others = [s for s in req.get("non_task_sinks", []) if isinstance(s, dict)
            and str(s.get("type") or "").strip() and str(s.get("id") or "").strip()]
        non_task.extend({"requirement_id": rid, **s} for s in others)
        if not sinks.get(rid) and not others:
            errors.append(f"round_requirement_missing_sink:{rid}")
    missing = sorted(required - set(map(str, task_ids)))
    if missing:
        errors.append("round_task_scope_incomplete:" + ",".join(missing))
    if not requirements:
        errors.append("round_delivery_scope_missing")
    witness = None
    if requirements and not required:
        # Reuse a current Chapter 5 global audit from a real task; do not mint
        # a synthetic task/readiness authority for non-task sinks.
        from chapter5_semantic_reconciliation import (
            DEFAULT_READINESS_DIR, load_task_readiness, reconciliation_path_for_task,
        )
        latest = load_json(root / DEFAULT_READINESS_DIR / "latest.json", {})
        tid = str(latest.get("task_id") or "")
        ok, _, _ = load_task_readiness(root, tid) if tid else (False, {}, "missing")
        audit = load_json(reconciliation_path_for_task(root, tid), {}) if tid else {}
        if ok and audit.get("global_audit_completed") is True:
            witness = tid
        else:
            errors.append("round_non_task_global_chapter5_audit_required")
    return {"source_paths": sorted(paths), "requirement_ids": sorted(str(r["requirement_id"]) for r in requirements),
        "required_task_ids": sorted(required), "non_task_sinks": non_task, "global_chapter5_witness": witness, "errors": errors}
