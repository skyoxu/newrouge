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
import shutil
import subprocess
from pathlib import Path
from typing import Any

_FILL_REFS_TIMEOUT_SEC = 300
_TIMEOUT_BUFFER_SEC = 120
_RETRY_TIMEOUT_BOOST_SEC = 240
_RETRYABLE_TIMEOUT_STEPS = {"extract", "align"}
_SNAPSHOT_PATTERNS = (
    "summary.json",
    "report.md",
    "verdict.json",
    "prompt.md",
    "output-last-message*.txt",
    "batch-*.tsv",
    "batch-*.trace.log",
    "trace-run-*.log",
)


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


def _delivery_profile_defaults(root: Path, delivery_profile: str) -> dict[str, Any]:
    config_path = root / "scripts" / "sc" / "config" / "delivery_profiles.json"
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") or {}
    payload = profiles.get(str(delivery_profile)) or {}
    return payload if isinstance(payload, dict) else {}


def _profile_step_llm_timeout_sec(root: Path, *, step_name: str, delivery_profile: str) -> int:
    profile = _delivery_profile_defaults(root, delivery_profile)
    if step_name == "extract":
        llm_obligations = profile.get("llm_obligations") or {}
        return int(llm_obligations.get("timeout_sec", 240) or 240)
    if step_name in {"align", "coverage", "semantic_gate"}:
        llm_semantic_gate_all = profile.get("llm_semantic_gate_all") or {}
        return int(llm_semantic_gate_all.get("timeout_sec", 480) or 480)
    return _FILL_REFS_TIMEOUT_SEC


def _resolve_step_timeout_sec(
    step_name: str,
    *,
    delivery_profile: str,
    explicit_timeout_sec: int | None,
    llm_timeout_sec: int | None = None,
    root: Path | None = None,
) -> int:
    if explicit_timeout_sec is not None:
        return max(1, int(explicit_timeout_sec))
    inner_timeout = max(
        1,
        int(
            llm_timeout_sec
            if llm_timeout_sec is not None
            else _profile_step_llm_timeout_sec(root or _repo_root(), step_name=step_name, delivery_profile=delivery_profile)
        ),
    )
    return inner_timeout + _TIMEOUT_BUFFER_SEC


def _step_supports_inner_timeout(step_name: str) -> bool:
    return step_name in {
        "extract",
        "align",
        "coverage",
        "semantic_gate",
        "fill_refs_dry",
        "fill_refs_write",
        "fill_refs_verify",
    }


def _replace_or_append_timeout_arg(cmd: list[str], *, timeout_sec: int) -> list[str]:
    updated: list[str] = []
    idx = 0
    replaced = False
    while idx < len(cmd):
        part = cmd[idx]
        if part == "--timeout-sec":
            updated.extend(["--timeout-sec", str(int(timeout_sec))])
            idx += 2
            replaced = True
            continue
        updated.append(part)
        idx += 1
    if not replaced:
        updated.extend(["--timeout-sec", str(int(timeout_sec))])
    return updated


def _retry_inner_timeout_sec(
    step_name: str,
    *,
    delivery_profile: str,
    llm_timeout_sec: int | None,
    root: Path,
) -> int:
    base_inner = max(
        1,
        int(
            llm_timeout_sec
            if llm_timeout_sec is not None
            else _profile_step_llm_timeout_sec(root, step_name=step_name, delivery_profile=delivery_profile)
        ),
    )
    return max(base_inner + _RETRY_TIMEOUT_BOOST_SEC, int(base_inner * 2))


