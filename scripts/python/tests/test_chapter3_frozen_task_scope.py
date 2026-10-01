"""Regression checks for configured reconciliation identity protection."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts/python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _knowledge_catalog_builder import _excluded
from chapter3_task_scope import load_scope, validate_candidate_operations, validate_master
from reconcile_frozen_task_candidates import reconcile
from chapter7_ui_gdd_writer import write_ui_gdd_flow
from run_chapter7_ui_wiring import main as run_chapter7
from audit_task_candidate_coverage import candidate_coverage
from validate_semantic_conservation import closure_checks


class FrozenTaskScopeTests(unittest.TestCase):
    def test_master_contains_exactly_original_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scope = {"master_path": "tasks.json", "allowed_numeric_task_ids": [2, 8], "expected_master_task_count": 2}
            (root / "tasks.json").write_text(json.dumps({"master": {"tasks": [{"id": 2}, {"id": 8}]}}), encoding="utf-8")
            self.assertEqual({2, 8}, validate_master(root, scope))
            (root / "tasks.json").write_text(json.dumps({"master": {"tasks": [{"id": 2}, {"id": 9}]}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differ"):
                validate_master(root, scope)

    def test_create_operation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "rejects new task"):
            validate_candidate_operations([{"id": "INT-0010", "action": "create"}], {2, 8})

    def test_historical_reconciliation_cannot_run_as_normal_add(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "scope is required"):
                reconcile(root)

    def test_cancelled_candidate_is_not_a_semantic_sink(self) -> None:
        candidates = {
            "candidates": [{
                "id": "GM-RETired",
                "taskmaster_id": 117,
                "taskmaster_status": "cancelled",
                "semantic_refs": ["FR-T0001"],
                "complexity_score": 1,
            }]
        }
        self.assertEqual({}, candidate_coverage(candidates)[0])
        semantics = {"requirements": [{
            "requirement_id": "FR-T0001",
            "status": "active",
            "delivery_relevant": True,
            "source_block_ids": [],
            "non_task_sinks": [],
        }]}
        report, edges = closure_checks(semantics, candidates)
        self.assertEqual(1, len(report["orphan_delivery_requirements"]))
        self.assertEqual([], edges)

    def test_chapter3_and_knowledge_use_only_current_gdd(self) -> None:
        current = "docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md"
        source_set = json.loads((ROOT / "docs/workflows/chapter3-source-set.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / "scripts/python/project_health_knowledge_config.json").read_text(encoding="utf-8"))
        self.assertEqual([current], source_set["active_patterns"])
        self.assertEqual([current], source_set["active_sources"])
        self.assertEqual([current], config["gdd_paths"])
        historical = {
            "_bmad-output/gdd.md",
            "docs/gdd/GDD-NEWROUGE-V1.md",
            "docs/gdd/ui-gdd-flow.md",
        }
        self.assertTrue(historical.issubset({row["path"] for row in source_set["retirements"]}))
        exclusions = json.loads((ROOT / "knowledge/policies/source-exclusions.v1.json").read_text(encoding="utf-8"))
        self.assertTrue(all(_excluded(path, exclusions) for path in historical))
        self.assertFalse(_excluded(current, exclusions))

    def test_chapter7_cannot_overwrite_retired_gdd(self) -> None:
        with self.assertRaisesRegex(ValueError, "read-only"):
            write_ui_gdd_flow(
                repo_root=ROOT,
                summary={},
                ui_gdd_flow_path=Path("docs/gdd/ui-gdd-flow.md"),
            )

    def test_chapter7_cannot_create_tasks_under_frozen_scope(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "docs/workflows/chapter3-task-scope.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"schema_version": "chapter3.task-scope.v1", "mode": "reconcile-existing-only"}), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "rejects Chapter 7 task creation"):
                run_chapter7(["--repo-root", str(root), "--create-tasks", "--self-check"])


if __name__ == "__main__":
    unittest.main()
