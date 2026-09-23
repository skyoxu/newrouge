#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Task Master compatible .taskmaster/tasks/tasks.json from NG/GM task files.

This script:
- Reads .taskmaster/tasks/tasks_back.json and tasks_gameplay.json (SSoT for NG/GM)
  by default, or任意指定的任务文件（见参数）。
- 根据给定的任务 ID 集合（或默认的 T2 根任务）计算依赖闭包，并将这些任务映射到
  Task Master schema 下指定的 Tag（默认 master），采用数字 ID 与数字依赖。
- 追加写入 .taskmaster/tasks/tasks.json（不会覆盖其他 Tag），并在源任务文件上标记：
  - taskmaster_id: 数字 ID（Task Master 使用）
  - taskmaster_exported: 是否已映射到 Task Master

Constraints are enforced by this script and the generated Task Master schema:
- Root object must be { "<tag>": { "tasks": [...] }, ... }
- id: number
- dependencies: number[]
- status: one of "pending" | "in-progress" | "done" | "deferred" | "cancelled" | "blocked"
- priority: "high" | "medium" | "low"
- testStrategy: string

Usage (from repo root on Windows):

    # 从指定任务文件中选择给定 ID（及其依赖）映射到指定 Tag（自动追加）
    py -3 scripts/python/build_taskmaster_tasks.py `
        --tasks-file .taskmaster/tasks/tasks_back.json `
        --ids NG-0001 NG-0020 `
        --tag master

    # 或使用 JSON 文件提供 ID 数组：
    # ids.json 内容示例：["NG-0001","NG-0020","GM-0101"]
    py -3 scripts/python/build_taskmaster_tasks.py `
        --tasks-file .taskmaster/tasks/tasks_back.json `
        --ids-file .taskmaster/tasks/ids.json `
        --tag feature-t2
"""

from __future__ import annotations

import json
import argparse
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set


ROOT = Path(__file__).resolve().parents[2]

TASKS_DIR = ROOT / ".taskmaster" / "tasks"
TASKS_BACK_FILE = TASKS_DIR / "tasks_back.json"
TASKS_GAMEPLAY_FILE = TASKS_DIR / "tasks_gameplay.json"
TASKS_LONGTERM_FILE = TASKS_DIR / "tasks_longterm.json"
TASKMASTER_TASKS_FILE = TASKS_DIR / "tasks.json"

# Seed tasks considered as "T2 scene" roots; their dependency closure will be exported
# when no explicit --ids/--ids-file are provided.
T2_ROOT_IDS: Set[str] = {
    "NG-0020",
    "NG-0021",
    "GM-0101",
    "GM-0103",
}


def load_tasks(task_file: Path) -> List[Dict]:
    if not task_file.exists():
        return []
    data = json.loads(task_file.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "tasks" in data and isinstance(data["tasks"], list):
        return data["tasks"]
    return []


def _merge_view_task(existing: Dict[str, Any], incoming: Dict[str, Any], tid: str, *, numeric_group: bool = False) -> Dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "id":
            continue
        if key in merged and merged[key] != value:
            if numeric_group and key in {"story_id", "description", "owner"}:
                # Distinct source tasks may share a numeric Taskmaster task. Keep
                # each source's identity in the view; do not silently choose one.
                merged[key] = " / ".join(dict.fromkeys([str(merged[key]), str(value)]))
                continue
            if numeric_group and key in {"depends_on", "dependencies"}:
                merged[key] = list(dict.fromkeys([*merged[key], *value]))
                continue
            if numeric_group and key == "status":
                # A shared master task cannot be done while either source view is pending.
                merged[key] = next((state for state in ("blocked", "in-progress", "pending", "deferred", "cancelled") if state in {str(merged[key]), str(value)}), "done")
                continue
            if key in {"taskmaster_id", "status", "depends_on", "dependencies"}:
                raise ValueError(f"conflicting cross-view field for {tid}: {key}")
            if isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = list(dict.fromkeys([*merged[key], *value]))
                continue
            if value in ("", None, [], {}):
                continue
            if merged[key] in ("", None, [], {}):
                merged[key] = value
                continue
            raise ValueError(f"conflicting cross-view field for {tid}: {key}")
        else:
            merged[key] = value
    return merged


def build_all_tasks(task_files: List[Path]) -> Dict[str, Dict]:
    """Load tasks from views and merge shared string ids without last-writer-wins."""
    all_tasks: Dict[str, Dict] = {}
    for path in task_files:
        tasks = load_tasks(path)
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue
            key = str(tid)
            if key in all_tasks:
                all_tasks[key] = _merge_view_task(all_tasks[key], t, key)
            else:
                all_tasks[key] = dict(t)
    return all_tasks


def get_dependencies(t: Dict) -> List[str]:
    deps = t.get("depends_on") or t.get("dependencies") or []
    return [d for d in deps if isinstance(d, str) and d]


def compute_closure(all_tasks: Dict[str, Dict], root_ids: Set[str]) -> Set[str]:
    """Compute dependency closure starting from root_ids."""
    closure: Set[str] = set()
    stack: List[str] = list(root_ids)
    while stack:
        tid = stack.pop()
        if tid in closure:
            continue
        closure.add(tid)
        t = all_tasks.get(tid)
        if not t:
            continue
        for dep in get_dependencies(t):
            if dep not in closure:
                stack.append(dep)
    return closure


def map_status(status: str | None) -> str:
    if not status:
        return "pending"
    s = status.strip().lower()
    if s in {"pending", "in-progress", "done", "deferred", "cancelled", "blocked"}:
        return s
    if s in {"in_progress", "inprogress"}:
        return "in-progress"
    if s in {"completed", "complete"}:
        return "done"
    return "pending"


def map_priority(priority: str | None) -> str:
    if not priority:
        return "medium"
    p = priority.strip().upper()
    if p in {"HIGH", "MEDIUM", "LOW"}:
        return p.lower()
    if p in {"P0", "P1"}:
        return "high"
    if p == "P2":
        return "medium"
    if p in {"P3", "P4"}:
        return "low"
    return "medium"


def merge_master_fields(existing_task: Dict[str, Any], generated_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update only view-owned Taskmaster fields while preserving master-native extensions."""
    merged = dict(existing_task)
    merged.update(generated_fields)
    return merged

