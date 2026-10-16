"""Offline regression guards for recovery write locks and cost lower bounds."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_recovery as recovery
import _mvg_capability_selection as selection
import _mvg_capability_generation as generation
import _planning_apply_journal as journal
import plan_mvg as pm
from _planning_skill_common import atomic_json, load_json


class RecoveryFixthroughTests(unittest.TestCase):
    def test_current_scope_seven_call_minimum_does_not_charge_unknown_future_scope(self):
        self.assertTrue(hasattr(selection, "scope_cost_budget"), "Current-scope budget helper is missing")
        with tempfile.TemporaryDirectory() as directory:
            labels = pm.MVG_CANDIDATE_LABELS
            for phase, spent in (("inspect", 0), ("semantic", 1)):
                with self.subTest(phase=phase):
                    budget = selection.scope_cost_budget(phase, remaining_run=7-spent,
                        remaining_lineage=64-spent, remaining_candidates=2,
                        known_evidence_calls=0, future_scopes=1)
                    report = generation.stage_cost_preflight(Path(directory) / "cost.json",
                        phase=phase, evidence_calls=0, **budget)
                    self.assertEqual(7-spent, report["minimum_required_calls"]["run"])
                    self.assertEqual(7, report["unknown_future_scope_estimate"]["run"])
                    self.assertEqual("ready", report["status"])
            final = selection.selector_cost_preflight(Path(directory) / "selector.json", remaining_run=1,
                lineage_invocations={label: 64 for label in labels}, future_scopes=1)
            self.assertEqual({"run": 1, "lineage": 0}, final["minimum_required_calls"])
            self.assertEqual(7, final["unknown_future_scope_estimate"]["run"])
            with self.assertRaisesRegex(ValueError, "mvg_stage_cost_budget_insufficient"):
                generation.stage_cost_preflight(Path(directory) / "next-scope.json", phase="inspect",
                    evidence_calls=0, **selection.scope_cost_budget("inspect", remaining_run=0,
                        remaining_lineage=64, remaining_candidates=2, known_evidence_calls=0, future_scopes=0))

    def test_existing_apply_journal_holds_activity_lock_through_all_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "logs/ci/mvg-planning/fixture"
            state = {"schema_version": pm.RUN_SCHEMA, "run_id": "fixture",
                "manifest_path": "docs/testing/mvg/fixture.json"}
            recovery.bind_epoch(root, state)
            atomic_json(run / "run.json", state)
            manifest = root / state["manifest_path"]
            trace = root / pm.FORMAL_TRACE_ROOT / "fixture.json"
            result = {"manifest_sha256": "sha256:fixture", "trace_path": trace.relative_to(root).as_posix(),
                "post_apply_task_readiness": [], "handoff_review_required_tasks": [], "status": "applied"}
            journal.create_journal(root, run / "apply-journal.json", {manifest: {"manifest": "after"},
                trace: {"handoff_bindings": {}}}, {}, result)
            real_writer = pm.atomic_json
            writes = []
            def checked_writer(path, payload):
                with self.assertRaisesRegex(ValueError, "coordinator_busy"):
                    recovery.clear(root)
                self.assertEqual(0, recovery.registry(root)["epoch"])
                writes.append(path)
                real_writer(path, payload)
            with patch.object(pm, "_validate_apply_checkpoint_binding"), \
                 patch.object(pm, "_validate_apply_accounting"), \
                 patch.object(pm, "atomic_json", side_effect=checked_writer), \
                 patch.object(pm, "run_isolated_model") as model:
                self.assertEqual("applied", pm.apply(root, run_id="fixture", confirm=True)["status"])
                model.assert_not_called()
            self.assertEqual({manifest, trace, run / "run.json", run / "apply-summary.json"}, set(writes))
            self.assertEqual("complete", load_json(run / "apply-journal.json")["status"])
            recovery.clear(root)
            with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
                pm.apply(root, run_id="fixture", confirm=True)


if __name__ == "__main__":
    unittest.main()
