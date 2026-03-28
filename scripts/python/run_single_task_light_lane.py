#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run workflow 5.1 single-task light lane with resilient full-step execution.

Key behavior:
- Runs all configured steps for each task by default (does not stop on step failure).
- Supports resume from summary.json.
- Writes per-step logs and rolling summary under logs/ci/<YYYY-MM-DD>/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _today() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def _default_out_dir(root: Path) -> Path:
    return root / "logs" / "ci" / _today() / "single-task-light-lane-v2"


def _parse_task_ids_csv(raw: str) -> list[int]:
    out: list[int] = []
    for token in str(raw or "").split(","):
        value = token.strip()
        if not value.isdigit():
            continue
        task_id = int(value)
        if task_id > 0:
            out.append(task_id)
    return sorted(set(out))


def _taskmaster_tasks_path(root: Path) -> Path:
    candidates = [
        root / ".taskmaster" / "tasks" / "tasks.json",
        root / "examples" / "taskmaster" / "tasks.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _load_master_tasks(root: Path) -> list[dict[str, Any]]:
    path = _taskmaster_tasks_path(root)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data.get("master"), dict) and isinstance(data["master"].get("tasks"), list):
        return [item for item in data["master"]["tasks"] if isinstance(item, dict)]
    if isinstance(data.get("tasks"), list):
        return [item for item in data["tasks"] if isinstance(item, dict)]
    return []


def _load_master_task_ids(root: Path) -> list[int]:
    task_ids: list[int] = []
    for item in _load_master_tasks(root):
        raw = str(item.get("id") or "").strip()
        if raw.isdigit():
            task_ids.append(int(raw))
    return sorted(set(task_ids))


def _load_in_progress_task_ids(root: Path) -> list[int]:
    task_ids: list[int] = []
    for item in _load_master_tasks(root):
        raw_id = str(item.get("id") or "").strip()
        if not raw_id.isdigit():
            continue
        status = str(item.get("status") or "").strip().lower().replace("-", "_")
        if status in {"in_progress", "active", "working"}:
            task_ids.append(int(raw_id))
    return sorted(set(task_ids))


def _steps(*, align_apply: bool, delivery_profile: str) -> list[tuple[str, list[str]]]:
    align_cmd = [
        "py",
        "-3",
        "scripts/sc/llm_align_acceptance_semantics.py",
        "--task-ids",
        "{id}",
        "--strict-task-selection",
        "--delivery-profile",
        delivery_profile,
    ]
    if align_apply:
        align_cmd.append("--apply")

    return [
        (
            "extract",
            [
                "py",
                "-3",
                "scripts/sc/llm_extract_task_obligations.py",
                "--task-id",
                "{id}",
                "--delivery-profile",
                delivery_profile,
                "--reuse-last-ok",
                "--explain-reuse-miss",
            ],
        ),
        ("align", align_cmd),
        (
            "coverage",
            [
                "py",
                "-3",
                "scripts/sc/llm_check_subtasks_coverage.py",
                "--task-id",
                "{id}",
                "--strict-view-selection",
                "--delivery-profile",
                delivery_profile,
            ],
        ),
        (
            "semantic_gate",
            [
                "py",
                "-3",
                "scripts/sc/llm_semantic_gate_all.py",
                "--task-ids",
                "{id}",
                "--max-needs-fix",
                "0",
                "--max-unknown",
                "3",
                "--delivery-profile",
                delivery_profile,
            ],
        ),
        (
            "fill_refs_dry",
            [
                "py",
                "-3",
                "scripts/sc/llm_fill_acceptance_refs.py",
                "--task-id",
                "{id}",
            ],
        ),
        (
            "fill_refs_write",
            [
                "py",
                "-3",
                "scripts/sc/llm_fill_acceptance_refs.py",
                "--task-id",
                "{id}",
                "--write",
            ],
        ),
        (
            "fill_refs_verify",
            [
                "py",
                "-3",
                "scripts/sc/llm_fill_acceptance_refs.py",
                "--task-id",
                "{id}",
            ],
        ),
    ]


