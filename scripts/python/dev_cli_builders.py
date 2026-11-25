#!/usr/bin/env python3
"""Command builders shared by dev_cli entrypoints."""

from __future__ import annotations

import sys
from pathlib import Path


DEFAULT_GATE_BUNDLE_TASK_FILES = [
    ".taskmaster/tasks/tasks_back.json",
    ".taskmaster/tasks/tasks_gameplay.json",
]


def build_gate_bundle_hard_cmd(
    *,
    delivery_profile: str,
    task_files: list[str],
    out_dir: str,
    run_id: str,
) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/run_gate_bundle.py",
        "--mode",
        "hard",
        "--task-files",
        *task_files,
    ]
    if delivery_profile:
        cmd += ["--delivery-profile", delivery_profile]
    if run_id:
        cmd += ["--run-id", run_id]
    if out_dir:
        cmd += ["--out-dir", out_dir]
    return cmd


def build_legacy_ci_pipeline_cmd(
    *,
    solution: str,
    configuration: str,
    godot_bin: str,
) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/ci_pipeline.py",
        "all",
        "--solution",
        solution,
        "--configuration",
        configuration,
        "--godot-bin",
        godot_bin,
        "--build-solutions",
    ]


def build_run_dotnet_cmd(*, solution: str, configuration: str) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/run_dotnet.py",
        "--solution",
        solution,
        "--configuration",
        configuration,
    ]


def build_quality_gates_cmd(
    *,
    solution: str,
    configuration: str,
    build_solutions: bool,
    godot_bin: str,
    delivery_profile: str,
    task_files: list[str],
    out_dir: str,
    run_id: str,
    gdunit_hard: bool,
    smoke: bool,
) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/quality_gates.py",
        "all",
    ]
    if solution:
        cmd += ["--solution", solution]
    if configuration:
        cmd += ["--configuration", configuration]
    if build_solutions:
        cmd.append("--build-solutions")
    if godot_bin:
        cmd += ["--godot-bin", godot_bin]
    if delivery_profile:
        cmd += ["--delivery-profile", delivery_profile]
    for item in task_files:
        cmd += ["--task-file", item]
    if out_dir:
        cmd += ["--out-dir", out_dir]
    if run_id:
        cmd += ["--run-id", run_id]
    if gdunit_hard:
        cmd.append("--gdunit-hard")
    if smoke:
        cmd.append("--smoke")
    return cmd


def build_run_gdunit_hard_cmd(*, godot_bin: str, report_dir: str) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/run_gdunit.py",
        "--prewarm",
        "--godot-bin",
        godot_bin,
        "--project",
        "Tests.Godot",
        "--add",
        "tests/Adapters/Config",
        "--add",
        "tests/Security/Hard",
        "--timeout-sec",
        "300",
        "--rd",
        report_dir,
    ]


def build_run_gdunit_full_cmd(*, godot_bin: str) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/run_gdunit.py",
        "--prewarm",
        "--godot-bin",
        godot_bin,
        "--project",
        "Tests.Godot",
        "--add",
        "tests/Adapters",
        "--add",
        "tests/Security/Hard",
        "--add",
        "tests/Integration",
        "--add",
        "tests/UI",
        "--timeout-sec",
        "600",
        "--rd",
        "logs/e2e/dev-cli/gdunit-full",
    ]


def build_preflight_cmd(*, test_project: str, configuration: str) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/preflight.py",
        "--test-project",
        test_project,
        "--configuration",
        configuration,
    ]


def build_smoke_strict_cmd(*, godot_bin: str, timeout_sec: int) -> list[str]:
    return [
        "py",
        "-3",
        "scripts/python/smoke_headless.py",
        "--godot-bin",
        godot_bin,
        "--project-path",
        ".",
        "--scene",
        "res://Game.Godot/Scenes/Main.tscn",
        "--timeout-sec",
        str(timeout_sec),
        "--strict",
    ]


def build_run_prototype_tdd_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/run_prototype_tdd.py",
        "--slug",
        args.slug,
        "--stage",
        args.stage,
    ]
    if args.expect:
        cmd += ["--expect", args.expect]
    if args.prototype_dir:
        cmd += ["--prototype-dir", args.prototype_dir]
    if args.record_path:
        cmd += ["--record-path", args.record_path]
    if args.skip_record:
        cmd.append("--skip-record")
    if args.owner:
        cmd += ["--owner", args.owner]
    for item in args.related_task_id:
        cmd += ["--related-task-id", item]
    if args.hypothesis:
        cmd += ["--hypothesis", args.hypothesis]
    if args.core_player_fantasy:
        cmd += ["--core-player-fantasy", args.core_player_fantasy]
    if args.minimum_playable_loop:
        cmd += ["--minimum-playable-loop", args.minimum_playable_loop]
    if args.game_feature:
        cmd += ["--game-feature", args.game_feature]
    if args.core_gameplay_loop:
        cmd += ["--core-gameplay-loop", args.core_gameplay_loop]
    if args.win_fail_conditions:
        cmd += ["--win-fail-conditions", args.win_fail_conditions]
    if args.game_type_specific_game_type:
        cmd += ["--game-type-specific-game-type", args.game_type_specific_game_type]
    if args.game_type_specific_guide_path:
        cmd += ["--game-type-specific-guide-path", args.game_type_specific_guide_path]
    for item in args.game_type_specific_section:
        cmd += ["--game-type-specific-section", item]
    for item in args.scope_in:
        cmd += ["--scope-in", item]
    for item in args.scope_out:
        cmd += ["--scope-out", item]
    for item in args.success_criteria:
        cmd += ["--success-criteria", item]
    for item in args.evidence:
        cmd += ["--evidence", item]
    if args.next_step:
        cmd += ["--next-step", args.next_step]
    if args.create_record_only:
        cmd.append("--create-record-only")
    for item in args.dotnet_target:
        cmd += ["--dotnet-target", item]
    if args.filter:
        cmd += ["--filter", args.filter]
    if args.configuration:
        cmd += ["--configuration", args.configuration]
    if args.godot_bin:
        cmd += ["--godot-bin", args.godot_bin]
    for item in args.gdunit_path:
        cmd += ["--gdunit-path", item]
    if args.timeout_sec:
        cmd += ["--timeout-sec", str(args.timeout_sec)]
    if args.out_dir:
        cmd += ["--out-dir", args.out_dir]
    return cmd