def _run_step_with_retry(
    *,
    root: Path,
    cmd: list[str],
    step_name: str,
    delivery_profile: str,
    explicit_timeout_sec: int | None,
    llm_timeout_sec: int | None,
) -> tuple[int, str, str, dict[str, Any]]:
    timeout_sec = _resolve_step_timeout_sec(
        step_name,
        delivery_profile=delivery_profile,
        explicit_timeout_sec=explicit_timeout_sec,
        llm_timeout_sec=llm_timeout_sec,
        root=root,
    )
    rc, stdout, stderr = _run_step(root, cmd, timeout_sec=timeout_sec)
    attempts: list[dict[str, Any]] = [
        {
            "attempt": 1,
            "rc": int(rc),
            "timeout_sec": int(timeout_sec),
            "cmd": list(cmd),
            "stdout": stdout,
            "stderr": stderr,
        }
    ]

    if int(rc) == 124 and step_name in _RETRYABLE_TIMEOUT_STEPS:
        retry_cmd = list(cmd)
        retry_inner_timeout = llm_timeout_sec
        if _step_supports_inner_timeout(step_name):
            retry_inner_timeout = _retry_inner_timeout_sec(
                step_name,
                delivery_profile=delivery_profile,
                llm_timeout_sec=llm_timeout_sec,
                root=root,
            )
            retry_cmd = _replace_or_append_timeout_arg(retry_cmd, timeout_sec=retry_inner_timeout)
        retry_wrapper_timeout = max(
            int(timeout_sec),
            _resolve_step_timeout_sec(
                step_name,
                delivery_profile=delivery_profile,
                explicit_timeout_sec=None,
                llm_timeout_sec=retry_inner_timeout,
                root=root,
            ),
        )
        rc, stdout, stderr = _run_step(root, retry_cmd, timeout_sec=retry_wrapper_timeout)
        attempts.append(
            {
                "attempt": 2,
                "rc": int(rc),
                "timeout_sec": int(retry_wrapper_timeout),
                "cmd": list(retry_cmd),
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    metadata = {
        "retry_count": max(0, len(attempts) - 1),
        "retry_rcs": [int(item["rc"]) for item in attempts],
        "attempt_count": len(attempts),
        "attempts": attempts,
    }
    return int(rc), stdout, stderr, metadata


def _steps(*, align_apply: bool, delivery_profile: str, llm_timeout_sec: int | None) -> list[tuple[str, list[str]]]:
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
    if llm_timeout_sec is not None:
        align_cmd.extend(["--timeout-sec", str(int(llm_timeout_sec))])
    if align_apply:
        align_cmd.append("--apply")

    steps: list[tuple[str, list[str]]] = [
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
    if llm_timeout_sec is not None:
        llm_timeout_parts = ["--timeout-sec", str(int(llm_timeout_sec))]
        step_names = {"extract", "coverage", "semantic_gate", "fill_refs_dry", "fill_refs_write", "fill_refs_verify"}
        steps = [
            (name, command + llm_timeout_parts if name in step_names else command)
            for name, command in steps
        ]
    return steps


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
    timeout_step_counts: dict[str, int] = {}
    failure_category_counts: dict[str, int] = {}
    failure_category_task_ids: dict[str, list[int]] = {}
    failure_category_by_task: dict[str, str] = {}
    prompt_trimmed_task_ids: list[int] = []
    semantic_gate_budget_hits: list[dict[str, Any]] = []
    passed_tasks = 0
    failed_tasks = 0
    for row in results:
        task_raw = str(row.get("task_id") or "").strip()
        for step in row.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            if int(step.get("rc") or 0) == 124:
                key = str(step.get("step") or "").strip()
                if key:
                    timeout_step_counts[key] = timeout_step_counts.get(key, 0) + 1
            if str(step.get("step") or "").strip() == "semantic_gate":
                inner_summary = step.get("inner_summary")
                if isinstance(inner_summary, dict) and bool(inner_summary.get("prompt_trimmed")) and task_raw.isdigit():
                    task_id = int(task_raw)
                    if task_id not in prompt_trimmed_task_ids:
                        prompt_trimmed_task_ids.append(task_id)
                        semantic_gate_budget_hits.append(
                            {
                                "task_id": task_id,
                                "prompt_trimmed": True,
                                "task_brief_budget": inner_summary.get("task_brief_budget"),
                                "prompt_chars": inner_summary.get("prompt_chars"),
                            }
                        )
        if bool(row.get("ok")):
            passed_tasks += 1
            continue
        failed_tasks += 1
        category = _classify_failed_task(row)
        if category and task_raw.isdigit():
            failure_category_counts[category] = failure_category_counts.get(category, 0) + 1
            failure_category_task_ids.setdefault(category, []).append(int(task_raw))
            failure_category_by_task[task_raw] = category
        for step in row.get("failed_steps", []) or []:
            key = str(step).strip()
            if not key:
                continue
            failed_step_counts[key] = failed_step_counts.get(key, 0) + 1
    summary["processed_tasks"] = len(results)
    summary["passed_tasks"] = passed_tasks
    summary["failed_tasks"] = failed_tasks
    summary["failed_step_counts"] = failed_step_counts
    summary["timeout_step_counts"] = timeout_step_counts
    summary["failure_category_counts"] = failure_category_counts
    summary["failure_category_task_ids"] = failure_category_task_ids
    summary["failure_category_by_task"] = failure_category_by_task
    summary["prompt_trimmed_task_ids"] = prompt_trimmed_task_ids
    summary["prompt_trimmed_count"] = len(prompt_trimmed_task_ids)
    summary["semantic_gate_budget_hits"] = semantic_gate_budget_hits


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


def _extract_inner_out_dir(stdout: str, stderr: str) -> Path | None:
    lines: list[str] = []
    for blob in (stdout, stderr):
        lines.extend(str(blob or "").splitlines())
    for line in reversed(lines):
        if "out=" not in line:
            continue
        raw = line.split("out=", 1)[1].strip().strip("\"'")
        if raw:
            return Path(raw)
    return None


def _copy_file_set(source_dir: Path, artifact_dir: Path) -> list[str]:
    copied: list[str] = []
    for pattern in _SNAPSHOT_PATTERNS:
        for path in sorted(source_dir.glob(pattern)):
            if not path.is_file():
                continue
            target = artifact_dir / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(str(target.name))
    return copied


def _summarize_inner_summary(step_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("cmd", "status", "error", "schema_version"):
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    if step_name == "semantic_gate":
        batch_meta = payload.get("batch_meta")
        if isinstance(batch_meta, list) and batch_meta:
            first = batch_meta[0]
            if isinstance(first, dict):
                for key in ("prompt_chars", "prompt_trimmed", "task_brief_budget", "task_count"):
                    value = first.get(key)
                    if value is not None:
                        summary[key] = value
    elif step_name == "coverage":
        summary["uncovered_subtask_ids"] = list(payload.get("uncovered_subtask_ids") or [])
        votes = payload.get("consensus_votes")
        if isinstance(votes, dict):
            summary["consensus_votes"] = votes
    elif step_name == "extract":
        for key in ("hard_uncovered_count", "advisory_uncovered_count", "excerpt_prefix_stripped_matches"):
            value = payload.get(key)
            if value is not None:
                summary[key] = value
        auto_escalate = payload.get("auto_escalate")
        if isinstance(auto_escalate, dict):
            summary["auto_escalate"] = {
                "triggered": bool(auto_escalate.get("triggered")),
                "reasons": list(auto_escalate.get("reasons") or []),
            }
    elif step_name.startswith("fill_refs"):
        for key in ("task_count", "changed_tasks", "written_tasks", "skipped_tasks"):
            value = payload.get(key)
            if value is not None:
                summary[key] = value
    return summary


def _snapshot_inner_artifacts(
    *,
    root: Path,
    wrapper_out_dir: Path,
    task_id: int,
    step_name: str,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    inner_out_dir = _extract_inner_out_dir(stdout, stderr)
    if inner_out_dir is None:
        return {}
    source_dir = inner_out_dir if inner_out_dir.is_absolute() else (root / inner_out_dir)
    if not source_dir.exists():
        return {"inner_out_dir": str(inner_out_dir).replace("\\", "/"), "inner_artifacts_missing": True}

    artifact_dir = wrapper_out_dir / f"t{task_id:04d}--{step_name}.artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_file_set(source_dir, artifact_dir)

    task_subdir_names = [f"task-{task_id}", f"task-{task_id:04d}"]
    copied_task_dirs: list[str] = []
    for name in task_subdir_names:
        source_task_dir = source_dir / name
        if not source_task_dir.is_dir():
            continue
        target_task_dir = artifact_dir / name
        shutil.copytree(source_task_dir, target_task_dir, dirs_exist_ok=True)
        copied_task_dirs.append(name)

    metadata: dict[str, Any] = {
        "inner_out_dir": str(source_dir).replace("\\", "/"),
        "artifact_dir": str(artifact_dir.relative_to(root)).replace("\\", "/"),
        "artifacts_copied": copied,
    }
    if copied_task_dirs:
        metadata["task_dirs_copied"] = copied_task_dirs
    summary_path = source_dir / "summary.json"
    if summary_path.is_file():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            metadata["inner_summary"] = _summarize_inner_summary(step_name, payload)
    return metadata


def _classify_failed_task(row: dict[str, Any]) -> str | None:
    steps = row.get("steps")
    if not isinstance(steps, list):
        return None

    for step in steps:
        if isinstance(step, dict) and int(step.get("rc") or 0) == 124:
            return "timeout"

    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("step") or "").strip() != "coverage" or int(step.get("rc") or 0) == 0:
            continue
        inner_summary = step.get("inner_summary")
        if isinstance(inner_summary, dict):
            uncovered = inner_summary.get("uncovered_subtask_ids") or []
            if isinstance(uncovered, list):
                return "coverage-gap"
        return "coverage-gap"

    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("step") or "").strip() == "semantic_gate" and int(step.get("rc") or 0) != 0:
            return "semantic-needs-fix"

    for step in steps:
        if not isinstance(step, dict):
            continue
        if int(step.get("rc") or 0) != 0:
            return "model-fail"
    return None


def _build_resume_scope(*, selected: list[int], delivery_profile: str, align_apply: bool) -> dict[str, Any]:
    step_names = [name for name, _ in _steps(align_apply=align_apply, delivery_profile=delivery_profile, llm_timeout_sec=None)]
    return {
        "task_ids": [int(task_id) for task_id in selected],
        "delivery_profile": str(delivery_profile),
        "align_apply": bool(align_apply),
        "step_names": step_names,
    }


def _summary_scope_matches(summary: dict[str, Any], scope: dict[str, Any]) -> bool:
    current = summary.get("resume_scope")
    return bool(isinstance(current, dict) and current == scope)


def _row_is_complete(row: dict[str, Any] | None, *, step_names: list[str]) -> bool:
    if not isinstance(row, dict) or not bool(row.get("ok")):
        return False
    steps = row.get("steps")
    if not isinstance(steps, list):
        return False
    actual_names = [str(item.get("step")) for item in steps if isinstance(item, dict)]
    return actual_names == list(step_names)


def _prepare_failed_row_resume(
    row: dict[str, Any] | None,
    *,
    step_names: list[str],
    resume_failed_task_from: str,
) -> tuple[dict[str, dict[str, Any]], int, str, list[str]]:
    if resume_failed_task_from != "first-failed-step" or not isinstance(row, dict) or bool(row.get("ok")):
        return {}, 0, "", []

    first_failed_step = str(row.get("first_failed_step") or "").strip()
    if not first_failed_step:
        for item in row.get("failed_steps", []) or []:
            first_failed_step = str(item).strip()
            if first_failed_step:
                break
    if not first_failed_step or first_failed_step not in step_names:
        return {}, 0, "", []

    resume_index = step_names.index(first_failed_step)
    if resume_index <= 0:
        return {}, 0, "", []

    prior_names = list(step_names[:resume_index])
    steps = row.get("steps")
    if not isinstance(steps, list):
        return {}, 0, "", []

    existing_by_name: dict[str, dict[str, Any]] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("step") or "").strip()
        if name and name not in existing_by_name:
            existing_by_name[name] = dict(step)

    prefix: dict[str, dict[str, Any]] = {}
    for name in prior_names:
        existing = existing_by_name.get(name)
        existing_rc = None if not isinstance(existing, dict) else existing.get("rc")
        if not isinstance(existing, dict) or existing_rc is None or int(existing_rc) != 0:
            return {}, 0, "", []
        prefix[name] = existing
    return prefix, resume_index, first_failed_step, prior_names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run workflow 5.1 single-task light lane with full-step execution.")
    parser.add_argument("--task-ids", default="", help="Optional CSV task ids override (e.g. 12,14,21).")
    parser.add_argument("--task-id-start", type=int, default=1)
    parser.add_argument("--task-id-end", type=int, default=0, help="0 means until max task id.")
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means all selected tasks.")
    parser.add_argument("--timeout-sec", type=int, default=None, help="Wrapper timeout per step in seconds (default: auto > inner step timeout).")
    parser.add_argument("--llm-timeout-sec", type=int, default=None, help="Forwarded inner timeout for LLM-backed 5.1 steps.")
    parser.add_argument("--out-dir", default="", help="Output directory. Default: logs/ci/<date>/single-task-light-lane-v2")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing summary.json and rerun from scratch.")
    parser.add_argument(
        "--resume-failed-task-from",
        default="always-rerun",
        choices=["always-rerun", "first-failed-step"],
        help="When resuming a failed task, rerun all steps or reuse the successful prefix and restart from the first failed step.",
    )
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
    align_apply = not bool(args.no_align_apply)
    steps = _steps(
        align_apply=align_apply,
        delivery_profile=str(args.delivery_profile),
        llm_timeout_sec=args.llm_timeout_sec,
    )
    step_names = [name for name, _ in steps]
    resume_scope = _build_resume_scope(selected=selected, delivery_profile=str(args.delivery_profile), align_apply=align_apply)

    if bool(args.self_check):
        payload = {
            "status": "ok",
            "task_count": len(selected),
            "task_id_start": selected[0],
            "task_id_end": selected[-1],
            "steps": step_names,
            "delivery_profile": str(args.delivery_profile),
            "out_dir": str(out_dir).replace("\\", "/"),
            "resume_scope": resume_scope,
            "resume_failed_task_from": str(args.resume_failed_task_from),
        }
        _write_json(summary_path, payload)
        print(
            f"SINGLE_TASK_LIGHT_LANE_SELF_CHECK status=ok tasks={len(selected)} "
            f"range=T{selected[0]}-T{selected[-1]} out={str(summary_path).replace('\\', '/')}"
        )
        return 0

    old_summary = None if bool(args.no_resume) else _load_summary(summary_path)
    summary: dict[str, Any]
    if isinstance(old_summary, dict) and _summary_scope_matches(old_summary, resume_scope):
        summary = old_summary
    else:
        summary = {}
    if not isinstance(summary.get("results"), list):
        summary["results"] = []
    summary.setdefault("cmd", "run_single_task_light_lane")
    summary.setdefault("started_at", dt.datetime.now().isoformat(timespec="seconds"))
    summary["task_id_start"] = selected[0]
    summary["task_id_end"] = selected[-1]
    summary["task_count"] = len(selected)
    summary["delivery_profile"] = str(args.delivery_profile)
    summary["align_apply"] = align_apply
    summary["out_dir"] = str(out_dir).replace("\\", "/")
    summary["status"] = "running"
    summary["resume_scope"] = resume_scope
    summary["resume_failed_task_from"] = str(args.resume_failed_task_from)
    summary["llm_timeout_sec"] = int(args.llm_timeout_sec) if args.llm_timeout_sec is not None else None
    summary["wrapper_timeout_sec"] = int(args.timeout_sec) if args.timeout_sec is not None else None
    summary["resume_reused"] = bool(isinstance(old_summary, dict) and _summary_scope_matches(old_summary, resume_scope))
    summary["resume_scope_reset"] = bool(isinstance(old_summary, dict) and not _summary_scope_matches(old_summary, resume_scope))

    existing = _index_results(summary["results"])
    updated: dict[int, dict[str, Any]] = {task_id: row for task_id, row in existing.items() if task_id in set(selected)}
    skipped_completed = 0

    for idx, task_id in enumerate(selected, start=1):
        existing_row = updated.get(task_id)
        if _row_is_complete(existing_row, step_names=step_names):
            skipped_completed += 1
            summary["results"] = [updated[key] for key in sorted(updated.keys())]
            _rebuild_counts(summary)
            summary["remaining_tasks"] = max(0, len(selected) - int(summary.get("processed_tasks", 0)))
            summary["last_task_id"] = task_id
            summary["last_updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
            summary["skipped_completed_tasks"] = skipped_completed
            _write_json(summary_path, summary)
            continue

        print(f"[{idx}/{len(selected)}] run task {task_id}")
        row = {"task_id": task_id, "steps": []}
        step_map, resume_start_index, resumed_from_step, reused_successful_steps = _prepare_failed_row_resume(
            existing_row,
            step_names=step_names,
            resume_failed_task_from=str(args.resume_failed_task_from),
        )
        if resumed_from_step:
            row["resumed_from_step"] = resumed_from_step
            row["reused_successful_steps"] = list(reused_successful_steps)
        else:
            resume_start_index = 0
        failed_steps: list[str] = []

        for step_name, template in steps[resume_start_index:]:
            cmd = [part.format(id=task_id) for part in template]
            rc, stdout, stderr, retry_meta = _run_step_with_retry(
                root=root,
                cmd=cmd,
                step_name=step_name,
                delivery_profile=str(args.delivery_profile),
                explicit_timeout_sec=args.timeout_sec,
                llm_timeout_sec=args.llm_timeout_sec,
            )
            log_path = out_dir / f"t{task_id:04d}--{step_name}.log"
            attempts = retry_meta.get("attempts") or []
            if isinstance(attempts, list) and attempts:
                log_chunks: list[str] = []
                for attempt in attempts:
                    if not isinstance(attempt, dict):
                        continue
                    log_chunks.extend(
                        [
                            f"attempt: {int(attempt.get('attempt') or 0)}",
                            f"cmd: {' '.join(list(attempt.get('cmd') or []))}",
                            f"timeout_sec: {int(attempt.get('timeout_sec') or 0)}",
                            f"rc: {int(attempt.get('rc') or 0)}",
                            "--- stdout ---",
                            str(attempt.get("stdout") or ""),
                            "--- stderr ---",
                            str(attempt.get("stderr") or ""),
                            "",
                        ]
                    )
                log_body = "\n".join(log_chunks).rstrip() + "\n"
                snapshot_stdout = "\n".join(str(attempt.get("stdout") or "") for attempt in attempts if isinstance(attempt, dict))
                snapshot_stderr = "\n".join(str(attempt.get("stderr") or "") for attempt in attempts if isinstance(attempt, dict))
            else:
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
                snapshot_stdout = stdout
                snapshot_stderr = stderr
            log_path.write_text(log_body, encoding="utf-8")
            step_map[step_name] = {
                "step": step_name,
                "rc": rc,
                "log": str(log_path.relative_to(root)).replace("\\", "/"),
                "stdout_tail": stdout.strip().splitlines()[-1] if stdout.strip() else "",
                "stderr_tail": stderr.strip().splitlines()[-1] if stderr.strip() else "",
            }
            step_map[step_name].update(
                {
                    "retry_count": int(retry_meta.get("retry_count") or 0),
                    "retry_rcs": [int(item) for item in list(retry_meta.get("retry_rcs") or [])],
                    "attempt_count": int(retry_meta.get("attempt_count") or 1),
                }
            )
            step_map[step_name].update(
                _snapshot_inner_artifacts(
                    root=root,
                    wrapper_out_dir=out_dir,
                    task_id=task_id,
                    step_name=step_name,
                    stdout=snapshot_stdout,
                    stderr=snapshot_stderr,
                )
            )
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
        summary["skipped_completed_tasks"] = skipped_completed
        _write_json(summary_path, summary)

    _rebuild_counts(summary)
    summary["remaining_tasks"] = max(0, len(selected) - int(summary.get("processed_tasks", 0)))
    summary["status"] = "ok" if int(summary.get("failed_tasks", 0)) == 0 else "fail"
    summary["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    summary["skipped_completed_tasks"] = skipped_completed
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
