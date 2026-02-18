#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update tasks_back.json / tasks_gameplay.json test_refs using acceptance "Refs:".

This is a deterministic sync helper:
  - Parse each acceptance item for "Refs:" paths.
  - Keep only test-file refs in test_refs (.cs/.gd under test roots).
  - Move logs/docs evidence refs into evidence_refs (per view task object).

Why:
  - validate_acceptance_refs.py can enforce that all acceptance refs are included in test_refs.
  - This script reduces manual bookkeeping.

Usage (Windows):
  py -3 scripts/python/update_task_test_refs_from_acceptance_refs.py --task-id 11 --write
  py -3 scripts/python/update_task_test_refs_from_acceptance_refs.py --task-id 11 --mode merge --write
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REFS_RE = re.compile(r"\bRefs\s*:\s*(.+)$", flags=re.IGNORECASE)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def find_view_task(view: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    tid = int(str(task_id))
    for t in view:
        if not isinstance(t, dict):
            continue
        if t.get("taskmaster_id") == tid:
            return t
    return None


def _split_refs_blob(blob: str) -> list[str]:
    s = str(blob or "").strip()
    s = s.replace("`", "")
    s = s.replace(",", " ")
    s = s.replace(";", " ")
    return [p.strip().replace("\\", "/") for p in s.split() if p.strip()]


def _extract_refs_from_acceptance(acceptance: Any) -> list[str]:
    if not isinstance(acceptance, list):
        return []
    refs: list[str] = []
    for item in acceptance:
        s = str(item or "").strip()
        m = REFS_RE.search(s)
        if not m:
            continue
        refs.extend(_split_refs_blob(m.group(1)))
    # De-dup preserving order.
    seen = set()
    out = []
    for r in refs:
        if not r:
            continue
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


def _is_allowed_test_path(p: str) -> bool:
    s = str(p or "").strip().replace("\\", "/")
    if not s:
        return False
    if not (s.endswith(".cs") or s.endswith(".gd")):
        return False
    return s.startswith("Game.Core.Tests/") or s.startswith("Tests.Godot/tests/") or s.startswith("Tests/")


def _is_evidence_path(p: str) -> bool:
    s = str(p or "").strip().replace("\\", "/")
    return s.startswith("logs/") or s.startswith("docs/")


def _ensure_list_field(obj: dict[str, Any], key: str) -> list[str]:
    v = obj.get(key)
    if v is None:
        obj[key] = []
        return obj[key]
    if isinstance(v, list):
        obj[key] = [str(x).replace("\\", "/") for x in v if str(x).strip()]
        return obj[key]
    raise ValueError(f"{key} must be a list")


def _add_unique(dst: list[str], items: list[str]) -> bool:
    before = list(dst)
    seen = set(dst)
    for it in items:
        it = str(it).strip().replace("\\", "/")
        if not it:
            continue
        if it in seen:
            continue
        dst.append(it)
        seen.add(it)
    return dst != before


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync test_refs from acceptance Refs: for one task.")
    ap.add_argument("--task-id", required=True, help="Task id (e.g. 11).")
    ap.add_argument("--mode", choices=["replace", "merge"], default="replace", help="Sync mode: replace (default) or merge.")
    ap.add_argument("--write", action="store_true", help="Write files in-place. Without this flag, runs as dry-run.")
    args = ap.parse_args()

    root = repo_root()
    back_path = root / ".taskmaster" / "tasks" / "tasks_back.json"
    gameplay_path = root / ".taskmaster" / "tasks" / "tasks_gameplay.json"

    back = load_json(back_path)
    gameplay = load_json(gameplay_path)
    if not isinstance(back, list) or not isinstance(gameplay, list):
        raise ValueError("tasks_back.json and tasks_gameplay.json must be JSON arrays")

    task_id = str(args.task_id).strip()
    back_task = find_view_task(back, task_id)
    gameplay_task = find_view_task(gameplay, task_id)
    if back_task is None and gameplay_task is None:
        raise ValueError(f"taskmaster_id not found in either view: {task_id}")

    # Union refs across existing views to keep both sides consistent when both exist.
    refs: list[str] = []
    if back_task is not None:
        for r in _extract_refs_from_acceptance(back_task.get("acceptance")):
            if r not in refs:
                refs.append(r)
    if gameplay_task is not None:
        for r in _extract_refs_from_acceptance(gameplay_task.get("acceptance")):
            if r not in refs:
                refs.append(r)

    test_refs_from_acceptance = [r for r in refs if _is_allowed_test_path(r)]
    evidence_refs_from_acceptance = [r for r in refs if _is_evidence_path(r)]

    changed_back = False
    changed_game = False

    if back_task is not None:
        back_refs = _ensure_list_field(back_task, "test_refs")
        back_evidence = _ensure_list_field(back_task, "evidence_refs")
        if args.mode == "replace":
            before = list(back_refs)
            back_task["test_refs"] = list(test_refs_from_acceptance)
            changed_back = before != back_task["test_refs"]
        else:
            changed_back = _add_unique(back_refs, test_refs_from_acceptance)
        changed_back = _add_unique(back_evidence, evidence_refs_from_acceptance) or changed_back

    if gameplay_task is not None:
        game_refs = _ensure_list_field(gameplay_task, "test_refs")
        game_evidence = _ensure_list_field(gameplay_task, "evidence_refs")
        if args.mode == "replace":
            before = list(game_refs)
            gameplay_task["test_refs"] = list(test_refs_from_acceptance)
            changed_game = before != gameplay_task["test_refs"]
        else:
            changed_game = _add_unique(game_refs, test_refs_from_acceptance)
        changed_game = _add_unique(game_evidence, evidence_refs_from_acceptance) or changed_game

    print(
        f"UPDATE_TEST_REFS_FROM_ACCEPTANCE task_id={task_id} mode={args.mode} refs={len(refs)} "
        f"test_refs={len(test_refs_from_acceptance)} evidence_refs={len(evidence_refs_from_acceptance)} "
        f"changed_back={changed_back} changed_game={changed_game} write={bool(args.write)}"
    )
    if not args.write:
        return 0

    write_json(back_path, back)
    write_json(gameplay_path, gameplay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