def build_run_prototype_workflow_cmd(args) -> list[str]:
    cmd = ["py", "-3", "scripts/python/run_prototype_workflow.py"]
    if args.prototype_file:
        cmd += ["--prototype-file", args.prototype_file]
    for item in args.set:
        cmd += ["--set", item]
    if getattr(args, "confirm", False):
        cmd.append("--confirm")
    if getattr(args, "godot_bin", ""):
        cmd += ["--godot-bin", args.godot_bin]
    if int(getattr(args, "stop_after_day", 0) or 0):
        cmd += ["--stop-after-day", str(args.stop_after_day)]
    if getattr(args, "resume_active", ""):
        cmd += ["--resume-active", args.resume_active]
    if args.score_engine:
        cmd += ["--score-engine", args.score_engine]
    if args.score_timeout_sec is not None:
        cmd += ["--score-timeout-sec", str(args.score_timeout_sec)]
    if getattr(args, "self_check", False):
        cmd.append("--self-check")
    return cmd


def build_create_prototype_scene_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/create_prototype_scene.py",
        "--slug",
        args.slug,
    ]
    if getattr(args, "scene_root", ""):
        cmd += ["--scene-root", args.scene_root]
    if getattr(args, "prototype_root", ""):
        cmd += ["--prototype-root", args.prototype_root]
    return cmd


def build_apply_chapter7_status_patch_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/apply_chapter7_status_patch.py",
        "--patch",
        args.patch,
    ]
    if getattr(args, "repo_root", ""):
        cmd += ["--repo-root", args.repo_root]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.out_json:
        cmd += ["--out-json", args.out_json]
    if args.self_check:
        cmd.append("--self-check")
    return cmd


def build_new_execution_plan_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/new_execution_plan.py",
        "--title",
        args.title,
    ]
    if args.status:
        cmd += ["--status", args.status]
    if args.goal:
        cmd += ["--goal", args.goal]
    if args.scope:
        cmd += ["--scope", args.scope]
    if args.current_step:
        cmd += ["--current-step", args.current_step]
    if args.stop_loss:
        cmd += ["--stop-loss", args.stop_loss]
    if args.next_action:
        cmd += ["--next-action", args.next_action]
    if args.exit_criteria:
        cmd += ["--exit-criteria", args.exit_criteria]
    for item in args.adr:
        cmd += ["--adr", item]
    for item in args.decision_log:
        cmd += ["--decision-log", item]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.latest_json:
        cmd += ["--latest-json", args.latest_json]
    if args.output:
        cmd += ["--output", args.output]
    return cmd


def build_new_decision_log_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/new_decision_log.py",
        "--title",
        args.title,
    ]
    if args.status:
        cmd += ["--status", args.status]
    if args.why_now:
        cmd += ["--why-now", args.why_now]
    if args.context:
        cmd += ["--context", args.context]
    if args.decision:
        cmd += ["--decision", args.decision]
    if args.consequences:
        cmd += ["--consequences", args.consequences]
    if args.recovery_impact:
        cmd += ["--recovery-impact", args.recovery_impact]
    if args.validation:
        cmd += ["--validation", args.validation]
    if args.supersedes:
        cmd += ["--supersedes", args.supersedes]
    if args.superseded_by:
        cmd += ["--superseded-by", args.superseded_by]
    for item in args.adr:
        cmd += ["--adr", item]
    for item in args.execution_plan:
        cmd += ["--execution-plan", item]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.latest_json:
        cmd += ["--latest-json", args.latest_json]
    if args.output:
        cmd += ["--output", args.output]
    return cmd


def build_resume_task_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/resume_task.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.latest:
        cmd += ["--latest", args.latest]
    if args.out_json:
        cmd += ["--out-json", args.out_json]
    if args.out_md:
        cmd += ["--out-md", args.out_md]
    if getattr(args, "recommendation_only", False):
        cmd += ["--recommendation-only"]
    recommendation_format = str(getattr(args, "recommendation_format", "") or "").strip()
    if recommendation_format:
        cmd += ["--recommendation-format", recommendation_format]
    return cmd


def build_inspect_run_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/inspect_run.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    if args.latest:
        cmd += ["--latest", args.latest]
    if args.kind:
        cmd += ["--kind", args.kind]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.out_json:
        cmd += ["--out-json", args.out_json]
    if getattr(args, "recommendation_only", False):
        cmd += ["--recommendation-only"]
    recommendation_format = str(getattr(args, "recommendation_format", "") or "").strip()
    if recommendation_format:
        cmd += ["--recommendation-format", recommendation_format]
    return cmd


