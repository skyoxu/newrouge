#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
sys.path.insert(0, str(SC_DIR))

from _acceptance_orchestration import run_tests_bundle  # noqa: E402
from _step_result import StepResult  # noqa: E402


class AcceptanceOrchestrationPostEvidenceTests(unittest.TestCase):
    def test_should_skip_post_evidence_when_headless_failed(self) -> None:
        triplet = SimpleNamespace(task_id="1")

        with (
            patch(
                "_acceptance_orchestration.step_tests_all",
                return_value=StepResult(name="tests-all", status="ok", rc=0),
            ),
            patch(
                "_acceptance_orchestration.step_headless_e2e_evidence",
                return_value=StepResult(name="headless-e2e-evidence", status="fail", rc=1),
            ),
            patch("_acceptance_orchestration.step_post_evidence_integration") as post_step,
        ):
            steps = run_tests_bundle(
                out_dir=REPO_ROOT / "logs" / "ci",
                triplet=triplet,
                only_steps={"tests"},
                has_gd_refs=True,
                require_headless_e2e=True,
                require_executed_refs=False,
                audit_evidence_mode="skip",
                godot_bin="C:/fake/godot.exe",
                run_id="rid",
            )

        names = [s.name for s in steps]
        self.assertEqual(["tests-all", "headless-e2e-evidence", "post-evidence-integration"], names)
        self.assertEqual("skipped", steps[-1].status)
        self.assertEqual("headless_e2e_evidence_failed", (steps[-1].details or {}).get("reason"))
        post_step.assert_not_called()

    def test_should_run_post_evidence_when_headless_ok(self) -> None:
        triplet = SimpleNamespace(task_id="1")

        with (
            patch(
                "_acceptance_orchestration.step_tests_all",
                return_value=StepResult(name="tests-all", status="ok", rc=0),
            ),
            patch(
                "_acceptance_orchestration.step_headless_e2e_evidence",
                return_value=StepResult(name="headless-e2e-evidence", status="ok", rc=0),
            ),
            patch(
                "_acceptance_orchestration.step_post_evidence_integration",
                return_value=StepResult(name="post-evidence-integration", status="ok", rc=0),
            ) as post_step,
        ):
            steps = run_tests_bundle(
                out_dir=REPO_ROOT / "logs" / "ci",
                triplet=triplet,
                only_steps={"tests"},
                has_gd_refs=True,
                require_headless_e2e=True,
                require_executed_refs=False,
                audit_evidence_mode="skip",
                godot_bin="C:/fake/godot.exe",
                run_id="rid",
            )

        self.assertEqual("post-evidence-integration", steps[-1].name)
        self.assertEqual("ok", steps[-1].status)
        post_step.assert_called_once()


if __name__ == "__main__":
    unittest.main()
