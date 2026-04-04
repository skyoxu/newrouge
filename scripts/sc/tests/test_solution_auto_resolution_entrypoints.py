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


run_dotnet = _load_module("run_dotnet_auto_solution_module", "scripts/python/run_dotnet.py")
quality_gates = _load_module("quality_gates_auto_solution_module", "scripts/python/quality_gates.py")
ci_pipeline = _load_module("ci_pipeline_auto_solution_module", "scripts/python/ci_pipeline.py")


class SolutionAutoResolutionEntrypointsTests(unittest.TestCase):
    def test_run_dotnet_should_prefer_repo_named_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "myrepo"
            root.mkdir(parents=True, exist_ok=True)
            (root / "Game.sln").write_text("", encoding="utf-8")
            (root / "NewRouge.sln").write_text("", encoding="utf-8")
            (root / "myrepo.sln").write_text("", encoding="utf-8")

            resolved = run_dotnet._resolve_default_solution(str(root))

        self.assertEqual("myrepo.sln", resolved)

    def test_quality_gates_should_fallback_to_newrouge_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Game.sln").write_text("", encoding="utf-8")
            (root / "NewRouge.sln").write_text("", encoding="utf-8")

            resolved = quality_gates._resolve_default_solution(root)

        self.assertEqual("NewRouge.sln", resolved)

    def test_quality_gates_main_should_use_auto_resolved_solution_when_omitted(self) -> None:
        fake_dotnet = Path("C:/dotnet/dotnet.exe")
        with mock.patch.object(quality_gates, "_resolve_default_solution", return_value="NewRouge.sln"), \
            mock.patch.object(quality_gates, "_ensure_dotnet_on_path", return_value=fake_dotnet), \
            mock.patch.object(quality_gates, "_write_env_evidence"), \
            mock.patch.object(quality_gates, "_require_prereqs", return_value=True), \
            mock.patch.object(quality_gates, "run_ci_pipeline", return_value=0) as ci_mock, \
            mock.patch.object(quality_gates, "run_task0056_audit_validation", return_value={"enabled": False, "rc": 0}), \
            mock.patch.object(quality_gates, "_resolve_selected_suites", return_value=([], [])), \
            mock.patch.object(quality_gates, "_collect_junit_artifact", return_value={"status": "skipped"}), \
            mock.patch.object(quality_gates, "_write_quality_summary", return_value={"overall_gate_conclusion": "pass", "suites": {}, "gdunit_suites": {}}), \
            mock.patch.object(quality_gates, "_write_task_0054_record"), \
            mock.patch.object(quality_gates, "write_task0056_record", return_value={"valid": True}):
            rc = quality_gates.main(["all"])

        self.assertEqual(0, rc)
        ci_mock.assert_called_once()
        self.assertEqual("NewRouge.sln", ci_mock.call_args[0][0])

    def test_ci_pipeline_should_fallback_to_newrouge_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Game.sln").write_text("", encoding="utf-8")
            (root / "NewRouge.sln").write_text("", encoding="utf-8")

            resolved = ci_pipeline._resolve_default_solution(str(root))

        self.assertEqual("NewRouge.sln", resolved)

    # ACC:T55.6
    def test_run_dotnet_main_should_treat_auto_solution_as_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(run_dotnet, "_resolve_default_solution", return_value="NewRouge.sln"), \
                mock.patch.object(run_dotnet.os, "getcwd", return_value=str(root)), \
                mock.patch.object(run_dotnet, "run_cmd", return_value=(1, "restore failed")) as run_cmd_mock:
                rc = run_dotnet.main(["--solution", "auto"])

        self.assertEqual(1, rc)
        self.assertGreaterEqual(run_cmd_mock.call_count, 1)
        self.assertEqual(["dotnet", "restore", "NewRouge.sln"], run_cmd_mock.call_args_list[0].args[0])

    def test_run_dotnet_main_should_fallback_to_test_project_when_solution_has_no_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "NewRouge.sln").write_text(
                'Microsoft Visual Studio Solution File, Format Version 12.00\n'
                'Project("{GUID}") = "Game.Core", "Game.Core\\Game.Core.csproj", "{ID}"\n'
                "EndProject\n",
                encoding="utf-8",
            )
            (root / "Game.Core.Tests").mkdir(parents=True, exist_ok=True)
            (root / "Game.Core.Tests" / "Game.Core.Tests.csproj").write_text("<Project />", encoding="utf-8")
            with mock.patch.object(run_dotnet, "_resolve_default_solution", return_value="NewRouge.sln"), \
                mock.patch.object(run_dotnet.os, "getcwd", return_value=str(root)), \
                mock.patch.object(run_dotnet, "run_cmd", return_value=(1, "restore failed")) as run_cmd_mock:
                rc = run_dotnet.main(["--solution", "auto"])

        self.assertEqual(1, rc)
        self.assertGreaterEqual(run_cmd_mock.call_count, 1)
        self.assertEqual(
            ["dotnet", "restore", "Game.Core.Tests/Game.Core.Tests.csproj"],
            run_cmd_mock.call_args_list[0].args[0],
        )

    # ACC:T55.1
    # ACC:T55.2
    def test_run_dotnet_threshold_resolution_should_prefer_threshold_env_and_default_to_90_85(self) -> None:
        with mock.patch.dict(run_dotnet.os.environ, {}, clear=True):
            lines_min, lines_src = run_dotnet._resolve_threshold_value(
                preferred_key="COVERAGE_LINES_THRESHOLD",
                legacy_key="COVERAGE_LINES_MIN",
                default_value=run_dotnet.DEFAULT_LINES_THRESHOLD,
            )
            branches_min, branches_src = run_dotnet._resolve_threshold_value(
                preferred_key="COVERAGE_BRANCHES_THRESHOLD",
                legacy_key="COVERAGE_BRANCHES_MIN",
                default_value=run_dotnet.DEFAULT_BRANCHES_THRESHOLD,
            )
        self.assertEqual(run_dotnet.DEFAULT_LINES_THRESHOLD, lines_min)
        self.assertEqual(run_dotnet.DEFAULT_BRANCHES_THRESHOLD, branches_min)
        self.assertEqual("default", lines_src)
        self.assertEqual("default", branches_src)

        with mock.patch.dict(
            run_dotnet.os.environ,
            {
                "COVERAGE_LINES_THRESHOLD": "93",
                "COVERAGE_LINES_MIN": "95",
                "COVERAGE_BRANCHES_MIN": "86",
            },
            clear=True,
        ):
            lines_min, lines_src = run_dotnet._resolve_threshold_value(
                preferred_key="COVERAGE_LINES_THRESHOLD",
                legacy_key="COVERAGE_LINES_MIN",
                default_value=run_dotnet.DEFAULT_LINES_THRESHOLD,
            )
            branches_min, branches_src = run_dotnet._resolve_threshold_value(
                preferred_key="COVERAGE_BRANCHES_THRESHOLD",
                legacy_key="COVERAGE_BRANCHES_MIN",
                default_value=run_dotnet.DEFAULT_BRANCHES_THRESHOLD,
            )
        self.assertEqual(93.0, lines_min)
        self.assertEqual("COVERAGE_LINES_THRESHOLD", lines_src)
        self.assertEqual(86.0, branches_min)
        self.assertEqual("COVERAGE_BRANCHES_MIN", branches_src)

    # ACC:T55.4
    def test_quality_gates_should_resolve_coverage_gate_summary_from_unit_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date = "2026-04-04"
            unit_summary_dir = root / "logs" / "unit" / date
            unit_summary_dir.mkdir(parents=True, exist_ok=True)
            (unit_summary_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "measured_line_coverage": 91.2,
                        "measured_branch_coverage": 88.4,
                        "effective_thresholds": {
                            "lines_min": 90,
                            "branches_min": 85,
                            "lines_source": "default",
                            "branches_source": "default",
                        },
                        "gate_mode": "hard",
                        "pass": True,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(quality_gates, "_repo_root", return_value=root), \
                mock.patch.dict(quality_gates.os.environ, {}, clear=True):
                coverage = quality_gates._resolve_coverage_gate_summary(date)

        self.assertEqual("ok", coverage["status"])
        self.assertEqual("hard", coverage["gate_mode"])
        self.assertEqual(91.2, coverage["measured_line_coverage"])
        self.assertEqual(88.4, coverage["measured_branch_coverage"])
        self.assertTrue(bool(coverage["pass"]))
        self.assertIn("effective_thresholds", coverage)

    def test_quality_gates_should_mark_missing_when_unit_summary_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(quality_gates, "_repo_root", return_value=root), \
                mock.patch.dict(quality_gates.os.environ, {}, clear=True):
                coverage = quality_gates._resolve_coverage_gate_summary("2026-04-04")

        self.assertEqual("missing", coverage["status"])
        self.assertFalse(bool(coverage["pass"]))
        self.assertEqual("failed", coverage["suite_status"])

    def test_quality_gates_summary_should_fail_when_hard_coverage_gate_is_not_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date = "2026-04-04"
            summary_path = root / "logs" / "ci" / date / "quality-gates" / "summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)

            suite_runs = {
                "adapters": quality_gates._suite_record(gate_level="hard", selected=False, executed=False, status="skipped", rc=None),
                "security": quality_gates._suite_record(gate_level="hard", selected=False, executed=False, status="skipped", rc=None),
                "integration": quality_gates._suite_record(gate_level="soft", selected=False, executed=False, status="skipped", rc=None),
                "ui": quality_gates._suite_record(gate_level="soft", selected=False, executed=False, status="skipped", rc=None),
            }
            coverage_gate = {
                "status": "ok",
                "suite_status": "failed",
                "pass": False,
                "threshold_ok": False,
                "gate_mode": "hard",
                "gate_mode_source": "unit_summary",
                "measured_line_coverage": 80.0,
                "measured_branch_coverage": 70.0,
                "effective_thresholds": {"lines_min": 90.0, "branches_min": 85.0},
                "warnings": [],
                "summary_path": f"logs/unit/{date}/summary.json",
            }
            with mock.patch.object(quality_gates, "_repo_root", return_value=root):
                payload = quality_gates._write_quality_summary(
                    date=date,
                    security_profile="host-safe",
                    suite_runs=suite_runs,
                    ci_rc=0,
                    smoke_rc=None,
                    smoke_enabled=False,
                    invalid_suites=[],
                    junit_artifact={"status": "skipped"},
                    coverage_gate=coverage_gate,
                )

            self.assertEqual("fail", payload["overall_gate_conclusion"])
            written = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual("hard", written["gate_mode"])
            self.assertEqual(80.0, written["measured_line_coverage"])
            self.assertFalse(bool(written["pass"]))

    # ACC:T55.3
    def test_quality_gates_should_differentiate_soft_vs_hard_for_same_below_threshold_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date = "2026-04-04"
            unit_summary_dir = root / "logs" / "unit" / date
            unit_summary_dir.mkdir(parents=True, exist_ok=True)
            summary_path = unit_summary_dir / "summary.json"

            below_threshold_payload = {
                "measured_line_coverage": 80.0,
                "measured_branch_coverage": 70.0,
                "effective_thresholds": {"lines_min": 90, "branches_min": 85},
                "pass": False,
            }

            with mock.patch.object(quality_gates, "_repo_root", return_value=root), \
                mock.patch.dict(quality_gates.os.environ, {}, clear=True):
                summary_path.write_text(
                    json.dumps({**below_threshold_payload, "gate_mode": "soft"}),
                    encoding="utf-8",
                )
                soft = quality_gates._resolve_coverage_gate_summary(date)

                summary_path.write_text(
                    json.dumps({**below_threshold_payload, "gate_mode": "hard"}),
                    encoding="utf-8",
                )
                hard = quality_gates._resolve_coverage_gate_summary(date)

        self.assertEqual("warn", soft["suite_status"])
        self.assertTrue(bool(soft["pass"]))
        self.assertEqual("soft", soft["gate_mode"])
        self.assertEqual("failed", hard["suite_status"])
        self.assertFalse(bool(hard["pass"]))
        self.assertEqual("hard", hard["gate_mode"])


if __name__ == "__main__":
    unittest.main()
