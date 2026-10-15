"""Offline checkpoint replay, identity-conflict and prefix-recovery coverage."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_checkpoint as checkpoint
import _mvg_capability_selection as selection
import plan_mvg
import test_mvg_capability_append as fixture
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json


class CheckpointReplayTests(unittest.TestCase):
    def committed_fixture(self, run):
        # This minimal fixture has no production protocol/frozen source tree;
        # full shared-prefix validation is covered by the public fixture below.
        state, seed, accepted, step = fixture.CapabilityAppendTests().checkpoint_fixture(run)
        step["record"]["delta"]["version"] = 1
        atomic_json(run / "run.json", state)
        pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
        self.assertEqual("committed", checkpoint.commit_checkpoint(run, state, pointer, step, accepted))
        return state, seed, accepted, step, pointer

    def assert_conflict(self, run, transaction_id):
        evidence = [load_json(path) for path in (run / "checkpoint-conflicts").glob("*/*.json")]
        matches = [row for row in evidence if row["transaction_id"] == transaction_id]
        self.assertTrue(matches, evidence)
        for row in matches:
            self.assertEqual(checkpoint.CONFLICT_SCHEMA, row["schema_version"])
            self.assertTrue(row["reason"])
            self.assertIn("expected_sha256", row)
            self.assertIn("actual_sha256", row)
        return matches

    def test_identical_replay_ignores_key_order_and_whitespace_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            payload_path = run / pointer["path"]
            payload = load_json(payload_path)
            payload_path.write_text(json.dumps(dict(reversed(list(payload.items()))), indent=4), encoding="utf-8")
            before = file_sha(run / "run.json")
            writer = Mock(side_effect=AssertionError("Replay must not publish state"))
            reordered = json.loads(json.dumps(step, sort_keys=True))
            self.assertEqual(pointer, checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, reordered))
            self.assertEqual("no-op", checkpoint.commit_checkpoint(run, state, pointer, reordered, accepted, writer=writer))
            writer.assert_not_called()
            self.assertEqual(before, file_sha(run / "run.json"))
            self.assertEqual(1, len(state["capability_selection"]["selected"]))

    def test_same_identity_rejects_canonical_type_and_content_differences(self):
        for value in (True, 1.0, "1", None, [1]):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                run = Path(folder)
                state, seed, accepted, step, pointer = self.committed_fixture(run)
                before = deepcopy(state)
                disk_sha = file_sha(run / "run.json")
                changed = deepcopy(step)
                changed["record"]["delta"]["version"] = value
                with self.assertRaisesRegex(ValueError, "checkpoint_identity_conflict:payload_changed"):
                    checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, changed)
                with self.assertRaisesRegex(ValueError, "checkpoint_selected_binding_changed"):
                    checkpoint.commit_checkpoint(run, state, pointer, changed, accepted)
                self.assertEqual(before, state)
                self.assertEqual(disk_sha, file_sha(run / "run.json"))
                self.assert_conflict(run, pointer["transaction_id"])

    def test_array_order_is_part_of_canonical_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step = fixture.CapabilityAppendTests().checkpoint_fixture(run)
            step["record"]["delta"]["ordered"] = ["first", "second"]
            pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            checkpoint.commit_checkpoint(run, state, pointer, step, accepted)
            step["record"]["delta"]["ordered"].reverse()
            with self.assertRaisesRegex(ValueError, "checkpoint_identity_conflict"):
                checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)

    def test_changed_accepted_content_records_conflict_before_payload_construction(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            disk_sha = file_sha(run / "run.json")
            changed = {"notes": ["different"]}
            with self.assertRaisesRegex(ValueError, "checkpoint_proposal_changed"):
                checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, changed, step)
            self.assert_conflict(run, pointer["transaction_id"])
            self.assertEqual(disk_sha, file_sha(run / "run.json"))

    def test_earlier_replay_verifies_successors_and_keeps_latest_head(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, first = self.committed_fixture(run)
            stale_state = deepcopy(state)
            second_step = deepcopy(step)
            next_accepted = {"notes": ["chosen", "next"]}
            second_step.update(input_identity={"base_sha256": canonical_sha(accepted)},
                proposal_sha256=canonical_sha(next_accepted), receipt_path="receipt-2.json")
            atomic_json(run / "receipt-2.json", {"verified": True, "order": 2})
            second_step["receipt_sha256"] = file_sha(run / "receipt-2.json")
            second = checkpoint.prepare_checkpoint(run, state, "CAP-b", 1, accepted, next_accepted, second_step)
            checkpoint.commit_checkpoint(run, state, second, second_step, next_accepted)
            before = deepcopy(state)
            writer = Mock(side_effect=AssertionError("Earlier replay must not publish"))
            self.assertEqual(first, checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step))
            self.assertEqual("no-op", checkpoint.commit_checkpoint(run, stale_state, first, step, accepted, writer=writer))
            self.assertEqual(before, stale_state)
            self.assertEqual(before, load_json(run / "run.json"))
            self.assertEqual(second, stale_state["capability_selection"]["checkpoint_head"])
            (run / "receipt-2.json").unlink()
            with self.assertRaisesRegex(ValueError, "checkpoint_receipt_changed"):
                checkpoint.commit_checkpoint(run, state, first, step, accepted, writer=writer)
            self.assertEqual(before, load_json(run / "run.json"))
            self.assert_conflict(run, second["transaction_id"])
            writer.assert_not_called()

    def test_prepared_orphan_is_not_committed_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step = fixture.CapabilityAppendTests().checkpoint_fixture(run)
            first = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            second = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            self.assertEqual(first, second)
            self.assertEqual([], load_json(run / "run.json")["capability_selection"]["selected"])
            self.assertEqual("committed", checkpoint.commit_checkpoint(run, state, second, step, accepted))

    def test_transaction_order_rejects_boolean_and_float(self):
        for index in (False, 0.0, 1.0, "1", -1):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as folder:
                run = Path(folder)
                state, seed, accepted, step = fixture.CapabilityAppendTests().checkpoint_fixture(run)
                with self.assertRaisesRegex(ValueError, "checkpoint_identity_invalid"):
                    checkpoint.prepare_checkpoint(run, state, "CAP-a", index, seed, accepted, step)
                self.assertEqual([], load_json(run / "run.json")["capability_selection"]["selected"])

    def test_occupied_slot_changed_receipt_identity_records_original_and_actual_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            changed = deepcopy(step)
            changed["receipt_sha256"] = "sha256:different"
            expected_txn = checkpoint.checkpoint_payload(state, "CAP-a", 0, seed, accepted, changed, None)["transaction_id"]
            before = file_sha(run / "run.json")
            with self.assertRaisesRegex(ValueError, "occupied_order_identity_changed"):
                checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, changed)
            evidence = self.assert_conflict(run, pointer["transaction_id"])
            self.assertEqual(expected_txn, evidence[0]["actual_transaction_id"])
            self.assertEqual(before, file_sha(run / "run.json"))

    def test_payload_conflict_hashes_describe_exact_canonical_payloads_once(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            original = load_json(run / pointer["path"])
            changed = deepcopy(step)
            changed["record"]["delta"]["version"] = True
            actual = checkpoint.checkpoint_payload(state, "CAP-a", 0, seed, accepted, changed, None)
            with self.assertRaises(ValueError):
                checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, changed)
            evidence = self.assert_conflict(run, pointer["transaction_id"])
            self.assertEqual(1, len(evidence))
            self.assertEqual("canonical_payload", evidence[0]["hash_subject"])
            self.assertEqual(canonical_sha(original), evidence[0]["expected_sha256"])
            self.assertEqual(canonical_sha(actual), evidence[0]["actual_sha256"])

    def test_malformed_pointer_and_receipt_paths_preserve_original_error(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            before = file_sha(run / "run.json")
            for bad in ([], "bad", {**pointer, "path": []}, {**pointer, "path": Path("invalid")},
                        {**pointer, "path": "../outside.json"}):
                with self.subTest(pointer=bad), self.assertRaisesRegex(ValueError, "checkpoint_(pointer_missing|path_changed)"):
                    checkpoint.commit_checkpoint(run, state, bad, step, accepted)
            for bad in ([], 3, Path("invalid"), "../outside.json", "bad\0path"):
                changed = deepcopy(step)
                changed["receipt_path"] = bad
                with self.subTest(receipt=bad), self.assertRaises((ValueError, TypeError)):
                    checkpoint.verify_checkpoint(run, state, "CAP-a", 0, seed, accepted,
                        {**changed, "checkpoint": pointer}, None)
                checkpoint.record_conflict(run, state, changed, "checkpoint_receipt_changed")
            self.assertEqual(before, file_sha(run / "run.json"))
            evidence = list((run / "checkpoint-conflicts").glob("*/*.json"))
            self.assertTrue(evidence)

    def test_missing_payload_fields_are_rejected_with_conflict_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step, pointer = self.committed_fixture(run)
            path = run / pointer["path"]
            original = load_json(path)
            for field in ("accepted_seed", "accepted", "predecessor", "selection", "delta"):
                changed = deepcopy(original)
                changed.pop(field)
                atomic_json(path, changed)
                broken_pointer = {**pointer, "payload_sha256": canonical_sha(changed)}
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "checkpoint_payload_incomplete"):
                    checkpoint.commit_checkpoint(run, state, broken_pointer, step, accepted)
                self.assert_conflict(run, pointer["transaction_id"])

    def exercise_completed_public_run(self, action):
        original = plan_mvg.generate
        observed = []

        def generate(root, **kwargs):
            result = original(root, **kwargs)
            if not observed:
                observed.append(True)
                run = root / "logs/ci/mvg-planning/fixture"
                with patch.object(plan_mvg, "run_isolated_model", side_effect=AssertionError("Unexpected model dispatch")):
                    action(root, run, original, kwargs)
            return result

        with patch.object(plan_mvg, "generate", side_effect=generate):
            fixture.CapabilityAppendTests().exercise_public_generation(coordinator_case="mixed")
        self.assertEqual([True], observed)

    def test_public_replay_of_earlier_transaction_preserves_budget_and_projection(self):
        def action(root, run, generate, kwargs):
            state = load_json(run / "run.json")
            before = deepcopy(state["capability_selection"])
            step = before["selected"][0]
            payload = load_json(run / step["checkpoint"]["path"])
            pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0,
                payload["accepted_seed"], payload["accepted"], step)
            self.assertEqual("no-op", checkpoint.commit_checkpoint(run, state, pointer, step, payload["accepted"]))
            generate(root, **kwargs)
            self.assertEqual(before, load_json(run / "run.json")["capability_selection"])
            self.assertEqual(14, before["total_invocations"])
        self.exercise_completed_public_run(action)

    def test_direct_production_replay_rejects_full_prefix_and_successor_corruption(self):
        def action(root, run, generate, kwargs):
            original = load_json(run / "run.json")
            first = original["capability_selection"]["selected"][0]
            payload = load_json(run / first["checkpoint"]["path"])
            proposal_sha = file_sha(run / "proposal.json")
            for mutation in ("order", "budget", "proof", "comparison-output", "successor-predecessor", "accepted",
                             "protocol-deleted", "all-markers-deleted"):
                with self.subTest(mutation=mutation):
                    state = deepcopy(original)
                    artifact, original_bytes = None, None
                    if mutation == "order":
                        state["capability_selection"]["order"].reverse()
                    elif mutation == "budget":
                        state["capability_selection"]["total_invocations"] += 1
                    elif mutation == "accepted":
                        state["capability_selection"]["accepted_sha256"] = "sha256:changed"
                    elif mutation in {"protocol-deleted", "all-markers-deleted"}:
                        state.pop("checkpoint_strategy")
                        state.pop("checkpoint_schema_version")
                        if mutation == "all-markers-deleted":
                            state.pop("generation_strategy")
                            artifact = run / "analysis-input/analysis-index.json"
                    elif mutation == "proof":
                        artifact = run / first["admissions"][first["selected_candidate"]]["proof_path"]
                    elif mutation == "comparison-output":
                        artifact = run / first["selection_path"]
                    else:
                        step = state["capability_selection"]["selected"][1]
                        artifact = run / step["checkpoint"]["path"]
                    try:
                        if artifact:
                            original_bytes = artifact.read_bytes()
                            changed = load_json(artifact)
                            if mutation == "all-markers-deleted":
                                artifact.unlink()
                            elif mutation == "successor-predecessor":
                                changed["predecessor"]["payload_sha256"] = "sha256:changed"
                                step["checkpoint"]["payload_sha256"] = canonical_sha(changed)
                                state["capability_selection"]["checkpoint_head"] = deepcopy(step["checkpoint"])
                            else:
                                changed["unexpected"] = mutation
                            if mutation != "all-markers-deleted":
                                atomic_json(artifact, changed)
                        atomic_json(run / "run.json", state)
                        before = file_sha(run / "run.json")
                        replay_run = (root / "LOGS/CI/MVG-PLANNING/FIXTURE"
                            if mutation == "all-markers-deleted" and sys.platform == "win32" else run)
                        for operation in (
                                lambda: checkpoint.prepare_checkpoint(replay_run, state, "CAP-a", 0,
                                    payload["accepted_seed"], payload["accepted"], first),
                                lambda: checkpoint.commit_checkpoint(replay_run, state, first["checkpoint"], first, payload["accepted"])):
                            with self.assertRaises(ValueError):
                                operation()
                            self.assertEqual(before, file_sha(run / "run.json"))
                            self.assertEqual(proposal_sha, file_sha(run / "proposal.json"))
                        conflicts = [load_json(path) for path in (run / "checkpoint-conflicts").glob("*/*.json")]
                        self.assertTrue(any(row["reason"] for row in conflicts))
                        if mutation == "accepted":
                            self.assertTrue(any(row["hash_subject"] == "accepted_projection_hash" for row in conflicts))
                    finally:
                        if artifact and original_bytes is not None:
                            artifact.write_bytes(original_bytes)
                        atomic_json(run / "run.json", original)
        self.exercise_completed_public_run(action)

    def test_public_and_knowledge_refuse_receipt_payload_and_predecessor_conflicts(self):
        def action(root, run, generate, kwargs):
            from _project_health_planning import _mvg_valid_candidates
            original = load_json(run / "run.json")
            projection = original["capability_selection"]
            proposal_sha = file_sha(run / "proposal.json")
            for mutation in ("receipt-missing", "receipt-changed", "payload", "predecessor"):
                with self.subTest(mutation=mutation):
                    state = deepcopy(original)
                    step = state["capability_selection"]["selected"][1 if mutation == "predecessor" else 0]
                    path = run / (step["receipt_path"] if mutation.startswith("receipt") else step["checkpoint"]["path"])
                    original_bytes = path.read_bytes()
                    try:
                        if mutation == "receipt-missing":
                            path.unlink()
                        else:
                            changed = load_json(path)
                            if mutation == "receipt-changed":
                                changed["attempt"] = 100
                            elif mutation == "payload":
                                changed["delta"]["notes"].append("conflicting-replay")
                            else:
                                changed["predecessor"]["payload_sha256"] = "sha256:changed"
                                pointer = step["checkpoint"]
                                pointer["payload_sha256"] = canonical_sha(changed)
                                state["capability_selection"]["checkpoint_head"] = deepcopy(pointer)
                            atomic_json(path, changed)
                        atomic_json(run / "run.json", state)
                        self.assertEqual([], _mvg_valid_candidates(run, state))
                        with self.assertRaises(ValueError):
                            generate(root, **kwargs)
                        disk = load_json(run / "run.json")["capability_selection"]
                        self.assertEqual(state["capability_selection"]["selected"], disk["selected"])
                        self.assertEqual(state["capability_selection"]["checkpoint_head"], disk["checkpoint_head"])
                        self.assertEqual(projection["accepted_sha256"], disk["accepted_sha256"])
                        self.assertEqual(proposal_sha, file_sha(run / "proposal.json"))
                        evidence = self.assert_conflict(run, step["checkpoint"]["transaction_id"])
                        if mutation.startswith("receipt"):
                            self.assertTrue(any(row["expected_sha256"] != row["actual_sha256"] for row in evidence))
                    finally:
                        path.write_bytes(original_bytes)
                        atomic_json(run / "run.json", original)
        self.exercise_completed_public_run(action)

    def test_real_prefix_recovery_dispatches_only_next_capability_with_recorded_seed(self):
        original_generate, original_commit = plan_mvg.generate, checkpoint.commit_checkpoint
        original_append = selection.generate_append
        interrupted, next_seeds = [], []

        def commit(run, state, pointer, step, accepted, **kwargs):
            result = original_commit(run, state, pointer, step, accepted, **kwargs)
            if not interrupted:
                interrupted.append((run, deepcopy(state)))
                raise SystemExit("fixture_interrupt_before_next_capability_dispatch")
            return result

        def append(*args, **kwargs):
            if kwargs.get("scope_index") == 1:
                next_seeds.append(deepcopy(kwargs["accepted_seed"]))
            return original_append(*args, **kwargs)

        def generate(root, **kwargs):
            if interrupted:
                return original_generate(root, **kwargs)
            with self.assertRaisesRegex(SystemExit, "before_next_capability_dispatch"):
                original_generate(root, **kwargs)
            run, persisted = interrupted[0]
            ledger = persisted["capability_selection"]
            self.assertEqual(1, len(ledger["selected"]))
            self.assertEqual(7, ledger["total_invocations"])
            self.assertIsNone(ledger["current"])
            first = ledger["selected"][0]
            payload = load_json(run / first["checkpoint"]["path"])
            self.assertFalse((run / "candidates/candidate-1/scope-2").exists())
            result = original_generate(root, **kwargs)
            recovered = load_json(run / "run.json")["capability_selection"]
            self.assertEqual(first, recovered["selected"][0])
            self.assertEqual(14, recovered["total_invocations"])
            self.assertEqual([payload["accepted"]] * 3, next_seeds)
            return result

        with patch.object(plan_mvg, "generate", side_effect=generate), \
             patch.object(checkpoint, "commit_checkpoint", side_effect=commit), \
             patch.object(selection, "generate_append", side_effect=append):
            fixture.CapabilityAppendTests().exercise_public_generation(coordinator_case="mixed")
        self.assertEqual(1, len(interrupted))


if __name__ == "__main__":
    unittest.main()
