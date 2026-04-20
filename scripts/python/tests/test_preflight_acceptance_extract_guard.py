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
SCRIPT = REPO_ROOT / "scripts" / "python" / "preflight_acceptance_extract_guard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("preflight_acceptance_extract_guard", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["preflight_acceptance_extract_guard"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PreflightAcceptanceExtractGuardTests(unittest.TestCase):
    def test_should_pass_when_acceptance_refs_are_traceable(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 59, "title": "Task"}]}})
            _write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            _write_json(
                root / ".taskmaster/tasks/tasks_gameplay.json",
                [
                    {
                        "id": "GM-0159",
                        "taskmaster_id": 59,
                        "acceptance": [
                            "ACC:T59.1 Run entry reaches Map. Refs: Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd Game.Core.Tests/Tasks/Task0059AcceptanceTests.cs"
                        ],
                        "test_refs": [
                            "Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd",
                            "Game.Core.Tests/Tasks/Task0059AcceptanceTests.cs",
                        ],
                    }
                ],
            )

            report = mod.evaluate_task(root=root, task_id=59)

        self.assertEqual("ok", report["status"])
        self.assertEqual([], report["issues"])

    def test_should_fail_when_acceptance_is_missing_refs(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 59, "title": "Task"}]}})
            _write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            _write_json(
                root / ".taskmaster/tasks/tasks_gameplay.json",
                [{"id": "GM-0159", "taskmaster_id": 59, "acceptance": ["Run entry reaches Map."], "test_refs": []}],
            )

            report = mod.evaluate_task(root=root, task_id=59)

        self.assertEqual("fail", report["status"])
        self.assertIn("acceptance_missing_refs", report["issue_ids"])

    def test_should_fail_when_acceptance_ref_is_missing_from_test_refs(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 59, "title": "Task"}]}})
            _write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            _write_json(
                root / ".taskmaster/tasks/tasks_gameplay.json",
                [
                    {
                        "id": "GM-0159",
                        "taskmaster_id": 59,
                        "acceptance": ["Run entry reaches Map. Refs: Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd"],
                        "test_refs": [],
                    }
                ],
            )

            report = mod.evaluate_task(root=root, task_id=59)

        self.assertEqual("fail", report["status"])
        self.assertIn("acceptance_ref_missing_from_test_refs", report["issue_ids"])

    def test_should_fail_on_question_mark_garbled_acceptance(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 59, "title": "Task"}]}})
            _write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            _write_json(
                root / ".taskmaster/tasks/tasks_gameplay.json",
                [
                    {
                        "id": "GM-0159",
                        "taskmaster_id": 59,
                        "acceptance": ["???? Refs: Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd"],
                        "test_refs": ["Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd"],
                    }
                ],
            )

            report = mod.evaluate_task(root=root, task_id=59)

        self.assertEqual("fail", report["status"])
        self.assertIn("acceptance_garbled_question_marks", report["issue_ids"])

    def test_main_should_write_summary_and_use_repo_root(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "logs/ci/preflight"
            _write_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 59, "title": "Task"}]}})
            _write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            _write_json(
                root / ".taskmaster/tasks/tasks_gameplay.json",
                [
                    {
                        "id": "GM-0159",
                        "taskmaster_id": 59,
                        "acceptance": ["Run entry reaches Map. Refs: Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd"],
                        "test_refs": ["Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd"],
                    }
                ],
            )
            argv = [
                "preflight_acceptance_extract_guard.py",
                "--task-id",
                "59",
                "--out-dir",
                str(out_dir),
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(mod, "repo_root", return_value=root):
                rc = mod.main()

            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(0, rc)
        self.assertEqual("ok", summary["status"])
        self.assertEqual(59, summary["task_id"])


if __name__ == "__main__":
    unittest.main()
