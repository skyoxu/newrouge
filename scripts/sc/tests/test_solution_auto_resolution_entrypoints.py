#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
