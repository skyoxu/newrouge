"""Focused synthetic metadata/control tests; no native admission or model proof.

The fixture helpers are available for Root's separately owned composition tests.
Only the frozen-barrier coordinator should import or execute this file.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_mvg_synthesis_recovery as recovery


def make_prefix():
    """Synthetic exact-shaped metadata, explicitly not genuine paid bindings."""
    sequence = [("candidate-1", "generate", False), ("candidate-1", "generate", True),
                ("candidate-1", "repair", False), ("candidate-1", "repair", True),
                ("candidate-1", "semantic", False), ("candidate-2", "generate", False),
                ("candidate-2", "generate", True)]
    calls = [{"number": n, "reservation_id": f"m4:dispatch:{n}", "candidate": slot,
              "phase": phase, "generation": 1, "execution": 1,
              "request_identity": {"attempt": n if n <= 5 else n - 5, "synthesis": synthesis},
              "outcome": {"status": "completed", "active_elapsed_seconds": 1.0}}
             for n, (slot, phase, synthesis) in enumerate(sequence, 1)]
    admissions = {slot: {"status": status, "total_invocations": count,
                        "append_terminal": terminal, "retryable": False, "generation": 1, "execution": 1}
                  for slot, status, count, terminal in [("candidate-1", "admitted", 5, False),
                                                       ("candidate-2", "blocked", 2, True)]}
    state = {"run_id": "m4", "input_stage": "3b", "planning_runtime": {"planner": "mvg", "profile": "3b-mvg-v1",
              "limits": {"request_limit": 192}}, "mvg.run_invocation_limit": 192, "active_elapsed_seconds": 7.0,
             "selection_status": "blocked", "selection_block_reason": "selection_blocked_insufficient_admitted_candidates",
             "capability_selection": {"calls": calls, "total_invocations": 7,
                 "lineage_invocations": {"candidate-1": 5, "candidate-2": 2, "candidate-3": 0},
                 "terminal": True, "selected": [], "current": {"order_index": 0, "execution": 1,
                     "selection_attempts": [], "admissions": admissions}},
             "b_route_campaign_funding": {"schema_version": "newrouge.story25-native-funding.v1",
                 "paid_or_unknown_before_run": 66, "campaign_limit": 290, "subsequent_full_reservation": 0,
                 "maximum_native_charges": 224, "released": 0}}
    append = {"status": "blocked", "total_invocations": 2, "calls": [{"number": n, "phase": "generate",
               "reservation_id": f"m4:dispatch:{n + 5}"} for n in (1, 2)], "records": [], "completed": [],
              "current": {"context": 1, "issue": None, "proposal": None, "delta": None, "issue_attempts": {}},
              "errors": [{"code": "append_execution_failure", "stage": "generate",
                          "error_type": "runner_execution_failed", "detail": "schema_validation_failed"}]}
    return state, append


def make_material_fixture():
    """Two complete placeholder drafts, only for explicit mocked composition."""
    drafts = [{"stage": "batch", "ordinal": 1, "content": {"synthetic": "original-batch"}},
              {"stage": "synthesis", "ordinal": 2, "content": {"synthetic": "retained-invalid-content"}}]
    seed = {"synthetic": "original-readonly-seed"}
    state = {recovery.REFERENCE: {"record_digest": "sha256:" + "a" * 64}}
    record = {"batch_draft_digest": recovery.codec.canonical_digest(drafts[0]),
              "rejected_synthesis_draft_digest": recovery.codec.canonical_digest(drafts[1]),
              "previous_append": recovery.image(b'{"accepted":{"synthetic":"original-readonly-seed"}}'),
              "schema_rejection": {"json_pointer": recovery.REJECTION_POINTER,
                  "observed_raw_digest": "sha256:short", "expected_raw_digest": "sha256:" + "b" * 64,
                  "source_path": "synthetic-reference", "structural_observations": []}}
    materials = {"phase": "generation", "slot": "candidate-2", "generation": 1, "execution": 1,
                 "lineage_context": 1, "prior_candidate": None, "repair_issue": None, "accepted_seed": seed,
                 "root_request": {"input": {"stage": "synthesis", "ordinal": 3,
                     "prior_drafts": [{"identity": recovery.codec.canonical_digest(d), "value": deepcopy(d)} for d in drafts]}}}
    return state, record, drafts, materials


class RecoveryMetadataTests(unittest.TestCase):
    def test_exact_seven_completed_metadata_keeps_first_admission_and_second_prefix(self):
        state, append = make_prefix()
        before = deepcopy((state, append))
        recovery.retained_shape(state, append)
        self.assertEqual((state, append), before)

    def test_unknown_refund_c1_change_or_fake_business_issue_are_rejected(self):
        cases = []
        for mutate in [lambda s, a: s["capability_selection"]["calls"][6]["outcome"].update(status="unknown"),
                       lambda s, a: s["b_route_campaign_funding"].update(released=1),
                       lambda s, a: s["capability_selection"]["current"]["admissions"]["candidate-1"].update(status="blocked"),
                       lambda s, a: a["current"].update(issue={"code": "invented_business_issue"}),
                       lambda s, a: a.update(total_invocations=0),
                       lambda s, a: s.update(run_id="replacement-m4")]:
            state, append = make_prefix()
            mutate(state, append)
            cases.append((state, append))
        for number, (state, append) in enumerate(cases):
            with self.subTest(case=number), self.assertRaises(ValueError):
                recovery.retained_shape(state, append)

    def test_boolean_float_metadata_cannot_impersonate_integer_slots(self):
        for mutate in [lambda s, a: s["capability_selection"]["calls"][0].update(generation=True),
                       lambda s, a: s["capability_selection"]["lineage_invocations"].update({"candidate-3": False}),
                       lambda s, a: s["b_route_campaign_funding"].update(released=False),
                       lambda s, a: a.update(total_invocations=2.0)]:
            state, append = make_prefix()
            mutate(state, append)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                recovery.retained_shape(state, append)

    def test_one_hint_preserves_both_original_drafts_and_ordinary_issue_is_none(self):
        state, record, drafts, materials = make_material_fixture()
        before = deepcopy(materials)
        with patch.object(recovery, "validate_recovery", return_value=record), \
             patch.object(recovery, "_check_synthesis_claim") as claim:
            decorated = recovery.decorate_payload(Path("."), state, materials, local_number=3)
            expected = recovery.expected_recovery_materials(Path("."), state, decorated)
        self.assertEqual(expected, decorated[recovery.HINT_KEY])
        self.assertEqual(materials, before)
        self.assertIsNone(decorated["repair_issue"])
        self.assertEqual([p["value"] for p in decorated["root_request"]["input"]["prior_drafts"]], drafts)
        self.assertTrue(claim.called)

    def test_hint_tamper_missing_original_draft_and_second_local_call_are_rejected(self):
        for kind in ("drop-old-synthesis", "replace-parent", "wrong-ordinal", "hint-tamper", "extra-local-call"):
            state, record, drafts, materials = make_material_fixture()
            with patch.object(recovery, "validate_recovery", return_value=record), patch.object(recovery, "_check_synthesis_claim"):
                if kind == "drop-old-synthesis":
                    materials["root_request"]["input"]["prior_drafts"].pop()
                    materials[recovery.HINT_KEY] = {}
                elif kind == "replace-parent":
                    materials["root_request"]["input"]["prior_drafts"][1]["value"] = {"forged": True}
                elif kind == "wrong-ordinal":
                    materials["root_request"]["input"]["ordinal"] = 4
                elif kind == "hint-tamper":
                    materials = recovery.decorate_payload(Path("."), state, materials, local_number=3)
                    materials[recovery.HINT_KEY]["expected_raw_digest"] = "sha256:" + "c" * 64
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    if kind == "extra-local-call":
                        recovery.decorate_payload(Path("."), state, materials, local_number=4)
                    else:
                        recovery.expected_recovery_materials(Path("."), state, materials)

    def test_legacy_other_slots_reviews_and_native_repairs_do_not_receive_hint(self):
        state, record, drafts, original = make_material_fixture()
        for updates in ({"slot": "candidate-1"}, {"slot": "candidate-3"}, {"phase": "independent_admission"},
                        {"repair_issue": {"code": "actual-native-issue"}, "prior_candidate": {"original": True}}):
            material = {**deepcopy(original), **updates}
            with patch.object(recovery, "validate_recovery", return_value=record):
                self.assertIsNone(recovery.expected_recovery_materials(Path("."), state, material))
                self.assertEqual(recovery.decorate_payload(Path("."), state, material, local_number=4), material)
        with self.assertRaises(ValueError):
            recovery.expected_recovery_materials(Path("."), {}, {recovery.HINT_KEY: {}})

    def test_preview_has_same_exact_hint_without_consuming_dispatch_claim(self):
        state, record, drafts, materials = make_material_fixture()
        with patch.object(recovery, "validate_recovery", return_value=record), \
             patch.object(recovery, "_check_synthesis_claim", side_effect=ValueError("claim absent")) as claim:
            preview = recovery.preview_payload(Path("."), state, materials)
            claim.assert_not_called()
            self.assertEqual([row["value"] for row in preview["root_request"]["input"]["prior_drafts"]], drafts)
            with self.assertRaises(ValueError):
                recovery.expected_recovery_materials(Path("."), state, preview)
            claim.assert_called_once()

    def test_preview_and_resume_share_original_two_binding_checks_and_claim_only_once(self):
        # All proof collaborators below are explicit synthetic mocks. This tests
        # control order and paid-chain preservation, never real protocol proof.
        root = Path("synthetic-only-root").resolve()
        run = root / recovery.RUN_REF
        workspace = run / recovery.WORKSPACE
        state, append = make_prefix()
        state.update(runtime_slot="candidate-2")
        state[recovery.REFERENCE] = {"record_ref": recovery.RUN_REF + "/recovery/m1/record.json",
                                   "record_digest": "sha256:" + "d" * 64}
        append.update(accepted={"seed": "original"}, binding="original")
        drafts = [{"ordinal": 1, "stage": "batch", "content": {"synthetic": "batch"}},
                  {"ordinal": 2, "stage": "synthesis", "content": {"synthetic": "bad-synthesis"}}]
        bindings = [{"synthetic_binding": 1}, {"synthetic_binding": 2}]
        record = {"previous_append": recovery.image(json.dumps(append).encode("utf-8")),
                  "batch_draft_ref": "synthetic-batch", "rejected_synthesis_draft_ref": "synthetic-synthesis",
                  "batch_binding_digest": recovery.codec.canonical_digest(bindings[0]),
                  "rejected_synthesis_binding_digest": recovery.codec.canonical_digest(bindings[1]),
                  "batch_draft_digest": recovery.codec.canonical_digest(drafts[0]),
                  "rejected_synthesis_draft_digest": recovery.codec.canonical_digest(drafts[1])}
        checked, claimed = [], set()
        def read(_root, reference):
            if reference == recovery.RUN_REF + "/run.json":
                return deepcopy(state)
            if reference.endswith("append-ledger.json"):
                return deepcopy(append)
            return deepcopy(drafts[0 if reference == "synthetic-batch" else 1])
        def root_request(_runtime, _frozen, previous, batch, _state):
            return {"synthetic_stage": "batch" if batch else "synthesis", "previous_count": len(previous)}
        def material(binding, _state, _frozen):
            i = binding["synthetic_binding"] - 1
            return {"phase": "generation", "slot": "candidate-2", "generation": 1, "execution": 1,
                    "lineage_context": 1, "prior_candidate": None, "repair_issue": None,
                    "lineage_identity": "synthetic-lineage",
                    "accepted_seed": append["accepted"], "root_request": root_request(None, None, drafts[:i], i == 0, state)}
        def verify(_run, row):
            checked.append(row["number"])
            return deepcopy(bindings[row["number"] - 6])
        def durable(path, value, *, exclusive):
            self.assertTrue(exclusive)
            self.assertNotIn(path, claimed)
            claimed.add(path)
            self.assertEqual(value["old_global_calls"], 7)
            self.assertEqual(value["old_local_calls"], 2)
            self.assertEqual(value["rejected_synthesis_draft_digest"], record["rejected_synthesis_draft_digest"])
        fake = SimpleNamespace(verify_reserved_call=verify, verify_call=lambda b: drafts[b["synthetic_binding"] - 1],
                               decode_generation_carrier=lambda value: value, bound_materials=material,
                               lineage_identity=lambda *args: "synthetic-lineage",
                               planning=SimpleNamespace(validate_draft_chain=lambda f, d: None))
        with patch.object(recovery, "validate_recovery", return_value=record), \
             patch.object(recovery, "read", side_effect=read), \
             patch.object(recovery.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref), \
             patch.object(recovery, "json_request", side_effect=root_request), \
             patch.object(recovery.os.path, "lexists", side_effect=lambda path: path in claimed), \
             patch.object(recovery, "_durable", side_effect=durable), \
             patch.dict(sys.modules, {"_b_route_planning_runtime": fake}):
            preview = recovery.preview_generation(root, state, workspace, {}, append["accepted"])
            self.assertEqual(preview, (drafts, bindings))
            self.assertEqual(checked, [6, 7])
            self.assertFalse(claimed)
            resumed = recovery.resume_generation(root, state, workspace, {}, append["accepted"], None, None, 1)
            self.assertEqual(resumed, preview)
            self.assertEqual(checked, [6, 7, 6, 7])
            self.assertEqual(len(claimed), 1)
            with self.assertRaises(ValueError):
                recovery.resume_generation(root, state, workspace, {}, append["accepted"], None, None, 1)
            self.assertEqual(checked, [6, 7, 6, 7])

    def test_call_namespace_keeps_old_paths_and_new_physical_name_is_short(self):
        workspace = Path("fixture")
        self.assertEqual(recovery.call_root({}, workspace, 3, "candidate-2"), workspace / "capability-append/c3")
        self.assertEqual(recovery.call_root({recovery.REFERENCE: {}}, workspace, 3, "candidate-2"), workspace / "capability-append/c3")
        state = {recovery.REFERENCE: {"record_digest": "fixture"}}
        self.assertEqual(recovery.call_root(state, workspace, 2, "candidate-2"), workspace / "capability-append/c2")
        self.assertEqual(recovery.call_root(state, workspace, 3, "candidate-2"), workspace / "capability-append/m1/c3")
        self.assertEqual(recovery.call_root(state, workspace, 3, "candidate-3"), workspace / "capability-append/c3")

    def test_typed_epoch_without_reference_cannot_authorize_or_hide_as_legacy(self):
        for reference in (None, {}):
            state = {"b_route_execution_transition": {"schema_version": recovery.MVG_EPOCH_SCHEMA},
                     "runtime_slot": "candidate-2"}
            if reference is not None:
                state[recovery.REFERENCE] = reference
            for action in (lambda: recovery.call_root(state, Path("fixture"), 3, "candidate-2"),
                           lambda: recovery.expected_recovery_materials(Path("."), state, {}),
                           lambda: recovery.resume_generation(Path("."), state, Path("."), {}, {}, None, None, 1)):
                with self.subTest(reference=reference, action=action), self.assertRaises(ValueError):
                    action()

    def test_graph_observation_uses_unedited_original_edges_without_approval(self):
        start, end = {"flow_id": "flow", "node_id": "guard"}, {"flow_id": "flow", "node_id": "startup"}
        draft = {"content": {"definitions": {"flows": [{"id": "flow", "graph": {"edges": []},
                   "handoffs": [{"id": "profile-to-harness", "from": start, "to": end}]}]}}}
        original = deepcopy(draft)
        observation = recovery.graph_observations(draft)
        self.assertEqual(draft, original)
        self.assertEqual(observation[0]["entity_id"], "profile-to-harness")
        self.assertIs(observation[0]["formal_business_finding"], False)
        draft["content"]["definitions"]["flows"][0]["graph"]["edges"].append({"from": start, "to": end})
        self.assertEqual(recovery.graph_observations(draft), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
