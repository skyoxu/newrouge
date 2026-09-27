#!/usr/bin/env python3
"""Synchronize frozen Taskmaster statuses from implemented pending scope."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PENDING_TO_DONE = {54, 57, 59, 60, 64, 71, 72, 73, 74, 75, 76, 92, 105, 131, 132, 133}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    master_path = ROOT / ".taskmaster/tasks/tasks.json"
    master = load(master_path)
    rows = master["master"]["tasks"]
    changed = []
    for row in rows:
        if row.get("id") in PENDING_TO_DONE and row.get("status") == "pending":
            row["status"] = "done"
            changed.append(row["id"])
    if set(changed) != PENDING_TO_DONE:
        raise SystemExit(f"unexpected pending status set; changed={sorted(changed)}")
    save(master_path, master)

    view_changed = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        path = ROOT / ".taskmaster/tasks" / name
        data = load(path)
        for row in data:
            if row.get("taskmaster_id") in PENDING_TO_DONE and row.get("status") == "pending":
                row["status"] = "done"
                view_changed.append((name, row["id"], row["taskmaster_id"]))
        save(path, data)

    audit = {
        "schema_version": "chapter3.frozen-status-sync.v1",
        "taskmaster_ids": sorted(PENDING_TO_DONE),
        "master_changed": sorted(changed),
        "view_changed": [list(item) for item in view_changed],
        "rule": "Implemented pending tasks are done; cancelled tasks remain cancelled.",
    }
    out = ROOT / "logs/ci/task-generation/frozen-status-sync.v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    save(out, audit)
    print(json.dumps({"master_changed": len(changed), "view_changed": len(view_changed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
