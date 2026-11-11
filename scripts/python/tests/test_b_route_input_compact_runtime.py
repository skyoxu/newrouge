"""Offline orchestration seams; no fixture is native admission evidence."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import uuid

import _b_route_compact_literal as compact
import _b_route_planning_runtime as runtime
import _b_route_planning_wire as wire
from _planning_skill_common import canonical_sha


class InputCompactRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / ("b-input-policy-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def payload(self, phase="generation"):
        return {"phase": phase, "wire_delivery": wire.CURRENT_SCHEMA,
                "root_request": {"exact": [True, 1, "中文  \r\n", None]},
                "unknown": [{"r": "literal", "@": ["data"]}]}

    def test_future_generation_and_review_are_explicit_and_lossless(self):
        state = {"b_route_input_compact_policy": compact.CURRENT_SCHEMA}
        for phase in ("generation", "independent_admission"):
            payload = self.payload(phase)
            original = deepcopy(payload)
            captured = []
            def factory(workspace):
                def invoke(prompt, number, **kwargs):
                    captured.append(prompt)
                    raise RuntimeError("stop before any native dispatch")
                return invoke
            with self.subTest(phase=phase), self.assertRaisesRegex(RuntimeError, "stop before any native dispatch"):
                runtime.invoke_data(factory, {}, self.root, 5, payload, {}, "repair", lambda *_: None, state=state)
            self.assertEqual(payload["input_compact_policy"], compact.CURRENT_SCHEMA)
            self.assertEqual(ast.literal_eval(captured[0].split("\n", 1)[1])["schema_version"], compact.CURRENT_SCHEMA)
            self.assertEqual(wire.read_prompt(captured[0], wire.CURRENT_SCHEMA), payload)
            self.assertEqual(payload["root_request"], original["root_request"])
            self.assertEqual(payload["unknown"], original["unknown"])
            self.assertEqual(payload["materials_identity"], canonical_sha({k: v for k, v in payload.items() if k != "materials_identity"}))

    def test_absent_policy_preserves_default_v1_packet_and_prompt_bytes(self):
        payload = self.payload()
        with patch.object(wire, "render", wraps=wire.render) as render:
            first = runtime.materials_prompt(payload)
            instruction, materials, delivery = render.call_args.args
        self.assertEqual(first, wire.render(instruction, materials, delivery))
        self.assertEqual(ast.literal_eval(first.split("\n", 1)[1])["schema_version"], compact.SCHEMA)
        self.assertEqual(wire.read_prompt(first, wire.CURRENT_SCHEMA), payload)
        self.assertNotIn("input_compact_policy", payload)

    def test_unknown_prepopulated_or_mixed_delivery_policy_stops_before_invoke(self):
        factory = Mock(side_effect=AssertionError("must not invoke"))
        for value in (None, False, compact.SCHEMA, "future"):
            with self.subTest(policy=value), self.assertRaises(ValueError):
                runtime.invoke_data(factory, {}, self.root, 5, self.payload(), {}, "repair", lambda *_: None,
                                    state={"b_route_input_compact_policy": value})
        for delivery in (None, wire.SCHEMA):
            payload = {**self.payload(), "wire_delivery": delivery}
            with self.subTest(delivery=delivery), self.assertRaises(ValueError):
                runtime.invoke_data(factory, {}, self.root, 5, payload, {}, "repair", lambda *_: None,
                                    state={"b_route_input_compact_policy": compact.CURRENT_SCHEMA})
        with self.assertRaisesRegex(ValueError, "prepopulated"):
            runtime.invoke_data(factory, {}, self.root, 5, {**self.payload(), "input_compact_policy": compact.CURRENT_SCHEMA},
                                {}, "repair", lambda *_: None, state={})
        factory.assert_not_called()

    def bound_fixture(self, policy=None, transition=None):
        materials = {"schema_version": runtime.PROFILE, "phase": "generation", "root_request": {"input": {}},
            "root_input_identity": "input", "accepted_seed": {}, "proposal": None, "prior_candidate": None,
            "repair_issue": None, "lineage_context": 1, "wire_delivery": wire.CURRENT_SCHEMA,
            "runtime_identity": "runtime", "run_id": "fixture", "slot": "candidate-2", "generation": 1,
            "execution": 1, "lineage_identity": "lineage", "actual_output_schema": {},
            "content_contract": {}, "final_content_target": {}}
        if policy is not None:
            materials["input_compact_policy"] = policy
        if transition is not None:
            materials["execution_source_transition"] = transition
        materials["materials_identity"] = canonical_sha(materials)
        prompt_path, schema_path = self.root / "prompt.txt", self.root / "schema.json"
        prompt_path.write_text(runtime.materials_prompt(materials), encoding="utf-8")
        schema_path.write_text("{}", encoding="utf-8")
        return {"prompt_path": str(prompt_path), "schema_path": str(schema_path)}, materials

    def bound_seams(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(runtime, "wire_delivery", return_value=wire.CURRENT_SCHEMA))
        stack.enter_context(patch.object(runtime, "generation_schemas", return_value={}))
        stack.enter_context(patch.object(runtime, "generation_target", return_value={}))
        stack.enter_context(patch.object(runtime, "check_generation_schema"))
        stack.enter_context(patch.object(runtime, "check_review_producer_schema"))
        return stack

    def test_bound_policy_and_actual_packet_must_both_match(self):
        state = {"runtime_identity": "runtime", "run_id": "fixture", "b_route_input_compact_policy": compact.CURRENT_SCHEMA}
        with self.bound_seams():
            binding, materials = self.bound_fixture(compact.CURRENT_SCHEMA)
            self.assertEqual(runtime.bound_materials(binding, state, {"input_identity": "input"}), materials)
            prompt = Path(binding["prompt_path"])
            prefix = prompt.read_text(encoding="utf-8").split("\n", 1)[0]
            prompt.write_text(prefix + "\n" + compact.dumps(wire.encode(materials, wire.CURRENT_SCHEMA)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "wire_or_generation_target_changed"):
                runtime.bound_materials(binding, state, {"input_identity": "input"})
            binding, _ = self.bound_fixture()
            with self.assertRaisesRegex(ValueError, "input_compact_policy_changed"):
                runtime.bound_materials(binding, state, {"input_identity": "input"})
            binding, _ = self.bound_fixture(compact.CURRENT_SCHEMA)
            with self.assertRaisesRegex(ValueError, "input_compact_policy_changed"):
                runtime.bound_materials(binding, {"runtime_identity": "runtime", "run_id": "fixture"}, {"input_identity": "input"})

    def test_historical_r8_materials_use_original_policy_after_source_resolution(self):
        import _b_route_execution_transition as transition
        original = {"runtime_identity": "runtime", "run_id": "fixture",
                    "b_route_execution_transition": {"transition_digest": "r8"}}
        active = {**original, "b_route_execution_history": {"r8": {}},
                  "b_route_execution_transition": {"transition_digest": "r9", "artifact_root": str(self.root)},
                  "b_route_input_compact_policy": compact.CURRENT_SCHEMA}
        with self.bound_seams():
            binding, materials = self.bound_fixture(transition="r8")
            with patch.object(transition, "source_state_for_materials", return_value=original) as resolve:
                self.assertEqual(runtime.bound_materials(binding, active, {"input_identity": "input"}), materials)
                resolve.assert_called_once_with(self.root, active, materials, binding)
            with patch.object(transition, "source_state_for_materials", side_effect=ValueError("unbound r8 proof")):
                with self.assertRaisesRegex(ValueError, "unbound r8 proof"):
                    runtime.bound_materials(binding, active, {"input_identity": "input"})

    def test_selector_policy_activation_lossless_prompt_and_invalid_policy(self):
        from _mvg_evidence_transport import lossless_context
        frozen, scope, base, proposals = {"input": "complete"}, {"capability_id": "scope"}, {}, {"candidate-1": {"unknown": [True, 1]}}
        aliases = {"A": "candidate-1"}
        comparison = {"A": {"frozen_input": frozen, "scope": scope, "accepted_seed": base, "proposal": proposals["candidate-1"]}}
        for name, value in {"A.json": proposals["candidate-1"], "accepted-seed.json": base,
                            "comparison-context.json": lossless_context(comparison)}.items():
            (self.root / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        public = {"candidates": {"A": {}}}
        with patch.object(runtime, "check_selector_aliases"), patch.object(runtime, "wire_delivery", return_value=wire.CURRENT_SCHEMA):
            for active in (False, True):
                state = {"runtime_identity": "runtime", "run_id": "fixture"}
                if active:
                    state["b_route_input_compact_policy"] = compact.CURRENT_SCHEMA
                materials = runtime.selector_materials(state, frozen, scope, public, base, proposals, aliases, self.root)
                prompt = runtime.selector_prompt(materials)
                self.assertEqual(wire.read_prompt(prompt, wire.CURRENT_SCHEMA), materials)
                self.assertEqual(ast.literal_eval(prompt.split("\n", 1)[1])["schema_version"], compact.CURRENT_SCHEMA if active else compact.SCHEMA)
            with self.assertRaises(ValueError):
                runtime.selector_materials({"runtime_identity": "runtime", "run_id": "fixture", "b_route_input_compact_policy": "future"},
                                           frozen, scope, public, base, proposals, aliases, self.root)

    def partial_module(self):
        module = types.ModuleType("_b_route_partial_generation_recovery")
        module.validate_recovery = Mock(return_value={})
        module.resume_generation = Mock()
        module.resume_propose_attempt = Mock(return_value=True)
        module.call_root = Mock(side_effect=lambda state, workspace, number, slot:
            workspace / "capability-append" / ("input-budget-recovery-1" if state.get("b_route_partial_generation_recovery") and slot == "candidate-2" and number >= 5 else "") / f"c{number}")
        return module

    def test_partial_propose_keeps_paid_batch_and_uses_new_root_and_once_hook(self):
        import _mvg_capability_append as append
        import _b_route_synthesis_recovery as old_recovery
        module = self.partial_module()
        draft8 = {"content": {"paid": 8}, "ordinal": 1}
        draft9 = {"content": {"future": 9}, "ordinal": 2}
        binding8, binding9 = {"original-binding": 8}, {"future-binding": 9}
        module.resume_generation.return_value = ([draft8], [binding8])
        state = {"runtime_identity": "runtime", "run_id": "fixture", "runtime_slot": "candidate-2",
                 "b_route_partial_generation_recovery": {"typed": True}, "b_route_synthesis_recovery": {"old": True}}
        frozen, accepted, prior, issue = {"transport": {"batches": [{}]}, "input_identity": "input"}, {"seed": True}, {"proposal": 7}, {"issue": "handoff"}
        result = {}
        def run(directory, **kwargs):
            current, ledger = {"issue_attempts": {"handoff": 1}}, {"total_invocations": 4}
            self.assertTrue(kwargs["resume_propose_attempt"](current, ledger))
            result["delta"] = kwargs["propose"]({}, accepted, prior, issue, 1, lambda *_: None)
            return {"status": "blocked"}
        def request(_frozen, **kwargs):
            self.assertEqual(kwargs["drafts"], [draft8])
            self.assertIsNone(kwargs["batch"])
            return {"phase": "generation", "root_request": {}, "lineage_context": 1, "repair_issue": issue}
        with patch.dict(sys.modules, {module.__name__: module}), \
                patch.object(append, "run_capability_append", side_effect=run), \
                patch.object(runtime, "frozen_input", return_value=frozen), \
                patch.object(runtime, "scopes", return_value=[{}]), \
                patch.object(runtime, "load_json", return_value={"total_invocations": 4}), \
                patch.object(runtime, "validate_input"), patch.object(runtime, "wire_delivery", return_value=None), \
                patch.object(runtime, "request_payload", side_effect=request), \
                patch.object(runtime, "generation_schemas", return_value={}), \
                patch.object(runtime, "generation_schema", return_value={}), \
                patch.object(runtime.planning, "validate_draft_chain") as validate, \
                patch.object(runtime, "invoke_data", return_value=(draft9, binding9)) as invoke, \
                patch.object(old_recovery, "resume_generation", side_effect=AssertionError("must not reuse old resume")):
            runtime.generate_append(self.root, state, self.root, invoke_factory=Mock(), before_call=Mock(), checkpoint=Mock(), accepted_seed=accepted)
            self.assertEqual(invoke.call_args.args[2:4], (self.root / "capability-append/input-budget-recovery-1/c5", 5))
            self.assertEqual(invoke.call_args.args[6], "repair")
            module.resume_generation.assert_called_once_with(self.root, state, self.root, frozen, accepted, prior, issue, 1)
            module.resume_propose_attempt.assert_called_once()
            validate.assert_called_once_with(frozen, [draft8, draft9])
        self.assertEqual(result["delta"]["generation_calls"], [binding8, binding9])
        self.assertEqual(result["delta"]["candidate"]["provenance"]["draft_chain"], [draft8, draft9])
        self.assertIs(result["delta"]["generation_calls"][0], binding8)

    def test_partial_validation_owns_archived_synthesis_validation_without_recursion(self):
        import _b_route_synthesis_recovery as old_recovery
        module = self.partial_module()
        frozen = {"input_identity": "input"}
        desc = {"prepared_ref": "fixture", "frozen_sha256": canonical_sha(frozen), "input_identity": "input", "rules": {}}
        state = {"b_route_partial_generation_recovery": {"typed": True}, "b_route_synthesis_recovery": {"old": True}}
        with patch.dict(sys.modules, {module.__name__: module}), \
                patch.object(runtime, "descriptor", return_value=desc), \
                patch.object(runtime.planning, "load_prepared", return_value=frozen), \
                patch.object(runtime, "rules_identity", return_value={}), \
                patch.object(old_recovery, "validate_recovery", side_effect=AssertionError("new state must not re-sign old synthesis")):
            self.assertIs(runtime.frozen_input(self.root, state), frozen)
            module.validate_recovery.assert_called_once_with(self.root, state)
            module.validate_recovery.side_effect = ValueError("partial proof changed")
            with self.assertRaisesRegex(ValueError, "partial proof changed"):
                runtime.frozen_input(self.root, state)

    def verification_seams(self, *, failure=None):
        from contextlib import ExitStack
        import _b_route_execution_transition as transition
        import _b_route_review_recovery as review_recovery
        stack = ExitStack()
        module = self.partial_module()
        frozen = {"input_identity": "input", "all_originals": [True, 1, "unchanged"]}
        raw = json.dumps(frozen).encode("utf-8")
        prepared = self.root / "verification-workspace"
        prepared.mkdir(exist_ok=True)
        prepared_file = prepared / "b-route-prepared.json"
        prepared_file.write_bytes(raw)
        desc = {"prepared_ref": "fixture", "frozen_sha256": canonical_sha(frozen), "input_identity": "input", "rules": {}}
        state = {"b_route_execution_transition": {"typed": True}, "b_route_review_recovery": {"typed": True},
                 "b_route_partial_generation_recovery": {"typed": True}}
        frames, events = [], []
        expected = {"fresh_native_witness": "same"}
        def nested(label):
            with transition._verification_transaction() as context:
                frames.append(context)
                events.append(label)
                if context["request"] is None:
                    context.update(request=(self.root, self.root, {"fixture": True}), expected=expected,
                                   prepared=(prepared_file, raw), key="same-bound-fixture")
                transition._remember_source(context, self.root, "fixture-commit", {"sources": "same"})
            return frozen
        def native(*_args):
            self.assertEqual(events[-1], "workspace-bound")
            events.append("fresh-native-closure")
            if failure == "native":
                raise ValueError("fresh currentness failed")
            return expected
        strict_loads = runtime.codec.strict_json_loads
        def parse(value):
            self.assertIsNotNone(transition._ACTIVE_VERIFICATION.get())
            self.assertEqual(value, raw)
            events.append("workspace-bound")
            return strict_loads(value)
        stack.enter_context(patch.dict(sys.modules, {module.__name__: module}))
        stack.enter_context(patch.object(runtime, "descriptor", return_value=desc))
        stack.enter_context(patch.object(transition, "load_prepared", side_effect=lambda *_: nested("prepared")))
        stack.enter_context(patch.object(review_recovery, "validate_recovery", side_effect=lambda *_: nested("review-history")))
        module.validate_recovery.side_effect = lambda *_: nested("partial-history")
        witness = stack.enter_context(patch.object(transition, "_run_original", side_effect=native))
        manifests = stack.enter_context(patch.object(transition, "_source_manifest", return_value={"sources": "changed" if failure == "source" else "same"}))
        stack.enter_context(patch.object(runtime.codec, "strict_json_loads", side_effect=parse))
        return stack, state, prepared, frozen, frames, events, witness, manifests

    def test_complete_frozen_transaction_shares_nested_witness_and_closes_before_return(self):
        import _b_route_execution_transition as transition
        stack, state, prepared, frozen, frames, events, witness, manifests = self.verification_seams()
        with stack:
            for invocation in range(2):
                self.assertEqual(runtime.frozen_input(self.root, state, prepared=prepared), frozen)
                self.assertIsNone(transition._ACTIVE_VERIFICATION.get())
                events.append("caller-resumed")
                self.assertEqual(witness.call_count, invocation + 1)
                self.assertEqual(manifests.call_count, invocation + 1)
            self.assertEqual(events, ["prepared", "review-history", "partial-history", "workspace-bound", "fresh-native-closure", "caller-resumed"] * 2)
            self.assertEqual(len(frames), 6)
            self.assertTrue(all(frame is frames[0] for frame in frames[:3]))
            self.assertTrue(all(frame is frames[3] for frame in frames[3:]))
            self.assertIsNot(frames[0], frames[3], "Independent calls require fresh verification transactions")

    def test_frozen_transaction_closure_failure_prevents_return_and_clears_context(self):
        import _b_route_execution_transition as transition
        for failure, reason in (("native", "fresh currentness failed"), ("source", "source_changed_during_transaction")):
            stack, state, prepared, _, _, _, witness, _ = self.verification_seams(failure=failure)
            caller = Mock(side_effect=AssertionError("caller must not receive unverified input"))
            with stack, self.subTest(failure=failure):
                with self.assertRaisesRegex(ValueError, reason):
                    value = runtime.frozen_input(self.root, state, prepared=prepared)
                    caller(value)
                caller.assert_not_called()
                witness.assert_called_once()
                self.assertIsNone(transition._ACTIVE_VERIFICATION.get())

    def test_proof_layout_uses_each_binding_source_before_root_choice(self):
        import _b_route_execution_transition as transition
        import _mvg_capability_selection as selection
        module = self.partial_module()
        active = {"run_id": "fixture", "runtime_identity": "runtime", "b_route_execution_history": {"r8": {}},
                  "b_route_partial_generation_recovery": {"typed": True}}
        original = {"run_id": "fixture", "runtime_identity": "runtime"}
        workspace = self.root / "candidates/candidate-2/scope-1"
        line = {"slot": "candidate-2", "generation": 1, "execution": 1, "identity": "lineage", "context": 1}
        bindings, rows, local_calls = [], [], []
        for number, source in ((4, original), (5, active)):
            call_root = module.call_root(source, workspace, number, "candidate-2")
            sandbox = call_root / "llm-sandbox" / f"attempt-{number}" / "r"
            sandbox.mkdir(parents=True)
            materials = {"phase": "generation" if number == 4 else "independent_admission", "wire_delivery": wire.CURRENT_SCHEMA,
                         "repair_issue": {"issue": "handoff"}, "lineage_identity": "lineage", "lineage_context": 1,
                         "slot": "candidate-2", "generation": 1, "execution": 1}
            prompt = sandbox / f"prompt-{number}-r.txt"
            prompt.write_text(wire.render("Synthetic proof fixture", materials, wire.CURRENT_SCHEMA), encoding="utf-8")
            binding = {"output_path": str(sandbox / "r.json"), "prompt_path": str(prompt), "schema_path": str(sandbox / "output-schema.json")}
            row = {"reservation_id": str(number), "request_identity": {"attempt": number,
                   "output_path": (sandbox / "r.json").relative_to(self.root).as_posix(), "fresh_lineage_identity": "lineage",
                   "execution_binding_path": (call_root / f"execution-binding-{number}-r.json").relative_to(self.root).as_posix()}}
            bindings.append(binding)
            rows.append(row)
            local_calls.append({"number": number, "reservation_id": str(number), "context": 1, "phase": "repair" if number == 4 else "semantic"})
        module.call_root.reset_mock()
        active["capability_selection"] = {"calls": rows}
        proof = {"seed": {}, "records": [{"context": 1, "scope": {"capability_id": "scope"},
                  "delta": {"lineage": line, "generation_calls": bindings[:1]}, "execution": bindings[1]}]}
        with patch.dict(sys.modules, {module.__name__: module}), \
                patch.object(runtime, "descriptor", return_value={"planner": "capabilities"}), \
                patch.object(runtime, "run_location", return_value=self.root), \
                patch.object(runtime, "labels", return_value=("candidate-1", "candidate-2")), \
                patch.object(runtime, "lineage_identity", return_value="lineage"), \
                patch.object(selection, "scope_workspace", return_value=workspace), \
                patch.object(runtime, "load_json", return_value={"calls": local_calls}), \
                patch.object(runtime, "wire_delivery", return_value=wire.CURRENT_SCHEMA), \
                patch.object(transition, "source_state_for_materials", side_effect=[original, active]) as resolve, \
                patch.object(runtime, "verify_bound_reservation", side_effect=rows) as verify:
            runtime.verify_proof_reservations(self.root, active, proof)
            self.assertEqual(resolve.call_count, 2)
            module.call_root.assert_called_once_with(active, workspace, 5, "candidate-2")
            for call, binding in zip(verify.call_args_list, bindings):
                self.assertEqual(call.kwargs["expected_workspace"], Path(binding["output_path"]).parent)
                self.assertEqual(call.kwargs["expected_output"], Path(binding["output_path"]))


if __name__ == "__main__":
    unittest.main()
