"""Exercise real task writers on isolated repositories after closeout."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))
from chapter3_closeout import atomic_json
from chapter3_task_scope import load_scope
from chapter7_output_policy import output_path, validate_output
from create_chapter7_tasks_from_ui_candidates import create_tasks
from run_chapter7_ui_wiring import main as chapter7


class CloseoutRouteTests(unittest.TestCase):
    def test_real_incremental_compile_export_preserves_existing_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = {"id": 9, "title": "Keep", "status": "done", "acceptance": ["Keep criterion"],
                   "subtasks": [{"id": 1, "status": "done"}], "extension": {"keep": True}}
            view = {"id": "INT-0009", "taskmaster_id": 9, "title": "Keep", "status": "done",
                    "acceptance": ["Keep criterion"], "subtasks": old["subtasks"], "depends_on": []}
            atomic_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [old]}})
            atomic_json(root / ".taskmaster/tasks/tasks_back.json", [view])
            atomic_json(root / ".taskmaster/tasks/tasks_gameplay.json", [])
            # A new registered GDD owns the new candidate, not an existing task.
            source = "docs/gdd/next.md"
            (root / source).parent.mkdir(parents=True)
            (root / source).write_text("The player must choose a route.\n", encoding="utf-8")
            atomic_json(root / "docs/workflows/chapter3-source-set.json", {"active_sources": [source], "retirements": []})
            candidate = {"id": "INT-0010", "change_action": "create", "title": "Choose route",
                         "owner": "gameplay", "layer": "core", "semantic_refs": ["FR-ROUTE"],
                         "source_refs": [source], "acceptance": ["Route is selected; Refs: Tests/Route.cs"]}
            atomic_json(root / "logs/ci/task-generation/task-candidates.enriched.json", {"candidates": [candidate]})
            atomic_json(root / "logs/ci/task-generation/coverage-report.json", {"status": "ok"})
            command = [sys.executable, str(ROOT / "scripts/python/compile_task_triplet.py"),
                       "--repo-root", str(root), "--mode", "add"]
            for extra in ([], ["--write"]):
                result = subprocess.run(command + extra, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for name in ("build_taskmaster_tasks.py", "chapter3_task_scope.py", "chapter3_closeout.py"):
                target = root / "scripts/python" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / "scripts/python" / name, target)
            result = subprocess.run([sys.executable, str(root / "scripts/python/build_taskmaster_tasks.py"),
                                     "--tasks-file", ".taskmaster/tasks/tasks_gameplay.json", "--ids", "INT-0010"],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            tasks = json.loads((root / ".taskmaster/tasks/tasks.json").read_text())["master"]["tasks"]
            self.assertEqual(old, tasks[0])
            self.assertEqual(10, tasks[1]["id"])
            self.assertEqual([view], json.loads((root / ".taskmaster/tasks/tasks_back.json").read_text()))
            # Reusing a stale preview after source-view edits must fail.
            changed = [{**view, "status": "in-progress"}]
            atomic_json(root / ".taskmaster/tasks/tasks_back.json", changed)
            result = subprocess.run(command + ["--write"], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)

    def test_chapter7_creation_and_retired_output_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_json(root / ".taskmaster/tasks/tasks.json", {"master": {"tasks": []}})
            atomic_json(root / ".taskmaster/tasks/tasks_back.json", [])
            atomic_json(root / ".taskmaster/tasks/tasks_gameplay.json", [])
            atomic_json(root / "docs/gdd/ui-gdd-flow.candidates.json", {"candidates": [{
                "screen_group": "route-map", "title": "Route selection", "bucket": "map"}]})
            atomic_json(root / "docs/workflows/chapter3-source-set.json", {"retirements": [{"path": "docs/gdd/ui-gdd-flow.md"}]})
            self.assertIsNone(load_scope(root))
            self.assertEqual(0, chapter7(["--repo-root", str(root), "--create-tasks", "--self-check"]))
            code, result = create_tasks(repo_root=root)
            self.assertEqual(0, code, result)
            self.assertEqual(1, len(json.loads((root / ".taskmaster/tasks/tasks.json").read_text())["master"]["tasks"]))
            self.assertEqual("docs/planning/chapter7/ui-wiring-board.md", output_path(root))
            with self.assertRaisesRegex(ValueError, "read-only"):
                validate_output(root, Path("docs/gdd/ui-gdd-flow.md"))
            code, result = create_tasks(repo_root=root, ui_candidates_path=Path("missing.json"))
            self.assertEqual(1, code)
            self.assertEqual("missing_candidate_sidecar", result["reason"])


if __name__ == "__main__":
    unittest.main()
