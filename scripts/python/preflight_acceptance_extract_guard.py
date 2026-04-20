#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic preflight guard before workflow 5.1 obligation extraction."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


REFS_RE = re.compile(r"\bRefs:\s*(.+)$")
REF_SPLIT_RE = re.compile(r"[,;\s]+")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def today_str() -> str:
    return dt.date.today().isoformat()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_path(value: object) -> str:
    return str(value or "").strip().replace("\\", "/")


def _task_files(root: Path) -> tuple[Path, Path, Path]:
    task_dir = root / ".taskmaster" / "tasks"
    return task_dir / "tasks.json", task_dir / "tasks_back.json", task_dir / "tasks_gameplay.json"


def _load_master_task(root: Path, task_id: int) -> dict[str, Any] | None:
    tasks_json, _, _ = _task_files(root)
    if not tasks_json.exists():
        return None
    payload = _load_json(tasks_json)
    tasks = []
    if isinstance(payload, dict) and isinstance(payload.get("master"), dict):
        tasks = payload["master"].get("tasks") or []
    elif isinstance(payload, dict):
        tasks = payload.get("tasks") or []
    if not isinstance(tasks, list):
        return None
    for task in tasks:
        if isinstance(task, dict) and int(task.get("id") or 0) == task_id:
            return task
    return None


def _load_view_tasks(root: Path, task_id: int) -> list[tuple[str, dict[str, Any]]]:
    _, back_path, gameplay_path = _task_files(root)
    out: list[tuple[str, dict[str, Any]]] = []
    for view_name, path in (("back", back_path), ("gameplay", gameplay_path)):
        if not path.exists():
            continue
        payload = _load_json(path)
        if not isinstance(payload, list):
            continue
        for task in payload:
            if isinstance(task, dict) and int(task.get("taskmaster_id") or 0) == task_id:
                out.append((view_name, task))
    return out


def _extract_refs(acceptance: str) -> list[str]:
    match = REFS_RE.search(str(acceptance or ""))
    if not match:
        return []
    refs_raw = match.group(1).strip()
    refs: list[str] = []
    for token in REF_SPLIT_RE.split(refs_raw):
        normalized = _normalize_path(token.strip().strip("`").strip())
        if not normalized:
            continue
        refs.append(normalized)
    return refs


def _is_garbled_question_marks(text: str) -> bool:
    value = str(text or "")
    if "??" in value:
        return True
    # A single leading question mark usually means mojibake replacement in these task files.
    return bool(re.search(r"(^|\s)\?[^\w]", value))


def _issue(issue_id: str, *, view: str = "", detail: str = "", acceptance_index: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": issue_id}
    if view:
        payload["view"] = view
    if detail:
        payload["detail"] = detail
    if acceptance_index is not None:
        payload["acceptance_index"] = acceptance_index
    return payload


def evaluate_task(*, root: Path, task_id: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    master = _load_master_task(root, task_id)
    if master is None:
        issues.append(_issue("master_task_missing", detail=f"T{task_id} not found in tasks.json"))

    view_tasks = _load_view_tasks(root, task_id)
    if not view_tasks:
        issues.append(_issue("view_task_missing", detail=f"T{task_id} missing from task views"))

    acceptance_item_counts: dict[str, int] = {}
    views_present: list[str] = []

    for view_name, task in view_tasks:
        views_present.append(view_name)
        acceptance_items = task.get("acceptance")
        if not isinstance(acceptance_items, list) or not acceptance_items:
            issues.append(_issue("acceptance_missing", view=view_name))
            acceptance_item_counts[view_name] = 0
            continue

        acceptance_item_counts[view_name] = len(acceptance_items)
        test_refs = {_normalize_path(item) for item in (task.get("test_refs") or []) if _normalize_path(item)}

        for index, acceptance in enumerate(acceptance_items, start=1):
            acceptance_text = str(acceptance or "")
            if _is_garbled_question_marks(acceptance_text):
                issues.append(_issue("acceptance_garbled_question_marks", view=view_name, acceptance_index=index))
            refs = _extract_refs(acceptance_text)
            if not refs:
                issues.append(_issue("acceptance_missing_refs", view=view_name, acceptance_index=index))
                continue
            for ref in refs:
                if ref not in test_refs:
                    issues.append(
                        _issue(
                            "acceptance_ref_missing_from_test_refs",
                            view=view_name,
                            acceptance_index=index,
                            detail=ref,
                        )
                    )

    issue_ids = sorted({str(issue["id"]) for issue in issues})
    status = "ok" if not issues else "fail"
    return {
        "cmd": "preflight_acceptance_extract_guard",
        "status": status,
        "task_id": task_id,
        "issue_count": len(issues),
        "issue_ids": issue_ids,
        "issues": issues,
        "acceptance_item_counts": acceptance_item_counts,
        "views_present": sorted(set(views_present)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic acceptance preflight before obligations extraction.")
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    root = repo_root()
    out_dir = Path(args.out_dir) if str(args.out_dir).strip() else root / "logs" / "ci" / today_str() / f"acceptance-extract-preflight-task-{args.task_id:04d}"
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    report = evaluate_task(root=root, task_id=int(args.task_id))
    _write_json(out_dir / "summary.json", report)
    print(f"SC_ACCEPTANCE_EXTRACT_PREFLIGHT status={report['status']} issues={report['issue_count']} out={out_dir}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
