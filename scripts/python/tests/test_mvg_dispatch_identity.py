"""Offline request identity and coordinator-owned dispatch outcome conservation."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _mvg_capability_generation import dispatch_request_identity, verify_dispatch_receipts
from _planning_skill_common import atomic_json, file_sha


class DispatchIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.workspace = self.run / "sandbox"
        self.workspace.mkdir()
        self.prompt = self.workspace / "prompt.txt"
        self.prompt.write_text("Return strict JSON", encoding="utf-8")
        self.schema = self.workspace / "output-schema.json"
        atomic_json(self.schema, {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
        self.output = self.workspace / "output.json"
        self.request = dispatch_request_identity(self.run, Path("fixture-runner.py"), workspace=self.workspace,
            prompt_path=self.prompt, output_path=self.output, output_schema=self.schema, attempt=1)
        self.row = {"number": 1, "reservation_id": "run:dispatch:1", "run_id": "run", "phase": "selection",
            "candidate": None, "status": "reserved", "request_identity": self.request}
        self.path = self.run / "dispatch-receipts/dispatch-1.json"

    def complete(self):
        atomic_json(self.output, {"ok": True})
        self.row["outcome"] = {"status": "completed", "completed_at_utc": "fixture-time", "error_type": None,
                               "output_sha256": file_sha(self.output)}
        projected = {**{key: value for key, value in self.row.items() if key != "outcome"}, **self.row["outcome"]}
        atomic_json(self.path, projected)
        return projected

    def test_outcome_hash_attempt_request_and_error_mutations_are_rejected(self):
        original = self.complete()
        verify_dispatch_receipts(self.run, [self.row])
        for field in ("output_sha256", "request_sha256", "attempt"):
            changed = deepcopy(original)
            target = changed if field == "output_sha256" else changed["request_identity"]
            target[field] = 2 if field == "attempt" else "sha256:changed"
            atomic_json(self.path, changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "outcome_projection_changed"):
                verify_dispatch_receipts(self.run, [self.row])
        self.row["outcome"] = {"status": "failed", "error_type": "runner_transport", "error_class": "RuntimeError"}
        failed = {**{key: value for key, value in self.row.items() if key != "outcome"}, **self.row["outcome"]}
        atomic_json(self.path, failed)
        verify_dispatch_receipts(self.run, [self.row])
        failed["error_type"] = "free-retry"
        atomic_json(self.path, failed)
        with self.assertRaisesRegex(ValueError, "outcome_projection_changed"):
            verify_dispatch_receipts(self.run, [self.row])

    def test_completed_output_bytes_and_schema_remain_bound_without_sidecar(self):
        self.complete()
        self.path.unlink()
        atomic_json(self.output, {"ok": False})
        with self.assertRaisesRegex(ValueError, "completed_output_changed"):
            verify_dispatch_receipts(self.run, [self.row])
        atomic_json(self.output, {"ok": "invalid-type"})
        self.row["outcome"]["output_sha256"] = file_sha(self.output)
        with self.assertRaisesRegex(ValueError, "does not satisfy JSON schema"):
            verify_dispatch_receipts(self.run, [self.row])

    def test_prompt_schema_evidence_and_output_destination_are_bound(self):
        atomic_json(self.path, self.row)
        verify_dispatch_receipts(self.run, [self.row])
        for name in ("prompt.txt", "output-schema.json", "late-evidence.txt"):
            target = self.workspace / name
            original = target.read_bytes() if target.is_file() else None
            target.write_text("Changed input", encoding="utf-8")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "request_inputs_changed"):
                verify_dispatch_receipts(self.run, [self.row])
            if original is None:
                target.unlink()
            else:
                target.write_bytes(original)

    def test_historical_calls_remain_unchanged_and_unknown_reservation_stays_charged(self):
        history = {"number": 1, "phase": "generate", "candidate": "candidate-1"}
        prior = deepcopy(history)
        verify_dispatch_receipts(self.run, [history, self.row])
        self.assertEqual(prior, history)
        self.assertNotIn("outcome", self.row)

    def test_historical_coordinator_call_can_reserve_new_calls_without_rewriting_history(self):
        import _mvg_capability_selection as coordinator
        from _planning_skill_common import canonical_sha, load_json
        scopes = [{"capability_id": "CAP-a", "cumulative_requirement_ids": []}]
        old = {"number": 1, "phase": "generate", "candidate": "candidate-1", "capability_id": "CAP-a"}
        state = {"run_id": "old-run", "analysis_identity_sha256": "sha256:old",
            "candidate_attempts": {}, "candidate_admissions": {}, "capability_selection": {
            "binding": "legacy-binding", "order": ["CAP-a"], "selected": [], "accepted_sha256": canonical_sha({}),
            "current": {"order_index": 0, "capability_id": "CAP-a", "base_sha256": canonical_sha({}),
                "admissions": {}, "selection_attempts": []}, "calls": [deepcopy(old)], "total_invocations": 1,
            "lineage_invocations": {"candidate-1": 1, "candidate-2": 0, "candidate-3": 0}}}
        atomic_json(self.run / "run.json", state)
        def worker(*args, **kwargs):
            kwargs["before_call"]("generate")
            return {"status": "blocked", "total_invocations": 1, "errors": []}
        with patch.object(coordinator, "frozen_scopes", return_value=scopes), \
             patch.object(coordinator, "seed_proposal", return_value={}), \
             patch.object(coordinator, "verified_prefix", return_value=(scopes, {}, [])), \
             patch.object(coordinator, "valid_current_candidates", return_value=[]), \
             patch.object(coordinator, "generate_append", side_effect=worker), \
             patch("plan_mvg._validate_input_freshness"), patch("_mvg_capability_selection.shutil.copytree"):
            with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                coordinator.generate_selected_capabilities(self.run, self.run, state, backend="fixture",
                    invoke_factory=None, selector_factory=None)
        stored = load_json(self.run / "run.json")
        self.assertEqual(old, stored["capability_selection"]["calls"][0])
        self.assertEqual(4, stored["capability_selection"]["total_invocations"])
        projected = load_json(self.run / "candidates/candidate-1/lineage-execution.json")
        self.assertIsNone(projected["reservation_ids"][0])

    def test_only_known_copilot_generated_evidence_is_allowed_after_dispatch(self):
        request = dispatch_request_identity(self.run, Path("copilot_isolated_model_runner.py"), workspace=self.workspace,
            prompt_path=self.prompt, output_path=self.output, output_schema=self.schema, attempt=1)
        self.row["request_identity"] = request
        atomic_json(self.path, self.row)
        atomic_json(self.workspace / "copilot-model-evidence.json", {"model": "fixture"})
        verify_dispatch_receipts(self.run, [self.row])
        atomic_json(self.workspace / "unexpected.json", {})
        with self.assertRaisesRegex(ValueError, "request_inputs_changed"):
            verify_dispatch_receipts(self.run, [self.row])
