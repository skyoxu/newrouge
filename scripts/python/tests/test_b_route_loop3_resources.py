"""Focused loop-three resource controls; no model or qualification claims."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_planning_input as planning
import _b_route_planning_wire as wire
import _mvg_lossless_context as legacy

compact = wire.compact


class LegacyEntryResourceTests(unittest.TestCase):
    def request_data(self):
        context = {"delivery": {"core_encoding": wire.MODEL_ENCODING,
            "prompt": "Original complete source", "output_schema": {"type": "object"}},
            "input_identity": "sha256:fixture", "global_proof": {"extractions": [
                {"original": "Complete source\r\n\u4e2d\u6587", "types": [False, 0, 0.0, None]}]}}
        plan = {"core": {"$mvg_ref": "literal data", "original": [False, 0,
            {"unknown": "Whole prior draft\r\n" * 3}]}, "inventory": [],
            "context_sha256": "sha256:original", "batches": []}
        return context, plan

    def test_core_factor_is_bounded_before_legacy_serialization(self):
        context, plan = self.request_data()
        plan["core"] = {"leaf": "x" * 128}
        with patch.object(compact, "MAX_EXPANDED_BYTES", 64), \
             patch.object(wire, "lossless_context", side_effect=AssertionError("legacy allocation reached")):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                planning.serialize_request(context, plan, [], stage="batch", ordinal=1, drafts=[])

    def test_legacy_core_request_bytes_types_and_namespace_are_unchanged(self):
        context, plan = self.request_data()
        draft = {"unknown": {"$mvg_source": "literal", "order": [False, 0, "\u4e2d"]}}
        expected_input = {"schema_version": planning.REQUEST, "input_stage": "3b", "stage": "synthesis",
            "ordinal": 2, "input_identity": context["input_identity"], "core": legacy.lossless_context(plan["core"]),
            "inventory": plan["inventory"], "transport_context_identity": plan["context_sha256"], "parts": [],
            "cross_batch_obligations": context["global_proof"]["extractions"],
            "prior_drafts": [{"identity": planning.codec.canonical_digest(draft), "value": draft}],
            "delivery": "All original characters and proof bytes are reconstructed in the complete ordered batch sequence; "
                "Internal archive:base64 entries decode to the exact historical bytes. Global semantic proof recurs in full.",
            "core_encoding": wire.MODEL_ENCODING}
        expected_prompt = context["delivery"]["prompt"] + (
            " Input.core is a self-contained lossless envelope. Resolve its shared definitions only within that core; "
            "all restored fields and original values apply in full. " + planning.ENCODING_INSTRUCTION)
        expected = json.dumps({"prompt": expected_prompt, "input": expected_input,
            "output_schema": context["delivery"]["output_schema"]}, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False)
        self.assertEqual(planning.serialize_request(context, plan, [], stage="synthesis", ordinal=2,
            drafts=[draft]), expected)

    def test_plain_request_keeps_original_core_without_factoring(self):
        context, plan = self.request_data()
        del context["delivery"]["core_encoding"]
        with patch.object(wire, "lossless_context", side_effect=AssertionError("unexpected factor")):
            raw = planning.serialize_request(context, plan, [], stage="batch", ordinal=1, drafts=[])
        result = json.loads(raw)
        self.assertEqual(wire.text(result["input"]["core"]), wire.text(plan["core"]))
        self.assertNotIn("core_encoding", result["input"])
        self.assertEqual(result["prompt"], context["delivery"]["prompt"])

    def test_factor_rejects_a_spent_caller_account_before_legacy_owner(self):
        work = compact._EncodingWork()
        work.spend(work.remaining)
        with patch.object(wire, "lossless_context", side_effect=AssertionError("legacy allocation reached")):
            with self.assertRaisesRegex(ValueError, "encoding work exceeds"):
                wire.factor_lossless_context({"complete": [False, 0, "source"]}, work=work)

    def test_frozen_resource_failure_precedes_identity_and_reconstruction(self):
        frozen = {"schema_version": planning.PREPARED, "input_stage": "3b", "leaf": "x" * 128}
        with patch.object(compact, "MAX_EXPANDED_BYTES", 64), \
             patch.object(planning.codec, "canonical_digest", side_effect=AssertionError("identity allocation reached")), \
             patch.object(planning, "reconstruction", side_effect=AssertionError("reconstruction reached")):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                planning.validate_frozen(frozen)

    def test_frozen_remeasurement_resource_failure_precedes_context_copy(self):
        frozen = {"inputs": {"leaf": "x" * 128}, "transport": {"batches": []}}
        with patch.object(compact, "MAX_EXPANDED_BYTES", 64), \
             patch.object(planning, "context_for", side_effect=AssertionError("context allocation reached")):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                planning._verify_current_capacity(frozen)

    def test_wire_successor_propagates_one_account_through_validation_and_core(self):
        # This is a pure propagation seam, not a passed frozen/native request.
        context, plan = self.request_data()
        frozen = {"inputs": {"delivery": context["delivery"]}, "transport": plan,
            "input_identity": context["input_identity"], "resume_ref": "fixture/prepared.json"}
        work, accounts = compact._EncodingWork(), []
        factor = wire.factor_lossless_context
        def record_factor(value, *, work=None):
            accounts.append(work)
            return factor(value, work=work)
        with patch.object(planning, "validate_frozen", side_effect=lambda value, **kw: accounts.append(kw["work"])), \
             patch.object(planning, "_verify_current_capacity", side_effect=lambda value, **kw: accounts.append(kw["work"])), \
             patch.object(planning, "context_for", return_value=context), \
             patch.object(planning, "validate_draft_chain", return_value=[]), \
             patch.object(wire, "factor_lossless_context", side_effect=record_factor):
            request = planning.build_wire_request(frozen, wire_delivery=wire.CURRENT_SCHEMA, work=work)
        self.assertEqual(len(accounts), 3)
        self.assertTrue(all(current is work for current in accounts))
        remaining = work.remaining
        self.assertLess(remaining, work.limit)
        wire.render("Final wrapper", {"root_request": json.loads(request["payload"])},
            wire.CURRENT_SCHEMA, work=work)
        self.assertLess(work.remaining, remaining)

    def test_host_artifact_bytes_are_exact_and_serialize_only_after_reservation(self):
        value = {"source": "\u4e2d\u6587\r\n", "types": [False, 0, 0.0, None], "$mvg_ref": {"unknown": 1}}
        self.assertEqual(wire.artifact_text(value), json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        work = compact._EncodingWork()
        work.spend(work.remaining)
        with patch.object(wire.json, "dumps", side_effect=AssertionError("artifact allocation reached")):
            with self.assertRaisesRegex(ValueError, "encoding work exceeds"):
                wire.artifact_text(deepcopy(value), work=work)


if __name__ == "__main__":
    unittest.main()
