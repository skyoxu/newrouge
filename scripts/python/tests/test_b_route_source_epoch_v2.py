"""R9 nested-source fixtures; mocked original native witness is not acceptance."""
from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_execution_transition as transition
import _b_route_review_recovery as review
import _b_route_synthesis_recovery as synthesis

spec = importlib.util.spec_from_file_location("epoch_fixture_v1", Path(__file__).with_name("test_b_route_source_epoch.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class SourceEpochV2Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SourceEpochTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        f.collect_patch.stop()  # Exercise actual _collect and transaction/witness logic.
        self.r9root = f.root / "r9"
        self.r9root.mkdir()
        self.r9commit = "9" * 40
        self.frozen = {"input_identity": codec.canonical_digest("fixture-input"), "fixture": "raw order preserved"}
        prepared = f.root / f.base["prepared_ref"]
        f.put(prepared, self.frozen)
        desc = {"planner": "capabilities", "prepared_ref": f.base["prepared_ref"],
                "input_identity": self.frozen["input_identity"], "frozen_sha256": codec.canonical_digest(self.frozen),
                "rules": {"fixture": True}}
        f.base.update(prepared_raw_digest=codec.raw_digest(prepared.read_bytes()), frozen_sha256=desc["frozen_sha256"],
                      original_runtime_identity=codec.canonical_digest(desc))
        f.prior = f.envelope(f.old_root, f.old_commit)
        f.state.update(runtime_identity=codec.canonical_digest(desc), planning_runtime=desc,
                       b_route_execution_transition=f.prior, phase="selection-blocked", selection_status="blocked",
                       selection_block_reason="selection_blocked_insufficient_admitted_candidates",
                       b_route_output_schema_policy="fixture-policy")
        f.state["b_route_campaign_funding"] = {"schema_version": "newrouge.story25-native-funding.v1",
            "paid_or_unknown_before_run": 55, "campaign_limit": 290, "subsequent_full_reservation": 192,
            "maximum_native_charges": 43, "released": 0}
        ledger = f.state["capability_selection"]
        ledger.update(lineage_invocations={"candidate-1": 4, "candidate-2": 2}, selected=[], terminal=True)
        ledger["current"].update(order_index=0, execution=1, selection_attempts=[], capability_id="fixture",
                                 base_sha256=codec.canonical_digest("fixture-base"))
        ledger["current"]["admissions"]["candidate-2"] = {"status": "blocked"}
        for number, row in enumerate(ledger["calls"], 1):
            row.update(candidate="candidate-1" if number <= 4 else "candidate-2", generation=1, execution=1,
                       phase="semantic" if number in (3, 4) else "generate")
            row["request_identity"].update(attempt=number if number <= 4 else number-4, synthesis=number == 6)
        f.proof = {"execution_source_transition": f.prior, "fixture": "unchanged admitted candidate-1"}
        f.put(f.proof_path, f.proof)
        self.manifests = {str(f.original_root): deepcopy(f.base["original_tracked_sources"]),
                          str(f.old_root): deepcopy(f.prior["current_tracked_sources"]),
                          str(f.new_root): f.envelope(f.new_root, f.new_commit)["current_tracked_sources"],
                          str(self.r9root): f.envelope(self.r9root, self.r9commit)["current_tracked_sources"]}
        self.commits = {str(f.original_root): transition.ORIGINAL_COMMIT, str(f.old_root): f.old_commit,
                        str(f.new_root): f.new_commit, str(self.r9root): self.r9commit}
        self.source_calls = []
        self.stale = False
        self.stack = []
        for target, value in (("_source_manifest", self.source_manifest), ("_allowed_delta", lambda *a: ["fixture"]),
                              ("_semantic_unchanged", lambda *a: {"fixture": "unchanged"})):
            item = patch.object(transition, target, side_effect=value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(transition, "_run_original", side_effect=self.original)
        self.native = item.start()
        self.addCleanup(item.stop)
        self.review_record = self.install_review_record(f.state)
        f.put(f.run / "run.json", f.state)
        self.r8 = self.activate(f.state, f.new_root, f.new_commit, f.old_root, f.old_commit)
        self.old_append = {"status": "blocked", "total_invocations": 2,
            "calls": [{"reservation_id": "c4:dispatch:5"}, {"reservation_id": "c4:dispatch:6"}],
            "records": [], "completed": [], "binding": "fixture",
            "current": {"context": 1, "issue": None, "proposal": None, "delta": None}}
        self.synth_record = self.install_synthesis_record(self.r8)
        for number in (7, 8):
            relative = "candidates/candidate-2/scope-1/capability-append/c" + str(number)
            binding = {"output_path": (f.run / relative / "output.json").as_posix(), "fixture": number}
            request = {"execution_binding_path": relative + "/binding.json", "output_path": relative + "/output.json"}
            self.r8["capability_selection"]["calls"].append({"number": number, "reservation_id": "c4:dispatch:" + str(number),
                "candidate": "candidate-2", "phase": "generate" if number == 7 else "repair",
                "request_identity": request, "outcome": {"status": "completed", "active_elapsed_seconds": 300.0}})
            f.put(f.run / request["execution_binding_path"], binding)
            f.bindings.append(binding)
        self.r8["capability_selection"].update(total_invocations=8, lineage_invocations={"candidate-1": 4, "candidate-2": 4})
        self.r8["active_elapsed_seconds"] = 4882.767
        self.r8["fixture_candidate2_elapsed"] = 1474.719
        local = deepcopy(self.old_append)
        local["calls"] += [{"reservation_id": "c4:dispatch:7"}, {"reservation_id": "c4:dispatch:8"}]
        local["total_invocations"] = 4
        f.put(f.run / synthesis.WORKSPACE / "capability-append/append-ledger.json", local)
        f.put(f.run / "run.json", self.r8)
        self.r9 = self.activate(self.r8, self.r9root, self.r9commit, f.new_root, f.new_commit)
        self.native.reset_mock()
        self.source_calls.clear()

    def image(self, value):
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        return {"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}

    def install(self, home, schema, record):
        f = self.f
        f.put(home / "record.json", record)
        reference = {"schema_version": schema, "record_ref": (home / "record.json").relative_to(f.root).as_posix(),
                     "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(f.root)}
        f.put(home / "committed.json", {"record_digest": reference["record_digest"],
                                      "transition_digest": record["transition"]["transition_digest"]})
        return reference

    def install_review_record(self, state):
        f = self.f
        original = deepcopy(state)
        original["schema_version"] = transition.ORIGINAL_RUN_SCHEMA
        original.pop("b_route_execution_transition")
        original["capability_selection"]["calls"] = original["capability_selection"]["calls"][:3]
        original["active_elapsed_seconds"] = 8.5
        record = {"schema_version": review.SCHEMA, "run_id": "c4", "run_ref": f.run.relative_to(f.root).as_posix(),
                  "transition": f.prior, "original_run": original, "campaign_funding": state["b_route_campaign_funding"],
                  "immutable_original_files": {f.proof_path.relative_to(f.run).as_posix(): codec.raw_digest(f.proof_path.read_bytes())}}
        state["b_route_review_recovery"] = self.install(f.run / "recovery/review-fixture", review.SCHEMA, record)
        return record

    def install_synthesis_record(self, state):
        f = self.f
        original = transition._previous_state(state["b_route_execution_transition"])
        record = {"schema_version": synthesis.SCHEMA, "run_id": "c4", "run_ref": f.run.relative_to(f.root).as_posix(),
            "transition": state["b_route_execution_transition"], "history": state["b_route_execution_history"],
            "previous_run": self.image(original), "previous_append": self.image(self.old_append),
            "output_schema_policy": state["b_route_output_schema_policy"],
            "immutable_files": {f.proof_path.relative_to(f.run).as_posix(): codec.raw_digest(f.proof_path.read_bytes())}}
        state["b_route_synthesis_recovery"] = self.install(f.run / "recovery/synthesis-fixture", synthesis.SCHEMA, record)
        return record

    def source_manifest(self, root, commit):
        key = str(Path(root))
        self.assertEqual(self.commits[key], commit)
        self.source_calls.append(key)
        return deepcopy(self.manifests[key])

    def original(self, original_root, artifact_root, state):
        if self.stale:
            raise transition.TransitionError("fixture_external_3a_not_current")
        desc = state["planning_runtime"]
        return {"frozen": deepcopy(self.frozen), "prepared_raw_digest": codec.raw_digest((self.f.root / desc["prepared_ref"]).read_bytes()),
                "runtime_rules": desc["rules"], "runtime_identity": state["runtime_identity"], "frozen_sha256": desc["frozen_sha256"]}

    def activate(self, state, root, commit, prior_root, prior_commit):
        f = self.f
        with patch.object(transition, "_SOURCE_ROOT", root):
            envelope = transition.build_successor_transition(f.root, state, f.original_root, commit, prior_root, prior_commit)
        value = deepcopy(state)
        value["b_route_execution_history"] = {**deepcopy(state.get("b_route_execution_history", {})),
            state["b_route_execution_transition"]["transition_digest"]: deepcopy(state["b_route_execution_transition"])}
        value["b_route_execution_transition"] = envelope
        return value

    def redigest(self, envelope):
        envelope["transition_digest"] = codec.canonical_digest({k: v for k, v in envelope.items() if k != "transition_digest"})

    def test_nested_lookup_routes_original_r7_proof_and_r8_paid_bindings(self):
        f = self.f
        self.assertEqual(self.r9["b_route_execution_transition"]["schema_version"], transition.EPOCH_V2_SCHEMA)
        self.assertEqual(self.r9["capability_selection"], self.r8["capability_selection"])
        self.assertEqual(self.r9["active_elapsed_seconds"], 4882.767)
        self.assertEqual(self.r9["fixture_candidate2_elapsed"], 1474.719)
        self.assertEqual(self.r9["mvg.run_invocation_limit"], 96)
        self.assertEqual(self.r9["b_route_campaign_funding"], self.r8["b_route_campaign_funding"])
        self.assertEqual(transition.source_state_for_proof(f.root, self.r9, f.proof)["b_route_execution_transition"], f.prior)
        for index in (6, 7):
            previous = transition.source_state_for_materials(f.root, self.r9,
                {"execution_source_transition": self.r8["b_route_execution_transition"]["transition_digest"]}, f.bindings[index])
            self.assertEqual(previous, self.r8)
        self.assertEqual(set(self.r9["b_route_execution_history"]),
                         {f.prior["transition_digest"], self.r8["b_route_execution_transition"]["transition_digest"]})

    def test_one_fresh_original_witness_per_outer_call_all_sources_rechecked(self):
        transition.validate_transition(self.f.root, self.r9)
        self.assertEqual(self.native.call_count, 1)
        for root in self.manifests:
            self.assertEqual(self.source_calls.count(root), 2)  # First scan plus fresh closure.
        self.stale = True
        with self.assertRaisesRegex(transition.TransitionError, "external_3a"):
            transition.load_prepared(self.f.root, self.r9)
        self.assertEqual(self.native.call_count, 2)
        self.assertIsNone(transition._ACTIVE_VERIFICATION.get())

    def test_nested_descriptor_mismatch_cannot_share_a_native_witness(self):
        state = deepcopy(self.r9)
        value = state["b_route_execution_transition"]
        previous = transition._previous_state(value)
        previous["planning_runtime"]["rules"] = {"fixture": "changed"}
        previous["runtime_identity"] = codec.canonical_digest(previous["planning_runtime"])
        value["previous_run"] = self.image(previous)
        self.redigest(value)
        with self.assertRaisesRegex(transition.TransitionError, "nested_original_binding"):
            transition.validate_transition(self.f.root, state)
        self.native.assert_not_called()

    def test_tampered_history_cycles_and_unknown_source_fail_closed(self):
        state = deepcopy(self.r9)
        state["b_route_execution_history"].pop(self.f.prior["transition_digest"])
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(self.f.root, state)
        with self.assertRaises(transition.TransitionError):
            transition.historical_state(self.f.root, self.r9, "sha256:" + "0"*64)
        cyclic = deepcopy(self.r9)
        cyclic["b_route_execution_transition"]["prior_transition"] = cyclic["b_route_execution_transition"]
        with self.assertRaises(ValueError):
            transition.validate_transition(self.f.root, cyclic)

    def test_unknown_new_dispatch_refunds_clock_and_budget_tampering_rejected(self):
        for mutation in ("clock", "charge", "time", "lineage", "funding", "native"):
            state = deepcopy(self.r9)
            if mutation == "clock":
                state["active_elapsed_seconds"] = 4882.766
            elif mutation == "charge":
                state["capability_selection"]["total_invocations"] = 7
            elif mutation == "time":
                state["capability_selection"]["calls"][7]["outcome"]["active_elapsed_seconds"] = 0
            elif mutation == "lineage":
                state["capability_selection"]["lineage_invocations"]["candidate-2"] = 3
            elif mutation == "funding":
                state["b_route_campaign_funding"]["released"] = 1
            else:
                state["mvg.run_invocation_limit"] = 97
            with self.subTest(mutation=mutation), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.f.root, state)
        old = deepcopy(self.r8)
        old["capability_selection"]["calls"][7]["outcome"]["status"] = "unknown"
        self.f.put(self.f.run / "run.json", old)
        with self.assertRaises(transition.TransitionError):
            self.activate(old, self.r9root, self.r9commit, self.f.new_root, self.f.new_commit)

    def test_artifact_tamper_and_source_drift_during_closure_rejected(self):
        f = self.f
        binding = f.run / self.r8["capability_selection"]["calls"][7]["request_identity"]["execution_binding_path"]
        original = binding.read_bytes()
        binding.write_bytes(original + b"\n")
        with self.assertRaisesRegex(transition.TransitionError, "historical_artifact"):
            transition.validate_transition(f.root, self.r9)
        binding.write_bytes(original)
        def changed(*args):
            result = self.original(*args)
            self.manifests[str(self.r9root)]["runtime.py"]["raw_digest"] = "changed-at-closure"
            return result
        self.native.side_effect = changed
        with self.assertRaisesRegex(transition.TransitionError, "source_changed_during_transaction"):
            transition.validate_transition(f.root, self.r9)

    def test_actual_recovery_callers_keep_original_records_and_committed_source(self):
        f = self.f
        before = {path: path.read_bytes() for path in (f.run / "recovery").rglob("*.json")}
        self.assertEqual(review.validate_recovery(f.root, self.r9), self.review_record)
        self.assertEqual(synthesis.validate_recovery(f.root, self.r9), self.synth_record)
        self.assertEqual(before, {path: path.read_bytes() for path in (f.run / "recovery").rglob("*.json")})
        lowered = deepcopy(self.r9)
        lowered["active_elapsed_seconds"] = 4882.766
        with self.assertRaises(ValueError):
            synthesis.validate_recovery(f.root, lowered)


if __name__ == "__main__":
    unittest.main()
