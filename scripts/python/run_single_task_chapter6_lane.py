#!/usr/bin/env python3
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


def _default_out_dir(task_id: str) -> Path:
    return _repo_root() / "logs" / "ci" / _today() / f"single-task-chapter6-task-{task_id}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _load_delivery_profiles() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[1] / "sc" / "config" / "delivery_profiles.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def resolve_profile_policy(
    delivery_profile: str | None,
    *,
    security_profile: str | None = None,
    fix_through: str | None = None,
) -> dict[str, str]:
    config = _load_delivery_profiles()
    profiles = config.get("profiles") if isinstance(config.get("profiles"), dict) else {}
    default_profile = str(config.get("default_profile") or "fast-ship").strip().lower() or "fast-ship"
    resolved_profile = str(delivery_profile or os.environ.get("DELIVERY_PROFILE") or default_profile).strip().lower()
    if resolved_profile not in profiles:
        resolved_profile = default_profile

    profile_payload = profiles.get(resolved_profile) if isinstance(profiles.get(resolved_profile), dict) else {}
    resolved_security = str(security_profile or profile_payload.get("security_profile_default") or "host-safe").strip().lower()
    if resolved_security not in {"host-safe", "strict"}:
        resolved_security = "host-safe"

    default_fix_through = "P0" if resolved_profile == "playable-ea" else "P1"
    resolved_fix_through = str(fix_through or default_fix_through).strip().upper() or default_fix_through
    if resolved_fix_through not in {"P0", "P1", "P2", "P3"}:
        resolved_fix_through = default_fix_through

    return {
        "delivery_profile": resolved_profile,
        "security_profile": resolved_security,
        "fix_through": resolved_fix_through,
        "execution_plan_policy": "warn" if resolved_profile == "playable-ea" else "draft",
        "red_verify": "auto" if resolved_profile == "standard" else "unit",
        "needs_fix_max_rounds": "1",
        "record_residual": "true" if resolved_fix_through in {"P0", "P1"} else "false",
    }


def build_resume_task_cmd(task_id: str) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/dev_cli.py",
        "resume-task",
        "--task-id",
        str(task_id),
        "--recommendation-only",
        "--recommendation-format",
        "json",
    ]


def build_chapter6_route_cmd(task_id: str, *, record_residual: bool) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/dev_cli.py",
        "chapter6-route",
        "--task-id",
        str(task_id),
        "--recommendation-only",
        "--recommendation-format",
        "json",
    ]
    if record_residual:
        cmd.append("--record-residual")
    return cmd


def build_check_tdd_plan_cmd(task_id: str, *, profile_policy: dict[str, str]) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/sc/check_tdd_execution_plan.py",
        "--task-id",
        str(task_id),
        "--tdd-stage",
        "red-first",
        "--verify",
        str(profile_policy["red_verify"]),
        "--execution-plan-policy",
        str(profile_policy["execution_plan_policy"]),
    ]


def build_red_first_cmd(task_id: str, *, profile_policy: dict[str, str], godot_bin: str) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/sc/llm_generate_tests_from_acceptance_refs.py",
        "--task-id",
        str(task_id),
        "--tdd-stage",
        "red-first",
        "--verify",
        str(profile_policy["red_verify"]),
    ]
    if str(profile_policy["red_verify"]) == "auto" and str(godot_bin).strip():
        cmd += ["--godot-bin", str(godot_bin)]
    return cmd


def build_build_tdd_cmd(task_id: str, *, stage: str, profile_policy: dict[str, str]) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/sc/build.py",
        "tdd",
        "--task-id",
        str(task_id),
        "--stage",
        str(stage),
        "--delivery-profile",
        str(profile_policy["delivery_profile"]),
        "--security-profile",
        str(profile_policy["security_profile"]),
    ]


