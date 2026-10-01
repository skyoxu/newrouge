"""Interruption, drift and fail-closed checks for reconciliation closeout."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))
import chapter3_closeout as closeout
from chapter3_task_scope import allowed_ids, load_scope
from create_chapter7_tasks_from_ui_candidates import create_tasks


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = {"sentinel": "sha256:input"}
        closeout.atomic_json(self.root / closeout.SCOPE, {
            "schema_version": "chapter3.task-scope.v1", "mode": "reconcile-existing-only",
            "master_path": closeout.TASKS[0], "allowed_numeric_task_ids": [3, 9], "expected_master_task_count": 2})
        closeout.atomic_json(self.root / closeout.TASKS[0], {"master": {"tasks": [{"id": 3}, {"id": 9}]}})
        self.manifest = patch.object(closeout, "input_manifest", return_value=self.inputs)
        self.manifest.start()
        self.addCleanup(self.manifest.stop)

    def begin(self):
        return closeout.begin(self.root, "test-run", temporary=True)

    def passed(self, root, commands, out):
        return [{"command": command, "returncode": 0} for command in commands]

    def test_complete_and_repeat_do_not_rewrite_tasks(self):
        before = (self.root / closeout.TASKS[0]).read_bytes()
        self.begin()
        with patch.object(closeout, "run_checks", side_effect=self.passed) as checks:
            self.assertEqual("complete", closeout.resume(self.root)["phase"])
            self.assertIsNone(load_scope(self.root))
            self.assertEqual("complete", closeout.resume(self.root)["phase"])
            self.assertEqual(2, checks.call_count)
        self.assertEqual(before, (self.root / closeout.TASKS[0]).read_bytes())

    def test_failed_repair_retains_scope(self):
        self.begin()
        with patch.object(closeout, "run_checks", return_value=[{"returncode": 1}]):
            with self.assertRaisesRegex(ValueError, "validation failed"):
                closeout.resume(self.root)
        self.assertTrue((self.root / closeout.SCOPE).exists())

    def test_crash_after_deletion_blocks_direct_and_wrapped_writers(self):
        self.begin()
        with patch.object(closeout, "run_checks", side_effect=[self.passed(self.root, closeout.REPAIR_CHECKS, None), RuntimeError("crash")]):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                closeout.resume(self.root)
        self.assertFalse((self.root / closeout.SCOPE).exists())
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_scope(self.root)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            create_tasks(repo_root=self.root)
        with patch.object(closeout, "run_checks", side_effect=self.passed) as checks:
            closeout.resume(self.root)
            self.assertEqual(1, checks.call_count)

    def test_missing_and_corrupt_target_fail_closed(self):
        self.begin()
        path, state = closeout.load_record(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "invalid"):
            load_scope(self.root)
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid"):
            load_scope(self.root)

    def test_drift_preserves_later_edits(self):
        self.begin()
        changed = (self.root / closeout.SCOPE).read_bytes() + b"\n"
        (self.root / closeout.SCOPE).write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "Scope changed"):
            closeout.resume(self.root)
        self.assertEqual(changed, (self.root / closeout.SCOPE).read_bytes())
        (self.root / closeout.SCOPE).write_bytes(changed[:-1])
        with patch.object(closeout, "input_manifest", return_value={"sentinel": "sha256:drift"}):
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                closeout.resume(self.root)

    def test_permanent_scope_is_not_released(self):
        scope = closeout.read(self.root / closeout.SCOPE)
        scope["lifecycle"] = "permanent"
        closeout.atomic_json(self.root / closeout.SCOPE, scope)
        with self.assertRaisesRegex(ValueError, "Permanent"):
            self.begin()

    def test_crash_after_verified_evidence_only_cleans_up(self):
        self.begin()
        path, state = closeout.load_record(self.root)
        state.update(phase="recovery-verified", repair_checks=self.passed(self.root, closeout.REPAIR_CHECKS, None),
                     recovery_checks=[{"returncode": 0}])
        closeout.atomic_json(path, state)
        (self.root / closeout.SCOPE).unlink()
        with patch.object(closeout, "run_checks", side_effect=AssertionError("must not rerun")):
            self.assertEqual("complete", closeout.resume(self.root)["phase"])

    def test_noncontiguous_and_duplicate_scope_ids(self):
        self.assertEqual({3, 9}, allowed_ids(closeout.read(self.root / closeout.SCOPE)))
        with self.assertRaisesRegex(ValueError, "unique"):
            allowed_ids({"allowed_numeric_task_ids": [3, 3], "expected_master_task_count": 2})


if __name__ == "__main__":
    unittest.main()
