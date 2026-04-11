#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "scripts" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lane = _load_module("single_task_chapter6_lane_module", "scripts/python/run_single_task_chapter6_lane.py")


class RunSingleTaskChapter6LaneTests(unittest.TestCase):
    def _resume_payload(
        self,
        *,
        recommended_action: str = "inspect",
        chapter6_next_action: str = "inspect",
        approval: dict | None = None,
    ) -> dict:
        return {
            "recommended_action": recommended_action,
            "chapter6_hints": {
                "next_action": chapter6_next_action,
                "blocked_by": str((approval or {}).get("status") or ""),
            },
            "approval": approval or {},
        }

    def test_resolve_profile_policy_should_default_to_p0_for_playable_ea(self) -> None:
        policy = lane.resolve_profile_policy("playable-ea")

        self.assertEqual("playable-ea", policy["delivery_profile"])
        self.assertEqual("host-safe", policy["security_profile"])
        self.assertEqual("P0", policy["fix_through"])
        self.assertEqual("warn", policy["execution_plan_policy"])
        self.assertEqual("unit", policy["red_verify"])

    def test_resolve_profile_policy_should_default_to_p1_for_standard(self) -> None:
        policy = lane.resolve_profile_policy("standard")

        self.assertEqual("standard", policy["delivery_profile"])
        self.assertEqual("strict", policy["security_profile"])
        self.assertEqual("P1", policy["fix_through"])
        self.assertEqual("draft", policy["execution_plan_policy"])
        self.assertEqual("auto", policy["red_verify"])

    def test_plan_should_run_full_lane_when_initial_route_has_no_real_recovery_bundle(self) -> None:
        initial_route = {
            "preferred_lane": "inspect-first",
            "run_id": "n/a",
            "latest_reason": "n/a",
            "blocked_by": "n/a",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(
            [
                "resume-task",
                "chapter6-route-initial",
                "check-tdd-plan",
                "red-first",
                "green",
                "refactor",
                "review-pipeline",
                "chapter6-route-post-review",
                "local-hard-checks-preflight",
                "local-hard-checks",
                "inspect-local-hard-checks",
            ],
            [step["name"] for step in plan["steps"]],
        )

    def test_plan_should_jump_to_68_when_initial_route_requires_targeted_closure(self) -> None:
        initial_route = {
            "preferred_lane": "run-6.8",
            "run_id": "run-15",
            "latest_reason": "rerun_blocked:repeat_review_needs_fix",
            "blocked_by": "rerun_guard",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(
                recommended_action="needs-fix-fast",
                chapter6_next_action="needs-fix-fast",
            ),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(
            [
                "resume-task",
                "chapter6-route-initial",
                "needs-fix-fast",
                "chapter6-route-post-needs-fix",
                "local-hard-checks-preflight",
                "local-hard-checks",
                "inspect-local-hard-checks",
            ],
            [step["name"] for step in plan["steps"]],
        )

    def test_plan_should_stop_after_repo_noise_signal(self) -> None:
        initial_route = {
            "preferred_lane": "repo-noise-stop",
            "run_id": "run-15",
            "latest_reason": "step_failed:sc-test",
            "blocked_by": "recent_failure_summary",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(["resume-task", "chapter6-route-initial"], [step["name"] for step in plan["steps"]])
        self.assertEqual("blocked", plan["status"])
        self.assertEqual("repo-noise-stop", plan["stop_reason"])

    def test_plan_should_use_targeted_closure_when_resume_requires_needs_fix_fast(self) -> None:
        initial_route = {
            "preferred_lane": "inspect-first",
            "run_id": "run-15",
            "latest_reason": "rerun_blocked:repeat_review_needs_fix",
            "blocked_by": "approval_denied",
            "recommended_action": "needs-fix-fast",
            "chapter6_next_action": "needs-fix-fast",
            "forbidden_commands": ["py -3 scripts/sc/run_review_pipeline.py --task-id 15"],
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(
                recommended_action="needs-fix-fast",
                chapter6_next_action="needs-fix-fast",
                approval={
                    "required_action": "fork",
                    "status": "denied",
                    "recommended_action": "resume",
                    "allowed_actions": ["resume", "inspect"],
                    "blocked_actions": ["fork", "rerun"],
                },
            ),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(
            [
                "resume-task",
                "chapter6-route-initial",
                "needs-fix-fast",
                "chapter6-route-post-needs-fix",
                "local-hard-checks-preflight",
                "local-hard-checks",
                "inspect-local-hard-checks",
            ],
            [step["name"] for step in plan["steps"]],
        )

    def test_plan_should_pause_when_approval_is_pending(self) -> None:
        initial_route = {
            "preferred_lane": "inspect-first",
            "run_id": "run-15",
            "latest_reason": "review_pending",
            "blocked_by": "approval_pending",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(
                recommended_action="pause",
                chapter6_next_action="pause",
                approval={
                    "required_action": "fork",
                    "status": "pending",
                    "recommended_action": "pause",
                    "allowed_actions": ["inspect", "pause"],
                    "blocked_actions": ["fork", "resume", "rerun"],
                },
            ),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(["resume-task", "chapter6-route-initial"], [step["name"] for step in plan["steps"]])
        self.assertEqual("blocked", plan["status"])
        self.assertEqual("approval_pending", plan["stop_reason"])

    def test_plan_should_fork_when_approval_is_approved(self) -> None:
        initial_route = {
            "preferred_lane": "inspect-first",
            "run_id": "run-15",
            "latest_reason": "review_pending",
            "blocked_by": "approval_approved",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(
                recommended_action="fork",
                chapter6_next_action="fork",
                approval={
                    "required_action": "fork",
                    "status": "approved",
                    "recommended_action": "fork",
                    "allowed_actions": ["fork", "inspect"],
                    "blocked_actions": ["resume", "rerun"],
                },
            ),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(
            [
                "resume-task",
                "chapter6-route-initial",
                "fork-review-pipeline",
                "chapter6-route-post-fork",
                "local-hard-checks-preflight",
                "local-hard-checks",
                "inspect-local-hard-checks",
            ],
            [step["name"] for step in plan["steps"]],
        )
        self.assertEqual("planned", plan["status"])

    def test_plan_should_stop_after_record_residual_signal(self) -> None:
        initial_route = {
            "preferred_lane": "record-residual",
            "run_id": "run-15",
            "latest_reason": "rerun_blocked:repeat_review_needs_fix",
            "blocked_by": "rerun_guard",
        }

        plan = lane.build_execution_plan(
            task_id="15",
            godot_bin="C:/Godot/Godot.exe",
            profile_policy=lane.resolve_profile_policy("fast-ship"),
            resume_payload=self._resume_payload(
                recommended_action="needs-fix-fast",
                chapter6_next_action="needs-fix-fast",
            ),
            initial_route=initial_route,
            post_review_route={"preferred_lane": "inspect-first"},
            final_route={"preferred_lane": "inspect-first"},
        )

        self.assertEqual(["resume-task", "chapter6-route-initial"], [step["name"] for step in plan["steps"]])
        self.assertEqual("blocked", plan["status"])
        self.assertEqual("record-residual", plan["stop_reason"])

    def test_route_command_should_record_residual_by_default_for_p1_policy(self) -> None:
        cmd = lane.build_chapter6_route_cmd(task_id="15", record_residual=True)

        self.assertEqual(["py", "-3", "scripts/python/dev_cli.py"], cmd[:3])
        self.assertIn("chapter6-route", cmd)
        self.assertIn("--record-residual", cmd)
        self.assertIn("--recommendation-only", cmd)
        self.assertIn("--recommendation-format", cmd)
        self.assertIn("json", cmd)

    def test_main_self_check_should_write_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "logs" / "ci" / "chapter6-self-check"
            argv = [
                "run_single_task_chapter6_lane.py",
                "--task-id",
                "15",
                "--godot-bin",
                "C:/Godot/Godot.exe",
                "--delivery-profile",
                "fast-ship",
                "--self-check",
                "--out-dir",
                str(out_dir),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(lane, "_repo_root", return_value=root),
            ):
                rc = lane.main()

            self.assertEqual(0, rc)
            payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", payload["status"])
            self.assertEqual("P1", payload["profile_policy"]["fix_through"])
            self.assertEqual("check-tdd-plan", payload["steps"][2]["name"])

    def test_main_should_run_targeted_closure_when_resume_requires_needs_fix_fast(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "logs" / "ci" / "chapter6-live"
            argv = [
                "run_single_task_chapter6_lane.py",
                "--task-id",
                "15",
                "--godot-bin",
                "C:/Godot/Godot.exe",
                "--delivery-profile",
                "fast-ship",
                "--out-dir",
                str(out_dir),
            ]
            plain_calls: list[str] = []

            def fake_json_step(_out_dir: Path, *, name: str, cmd: list[str]):
                step = {"name": name, "cmd": list(cmd), "rc": 0, "stdout_tail": "", "stderr_tail": "", "log": f"{name}.log"}
                if name == "resume-task":
                    return (
                        step,
                        self._resume_payload(
                            recommended_action="needs-fix-fast",
                            chapter6_next_action="needs-fix-fast",
                            approval={
                                "required_action": "fork",
                                "status": "denied",
                                "recommended_action": "resume",
                                "allowed_actions": ["resume", "inspect"],
                                "blocked_actions": ["fork", "rerun"],
                            },
                        ),
                    )
                if name == "chapter6-route-initial":
                    return (
                        step,
                        {
                            "preferred_lane": "inspect-first",
                            "run_id": "run-15",
                            "latest_reason": "rerun_blocked:repeat_review_needs_fix",
                            "blocked_by": "approval_denied",
                            "recommended_action": "needs-fix-fast",
                            "chapter6_next_action": "needs-fix-fast",
                            "forbidden_commands": ["py -3 scripts/sc/run_review_pipeline.py --task-id 15"],
                        },
                    )
                if name == "chapter6-route-post-needs-fix":
                    return (step, {"preferred_lane": "inspect-first"})
                if name == "chapter6-route-post-review":
                    return (step, {"preferred_lane": "inspect-first"})
                if name == "inspect-local-hard-checks":
                    return (step, {"status": "ok"})
                raise AssertionError(f"unexpected json step: {name}")

            def fake_plain_step(_out_dir: Path, *, name: str, cmd: list[str]):
                plain_calls.append(name)
                return {"name": name, "cmd": list(cmd), "rc": 0, "stdout_tail": "", "stderr_tail": "", "log": f"{name}.log"}

            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(lane, "_repo_root", return_value=root),
                mock.patch.object(lane, "_run_json_step", side_effect=fake_json_step),
                mock.patch.object(lane, "_run_plain_step", side_effect=fake_plain_step),
            ):
                rc = lane.main()

            self.assertEqual(0, rc)
            self.assertEqual(
                ["needs-fix-fast", "local-hard-checks-preflight", "local-hard-checks"],
                plain_calls,
            )
            payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [
                    "resume-task",
                    "chapter6-route-initial",
                    "needs-fix-fast",
                    "chapter6-route-post-needs-fix",
                    "local-hard-checks-preflight",
                    "local-hard-checks",
                    "inspect-local-hard-checks",
                ],
                [step["name"] for step in payload["steps"]],
            )
            self.assertNotIn("check-tdd-plan", payload["planned_steps"])


if __name__ == "__main__":
    unittest.main()
