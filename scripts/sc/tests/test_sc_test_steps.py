#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

import _sc_test_steps as sc_steps  # noqa: E402


class ScTestStepsUnitFallbackTests(unittest.TestCase):
    def test_run_unit_should_retry_without_filter_when_task_scoped_coverage_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            first_out = "RUN_DOTNET status=coverage_failed line=0.0% branch=0.0 out=logs/unit/2026-03-30\n"
            second_out = "RUN_DOTNET status=ok line=92.0% branch=86.0 out=logs/unit/2026-03-30\n"

            with (
                mock.patch.object(sc_steps, "repo_root", return_value=REPO_ROOT),
                mock.patch.object(sc_steps, "today_str", return_value="2026-03-30"),
                mock.patch.object(sc_steps, "task_scoped_cs_refs", return_value=["Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs"]),
                mock.patch.object(sc_steps, "build_dotnet_filter_from_cs_refs", return_value="FullyQualifiedName~Task0056AcceptanceTests"),
                mock.patch.object(sc_steps, "run_cmd", side_effect=[(2, first_out), (0, second_out)]),
            ):
                step = sc_steps.run_unit(out_dir, "Game.sln", "Debug", run_id="r1", task_id="56")

            self.assertEqual(0, int(step["rc"]))
            self.assertEqual("ok", step["status"])
            self.assertEqual(
                ["py", "-3", "scripts/python/run_dotnet.py", "--solution", "Game.sln", "--configuration", "Debug"],
                step["cmd"],
            )
            log_text = (out_dir / "unit.log").read_text(encoding="utf-8")
            self.assertIn("retrying unit without task filter", log_text)
            self.assertIn("fallback_rc: 0", log_text)

    def test_run_unit_should_keep_original_failure_when_fallback_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            first_out = "RUN_DOTNET status=coverage_failed line=0.0% branch=0.0 out=logs/unit/2026-03-30\n"
            second_out = "RUN_DOTNET status=tests_failed line=10.0% branch=5.0 out=logs/unit/2026-03-30\n"

            with (
                mock.patch.object(sc_steps, "repo_root", return_value=REPO_ROOT),
                mock.patch.object(sc_steps, "today_str", return_value="2026-03-30"),
                mock.patch.object(sc_steps, "task_scoped_cs_refs", return_value=["Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs"]),
                mock.patch.object(sc_steps, "build_dotnet_filter_from_cs_refs", return_value="FullyQualifiedName~Task0056AcceptanceTests"),
                mock.patch.object(sc_steps, "run_cmd", side_effect=[(2, first_out), (1, second_out)]),
            ):
                step = sc_steps.run_unit(out_dir, "Game.sln", "Debug", run_id="r2", task_id="56")

            self.assertEqual(2, int(step["rc"]))
            self.assertEqual("fail", step["status"])
            self.assertIn("--filter", step["cmd"])

    def test_run_unit_should_retry_without_filter_when_task_scoped_coverage_is_nonzero_but_below_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            first_out = "RUN_DOTNET status=coverage_failed line=1.1% branch=0.5 out=logs/unit/2026-03-30\n"
            second_out = "RUN_DOTNET status=ok line=92.0% branch=86.0 out=logs/unit/2026-03-30\n"

            with (
                mock.patch.object(sc_steps, "repo_root", return_value=REPO_ROOT),
                mock.patch.object(sc_steps, "today_str", return_value="2026-03-30"),
                mock.patch.object(sc_steps, "task_scoped_cs_refs", return_value=["Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs"]),
                mock.patch.object(sc_steps, "build_dotnet_filter_from_cs_refs", return_value="FullyQualifiedName~Task0056AcceptanceTests"),
                mock.patch.object(sc_steps, "run_cmd", side_effect=[(2, first_out), (0, second_out)]),
            ):
                step = sc_steps.run_unit(out_dir, "Game.sln", "Debug", run_id="r5", task_id="56")

            self.assertEqual(0, int(step["rc"]))
            self.assertEqual("ok", step["status"])
            self.assertEqual(
                ["py", "-3", "scripts/python/run_dotnet.py", "--solution", "Game.sln", "--configuration", "Debug"],
                step["cmd"],
            )
            log_text = (out_dir / "unit.log").read_text(encoding="utf-8")
            self.assertIn("task-scoped coverage gate failed; retrying unit without task filter", log_text)
            self.assertIn("fallback_rc: 0", log_text)

    def test_run_gdunit_hard_should_fail_fast_when_task_scoped_refs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir(parents=True, exist_ok=True)
            out_dir = Path(td) / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            with (
                mock.patch.object(sc_steps, "repo_root", return_value=root),
                mock.patch.object(sc_steps, "today_str", return_value="2026-04-01"),
                mock.patch.object(sc_steps, "task_scoped_gdunit_refs", return_value=[]),
            ):
                step = sc_steps.run_gdunit_hard(out_dir, "C:/Godot/Godot.exe", 120, run_id="r3", task_id="56")

            self.assertEqual(2, int(step["rc"]))
            self.assertEqual("fail", step["status"])
            self.assertEqual("missing_task_scoped_gdunit_refs", step["reason"])
            self.assertIn("FAIL: no task-scoped gdunit refs found", (out_dir / "gdunit-hard.log").read_text(encoding="utf-8"))

    def test_run_gdunit_hard_should_only_use_task_scoped_refs_when_task_id_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            (root / "Tests.Godot").mkdir(parents=True, exist_ok=True)
            out_dir = Path(td) / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            with (
                mock.patch.object(sc_steps, "repo_root", return_value=root),
                mock.patch.object(sc_steps, "today_str", return_value="2026-04-01"),
                mock.patch.object(sc_steps, "task_scoped_gdunit_refs", return_value=["tests/Tasks/test_task0056_acceptance.gd"]),
                mock.patch.object(sc_steps, "run_cmd", return_value=(0, "ok")),
            ):
                step = sc_steps.run_gdunit_hard(out_dir, "C:/Godot/Godot.exe", 120, run_id="r4", task_id="56")

            self.assertEqual(0, int(step["rc"]))
            self.assertEqual("ok", step["status"])
            cmd = step["cmd"]
            self.assertIn("--add", cmd)
            self.assertIn("tests/Tasks/test_task0056_acceptance.gd", cmd)
            self.assertNotIn("tests/Scenes", cmd)
            self.assertNotIn("tests/UI", cmd)


if __name__ == "__main__":
    unittest.main()