def build_review_pipeline_cmd(task_id: str, *, profile_policy: dict[str, str], godot_bin: str) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/sc/run_review_pipeline.py",
        "--task-id",
        str(task_id),
        "--delivery-profile",
        str(profile_policy["delivery_profile"]),
        "--security-profile",
        str(profile_policy["security_profile"]),
    ]
    if str(godot_bin).strip():
        cmd += ["--godot-bin", str(godot_bin)]
    return cmd


def build_fork_review_pipeline_cmd(task_id: str, *, profile_policy: dict[str, str], godot_bin: str) -> list[str]:
    cmd = build_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=godot_bin)
    cmd.append("--fork")
    return cmd


def build_needs_fix_fast_cmd(task_id: str, *, profile_policy: dict[str, str]) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/sc/llm_review_needs_fix_fast.py",
        "--task-id",
        str(task_id),
        "--delivery-profile",
        str(profile_policy["delivery_profile"]),
        "--security-profile",
        str(profile_policy["security_profile"]),
        "--rerun-failing-only",
        "--max-rounds",
        str(profile_policy["needs_fix_max_rounds"]),
    ]


def build_local_hard_checks_preflight_cmd(*, profile_policy: dict[str, str]) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/dev_cli.py",
        "run-local-hard-checks-preflight",
        "--delivery-profile",
        str(profile_policy["delivery_profile"]),
    ]


def build_local_hard_checks_cmd(*, profile_policy: dict[str, str], godot_bin: str) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/dev_cli.py",
        "run-local-hard-checks",
        "--delivery-profile",
        str(profile_policy["delivery_profile"]),
    ]
    if str(godot_bin).strip():
        cmd += ["--godot-bin", str(godot_bin)]
    return cmd


def build_inspect_local_hard_checks_cmd() -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/dev_cli.py",
        "inspect-run",
        "--kind",
        "local-hard-checks",
        "--recommendation-only",
        "--recommendation-format",
        "json",
    ]


def _route_lane(route_payload: dict[str, Any] | None) -> str:
    return str((route_payload or {}).get("preferred_lane") or "").strip().lower() or "inspect-first"


