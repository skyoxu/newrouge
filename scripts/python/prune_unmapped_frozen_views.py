#!/usr/bin/env python3
"""Remove legacy task-view rows that have no frozen Taskmaster identity."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    paths = [ROOT / ".taskmaster/tasks/tasks_back.json", ROOT / ".taskmaster/tasks/tasks_gameplay.json"]
    removed = []
    stale_ids = set()
    payloads = {}
    for path in paths:
        rows = load(path)
        if not isinstance(rows, list):
            raise SystemExit(f"task view is not a list: {path}")
        payloads[path] = rows
        for row in rows:
            if row.get("taskmaster_id") is None:
                stale_ids.add(str(row.get("id")))
    if not stale_ids:
        print(json.dumps({"removed": 0, "dependency_refs_removed": 0}))
        return 0
    dependency_refs_removed = []
    for path, rows in payloads.items():
        kept = []
        for row in rows:
            if str(row.get("id")) in stale_ids:
                removed.append({"view": path.name, "id": row.get("id"), "title": row.get("title")})
                continue
            deps = row.get("depends_on")
            if isinstance(deps, list):
                filtered = [dep for dep in deps if str(dep) not in stale_ids]
                for dep in deps:
                    if str(dep) in stale_ids:
                        dependency_refs_removed.append({"view": path.name, "task": row.get("id"), "dependency": dep})
                row["depends_on"] = filtered
            kept.append(row)
        save(path, kept)
    audit = {
        "schema_version": "chapter3.unmapped-view-prune.v1",
        "removed_ids": sorted(stale_ids),
        "removed_rows": removed,
        "dependency_refs_removed": dependency_refs_removed,
        "reason": "Rows without taskmaster_id are outside the frozen T1-T133 authority set.",
    }
    out = ROOT / "logs/ci/task-generation/unmapped-view-prune.v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    save(out, audit)
    print(json.dumps({"removed": len(removed), "dependency_refs_removed": len(dependency_refs_removed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
