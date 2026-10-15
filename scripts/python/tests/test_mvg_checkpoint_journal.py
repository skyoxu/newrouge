"""Offline public-entrypoint coverage for checkpoint-bound apply recovery."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _planning_apply_journal as journal
import plan_mvg
import test_mvg_capability_append as append_fixture
from _planning_skill_common import atomic_json, file_sha, load_json


class CheckpointJournalTests(unittest.TestCase):
    def exercise(self):
        append_fixture.CapabilityAppendTests().exercise_public_generation(coordinator_case="apply-replay")

    def test_pending_journal_rejects_changed_or_deleted_checkpoint_authority_before_target_writes(self):
        for mutation in ("payload", "deleted-payload", "state-pointer", "protocol-delete",
                         "missing-binding", "missing-binding-protocol-delete", "receipt"):
            with self.subTest(mutation=mutation):
                original = journal.create_journal
                observed = []

                def create(root, path, targets, *args, **kwargs):
                    before = {target: file_sha(target) if target.is_file() else None for target in targets}
                    result = original(root, path, targets, *args, **kwargs)
                    state_path = path.parent / "run.json"
                    state = load_json(state_path)
                    step = state["capability_selection"]["selected"][0]
                    payload_path = path.parent / step["checkpoint"]["path"]
                    if mutation == "payload":
                        payload = load_json(payload_path)
                        payload["accepted"]["notes"].append("changed-after-journal")
                        atomic_json(payload_path, payload)
                    elif mutation == "deleted-payload":
                        payload_path.unlink()
                    elif mutation == "state-pointer":
                        step["checkpoint"]["payload_sha256"] = "sha256:changed"
                        atomic_json(state_path, state)
                    elif mutation == "protocol-delete":
                        state.pop("checkpoint_strategy")
                        state.pop("checkpoint_schema_version")
                        atomic_json(state_path, state)
                    elif mutation.startswith("missing-binding"):
                        changed = deepcopy(result)
                        changed["result"].pop("_mvg_checkpoint_binding")
                        atomic_json(path, changed)
                        if mutation.endswith("protocol-delete"):
                            state.pop("checkpoint_strategy")
                            state.pop("checkpoint_schema_version")
                            atomic_json(state_path, state)
                    else:
                        receipt = path.parent / step["receipt_path"]
                        changed = load_json(receipt)
                        changed["attempt"] = 100
                        atomic_json(receipt, changed)
                    observed.append((path, before))
                    return result

                with patch.object(journal, "create_journal", side_effect=create):
                    # The fixture owns and removes its temporary checkout, so
                    # inspect target hashes while unwinding the rejected apply.
                    original_apply = plan_mvg.apply

                    def apply(*args, **kwargs):
                        try:
                            return original_apply(*args, **kwargs)
                        except ValueError:
                            for journal_path, before in observed:
                                self.assertEqual("pending", load_json(journal_path)["status"])
                                for target, expected in before.items():
                                    self.assertEqual(expected, file_sha(target) if target.is_file() else None)
                            raise

                    with patch.object(plan_mvg, "apply", side_effect=apply), \
                         self.assertRaisesRegex(ValueError, "checkpoint journal (evidence|binding)"):
                        self.exercise()
                self.assertEqual(1, len(observed))

    def test_completed_journal_rejects_checkpoint_tampering_on_replay(self):
        original = journal.resume_journal
        observed = []

        def resume(root, path, writer):
            result = original(root, path, writer)
            self.assertEqual("complete", load_json(path)["status"])
            state = load_json(path.parent / "run.json")
            pointer = state["capability_selection"]["selected"][0]["checkpoint"]
            payload_path = path.parent / pointer["path"]
            payload = load_json(payload_path)
            payload["accepted"]["notes"].append("changed-after-complete")
            atomic_json(payload_path, payload)
            observed.append(True)
            return result

        with patch.object(journal, "resume_journal", side_effect=resume), \
             self.assertRaisesRegex(ValueError, "checkpoint journal evidence changed"):
            self.exercise()
        self.assertEqual([True], observed, "Replay must reject drift before reentering the journal writer")

    def test_completed_replay_preserves_mutable_handoff_bindings_and_public_result(self):
        original = journal.resume_journal
        calls = []

        def resume(root, path, writer):
            result = original(root, path, writer)
            self.assertIn("_mvg_checkpoint_binding", result)
            trace_path = root / result["trace_path"]
            trace = load_json(trace_path)
            trace["handoff_bindings"] = {"fixture-task": {"status": "valid"}}
            atomic_json(trace_path, trace)
            calls.append(True)
            return result

        original_apply = plan_mvg.apply

        def apply(*args, **kwargs):
            result = original_apply(*args, **kwargs)
            self.assertNotIn("_mvg_checkpoint_binding", result)
            return result

        with patch.object(journal, "resume_journal", side_effect=resume), \
             patch.object(plan_mvg, "apply", side_effect=apply):
            self.exercise()
        self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main()
