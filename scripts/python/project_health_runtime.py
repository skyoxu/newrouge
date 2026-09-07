#!/usr/bin/env python3
"""Run task-scoped Godot evidence checks without changing repository sources."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from project_health_knowledge import base_dir, read_json, write_json


def _gameplay_tasks(root: Path) -> list[dict]:
    path = root / ".taskmaster/tasks/tasks_gameplay.json"
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    return [row for row in rows if any(str(ref).replace("\\", "/").startswith("Tests.Godot/") for ref in row.get("test_refs", []))]


def _run_task(root: Path, task: dict, godot_bin: str, timeout: int) -> dict:
    refs = [str(ref).replace("\\", "/") for ref in task.get("test_refs", [])]
    refs = [ref for ref in refs if ref.startswith("Tests.Godot/")]
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, str(root / "scripts/python/run_gdunit.py"), "--godot-bin", godot_bin,
               "--project", "Tests.Godot", "--timeout-sec", str(timeout)]
    for ref in refs:
        command.extend(["--add", ref.removeprefix("Tests.Godot/")])
    try:
        proc = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout + 30)
        status = "passed" if proc.returncode == 0 else "failed"
        reason = None if status == "passed" else (proc.stderr or proc.stdout)[-2000:]
    except subprocess.TimeoutExpired as exc:
        status, reason = "failed", "runtime test timed out"
        proc = None
    evidence = base_dir(root) / "runtime" / f"task-{task.get('taskmaster_id', task.get('id'))}-{uuid.uuid4().hex}.json"
    payload = {"schema_version": "newrouge.project-health-runtime.v1", "task_id": task.get("taskmaster_id"),
               "source_revision": _main_revision(root), "test_refs": refs, "command": command,
               "status": status, "reason": reason, "started_at": started,
               "finished_at": datetime.now(timezone.utc).isoformat(), "exit_code": proc.returncode if proc else None}
    write_json(evidence, payload)
    payload["evidence_path"] = evidence.relative_to(root).as_posix()
    return payload


def _main_revision(root: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "refs/heads/main"],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() if proc.returncode == 0 else None


def verify(root: Path, godot_bin: str, timeout: int) -> dict:
    tasks = _gameplay_tasks(root)
    results = [_run_task(root, task, godot_bin, timeout) for task in tasks]
    revision = _main_revision(root)
    for result in results:
        result["runtime_verified"] = result["status"] == "passed" and result["source_revision"] == revision
    output = base_dir(root) / "runtime" / "latest.json"
    write_json(output, {"schema_version": "newrouge.project-health-runtime-index.v1", "source_revision": revision,
                        "tasks": results, "summary": {"total": len(results),
                        "runtime_verified": sum(x["runtime_verified"] for x in results),
                        "runtime_failed": sum(x["status"] == "failed" for x in results)}})
    return read_json(output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--godot-bin", required=True)
    parser.add_argument("--timeout-sec", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.repo_root.resolve(), args.godot_bin, args.timeout_sec), ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
