#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pre-check whether TDD acceptance-test generation should require an execution plan."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _bootstrap_imports() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


_bootstrap_imports()

import _execution_plan_policy as _policy  # noqa: E402
from _taskmaster import resolve_triplet  # noqa: E402
from _util import ci_dir, repo_root, write_json, write_text  # noqa: E402


def _build_report_markdown(*, payload: dict) -> str:
    signal_lines = [
        f"- {item['id']}: {'active' if item['active'] else 'inactive'} ({item['detail']})"
        for item in payload.get("signals", [])
        if isinstance(item, dict)
    ]
    lines = [
        f"# TDD Execution-Plan Check (Task {payload.get('task_id', '')})",
        "",
        f"- Policy: {payload.get('policy', '')}",
        f"- Decision: {payload.get('decision', '')}",
        f"- Need level: {payload.get('need_level', 'none')}",
        f"- Threshold hit: {payload.get('threshold_hit', False)}",
        f"- Signal count: {payload.get('signal_count', 0)}",
        f"- Reasons: {', '.join(payload.get('reason_codes', [])) or 'none'}",
        f"- Missing refs: {payload.get('missing_refs_count', 0)}",
        f"- Anchor count: {payload.get('anchor_count', 0)}",
        f"- Active execution plans: {', '.join(payload.get('active_execution_plans', [])) or 'none'}",
        f"- Created execution plan: {payload.get('created_execution_plan', '') or 'none'}",
        f"- Message: {payload.get('message', '')}",
        "",
        "## Signals",
        "",
        *(signal_lines or ["- none"]),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether acceptance-driven TDD work should create or require an execution plan.")
    ap.add_argument("--task-id", required=True, help="Task id (master id, e.g. 11).")
    ap.add_argument("--tdd-stage", choices=["normal", "red-first"], default="normal")
    ap.add_argument("--verify", choices=["none", "unit", "all", "auto"], default="auto")
    ap.add_argument("--execution-plan-policy", choices=["off", "warn", "draft", "require"], default="warn")
    ap.add_argument("--latest-json", default="", help="Optional latest.json path for execution-plan linkage.")
    ap.add_argument(
        "--plan-signal",
        action="append",
        default=[],
        choices=sorted(_policy.REQUIRED_PLAN_SIGNALS | _policy.RECOMMENDED_PLAN_SIGNALS),
        help="Persistent coordination/recovery signal. May be repeated.",
    )
    ap.add_argument("--plan-reason", default="", help="Short observable reason for the declared plan signal.")
    args = ap.parse_args()

    task_id = str(args.task_id).split(".", 1)[0].strip()
    if not task_id.isdigit():
        print("SC_TDD_EXECUTION_PLAN ERROR: --task-id must be a numeric master id.")
        return 2

    root = repo_root()
    out_dir = ci_dir("sc-tdd-execution-plan")
    triplet = resolve_triplet(task_id=task_id)
    assessment = _policy.assess_execution_plan_need(
        repo_root=root,
        triplet=triplet,
        task_id=task_id,
        tdd_stage=str(args.tdd_stage),
        verify=str(args.verify),
        plan_signals=list(args.plan_signal or []),
        plan_reason=str(args.plan_reason or ""),
    )
    active_plans = _policy.find_active_execution_plans(root, task_id=task_id)
    created_execution_plan = ""
    decision = "ok"
    message = "No execution-plan escalation is required."
    signal_count = sum(1 for item in assessment.signals if item["active"])

    if assessment.need_level == "required" and not active_plans:
        if str(args.execution_plan_policy) == "off":
            decision = "skip"
            message = "A durable plan is required by persistent coordination signals, but policy=off leaves enforcement to the operator."
        elif str(args.execution_plan_policy) == "warn":
            decision = "warn"
            message = "A durable plan is required by persistent coordination signals; create or bind one before staged writes."
        elif str(args.execution_plan_policy) == "draft":
            created_execution_plan = _policy.create_execution_plan_draft(
                repo_root=root,
                task_id=task_id,
                title=assessment.title,
                assessment=assessment,
                latest_json=str(args.latest_json),
            )
            decision = "draft"
            message = f"Persistent coordination requires a durable plan; created draft at {created_execution_plan}."
        else:
            decision = "require_failed"
            message = "Persistent coordination requires an active execution plan and policy=require."
    elif assessment.need_level == "recommended" and not active_plans:
        decision = "recommended"
        message = "A durable plan is recommended for the declared risk, but it is not an execution gate."

    payload = {
        "cmd": "sc-check-tdd-execution-plan",
        "task_id": task_id,
        "title": assessment.title,
        "policy": str(args.execution_plan_policy),
        "tdd_stage": str(args.tdd_stage),
        "verify": str(args.verify),
        "threshold_hit": assessment.threshold_hit,
        "need_level": assessment.need_level,
        "reason_codes": assessment.reason_codes,
        "signal_count": signal_count,
        "signals": assessment.signals,
        "refs_total": assessment.refs_total,
        "allowed_refs": assessment.allowed_refs,
        "missing_refs": assessment.missing_refs,
        "missing_refs_count": assessment.missing_refs_count,
        "anchor_count": assessment.anchor_count,
        "test_roots": assessment.test_roots,
        "active_execution_plans": active_plans,
        "created_execution_plan": created_execution_plan,
        "decision": decision,
        "message": message,
        "out_dir": str(out_dir),
    }
    write_json(out_dir / f"summary-{task_id}.json", payload)
    write_text(out_dir / f"summary-{task_id}.md", _build_report_markdown(payload=payload))

    failed = decision == "require_failed"
    print(
        "SC_TDD_EXECUTION_PLAN "
        f"status={'fail' if failed else 'ok'} "
        f"policy={args.execution_plan_policy} "
        f"need_level={assessment.need_level} "
        f"threshold_hit={'true' if assessment.threshold_hit else 'false'} "
        f"signal_count={signal_count} "
        f"active_plans={len(active_plans)} "
        f"out={out_dir}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
