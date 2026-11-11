"""Synthetic control/metadata fixtures; no real protocol/admission/model proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_selector_recovery as owner


def retained_fixture():
    sequence = [("candidate-1", "generate", 1, False), ("candidate-1", "generate", 2, True),
                ("candidate-1", "repair", 3, False), ("candidate-1", "repair", 4, True),
                ("candidate-1", "semantic", 5, False), ("candidate-2", "generate", 1, False),
                ("candidate-2", "generate", 2, True), ("candidate-2", "generate", 3, True),
                ("candidate-2", "semantic", 4, False), ("candidate-3", "generate", 1, False),
                ("candidate-3", "generate", 2, True), ("candidate-3", "semantic", 3, False)]
    calls = [{"number": n, "reservation_id": f"m4:dispatch:{n}", "candidate": slot, "phase": phase,
              "generation": 1, "execution": 1, "request_identity": {"attempt": attempt, "synthesis": synthesis},
              "outcome": {"status": "completed"}} for n, (slot, phase, attempt, synthesis) in enumerate(sequence, 1)]
    admissions = {slot: {"candidate": slot, "status": "admitted", "total_invocations": count,
                        "retryable": False, "append_terminal": False}
                  for slot, count in (("candidate-1", 5), ("candidate-2", 4), ("candidate-3", 3))}
    detail = ("runner_context_budget_exceeded:estimated_input_tokens=114776;continuation_reserve=0;limit=96000;"
              "complete_request_chars=392053;complete_request_bytes=392053;token_counter=max(o200k_base,cl100k_base)+10_percent")
    current = {"order_index": 0, "execution": 1, "stage": "selection-preparing", "selection_attempts": [],
               "aliases": {"A": "candidate-2", "B": "candidate-3", "C": "candidate-1"},
               "input_identity": {"order_index": 0, "synthetic": "complete-original-input"}, "input_sha256": "sha256:" + "a" * 64,
               "admissions": admissions, "preparation_error": {"code": "selection_preparation_failed",
                   "error_type": "runner_execution_failed", "detail": detail}}
    old = {"run_id": "m4", "input_stage": "3b", "planning_runtime": {"planner": "mvg", "profile": "3b-mvg-v1",
            "limits": {"request_limit": 192}}, "mvg.run_invocation_limit": 192, "active_elapsed_seconds": 12.0,
           "phase": "selection-blocked", "selection_status": "blocked", "selection_block_reason": detail,
           "b_route_mvg_synthesis_recovery": {"original": "m1-reference-retained"},
           "b_route_execution_transition": {"schema_version": "newrouge.b-route-mvg-source-epoch.v1", "transition_digest": "old"},
           "b_route_execution_history": {"original-r10": {"actual": "history"}},
           "capability_selection": {"calls": calls, "total_invocations": 12,
               "lineage_invocations": {"candidate-1": 5, "candidate-2": 4, "candidate-3": 3},
               "current": current, "selected": [], "terminal": True},
           "b_route_campaign_funding": {"schema_version": "newrouge.story25-native-funding.v1",
               "paid_or_unknown_before_run": 66, "campaign_limit": 290, "subsequent_full_reservation": 0,
               "maximum_native_charges": 224, "released": 0}}
    anchor = {"original_state": deepcopy(old), "selection": {"scopes": [{"synthetic": "scope0"}],
                "accepted_seed": {"original": "seed"}, "records": [], "aliases": deepcopy(current["aliases"]),
                "input_identity": deepcopy(current["input_identity"]), "input_sha256": current["input_sha256"]},
              "admissions": {slot: {"admission": deepcopy(row), "canonical_digests": {}} for slot, row in admissions.items()},
              "manifest": {"files": {}, "directories": []}}
    state = deepcopy(old)
    state["b_route_execution_transition"] = {"schema_version": owner.SELECTOR_EPOCH_SCHEMA, "transition_digest": "new"}
    state[owner.REFERENCE] = {"schema_version": owner.SCHEMA, "record_ref": owner.RUN_REF + "/recovery/s1/record.json",
                              "record_digest": "sha256:" + "b" * 64, "artifact_root": "synthetic"}
    state["capability_selection"]["terminal"] = False
    state["phase"], state["selection_status"] = "selector-recovery-prepared", "pending"
    return old, state, anchor


def selector_row(anchor):
    return {"number": 13, "reservation_id": "m4:dispatch:13", "phase": "selection", "candidate": None,
            "generation": 1, "execution": 1, "request_identity": {"attempt": 1,
                "selector_transport_policy": "newrouge.b-route-compact-literal.v3",
                "selection_input_sha256": anchor["selection"]["input_sha256"]}}


class SelectorRecoveryTests(unittest.TestCase):
    def test_exact_original_twelve_retained_without_mutation(self):
        old, state, anchor = retained_fixture()
        before = deepcopy(old)
        owner.retained_shape(old)
        self.assertEqual(old, before)

    def test_unknown_missing_admission_or_real_selector_cannot_enter(self):
        changes = [lambda s: s["capability_selection"]["calls"][7]["outcome"].update(status="unknown"),
                   lambda s: s["capability_selection"]["current"]["admissions"]["candidate-3"].update(status="blocked"),
                   lambda s: s["capability_selection"]["current"]["selection_attempts"].append({"status": "running"}),
                   lambda s: s["b_route_campaign_funding"].update(released=1),
                   lambda s: s["capability_selection"].update(total_invocations=11)]
        for change in changes:
            old, _, _ = retained_fixture()
            change(old)
            with self.subTest(change=change), self.assertRaises(ValueError):
                owner.retained_shape(old)

    def test_boolean_or_float_identity_does_not_impersonate_integer(self):
        for change in (lambda s: s["capability_selection"]["calls"][0].update(generation=True),
                       lambda s: s["capability_selection"].update(total_invocations=12.0),
                       lambda s: s["b_route_campaign_funding"].update(released=False)):
            old, _, _ = retained_fixture()
            change(old)
            with self.subTest(change=change), self.assertRaises(ValueError):
                owner.retained_shape(old)

    def test_unsealed_actual_capture_or_self_signed_dictionary_is_not_authority(self):
        with patch.object(owner, "ANCHOR_DIGEST", None), patch.object(owner, "CAPTURE_EXIT_DIGEST", None):
            with self.assertRaises(ValueError):
                owner.capture_retained_selector(Path("synthetic"))
        with self.assertRaises(ValueError):
            owner.verify_retained_selector_capture(Path("synthetic"), {"qualified": True}, current_state={})

    def test_missing_empty_reference_under_typed_epoch_never_falls_back(self):
        for value in (None, {}):
            state = {"b_route_execution_transition": {"schema_version": owner.SELECTOR_EPOCH_SCHEMA}}
            if value is not None:
                state[owner.REFERENCE] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                owner.is_selector_recovery(state)

    def test_current_projection_retains_twelve_and_one_unknown_liability(self):
        old, state, anchor = retained_fixture()
        owner._current_projection(anchor, state)
        state["capability_selection"]["calls"].append(selector_row(anchor))
        state["capability_selection"]["total_invocations"] = 13
        view = owner._current_projection(anchor, state)
        self.assertEqual(view["admissions"], old["capability_selection"]["current"]["admissions"])
        self.assertNotIn("outcome", state["capability_selection"]["calls"][12])
        self.assertEqual(state["capability_selection"]["lineage_invocations"], old["capability_selection"]["lineage_invocations"])

    def test_current_projection_rejects_regeneration_new_execution_or_second_selector(self):
        for change in (lambda s: s["capability_selection"]["current"].update(execution=2),
                       lambda s: s["capability_selection"]["current"]["aliases"].update(A="candidate-1"),
                       lambda s: s["capability_selection"].update(generation=2)):
            _, state, anchor = retained_fixture()
            change(state)
            with self.subTest(change=change), self.assertRaises(ValueError):
                owner._current_projection(anchor, state)
        _, state, anchor = retained_fixture()
        row = selector_row(anchor)
        row.update(candidate="candidate-2", phase="repair")
        state["capability_selection"]["calls"].append(row)
        state["capability_selection"]["total_invocations"] = 13
        with self.assertRaises(ValueError):
            owner._current_projection(anchor, state)

    def test_native_selected_projection_keeps_same_three_admissions(self):
        old, state, anchor = retained_fixture()
        current = state["capability_selection"]["current"]
        step = {key: deepcopy(current[key]) for key in ("input_identity", "input_sha256", "admissions", "aliases", "execution")}
        step.update(status="completed", selected_candidate="candidate-2")
        ledger = state["capability_selection"]
        ledger["calls"].append(selector_row(anchor))
        ledger.update(total_invocations=13, selected=[step], current=None)
        self.assertEqual(owner._current_projection(anchor, state)["admissions"], old["capability_selection"]["current"]["admissions"])

    def test_namespace_is_exact_and_original_generations_cannot_be_retried(self):
        _, state, anchor = retained_fixture()
        root = Path("synthetic").resolve()
        with patch.object(owner.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref):
            self.assertEqual(owner.selector_workspace(root, state, 0, 1), root / owner.RUN_REF / "s1/attempt-1")
            for index, attempt in ((1, 1), (0, 2), (False, 1), (0, True)):
                with self.subTest(index=index, attempt=attempt), self.assertRaises(ValueError):
                    owner.selector_workspace(root, state, index, attempt)

    def test_intent_exclusive_and_does_not_reset_or_reserve_ledger(self):
        _, state, anchor = retained_fixture()
        original = deepcopy(state)
        root = Path("synthetic").resolve()
        request = selector_row(anchor)["request_identity"]
        request["workspace"] = "s1/attempt-1/llm-sandbox/attempt-1/selection"
        written = []
        def durable(path, value, *, exclusive):
            self.assertTrue(exclusive)
            if written:
                raise FileExistsError("synthetic occupied intent")
            written.append((path, value))
        record = {"anchor_identity": {"synthetic": "sealed"}}
        with patch.object(owner, "validate_recovery", return_value=record), \
             patch.object(owner, "read", return_value=deepcopy(state)), \
             patch.object(owner.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref), \
             patch.object(owner, "_durable", side_effect=durable):
            owner.authorize_selector_reservation(root, state, phase="selection", candidate=None, request_identity=request)
            self.assertEqual(state, original)
            self.assertEqual(written[0][1]["next_global_call"], 13)
            with self.assertRaises(FileExistsError):
                owner.authorize_selector_reservation(root, state, phase="selection", candidate=None, request_identity=request)

    def test_nonselector_dispatch_fails_before_any_record_or_intent(self):
        _, state, _ = retained_fixture()
        with patch.object(owner, "validate_recovery") as validation:
            with self.assertRaises(ValueError):
                owner.authorize_selector_reservation(Path("synthetic"), state, phase="generate", candidate="candidate-1", request_identity={})
            validation.assert_not_called()

    def test_archived_m1_validation_receives_genuine_old_frame_not_new_epoch(self):
        old, state, anchor = retained_fixture()
        root = Path("synthetic").resolve()
        identity = {"synthetic": "actual factory identity"}
        capture = owner._RetainedSelectorCapture(owner._SEAL, root, anchor, identity)
        raw = json.dumps(old).encode()
        model = b'{}'
        anchor["manifest"]["files"][owner.RUN_REF + "/model-execution.json"] = owner.codec.raw_digest(model)
        record = {"anchor_identity": identity, "transition": state["b_route_execution_transition"],
                  "history": state["b_route_execution_history"], "previous_run": owner.image(raw),
                  "model_execution_preimage": owner.image(model)}
        delegated = []
        previous = SimpleNamespace(validate_recovery=lambda r, value: delegated.append(deepcopy(value)))
        with patch.object(owner, "_record", return_value=record), \
             patch.object(owner, "capture_retained_selector", return_value=capture), \
             patch.object(owner, "verify_retained_selector_capture", return_value=deepcopy(old)), \
             patch.dict(sys.modules, {"_b_route_mvg_synthesis_recovery": previous}):
            self.assertIs(owner.validate_recovery(root, state), record)
        self.assertEqual(delegated, [old])
        self.assertNotEqual(delegated[0]["b_route_execution_transition"], state["b_route_execution_transition"])
        self.assertIn("b_route_mvg_synthesis_recovery", delegated[0])

    def test_finite_new_path_domain_does_not_mask_old_candidates_or_foreign_temps(self):
        _, state, anchor = retained_fixture()
        files, dirs, sandbox = owner._new_paths(state, anchor)
        self.assertIn(owner.RUN_REF + "/s1/attempt-1/A.json", files)
        self.assertNotIn(owner.RUN_REF + "/candidates/candidate-1/extra.json", files)
        self.assertNotIn(owner.RUN_REF + "/s1/attempt-1/unowned.tmp", files)
        self.assertNotIn(owner.RUN_REF + "/s1/unknown", dirs)

    def test_dispatch_reuse_keeps_actual_retention_close_and_only_verifies_new_thirteen(self):
        _, state, anchor = retained_fixture()
        root = Path("synthetic").resolve()
        checked = []
        fake = SimpleNamespace(verify_reserved_call=lambda run, row: checked.append(row["number"]))
        with patch.object(owner, "validate_recovery") as validation, \
             patch.object(owner.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref), \
             patch.dict(sys.modules, {"_b_route_planning_runtime": fake}):
            self.assertEqual(owner.verify_retained_dispatches(root, root / owner.RUN_REF, state)["logical_reserved_calls"], 12)
            validation.assert_called_once_with(root, state)
            self.assertEqual(checked, [])
            row = selector_row(anchor)
            row["outcome"] = {"status": "completed"}
            state["capability_selection"]["calls"].append(row)
            state["capability_selection"]["total_invocations"] = 13
            before = deepcopy(state)
            owner.verify_retained_dispatches(root, root / owner.RUN_REF, state)
            self.assertEqual(checked, [13])
            self.assertEqual(state, before)

    def test_unknown_or_failed_thirteen_never_qualifies_or_refunds(self):
        for status in (None, "failed"):
            _, state, anchor = retained_fixture()
            row = selector_row(anchor)
            if status is not None:
                row["outcome"] = {"status": status}
            state["capability_selection"]["calls"].append(row)
            state["capability_selection"]["total_invocations"] = 13
            root = Path("synthetic").resolve()
            before = deepcopy(state)
            checked = []
            def verify(run, value):
                checked.append(value["number"])
                if status is None:
                    raise ValueError("synthetic_original_unknown_verifier")
            with patch.object(owner, "validate_recovery"), \
                 patch.object(owner.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref), \
                 patch.dict(sys.modules, {"_b_route_planning_runtime": SimpleNamespace(verify_reserved_call=verify)}):
                with self.assertRaises(ValueError):
                    owner.verify_retained_dispatches(root, root / owner.RUN_REF, state)
                self.assertEqual(checked, [13])
                self.assertEqual(state, before)

    def test_retention_drift_fails_before_new_protocol_verifier(self):
        _, state, anchor = retained_fixture()
        root = Path("synthetic").resolve()
        fake = SimpleNamespace(verify_reserved_call=lambda *args: self.fail("must not reach protocol"))
        with patch.object(owner, "validate_recovery", side_effect=ValueError("synthetic_raw_source_capture_drift")), \
             patch.object(owner.sources, "checked_path", side_effect=lambda base, ref: Path(base) / ref), \
             patch.dict(sys.modules, {"_b_route_planning_runtime": fake}):
            with self.assertRaises(ValueError):
                owner.verify_retained_dispatches(root, root / owner.RUN_REF, state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
