"""Offline transport-policy tests; synthetic outputs never grant native admission."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

import jsonschema
import _b_route_codec as codec
import _b_route_planning_input as planning
import _b_route_planning_runtime as runtime
from _planning_skill_common import canonical_sha, file_sha


def carrier(draft):
    return {**{key: deepcopy(value) for key, value in draft.items() if key != "content"},
            "producer_schema_version": runtime.DRAFT_CARRIER,
            "content_json": json.dumps(draft["content"], ensure_ascii=False, allow_nan=False)}


class ProviderSchemaTests(unittest.TestCase):
    def setUp(self):
        # Path.mkdir inherits the ordinary temp ACL; no shared run or map exists.
        self.root = Path(tempfile.gettempdir()) / ("b-provider-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.frozen = {"input_identity": "sha256:" + "1" * 64,
                       "inputs": {"delivery": {"output_schema": planning.output_schema()}},
                       "transport": {"batches": [{}, {}]}}
        # Only the surrounding request constructor is a fixture. Actual schema,
        # carrier, JSON codec and ordered draft-chain validators stay real.
        def attempt(frozen, *, batch=None, drafts=(), delivery=None):
            return {"payload": json.dumps({"input": {
                "stage": "batch" if batch is not None else "synthesis",
                "ordinal": batch if batch is not None else len(drafts) + 1,
                "prior_drafts": [{"identity": codec.canonical_digest(value), "value": value} for value in drafts]}})}
        self.attempt = attempt
        seam = patch.object(runtime, "request_attempt", side_effect=attempt)
        seam.start()
        self.addCleanup(seam.stop)
        # This fixture isolates provider/canonical schema replay with bare
        # historical states. Full frozen runtime/account activation belongs to
        # the create_run entry controls, not this synthetic request seam.
        account = patch.object(runtime, "issue_account_policy", return_value=None)
        account.start()
        self.addCleanup(account.stop)

    def request(self, drafts=(), batch=None, *, policy=True):
        value = {"phase": "generation", "root_request": json.loads(self.attempt(self.frozen, batch=batch, drafts=drafts)["payload"])}
        if policy:
            value["output_schema_policy"] = runtime.PROVIDER_SCHEMA_POLICY
        return value

    def draft(self, drafts=(), batch=None):
        return {"schema_version": planning.DRAFT, "input_identity": self.frozen["input_identity"],
                "stage": "batch" if batch is not None else "synthesis", "ordinal": batch if batch is not None else len(drafts) + 1,
                "parent_draft_identities": [codec.canonical_digest(value) for value in drafts],
                "content": {"unknown": {"exact": [True, 1, "中文  \r\n", None]}, "ordinal": len(drafts) + 1}}

    def chain(self):
        first = self.draft(batch=1)
        second = self.draft([first], batch=2)
        return [first, second]

    def test_zero_one_two_parent_compilation_and_host_lossless_roundtrip(self):
        chain = self.chain()
        for parents, batch in (([], 1), (chain[:1], 2), (chain, None)):
            with self.subTest(parents=len(parents)):
                materials = self.request(parents, batch)
                canonical = runtime.generation_schema(self.frozen, materials["root_request"])
                before = deepcopy(canonical)
                producer = runtime.generation_producer_schema(self.frozen, materials)
                array = producer["properties"]["parent_draft_identities"]
                self.assertNotIn("const", array)
                self.assertEqual((array["minItems"], array["maxItems"]), (len(parents), len(parents)))
                self.assertEqual(array["items"]["type"], "string")
                if parents:
                    self.assertEqual(array["items"]["enum"], [codec.canonical_digest(value) for value in parents])
                else:
                    self.assertNotIn("enum", array["items"])
                self.assertEqual(canonical, before)
                self.assertEqual(producer, runtime.compile_provider_schema(before))
                draft = self.draft(parents, batch)
                jsonschema.Draft202012Validator(producer).validate(carrier(draft))
                self.assertTrue(runtime.same_json(runtime.decode_generation_output(self.frozen, materials, carrier(draft)), draft))
                planning.validate_draft_chain(self.frozen, [*parents, draft])

    def test_membership_length_reject_foreign_missing_extra_and_boolean(self):
        chain = self.chain()
        materials = self.request(chain)
        schema = runtime.generation_producer_schema(self.frozen, materials)
        original = carrier(self.draft(chain))
        for wrong in (["foreign", original["parent_draft_identities"][1]], [], original["parent_draft_identities"] + ["extra"], [True, False]):
            changed = {**original, "parent_draft_identities": wrong}
            self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(changed))
            with self.assertRaisesRegex(ValueError, "canonical_envelope_changed"):
                runtime.decode_generation_output(self.frozen, materials, changed)

    def test_provider_membership_does_not_replace_host_order_or_multiplicity(self):
        chain = self.chain()
        materials = self.request(chain)
        schema = runtime.generation_producer_schema(self.frozen, materials)
        draft = self.draft(chain)
        ids = draft["parent_draft_identities"]
        for wrong in (list(reversed(ids)), [ids[0], ids[0]]):
            changed = {**draft, "parent_draft_identities": wrong}
            self.assertTrue(jsonschema.Draft202012Validator(schema).is_valid(carrier(changed)))
            with self.assertRaisesRegex(ValueError, "canonical_envelope_changed"):
                runtime.decode_generation_output(self.frozen, materials, carrier(changed))
            with self.assertRaises(ValueError):
                planning.validate_draft_chain(self.frozen, [*chain, changed])

    def test_exact_host_metadata_and_no_output_repair(self):
        materials = self.request(batch=1)
        raw = carrier(self.draft(batch=1))
        before = deepcopy(raw)
        for key, wrong in (("input_identity", "foreign"), ("ordinal", True), ("ordinal", 2),
                           ("stage", "synthesis"), ("producer_schema_version", "future")):
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                runtime.decode_generation_output(self.frozen, materials, {**raw, key: wrong})
        for wrong in ('{"a":1,"a":2}', "[]", '{"a":NaN}'):
            with self.assertRaises(ValueError):
                runtime.decode_generation_output(self.frozen, materials, {**raw, "content_json": wrong})
        self.assertEqual(raw, before)

    def test_policy_is_explicit_versioned_generation_only_and_schema_rederived(self):
        materials = self.request(batch=1)
        producer = runtime.generation_producer_schema(self.frozen, materials)
        materials["actual_output_schema"] = producer
        runtime.check_generation_schema(self.frozen, materials, producer)
        for mutated in ({**materials, "output_schema_policy": None}, {**materials, "output_schema_policy": "future"},
                        {**materials, "phase": "independent_admission"}):
            with self.assertRaises(ValueError):
                runtime.check_generation_schema(self.frozen, mutated, producer)
        changed = deepcopy(producer)
        changed["properties"]["parent_draft_identities"]["maxItems"] = 10
        with self.assertRaisesRegex(ValueError, "producer_schema_changed"):
            runtime.check_generation_schema(self.frozen, {**materials, "actual_output_schema": changed}, changed)
        legacy = self.request(batch=1, policy=False)
        old_schema = runtime.generation_schema(self.frozen, legacy["root_request"])
        runtime.check_generation_schema(self.frozen, {**legacy, "actual_output_schema": old_schema}, old_schema)
        with self.assertRaises(ValueError):
            runtime.check_generation_schema(self.frozen, {**legacy, "actual_output_schema": producer}, producer)

    def test_compiler_preserves_scalar_singleton_enum_and_rejects_compound_array(self):
        schema = {"type": "array", "items": {"type": "string", "enum": ["same"]}, "const": ["same"]}
        result = runtime.compile_provider_schema(schema)
        self.assertEqual(result["items"], schema["items"])
        self.assertEqual(runtime.compile_provider_schema({"type": "string", "const": "fixed"}), {"type": "string", "const": "fixed"})
        self.assertEqual(runtime.compile_provider_schema({"type": "object", "const": {"unknown": [1, 2]}}),
                         {"type": "object", "const": {"unknown": [1, 2]}})
        with self.assertRaises(ValueError):
            runtime.compile_provider_schema({"type": "array", "const": [{"unsupported": 1}]})

    def test_invoke_explicit_future_policy_and_legacy_prompt_schema_are_bound(self):
        captured = []
        def factory(workspace):
            def invoke(prompt, number, **kwargs):
                captured.append((prompt, deepcopy(kwargs["output_schema"])))
                path = self.root / "synthetic-output.json"
                path.write_text(json.dumps(carrier(self.draft(batch=1))), encoding="utf-8")
                kwargs["before_dispatch"]({"fixture": True})
                return path, {"execution_binding": {"fixture": True}}
            return invoke
        for active in (False, True):
            materials = self.request(batch=1, policy=False)
            materials["wire_delivery"] = runtime.wire.SCHEMA
            schema = runtime.generation_schema(self.frozen, materials["root_request"], delivery=runtime.wire.SCHEMA)
            state = {"b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY} if active else {}
            calls = []
            with patch.object(runtime, "verify_call", return_value={}), patch.object(runtime, "atomic_json"):
                draft, binding = runtime.invoke_data(factory, self.frozen, self.root, 1, materials, schema, "generate",
                                                     lambda *args: calls.append(args), state=state)
            self.assertEqual(len(calls), 1)
            self.assertEqual(materials.get("output_schema_policy"), runtime.PROVIDER_SCHEMA_POLICY if active else None)
            self.assertEqual(captured[-1][1], runtime.compile_provider_schema(schema) if active else schema)
            self.assertEqual(materials["materials_identity"], canonical_sha({k: v for k, v in materials.items() if k != "materials_identity"}))
            self.assertEqual(captured[-1][0], runtime.materials_prompt(materials))
            self.assertTrue(runtime.same_json(draft, self.draft(batch=1)))

    def test_invoke_rejects_unknown_unactivated_prepopulated_or_changed_schema_before_dispatch(self):
        materials = self.request(batch=1, policy=False)
        schema = runtime.generation_schema(self.frozen, materials["root_request"])
        factory = unittest.mock.Mock(side_effect=AssertionError("must not dispatch"))
        cases = ((materials, schema, {"b_route_output_schema_policy": "future"}),
                 (self.request(batch=1), schema, {}),
                 (self.request(batch=1), schema, {"b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY}),
                 ({**self.request(batch=1), "phase": "independent_admission"}, schema,
                  {"b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY}),
                 (materials, {}, {"b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY}))
        for payload, supplied, state in cases:
            with self.assertRaises(ValueError):
                runtime.invoke_data(factory, self.frozen, self.root, 1, deepcopy(payload), supplied, "generate", lambda *_: None, state=state)
        factory.assert_not_called()

    def binding_materials(self, *, policy=False):
        materials = self.request(batch=1, policy=policy)
        materials.update(root_input_identity=self.frozen["input_identity"], runtime_identity="original-runtime", run_id="fixture")
        materials["actual_output_schema"] = runtime.generation_producer_schema(self.frozen, materials)
        materials["materials_identity"] = canonical_sha(materials)
        prompt, schema = self.root / "prompt.txt", self.root / "schema.json"
        prompt.write_text(runtime.materials_prompt(materials), encoding="utf-8")
        schema.write_text(json.dumps(materials["actual_output_schema"]), encoding="utf-8")
        return {"prompt_path": str(prompt), "schema_path": str(schema)}, materials

    def test_bound_materials_policy_cannot_be_stripped_or_added(self):
        state = {"runtime_identity": "original-runtime", "run_id": "fixture"}
        with patch.object(runtime, "wire_delivery", return_value=None):
            for policy in (False, True):
                binding, materials = self.binding_materials(policy=policy)
                matching = {**state, **({"b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY} if policy else {})}
                self.assertEqual(runtime.bound_materials(binding, matching, self.frozen), materials)
                opposite = state if policy else {**state, "b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY}
                with self.assertRaisesRegex(ValueError, "policy_changed"):
                    runtime.bound_materials(binding, opposite, self.frozen)

    def test_bound_materials_routes_original_epoch_before_identity_and_policy_checks(self):
        import _b_route_execution_transition as transition
        binding, materials = self.binding_materials()
        original = {"runtime_identity": "original-runtime", "run_id": "fixture"}
        active = {"runtime_identity": "new-runtime", "run_id": "fixture",
                  "b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY,
                  "b_route_execution_history": {"original": {}},
                  "b_route_execution_transition": {"artifact_root": str(self.root)}}
        with patch.object(runtime, "wire_delivery", return_value=None), \
                patch.object(transition, "source_state_for_materials", return_value=original) as route:
            self.assertEqual(runtime.bound_materials(binding, active, self.frozen), materials)
            route.assert_called_once_with(self.root, active, materials, binding)
        with patch.object(runtime, "wire_delivery", return_value=None), \
                patch.object(transition, "source_state_for_materials", side_effect=ValueError("unpinned original")):
            with self.assertRaisesRegex(ValueError, "unpinned original"):
                runtime.bound_materials(binding, active, self.frozen)

    def test_proof_routes_original_epoch_before_loading_frozen_or_rebuilding_proof(self):
        import _b_route_execution_transition as transition
        original, active, proof = {"original": True}, {"b_route_execution_history": {"original": {}}}, {"original-proof": True}
        with patch.object(transition, "source_state_for_proof", return_value=original) as route, \
                patch.object(runtime, "frozen_input", side_effect=ValueError("stop after source resolution")) as frozen:
            errors = runtime.proof_errors(self.root, active, {}, proof)
            self.assertIn("stop after source resolution", errors[0])
            route.assert_called_once_with(self.root, active, proof)
            frozen.assert_called_once_with(self.root, original)
        with patch.object(transition, "source_state_for_proof", side_effect=ValueError("unpinned proof")), \
                patch.object(runtime, "frozen_input") as frozen:
            self.assertIn("unpinned proof", runtime.proof_errors(self.root, active, {}, proof)[0])
            frozen.assert_not_called()

    def test_authenticated_no_digest_legacy_retains_absent_policy_in_new_epoch(self):
        import _b_route_execution_transition as transition
        import _b_route_review_recovery as recovery
        binding, materials = self.binding_materials()
        state = {"runtime_identity": "original-runtime", "run_id": "fixture",
                 "b_route_output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY,
                 "b_route_execution_history": {"original": {}},
                 "b_route_execution_transition": {"artifact_root": str(self.root)}}
        # Only recovery's exact historical-binding authentication is a seam;
        # absence of a source digest alone must never grant this exception.
        with patch.object(runtime, "wire_delivery", return_value=None), \
                patch.object(transition, "source_state_for_materials", return_value=state), \
                patch.object(recovery, "validate_materials_transition") as authenticate:
            self.assertEqual(runtime.bound_materials(binding, state, self.frozen), materials)
            authenticate.assert_called_once_with(state, materials, binding, allow_failed_review=False)
        with patch.object(runtime, "wire_delivery", return_value=None), \
                patch.object(transition, "source_state_for_materials", return_value=state), \
                patch.object(recovery, "validate_materials_transition", side_effect=ValueError("unbound legacy")):
            with self.assertRaisesRegex(ValueError, "unbound legacy"):
                runtime.bound_materials(binding, state, self.frozen)

    def failed_row(self):
        workspace = self.root / "sandbox"
        workspace.mkdir(exist_ok=True)
        (workspace / "prompt.txt").write_text("original prompt", encoding="utf-8")
        request = {"workspace": "sandbox", "output_path": "sandbox/absent.json", "prompt_path": "sandbox/prompt.txt",
                   "schema_path": "sandbox/schema.json", "execution_binding_path": "binding.json",
                   "input_files": {"prompt.txt": file_sha(workspace / "prompt.txt")}}
        request["request_sha256"] = canonical_sha(request)
        return {"number": 6, "request_identity": request, "outcome": {"status": "failed", "error_type": "RuntimeError", "error_class": "native"}}

    def test_effectful_dispatch_rejects_historical_source_before_frozen_or_runner(self):
        import _mvg_capability_generation as generation
        import openai_isolated_model_runner as runner
        arguments = (self.root, self.root, None, self.root / "never-run.py", self.root,
                     self.root / "prompt.txt", self.root / "schema.json", self.root / "output.json", 1,
                     self.root / "binding.json")
        historical = {"b_route_execution_transition": {"current_source_root": str(self.root / "historical-source")}}
        actual = {"b_route_execution_transition": {"current_source_root": str(Path(runtime.__file__).resolve().parents[2])}}
        with patch.object(runtime, "frozen_input", side_effect=RuntimeError("next frozen boundary")) as frozen, \
                patch.object(runtime, "require_live_high") as live_high, \
                patch.object(runner, "workspace_payload", side_effect=AssertionError("runner must not be reached")) as payload, \
                patch.object(generation, "dispatch_request_identity", side_effect=AssertionError("reservation must not be reached")) as reserve:
            with self.assertRaisesRegex(ValueError, "^b_route_dispatch_source_root_mismatch$"):
                runtime.prepare_dispatch(*(*arguments[:2], historical, *arguments[3:]), timeout_sec=1)
            frozen.assert_not_called()
            live_high.assert_not_called()
            for state in (actual, {}):
                with self.subTest(transition=bool(state)), self.assertRaisesRegex(RuntimeError, "^next frozen boundary$"):
                    runtime.prepare_dispatch(*(*arguments[:2], state, *arguments[3:]), timeout_sec=1)
                frozen.assert_called_with(self.root, state)
            self.assertEqual(frozen.call_count, 2)
            self.assertEqual(live_high.call_count, 2)
            payload.assert_not_called()
            reserve.assert_not_called()

    def test_failed_receipt_without_output_remains_charged_and_never_binding(self):
        row = self.failed_row()
        original = deepcopy(row)
        with patch.object(runtime, "verify_call", side_effect=AssertionError("failed is never proof")):
            self.assertIsNone(runtime.verify_reserved_call(self.root, row))
        self.assertEqual(row, original)
        self.assertFalse((self.root / "sandbox/absent.json").exists())

    def test_failed_receipt_request_input_outcome_sidecar_and_unsafe_paths_fail_closed(self):
        row = self.failed_row()
        changed = deepcopy(row)
        changed["request_identity"]["output_path"] = "altered.json"
        with self.assertRaisesRegex(ValueError, "request_changed"):
            runtime.verify_reserved_call(self.root, changed)
        for field in ("workspace", "output_path", "prompt_path", "schema_path", "execution_binding_path"):
            changed = deepcopy(row)
            changed["request_identity"][field] = "../outside.json"
            changed["request_identity"]["request_sha256"] = canonical_sha({k: v for k, v in changed["request_identity"].items() if k != "request_sha256"})
            with self.subTest(field=field), self.assertRaises(ValueError):
                runtime.verify_reserved_call(self.root, changed)
        for outcome in (None, {"status": "unknown"}, {"status": "failed", "error_type": "RuntimeError"}):
            changed = {**row, "outcome": outcome}
            with self.assertRaises(ValueError):
                runtime.verify_reserved_call(self.root, changed)
        sidecars = self.root / "dispatch-receipts"
        sidecars.mkdir()
        (sidecars / "dispatch-6.json").write_text('{"forged":true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outcome_changed"):
            runtime.verify_reserved_call(self.root, row)
        (sidecars / "dispatch-6.json").unlink()
        (self.root / "sandbox/prompt.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs_changed"):
            runtime.verify_reserved_call(self.root, row)


if __name__ == "__main__":
    unittest.main()
