#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
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


lane = _load_module("single_task_light_lane_module", "scripts/python/run_single_task_light_lane.py")


def _write_master_tasks(path: Path, tasks: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"master": {"tasks": tasks}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class RunSingleTaskLightLaneTests(unittest.TestCase):
    def test_steps_should_toggle_align_apply_and_delivery_profile(self) -> None:
        steps_apply = lane._steps(align_apply=True, delivery_profile="fast-ship")
        steps_read_only = lane._steps(align_apply=False, delivery_profile="playable-ea")
        align_apply_cmd = dict(steps_apply)["align"]
        align_read_only_cmd = dict(steps_read_only)["align"]

        self.assertIn("--apply", align_apply_cmd)
        self.assertNotIn("--apply", align_read_only_cmd)

        for step_name, cmd in steps_read_only[:4]:
            self.assertIn("--delivery-profile", cmd, msg=step_name)
            idx = cmd.index("--delivery-profile")
            self.assertEqual("playable-ea", cmd[idx + 1], msg=step_name)

    def test_taskmaster_tasks_path_should_fallback_to_examples(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            expected = root / "examples" / "taskmaster" / "tasks.json"
            _write_master_tasks(expected, [{"id": 1, "status": "in-progress"}])

            actual = lane._taskmaster_tasks_path(root)

        self.assertEqual(expected, actual)

    def test_select_task_ids_should_prefer_in_progress_when_no_explicit_ids(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_path = root / ".taskmaster" / "tasks" / "tasks.json"
            _write_master_tasks(
                tasks_path,
                [
                    {"id": 1, "status": "done"},
                    {"id": 2, "status": "in-progress"},
                    {"id": 3, "status": "active"},
                    {"id": 4, "status": "working"},
                ],
            )
            args = Namespace(task_ids="", task_id_start=1, task_id_end=0, max_tasks=0)

            selected = lane._select_task_ids(root, args)

        self.assertEqual([2, 3, 4], selected)

    def test_select_task_ids_should_honor_explicit_csv_and_max_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_path = root / ".taskmaster" / "tasks" / "tasks.json"
            _write_master_tasks(
                tasks_path,
                [
                    {"id": 1, "status": "done"},
                    {"id": 2, "status": "done"},
                    {"id": 3, "status": "done"},
                    {"id": 4, "status": "done"},
                ],
            )
            args = Namespace(task_ids="4,3,100,3", task_id_start=1, task_id_end=0, max_tasks=1)

            selected = lane._select_task_ids(root, args)

        self.assertEqual([3], selected)

    def test_main_self_check_should_write_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_path = root / ".taskmaster" / "tasks" / "tasks.json"
            _write_master_tasks(tasks_path, [{"id": 11, "status": "in-progress"}])
            out_dir = root / "logs" / "ci" / "self-check"
            argv = [
                "run_single_task_light_lane.py",
                "--task-ids",
                "11",
                "--out-dir",
                str(out_dir),
                "--self-check",
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(lane, "_repo_root", return_value=root):
                rc = lane.main()

            self.assertEqual(0, rc)
            payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("ok", payload["status"])
            self.assertEqual(["extract", "align", "coverage", "semantic_gate", "fill_refs_dry", "fill_refs_write", "fill_refs_verify"], payload["steps"])
            self.assertEqual(11, payload["task_id_start"])
            self.assertEqual(11, payload["task_id_end"])


if __name__ == "__main__":
    unittest.main()
