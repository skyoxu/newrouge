#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_BUILD_DIR = REPO_ROOT / "scripts" / "sc" / "build"
SC_DIR = REPO_ROOT / "scripts" / "sc"
for candidate in (SC_BUILD_DIR, SC_DIR):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tdd_script = _load_module("sc_build_tdd_module", "scripts/sc/build/tdd.py")


class _FakeTriplet:
    def __init__(self, task_id: str = "14", title: str = "Demo task", status: str = "in-progress") -> None:
        self.task_id = task_id
        self.master = {"title": title, "status": status}
        self.taskdoc_path = "docs/tasks/task-14.md"

    def adr_refs(self) -> list[str]:
        return ["ADR-0005"]

    def arch_refs(self) -> list[str]:
        return ["CH07"]

    def overlay(self) -> str:
        return "docs/architecture/overlays/PRD-demo/08/_index.md"


class GreenPrerequisiteSurfaceTests(unittest.TestCase):
    def test_pure_human_pending_preflight_can_enter_green_without_machine_red(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "sc-build-tdd"
            out_dir.mkdir(parents=True, exist_ok=True)
            triplet = SimpleNamespace(
                task_id="14",
                back={
                    "acceptance": ["Combat pacing must be readable during playtest."],
                    "acceptance_verification": {
                        "ACC:T14.1": {
                            "verification_surface": "human-experience",
                            "primary_evidence": ["logs/manual/task-14-playtest.md"],
                            "secondary_evidence": [],
                            "human_evidence_required": True,
                            "human_evidence_status": "pending",
                        }
                    },
                },
                gameplay=None,
            )
            with mock.patch.object(tdd_script, "_find_latest_red_first_summary") as red_summary:
                result = tdd_script.validate_green_red_prerequisite(
                    task_id="14",
                    out_dir=out_dir,
                    triplet=triplet,
                )
            self.assertEqual(0, result["rc"])
            self.assertTrue(result["manual_only"])
            self.assertEqual(["ACC:T14.1"], result["human_obligations"])
            red_summary.assert_not_called()

    def test_mixed_human_and_automated_obligations_still_require_machine_red(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "sc-build-tdd"
            out_dir.mkdir(parents=True, exist_ok=True)
            triplet = SimpleNamespace(
                task_id="14",
                back={
                    "acceptance": ["Combat reward and pacing obligations."],
                    "acceptance_verification": {
                        "ACC:T14.1": {
                            "obligations": [
                                {
                                    "obligation_id": "reward-core",
                                    "verification_surface": "core-behavior",
                                    "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                                    "secondary_evidence": [],
                                    "human_evidence_required": False,
                                },
                                {
                                    "obligation_id": "pacing-human",
                                    "verification_surface": "human-experience",
                                    "primary_evidence": ["logs/manual/task-14-playtest.md"],
                                    "secondary_evidence": [],
                                    "human_evidence_required": True,
                                    "human_evidence_status": "pending",
                                },
                            ]
                        }
                    },
                },
                gameplay=None,
            )
            with mock.patch.object(tdd_script, "_find_latest_red_first_summary", return_value=(None, {})):
                result = tdd_script.validate_green_red_prerequisite(
                    task_id="14",
                    out_dir=out_dir,
                    triplet=triplet,
                )
            self.assertEqual(1, result["rc"])
            self.assertFalse(result["manual_only"])
            self.assertEqual(["ACC:T14.1#reward-core"], result["automated_obligations"])
            self.assertIn("missing red-first summary", " ".join(result["errors"]))

    def test_partial_surface_metadata_cannot_use_manual_item_to_waive_red(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "sc-build-tdd"
            out_dir.mkdir(parents=True, exist_ok=True)
            triplet = SimpleNamespace(
                task_id="14",
                back={
                    "acceptance": [
                        "Combat pacing must be readable during playtest.",
                        "Reward totals must remain deterministic.",
                    ],
                    "acceptance_verification": {
                        "ACC:T14.1": {
                            "verification_surface": "human-experience",
                            "primary_evidence": ["logs/manual/task-14-playtest.md"],
                            "secondary_evidence": [],
                            "human_evidence_required": True,
                            "human_evidence_status": "pending",
                        }
                    },
                },
                gameplay=None,
            )
            with mock.patch.object(tdd_script, "_find_latest_red_first_summary", return_value=(None, {})):
                result = tdd_script.validate_green_red_prerequisite(
                    task_id="14",
                    out_dir=out_dir,
                    triplet=triplet,
                )
            self.assertEqual(1, result["rc"])
            self.assertEqual(["ACC:T14.2"], result["unclassified_anchors"])
            self.assertIn("cannot waive RED", " ".join(result["errors"]))

    def test_mvg_integration_journey_does_not_require_task_local_red_first(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "sc-build-tdd"
            out_dir.mkdir(parents=True, exist_ok=True)
            triplet = SimpleNamespace(
                task_id="14",
                back={
                    "acceptance": ["Combat to reward integrated journey."],
                    "acceptance_verification": {
                        "ACC:T14.1": {
                            "verification_surface": "player-journey",
                            "journey_scope": "mvg-critical",
                            "primary_evidence": ["docs/testing/mvg/m1-critical.json"],
                            "secondary_evidence": [],
                            "human_evidence_required": False,
                        }
                    },
                },
                gameplay=None,
            )
            with mock.patch.object(tdd_script, "_find_latest_red_first_summary") as red_summary:
                result = tdd_script.validate_green_red_prerequisite(
                    task_id="14",
                    out_dir=out_dir,
                    triplet=triplet,
                )

            self.assertEqual(0, result["rc"])
            self.assertTrue(result["red_not_required"])
            self.assertFalse(result["manual_only"])
            self.assertEqual(["ACC:T14.1"], result["integration_obligations"])
            red_summary.assert_not_called()



class BuildTddOrchestrationTests(unittest.TestCase):
    def test_direct_red_does_not_consume_a_report_from_an_earlier_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            old_trx = out_dir / "direct-red.trx"
            old_trx.write_text(
                '<TestRun><Results><UnitTestResult testName="Game.Core.Tests.Tasks.Task14RedTests.ShouldFail" outcome="Failed">'
                '<Output><ErrorInfo><Message>Assert.Equal() Failure: Expected: 1 Actual: 0</Message></ErrorInfo></Output>'
                '</UnitTestResult></Results></TestRun>', encoding="utf-8",
            )
            with mock.patch.object(tdd_script, "run_cmd", return_value=(1, "Test host exited unexpectedly")):
                step = tdd_script.run_dotnet_test_filtered("14", solution="Game.sln", configuration="Debug", out_dir=out_dir)
            report = tdd_script.evaluate_direct_dotnet_red(
                test_step=step, verify_log_text=(out_dir / "dotnet-test-filtered.log").read_text(encoding="utf-8"),
                expected_test_refs=["Game.Core.Tests/Tasks/Task14RedTests.cs"],
            )
            self.assertNotEqual(old_trx, Path(step["trx_path"]))
            self.assertEqual("fail", report["status"])
            self.assertEqual("verification_report_missing", report["reason"])

    def test_red_should_stop_when_context_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "red", "--task-id", "14"]
            preflight_step = {"name": "task_preflight", "rc": 0, "status": "ok", "log": str(out_dir / "task-preflight.log")}
            analyze_step = {"name": "sc-analyze", "rc": 0, "status": "ok", "log": str(out_dir / "sc-analyze.log")}
            ctx_step = {"name": "validate_task_context_required_fields", "rc": 1, "status": "fail", "log": str(out_dir / "ctx.log")}
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "run_task_preflight", return_value=preflight_step), \
                mock.patch.object(tdd_script, "run_sc_analyze_task_context", return_value=analyze_step), \
                mock.patch.object(tdd_script, "validate_task_context_required_fields", return_value=ctx_step), \
                mock.patch.object(tdd_script, "run_dotnet_test_filtered") as filtered_mock, \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(1, rc)
            filtered_mock.assert_not_called()
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("fail", summary["status"])
            self.assertEqual(
                ["task_preflight", "sc-analyze", "validate_task_context_required_fields"],
                [item["name"] for item in summary["steps"]],
            )

    def test_red_should_return_two_when_task_test_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "red", "--task-id", "14"]
            preflight_step = {"name": "task_preflight", "rc": 0, "status": "ok", "log": str(out_dir / "task-preflight.log")}
            analyze_step = {"name": "sc-analyze", "rc": 0, "status": "ok", "log": str(out_dir / "sc-analyze.log")}
            ctx_step = {"name": "validate_task_context_required_fields", "rc": 0, "status": "ok", "log": str(out_dir / "ctx.log")}
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "run_task_preflight", return_value=preflight_step), \
                mock.patch.object(tdd_script, "run_sc_analyze_task_context", return_value=analyze_step), \
                mock.patch.object(tdd_script, "validate_task_context_required_fields", return_value=ctx_step), \
                mock.patch.object(tdd_script, "ensure_red_test_exists", return_value=None), \
                mock.patch.object(tdd_script, "run_dotnet_test_filtered") as filtered_mock:
                rc = tdd_script.main()

            self.assertEqual(2, rc)
            filtered_mock.assert_not_called()
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("fail", summary["status"])
            self.assertEqual(
                ["task_preflight", "sc-analyze", "validate_task_context_required_fields"],
                [item["name"] for item in summary["steps"]],
            )

    def test_green_should_append_coverage_hotspots_when_run_dotnet_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "green", "--task-id", "14"]
            prereq_step = {"name": "validate_green_red_prerequisite", "rc": 0, "status": "ok", "log": str(out_dir / "prereq.log")}
            preflight_step = {"name": "task_preflight", "rc": 0, "status": "ok", "log": str(out_dir / "task-preflight.log")}
            analyze_step = {"name": "sc-analyze", "rc": 0, "status": "ok", "log": str(out_dir / "sc-analyze.log")}
            ctx_step = {"name": "validate_task_context_required_fields", "rc": 0, "status": "ok", "log": str(out_dir / "ctx.log")}
            green_step = {"name": "run_dotnet", "rc": 2, "log": str(out_dir / "run_dotnet.log"), "stdout": "coverage out", "status": "fail"}
            hotspots_step = {"name": "coverage_hotspots", "rc": 0, "log": str(out_dir / "coverage-hotspots.txt"), "status": "ok"}
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "validate_green_red_prerequisite", return_value=prereq_step), \
                mock.patch.object(tdd_script, "run_task_preflight", return_value=preflight_step), \
                mock.patch.object(tdd_script, "run_sc_analyze_task_context", return_value=analyze_step), \
                mock.patch.object(tdd_script, "validate_task_context_required_fields", return_value=ctx_step), \
                mock.patch.object(tdd_script, "run_green_gate", return_value=green_step), \
                mock.patch.object(tdd_script, "write_coverage_hotspots", return_value=hotspots_step), \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(1, rc)
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("fail", summary["status"])
            self.assertEqual(
                [
                    "validate_green_red_prerequisite",
                    "task_preflight",
                    "sc-analyze",
                    "validate_task_context_required_fields",
                    "run_dotnet",
                    "coverage_hotspots",
                ],
                [item["name"] for item in summary["steps"]],
            )

    def test_refactor_should_fail_when_any_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "refactor", "--task-id", "14"]
            prereq_step = {"name": "validate_refactor_green_prerequisite", "rc": 0, "status": "ok", "log": str(out_dir / "prereq.log")}
            preflight_step = {"name": "task_preflight", "rc": 0, "status": "ok", "log": str(out_dir / "task-preflight.log")}
            analyze_step = {"name": "sc-analyze", "rc": 0, "status": "ok", "log": str(out_dir / "sc-analyze.log")}
            ctx_step = {"name": "validate_task_context_required_fields", "rc": 0, "status": "ok", "log": str(out_dir / "ctx.log")}
            checks = [
                {"name": "validate_task_test_refs", "rc": 0, "status": "ok", "log": str(out_dir / "task-test-refs.log")},
                {"name": "validate_acceptance_refs", "rc": 1, "status": "fail", "log": str(out_dir / "validate_acceptance_refs.log")},
            ]
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "validate_refactor_green_prerequisite", return_value=prereq_step), \
                mock.patch.object(tdd_script, "run_task_preflight", return_value=preflight_step), \
                mock.patch.object(tdd_script, "run_sc_analyze_task_context", return_value=analyze_step), \
                mock.patch.object(tdd_script, "validate_task_context_required_fields", return_value=ctx_step), \
                mock.patch.object(tdd_script, "run_refactor_checks", return_value=checks), \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(1, rc)
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("fail", summary["status"])
            self.assertEqual(
                [
                    "validate_refactor_green_prerequisite",
                    "task_preflight",
                    "sc-analyze",
                    "validate_task_context_required_fields",
                    "validate_task_test_refs",
                    "validate_acceptance_refs",
                ],
                [item["name"] for item in summary["steps"]],
            )

    def test_green_should_fail_fast_when_red_prerequisite_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "green", "--task-id", "14"]
            prereq_step = {"name": "validate_green_red_prerequisite", "rc": 1, "status": "fail", "log": str(out_dir / "prereq.log")}
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "validate_green_red_prerequisite", return_value=prereq_step), \
                mock.patch.object(tdd_script, "run_task_preflight") as preflight_mock, \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(1, rc)
            preflight_mock.assert_not_called()
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(["validate_green_red_prerequisite"], [item["name"] for item in summary["steps"]])

    def test_refactor_should_fail_fast_when_green_prerequisite_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "refactor", "--task-id", "14"]
            prereq_step = {"name": "validate_refactor_green_prerequisite", "rc": 1, "status": "fail", "log": str(out_dir / "prereq.log")}
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "validate_refactor_green_prerequisite", return_value=prereq_step), \
                mock.patch.object(tdd_script, "run_task_preflight") as preflight_mock, \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(1, rc)
            preflight_mock.assert_not_called()
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(["validate_refactor_green_prerequisite"], [item["name"] for item in summary["steps"]])

    def test_run_green_gate_should_restore_coverage_environment_after_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            previous = {
                "COVERAGE_LINES_MIN": "33",
                "COVERAGE_BRANCHES_MIN": "22",
                "COVERAGE_GATE_MODE": "legacy",
            }
            observed: dict[str, str | None] = {}

            def _fake_run_cmd(cmd, cwd, timeout_sec):
                observed["lines"] = tdd_script.os.environ.get("COVERAGE_LINES_MIN")
                observed["branches"] = tdd_script.os.environ.get("COVERAGE_BRANCHES_MIN")
                observed["mode"] = tdd_script.os.environ.get("COVERAGE_GATE_MODE")
                return 0, "ok"

            with mock.patch.dict(tdd_script.os.environ, previous, clear=False), \
                mock.patch.object(tdd_script, "run_cmd", side_effect=_fake_run_cmd):
                step = tdd_script.run_green_gate(
                    task_id="14",
                    triplet=_FakeTriplet(),
                    solution="Game.sln",
                    configuration="Debug",
                    out_dir=out_dir,
                    coverage_gate=True,
                    coverage_lines_min=70,
                    coverage_branches_min=60,
                    green_scope="all",
                )
                self.assertEqual("33", tdd_script.os.environ.get("COVERAGE_LINES_MIN"))
                self.assertEqual("22", tdd_script.os.environ.get("COVERAGE_BRANCHES_MIN"))
                self.assertEqual("legacy", tdd_script.os.environ.get("COVERAGE_GATE_MODE"))

            self.assertEqual(0, step["rc"])
            self.assertEqual("70", observed["lines"])
            self.assertEqual("60", observed["branches"])
            self.assertEqual("hard", observed["mode"])

    def test_green_should_resolve_test_solution_when_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "sc-build-tdd"
            argv = ["tdd.py", "--stage", "green", "--task-id", "14"]
            prereq_step = {"name": "validate_green_red_prerequisite", "rc": 0, "status": "ok", "log": str(out_dir / "prereq.log")}
            preflight_step = {"name": "task_preflight", "rc": 0, "status": "ok", "log": str(out_dir / "task-preflight.log")}
            analyze_step = {"name": "sc-analyze", "rc": 0, "status": "ok", "log": str(out_dir / "sc-analyze.log")}
            ctx_step = {"name": "validate_task_context_required_fields", "rc": 0, "status": "ok", "log": str(out_dir / "ctx.log")}

            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(tdd_script, "ci_dir", return_value=out_dir), \
                mock.patch.object(tdd_script, "resolve_triplet", return_value=_FakeTriplet()), \
                mock.patch.object(tdd_script, "resolve_test_solution_arg", return_value="Game.sln") as solution_mock, \
                mock.patch.object(tdd_script, "validate_green_red_prerequisite", return_value=prereq_step), \
                mock.patch.object(tdd_script, "run_task_preflight", return_value=preflight_step), \
                mock.patch.object(tdd_script, "run_sc_analyze_task_context", return_value=analyze_step), \
                mock.patch.object(tdd_script, "validate_task_context_required_fields", return_value=ctx_step), \
                mock.patch.object(tdd_script, "run_green_gate", return_value={"name": "run_dotnet", "rc": 0, "status": "ok", "log": str(out_dir / "run.log")}) as green_mock, \
                mock.patch.object(tdd_script, "assert_no_new_contract_files", return_value=None):
                rc = tdd_script.main()

            self.assertEqual(0, rc)
            solution_mock.assert_called_once()
            self.assertEqual("Game.sln", green_mock.call_args.kwargs["solution"])
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("Game.sln", summary["solution"])


if __name__ == "__main__":
    unittest.main()
