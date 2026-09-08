#!/usr/bin/env python3
"""Run task-scoped Godot evidence checks without changing repository sources."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from project_health_knowledge import base_dir, read_json, write_json

GODOT_REF = "Tests.Godot/"
CLEANUP_MARGIN_SECONDS = 30
REQUIRED_EVIDENCE_FIELDS = {
    "task_id", "source_revision", "test_refs", "scenes", "status",
    "started_at", "finished_at", "evidence_path",
}


def _references(value, sources: dict[str, str]) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    refs = re.findall(r"Tests\.Godot/[A-Za-z0-9_./-]+", text.replace("\\\\", "/"))
    refs = [ref.rstrip(".,;/") for ref in refs]
    refs = [ref for ref in refs if '..' not in Path(ref).parts and
            (ref in sources or any(path.startswith(ref.rstrip('/') + '/') for path in sources))]
    return list(dict.fromkeys(refs))


def _task_id(value) -> str:
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise ValueError("taskmaster_id must be a canonical positive numeric id")
    return text


def _gameplay_tasks(root: Path, state: dict | None = None, include_all: bool = False) -> list[dict]:
    if state is None:
        latest = base_dir(root) / "latest.json"
        if not latest.exists():
            raise ValueError("A successful local source scan is required before runtime verification")
        state = read_json(latest)
    source = state.get("sources", {}).get(".taskmaster/tasks/tasks_gameplay.json")
    if not isinstance(source, str):
        raise ValueError("The selected scan does not contain tasks_gameplay.json")
    rows = json.loads(source)
    static_by_id = {_task_id(item["task"]["id"]): item.get("godot", {}) for item in state.get("tasks", [])}
    result, seen = [], set()
    for row in rows:
        task_id = _task_id(row.get("taskmaster_id", ""))
        if task_id not in static_by_id:
            continue
        if task_id in seen:
            continue
        seen.add(task_id)
        refs = _references({"test_refs": row.get("test_refs", []),
                            "acceptance_criteria": row.get("acceptance_criteria", []),
                            "test_strategy": row.get("testStrategy", row.get("test_strategy", []))},
                           state.get("sources", {}))
        static = static_by_id.get(task_id, {})
        explicit_runtime = "gdunit" in json.dumps(row, ensure_ascii=False).casefold()
        reviewed_mapping = bool(static.get("scenes"))
        if include_all or refs or explicit_runtime or reviewed_mapping:
            result.append({**row, "taskmaster_id": task_id,
                           "runtime_test_refs": refs, "static_godot": static})
    return result


def _write_evidence(root: Path, task: dict, revision: str, status: str, reason: str | None,
                    command: list[str], started: str, exit_code: int | None) -> dict:
    task_id = _task_id(task.get("taskmaster_id"))
    refs = task.get("runtime_test_refs", [])
    scenes = [item.get("scene") for item in task.get("static_godot", {}).get("scenes", []) if item.get("scene")]
    evidence = base_dir(root) / "runtime" / f"task-{task_id}-{uuid.uuid4().hex}.json"
    payload = {"schema_version": "newrouge.project-health-runtime.v1", "task_id": task_id,
               "source_revision": revision, "test_refs": refs, "scenes": scenes, "command": command,
               "status": status, "reason": reason, "started_at": started,
               "finished_at": datetime.now(timezone.utc).isoformat(), "exit_code": exit_code,
               "evidence_path": evidence.relative_to(root).as_posix(), "runtime_verified": False}
    write_json(evidence, payload)
    return payload


def _run_task(root: Path, task: dict, godot_bin: str, timeout: int, revision: str) -> dict:
    refs = task.get("runtime_test_refs", [])
    started = datetime.now(timezone.utc).isoformat()
    if not refs:
        return _write_evidence(root, task, revision, "runtime_unverified",
                               "No task-scoped Godot/GdUnit assertion path was found", [], started, None)
    command = [sys.executable, str(root / "scripts/python/run_gdunit.py"), "--godot-bin", godot_bin,
               "--project", "Tests.Godot", "--prewarm", "--timeout-sec", str(timeout)]
    for ref in refs:
        command.extend(["--add", ref.removeprefix("Tests.Godot/")])
    try:
        proc = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout + CLEANUP_MARGIN_SECONDS)
        status = "passed" if proc.returncode == 0 else "failed"
        reason = None if status == "passed" else (proc.stderr or proc.stdout)[-2000:]
    except subprocess.TimeoutExpired as exc:
        status, reason = "failed", "runtime test timed out"
        proc = None
    return _write_evidence(root, task, revision, status, reason, command, started,
                           proc.returncode if proc else None)


def _main_revision(root: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "refs/heads/main"],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() if proc.returncode == 0 else None


def _scan_revision(root: Path) -> str | None:
    latest = base_dir(root) / "latest.json"
    return read_json(latest).get("revision") if latest.exists() else None


def _complete(result: dict) -> bool:
    return REQUIRED_EVIDENCE_FIELDS <= result.keys() and bool(result.get("test_refs"))


def _unverified_evidence(root: Path, task: dict, revision: str, reason: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return _write_evidence(root, task, revision, "runtime_unverified", reason, [], now, None)


def _runtime_inputs_match(root: Path, revision: str) -> tuple[bool, str | None]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        return False, "Runtime verification requires a local-main Git revision"
    main = _main_revision(root)
    if main != revision:
        return False, "The scanned revision no longer matches local main"
    paths = ["project.godot", "addons", "Game.Godot", "Tests.Godot"]
    diff = subprocess.run(["git", "-C", str(root), "diff", "--quiet", revision, "--", *paths])
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", *paths],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if diff.returncode != 0 or status.returncode != 0 or status.stdout.strip():
        return False, "Runtime inputs differ from the scanned local-main revision"
    return True, None


def _persist_result(root: Path, result: dict) -> None:
    path = root / result["evidence_path"]
    write_json(path, result)


def _summary(results: list[dict], timed_out: bool) -> dict:
    return {"total": len(results), "runtime_verified": sum(bool(x.get("runtime_verified")) for x in results),
            "runtime_failed": sum(x["status"] == "failed" for x in results),
            "runtime_unverified": sum(x["status"] == "runtime_unverified" for x in results),
            "global_timeout_reached": timed_out}


def verify(root: Path, godot_bin: str, timeout: int, task_id: str | None = None,
           global_timeout: int = 3600, task_ids: list[str] | None = None,
           all_gameplay: bool = False) -> dict:
    scan_path = base_dir(root) / "latest.json"
    if not scan_path.exists():
        raise ValueError("A successful local source scan is required before runtime verification")
    state = read_json(scan_path)
    scan_revision = state.get("revision")
    tasks = _gameplay_tasks(root, state, include_all=all_gameplay)
    if all_gameplay and (task_id is not None or task_ids is not None):
        raise ValueError("--all-gameplay cannot be combined with task selection")
    selected_ids = None
    if task_ids is not None:
        selected_ids = {_task_id(value) for value in task_ids}
        if not selected_ids:
            raise ValueError("At least one task id is required")
        tasks = [task for task in tasks if task.get("taskmaster_id") in selected_ids]
        found_ids = {task.get("taskmaster_id") for task in tasks}
        missing = sorted(selected_ids - found_ids, key=int)
        if missing:
            raise ValueError(f"Runtime-eligible gameplay tasks not found: {','.join(missing)}")
    elif task_id is not None:
        task_id = _task_id(task_id)
        tasks = [task for task in tasks if task.get("taskmaster_id") == task_id]
        if not tasks:
            raise ValueError("Runtime-eligible gameplay task not found")
    deadline = time.monotonic() + global_timeout
    results = []
    inputs_match, input_reason = _runtime_inputs_match(root, scan_revision)
    if not inputs_match:
        results = [_unverified_evidence(root, task, scan_revision, input_reason) for task in tasks]
    else:
        for task in tasks:
            remaining = int(deadline - time.monotonic())
            if remaining <= CLEANUP_MARGIN_SECONDS:
                break
            inner_timeout = min(timeout, remaining - CLEANUP_MARGIN_SECONDS)
            results.append(_run_task(root, task, godot_bin, inner_timeout, scan_revision))
        for task in tasks[len(results):]:
            results.append(_unverified_evidence(root, task, scan_revision,
                           "Global runtime verification timeout reached before this task started"))
    stable = _scan_revision(root) == scan_revision and _main_revision(root) == scan_revision
    for result in results:
        result["runtime_verified"] = (result["status"] == "passed" and _complete(result)
                                      and result["source_revision"] == scan_revision and stable)
        if result["status"] == "passed" and not stable:
            result["status"] = "runtime_unverified"
            result["reason"] = "Scan or local-main revision changed during runtime verification"
        _persist_result(root, result)
    timed_out = any((result.get("reason") or "").startswith("Global runtime verification timeout")
                    for result in results)
    output = base_dir(root) / "runtime" / "latest.json"
    merge_ids = selected_ids if selected_ids is not None else ({task_id} if task_id is not None else None)
    if merge_ids is not None and output.exists():
        previous = read_json(output)
        if previous.get("source_revision") == scan_revision:
            results = [row for row in previous.get("tasks", [])
                       if str(row.get("task_id")) not in merge_ids] + results
    write_json(output, {"schema_version": "newrouge.project-health-runtime-index.v1",
                        "source_revision": scan_revision, "tasks": results,
                        "summary": _summary(results, timed_out)})
    return read_json(output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--godot-bin", required=True)
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--global-timeout-sec", type=int, default=3600)
    parser.add_argument("--task-id")
    parser.add_argument("--task-ids", help="Comma-separated gameplay task ids")
    parser.add_argument("--all-gameplay", action="store_true",
                        help="Audit every master-mapped tasks_gameplay row")
    args = parser.parse_args(argv)
    try:
        if args.timeout_sec <= 0 or args.global_timeout_sec <= 0:
            raise ValueError("Timeout values must be positive")
        if sum(bool(value) for value in (args.task_id, args.task_ids, args.all_gameplay)) > 1:
            raise ValueError("Use only one task selection mode")
        task_ids = args.task_ids.split(",") if args.task_ids is not None else None
        print(json.dumps(verify(args.repo_root.resolve(), args.godot_bin, args.timeout_sec,
                                args.task_id, args.global_timeout_sec, task_ids,
                                args.all_gameplay), ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