def build_chapter6_route_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/chapter6_route.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.latest:
        cmd += ["--latest", args.latest]
    if getattr(args, "record_residual", False):
        cmd += ["--record-residual"]
    if args.out_json:
        cmd += ["--out-json", args.out_json]
    if args.out_md:
        cmd += ["--out-md", args.out_md]
    if getattr(args, "recommendation_only", False):
        cmd += ["--recommendation-only"]
    recommendation_format = str(getattr(args, "recommendation_format", "") or "").strip()
    if recommendation_format:
        cmd += ["--recommendation-format", recommendation_format]
    return cmd


def build_run_single_task_chapter6_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/run_single_task_chapter6_lane.py",
        "--task-id",
        args.task_id,
    ]
    if args.godot_bin:
        cmd += ["--godot-bin", args.godot_bin]
    if args.delivery_profile:
        cmd += ["--delivery-profile", args.delivery_profile]
    if args.security_profile:
        cmd += ["--security-profile", args.security_profile]
    if args.fix_through:
        cmd += ["--fix-through", args.fix_through]
    if args.out_dir:
        cmd += ["--out-dir", args.out_dir]
    for name in ("frozen_context", "impact_report", "revision", "binding_evidence", "milestone_handoff", "milestone_regression_summary"):
        value = str(getattr(args, name, "") or "").strip()
        if value:
            cmd += [f"--{name.replace('_', '-')}", value]
    for signal in getattr(args, "execution_plan_signal", None) or []:
        sig_text = str(signal or "").strip()
        if sig_text:
            cmd += ["--execution-plan-signal", sig_text]
    if getattr(args, "self_check", False):
        cmd.append("--self-check")
    return cmd


def build_run_chapter7_ui_wiring_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/run_chapter7_ui_wiring.py",
    ]
    if getattr(args, 'repo_root', ''):
        cmd += ["--repo-root", args.repo_root]
    if getattr(args, 'delivery_profile', ''):
        cmd += ["--delivery-profile", args.delivery_profile]
    if getattr(args, 'tasks_json_path', ''):
        cmd += ["--tasks-json-path", args.tasks_json_path]
    if getattr(args, 'tasks_back_path', ''):
        cmd += ["--tasks-back-path", args.tasks_back_path]
    if getattr(args, 'tasks_gameplay_path', ''):
        cmd += ["--tasks-gameplay-path", args.tasks_gameplay_path]
    if getattr(args, 'overlay_root_path', ''):
        cmd += ["--overlay-root-path", args.overlay_root_path]
    if getattr(args, 'ui_gdd_flow_path', ''):
        cmd += ["--ui-gdd-flow-path", args.ui_gdd_flow_path]
    if getattr(args, 'alignment_audit_path', ''):
        cmd += ["--alignment-audit-path", args.alignment_audit_path]
    if getattr(args, 'wiring_audit_path', ''):
        cmd += ["--wiring-audit-path", args.wiring_audit_path]
    if getattr(args, 'chapter7_profile_path', ''):
        cmd += ["--chapter7-profile-path", args.chapter7_profile_path]
    if getattr(args, 'repo_label', ''):
        cmd += ["--repo-label", args.repo_label]
    if getattr(args, 'back_story_id', ''):
        cmd += ["--back-story-id", args.back_story_id]
    if getattr(args, 'gameplay_story_id', ''):
        cmd += ["--gameplay-story-id", args.gameplay_story_id]
    if getattr(args, 'write_doc', False):
        cmd.append("--write-doc")
    if getattr(args, 'create_tasks', False):
        cmd.append("--create-tasks")
    for item in getattr(args, 'slice', None) or []:
        if str(item).strip():
            cmd += ["--slice", str(item)]
    if getattr(args, 'flow_id', ''):
        cmd += ["--flow-id", args.flow_id]
    if getattr(args, 'out_json', ''):
        cmd += ["--out-json", args.out_json]
    if getattr(args, 'self_check', False):
        cmd.append("--self-check")
    return cmd


def build_run_chapter7_backlog_gap_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/run_chapter7_backlog_gap.py",
    ]
    if getattr(args, 'repo_root', ''):
        cmd += ["--repo-root", args.repo_root]
    if getattr(args, 'delivery_profile', ''):
        cmd += ["--delivery-profile", args.delivery_profile]
    if getattr(args, 'tasks_json_path', ''):
        cmd += ["--tasks-json-path", args.tasks_json_path]
    if getattr(args, 'tasks_back_path', ''):
        cmd += ["--tasks-back-path", args.tasks_back_path]
    if getattr(args, 'tasks_gameplay_path', ''):
        cmd += ["--tasks-gameplay-path", args.tasks_gameplay_path]
    if getattr(args, 'design_doc_path', ''):
        cmd += ["--design-doc-path", args.design_doc_path]
    if getattr(args, 'epics_doc_path', ''):
        cmd += ["--epics-doc-path", args.epics_doc_path]
    if getattr(args, 'duplicate_audit_path', ''):
        cmd += ["--duplicate-audit-path", args.duplicate_audit_path]
    for item in getattr(args, 'slice', None) or []:
        if str(item).strip():
            cmd += ["--slice", str(item)]
    if getattr(args, 'flow_id', ''):
        cmd += ["--flow-id", args.flow_id]
    if getattr(args, 'chapter7_profile_path', ''):
        cmd += ["--chapter7-profile-path", args.chapter7_profile_path]
    if getattr(args, 'ui_evidence', ''):
        cmd += ["--ui-evidence", args.ui_evidence]
    if getattr(args, 'out_json', ''):
        cmd += ["--out-json", args.out_json]
    if getattr(args, 'self_check', False):
        cmd.append("--self-check")
    return cmd


