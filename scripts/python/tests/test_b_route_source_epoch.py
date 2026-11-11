"""Offline epoch fixtures; mocked source verification is not native acceptance."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_execution_transition as transition
import _b_route_review_recovery as recovery


class SourceEpochTests(unittest.TestCase):
    def setUp(self):
        directory = r"C:\Windows\TEMP" if os.name == "nt" else tempfile.gettempdir()
        self.temp = tempfile.TemporaryDirectory(prefix="bre-" + uuid.uuid4().hex[:8] + "-", dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old_root, self.new_root, self.original_root = [self.root / name for name in ("r7", "r8", "r5")]
        for path in (self.old_root, self.new_root, self.original_root):
            path.mkdir()
        self.run = self.root / "logs/ci/capability-planning/c4"
        self.run.mkdir(parents=True)
        self.old_commit, self.new_commit = "7" * 40, "8" * 40
        self.base = {
            "schema_version": transition.SCHEMA, "original_source_root": str(self.original_root),
            "original_commit": transition.ORIGINAL_COMMIT, "artifact_root": str(self.root),
            "original_run_schema": transition.ORIGINAL_RUN_SCHEMA, "prepared_ref": "fixture/prepared.json",
            "prepared_raw_digest": codec.raw_digest(b"fixture"), "frozen_sha256": codec.canonical_digest("fixture"),
            "original_runtime_identity": codec.canonical_digest("runtime"), "original_runtime_rules": {"fixture": True},
            "original_tracked_sources": {"original.py": {"raw_digest": "old"}},
        }
        prepared = self.root / self.base["prepared_ref"]
        prepared.parent.mkdir(parents=True)
        prepared.write_bytes(b"fixture")  # Raw pin for this explicitly mocked collector.
        self.prior = self.envelope(self.old_root, self.old_commit)
        self.state = {
            "schema_version": transition.CURRENT_RUN_SCHEMA, "run_id": "c4",
            "b_route_execution_transition": self.prior, "active_elapsed_seconds": 30.5,
            "runtime_identity": self.base["original_runtime_identity"],
            "planning_runtime": {"planner": "capabilities"}, "mvg.run_invocation_limit": 96,
            "b_route_campaign_funding": {"before": 55, "maximum": 43, "full": 192},
            "capability_selection": {"calls": [], "total_invocations": 6,
                                    "lineage_invocations": {"candidate-1": 6, "candidate-2": 0}},
        }
        self.bindings = []
        for number in range(1, 7):
            relative = "candidates/candidate-1/scope-1/capability-append/c" + str(number)
            binding = {"output_path": str(self.run / relative / "output.json"), "fixture": number}
            request = {"execution_binding_path": relative + "/binding.json", "output_path": relative + "/output.json"}
            self.state["capability_selection"]["calls"].append({
                "number": number, "reservation_id": "c4:dispatch:" + str(number), "request_identity": request,
                "outcome": {"status": "completed" if number < 6 else "failed", "active_elapsed_seconds": number},
            })
            self.bindings.append(binding)
            if number < 6:
                self.put(self.run / request["execution_binding_path"], binding)
        self.proof = {"execution_source_transition": self.prior, "fixture": "unchanged admitted candidate-1"}
        self.proof_path = self.run / "candidates/candidate-1/scope-1/admission-review.json"
        self.put(self.proof_path, self.proof)
        self.state["capability_selection"]["current"] = {"admissions": {"candidate-1": {
            "status": "admitted", "proof_path": self.proof_path.relative_to(self.run).as_posix()}}}
        self.put(self.run / "run.json", self.state)
        self.collect_patch = patch.object(transition, "_collect", side_effect=self.collect)
        self.collect_mock = self.collect_patch.start()
        self.addCleanup(self.collect_patch.stop)
        self.source_patch = patch.object(transition, "_SOURCE_ROOT", self.new_root)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def envelope(self, root, commit):
        body = {**self.base, "current_source_root": str(root), "current_commit": commit,
                "current_tracked_sources": {"runtime.py": {"raw_digest": commit}}}
        return {**body, "transition_digest": codec.canonical_digest(body)}

    def collect(self, root, state, original_root, current_commit, *, current_root=None):
        expected_root = self.new_root if current_root is None else Path(current_root)
        expected_commit = self.new_commit if expected_root == self.new_root else self.old_commit
        if expected_root not in (self.old_root, self.new_root) or current_commit != expected_commit:
            raise transition.TransitionError("fixture_source_drift")
        body = self.envelope(expected_root, expected_commit)
        body.pop("transition_digest")
        return body, {"fixture": "lossless insertion order"}

    def active(self):
        value = transition.build_successor_transition(self.root, self.state, self.original_root, self.new_commit,
                                                     self.old_root, self.old_commit)
        state = deepcopy(self.state)
        state["b_route_execution_transition"] = value
        state["b_route_execution_history"] = {self.prior["transition_digest"]: deepcopy(self.prior)}
        return state

    def digest(self, value):
        value["transition_digest"] = codec.canonical_digest({k: v for k, v in value.items() if k != "transition_digest"})

    def test_successor_preserves_six_calls_bytes_original_source_and_admission(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        active = self.active()
        epoch = active["b_route_execution_transition"]
        self.assertEqual(transition.validate_transition(self.root, self.state), self.prior["transition_digest"])
        self.assertEqual(transition.validate_transition(self.root, active), epoch["transition_digest"])
        self.assertEqual(transition._previous_state(epoch), self.state)
        self.assertEqual(active["capability_selection"], self.state["capability_selection"])
        self.assertEqual(transition.source_state_for_proof(self.root, active, self.proof), self.state)
        for number in (4, 5):
            materials = {"phase": "generation" if number == 5 else "independent_admission",
                         "execution_source_transition": self.prior["transition_digest"]}
            self.assertEqual(transition.source_state_for_materials(self.root, active, materials, self.bindings[number-1]), self.state)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        # Future admissions do not change the immutable historical membership.
        self.put(self.run / "candidates/candidate-2/scope-1/admission-review.json", {"fixture": "future R8"})
        self.assertEqual(transition.validate_transition(self.root, active), epoch["transition_digest"])
        self.assertTrue(any(call.kwargs.get("current_root") == str(self.old_root) for call in self.collect_mock.call_args_list))

    def test_historical_native_as_posix_output_path_matches_without_rewriting_binding(self):
        # Native capture_binding stores as_posix(), including on real Windows.
        binding = {**self.bindings[4], "output_path": Path(self.bindings[4]["output_path"]).as_posix()}
        path = self.run / self.state["capability_selection"]["calls"][4]["request_identity"]["execution_binding_path"]
        self.put(path, binding)
        raw = path.read_bytes()
        active = self.active()
        materials = {"phase": "generation", "execution_source_transition": self.prior["transition_digest"]}
        self.assertEqual(transition.source_state_for_materials(self.root, active, materials, binding), self.state)
        self.assertEqual(path.read_bytes(), raw)
        rewritten = {**binding, "fixture": "changed despite same output path"}
        with self.assertRaisesRegex(transition.TransitionError, "historical_binding_changed"):
            transition.source_state_for_materials(self.root, active, materials, rewritten)
        for invalid in (None, 5, "relative/output.json", str(self.root / "outside.json"),
                        str(self.run / ".." / "outside.json")):
            with self.subTest(output_path=invalid), self.assertRaisesRegex(transition.TransitionError, "invalid_output_path"):
                transition.source_state_for_materials(self.root, active, materials, {**binding, "output_path": invalid})

    def test_unknown_duplicate_source_mismatch_and_repeat_fail_closed(self):
        for mutation in ("unknown", "duplicate", "ordinal", "total"):
            state = deepcopy(self.state)
            if mutation == "unknown":
                state["capability_selection"]["calls"][-1]["outcome"]["status"] = "unknown"
            elif mutation == "duplicate":
                state["capability_selection"]["calls"][-1]["reservation_id"] = "c4:dispatch:5"
            elif mutation == "ordinal":
                state["capability_selection"]["calls"][-1]["number"] = 5
            else:
                state["capability_selection"]["total_invocations"] = 5
            with self.subTest(mutation=mutation), self.assertRaises(transition.TransitionError):
                transition.build_successor_transition(self.root, state, self.original_root, self.new_commit, self.old_root, self.old_commit)
        with self.assertRaises(transition.TransitionError):
            transition.build_successor_transition(self.root, self.state, self.original_root, self.new_commit, self.old_root, "9"*40)
        active = self.active()
        with self.assertRaises(transition.TransitionError):
            transition.build_successor_transition(self.root, active, self.original_root, self.new_commit, self.old_root, self.old_commit)

    def test_history_source_drift_lowered_clock_and_paid_prefix_tampering_rejected(self):
        active = self.active()
        for mutation in ("history", "clock", "nan", "paid", "native96", "lineage"):
            value = deepcopy(active)
            if mutation == "history":
                value["b_route_execution_history"] = {}
            elif mutation == "clock":
                value["active_elapsed_seconds"] = 30.4
            elif mutation == "nan":
                value["active_elapsed_seconds"] = float("nan")
            elif mutation == "paid":
                value["capability_selection"]["calls"][4]["outcome"]["active_elapsed_seconds"] = 0
            elif mutation == "native96":
                value["mvg.run_invocation_limit"] = 97
            else:
                value["capability_selection"]["lineage_invocations"]["candidate-1"] = 5
            with self.subTest(mutation=mutation), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.root, value)
        with patch.object(transition, "_collect", side_effect=transition.TransitionError("fixture_source_drift")):
            with self.assertRaisesRegex(transition.TransitionError, "source_drift"):
                transition.validate_transition(self.root, active)

    def test_historical_proof_binding_artifact_and_unknown_envelope_rejected(self):
        active = self.active()
        materials = {"execution_source_transition": self.prior["transition_digest"]}
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_materials(self.root, active, materials, self.bindings[5])
        binding = {**self.bindings[4], "fixture": "rewritten"}
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_materials(self.root, active, materials, binding)
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_materials(self.root, active, {"execution_source_transition": "sha256:unknown"}, self.bindings[4])
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_proof(self.root, active, {**self.proof, "fixture": "new proof"})
        self.put(self.proof_path, {**self.proof, "fixture": "rewritten file"})
        with self.assertRaisesRegex(transition.TransitionError, "historical_artifact"):
            transition.validate_transition(self.root, active)

    def test_recovery_keeps_r7_record_and_committed_identity_under_r8(self):
        original = deepcopy(self.state)
        original["capability_selection"]["calls"] = original["capability_selection"]["calls"][:3]
        original["capability_selection"]["total_invocations"] = 3
        original["capability_selection"]["lineage_invocations"]["candidate-1"] = 3
        original["active_elapsed_seconds"] = 8
        home = self.run / "recovery/review-1"
        record = {"schema_version": recovery.SCHEMA, "run_id": "c4", "run_ref": self.run.relative_to(self.root).as_posix(),
                  "transition": self.prior, "original_run": original, "immutable_original_files": {},
                  "campaign_funding": self.state["b_route_campaign_funding"]}
        self.put(home / "record.json", record)
        ref = {"schema_version": recovery.SCHEMA, "record_ref": (home / "record.json").relative_to(self.root).as_posix(),
               "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(self.root)}
        self.state["b_route_review_recovery"] = ref
        self.put(self.run / "run.json", self.state)
        self.put(home / "committed.json", {"record_digest": ref["record_digest"], "transition_digest": self.prior["transition_digest"]})
        original_record = (home / "record.json").read_bytes()
        original_marker = (home / "committed.json").read_bytes()
        active = self.active()
        self.assertEqual(recovery.validate_recovery(self.root, active), record)
        self.assertEqual((home / "record.json").read_bytes(), original_record)
        self.assertEqual((home / "committed.json").read_bytes(), original_marker)
        (home / "committed.json").unlink()
        with self.assertRaises(OSError):
            recovery.validate_recovery(self.root, active)


if __name__ == "__main__":
    unittest.main()
