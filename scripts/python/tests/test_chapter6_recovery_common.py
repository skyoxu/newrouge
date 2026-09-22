#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


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


recovery_common = _load_module("chapter6_recovery_common_module", "scripts/python/_chapter6_recovery_common.py")


class Chapter6RecoveryCommonTests(unittest.TestCase):
    def test_should_infer_artifact_integrity_from_planned_only_reason_without_blocked_by(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {},
            {"reason": "planned_only_incomplete", "artifact_integrity_kind": "planned_only_incomplete"},
        )
        self.assertIn("planned-only terminal run", note)

    def test_should_keep_generic_artifact_integrity_note_for_non_planned_only_kind(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {"blocked_by": "artifact_integrity"},
            {"reason": "latest_bundle_incomplete", "artifact_integrity_kind": "missing_summary"},
        )
        self.assertIn("incomplete or stale", note)

    def test_should_keep_rerun_guard_priority_over_other_inference(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {},
            {"reason": "rerun_blocked:deterministic_green_llm_not_clean", "artifact_integrity_kind": "planned_only_incomplete"},
        )
        self.assertIn("Deterministic evidence is already green", note)

    def test_should_explain_repeat_review_needs_fix_rerun_guard(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {},
            {"reason": "rerun_blocked:repeat_review_needs_fix", "artifact_integrity_kind": ""},
        )
        self.assertIn("reviewer-only reruns", note)


    def test_should_explain_route_run_6_8_rerun_guard(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {},
            {"reason": "rerun_blocked:chapter6_route_run_6_8", "artifact_integrity_kind": ""},
        )
        self.assertIn("continue with needs-fix-fast", note)

    def test_should_explain_route_repo_noise_stop_rerun_guard(self) -> None:
        note = recovery_common.chapter6_stop_loss_note(
            {},
            {"reason": "rerun_blocked:chapter6_route_repo_noise_stop", "artifact_integrity_kind": ""},
        )
        self.assertIn("repo noise or process contention", note)



    def test_compact_recovery_projection_should_match_for_direct_and_inspection_evidence(self) -> None:
        shared = {
            "task_id": "15",
            "run_id": "run-1",
            "recommended_action": "fork",
            "recommended_command": "py -3 scripts/sc/run_review_pipeline.py --task-id 15 --fork",
            "forbidden_commands": [
                "py -3 scripts/sc/run_review_pipeline.py --task-id 15 --resume",
                "py -3 scripts/sc/run_review_pipeline.py --task-id 15",
            ],
        }
        evidence = {
            "latest_summary_signals": {"reason": "approval_required"},
            "chapter6_hints": {"next_action": "fork", "blocked_by": "approval_approved"},
            "approval": {
                "status": "approved",
                "recommended_action": "fork",
                "allowed_actions": ["fork"],
                "blocked_actions": ["resume", "rerun"],
            },
            "run_event_summary": {"latest_turn_id": "turn-2", "turn_count": 2},
            "failure": {"code": "approval_required"},
        }
        direct = recovery_common.compact_recommendation_fields({**shared, **evidence})
        nested = recovery_common.compact_recommendation_fields({**shared, "inspection": evidence})
        self.assertEqual(direct, nested)
        self.assertEqual("fork", direct["recommended_action"])
        self.assertEqual("approval_approved", direct["blocked_by"])
        self.assertEqual("approved", direct["approval_status"])
        self.assertIn("--resume", direct["forbidden_commands"])

    def test_route_execution_policy_should_fail_closed_on_chapter5_readiness(self) -> None:
        policy = recovery_common.route_execution_policy({
            "execution_allowed": False,
            "blocked_by": "chapter5_readiness",
            "preferred_lane": "run-6.8",
        })
        self.assertFalse(policy["execution_allowed"])
        self.assertEqual("chapter5_readiness", policy["stop_reason"])

    def test_route_execution_policy_should_allow_normal_route_without_explicit_flag(self) -> None:
        policy = recovery_common.route_execution_policy({
            "blocked_by": "",
            "preferred_lane": "run-6.8",
        })
        self.assertTrue(policy["execution_allowed"])
        self.assertEqual("", policy["stop_reason"])


if __name__ == "__main__":
    unittest.main()