def merge_numeric_view_group(rows: List[Dict[str, Any]], num_id: int) -> Dict[str, Any]:
    """Merge distinct view rows that intentionally map to one Taskmaster id."""
    if not rows:
        raise ValueError(f"Taskmaster {num_id} has no source rows")
    merged = dict(rows[0])
    source_ids = [str(merged.get("id") or "")]
    for row in rows[1:]:
        source_ids.append(str(row.get("id") or ""))
        merged = _merge_view_task(merged, row, f"taskmaster:{num_id}", numeric_group=True)
    merged["source_view_ids"] = [value for value in source_ids if value]
    merged["taskmaster_id"] = num_id
    return merged


def build_taskmaster_tasks(args: argparse.Namespace) -> None:
    # 1) 解析任务文件列表（源 SSoT）
    if not args.tasks_files:
        print("Error: --tasks-file is required (one or more).")
        raise SystemExit(1)

    task_files: List[Path] = []
    for p_str in args.tasks_files:
        p = Path(p_str)
        if not p.is_absolute():
            p = ROOT / p
        task_files.append(p)

    all_tasks = build_all_tasks(task_files)
    if not all_tasks:
        print("No tasks loaded from task files; aborting.")
        return

    # 2) 解析根任务 ID 集合
    root_ids: Set[str] = set()
    if args.ids:
        root_ids.update(args.ids)
    if args.ids_file:
        ids_path = Path(args.ids_file)
        if not ids_path.is_absolute():
            ids_path = ROOT / ids_path
        try:
            id_data = json.loads(ids_path.read_text(encoding="utf-8"))
            if isinstance(id_data, list):
                for x in id_data:
                    if isinstance(x, str) and x:
                        root_ids.add(x)
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to read ids-file {ids_path}: {exc}")
    if not root_ids:
        if args.allow_legacy_t2_default:
            root_ids = set(T2_ROOT_IDS)
        else:
            print("Error: explicit --ids or --ids-file is required for incremental export.")
            raise SystemExit(1)

    # 3) 计算依赖闭包
    t2_ids = compute_closure(all_tasks, root_ids)
    if not t2_ids:
        print("Closure is empty; nothing to export.")
        return

    # Topologically sort T2 ids so that:
    # - Dependencies appear before dependents.
    # - NG-*/backbone tasks自然排在前面，GM-*/玩法任务排在其后。
    visited: Dict[str, bool] = {}
    ordered: List[str] = []

    def visit(tid: str) -> None:
        if tid in visited:
            return
        visited[tid] = True
        t = all_tasks.get(tid)
        if t:
            for dep in sorted(get_dependencies(t)):
                if dep in t2_ids:
                    visit(dep)
        ordered.append(tid)

    for tid in sorted(t2_ids):
        visit(tid)

    sorted_ids = ordered
    # 4) 载入现有 Task Master tasks.json（若存在），并准备目标 Tag
    root_obj: Dict[str, Dict]
    if TASKMASTER_TASKS_FILE.exists():
        try:
            root_obj = json.loads(TASKMASTER_TASKS_FILE.read_text(encoding="utf-8"))
            if not isinstance(root_obj, dict):
                raise ValueError("existing tasks.json is not an object")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"cannot load existing tasks.json: {exc}") from exc
    else:
        root_obj = {}

    tag = args.tag or "master"
    tag_obj = root_obj.get(tag)
    if not isinstance(tag_obj, dict):
        tag_obj = {}
        root_obj[tag] = tag_obj
    tag_tasks = tag_obj.get("tasks")
    if not isinstance(tag_tasks, list):
        tag_tasks = []
        tag_obj["tasks"] = tag_tasks

    # Collect already used numeric ids across all tags to avoid collisions.
    used_ids: Set[int] = set()
    for v in root_obj.values():
        if not isinstance(v, dict):
            continue
        tasks_list = v.get("tasks")
        if not isinstance(tasks_list, list):
            continue
        for t in tasks_list:
            tid_val = t.get("id")
            if isinstance(tid_val, int):
                used_ids.add(tid_val)

    # 5) 为字符串 ID 分配稳定的数字 ID（优先复用 taskmaster_id）
    id_map: Dict[str, int] = {}
    next_id = (max(used_ids) if used_ids else 0) + 1

    for tid in sorted_ids:
        src = all_tasks.get(tid)
        if not src:
            continue
        existing = src.get("taskmaster_id")
        num: int | None = None
        if isinstance(existing, int) and existing > 0:
            num = existing
            if num not in used_ids:
                used_ids.add(num)
        if num is None:
            # 分配新的全局唯一数字 ID
            while next_id in used_ids:
                next_id += 1
            num = next_id
            used_ids.add(num)
            next_id += 1
        id_map[tid] = num

    print("Tasks to export (string id -> numeric id):")
    for tid in sorted_ids:
        num = id_map.get(tid)
        print(f"  {tid} -> {num}")

    rows_by_numeric: Dict[int, List[Dict[str, Any]]] = {}
    tids_by_numeric: Dict[int, List[str]] = {}
    for tid in sorted_ids:
        src = all_tasks.get(tid)
        num = id_map.get(tid)
        if not src or num is None:
            continue
        rows_by_numeric.setdefault(num, []).append(src)
        tids_by_numeric.setdefault(num, []).append(tid)
    export_units: List[tuple[str, Dict[str, Any], int]] = []
    emitted_numeric: Set[int] = set()
    for tid in sorted_ids:
        num = id_map.get(tid)
        if num is None or num in emitted_numeric:
            continue
        emitted_numeric.add(num)
        merged_source = merge_numeric_view_group(rows_by_numeric[num], num)
        export_units.append((tid, merged_source, num))

    # 6) 构建/更新目标 Tag 下的 Task Master 任务列表
    existing_by_id: Dict[int, int] = {
        t["id"]: idx
        for idx, t in enumerate(tag_tasks)
        if isinstance(t, dict) and isinstance(t.get("id"), int)
    }

    for tid, src, num_id in export_units:
        title = src.get("title") or tid
        description = src.get("description") or ""

        # Build details as a markdown-like blob with meta info.
        details_parts: List[str] = []
        story_id = src.get("story_id")
        if story_id:
            details_parts.append(f"Story: {story_id}")
        for key, label in (
            ("adr_refs", "ADR Refs"),
            ("chapter_refs", "Chapters"),
            ("overlay_refs", "Overlays"),
            ("test_refs", "Test Refs"),
            ("acceptance", "Acceptance"),
            ("test_strategy", "Test Strategy"),
            ("labels", "Labels"),
            ("owner", "Owner"),
            ("layer", "Layer"),
        ):
            val = src.get(key)
            if not val:
                continue
            if isinstance(val, list):
                text = "; ".join(str(v) for v in val)
            else:
                text = str(val)
            details_parts.append(f"{label}: {text}")
        details = "\n".join(details_parts) if details_parts else ""

        # Map test_strategy (list) to single string testStrategy if present.
        ts = src.get("test_strategy")
        if isinstance(ts, list):
            test_strategy_str = "\n".join(str(x) for x in ts)
        elif isinstance(ts, str):
            test_strategy_str = ts
        else:
            test_strategy_str = ""

        # Map dependencies to numeric ids (only within closure subset).
        dep_ids: List[int] = []
        for dep in get_dependencies(src):
            num_dep = id_map.get(dep)
            if num_dep is not None and num_dep != num_id and num_dep not in dep_ids:
                dep_ids.append(num_dep)

        generated_fields: Dict[str, Any] = {
            "id": num_id,
            "title": title,
            "description": description,
            "status": map_status(src.get("status")),
            "priority": map_priority(src.get("priority")),
            "dependencies": dep_ids,
        }
        if details:
            generated_fields["details"] = details
        if test_strategy_str:
            generated_fields["testStrategy"] = test_strategy_str

        existing_idx = existing_by_id.get(num_id)
        if existing_idx is not None:
            existing_task = tag_tasks[existing_idx]
            if not isinstance(existing_task, dict):
                raise ValueError(f"existing Taskmaster task {num_id} is not an object")
            # The view owns the mapped fields above. Master-native fields such as
            # subtasks and future extensions survive unless an explicit mapped field changes.
            tag_tasks[existing_idx] = merge_master_fields(existing_task, generated_fields)
        else:
            existing_by_id[num_id] = len(tag_tasks)
            tag_tasks.append(generated_fields)

    # Prepare every view before writing any of the three files.
    def mark_exported(file_path: Path) -> Any:
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        is_list = isinstance(data, list)
        tasks = data if is_list else data.get("tasks", [])
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue
            if tid in id_map:
                t["taskmaster_id"] = id_map[tid]
                t["taskmaster_exported"] = True
            else:
                # 仅在缺失时写入 False，避免覆盖之前的 True
                if "taskmaster_exported" not in t:
                    t["taskmaster_exported"] = False
        if is_list:
            new_data = tasks
        else:
            new_data = data
            new_data["tasks"] = tasks
        return new_data

    updates: list[tuple[Path, Any]] = [(TASKMASTER_TASKS_FILE, root_obj)]
    for src_file in task_files:
        marked = mark_exported(src_file)
        if marked is not None:
            updates.append((src_file, marked))
    _atomic_write_many(updates)
    print(f"Wrote Task Master tasks file to: {TASKMASTER_TASKS_FILE}")


