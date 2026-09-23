#!/usr/bin/env python3
"""Validate reviewed milestone change plans and build task-local Chapter 5/6 handoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
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


def validate_change_plan(root: Path, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != CHANGE_PLAN_SCHEMA:
        errors.append("invalid_schema")
    source_identity = payload.get("source_identity")
    if not isinstance(source_identity, dict) or not str(source_identity.get("source_revision") or "").strip():
        errors.append("missing_source_identity")
    rows = payload.get("changes")
    if not isinstance(rows, list) or not rows:
        errors.append("missing_changes")
        return errors
    task_index = _task_index(root)
    known_tasks = set(task_index)
    active_requirements = _active_requirements(root)
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
    readiness = _load(root / str(payload["chapter5_readiness_path"]))
    if not bool(readiness.get("closure_allowed")):
        return False, "milestone_handoff_readiness_not_closable", {}
    if readiness.get("input_fingerprint") != payload.get("chapter5_input_fingerprint"):
        return False, "milestone_handoff_readiness_fingerprint_drift", {}
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        return False, "milestone_handoff_missing_changes", {}
    if any(str(row.get("action") or "").lower() == "unresolved" for row in changes if isinstance(row, dict)):
        return False, "milestone_handoff_unresolved", {}
    return True, "ok", payload


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
