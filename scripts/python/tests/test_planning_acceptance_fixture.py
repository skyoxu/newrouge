#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from planning_acceptance_fixture import build_fixture
from chapter5_semantic_reconciliation import load_task_readiness


class PlanningAcceptanceFixtureTests(unittest.TestCase):
    def test_second_project_fixture_has_non_contiguous_ids_and_real_chapter5_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "harbor"
            result = build_fixture(root)
            self.assertEqual([7, 42], result["task_ids"])
            self.assertTrue(result["non_contiguous_task_ids"])
            self.assertGreaterEqual(result["delivery_requirement_count"], 2)
            self.assertNotIn("133", root.joinpath(".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
            for task_id in ("7", "42"):
                ok, payload, reason = load_task_readiness(root, task_id)
                self.assertTrue(ok, reason)
                self.assertEqual("READY", payload["readiness"])

    def test_fixture_starts_without_derived_capability_answer(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "harbor"
            build_fixture(root)
            self.assertFalse(
                (root / "docs/planning/semantic-topology/capabilities.v1.json").exists()
            )
            task_text = (root / ".taskmaster/tasks/tasks_gameplay.json").read_text(encoding="utf-8")
            self.assertIn('"capability_refs": []', task_text)


if __name__ == "__main__":
    unittest.main()