def build_detect_project_stage_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/detect_project_stage.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    return cmd


def build_doctor_project_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/doctor_project.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    return cmd


def build_check_directory_boundaries_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/check_directory_boundaries.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    return cmd


def build_project_health_scan_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/project_health_scan.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    if getattr(args, "serve", False):
        cmd.append("--serve")
    port = int(getattr(args, "port", 0) or 0)
    if port > 0:
        cmd += ["--port", str(port)]
    return cmd


def build_serve_project_health_cmd(args) -> list[str]:
    cmd = [
        "py",
        "-3",
        "scripts/python/serve_project_health.py",
    ]
    if args.repo_root:
        cmd += ["--repo-root", args.repo_root]
    port = int(getattr(args, "port", 0) or 0)
    if port > 0:
        cmd += ["--port", str(port)]
    return cmd


def enforce_paid_api_opt_in(backend: str | None, *, allow_paid_api: bool = False, repo_root: str | Path = ".") -> None:
    import os
    env_allowed = str(os.environ.get("NEWROGUE_ALLOW_PAID_API") or os.environ.get("SC_ALLOW_PAID_API") or "").strip().lower() in {"1", "true", "yes"}
    if allow_paid_api or env_allowed:
        os.environ["NEWROGUE_ALLOW_PAID_API"] = "1"
    name = str(backend or "").strip().lower()
    if not name:
        return
    opt_in_backends = {"openai-api", "gemini-api"}
    try:
        from _isolated_runner_registry import load_llm_routing
        routing = load_llm_routing(Path(repo_root).resolve())
        backends_cfg = routing.get("plane_a", {}).get("backends", {})
        if isinstance(backends_cfg, dict):
            for key, cfg in backends_cfg.items():
                if isinstance(cfg, dict) and cfg.get("opt_in_only") is True:
                    opt_in_backends.add(str(key).strip().lower())
    except Exception:
        pass
    if name in opt_in_backends and not (allow_paid_api or env_allowed):
        raise ValueError(f"paid API backend '{name}' is opt-in only; pass --allow-paid-api to authorize")


def _resolve_cli_plane_b_runner(raw_runner: str | None, repo_root: str | Path) -> str:
    import os
    aliases = {"auto": None, "codex": "codex", "gemini": "gemini", "codex-cli": "codex", "gemini-cli": "gemini"}
    default_codex = str(Path(__file__).resolve().with_name("codex_isolated_model_runner.py"))
    default_codex_set = {
        default_codex,
        "codex_isolated_model_runner.py",
        "scripts/python/codex_isolated_model_runner.py",
    }
    raw_str = str(raw_runner).strip() if raw_runner is not None else None
    lowered = raw_str.lower() if raw_str is not None else None
    if lowered in aliases or (
        (raw_str is None or raw_str in default_codex_set)
        and str(os.environ.get("NEWROGUE_PLANE_B_RUNNER") or "").strip()
    ):
        from _isolated_runner_registry import resolve_plane_b_runner
        target_root = Path(repo_root).resolve()
        tool_root = Path(__file__).resolve().parents[2]
        runner_root = target_root if (target_root / "scripts/python/codex_isolated_model_runner.py").is_file() else tool_root
        routing_env = dict(os.environ)
        if "NEWROGUE_LLM_ROUTING_PATH" not in routing_env and (target_root / "docs/workflows/llm-routing.json").is_file():
            routing_env["NEWROGUE_LLM_ROUTING_PATH"] = str((target_root / "docs/workflows/llm-routing.json").resolve())
        requested = aliases[lowered] if lowered in aliases else None
        return str(resolve_plane_b_runner(runner_root, requested, env=routing_env))
    return raw_runner if raw_runner is not None else default_codex


def build_plan_capabilities_cmd(args) -> list[str]:
    _planning_stage_arguments(args)
    # A page/launcher can invoke dev_cli by absolute path from another cwd.
    # Reuse its interpreter and locate the child next to this module.
    cmd = [sys.executable, str(Path(__file__).resolve().with_name("plan_capabilities.py")),
           "--repo-root", args.repo_root, args.stage]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.stage == "prepare":
        cmd += ["--input-stage", getattr(args, "input_stage", "legacy")]
        if getattr(args, "planning_contract", ""):
            cmd += ["--planning-contract", args.planning_contract]
        for task_id in args.task_id:
            cmd += ["--task-id", task_id]
        if args.allow_unready_draft:
            cmd.append("--allow-unready-draft")
        cmd += ["--source-manifest", args.source_manifest, "--ledger", args.ledger, "--semantics", args.semantics]
        if args.model_batch_char_budget is not None:
            cmd += ["--model-batch-char-budget", str(args.model_batch_char_budget)]
        cmd += [
            "--candidate-retry-limit", str(args.candidate_retry_limit),
            "--review-retry-limit", str(args.review_retry_limit),
            "--candidate-budget-sec", str(args.candidate_budget_sec),
            "--synthesis-budget-sec", str(args.synthesis_budget_sec),
            "--total-budget-sec", str(args.total_budget_sec),
            "--request-limit", str(args.request_limit),
        ]
    elif args.stage in {"generate", "review", "align"}:
        if args.runner:
            cmd += ["--runner", _resolve_cli_plane_b_runner(args.runner, args.repo_root)]
        cmd += ["--timeout-sec", str(args.timeout_sec)]
        if args.stage == "generate":
            if getattr(args, "max_new_dispatches", None) is not None:
                cmd += ["--max-new-dispatches", str(args.max_new_dispatches)]
            if getattr(args, "pause_after_sec", None) is not None:
                cmd += ["--pause-after-sec", str(args.pause_after_sec)]
    elif args.stage == "apply":
        if args.alignment_override:
            cmd += ["--alignment-override", args.alignment_override]
        if args.confirm:
            cmd.append("--confirm")
    elif args.stage == "validate-candidate" and args.candidate:
        cmd += ["--candidate", args.candidate]
        if getattr(args, "input_stage", "legacy") == "3b":
            cmd += ["--input-stage", "3b", "--prepared-ref", args.prepared_ref]
    return _runtime_arguments(args, cmd)


