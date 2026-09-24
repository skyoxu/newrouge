#!/usr/bin/env python3
"""Validate reviewed milestone change plans and build task-local Chapter 5/6 handoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

CHANGE_PLAN_SCHEMA = "newrouge.milestone-change-plan.v1"
HANDOFF_SCHEMA = "newrouge.milestone-task-handoff.v1"
ACTIONS = {"new", "extend", "reuse", "replace", "retire", "unresolved"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _task_index(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for rel in (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"):
        path = root / rel
        if not path.is_file():
            continue
        payload = _load(path)
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("id", "taskmaster_id"):
                if row.get(key) is not None and str(row.get(key)).strip():
                    result[str(row.get(key)).strip()] = row
    return result


def _task_ids(root: Path) -> set[str]:
    return set(_task_index(root))


def _task_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"):
        path = root / rel
        if path.is_file():
            payload = _load(path)
            if isinstance(payload, list):
                rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def _canonical_task_id(index: dict[str, dict[str, Any]], value: Any) -> str:
    row = index.get(str(value))
    return str(row.get("taskmaster_id") or row.get("id")) if row else str(value)


def _required_old_regressions(manifest_path: Path | None, impacted_tasks: set[str], index: dict[str, dict[str, Any]]) -> set[str]:
    required: set[str] = set()
    if manifest_path is None:
        return required
    manifest = _load(manifest_path)
    if not isinstance(manifest, dict):
        return required
    for flow in manifest.get("flows", []):
        if not isinstance(flow, dict):
            continue
        flow_tasks = {_canonical_task_id(index, value) for value in (flow.get("task_ids") or [])}
        if flow_tasks & impacted_tasks:
            required.update(str(value) for value in (flow.get("test_ids") or []) if str(value).strip())
        for handoff in flow.get("handoffs") or []:
            if not isinstance(handoff, dict):
                continue
            participants = {
                _canonical_task_id(index, handoff[key])
                for key in ("producer_task", "consumer_task") if handoff.get(key) is not None
            }
            if participants & impacted_tasks:
                required.update(str(value) for value in (handoff.get("test_ids") or []) if str(value).strip())
    return required


def _active_requirements(root: Path) -> set[str]:
    path = root / "logs/ci/task-generation/semantic-requirements.v1.json"
    if not path.is_file():
        return set()
    payload = _load(path)
    return {
        str(row.get("requirement_id"))
        for row in payload.get("requirements", [])
        if isinstance(row, dict)
        and row.get("requirement_id")
        and str(row.get("status", "active")).lower() == "active"
    }


def _requirements_by_block(root: Path) -> dict[str, set[str]]:
    path = root / "logs/ci/task-generation/semantic-requirements.v1.json"
    if not path.is_file():
        return {}
    mapping: dict[str, set[str]] = {}
    for row in _load(path).get("requirements", []):
        if not isinstance(row, dict) or str(row.get("status", "active")).lower() != "active":
            continue
        for block_id in row.get("source_block_ids", []):
            mapping.setdefault(str(block_id), set()).add(str(row.get("requirement_id")))
    return mapping


def validate_change_plan(root: Path, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != CHANGE_PLAN_SCHEMA:
        errors.append("invalid_schema")
    source_identity = payload.get("source_identity")
    if not isinstance(source_identity, dict) or not str(source_identity.get("source_revision") or "").strip():
        errors.append("missing_source_identity")
    manifest_path = root / "logs/ci/task-generation/source-manifest.v1.json"
    if manifest_path.is_file() and isinstance(source_identity, dict):
        manifest = _load(manifest_path)
        if source_identity.get("source_revision") != manifest.get("source_revision"):
            errors.append("stale_source_identity")
    rows = payload.get("changes")
    if not isinstance(rows, list) or not rows:
        errors.append("missing_changes")
        return errors
    mapped_requirements = {
        str(value) for change in rows if isinstance(change, dict)
        for value in (change.get("requirement_ids") or [])
    }
    task_index = _task_index(root)
    known_tasks = set(task_index)
    task_rows = _task_rows(root)
    active_requirements = _active_requirements(root)
    requirements_by_block = _requirements_by_block(root)
    baseline_ref = str(payload.get("baseline_manifest") or "")
    baseline_path = (root / baseline_ref).resolve() if baseline_ref else None
    baseline_root = (root / "docs/testing/mvg").resolve()
    if baseline_path is not None and (not baseline_path.is_file() or baseline_path.parent != baseline_root):
        errors.append("invalid_baseline_manifest")
        baseline_path = None
    if baseline_path is None and any(baseline_root.glob("*.json")):
        errors.append("missing_baseline_manifest")
    ledger_path = root / "logs/ci/task-generation/source-blocks.v1.json"
    if ledger_path.is_file():
        ledger = _load(ledger_path)
        expected_blocks = set((ledger.get("delta") or {}).get("added", [])) | set((ledger.get("delta") or {}).get("changed", []))
        blocks = {str(block.get("block_id")): block for block in ledger.get("blocks", []) if isinstance(block, dict)}
        reviews = payload.get("source_block_reviews")
        reviewed_ids: set[str] = set()
        if expected_blocks and not isinstance(reviews, list):
            errors.append("missing_source_block_reviews")
        for review in reviews if isinstance(reviews, list) else []:
            if not isinstance(review, dict):
                errors.append("invalid_source_block_review")
                continue
            block_id = str(review.get("block_id") or "")
            if block_id in reviewed_ids or block_id not in expected_blocks:
                errors.append(f"invalid_source_block_review:{block_id}")
                continue
            reviewed_ids.add(block_id)
            if review.get("content_hash") != (blocks.get(block_id) or {}).get("content_hash"):
                errors.append(f"stale_source_block_review:{block_id}")
            disposition = review.get("disposition")
            if disposition not in {"requirement", "context"} or not str(review.get("reason") or "").strip():
                errors.append(f"unresolved_source_block_review:{block_id}")
            declared = set(map(str, review.get("requirement_ids") or []))
            grounded = requirements_by_block.get(block_id, set()) & active_requirements
            if disposition == "requirement" and (not declared or not declared <= grounded):
                errors.append(f"unmapped_source_block_review:{block_id}")
            if disposition == "requirement" and declared - mapped_requirements:
                errors.append(f"unassigned_source_block_requirements:{block_id}")
            if disposition == "context" and grounded:
                errors.append(f"source_block_review_conflicts_with_requirements:{block_id}")
            if disposition == "context" and (blocks.get(block_id) or {}).get("requirement_like_hint"):
                if not str(review.get("non_delivery_rationale") or "").strip():
                    errors.append(f"requirement_like_context_needs_review:{block_id}")
        if expected_blocks - reviewed_ids:
            errors.append("unreviewed_source_blocks:" + ",".join(sorted(expected_blocks - reviewed_ids)))
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"change_{index}:not_object")
            continue
        change_id = str(row.get("change_id") or "").strip()
        if not change_id or change_id in seen:
            errors.append(f"change_{index}:invalid_change_id")
        seen.add(change_id)
        action = str(row.get("action") or "").strip().lower()
        if action not in ACTIONS:
            errors.append(f"{change_id or index}:invalid_action")
        reason = str(row.get("reason") or "").strip()
        if not reason:
            errors.append(f"{change_id or index}:missing_reason")
        target = str(row.get("target_task_id") or "").strip()
        owner = str(row.get("owner_task_id") or "").strip()
        if action == "new":
            if not target:
                errors.append(f"{change_id}:new_missing_target_task")
        elif action != "unresolved" and target and target not in known_tasks:
            errors.append(f"{change_id}:unknown_target_task:{target}")
        if action in {"extend", "replace", "retire"} and not owner:
            errors.append(f"{change_id}:missing_owner_task")
        if owner and owner not in known_tasks and owner != target:
            errors.append(f"{change_id}:unknown_owner_task:{owner}")
        target_status = str((task_index.get(target) or {}).get("status") or "").strip().lower()
        if action in {"extend", "replace"} and target_status == "done":
            if owner == target and row.get("reopen_task") is not True:
                errors.append(f"{change_id}:done_target_requires_change_owner_or_explicit_reopen")
        requirement_ids = [str(value) for value in row.get("requirement_ids", []) if str(value).strip()]
        if active_requirements:
            stale = sorted(set(requirement_ids) - active_requirements)
            if stale:
                errors.append(f"{change_id}:inactive_requirement:{','.join(stale)}")
        impact = row.get("impact")
        if not isinstance(impact, dict):
            errors.append(f"{change_id}:missing_impact")
        else:
            impacted = {_canonical_task_id(task_index, value) for value in impact.get("tasks", [])} if isinstance(impact.get("tasks"), list) else set()
            expected_tasks = {_canonical_task_id(task_index, value) for value in (target, owner) if value}
            missing_tasks = sorted(expected_tasks - impacted)
            if missing_tasks and action != "unresolved":
                errors.append(f"{change_id}:impact_missing_tasks:{','.join(missing_tasks)}")
            old_contracts = {
                ref for task in task_rows if target and target in {str(task.get("id")), str(task.get("taskmaster_id"))}
                for ref in (task.get("contractRefs") or [])
            }
            owner_contracts = {
                ref for task in task_rows if owner and owner in {str(task.get("id")), str(task.get("taskmaster_id"))}
                for ref in (task.get("contractRefs") or [])
            }
            shared_contracts = old_contracts & owner_contracts if target != owner else set()
            declared_contracts = set(impact.get("contracts") or []) if isinstance(impact.get("contracts"), list) else set()
            missing_contracts = sorted(shared_contracts - declared_contracts)
            if missing_contracts:
                errors.append(f"{change_id}:impact_missing_shared_contracts:{','.join(missing_contracts)}")
            affected_contracts = declared_contracts | shared_contracts
            consumers = {
                _canonical_task_id(task_index, task.get("id"))
                for task in task_rows
                if set(task.get("contractRefs") or []) & affected_contracts
            }
            missing_consumers = sorted(consumers - impacted)
            if missing_consumers:
                errors.append(f"{change_id}:impact_missing_contract_consumers:{','.join(missing_consumers)}")
        verification = row.get("verification")
        if not isinstance(verification, dict):
            errors.append(f"{change_id}:missing_verification")
        elif action != "unresolved":
            has_evidence_plan = any(
                isinstance(verification.get(key), list) and verification.get(key)
                for key in ("required_regressions", "planned_tests", "manual_obligations")
            )
            if not has_evidence_plan:
                errors.append(f"{change_id}:missing_verification_plan")
            if isinstance(impact, dict) and action != "unresolved":
                required_tests = _required_old_regressions(baseline_path, impacted, task_index)
                actual_tests = set(map(str, verification.get("required_regressions") or []))
                missing_tests = sorted(required_tests - actual_tests)
                if missing_tests:
                    errors.append(f"{change_id}:missing_old_regressions:{','.join(missing_tests)}")
        if action == "unresolved" and not str(row.get("blocked_reason") or "").strip():
            errors.append(f"{change_id}:unresolved_without_block_reason")
    return errors


def build_task_handoff(
    root: Path,
    *,
    plan_path: Path,
    task_id: str,
    readiness_path: Path,
) -> dict[str, Any]:
    plan = _load(plan_path)
    if not isinstance(plan, dict):
        raise ValueError("change plan must be an object")
    errors = validate_change_plan(root, plan)
    if errors:
        raise ValueError("invalid change plan: " + "; ".join(errors))
    readiness = _load(readiness_path)
    if not isinstance(readiness, dict) or readiness.get("schema_version") != "newrouge.chapter5-readiness.v1":
        raise ValueError("invalid Chapter 5 readiness document")
    if str(readiness.get("task_id") or "") != str(task_id):
        raise ValueError("Chapter 5 readiness task mismatch")
    if not bool(readiness.get("closure_allowed")):
        raise ValueError("Chapter 5 readiness is not closable")
    if (root / "logs/ci/task-generation/source-manifest.v1.json").is_file():
        from chapter5_semantic_reconciliation import load_task_readiness
        ready, current, reason = load_task_readiness(root, task_id)
        if not ready or current != readiness:
            raise ValueError("Chapter 5 readiness is stale: " + reason)
    changes = [
        row for row in plan.get("changes", [])
        if isinstance(row, dict)
        and str(row.get("owner_task_id") or row.get("target_task_id") or "") == str(task_id)
    ]
    if not changes:
        raise ValueError("change plan has no entry owned by this task")
    unresolved = [row for row in changes if str(row.get("action") or "").lower() == "unresolved"]
    if unresolved:
        raise ValueError("task-local change plan remains unresolved")
    if str(readiness.get("task_id") or "") != str(task_id) or not readiness.get("input_fingerprint"):
        raise ValueError("Chapter 5 readiness identity is incomplete")
    return {
        "schema_version": HANDOFF_SCHEMA,
        "task_id": str(task_id),
        "source_identity": dict(plan.get("source_identity") or {}),
        "change_plan_path": plan_path.relative_to(root).as_posix(),
        "change_plan_sha256": _file_sha(plan_path),
        "chapter5_readiness_path": readiness_path.relative_to(root).as_posix(),
        "chapter5_readiness_sha256": _file_sha(readiness_path),
        "chapter5_input_fingerprint": readiness.get("input_fingerprint"),
        "changes": changes,
        "required_regressions": sorted({
            str(test)
            for row in changes
            for test in (row.get("verification") or {}).get("required_regressions", [])
            if str(test).strip()
        }),
        "planned_tests": sorted({
            str(test)
            for row in changes
            for test in (row.get("verification") or {}).get("planned_tests", [])
            if str(test).strip()
        }),
        "manual_obligations": sorted({
            str(test)
            for row in changes
            for test in (row.get("verification") or {}).get("manual_obligations", [])
            if str(test).strip()
        }),
        "baseline_delta": [
            row.get("baseline_delta")
            for row in changes
            if isinstance(row.get("baseline_delta"), dict)
        ],
    }


def validate_task_handoff(root: Path, path: Path, task_id: str) -> tuple[bool, str, dict[str, Any]]:
    if not path.is_file():
        return False, "milestone_handoff_missing", {}
    try:
        payload = _load(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, "milestone_handoff_invalid_json", {}
    if not isinstance(payload, dict) or payload.get("schema_version") != HANDOFF_SCHEMA:
        return False, "milestone_handoff_invalid_schema", {}
    if str(payload.get("task_id") or "") != str(task_id):
        return False, "milestone_handoff_task_mismatch", {}
    for path_key, sha_key in (
        ("change_plan_path", "change_plan_sha256"),
        ("chapter5_readiness_path", "chapter5_readiness_sha256"),
    ):
        rel = str(payload.get(path_key) or "").strip()
        if not rel:
            return False, f"milestone_handoff_missing_{path_key}", {}
        target = (root / rel).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return False, "milestone_handoff_path_escape", {}
        if not target.is_file() or _file_sha(target) != str(payload.get(sha_key) or ""):
            return False, f"milestone_handoff_stale_{path_key}", {}
    plan = _load(root / str(payload["change_plan_path"]))
    readiness = _load(root / str(payload["chapter5_readiness_path"]))
    if not isinstance(plan, dict) or validate_change_plan(root, plan):
        return False, "milestone_handoff_invalid_change_plan", {}
    if not isinstance(readiness, dict) or readiness.get("schema_version") != "newrouge.chapter5-readiness.v1" or str(readiness.get("task_id") or "") != str(task_id):
        return False, "milestone_handoff_invalid_readiness", {}
    if not bool(readiness.get("closure_allowed")):
        return False, "milestone_handoff_readiness_not_closable", {}
    if readiness.get("input_fingerprint") != payload.get("chapter5_input_fingerprint"):
        return False, "milestone_handoff_readiness_fingerprint_drift", {}
    try:
        expected = build_task_handoff(
            root,
            plan_path=root / str(payload["change_plan_path"]),
            task_id=task_id,
            readiness_path=root / str(payload["chapter5_readiness_path"]),
        )
    except (ValueError, OSError, KeyError, TypeError):
        return False, "milestone_handoff_invalid_projection", {}
    if payload != expected:
        return False, "milestone_handoff_projection_drift", {}
    return True, "ok", payload


def validate_milestone_regressions(root: Path, handoff: dict[str, Any], summary_path: Path | None) -> tuple[bool, str]:
    required = set(map(str, handoff.get("required_regressions") or []))
    if not required:
        return True, "ok"
    if summary_path is None or not summary_path.is_file():
        return False, "milestone_regression_evidence_missing"
    try:
        summary_path.resolve().relative_to((root / "logs/ci/mvg-acceptance").resolve())
        if summary_path.name != "summary.json":
            raise ValueError("not a MVG run summary")
        evidence = _load(summary_path)
        manifest_ref = str(evidence.get("manifest") or "")
        manifest_path = (root / manifest_ref).resolve()
        manifest_path.relative_to(root.resolve())
        manifest = _load(manifest_path)
    except (OSError, ValueError, KeyError, AttributeError, json.JSONDecodeError):
        return False, "milestone_regression_evidence_invalid"
    if (
        not manifest_ref.startswith("docs/testing/mvg/")
        or evidence.get("schema_version") != "newrouge.mvg-acceptance.v1"
        or evidence.get("mode") != "run"
        or evidence.get("status") != "passed"
        or evidence.get("runtime_verified") is not True
        or evidence.get("workspace_dirty")
        or evidence.get("manifest_sha256") != _file_sha(manifest_path)
    ):
        return False, "milestone_regression_evidence_stale_or_unverified"
    try:
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, "milestone_regression_revision_unavailable"
    if evidence.get("source_revision") != revision:
        return False, "milestone_regression_revision_drift"
    if dirty:
        return False, "milestone_regression_workspace_dirty"
    tests = {str(item.get("id")) for item in manifest.get("tests", []) if isinstance(item, dict)}
    passed = {str(item.get("id")) for item in evidence.get("steps", []) if isinstance(item, dict) and item.get("status") == "passed"}
    if not required <= tests & passed:
        return False, "milestone_required_regressions_not_passed"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--change-plan", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    plan = root / args.change_plan
    readiness = root / args.readiness
    try:
        handoff = build_task_handoff(root, plan_path=plan, task_id=args.task_id, readiness_path=readiness)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MILESTONE_HANDOFF status=blocked reason={exc}")
        return 2
    out = root / args.out
    _write(out, handoff)
    print(f"MILESTONE_HANDOFF status=ok task={args.task_id} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
