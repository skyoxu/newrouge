#!/usr/bin/env python3
"""Report explicit Taskmaster mentions in Chapter 3 semantic requirements.

Mentions are review hints, never evidence of ownership. This command only writes
an audit report under logs and does not edit Taskmaster or semantic artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path


TASK_TOKEN = re.compile(r"\bT(\d{1,3})\b", re.IGNORECASE)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--semantics", default="logs/ci/task-generation/semantic-requirements.v1.json")
    parser.add_argument("--out", default="logs/ci/task-generation/task-semantic-ref-review.v1.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    requirements = read_json(root / args.semantics)["requirements"]
    views = [read_json(root / ".taskmaster/tasks/tasks_back.json"), read_json(root / ".taskmaster/tasks/tasks_gameplay.json")]
    task_ids = {str(row["taskmaster_id"]) for rows in views for row in rows}
    rows = []
    for requirement in requirements:
        statement = str(requirement.get("statement") or "")
        mentions = sorted(set(TASK_TOKEN.findall(statement)) & task_ids, key=int)
        rows.append({
            "requirement_id": str(requirement["requirement_id"]),
            "mentioned_task_ids": mentions,
            "classification": "single_mention" if len(mentions) == 1 else "aggregate_mention" if mentions else "no_mention",
            "statement": statement,
            "source_block_ids": requirement.get("source_block_ids", []),
        })
    counts = {kind: sum(row["classification"] == kind for row in rows) for kind in ("single_mention", "aggregate_mention", "no_mention")}
    report = {
        "schema": "chapter3.task-semantic-ref-review.v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requirement_count": len(rows),
        "classification_counts": counts,
        "review_rule": "A task mention is not an ownership assignment; verify source, task scope, and acceptance before patching.",
        "requirements": rows,
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
