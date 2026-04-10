#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


def candidate_commands(task_id: str, latest: str) -> dict[str, str]:
    inspect_cmd = ["py", "-3", "scripts/python/dev_cli.py", "inspect-run", "--kind", "pipeline"]
    latest_value = str(latest or "").strip()
    task_value = str(task_id or "").strip()
    if latest_value:
        inspect_cmd += ["--latest", latest_value]
    elif task_value:
        inspect_cmd += ["--task-id", task_value]
    commands = {
        "inspect": " ".join(inspect_cmd),
        "resume": "",
        "fork": "",
        "rerun": "",
        "needs_fix_fast": "",
    }
    if task_value:
        commands["resume"] = f"py -3 scripts/sc/run_review_pipeline.py --task-id {task_value} --resume"
        commands["fork"] = f"py -3 scripts/sc/run_review_pipeline.py --task-id {task_value} --fork"
        commands["rerun"] = f"py -3 scripts/sc/run_review_pipeline.py --task-id {task_value}"
        commands["needs_fix_fast"] = (
            f"py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id {task_value} "
            "--delivery-profile fast-ship --rerun-failing-only --max-rounds 1"
        )
    return commands


def recommended_command(
    recommended_action: str,
    commands: dict[str, str],
    chapter6_hints: dict[str, Any],
) -> str:
    hinted_action = str(chapter6_hints.get("next_action") or "").strip().lower().replace("_", "-")
    action = hinted_action or str(recommended_action or "").strip().lower().replace("_", "-")
    if action == "needs-fix-fast":
        return str(commands.get("needs_fix_fast") or "").strip()
    if action in {"resume", "fix-and-resume"}:
        return str(commands.get("resume") or "").strip()
    if action == "fork":
        return str(commands.get("fork") or "").strip()
    if action == "rerun":
        return str(commands.get("rerun") or "").strip()
    if action == "inspect":
        return str(commands.get("inspect") or "").strip()
    return ""


def forbidden_commands(
    *,
    recommended_action: str,
    commands: dict[str, str],
    chapter6_hints: dict[str, Any],
) -> list[str]:
    forbidden: list[str] = []
    action = str(recommended_action or "").strip().lower().replace("_", "-")
    if bool(chapter6_hints.get("rerun_forbidden")) and str(commands.get("rerun") or "").strip():
        forbidden.append(str(commands.get("rerun") or "").strip())
    if action == "needs-fix-fast" and str(commands.get("resume") or "").strip():
        forbidden.append(str(commands.get("resume") or "").strip())
    unique: list[str] = []
    for item in forbidden:
        if item and item not in unique:
            unique.append(item)
    return unique


def chapter6_stop_loss_note(chapter6_hints: dict[str, Any], latest_summary_signals: dict[str, Any]) -> str:
    blocked_by = str(chapter6_hints.get("blocked_by") or "").strip().lower()
    reason = str(latest_summary_signals.get("reason") or "").strip()
    artifact_integrity_kind = str(latest_summary_signals.get("artifact_integrity_kind") or "").strip().lower()
    if not blocked_by and reason.startswith("rerun_blocked:chapter6_route_"):
        blocked_by = "rerun_guard"
    if not blocked_by and reason.startswith("rerun_blocked:deterministic_green_llm_not_clean"):
        blocked_by = "rerun_guard"
    elif not blocked_by and reason.startswith("rerun_blocked:repeat_review_needs_fix"):
        blocked_by = "rerun_guard"
    elif not blocked_by and reason.startswith("rerun_blocked:repeat_deterministic_failure"):
        blocked_by = "rerun_guard"
    elif not blocked_by and (
        reason.startswith("rerun_blocked:dirty_worktree_unsafe_paths_ceiling")
        or reason.startswith("rerun_blocked:dirty_worktree_changed_paths_ceiling")
        or reason.startswith("rerun_blocked:profile_drift_change_scope_ceiling")
    ):
        blocked_by = "rerun_guard"
    elif not blocked_by and (reason == "planned_only_incomplete" or artifact_integrity_kind == "planned_only_incomplete"):
        blocked_by = "artifact_integrity"
    if blocked_by == "rerun_guard":
        if reason.startswith("rerun_blocked:chapter6_route_run_6_8"):
            return "The latest Chapter 6 route already proved deterministic evidence is sufficient; continue with needs-fix-fast instead of reopening a full 6.7."
        if reason.startswith("rerun_blocked:chapter6_route_fix_deterministic"):
            return "The latest Chapter 6 route says a deterministic root cause still blocks progress; fix that first, then resume."
        if reason.startswith("rerun_blocked:chapter6_route_repo_noise_stop"):
            return "The latest Chapter 6 route classified this failure as repo noise or process contention; inspect the artifacts and environment before paying for another rerun."
        if reason.startswith("rerun_blocked:chapter6_route_inspect_first"):
            return "The latest Chapter 6 route requires inspection first; read the current artifacts before choosing 6.7 or 6.8."
        if reason.startswith("rerun_blocked:deterministic_green_llm_not_clean"):
            return "Deterministic evidence is already green; do not pay for another full 6.7. Continue with 6.8 or needs-fix-fast."
        if reason.startswith("rerun_blocked:repeat_review_needs_fix"):
            return "Recent reviewer-only reruns already repeated the same Needs Fix family; switch to needs-fix-fast or record the remaining findings instead of reopening 6.7."
        if reason.startswith("rerun_blocked:repeat_deterministic_failure"):
            return "Recent deterministic failures already repeated with the same fingerprint; inspect and fix the root cause before rerunning 6.7."
        if (
            reason.startswith("rerun_blocked:dirty_worktree_unsafe_paths_ceiling")
            or reason.startswith("rerun_blocked:dirty_worktree_changed_paths_ceiling")
            or reason.startswith("rerun_blocked:profile_drift_change_scope_ceiling")
        ):
            return "Current changes exceed the standard Chapter 6 safe scope; shrink the dirty worktree or inspect/reset the drift before paying for another full 6.7."
        return "A rerun guard is active; check the latest diagnostics before paying for another full rerun."
    if blocked_by == "llm_retry_stop_loss":
        return "This run already stopped after the first costly llm timeout; continue with the narrow llm-only closure path instead of reopening deterministic steps."
    if blocked_by == "sc_test_retry_stop_loss":
        return "The pipeline already proved the unit root cause and stopped the same-run retry; fix the unit issue first, then start a fresh run."
    if blocked_by == "waste_signals":
        return "Unit failure was already known before more expensive engine-lane work continued; fix the unit/root cause before paying that cost again."
    if blocked_by == "recent_failure_summary":
        return "Recent runs already repeat the same failure family; inspect the repeated fingerprint and fix the root cause before rerunning 6.7."
    if blocked_by == "artifact_integrity":
        if reason == "planned_only_incomplete" or artifact_integrity_kind == "planned_only_incomplete":
            return "The latest bundle is a planned-only terminal run, not a real completed producer run; inspect it only for evidence and start a fresh real run before reopening Chapter 6."
        return "The latest recovery bundle is incomplete or stale; inspect the evidence only, then start a fresh real run instead of resuming from this pointer."
    return ""