def _planning_stage_arguments(args):
    stage = getattr(args, "input_stage", "legacy")
    contract = getattr(args, "planning_contract", "")
    prepared = getattr(args, "prepared_ref", "")
    profile = getattr(args, "planning_profile", "")
    reading = args.stage in {"validate-candidate", "validate"} and bool(getattr(args, "candidate", ""))
    runtime = args.stage in {"generate", "review", "verify-selection", "status", "validate"} and not reading
    if contract and (stage != "3b" or args.stage != "prepare"):
        raise ValueError("--planning-contract requires explicit 3b prepare")
    if stage == "legacy":
        if profile or prepared:
            raise ValueError("--prepared-ref/--planning-profile require explicit 3b")
        return
    if stage != "3b":
        raise ValueError("unsupported input stage")
    if (getattr(args, "task_id", []) or getattr(args, "allow_unready_draft", False)
            or getattr(args, "capabilities", "") or getattr(args, "manifest", "")
            or getattr(args, "evidence_ref", []) or getattr(args, "run_invocation_limit", None) is not None
            or getattr(args, "model_batch_char_budget", None) is not None
            or getattr(args, "source_manifest", "logs/ci/task-generation/source-manifest.v1.json") != "logs/ci/task-generation/source-manifest.v1.json"
            or getattr(args, "ledger", "logs/ci/task-generation/source-blocks.v1.json") != "logs/ci/task-generation/source-blocks.v1.json"
            or getattr(args, "semantics", "logs/ci/task-generation/semantic-requirements.v1.json") != "logs/ci/task-generation/semantic-requirements.v1.json"):
        raise ValueError("3b rejects legacy Task/readiness/manifest/evidence gates")
    if args.stage == "prepare":
        if not contract or prepared or profile:
            raise ValueError("3b prepare requires --planning-contract only")
        return
    if reading:
        if not prepared or profile:
            raise ValueError("3b candidate validation requires prepared-ref, candidate and no execution profile")
    elif runtime:
        from _b_route_planning_runtime import PROFILES
        cmd_name = getattr(args, "cmd", "") or getattr(args, "command", "")
        if not prepared or profile not in PROFILES:
            raise ValueError("3b execution requires --prepared-ref and known --planning-profile")
        if cmd_name in {"plan-capabilities", "plan-mvg"} and PROFILES[profile][0] != (
            "capabilities" if cmd_name == "plan-capabilities" else "mvg"
        ):
            raise ValueError("3b planning profile does not match selected planner command")
    else:
        raise ValueError("3b stage is not a planning execution or inspection stage")


def _runtime_arguments(args, cmd):
    enforce_paid_api_opt_in(None, allow_paid_api=bool(getattr(args, "allow_paid_api", False)), repo_root=getattr(args, "repo_root", "."))
    if getattr(args, "allow_paid_api", False):
        cmd.append("--allow-paid-api")
    if getattr(args, "input_stage", "legacy") == "3b" and getattr(args, "planning_profile", ""):
        cmd += ["--input-stage", "3b", "--prepared-ref", args.prepared_ref,
                "--planning-profile", args.planning_profile]
    return cmd


