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
    def test_explicit_3b_mvg_uses_direct_codex_default_and_keeps_explicit_runner(self):
        for stage in ("generate", "review"):
            for runner in (None,"tools/explicit-runner.exe"):
                argv=["plan-mvg","--stage",stage,"--run-id","b-default","--input-stage","3b",
                    "--prepared-ref","logs/prepared.json","--planning-profile","3b-mvg-v1"]
                if runner is not None:
                    argv += ["--runner",runner]
                args=dev_cli.build_parser().parse_args(argv)
                command=build_plan_mvg_cmd(args)
                expected=str(PYTHON/"codex_isolated_model_runner.py") if runner is None else runner
                self.assertEqual(command[command.index("--runner")+1],expected)
                self.assertEqual(args.runner,runner)
                self.assertEqual(command[command.index("--planning-profile")+1],"3b-mvg-v1")

    def test_legacy_mvg_review_runner_and_generate_backend_keep_existing_defaults(self):
        for stage in ("generate","review"):
            args=dev_cli.build_parser().parse_args(["plan-mvg","--stage",stage,"--run-id","legacy-default"])
            command=build_plan_mvg_cmd(args)
            if stage=="review":
                self.assertEqual(command[command.index("--runner")+1],"scripts/python/openai_isolated_model_runner.py")
            else:
                self.assertNotIn("--runner",command)
                self.assertEqual(command[command.index("--llm-backend")+1],"codex-cli")
        args=dev_cli.build_parser().parse_args(["plan-mvg","--stage","review","--run-id","explicit",
            "--runner","tools/explicit.exe"])
        command=build_plan_mvg_cmd(args)
        self.assertEqual(command[command.index("--runner")+1],"tools/explicit.exe")

    def test_3b_both_builders_forward_one_contract(self):
        for command, builder, script in (("plan-capabilities", build_plan_capabilities_cmd, "plan_capabilities.py"),
                                         ("plan-mvg", build_plan_mvg_cmd, "plan_mvg.py")):
            args = dev_cli.build_parser().parse_args([command, "--stage", "prepare", "--run-id", "r3b",
                "--input-stage", "3b", "--planning-contract", "contracts/planning.json"])
            cmd = builder(args)
            self.assertEqual(sys.executable, cmd[0])
            self.assertEqual(PYTHON / script, Path(cmd[1]))
            self.assertEqual(cmd.count("--planning-contract"), 1)
            self.assertEqual(cmd[cmd.index("--planning-contract") + 1], "contracts/planning.json")
            self.assertEqual(cmd[cmd.index("--input-stage") + 1], "3b")

    def test_3b_stage_and_contract_cannot_be_silently_ignored(self):
        for command, builder in (("plan-capabilities", build_plan_capabilities_cmd), ("plan-mvg", build_plan_mvg_cmd)):
            for stage, extras in (("generate", ["--input-stage", "3b", "--planning-contract", "c.json"]),
                                  ("prepare", ["--planning-contract", "c.json"]),
                                  ("prepare", ["--input-stage", "3b"])):
                args = dev_cli.build_parser().parse_args([command, "--stage", stage, "--run-id", "r3b", *extras])
                with self.assertRaises(ValueError):
                    builder(args)

    def test_both_cli_shells_3b_fail_closed_without_legacy_inputs(self):
        # These are CLI-shell Python processes, never model-runner processes.
        with tempfile.TemporaryDirectory() as directory:
            for script in ("plan_capabilities.py", "plan_mvg.py", "dev_cli.py"):
                commands = ("plan-capabilities", "plan-mvg") if script == "dev_cli.py" else (None,)
                for command in commands:
                    args = ([command, "--stage", "prepare"] if command else ["prepare"])
                    process = subprocess.run([sys.executable, str(PYTHON / script),
                        *([] if command else ["--repo-root", directory]), *args,
                        *(["--repo-root", directory] if command else []), "--run-id", "shell-probe",
                        "--input-stage", "3b", "--planning-contract", "missing-contract.json"],
                        cwd=directory, capture_output=True, text=True, timeout=30)
                    self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                    self.assertIn('"input_stage": "3b"', process.stdout)
                    self.assertNotIn("capabilities and --manifest", process.stdout)
                    self.assertFalse(list(Path(directory).rglob("run.json")))

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
                self.assertEqual(1200, action.call_args.kwargs['synthesis_budget_sec'])
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
                self.assertEqual('1200', cmd[cmd.index('--synthesis-budget-sec') + 1])
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
