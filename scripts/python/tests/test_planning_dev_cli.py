#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import dev_cli
from dev_cli_builders import build_plan_capabilities_cmd, build_plan_mvg_cmd


class PlanningDevCliTests(unittest.TestCase):
    def test_capability_prepare_entrypoint(self) -> None:
        args = dev_cli.build_parser().parse_args([
            "plan-capabilities", "--stage", "prepare", "--run-id", "r1",
            "--task-id", "15", "--task-id", "16",
        ])
        cmd = build_plan_capabilities_cmd(args)
        self.assertIn("scripts/python/plan_capabilities.py", cmd)
        self.assertEqual(2, cmd.count("--task-id"))
        self.assertIn("prepare", cmd)

    def test_capability_generate_forwards_isolated_runner(self) -> None:
        args = dev_cli.build_parser().parse_args([
            "plan-capabilities", "--stage", "generate", "--run-id", "r1",
            "--runner", "tools/isolated-runner.exe",
        ])
        cmd = build_plan_capabilities_cmd(args)
        self.assertIn("--runner", cmd)
        self.assertIn("tools/isolated-runner.exe", cmd)

    def test_mvg_rebind_handoff_forwards_existing_contract_inputs(self) -> None:
        args = dev_cli.build_parser().parse_args([
            "plan-mvg", "--stage", "rebind-handoff", "--run-id", "m1",
            "--task-id", "42",
            "--change-plan", "logs/milestone/change-plan.json",
            "--handoff-out", "logs/milestone/task-42-handoff.json",
        ])
        cmd = build_plan_mvg_cmd(args)
        self.assertIn("rebind-handoff", cmd)
        self.assertEqual(1, cmd.count("--task-id"))
        self.assertIn("logs/milestone/change-plan.json", cmd)
        self.assertIn("logs/milestone/task-42-handoff.json", cmd)

    def test_mvg_prepare_forwards_explicit_capability_and_manifest(self) -> None:
        args = dev_cli.build_parser().parse_args([
            "plan-mvg", "--stage", "prepare", "--run-id", "m1",
            "--capabilities", "docs/planning/semantic-topology/capabilities.v1.json",
            "--manifest", "docs/testing/mvg/m2.json",
            "--task-id", "15",
            "--evidence-ref", "Game.Core.Tests/Tasks/ExistingTests.cs",
            "--evidence-ref", "docs/contracts/extra.md",
        ])
        cmd = build_plan_mvg_cmd(args)
        self.assertIn("--capabilities", cmd)
        self.assertIn("docs/planning/semantic-topology/capabilities.v1.json", cmd)
        self.assertIn("--manifest", cmd)
        self.assertIn("docs/testing/mvg/m2.json", cmd)
        self.assertEqual(2, cmd.count("--evidence-ref"))
        self.assertIn("Game.Core.Tests/Tasks/ExistingTests.cs", cmd)
        self.assertIn("docs/contracts/extra.md", cmd)


if __name__ == "__main__":
    unittest.main()
