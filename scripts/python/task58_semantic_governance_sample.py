#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("input json must be an object")
    return payload


def _extract_acceptance_ids(items: list[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(r"ACC:[A-Za-z0-9_.-]+")
    for item in items:
        for matched in pattern.findall(item):
            if matched not in seen:
                seen.add(matched)
                ids.append(matched)
    return ids


def _load_task_context(task_id: int) -> dict[str, Any]:
    repo_root = _repo_root()
    tasks_path = repo_root / ".taskmaster" / "tasks" / "tasks.json"
    back_path = repo_root / ".taskmaster" / "tasks" / "tasks_back.json"

    tasks_doc = _read_json(tasks_path)
    back_doc_raw = json.loads(back_path.read_text(encoding="utf-8"))
    if not isinstance(back_doc_raw, list):
        raise ValueError("tasks_back.json must be an array")

    master_tasks = (
        tasks_doc.get("master", {})
        .get("tasks", [])
    )
    if not isinstance(master_tasks, list):
        raise ValueError("tasks.json master.tasks must be an array")

    task_record = None
    for item in master_tasks:
        if isinstance(item, dict) and item.get("id") == task_id:
            task_record = item
            break
    if task_record is None:
        raise ValueError(f"task {task_id} not found in tasks.json")

    back_record = None
    for item in back_doc_raw:
        if isinstance(item, dict) and item.get("taskmaster_id") == task_id:
            back_record = item
            break
    if back_record is None:
        raise ValueError(f"task {task_id} not found in tasks_back.json")

    master_details = str(task_record.get("details", ""))
    acceptance_items_raw = back_record.get("acceptance")
    if not isinstance(acceptance_items_raw, list):
        acceptance_items_raw = back_record.get("acceptance_criteria", [])
    acceptance_items = [str(it) for it in acceptance_items_raw] if isinstance(acceptance_items_raw, list) else []
    acceptance_ids = _extract_acceptance_ids(acceptance_items)

    allowed_scope_items: list[str] = []
    if master_details.strip():
        allowed_scope_items.append("task.master.details")
    if acceptance_items:
        allowed_scope_items.append("task.mapped.acceptance")

    return {
        "task_id": task_id,
        "master_details_present": bool(master_details.strip()),
        "mapped_acceptance_count": len(acceptance_items),
        "mapped_acceptance_ids": acceptance_ids,
        "allowed_scope_items": allowed_scope_items,
    }


def _build_payload(sample: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "task_id": 58,
        "sample": sample,
        "semantic_policy_mode": "strict",
        "gate_precedence": "acceptance_first",
        "platform": "windows",
        "run_id": "task58-sample-run",
        "manual_edit_required": False,
        "command": f"py -3 scripts/python/task58_semantic_governance_sample.py --sample {sample}",
        "acceptance_check": "ok",
        "blocker_findings": [],
        "advisory_findings": [],
        "advisory_notes": [],
        "evidence_refs": {
            "acceptance_check_summary": "logs/ci/<date>/sc-acceptance-check-task-<id>/summary.json",
            "llm_review_summary": "logs/ci/<date>/sc-llm-review-task-<id>/summary.json",
        },
        "evidence_summaries": {
            "acceptance_check": {
                "status": "ok",
                "task_id": 58,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "finding_count": 0,
            },
            "llm_review": {
                "status": "ok",
                "task_id": 58,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "summary_count": 0,
            },
        },
    }

    if sample == "pass":
        base["governance_result"] = "pass"
        base["evidence_summaries"]["llm_review"]["summary_count"] = 1
        return base

    if sample == "advisory-warning":
        base["governance_result"] = "pass"
        base["advisory_findings"] = [
            {
                "id": "scope:repo.scan",
                "severity": "info",
                "classification": "advisory_out_of_scope",
                "message": "Scope item 'repo.scan' is outside policy evaluation boundary.",
                "elevation_rule_id": "",
                "evidence": "",
            },
            {
                "id": "warn-1",
                "severity": "warn",
                "classification": "advisory_warn",
                "message": "Naming consistency warning.",
                "elevation_rule_id": "",
                "evidence": "",
            },
        ]
        base["advisory_notes"] = ["out_of_scope:repo.scan", "advisory:warn-1"]
        base["evidence_summaries"]["llm_review"]["summary_count"] = 2
        return base

    if sample == "acceptance-fail":
        base["acceptance_check"] = "fail"
        base["governance_result"] = "fail"
        base["advisory_findings"] = [
            {
                "id": "warn-acceptance",
                "severity": "warn",
                "classification": "advisory_warn",
                "message": "Warning does not override acceptance failure.",
                "elevation_rule_id": "",
                "evidence": "",
            }
        ]
        base["advisory_notes"] = ["advisory:warn-acceptance"]
        base["evidence_summaries"]["acceptance_check"]["status"] = "fail"
        base["evidence_summaries"]["llm_review"]["summary_count"] = 1
        return base

    if sample == "elevated-blocker":
        base["governance_result"] = "fail"
        base["blocker_findings"] = [
            {
                "id": "warn-elevated",
                "severity": "blocker",
                "classification": "elevated_warn",
                "message": "Explicitly elevated warning.",
                "elevation_rule_id": "RULE-ELV-001",
                "evidence": "logs/ci/2026-04-18/sc-review-pipeline-task-58/latest.json",
            }
        ]
        base["advisory_findings"] = [
            {
                "id": "warn-normal",
                "severity": "warn",
                "classification": "advisory_warn",
                "message": "Non-elevated warning remains advisory.",
                "elevation_rule_id": "",
                "evidence": "",
            }
        ]
        base["advisory_notes"] = ["advisory:warn-normal"]
        base["evidence_summaries"]["llm_review"]["summary_count"] = 2
        return base

    if sample == "elevated-missing-evidence":
        base["governance_result"] = "pass"
        base["advisory_findings"] = [
            {
                "id": "warn-elevated-missing-evidence",
                "severity": "warn",
                "classification": "invalid_elevation_missing_evidence",
                "message": "Elevation rejected because supporting evidence is missing.",
                "elevation_rule_id": "RULE-ELV-001",
                "evidence": "",
            }
        ]
        base["advisory_notes"] = ["invalid_elevation:warn-elevated-missing-evidence"]
        base["evidence_summaries"]["llm_review"]["summary_count"] = 1
        return base

    raise ValueError(f"unsupported sample: {sample}")


def _normalize_finding(raw: dict[str, Any]) -> dict[str, str]:
    finding_id = str(raw.get("id", "")).strip() or "finding-unknown"
    severity = str(raw.get("severity", "warn")).strip().lower() or "warn"
    scope_item = str(raw.get("scope_item", "")).strip()
    elevation_rule_id = str(raw.get("elevation_rule_id", "")).strip()
    evidence = str(raw.get("evidence", "")).strip()
    message = str(raw.get("message", "")).strip()
    if not message:
        message = f"Finding '{finding_id}' evaluated by semantic governance policy."
    return {
        "id": finding_id,
        "severity": severity,
        "scope_item": scope_item,
        "elevation_rule_id": elevation_rule_id,
        "evidence": evidence,
        "message": message,
    }


def _build_payload_from_input(
    input_payload: dict[str, Any],
    task_context: dict[str, Any] | None,
    command: str,
    task_id_override: int | None,
) -> dict[str, Any]:
    acceptance_check = str(input_payload.get("acceptance_check", "ok")).strip().lower()
    if acceptance_check not in {"ok", "fail"}:
        raise ValueError("acceptance_check must be either 'ok' or 'fail'")

    findings_raw = input_payload.get("findings", [])
    if not isinstance(findings_raw, list):
        raise ValueError("findings must be an array")

    normalized_findings: list[dict[str, str]] = []
    for item in findings_raw:
        if not isinstance(item, dict):
            raise ValueError("each finding must be an object")
        normalized_findings.append(_normalize_finding(item))

    input_policy_scope_raw = input_payload.get("policy_scope", [])
    input_policy_scope = (
        [str(item) for item in input_policy_scope_raw]
        if isinstance(input_policy_scope_raw, list)
        else []
    )
    input_task_context_raw = input_payload.get("task_context")
    input_task_context = input_task_context_raw if isinstance(input_task_context_raw, dict) else {}

    context_payload = dict(task_context or {})
    if not context_payload and input_task_context:
        context_payload = dict(input_task_context)

    context_scope = list(context_payload.get("allowed_scope_items", []))
    effective_scope = context_scope or input_policy_scope

    advisory_findings: list[dict[str, str]] = []
    blocker_findings: list[dict[str, str]] = []
    advisory_notes: list[str] = []

    for finding in normalized_findings:
        scope_item = finding["scope_item"]
        if scope_item and effective_scope and scope_item not in effective_scope:
            advisory_findings.append({
                "id": finding["id"],
                "severity": "info",
                "classification": "advisory_out_of_scope",
                "message": f"Scope item '{scope_item}' is outside policy evaluation boundary.",
                "elevation_rule_id": finding["elevation_rule_id"],
                "evidence": finding["evidence"],
            })
            advisory_notes.append(f"out_of_scope:{finding['id']}")
            continue

        if finding["severity"] in {"blocker", "error", "fail"}:
            blocker_findings.append({
                "id": finding["id"],
                "severity": "blocker",
                "classification": "hard_blocker",
                "message": finding["message"],
                "elevation_rule_id": finding["elevation_rule_id"],
                "evidence": finding["evidence"],
            })
            continue

        if finding["elevation_rule_id"] and finding["evidence"]:
            blocker_findings.append({
                "id": finding["id"],
                "severity": "blocker",
                "classification": "elevated_warn",
                "message": finding["message"],
                "elevation_rule_id": finding["elevation_rule_id"],
                "evidence": finding["evidence"],
            })
            continue

        if finding["elevation_rule_id"] and not finding["evidence"]:
            advisory_findings.append({
                "id": finding["id"],
                "severity": "warn",
                "classification": "invalid_elevation_missing_evidence",
                "message": finding["message"],
                "elevation_rule_id": finding["elevation_rule_id"],
                "evidence": finding["evidence"],
            })
            advisory_notes.append(f"invalid_elevation:{finding['id']}")
            continue

        advisory_findings.append({
            "id": finding["id"],
            "severity": "warn",
            "classification": "advisory_warn",
            "message": finding["message"],
            "elevation_rule_id": finding["elevation_rule_id"],
            "evidence": finding["evidence"],
        })
        advisory_notes.append(f"advisory:{finding['id']}")

    governance_result = "pass"
    if acceptance_check == "fail" or blocker_findings:
        governance_result = "fail"

    resolved_task_id = task_id_override if task_id_override is not None else int(input_payload.get("task_id", 58))
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "task_id": resolved_task_id,
        "sample": "input-json",
        "semantic_policy_mode": "strict",
        "gate_precedence": "acceptance_first",
        "platform": "windows",
        "run_id": "task58-sample-run",
        "manual_edit_required": False,
        "command": command,
        "acceptance_check": acceptance_check,
        "governance_result": governance_result,
        "blocker_findings": blocker_findings,
        "advisory_findings": advisory_findings,
        "advisory_notes": advisory_notes,
        "policy_scope": effective_scope,
        "evidence_refs": {
            "acceptance_check_summary": "logs/ci/<date>/sc-acceptance-check-task-<id>/summary.json",
            "llm_review_summary": "logs/ci/<date>/sc-llm-review-task-<id>/summary.json",
        },
        "evidence_summaries": {
            "acceptance_check": {
                "status": acceptance_check,
                "task_id": resolved_task_id,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "finding_count": len(normalized_findings),
            },
            "llm_review": {
                "status": "ok",
                "task_id": resolved_task_id,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "summary_count": len(blocker_findings) + len(advisory_findings),
            },
        },
    }
    if context_payload:
        payload["task_context"] = context_payload
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Task58 semantic governance sample artifact.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--sample",
        choices=[
            "pass",
            "advisory-warning",
            "acceptance-fail",
            "elevated-blocker",
            "elevated-missing-evidence",
        ],
    )
    input_group.add_argument("--input-json", help="Input JSON path for input-driven evaluation mode.")
    parser.add_argument("--task-id", type=int, help="Optional task id used to load task context for policy scope.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    args = parser.parse_args()

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _repo_root() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = "py -3 scripts/python/task58_semantic_governance_sample.py " + " ".join(sys.argv[1:])
    if args.sample:
        payload = _build_payload(args.sample)
        payload["command"] = command
    else:
        input_path = Path(args.input_json)
        if not input_path.is_absolute():
            input_path = _repo_root() / input_path
        input_payload = _read_json(input_path)
        task_context = _load_task_context(args.task_id) if args.task_id is not None else None
        payload = _build_payload_from_input(
            input_payload=input_payload,
            task_context=task_context,
            command=command,
            task_id_override=args.task_id,
        )

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mode = args.sample if args.sample else "input-json"
    print(f"TASK58_SEMANTIC_GOVERNANCE_SAMPLE status=ok mode={mode} out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