def _normalize_action(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _split_compact_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text or text.lower() == "none":
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def _route_run_id(route_payload: dict[str, Any] | None) -> str:
    return str((route_payload or {}).get("run_id") or "").strip().lower()


def _route_latest_reason(route_payload: dict[str, Any] | None) -> str:
    return str((route_payload or {}).get("latest_reason") or "").strip().lower()


def _route_recommended_action(route_payload: dict[str, Any] | None) -> str:
    return _normalize_action((route_payload or {}).get("recommended_action"))


def _route_next_action(route_payload: dict[str, Any] | None) -> str:
    route = route_payload or {}
    hints = route.get("chapter6_hints")
    if isinstance(hints, dict):
        value = hints.get("next_action")
        if value:
            return _normalize_action(value)
    return _normalize_action(route.get("chapter6_next_action"))


def _route_blocked_by(route_payload: dict[str, Any] | None) -> str:
    route = route_payload or {}
    hints = route.get("chapter6_hints")
    if isinstance(hints, dict):
        value = hints.get("blocked_by")
        if value:
            return str(value).strip().lower()
    return str(route.get("blocked_by") or "").strip().lower()


def _initial_route_has_recovery_signal(route_payload: dict[str, Any] | None) -> bool:
    route = route_payload or {}
    return bool(_route_run_id(route) not in {"", "n/a"} or _route_latest_reason(route) not in {"", "n/a", "none"})


def _route_is_blocking(route_payload: dict[str, Any] | None) -> bool:
    return _route_lane(route_payload) in {"repo-noise-stop", "fix-deterministic"}


def _route_stop_reason(route_payload: dict[str, Any] | None) -> str:
    lane = _route_lane(route_payload)
    if lane in {"repo-noise-stop", "fix-deterministic", "record-residual"}:
        return lane
    blocked_by = _route_blocked_by(route_payload)
    latest_reason = _route_latest_reason(route_payload)
    if blocked_by == "artifact_integrity" or latest_reason == "planned_only_incomplete":
        return "artifact_integrity"
    return ""


def _resume_approval(resume_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = resume_payload or {}
    approval = payload.get("approval")
    if isinstance(approval, dict):
        return dict(approval)
    status = str(payload.get("approval_status") or "").strip()
    required_action = str(payload.get("approval_required_action") or "fork").strip()
    if not status:
        return {}
    return {
        "required_action": required_action,
        "status": status,
        "recommended_action": str(payload.get("approval_recommended_action") or "").strip(),
        "allowed_actions": _split_compact_items(payload.get("approval_allowed_actions")),
        "blocked_actions": _split_compact_items(payload.get("approval_blocked_actions")),
    }


def _resume_recommended_action(resume_payload: dict[str, Any] | None) -> str:
    return _normalize_action((resume_payload or {}).get("recommended_action"))


def _resume_next_action(resume_payload: dict[str, Any] | None) -> str:
    payload = resume_payload or {}
    hints = payload.get("chapter6_hints")
    if isinstance(hints, dict):
        value = hints.get("next_action")
        if value:
            return _normalize_action(value)
    return _normalize_action(payload.get("chapter6_next_action"))


def _payload_forbidden_commands(*payloads: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        value = payload.get("forbidden_commands")
        items = _split_compact_items(value)
        for item in items:
            if item not in out:
                out.append(item)
    return out


def _normalize_cmd_text(cmd: list[str] | str) -> str:
    if isinstance(cmd, list):
        text = " ".join(str(item) for item in cmd)
    else:
        text = str(cmd or "")
    return " ".join(text.strip().lower().split())


def _command_is_forbidden(cmd: list[str], *payloads: dict[str, Any] | None) -> bool:
    normalized_cmd = _normalize_cmd_text(cmd)
    if not normalized_cmd:
        return False
    return any(_normalize_cmd_text(item) == normalized_cmd for item in _payload_forbidden_commands(*payloads))


def _guard_forbidden_command(cmd: list[str], *payloads: dict[str, Any] | None) -> str:
    return "forbidden_command" if _command_is_forbidden(cmd, *payloads) else ""


def _decide_initial_action(
    *,
    resume_payload: dict[str, Any] | None,
    initial_route: dict[str, Any] | None,
    review_pipeline_cmd: list[str],
) -> dict[str, str]:
    approval_stop_reason = _approval_stop_reason(resume_payload)
    if approval_stop_reason:
        return {"mode": "blocked", "reason": approval_stop_reason}

    initial_stop_reason = _route_stop_reason(initial_route)
    if initial_stop_reason and _initial_route_has_recovery_signal(initial_route):
        return {"mode": "blocked", "reason": initial_stop_reason}

    if _initial_route_has_recovery_signal(initial_route):
        if _approval_requires_fork(resume_payload):
            return {"mode": "fork", "reason": ""}
        if _route_requires_needs_fix(initial_route, resume_payload=resume_payload):
            return {"mode": "needs-fix-fast", "reason": ""}
        if _route_lane(initial_route) == "inspect-first":
            return {"mode": "blocked", "reason": "inspect-first"}

    forbidden_reason = _guard_forbidden_command(review_pipeline_cmd, resume_payload, initial_route)
    if forbidden_reason:
        return {"mode": "blocked", "reason": forbidden_reason}

    return {"mode": "full", "reason": ""}


def _decide_followup_action(route_payload: dict[str, Any] | None) -> dict[str, str]:
    stop_reason = _route_stop_reason(route_payload)
    if stop_reason:
        return {"mode": "blocked", "reason": stop_reason}
    if _route_requires_needs_fix(route_payload):
        return {"mode": "needs-fix-fast", "reason": ""}
    return {"mode": "continue", "reason": ""}


def _approval_stop_reason(resume_payload: dict[str, Any] | None) -> str:
    approval = _resume_approval(resume_payload)
    if _normalize_action(approval.get("required_action")) != "fork":
        return ""
    status = _normalize_action(approval.get("status"))
    if status == "pending":
        return "approval_pending"
    if status in {"invalid", "mismatched"}:
        return f"approval_{status}"
    return ""


def _approval_requires_fork(resume_payload: dict[str, Any] | None) -> bool:
    approval = _resume_approval(resume_payload)
    return _normalize_action(approval.get("required_action")) == "fork" and _normalize_action(approval.get("status")) == "approved"


def _route_requires_needs_fix(route_payload: dict[str, Any] | None, *, resume_payload: dict[str, Any] | None = None) -> bool:
    if _route_lane(route_payload) == "run-6.8":
        return True
    actions = {
        _route_recommended_action(route_payload),
        _route_next_action(route_payload),
        _resume_recommended_action(resume_payload),
        _resume_next_action(resume_payload),
    }
    return "needs-fix-fast" in actions


def _build_step(name: str, cmd: list[str]) -> dict[str, Any]:
    return {"name": name, "cmd": list(cmd)}


def build_execution_plan(
    *,
    task_id: str,
    godot_bin: str,
    profile_policy: dict[str, str],
    resume_payload: dict[str, Any] | None,
    initial_route: dict[str, Any],
    post_review_route: dict[str, Any],
    final_route: dict[str, Any],
) -> dict[str, Any]:
    record_residual = str(profile_policy.get("record_residual") or "").strip().lower() == "true"
    review_pipeline_cmd = build_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=godot_bin)
    steps: list[dict[str, Any]] = [
        _build_step("resume-task", build_resume_task_cmd(task_id)),
        _build_step("chapter6-route-initial", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
    ]
    initial_decision = _decide_initial_action(
        resume_payload=resume_payload,
        initial_route=initial_route,
        review_pipeline_cmd=review_pipeline_cmd,
    )
    if initial_decision["mode"] == "blocked":
        return {
            "status": "blocked",
            "stop_reason": initial_decision["reason"],
            "steps": steps,
        }

    if initial_decision["mode"] == "fork":
        fork_cmd = build_fork_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=godot_bin)
        forbidden_reason = _guard_forbidden_command(fork_cmd, resume_payload, initial_route)
        if forbidden_reason:
            return {
                "status": "blocked",
                "stop_reason": forbidden_reason,
                "steps": steps,
            }
        steps.extend(
            [
                _build_step("fork-review-pipeline", fork_cmd),
                _build_step("chapter6-route-post-fork", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
            ]
        )
        post_fork_decision = _decide_followup_action(post_review_route)
        if post_fork_decision["mode"] == "blocked":
            return {
                "status": "blocked",
                "stop_reason": post_fork_decision["reason"],
                "steps": steps,
            }
        if post_fork_decision["mode"] == "needs-fix-fast":
            needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
            forbidden_reason = _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route, post_review_route)
            if forbidden_reason:
                return {
                    "status": "blocked",
                    "stop_reason": forbidden_reason,
                    "steps": steps,
                }
            steps.extend(
                [
                    _build_step("needs-fix-fast", needs_fix_cmd),
                    _build_step("chapter6-route-post-needs-fix", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
                ]
            )
            final_decision = _decide_followup_action(final_route)
            if final_decision["mode"] != "continue":
                return {
                    "status": "blocked",
                    "stop_reason": final_decision["reason"] or _route_lane(final_route),
                    "steps": steps,
                }
        steps.extend(
            [
                _build_step("local-hard-checks-preflight", build_local_hard_checks_preflight_cmd(profile_policy=profile_policy)),
                _build_step("local-hard-checks", build_local_hard_checks_cmd(profile_policy=profile_policy, godot_bin=godot_bin)),
                _build_step("inspect-local-hard-checks", build_inspect_local_hard_checks_cmd()),
            ]
        )
        return {
            "status": "planned",
            "stop_reason": "",
            "steps": steps,
        }

    if initial_decision["mode"] == "needs-fix-fast":
        needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
        forbidden_reason = _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route)
        if forbidden_reason:
            return {
                "status": "blocked",
                "stop_reason": forbidden_reason,
                "steps": steps,
            }
        steps.extend(
            [
                _build_step("needs-fix-fast", needs_fix_cmd),
                _build_step("chapter6-route-post-needs-fix", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
            ]
        )
        final_decision = _decide_followup_action(final_route)
        if final_decision["mode"] == "continue":
            steps.extend(
                [
                    _build_step("local-hard-checks-preflight", build_local_hard_checks_preflight_cmd(profile_policy=profile_policy)),
                    _build_step("local-hard-checks", build_local_hard_checks_cmd(profile_policy=profile_policy, godot_bin=godot_bin)),
                    _build_step("inspect-local-hard-checks", build_inspect_local_hard_checks_cmd()),
            ]
        )
        else:
            return {
                "status": "blocked",
                "stop_reason": final_decision["reason"] or _route_lane(final_route),
                "steps": steps,
            }
        return {
            "status": "planned",
            "stop_reason": "",
            "steps": steps,
        }

    steps.extend(
        [
            _build_step("check-tdd-plan", build_check_tdd_plan_cmd(task_id, profile_policy=profile_policy)),
            _build_step("red-first", build_red_first_cmd(task_id, profile_policy=profile_policy, godot_bin=godot_bin)),
            _build_step("green", build_build_tdd_cmd(task_id, stage="green", profile_policy=profile_policy)),
            _build_step("refactor", build_build_tdd_cmd(task_id, stage="refactor", profile_policy=profile_policy)),
            _build_step("review-pipeline", review_pipeline_cmd),
            _build_step("chapter6-route-post-review", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
        ]
    )

    post_review_decision = _decide_followup_action(post_review_route)
    if post_review_decision["mode"] == "needs-fix-fast":
        needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
        forbidden_reason = _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route, post_review_route)
        if forbidden_reason:
            return {
                "status": "blocked",
                "stop_reason": forbidden_reason,
                "steps": steps,
            }
        steps.extend(
            [
                _build_step("needs-fix-fast", needs_fix_cmd),
                _build_step("chapter6-route-post-needs-fix", build_chapter6_route_cmd(task_id, record_residual=record_residual)),
            ]
        )
        final_decision = _decide_followup_action(final_route)
        if final_decision["mode"] != "continue":
            return {
                "status": "blocked",
                "stop_reason": final_decision["reason"] or _route_lane(final_route),
                "steps": steps,
            }
    elif post_review_decision["mode"] == "blocked":
        return {
            "status": "blocked",
            "stop_reason": post_review_decision["reason"],
            "steps": steps,
        }

    steps.extend(
        [
            _build_step("local-hard-checks-preflight", build_local_hard_checks_preflight_cmd(profile_policy=profile_policy)),
            _build_step("local-hard-checks", build_local_hard_checks_cmd(profile_policy=profile_policy, godot_bin=godot_bin)),
            _build_step("inspect-local-hard-checks", build_inspect_local_hard_checks_cmd()),
        ]
    )
    return {
        "status": "planned",
        "stop_reason": "",
        "steps": steps,
    }


def _run_cmd(cmd: list[str], *, cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""


def _write_step_log(out_dir: Path, *, name: str, cmd: list[str], stdout: str, stderr: str, rc: int) -> str:
    log_path = out_dir / f"{name}.log"
    log_path.write_text(
        "\n".join(
            [
                f"cmd: {' '.join(cmd)}",
                f"rc: {int(rc)}",
                "--- stdout ---",
                stdout,
                "--- stderr ---",
                stderr,
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return str(log_path).replace("\\", "/")


def _parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass

    # Some dev_cli commands print a JSON line plus extra diagnostics lines.
    # Prefer the first/last JSON object line if full-blob parsing fails.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for candidate in lines:
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    for candidate in reversed(lines):
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _run_json_step(out_dir: Path, *, name: str, cmd: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    rc, stdout, stderr = _run_cmd(cmd, cwd=_repo_root())
    log_path = _write_step_log(out_dir, name=name, cmd=cmd, stdout=stdout, stderr=stderr, rc=rc)
    step = {
        "name": name,
        "cmd": list(cmd),
        "rc": rc,
        "stdout_tail": stdout.strip().splitlines()[-1] if stdout.strip() else "",
        "stderr_tail": stderr.strip().splitlines()[-1] if stderr.strip() else "",
        "log": log_path,
    }
    payload = _parse_json_stdout(stdout) if rc == 0 else {}
    return step, payload


def _run_plain_step(out_dir: Path, *, name: str, cmd: list[str]) -> dict[str, Any]:
    rc, stdout, stderr = _run_cmd(cmd, cwd=_repo_root())
    log_path = _write_step_log(out_dir, name=name, cmd=cmd, stdout=stdout, stderr=stderr, rc=rc)
    return {
        "name": name,
        "cmd": list(cmd),
        "rc": rc,
        "stdout_tail": stdout.strip().splitlines()[-1] if stdout.strip() else "",
        "stderr_tail": stderr.strip().splitlines()[-1] if stderr.strip() else "",
        "log": log_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Chapter 6 single-task orchestrator.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--godot-bin", default=str(os.environ.get("GODOT_BIN") or ""))
    parser.add_argument("--delivery-profile", default=str(os.environ.get("DELIVERY_PROFILE") or "fast-ship"))
    parser.add_argument("--security-profile", default="")
    parser.add_argument("--fix-through", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--self-check", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    task_id = str(args.task_id).strip()
    out_dir = Path(str(args.out_dir).strip()) if str(args.out_dir).strip() else _default_out_dir(task_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_policy = resolve_profile_policy(
        str(args.delivery_profile),
        security_profile=str(args.security_profile),
        fix_through=str(args.fix_through),
    )

    if bool(args.self_check):
        placeholder_route = {
            "preferred_lane": "inspect-first",
            "run_id": "n/a",
            "latest_reason": "n/a",
            "blocked_by": "n/a",
        }
        plan = build_execution_plan(
            task_id=task_id,
            godot_bin=str(args.godot_bin),
            profile_policy=profile_policy,
            resume_payload={},
            initial_route=placeholder_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )
        payload = {
            "cmd": "run-single-task-chapter6",
            "task_id": task_id,
            "status": "ok",
            "profile_policy": profile_policy,
            "plan_status": plan["status"],
            "steps": plan["steps"],
            "out_dir": str(out_dir).replace("\\", "/"),
        }
        _write_json(out_dir / "summary.json", payload)
        print(
            "SINGLE_TASK_CHAPTER6_SELF_CHECK "
            f"status=ok task={task_id} profile={profile_policy['delivery_profile']} "
            f"out={str((out_dir / 'summary.json')).replace('\\', '/')}"
        )
        return 0

    summary: dict[str, Any] = {
        "cmd": "run-single-task-chapter6",
        "task_id": task_id,
        "status": "running",
        "profile_policy": profile_policy,
        "out_dir": str(out_dir).replace("\\", "/"),
        "steps": [],
        "stop_reason": "",
    }

    resume_step, resume_payload = _run_json_step(out_dir, name="resume-task", cmd=build_resume_task_cmd(task_id))
    summary["steps"].append(resume_step)
    summary["resume"] = resume_payload
    if int(resume_step["rc"]) != 0:
        summary["status"] = "fail"
        summary["stop_reason"] = "resume-task"
        _write_json(out_dir / "summary.json", summary)
        print(f"SINGLE_TASK_CHAPTER6 status=fail task={task_id} stop=resume-task")
        return 1

    record_residual = str(profile_policy["record_residual"]).strip().lower() == "true"
    initial_route_step, initial_route = _run_json_step(
        out_dir,
        name="chapter6-route-initial",
        cmd=build_chapter6_route_cmd(task_id, record_residual=record_residual),
    )
    summary["steps"].append(initial_route_step)
    summary["initial_route"] = initial_route
    if int(initial_route_step["rc"]) != 0:
        summary["status"] = "fail"
        summary["stop_reason"] = "chapter6-route-initial"
        _write_json(out_dir / "summary.json", summary)
        print(f"SINGLE_TASK_CHAPTER6 status=fail task={task_id} stop=chapter6-route-initial")
        return 1

    plan = build_execution_plan(
        task_id=task_id,
        godot_bin=str(args.godot_bin),
        profile_policy=profile_policy,
        resume_payload=resume_payload,
        initial_route=initial_route,
        post_review_route={"preferred_lane": "inspect-first"},
        final_route={"preferred_lane": "inspect-first"},
    )
    summary["planned_steps"] = [step["name"] for step in plan["steps"]]
    if plan["status"] == "blocked":
        summary["status"] = "blocked"
        summary["stop_reason"] = str(plan["stop_reason"])
        _write_json(out_dir / "summary.json", summary)
        print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={plan['stop_reason']}")
        return 1

    def _run_required(name: str, cmd: list[str]) -> bool:
        step = _run_plain_step(out_dir, name=name, cmd=cmd)
        summary["steps"].append(step)
        if int(step["rc"]) != 0:
            summary["status"] = "fail"
            summary["stop_reason"] = name
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=fail task={task_id} stop={name}")
            return False
        return True

    def _run_route(name: str) -> dict[str, Any] | None:
        step, payload = _run_json_step(
            out_dir,
            name=name,
            cmd=build_chapter6_route_cmd(task_id, record_residual=record_residual),
        )
        summary["steps"].append(step)
        summary[name.replace("-", "_")] = payload
        if int(step["rc"]) != 0:
            summary["status"] = "fail"
            summary["stop_reason"] = name
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=fail task={task_id} stop={name}")
            return None
        return payload

    initial_decision = _decide_initial_action(
        resume_payload=resume_payload,
        initial_route=initial_route,
        review_pipeline_cmd=build_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=str(args.godot_bin)),
    )

    if initial_decision["mode"] == "fork":
        fork_cmd = build_fork_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=str(args.godot_bin))
        if _guard_forbidden_command(fork_cmd, resume_payload, initial_route):
            summary["status"] = "blocked"
            summary["stop_reason"] = "forbidden_command"
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
            return 1
        if not _run_required("fork-review-pipeline", fork_cmd):
            return 1
        post_fork_route = _run_route("chapter6-route-post-fork")
        if post_fork_route is None:
            return 1
        post_fork_decision = _decide_followup_action(post_fork_route)
        if post_fork_decision["mode"] == "blocked":
            summary["status"] = "blocked"
            summary["stop_reason"] = post_fork_decision["reason"]
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
            return 1
        if post_fork_decision["mode"] == "needs-fix-fast":
            needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
            if _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route, post_fork_route):
                summary["status"] = "blocked"
                summary["stop_reason"] = "forbidden_command"
                _write_json(out_dir / "summary.json", summary)
                print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
                return 1
            if not _run_required("needs-fix-fast", needs_fix_cmd):
                return 1
            final_route = _run_route("chapter6-route-post-needs-fix")
            if final_route is None:
                return 1
            final_decision = _decide_followup_action(final_route)
            if final_decision["mode"] != "continue":
                summary["status"] = "blocked"
                summary["stop_reason"] = final_decision["reason"] or _route_lane(final_route)
                _write_json(out_dir / "summary.json", summary)
                print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
                return 1
    elif initial_decision["mode"] == "needs-fix-fast":
        needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
        if _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route):
            summary["status"] = "blocked"
            summary["stop_reason"] = "forbidden_command"
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
            return 1
        if not _run_required("needs-fix-fast", needs_fix_cmd):
            return 1
        final_route = _run_route("chapter6-route-post-needs-fix")
        if final_route is None:
            return 1
        final_decision = _decide_followup_action(final_route)
        if final_decision["mode"] != "continue":
            summary["status"] = "blocked"
            summary["stop_reason"] = final_decision["reason"] or _route_lane(final_route)
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
            return 1
    elif initial_decision["mode"] == "full":
        full_path_steps = [
            ("check-tdd-plan", build_check_tdd_plan_cmd(task_id, profile_policy=profile_policy)),
            ("red-first", build_red_first_cmd(task_id, profile_policy=profile_policy, godot_bin=str(args.godot_bin))),
            ("green", build_build_tdd_cmd(task_id, stage="green", profile_policy=profile_policy)),
            ("refactor", build_build_tdd_cmd(task_id, stage="refactor", profile_policy=profile_policy)),
            ("review-pipeline", build_review_pipeline_cmd(task_id, profile_policy=profile_policy, godot_bin=str(args.godot_bin))),
        ]
        for name, cmd in full_path_steps:
            if _guard_forbidden_command(cmd, resume_payload, initial_route):
                summary["status"] = "blocked"
                summary["stop_reason"] = "forbidden_command"
                _write_json(out_dir / "summary.json", summary)
                print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
                return 1
            if not _run_required(name, cmd):
                return 1
        post_review_route = _run_route("chapter6-route-post-review")
        if post_review_route is None:
            return 1
        post_review_decision = _decide_followup_action(post_review_route)
        if post_review_decision["mode"] == "blocked":
            summary["status"] = "blocked"
            summary["stop_reason"] = post_review_decision["reason"]
            _write_json(out_dir / "summary.json", summary)
            print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
            return 1
        if post_review_decision["mode"] == "needs-fix-fast":
            needs_fix_cmd = build_needs_fix_fast_cmd(task_id, profile_policy=profile_policy)
            if _guard_forbidden_command(needs_fix_cmd, resume_payload, initial_route, post_review_route):
                summary["status"] = "blocked"
                summary["stop_reason"] = "forbidden_command"
                _write_json(out_dir / "summary.json", summary)
                print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
                return 1
            if not _run_required("needs-fix-fast", needs_fix_cmd):
                return 1
            final_route = _run_route("chapter6-route-post-needs-fix")
            if final_route is None:
                return 1
            final_decision = _decide_followup_action(final_route)
            if final_decision["mode"] != "continue":
                summary["status"] = "blocked"
                summary["stop_reason"] = final_decision["reason"] or _route_lane(final_route)
                _write_json(out_dir / "summary.json", summary)
                print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
                return 1
    else:
        summary["status"] = "blocked"
        summary["stop_reason"] = initial_decision["reason"] or "inspect-first"
        _write_json(out_dir / "summary.json", summary)
        print(f"SINGLE_TASK_CHAPTER6 status=blocked task={task_id} stop={summary['stop_reason']}")
        return 1

    if not _run_required("local-hard-checks-preflight", build_local_hard_checks_preflight_cmd(profile_policy=profile_policy)):
        return 1
    if not _run_required("local-hard-checks", build_local_hard_checks_cmd(profile_policy=profile_policy, godot_bin=str(args.godot_bin))):
        return 1
    inspect_step, inspect_payload = _run_json_step(out_dir, name="inspect-local-hard-checks", cmd=build_inspect_local_hard_checks_cmd())
    summary["steps"].append(inspect_step)
    summary["inspect_local_hard_checks"] = inspect_payload
    if int(inspect_step["rc"]) != 0:
        summary["status"] = "fail"
        summary["stop_reason"] = "inspect-local-hard-checks"
        _write_json(out_dir / "summary.json", summary)
        print(f"SINGLE_TASK_CHAPTER6 status=fail task={task_id} stop=inspect-local-hard-checks")
        return 1

    summary["status"] = "ok"
    _write_json(out_dir / "summary.json", summary)
    print(f"SINGLE_TASK_CHAPTER6 status=ok task={task_id} out={str((out_dir / 'summary.json')).replace('\\', '/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