def build_plan_mvg_cmd(args) -> list[str]:
    _planning_stage_arguments(args)
    runner = args.runner
    if runner is None:
        runner = (_resolve_cli_plane_b_runner(None, args.repo_root)
                  if getattr(args, "input_stage", "legacy") == "3b"
                  else "scripts/python/openai_isolated_model_runner.py")
    elif runner in {"auto", "codex", "gemini", "codex-cli", "gemini-cli"}:
        runner = _resolve_cli_plane_b_runner(runner, args.repo_root)
    if getattr(args, "candidate", "") and args.stage != "validate":
        raise ValueError("--candidate is limited to explicit 3b MVG validate")
    cmd = [sys.executable, str(Path(__file__).resolve().with_name("plan_mvg.py")), "--repo-root", args.repo_root, args.stage]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.stage == "prepare":
        cmd += ["--input-stage", getattr(args, "input_stage", "legacy")]
        if getattr(args, "planning_contract", ""):
            cmd += ["--planning-contract", args.planning_contract]
        if getattr(args, "run_invocation_limit", None) is not None:
            cmd += ["--run-invocation-limit", str(args.run_invocation_limit)]
        if args.capabilities:
            cmd += ["--capabilities", args.capabilities]
        if args.manifest:
            cmd += ["--manifest", args.manifest]
        for task_id in args.task_id:
            cmd += ["--task-id", task_id]
        for ref in getattr(args, "evidence_ref", []):
            cmd += ["--evidence-ref", ref]
        if args.allow_unready_draft:
            cmd.append("--allow-unready-draft")
    elif args.stage == "validate":
        if getattr(args, "input_stage", "legacy") == "3b" and args.candidate:
            cmd += ["--input-stage", "3b", "--prepared-ref", args.prepared_ref, "--candidate", args.candidate]
        elif getattr(args, "candidate", ""):
            raise ValueError("legacy MVG validate does not accept --candidate")
    elif args.stage == "generate":
        if getattr(args, "input_stage", "legacy") != "3b":
            enforce_paid_api_opt_in(args.llm_backend, allow_paid_api=getattr(args, "allow_paid_api", False), repo_root=args.repo_root)
        cmd += ["--timeout-sec", str(args.timeout_sec), "--llm-backend", args.llm_backend]
        if getattr(args, "input_stage", "legacy") == "3b":
            cmd += ["--runner", runner]
        if getattr(args, "max_new_dispatches", None) is not None:
            cmd += ["--max-new-dispatches", str(args.max_new_dispatches)]
        if getattr(args, "pause_after_sec", None) is not None:
            cmd += ["--pause-after-sec", str(args.pause_after_sec)]
    elif args.stage == "review":
        cmd += ["--timeout-sec", str(args.timeout_sec), "--runner", runner]
    elif args.stage == "apply" and args.confirm:
        cmd.append("--confirm")
    elif args.stage in {"audit", "reopen-plan", "reopen"}:
        names = {"audit": ("conflict_report", "conflict_report_sha256"),
            "reopen-plan": ("audit", "audit_sha256"), "reopen": ("plan", "plan_sha256")}[args.stage]
        values = [getattr(args, name, "") for name in names]
        if bool(values[0]) != bool(values[1]) or (args.stage != "audit" and not all(values)):
            raise ValueError("plan-mvg " + args.stage + " requires the exact artifact and SHA-256 pair")
        for name, value in zip(names, values):
            if value:
                cmd += ["--" + name.replace("_", "-"), value]
    elif args.stage == "rebind-handoff":
        if not args.task_id or len(args.task_id) != 1:
            raise ValueError("plan-mvg rebind-handoff requires exactly one --task-id")
        if bool(args.change_plan) != bool(args.handoff_out):
            raise ValueError("milestone rebind requires both --change-plan and --handoff-out")
        cmd += ["--task-id", args.task_id[0]]
        if args.change_plan:
            cmd += ["--change-plan", args.change_plan, "--out", args.handoff_out]
    return _runtime_arguments(args, cmd)


def build_b_route_task_preview_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-task-preview is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("preview_b_route_task_changes.py")),
    ]
    for attr, flag in (
        ("root", "--root"),
        ("plan_id", "--plan-id"),
        ("run_id", "--run-id"),
        ("audit_ref", "--audit-ref"),
        ("scope_id", "--scope-id"),
    ):
        value = getattr(args, attr, None)
        if value is None or not str(value).strip():
            raise ValueError(f"b-route-task-preview requires nonempty {flag}")
        cmd += [flag, str(value)]
    for attr, flag in (
        ("protection_ref", "--protection-ref"),
        ("manifest", "--manifest"),
        ("change_intents", "--change-intents"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-task-preview optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_b_route_task_compile_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("compile_b_route_tasks.py")),
    ]
    for attr, flag in (
        ("root", "--root"),
        ("stage", "--stage"),
        ("operation_id", "--operation-id"),
    ):
        value = getattr(args, attr, None)
        if value is None or not str(value).strip():
            raise ValueError(f"b-route-task-compile requires nonempty {flag}")
        cmd += [flag, str(value)]
    request = getattr(args, "request", None)
    if request is not None:
        if not str(request).strip():
            raise ValueError("b-route-task-compile --request must be nonempty when provided")
        cmd += ["--request", str(request)]
    return cmd


def build_b_route_task_origin_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-task-origin is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("resolve_b_route_task_origin.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-task-origin requires nonempty --root")
    cmd += ["--root", str(root)]
    task_id = getattr(args, "task_id", None)
    if task_id is None or not str(task_id).strip():
        raise ValueError("b-route-task-origin requires nonempty --task-id")
    cmd += ["--task-id", str(task_id)]
    for attr, flag in (("operation", "--operation"), ("report", "--report")):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-task-origin optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_b_route_chapter4_binding_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("refine_b_route_chapter4_binding.py")),
    ]
    for attr, flag in (
        ("root", "--root"),
        ("stage", "--stage"),
        ("operation_id", "--operation-id"),
    ):
        value = getattr(args, attr, None)
        if value is None or not str(value).strip():
            raise ValueError(f"b-route-chapter4-binding requires nonempty {flag}")
        cmd += [flag, str(value)]
    request = getattr(args, "request", None)
    if request is not None:
        if not str(request).strip():
            raise ValueError("b-route-chapter4-binding --request must be nonempty when provided")
        cmd += ["--request", str(request)]
    return cmd


def build_b_route_input_set_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-input-set is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("resolve_b_route_input_set.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-input-set requires nonempty --root")
    cmd += ["--root", str(root)]
    task_id = getattr(args, "task_id", None)
    if task_id is None or not str(task_id).strip():
        raise ValueError("b-route-input-set requires nonempty --task-id")
    cmd += ["--task-id", str(task_id)]
    for attr, flag in (
        ("operation", "--operation"),
        ("candidate_binding", "--candidate-binding"),
        ("baseline", "--baseline"),
        ("lock_mode", "--lock-mode"),
        ("report", "--report"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-input-set optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    max_attempts = getattr(args, "max_attempts", None)
    if max_attempts is not None:
        cmd += ["--max-attempts", str(max_attempts)]
    return cmd


def build_b_route_stage5_obligations_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("bind_b_route_stage5_obligations.py")),
    ]
    for attr, flag in (
        ("root", "--root"),
        ("stage", "--stage"),
        ("operation_id", "--operation-id"),
    ):
        value = getattr(args, attr, None)
        if value is None or not str(value).strip():
            raise ValueError(f"b-route-stage5-obligations requires nonempty {flag}")
        cmd += [flag, str(value)]
    request = getattr(args, "request", None)
    if request is not None:
        if not str(request).strip():
            raise ValueError("b-route-stage5-obligations --request must be nonempty when provided")
        cmd += ["--request", str(request)]
    return cmd