def _atomic_write_many(updates: list[tuple[Path, Any]]) -> None:
    staged: list[tuple[Path, Path]] = []
    originals: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    try:
        for path, payload in updates:
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = path.read_bytes() if path.exists() else None
            fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
            os.close(fd)
            temp_path = Path(tmp)
            staged.append((path, temp_path))
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        for path, temp_path in staged:
            os.replace(temp_path, path)
            replaced.append(path)
    except Exception:
        for path in reversed(replaced):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    finally:
        for _, temp_path in staged:
            temp_path.unlink(missing_ok=True)

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build or update Task Master-compatible tasks.json from NG/GM tasks, "
            "optionally for a specific tag and task id set."
        )
    )
    parser.add_argument(
        "--tag",
        default="master",
        help="Task Master tag name to update (default: master).",
    )
    parser.add_argument(
        "--tasks-file",
        dest="tasks_files",
        action="append",
        help="Source tasks json file (e.g. .taskmaster/tasks/tasks_back.json). "
             "Can be given multiple times; defaults to tasks_back/gameplay/longterm.",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        help="Task ids (e.g. NG-0020 GM-0101) to export (closure of dependencies will be included).",
    )
    parser.add_argument(
        "--ids-file",
        help="JSON file containing an array of task ids (strings) to export.",
    )
    parser.add_argument(
        "--allow-legacy-t2-default",
        action="store_true",
        help="Use the historical T2 root set when no explicit ids are supplied. Not for Chapter 3 incremental export.",
    )
    args = parser.parse_args()
    build_taskmaster_tasks(args)


if __name__ == "__main__":
    main()
