#!/usr/bin/env python3
from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from planning_acceptance_fixture import build_fixture
from chapter5_semantic_reconciliation import load_task_readiness, DEFAULT_EXTRACTION_SNAPSHOT


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

    def test_handoff_inputs_result_and_retry_rule_reach_reviewed_task_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "harbor"
            build_fixture(root)
            semantics = json.loads((root / "logs/ci/task-generation/semantic-requirements.v1.json").read_text(encoding="utf-8"))
            reqs = {r["requirement_id"]: r for r in semantics["requirements"]}
            launch, delivery = reqs["RQ-HARBOR-001"], reqs["RQ-HARBOR-002"]
            for field in ("RouteId", "CargoUnits", "RetryAllowed=true"):
                self.assertIn(field, launch["statement"])
            for obligation in ("completion or failure signal", "original request", "retryable failure", "outside the accepted-transfer scope"):
                self.assertIn(obligation, delivery["statement"])
            tasks = json.loads((root / ".taskmaster/tasks/tasks_gameplay.json").read_text(encoding="utf-8"))
            snapshot = json.loads((root / DEFAULT_EXTRACTION_SNAPSHOT).read_text(encoding="utf-8"))
            for task_id, requirement in ((7, launch), (42, delivery)):
                task = next(t for t in tasks if str(t["taskmaster_id"]) == str(task_id))
                self.assertIn(requirement["requirement_id"], task["semantic_refs"])
                self.assertTrue(any(requirement["requirement_id"] in str(a) for a in task["acceptance"]))
                self.assertTrue(any(o["statement"] == requirement["statement"] for o in snapshot["semantic_inventory"]))
                ok, readiness, reason = load_task_readiness(root, str(task_id))
                self.assertTrue(ok, reason)
                self.assertTrue(readiness["closure_allowed"])


if __name__ == "__main__":
    unittest.main()
