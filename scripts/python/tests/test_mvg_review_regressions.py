"""Self-contained regression guards for ADR-0039 review findings."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_generation as generation
import _mvg_capability_recovery as recovery
import _mvg_capability_selection as selection
import _mvg_global_audit as audit
import plan_mvg as pm
from _planning_skill_common import atomic_json, canonical_sha, load_json


class ReviewRegressionTests(unittest.TestCase):
    def test_dependency_binds_related_behavior_but_not_unrelated_flows(self):
        scope = {"requirement_ids": ["R-a"], "cumulative_requirement_ids": ["R-a", "R-b"]}
        base = {"manifest_candidate": {"flows": [
            {"id": "a", "requirement_ids": ["R-a"], "test_ids": [],
             "handoffs": [{"behavior": "Observe outcome"}]},
            {"id": "b", "requirement_ids": ["R-b"], "test_ids": [], "handoffs": []}]},
            "coverage_table": [], "tests": [], "entrypoints": []}
        context = {key: [] for key in ("requirements", "source_blocks", "task_views", "task_master", "evidence")}
        with patch.object(generation, "complete_scope_context", return_value=context):
            expected = recovery._dependency(Path("unused"), scope, base, base)
            changed = deepcopy(base)
            changed["manifest_candidate"]["flows"][0]["handoffs"][0]["behavior"] = "Reset then observe outcome"
            self.assertNotEqual(canonical_sha(expected), canonical_sha(
                recovery._dependency(Path("unused"), scope, changed, changed)))
            unrelated = deepcopy(base)
            unrelated["manifest_candidate"]["flows"][1]["outcome"] = "Unrelated new behavior"
            self.assertEqual(expected, recovery._dependency(Path("unused"), scope, unrelated, unrelated))

    def test_current_execution_uses_its_own_ledger_without_refunding_old_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "logs/ci/mvg-planning/run"
            scope, seed = {"capability_id": "CAP-a"}, {}
            calls = [{"number": n, "candidate": "candidate-1", "capability_id": "CAP-a",
                      "execution": 1 if n <= 2 else 2, "reservation_id": str(n)} for n in range(1, 5)]
            state = {"run_id": "run", "capability_selection": {
                "binding": canonical_sha({"strategy": selection.STRATEGY, "scopes": [scope], "seed": seed}),
                "order": ["CAP-a"], "selected": [], "accepted_sha256": canonical_sha(seed),
                "current": {"capability_id": "CAP-a", "order_index": 0, "execution": 2,
                            "base_sha256": canonical_sha(seed)},
                "calls": calls, "total_invocations": 4,
                "lineage_invocations": {label: 4 if label == "candidate-1" else 0 for label in pm.MVG_CANDIDATE_LABELS}}}
            old = selection.scope_workspace(run, "candidate-1", 0, 1) / "capability-append/append-ledger.json"
            new = selection.scope_workspace(run, "candidate-1", 0, 1, 2) / "capability-append/append-ledger.json"
            atomic_json(old, {"status": "admitted", "total_invocations": 2, "records": [{"old": True}]})
            atomic_json(new, {"status": "admitted", "total_invocations": 2, "records": [{"new": True}]})
            before = old.read_bytes()
            with patch.object(pm, "_validate_input_freshness"), \
                 patch.object(selection, "frozen_scopes", return_value=[scope]), \
                 patch.object(selection, "seed_proposal", return_value=seed):
                self.assertEqual(([scope], seed, []), selection.verified_prefix(root, run, state))
            self.assertEqual(before, old.read_bytes())
            self.assertEqual(4, state["capability_selection"]["total_invocations"])

    def test_progress_preserves_historical_charges_and_excludes_active_dispatch(self):
        calls = [{"number": n, "candidate": "candidate-1", "reservation_id": str(n)} for n in range(1, 6)]
        selected = {"reservation_id": "1", "checkpoint": {"transaction_id": "a"}}
        state = {"run_id": "run", "recovery": {"epoch": 0}, "capability_selection": {
            "selected": [selected], "calls": calls, "total_invocations": 5,
            "lineage_invocations": {"candidate-1": 5}, "current": {"capability_id": "CAP-b"}}}
        prior = {"capability_selection": {"calls": calls[:3]}}
        def verified(_root, _run, projected, **kwargs):
            self.assertEqual(calls[:3], projected["capability_selection"]["calls"],
                             "Reopen history must retain all original charges, not only the retained rank")
            self.assertEqual(3, projected["capability_selection"]["total_invocations"])
            self.assertFalse(kwargs["recover_counters"])
            return [{"capability_id": "CAP-a"}, {"capability_id": "CAP-b"}], {}, [{}]
        with patch.object(recovery, "assert_active_chain"), \
             patch.object(audit, "historical_states", return_value=[prior]), \
             patch.object(selection, "verified_prefix", side_effect=verified):
            self.assertEqual(1, recovery.progress(Path("unused"), Path("unused"), state)["completed"])
        self.assertEqual(calls, state["capability_selection"]["calls"])


if __name__ == "__main__":
    unittest.main()
