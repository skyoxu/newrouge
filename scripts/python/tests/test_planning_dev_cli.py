#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
import contextlib
import io
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import dev_cli
from dev_cli_builders import build_plan_capabilities_cmd, build_plan_mvg_cmd


class PlanningDevCliTests(unittest.TestCase):
    def test_absolute_entrypoint_works_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.run([sys.executable, str(PYTHON / 'dev_cli.py'),
                'plan-capabilities', '--stage', 'status', '--run-id', 'missing-cli-probe'],
                cwd=directory, capture_output=True, text=True, timeout=30)
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn('missing-cli-probe', proc.stdout)
        self.assertNotIn("can't open file", proc.stderr)
        self.assertIn('"status": "blocked"', proc.stdout)

    def test_capability_align_forwards_runner_and_timeout(self):
        args = dev_cli.build_parser().parse_args([
            'plan-capabilities', '--stage', 'align', '--run-id', 'r1',
            '--runner', 'tools/isolated-runner.exe', '--timeout-sec', '123'])
        cmd = build_plan_capabilities_cmd(args)
        self.assertIn('align', cmd)
        self.assertEqual('tools/isolated-runner.exe', cmd[cmd.index('--runner') + 1])
        self.assertEqual('123', cmd[cmd.index('--timeout-sec') + 1])

    def test_direct_planner_defaults_used_by_web_match_time_budgets(self):
        import plan_capabilities as planner
        for stage in ('prepare', 'generate', 'review', 'align'):
            function = {'prepare': 'prepare', 'generate': 'generate',
                        'review': 'review', 'align': 'align_with_llm'}[stage]
            argv = [stage, '--run-id', 'time-budget']
            if stage != 'prepare':
                argv += ['--runner', 'scripts/python/codex_isolated_model_runner.py']
            with patch.object(planner, function, return_value={}) as action, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, planner.main(argv))
            if stage == 'prepare':
                self.assertEqual(2700, action.call_args.kwargs['candidate_budget_sec'])
                self.assertEqual(13500, action.call_args.kwargs['total_budget_sec'])
            else:
                self.assertEqual(2700, action.call_args.kwargs['timeout_sec'])

    def test_capability_time_budgets_allow_three_candidates_review_and_alignment(self):
        for stage in ('prepare', 'generate', 'review'):
            args = dev_cli.build_parser().parse_args([
                'plan-capabilities', '--stage', stage, '--run-id', 'time-budget'])
            cmd = build_plan_capabilities_cmd(args)
            if stage == 'prepare':
                self.assertEqual('2700', cmd[cmd.index('--candidate-budget-sec') + 1])
                self.assertEqual('13500', cmd[cmd.index('--total-budget-sec') + 1])
            else:
                self.assertEqual('2700', cmd[cmd.index('--timeout-sec') + 1])

    def test_capability_batch_default_is_owned_by_planner(self):
        for limit in (None, 40000):
            values = ["plan-capabilities", "--stage", "prepare", "--run-id", "batch-default"]
            if limit is not None:
                values += ["--model-batch-char-budget", str(limit)]
            args = dev_cli.build_parser().parse_args(values)
            cmd = build_plan_capabilities_cmd(args)
            self.assertEqual(limit, args.model_batch_char_budget)
            if limit is None:
                self.assertNotIn("--model-batch-char-budget", cmd)
            else:
                self.assertEqual(str(limit), cmd[cmd.index("--model-batch-char-budget") + 1])

    def test_mvg_prepare_budget_preserves_default_or_explicit_source(self):
        for limit in (None, 7):
            values = ["plan-mvg", "--stage", "prepare", "--run-id", "budget"]
            if limit is not None:
                values += ["--run-invocation-limit", str(limit)]
            args = dev_cli.build_parser().parse_args(values)
            cmd = build_plan_mvg_cmd(args)
            self.assertEqual(limit, args.run_invocation_limit)
            if limit is None:
                self.assertNotIn("--run-invocation-limit", cmd)
            else:
                self.assertEqual("7", cmd[cmd.index("--run-invocation-limit") + 1])

    def test_capability_prepare_entrypoint(self) -> None:
        args = dev_cli.build_parser().parse_args([
            "plan-capabilities", "--stage", "prepare", "--run-id", "r1",
            "--task-id", "15", "--task-id", "16",
        ])
        cmd = build_plan_capabilities_cmd(args)
        self.assertEqual(PYTHON / 'plan_capabilities.py', Path(cmd[1]))
        self.assertEqual(sys.executable, cmd[0])
        self.assertEqual(2, cmd.count("--task-id"))
        self.assertIn("prepare", cmd)

    def test_capability_generate_forwards_isolated_runner(self) -> None:
        default_args = dev_cli.build_parser().parse_args([
            "plan-capabilities", "--stage", "generate", "--run-id", "r-default",
        ])
        self.assertEqual(PYTHON / 'codex_isolated_model_runner.py', Path(default_args.runner))

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
