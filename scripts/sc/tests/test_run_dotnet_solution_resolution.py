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


run_dotnet = _load_module("run_dotnet_test_module", "scripts/python/run_dotnet.py")


class RunDotnetSolutionResolutionTests(unittest.TestCase):
    def test_main_should_resolve_test_solution_when_auto(self) -> None:
        commands: list[list[str]] = []

        def _fake_run_cmd(args, cwd=None, timeout=900_000):
            commands.append(list(args))
            return 1, "restore failed\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "templategame"
            root.mkdir(parents=True, exist_ok=True)
            (root / "templategame.sln").write_text("", encoding="utf-8")
            (root / "Game.sln").write_text(
                'Project("{x}") = "Game.Core.Tests", "Game.Core.Tests\\\\Game.Core.Tests.csproj", "{2}"\nEndProject\n',
                encoding="utf-8",
            )
            argv = ["run_dotnet.py", "--solution", "auto", "--configuration", "Debug"]
            with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(run_dotnet.os, "getcwd", return_value=str(root)), \
                mock.patch.object(run_dotnet, "run_cmd", side_effect=_fake_run_cmd):
                rc = run_dotnet.main()

            self.assertEqual(1, rc)
            self.assertEqual(["dotnet", "restore", "NewRouge.sln"], commands[0])
            summary = json.loads((root / "logs" / "unit" / run_dotnet.dt.date.today().strftime("%Y-%m-%d") / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("NewRouge.sln", summary["solution"])

    def test_should_detect_retryable_coverlet_file_lock_abort_from_output(self) -> None:
        output = """
The active test run was aborted. Reason: Test host process crashed
Data collector 'XPlat code coverage' message: [coverlet]Coverlet.Collector.Utilities.CoverletDataCollectorException: CoverletCoverageDataCollector: Failed to get coverage result
System.IO.IOException: The process cannot access the file 'D:\\a\\newrouge\\newrouge\\Game.Core.Tests\\bin\\Debug\\net8.0\\Game.Core.dll' because it is being used by another process.
Passed!  - Failed:     0, Passed:   950, Skipped:     0, Total:   950, Duration: 5 s - Game.Core.Tests.dll (net8.0)
Test Run Aborted.
"""
        self.assertTrue(run_dotnet._is_retryable_coverlet_file_lock_abort(output))

    def test_main_should_retry_when_coverlet_file_lock_abort_happens_even_if_tests_passed(self) -> None:
        commands: list[list[str]] = []

        first_test_output = """
Starting test execution, please wait...
The active test run was aborted. Reason: Test host process crashed
Data collector 'XPlat code coverage' message: [coverlet]Coverlet.Collector.Utilities.CoverletDataCollectorException: CoverletCoverageDataCollector: Failed to get coverage result
System.IO.IOException: The process cannot access the file 'D:\\a\\newrouge\\newrouge\\Game.Core.Tests\\bin\\Debug\\net8.0\\Game.Core.dll' because it is being used by another process.
Passed!  - Failed:     0, Passed:   950, Skipped:     0, Total:   950, Duration: 5 s - Game.Core.Tests.dll (net8.0)
Test Run Aborted.
"""
        second_test_output = r"D:\repo\Game.Core.Tests\TestResults\tests.trx" + "\n" + r"D:\repo\Game.Core.Tests\TestResults\abc\coverage.cobertura.xml"

        def _fake_run_cmd(args, cwd=None, timeout=900_000):
            commands.append(list(args))
            if args[:2] == ["dotnet", "restore"]:
                return 0, "restore ok\n"
            dotnet_test_calls = [cmd for cmd in commands if cmd[:2] == ["dotnet", "test"]]
            if len(dotnet_test_calls) == 1:
                return 0, first_test_output
            results_dir = Path(args[args.index("--results-directory") + 1])
            results_dir.mkdir(parents=True, exist_ok=True)
            (results_dir / "tests.trx").write_text("trx", encoding="utf-8")
            (results_dir / "coverage.cobertura.xml").write_text(
                '<coverage lines-covered="95" lines-valid="100" branches-covered="90" branches-valid="100"></coverage>',
                encoding="utf-8",
            )
            return 0, second_test_output

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "newrouge"
            root.mkdir(parents=True, exist_ok=True)
            (root / "NewRouge.sln").write_text("", encoding="utf-8")

            with mock.patch.object(run_dotnet.os, "getcwd", return_value=str(root)), \
                mock.patch.object(run_dotnet, "run_cmd", side_effect=_fake_run_cmd), \
                mock.patch.object(run_dotnet, "_best_effort_cleanup_testhosts", return_value=None), \
                mock.patch.dict(run_dotnet.os.environ, {"DOTNET_TEST_RETRY_ON_FAIL": "1"}, clear=False):
                rc = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(root / "logs" / "unit" / "manual")])

            self.assertEqual(0, rc)
            dotnet_test_calls = [cmd for cmd in commands if cmd[:2] == ["dotnet", "test"]]
            self.assertEqual(2, len(dotnet_test_calls))
            summary = json.loads((root / "logs" / "unit" / "manual" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", summary["status"])
            self.assertEqual(2, len(summary["test_attempts"]))
            self.assertTrue(summary["test_attempts"][0]["retryable_coverlet_file_lock"])
            self.assertEqual(0, summary["test_attempts"][1]["rc"])

    def test_main_should_isolate_results_and_clean_outputs_before_retry_after_coverlet_abort(self) -> None:
        commands: list[list[str]] = []
        clean_markers: list[tuple[bool, bool, bool]] = []

        first_test_output = """
Starting test execution, please wait...
The active test run was aborted. Reason: Test host process crashed
Data collector 'XPlat code coverage' message: [coverlet]Coverlet.Collector.Utilities.CoverletDataCollectorException: CoverletCoverageDataCollector: Failed to get coverage result
System.IO.IOException: The process cannot access the file 'D:\\a\\newrouge\\newrouge\\Game.Core.Tests\\bin\\Debug\\net8.0\\Game.Core.dll' because it is being used by another process.
Passed!  - Failed:     0, Passed:   950, Skipped:     0, Total:   950, Duration: 5 s - Game.Core.Tests.dll (net8.0)
Test Run Aborted.
"""
        second_test_output = r"D:\repo\Game.Core.Tests\TestResults\attempt-2\tests.trx" + "\n" + r"D:\repo\Game.Core.Tests\TestResults\attempt-2\coverage.cobertura.xml"

        def _fake_run_cmd(args, cwd=None, timeout=900_000):
            commands.append(list(args))
            if args[:2] == ["dotnet", "restore"]:
                return 0, "restore ok\n"
            if args[:2] != ["dotnet", "test"]:
                return 0, ""
            dotnet_test_calls = [cmd for cmd in commands if cmd[:2] == ["dotnet", "test"]]
            if len(dotnet_test_calls) == 2:
                clean_markers.append((
                    not (root / "Game.Core.Tests" / "bin" / "Debug" / "net8.0").exists(),
                    not (root / "Game.Core" / "bin" / "Debug" / "net8.0").exists(),
                    not (root / "Game.Core.Tests" / "TestResults").exists(),
                ))
                results_dir = Path(args[args.index("--results-directory") + 1])
                results_dir.mkdir(parents=True, exist_ok=True)
                (results_dir / "tests.trx").write_text("trx", encoding="utf-8")
                (results_dir / "coverage.cobertura.xml").write_text(
                    '<coverage lines-covered="95" lines-valid="100" branches-covered="90" branches-valid="100"></coverage>',
                    encoding="utf-8",
                )
                return 0, second_test_output
            return 0, first_test_output

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "newrouge"
            root.mkdir(parents=True, exist_ok=True)
            (root / "NewRouge.sln").write_text("", encoding="utf-8")

            test_bin_dir = root / "Game.Core.Tests" / "bin" / "Debug" / "net8.0"
            core_bin_dir = root / "Game.Core" / "bin" / "Debug" / "net8.0"
            results_dir = root / "Game.Core.Tests" / "TestResults"
            test_bin_dir.mkdir(parents=True, exist_ok=True)
            core_bin_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)
            (test_bin_dir / "Game.Core.Tests.dll").write_text("stale", encoding="utf-8")
            (core_bin_dir / "Game.Core.dll").write_text("stale", encoding="utf-8")
            (results_dir / "tests.trx").write_text("stale", encoding="utf-8")

            with mock.patch.object(run_dotnet.os, "getcwd", return_value=str(root)), \
                mock.patch.object(run_dotnet, "run_cmd", side_effect=_fake_run_cmd), \
                mock.patch.object(run_dotnet, "_best_effort_cleanup_testhosts", return_value=None), \
                mock.patch.dict(run_dotnet.os.environ, {"DOTNET_TEST_RETRY_ON_FAIL": "1"}, clear=False):
                rc = run_dotnet.main(["--solution", "NewRouge.sln", "--out-dir", str(root / "logs" / "unit" / "manual")])

            self.assertEqual(0, rc)
            self.assertEqual([(True, True, True)], clean_markers)
            dotnet_test_calls = [cmd for cmd in commands if cmd[:2] == ["dotnet", "test"]]
            self.assertEqual(2, len(dotnet_test_calls))
            self.assertIn("--results-directory", dotnet_test_calls[0])
            self.assertIn("--results-directory", dotnet_test_calls[1])
            first_results_dir = dotnet_test_calls[0][dotnet_test_calls[0].index("--results-directory") + 1]
            second_results_dir = dotnet_test_calls[1][dotnet_test_calls[1].index("--results-directory") + 1]
            self.assertNotEqual(first_results_dir, second_results_dir)


if __name__ == "__main__":
    unittest.main()