def build_b_route_chapter5_readiness_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("reconcile_b_route_chapter5_readiness.py")),
    ]
    for attr, flag in (
        ("root", "--root"),
        ("stage", "--stage"),
        ("task_id", "--task-id"),
    ):
        value = getattr(args, attr, None)
        if value is None or not str(value).strip():
            raise ValueError(f"b-route-chapter5-readiness requires nonempty {flag}")
        cmd += [flag, str(value)]
    for attr, flag in (
        ("decisions", "--decisions"),
        ("operation", "--operation"),
        ("out", "--out"),
        ("readiness_out", "--readiness-out"),
        ("reconciliation", "--reconciliation"),
        ("readiness", "--readiness"),
        ("lock_mode", "--lock-mode"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-chapter5-readiness optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    for audit_ref in getattr(args, "audit_ref", None) or []:
        if not str(audit_ref).strip():
            raise ValueError("b-route-chapter5-readiness --audit-ref entries must be nonempty")
        cmd += ["--audit-ref", str(audit_ref)]
    for attr, flag in (
        ("no_latest", "--no-latest"),
        ("dry_run", "--dry-run"),
        ("record_technical_debt", "--record-technical-debt"),
        ("require_full_audit_proof", "--require-full-audit-proof"),
    ):
        if getattr(args, attr, False):
            cmd.append(flag)
    return cmd


def build_b_route_chapter6_gate_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-chapter6-gate is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("check_b_route_chapter6_gate.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-chapter6-gate requires nonempty --root")
    cmd += ["--root", str(root)]
    task_id = getattr(args, "task_id", None)
    if task_id is None or not str(task_id).strip():
        raise ValueError("b-route-chapter6-gate requires nonempty --task-id")
    cmd += ["--task-id", str(task_id)]
    for attr, flag in (
        ("operation", "--operation"),
        ("lock_mode", "--lock-mode"),
        ("expected_input_set_digest", "--expected-input-set-digest"),
        ("report", "--report"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-chapter6-gate optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_b_route_defect_routing_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-defect-routing is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("check_b_route_defect_routing.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-defect-routing requires nonempty --root")
    cmd += ["--root", str(root)]
    task_id = getattr(args, "task_id", None)
    if task_id is None or not str(task_id).strip():
        raise ValueError("b-route-defect-routing requires nonempty --task-id")
    cmd += ["--task-id", str(task_id)]
    for attr, flag in (
        ("run_dir", "--run-dir"),
        ("defect_input", "--defect-input"),
        ("delta_intents", "--delta-intents"),
        ("fix_through", "--fix-through"),
        ("report", "--report"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-defect-routing optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_b_route_chapter7_slice_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-chapter7-slice is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("check_b_route_chapter7_slice.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-chapter7-slice requires nonempty --root")
    cmd += ["--root", str(root)]
    flow_id = getattr(args, "flow_id", None)
    slice_name = getattr(args, "slice", None)
    task_ids = list(getattr(args, "task_id", None) or [])
    if not flow_id and not slice_name and not task_ids:
        raise ValueError("b-route-chapter7-slice requires at least one of --flow-id, --slice, or --task-id")
    for tid in task_ids:
        if not str(tid).strip():
            raise ValueError("b-route-chapter7-slice --task-id entries must be nonempty")
        cmd += ["--task-id", str(tid)]
    for attr, flag in (
        ("flow_id", "--flow-id"),
        ("slice", "--slice"),
        ("profile", "--profile"),
        ("evidence_dir", "--evidence-dir"),
        ("ui_evidence", "--ui-evidence"),
        ("gap_input", "--gap-input"),
        ("operation", "--operation"),
        ("report", "--report"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-chapter7-slice optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_b_route_entrypoint_parity_cmd(args) -> list[str]:
    if getattr(args, "write", False) or getattr(args, "apply", False):
        raise ValueError("b-route-entrypoint-parity is strictly read-only and rejects write/apply flags")
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("check_b_route_entrypoint_parity.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or not str(root).strip():
        raise ValueError("b-route-entrypoint-parity requires nonempty --root")
    cmd += ["--root", str(root)]
    task_ids = list(getattr(args, "task_id", None) or [])
    epic3_handoff = bool(getattr(args, "epic3_handoff", False))
    if not task_ids and not epic3_handoff:
        raise ValueError("b-route-entrypoint-parity requires at least one --task-id or --epic3-handoff")
    for tid in task_ids:
        if not str(tid).strip():
            raise ValueError("b-route-entrypoint-parity --task-id entries must be nonempty")
        cmd += ["--task-id", str(tid)]
    if epic3_handoff:
        cmd.append("--epic3-handoff")
    for attr, flag in (
        ("operation", "--operation"),
        ("report", "--report"),
        ("handoff_report", "--handoff-report"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if not str(value).strip():
                raise ValueError(f"b-route-entrypoint-parity optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


IMPACT_CLOSURE_FORBIDDEN_FLAGS = ("write", "apply", "commit", "mutate_tasks", "publish", "set_status", "retire")


def build_b_route_impact_closure_cmd(args) -> list[str]:
    for flag in IMPACT_CLOSURE_FORBIDDEN_FLAGS:
        if getattr(args, flag, False):
            raise ValueError(
                "b-route-impact-closure is strictly read-only and rejects --apply/--write/--commit/--mutate-tasks flags"
            )
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("compute_b_route_impact_closure.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or type(root) is bool or not str(root).strip():
        raise ValueError("b-route-impact-closure requires nonempty --root")
    cmd += ["--root", str(root)]
    change_roots = list(getattr(args, "change_root", None) or [])
    proof = getattr(args, "revalidate_proof", None)
    if not change_roots and proof is None:
        raise ValueError("b-route-impact-closure requires at least one --change-root or --revalidate-proof")
    if change_roots and proof is not None:
        raise ValueError("b-route-impact-closure accepts either --change-root or --revalidate-proof, not both")
    for attr, flag in (("change_root", "--change-root"), ("plan_id", "--plan-id"), ("manifest", "--manifest")):
        for value in list(getattr(args, attr, None) or []):
            if type(value) is bool:
                raise ValueError(f"b-route-impact-closure {flag} entries must be strings, not booleans")
            if not str(value).strip():
                raise ValueError(f"b-route-impact-closure {flag} entries must be nonempty")
            cmd += [flag, str(value)]
    for attr, flag in (
        ("revalidate_proof", "--revalidate-proof"),
        ("operation", "--operation"),
        ("report", "--report"),
        ("events_log", "--events-log"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if type(value) is bool:
                raise ValueError(f"b-route-impact-closure optional {flag} must be a string, not a boolean")
            if not str(value).strip():
                raise ValueError(f"b-route-impact-closure optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


VERIFICATION_SCOPE_FORBIDDEN_FLAGS = ("write", "apply", "commit", "mutate_tasks", "publish", "set_status", "retire",
                                      "mark_done", "claim_passed")


def build_b_route_verification_scope_cmd(args) -> list[str]:
    for flag in VERIFICATION_SCOPE_FORBIDDEN_FLAGS:
        if getattr(args, flag, False):
            raise ValueError(
                "b-route-verification-scope is strictly read-only and rejects --apply/--write/--commit/--mutate-tasks flags"
            )
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("build_b_route_verification_scope.py")),
    ]
    root = getattr(args, "root", ".")
    if root is None or type(root) is bool or not str(root).strip():
        raise ValueError("b-route-verification-scope requires nonempty --root")
    cmd += ["--root", str(root)]
    for attr, flag in (("change_root", "--change-root"), ("task_id", "--task-id"), ("plan_id", "--plan-id"),
                       ("flow_id", "--flow-id"), ("manifest", "--manifest"),
                       ("cumulative_manifest", "--cumulative-manifest")):
        for value in list(getattr(args, attr, None) or []):
            if type(value) is bool:
                raise ValueError(f"b-route-verification-scope {flag} entries must be strings, not booleans")
            if not str(value).strip():
                raise ValueError(f"b-route-verification-scope {flag} entries must be nonempty")
            cmd += [flag, str(value)]
    for attr, flag in (
        ("impact_proof", "--impact-proof"),
        ("scope_delta", "--scope-delta"),
        ("validate_scope", "--validate-scope"),
        ("revalidate_scope", "--revalidate-scope"),
        ("prior_conclusions", "--prior-conclusions"),
        ("operation", "--operation"),
        ("report", "--report"),
        ("events_log", "--events-log"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            if type(value) is bool:
                raise ValueError(f"b-route-verification-scope optional {flag} must be a string, not a boolean")
            if not str(value).strip():
                raise ValueError(f"b-route-verification-scope optional {flag} must be nonempty when provided")
            cmd += [flag, str(value)]
    return cmd


def build_run_mvg_acceptance_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve().with_name("run_mvg_acceptance.py")),
    ]
    if getattr(args, "root", None):
        cmd += ["--root", str(args.root)]
    cmd += [
        "--manifest", str(getattr(args, "manifest", "docs/testing/mvg/m1-critical.json")),
        "--mode", str(getattr(args, "mode", "plan")),
        "--snapshot", str(getattr(args, "snapshot", "workspace")),
        "--revision", str(getattr(args, "revision", "HEAD")),
    ]
    if getattr(args, "base", ""):
        cmd += ["--base", str(args.base)]
    if getattr(args, "godot_bin", ""):
        cmd += ["--godot-bin", str(args.godot_bin)]
    if getattr(args, "dotnet_bin", ""):
        cmd += ["--dotnet-bin", str(args.dotnet_bin)]
    if getattr(args, "timeout_sec", None) is not None:
        cmd += ["--timeout-sec", str(args.timeout_sec)]
    if getattr(args, "challenge_input", False):
        cmd.append("--challenge-input")
    if getattr(args, "verification_scope", ""):
        cmd += ["--verification-scope", str(args.verification_scope)]
    if getattr(args, "execution_strategy", ""):
        cmd += ["--execution-strategy", str(args.execution_strategy)]
    if getattr(args, "protocol_fixture", False):
        cmd.append("--protocol-fixture")
    if getattr(args, "stop_on_deterministic_failure", True) is False:
        cmd.append("--no-stop-on-deterministic-failure")
    for prior in getattr(args, "reuse_evidence_from", None) or []:
        if prior is not None:
            cmd += ["--reuse-evidence-from", str(prior)]
    if getattr(args, "reuse_build_from", None) is not None:
        cmd += ["--reuse-build-from", str(args.reuse_build_from)]
    if getattr(args, "events_log", None) is not None:
        cmd += ["--events-log", str(args.events_log)]
    return cmd
