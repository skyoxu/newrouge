#!/usr/bin/env python3
"""Render the frozen 133-task design baseline from the Taskmaster triplet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md")


def cell(value: object) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def render(root: Path) -> str:
    task_root = root / ".taskmaster/tasks"
    master = json.loads((task_root / "tasks.json").read_text(encoding="utf-8"))["master"]["tasks"]
    back = json.loads((task_root / "tasks_back.json").read_text(encoding="utf-8"))
    gameplay = json.loads((task_root / "tasks_gameplay.json").read_text(encoding="utf-8"))
    expected = set(range(1, 134))
    ids = [row["id"] for row in master]
    if len(ids) != 133 or set(ids) != expected:
        raise ValueError("Taskmaster baseline must contain exactly numeric task IDs 1-133")
    views: dict[int, list[tuple[str, dict]]] = {task_id: [] for task_id in expected}
    for name, rows in (("back", back), ("gameplay", gameplay)):
        for row in rows:
            task_id = row.get("taskmaster_id")
            if task_id in views:
                views[task_id].append((name, row))
    if any(not rows for rows in views.values()):
        raise ValueError("Every master task must have at least one task-view row")
    lines = [
        "# NewRouge current-stage GDD task baseline",
        "",
        "GDD-ID: GDD-NEWROUGE-TASK-BASELINE",
        "Status: Current",
        "Task scope: T1-T133 only",
        "",
        "This GDD projects the existing task scope from the Taskmaster triplet.",
        "It is the sole GDD input for Chapter 3 and the sole GDD path for Knowledge.",
        "It does not authorize new tasks. Task identity and status remain authoritative",
        "only in `.taskmaster/tasks/tasks.json`. Acceptance and test evidence remain",
        "in the two task views and are not duplicated as design requirements here.",
        "The historical GDD files remain available as references, not generation inputs.",
        "",
        "## Existing task scope",
        "",
        "| Task | Title | Design scope | View-specific detail | Task views |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task in sorted(master, key=lambda row: row["id"]):
        task_id = task["id"]
        rows = views[task_id]
        description = cell(task.get("description"))
        differences = list(dict.fromkeys(
            f"{name}: {cell(row.get('description'))}"
            for name, row in rows
            if cell(row.get("description")) != description
        ))
        view_ids = ", ".join(f"{name}:{row.get('id', '?')}" for name, row in rows)
        lines.append(
            f"| T{task_id} | {cell(task.get('title'))} | {description} | "
            f"{' / '.join(differences) or '—'} | "
            f"{view_ids} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / OUTPUT
    expected = render(ROOT)
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            raise SystemExit("GDD task baseline is stale")
        print("GDD task baseline is current: T1-T133")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Wrote {OUTPUT}: T1-T133")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
