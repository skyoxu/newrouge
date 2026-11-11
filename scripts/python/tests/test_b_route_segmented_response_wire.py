"""Pure representation tests; no model, native proof or paid-call acceptance."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import _b_route_segmented_workflow as core
import _b_route_segmented_response_wire as wire


class SegmentedResponseWireTests(unittest.TestCase):
    def setUp(self):
        self.envelope = {"protocol": core.PROTOCOL, "run_id": "wire-only", "plan_digest": "digest",
                         "node_id": "panel", "phase": "selection"}
        a = [{"segment_id": "source-a", "start": 0, "end": 5, "raw_digest": "raw-a"}]
        b = [{"segment_id": "source-b", "start": 5, "end": 9, "raw_digest": "raw-b"}]
        self.body = '{"citations":[{"business":"unchanged"}],"citation_set_index":true}'
        self.logical = {**self.envelope, "schema_version": core.RESPONSE,
            "coverage": [{"obligation_id": "oa", "citations": a}, {"obligation_id": "ob", "citations": b}],
            "decisions": [{"decision_id": "d", "obligation_ids": ["oa"], "depends_on": [], "citations": a, "statement": "preserve"}],
            "dependency_edges": [["oa", "ob"]],
            "unresolved": [{"obligation_id": "oa", "reason": "retained unresolved", "citations": a}],
            "findings": [{"obligation_id": "ob", "reason": "retained finding", "citations": b}],
            "checks": [{"obligation_id": "oa", "verdict": "supported", "citations": a}],
            "comparisons": [{"candidate_label": "A", "dimension": "source", "obligation_ids": ["oa", "ob"],
                "assessment": "retained comparison", "citations": a,
                "cross_impacts": [{"from": "oa", "to": "ob", "explanation": "retained impact", "citations": b}]}],
            "candidate_pieces": [{"slot_id": "A/body", "value_json": self.body, "citations": a,
                                  "parent_piece_refs": [{"slot_id": "A/parent", "raw_digest": "parent"}], "change_reason": "retained"}],
            "product_checks": [{"candidate_label": "A", "slot_id": "A/body", "raw_digest": "body", "verdict": "supported", "citations": a}],
            "joint_checks": [{"candidate_label": "A", "domain_digest": "domain", "member_digests": [{"slot_id": "A/body", "raw_digest": "body"}],
                              "interaction_edges": [["A/body", "A/parent"]], "source_obligation_ids": ["oa", "ob"], "verdict": "supported", "citations": a}],
            "selected_label": None, "rationale": "", "derived_not_lossless": True}

    def encoded(self):
        return core.encode_response_wire(self.logical)

    def decode(self, value):
        return core.decode_response_wire(value, self.envelope)

    def test_complete_roundtrip_preserves_all_proof_rows_and_business_bytes(self):
        original = deepcopy(self.logical)
        value = self.encoded()
        self.assertEqual(self.decode(value), original)
        self.assertEqual(json.dumps(self.decode(value), ensure_ascii=False), json.dumps(original, ensure_ascii=False))
        self.assertEqual(self.logical, original)
        self.assertEqual(len(value["citation_sets"]), 2)
        self.assertEqual(value["result"]["candidate_pieces"][0]["value_json"], self.body)
        self.assertEqual(json.loads(self.decode(value)["candidate_pieces"][0]["value_json"])["citation_set_index"], True)
        self.assertEqual(value["result"]["comparisons"][0]["cross_impacts"][0]["citation_set_index"], 1)

    def test_wrong_version_and_legacy_raw_response_have_no_fallback(self):
        for version in (core.RESPONSE, "newrouge.b-route-segmented-response-citation-wire.v2", None):
            with self.subTest(version=version):
                value = self.encoded()
                value["schema_version"] = version
                with self.assertRaises(ValueError):
                    self.decode(value)
        with self.assertRaises(ValueError):
            self.decode(self.logical)

    def test_duplicate_and_unused_table_entries_are_rejected(self):
        for duplicate in (True, False):
            with self.subTest(duplicate=duplicate):
                value = self.encoded()
                extra = deepcopy(value["citation_sets"][0])
                if not duplicate:
                    extra[0]["segment_id"] = "unused-original"
                value["citation_sets"].append(extra)
                with self.assertRaises(ValueError):
                    self.decode(value)

    def test_permuted_table_with_consistently_remapped_indices_is_rejected(self):
        value = self.encoded()
        value["citation_sets"].reverse()
        for row in wire._rows(value["result"]):
            row["citation_set_index"] = 1 - row["citation_set_index"]
        with self.assertRaisesRegex(ValueError, "first_use_order"):
            self.decode(value)

    def test_index_types_and_bounds_are_exact(self):
        for index in (True, False, 0.0, 1.0, -1, 2, "0", None):
            with self.subTest(index=index):
                value = self.encoded()
                value["result"]["coverage"][0]["citation_set_index"] = index
                with self.assertRaises(ValueError):
                    self.decode(value)

    def test_missing_reference_and_unknown_fields_are_rejected(self):
        mutations = (
            lambda v: v["result"]["coverage"][0].pop("citation_set_index"),
            lambda v: v["result"]["coverage"][0].update(citations=v["citation_sets"][0]),
            lambda v: v.update(extra=True),
            lambda v: v["result"].update(extra=True),
            lambda v: v["citation_sets"][0][0].update(extra=True),
            lambda v: v["result"]["comparisons"][0]["cross_impacts"][0].pop("citation_set_index"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                value = self.encoded()
                mutate(value)
                with self.assertRaises(ValueError):
                    self.decode(value)
        with self.assertRaises(ValueError):
            core.codec.strict_json_loads(b'{"schema_version":"x","schema_version":"y"}')

    def test_provider_schema_is_closed_typed_and_contains_no_compound_const(self):
        schema = core.output_schema(self.envelope)
        self.assertEqual(schema["properties"]["schema_version"]["const"], core.RESPONSE_WIRE)
        self.assertNotIn("citations", schema["properties"]["result"]["properties"]["coverage"]["items"]["properties"])
        def check(node):
            if isinstance(node, dict):
                if any(key in node for key in ("const", "enum", "items", "properties")):
                    self.assertIn("type", node)
                if node.get("type") == "object":
                    self.assertIs(node["additionalProperties"], False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                if "const" in node:
                    self.assertNotIsInstance(node["const"], (dict, list))
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(schema)

    def test_nested_citation_contents_and_logical_identity_are_not_normalized(self):
        value = self.encoded()
        value["result"]["run_id"] = "another-run"
        with self.assertRaises(ValueError):
            self.decode(value)
        value = self.encoded()
        value["citation_sets"][0][0]["start"] = True
        with self.assertRaises(ValueError):
            self.decode(value)
        self.assertEqual(self.decode(self.encoded())["findings"], self.logical["findings"])
        value = self.encoded()
        byte_cost, node_cost = wire._preflight_expansion(value, byte_limit=wire.MAX_EXPANDED_UTF8_BYTES,
                                                       node_limit=wire.MAX_EXPANDED_NODES)
        self.assertEqual(byte_cost, len(json.dumps(self.logical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
        # Lower only the test policy. No large tree is created: the original
        # small fixture repeatedly references two small citation arrays.
        original_copy = wire.deepcopy
        payload_ids = {id(value["result"]), *(id(entry) for entry in value["citation_sets"])}
        def guarded_copy(item):
            if id(item) in payload_ids:
                self.fail("model subtree copied before expansion preflight rejected it")
            return original_copy(item)
        entry_costs = [wire._measure_expanded(entry, 100000, 100000)[0] for entry in value["citation_sets"]]
        repeated_reference_bytes = sum(entry_costs[row["citation_set_index"]] for row in wire._rows(value["result"]))
        for setting, limit, diagnostic in (
                ("MAX_EXPANDED_UTF8_BYTES", repeated_reference_bytes - 1, "expansion_utf8_limit"),
                ("MAX_EXPANDED_UTF8_BYTES", byte_cost - 1, "expansion_utf8_limit"),
                ("MAX_EXPANDED_NODES", node_cost - 1, "expansion_node_limit")):
            with self.subTest(policy=setting), patch.object(wire, setting, limit), patch.object(wire, "deepcopy", side_effect=guarded_copy):
                with self.assertRaisesRegex(ValueError, diagnostic):
                    self.decode(value)
        text = {"quoted": '\\"\b\f\n\r\t\x01\u00e9\U0001f600'}
        measured, _nodes = wire._measure_expanded(text, 1000, 100)
        self.assertEqual(measured, len(json.dumps(text, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