def _run_step(root: Path, cmd: list[str], *, timeout_sec: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(1, int(timeout_sec)),
        )
        return int(proc.returncode), proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "") if exc.stdout is not None else ""
        stderr = str(exc.stderr or "") if exc.stderr is not None else ""
        return 124, stdout, stderr


def _load_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _index_results(results: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in results:
        task_raw = str(row.get("task_id") or "").strip()
        if task_raw.isdigit():
            indexed[int(task_raw)] = row
    return indexed


def _rebuild_counts(summary: dict[str, Any]) -> None:
    results = [row for row in summary.get("results", []) if isinstance(row, dict)]
    failed_step_counts: dict[str, int] = {}
    passed_tasks = 0
    failed_tasks = 0
    for row in results:
        if bool(row.get("ok")):
            passed_tasks += 1
            continue
        failed_tasks += 1
        for step in row.get("failed_steps", []) or []:
            key = str(step).strip()
            if not key:
                continue
            failed_step_counts[key] = failed_step_counts.get(key, 0) + 1
    summary["processed_tasks"] = len(results)
    summary["passed_tasks"] = passed_tasks
    summary["failed_tasks"] = failed_tasks
    summary["failed_step_counts"] = failed_step_counts


def _select_task_ids(root: Path, args: argparse.Namespace) -> list[int]:
    all_ids = _load_master_task_ids(root)
    if not all_ids:
        return []
    if str(args.task_ids).strip():
        selected = [task_id for task_id in _parse_task_ids_csv(args.task_ids) if task_id in set(all_ids)]
    else:
        in_progress = _load_in_progress_task_ids(root)
        if in_progress:
            selected = in_progress
        else:
            start = max(1, int(args.task_id_start))
            end = int(args.task_id_end) if int(args.task_id_end) > 0 else max(all_ids)
            selected = [task_id for task_id in all_ids if start <= task_id <= end]
    if int(args.max_tasks) > 0:
        selected = selected[: int(args.max_tasks)]
    return selected


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run workflow 5.1 single-task light lane with full-step execution.")
    parser.add_argument("--task-ids", default="", help="Optional CSV task ids override (e.g. 12,14,21).")
    parser.add_argument("--task-id-start", type=int, default=1)
    parser.add_argument("--task-id-end", type=int, default=0, help="0 means until max task id.")
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means all selected tasks.")
    parser.add_argument("--timeout-sec", type=int, default=420, help="Per-step timeout in seconds.")
    parser.add_argument("--out-dir", default="", help="Output directory. Default: logs/ci/<date>/single-task-light-lane-v2")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing summary.json and rerun from scratch.")
    parser.add_argument("--stop-on-step-failure", action="store_true", help="Stop remaining steps in one task when one step fails.")
    parser.add_argument("--no-align-apply", action="store_true", help="Do not pass --apply to align step (read-only mode).")
    parser.add_argument(
        "--delivery-profile",
        default=str(os.environ.get("DELIVERY_PROFILE") or "fast-ship"),
        choices=["playable-ea", "fast-ship", "standard"],
        help="Delivery profile for light-lane LLM steps.",
    )
    parser.add_argument("--self-check", action="store_true", help="Print resolved task range and step names, then exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = _repo_root()
    selected = _select_task_ids(root, args)
    if not selected:
        print("SINGLE_TASK_LIGHT_LANE status=fail reason=no_selected_tasks")
        return 2

    out_dir = Path(args.out_dir) if str(args.out_dir).strip() else _default_out_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"
    steps = _steps(align_apply=(not bool(args.no_align_apply)), delivery_profile=str(args.delivery_profile))

    if bool(args.self_check):
        payload = {
            "status": "ok",
            "task_count": len(selected),
            "task_id_start": selected[0],
            "task_id_end": selected[-1],
            "steps": [name for name, _ in steps],
            "delivery_profile": str(args.delivery_profile),
            "out_dir": str(out_dir).replace("\\", "/"),
        }
        _write_json(summary_path, payload)
        print(
            f"SINGLE_TASK_LIGHT_LANE_SELF_CHECK status=ok tasks={len(selected)} "
            f"range=T{selected[0]}-T{selected[-1]} out={str(summary_path).replace('\\', '/')}"
        )
        return 0

    old_summary = None if bool(args.no_resume) else _load_summary(summary_path)
    summary: dict[str, Any] = old_summary if isinstance(old_summary, dict) else {}
    if not isinstance(summary.get("results"), list):
        summary["results"] = []
    summary.setdefault("cmd", "run_single_task_light_lane")
    summary.setdefault("started_at", dt.datetime.now().isoformat(timespec="seconds"))
    summary["task_id_start"] = selected[0]
    summary["task_id_end"] = selected[-1]
    summary["task_count"] = len(selected)
    summary["delivery_profile"] = str(args.delivery_profile)
    summary["align_apply"] = not bool(args.no_align_apply)
    summary["out_dir"] = str(out_dir).replace("\\", "/")
    summary["status"] = "running"

    existing = _index_results(summary["results"])
    updated: dict[int, dict[str, Any]] = {task_id: row for task_id, row in existing.items() if task_id in set(selected)}

    for idx, task_id in enumerate(selected, start=1):
        print(f"[{idx}/{len(selected)}] run task {task_id}")
        row = updated.get(task_id, {"task_id": task_id, "steps": []})
        step_map = {str(item.get("step")): item for item in row.get("steps", []) if isinstance(item, dict)}
        failed_steps: list[str] = []

        for step_name, template in steps:
            cmd = [part.format(id=task_id) for part in template]
            rc, stdout, stderr = _run_step(root, cmd, timeout_sec=int(args.timeout_sec))
            log_path = out_dir / f"t{task_id:04d}--{step_name}.log"
            log_body = "\n".join(
                [
                    f"cmd: {' '.join(cmd)}",
                    f"rc: {rc}",
                    "--- stdout ---",
                    stdout or "",
                    "--- stderr ---",
                    stderr or "",
                ]
            )
            log_path.write_text(log_body, encoding="utf-8")
            step_map[step_name] = {
                "step": step_name,
                "rc": rc,
                "log": str(log_path.relative_to(root)).replace("\\", "/"),
                "stdout_tail": stdout.strip().splitlines()[-1] if stdout.strip() else "",
                "stderr_tail": stderr.strip().splitlines()[-1] if stderr.strip() else "",
            }
            if rc != 0:
                failed_steps.append(step_name)
                if bool(args.stop_on_step_failure):
                    break

        ordered = [step_map[name] for name, _ in steps if name in step_map]
        row["steps"] = ordered
        row["failed_steps"] = failed_steps
        row["first_failed_step"] = failed_steps[0] if failed_steps else ""
        row["ok"] = (len(failed_steps) == 0 and len(ordered) == len(steps))
        updated[task_id] = row

        summary["results"] = [updated[key] for key in sorted(updated.keys())]
        _rebuild_counts(summary)
        summary["remaining_tasks"] = max(0, len(selected) - int(summary.get("processed_tasks", 0)))
        summary["last_task_id"] = task_id
        summary["last_updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
        _write_json(summary_path, summary)

    _rebuild_counts(summary)
    summary["remaining_tasks"] = max(0, len(selected) - int(summary.get("processed_tasks", 0)))
    summary["status"] = "ok" if int(summary.get("failed_tasks", 0)) == 0 else "fail"
    summary["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    _write_json(summary_path, summary)
    print(
        "SINGLE_TASK_LIGHT_LANE "
        f"status={summary['status']} processed={summary.get('processed_tasks', 0)}/{len(selected)} "
        f"passed={summary.get('passed_tasks', 0)} failed={summary.get('failed_tasks', 0)} "
        f"out={str(summary_path).replace('\\', '/')}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
