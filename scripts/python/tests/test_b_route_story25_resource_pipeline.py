"""Small R26 resource-pipeline controls; execution belongs to Root."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts/python"))
sys.path.insert(0, str(_ROOT))
from scripts.python import _b_route_planning_wire as wire
import _mvg_lossless_context as legacy

# Use the exact module used by wire, including under package-qualified CI load.
compact = wire.compact


def envelope(encoded):
    return {"schema_version": wire.SCHEMA, "materials_identity": "untrusted",
        "materials_bytes_sha256": "untrusted", "encoded": encoded}


def inner(shared, value):
    return {"schema_version": wire.MODEL_ENCODING, "content_sha256": "untrusted",
        "shared": shared, "value": value}


class SyntaxPreallocationTests(unittest.TestCase):
    def test_compact_node_bound_precedes_ast_construction(self):
        packet = "{'schema_version':'" + compact.CURRENT_SCHEMA + "','value':[" + ",".join(["0"] * 30) + "]}"
        with patch.object(compact, "MAX_EXPANDED_NODES", 20), \
             patch.object(compact.ast, "parse", side_effect=AssertionError("AST allocation reached")):
            with self.assertRaisesRegex(ValueError, "syntax exceeds"):
                compact.loads(packet)

    def test_compact_depth_bound_precedes_ast_construction(self):
        packet = "[" * 8 + "0" + "]" * 8
        with patch.object(compact, "MAX_DEPTH", 4), \
             patch.object(compact.ast, "parse", side_effect=AssertionError("AST allocation reached")):
            with self.assertRaisesRegex(ValueError, "syntax exceeds"):
                compact.loads(packet)

    def test_operator_chains_reject_before_ast_construction(self):
        for packet in ("-" * 40 + "1", "1" + "-1" * 40, "R1[0][0]"):
            with self.subTest(packet=packet), \
                 patch.object(compact.ast, "parse", side_effect=AssertionError("AST allocation reached")):
                with self.assertRaisesRegex(ValueError, "Unsupported"):
                    compact.loads(packet)

    def test_plain_json_node_bound_precedes_json_tree_construction(self):
        prompt = "original header\n[" + ",".join(["false"] * 20) + "]"
        with patch.object(compact, "MAX_EXPANDED_NODES", 12), \
             patch.object(wire.codec, "strict_json_loads", side_effect=AssertionError("JSON allocation reached")):
            with self.assertRaisesRegex(ValueError, "syntax exceeds"):
                wire.read_prompt(prompt)

    def test_strings_escapes_atoms_and_numbers_keep_all_version_canonical_bytes(self):
        value = {"quoted": "[{('not syntax')}]:\\\"\n\u4e2d\u6587", "negative": -4,
            "fraction": 1.25e-5, "types": [False, 0, 0.0, None], "r": {"literal": "marker"}}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            with self.subTest(schema=schema):
                packet = compact.dumps(value, schema=schema)
                restored = compact.loads(packet)
                self.assertEqual(wire.text(restored), wire.text(value))
                self.assertEqual(compact.dumps(restored, schema=schema), packet)
                with self.assertRaisesRegex(ValueError, "Noncanonical"):
                    compact.loads(packet + " ")

    def test_empty_v1_and_v2_golden_bytes_are_unchanged(self):
        digest = "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        for schema, extra in ((compact.SCHEMA, ""), (compact.CURRENT_SCHEMA, "'strings':[],'shared':[],")):
            expected = "{'schema_version':'" + schema + "','keysets':[]," + extra + "'value':{},'sha256':'" + digest + "'}"
            self.assertEqual(compact.dumps({}, schema=schema), expected)

    def test_encoded_utf8_byte_bound_precedes_ast_construction(self):
        packet = "'\u4e2d'"
        with patch.object(compact, "MAX_ENCODED_BYTES", len(packet)), \
             patch.object(compact.ast, "parse", side_effect=AssertionError("AST allocation reached")):
            with self.assertRaisesRegex(ValueError, "encoded bytes"):
                compact.loads(packet)


class CompactWorkTests(unittest.TestCase):
    def test_literal_refuses_before_join_and_does_not_reset_caller_budget(self):
        work = compact._EncodingWork()
        work.spend(work.remaining - 10)
        with patch.object(compact, "_join", side_effect=AssertionError("render allocation reached")):
            with self.assertRaisesRegex(ValueError, "encoding work exceeds"):
                compact._literal({"leaf": "x" * 64}, work)

    def test_share_charges_repeated_subtree_rendering_before_phrase_stage(self):
        value = {"outer": {"middle": {"leaf": "complete original " * 12}}}
        with patch.object(compact, "MAX_ENCODING_WORK", 1800):
            work = compact._EncodingWork()
        render = compact._literal
        observed = []
        def charged_render(node, current=None):
            observed.append(current)
            return render(node, current)
        with patch.object(compact, "_literal", side_effect=charged_render):
            with self.assertRaisesRegex(ValueError, "encoding work exceeds"):
                compact._share(value, work)
        self.assertTrue(observed)
        self.assertTrue(all(current is work for current in observed))

    def test_all_encoder_versions_share_the_supplied_counter_without_factory_reset(self):
        value = {"rows": [{"same_key": "source witness " * 8}] * 3, "typed": [False, 0, None]}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            work = compact._EncodingWork()
            with patch.object(compact, "_EncodingWork", side_effect=AssertionError("budget reset")):
                packet = compact.dumps(value, schema=schema, work=work)
                restored = compact.loads(packet, work=work)
            self.assertEqual(wire.text(restored), wire.text(value))
            self.assertLess(work.remaining, work.limit)

    def test_input_work_refusal_precedes_alias_copy(self):
        work = compact._EncodingWork()
        work.spend(work.remaining - 2)
        with patch.object(compact, "_copy_aliased", side_effect=AssertionError("copy reached")):
            with self.assertRaisesRegex(ValueError, "charged=.*reserve=.*remaining="):
                compact.dumps({"x": "original"}, work=work)


class LosslessPreallocationTests(unittest.TestCase):
    def test_inner_reference_dag_rejects_before_original_decoder(self):
        definitions = [[]]
        for number in range(1, 18):
            definitions.append([{"$mvg_ref": number - 1}, {"$mvg_ref": number - 1}])
        encoded = inner(definitions, {"x": {"$mvg_ref": 17}})
        with patch.object(compact, "MAX_EXPANDED_BYTES", 20_000), \
             patch.object(compact, "MAX_EXPANDED_NODES", 2000):
            compact._json_preflight(encoded)
            with patch.object(wire, "_restore_lossless_value", side_effect=AssertionError("deepcopy reached")):
                with self.assertRaisesRegex(ValueError, "exceeds"):
                    wire.decode(envelope(encoded))

    def test_inner_concat_and_addressed_source_fanout_reject_before_join(self):
        for marker in ("concat", "source"):
            definitions = [{"$mvg_lines": [[1, "complete source line\n"]]}]
            for number in range(1, 14):
                ref = {"$mvg_ref": number - 1}
                body = ({"$mvg_concat": [ref, deepcopy(ref)]} if marker == "concat" else
                    {"$mvg_source": [{"first_line": 1, "first_column": 1, "value": ref},
                        {"first_line": 1 + 2 ** (number - 1), "first_column": 1, "value": deepcopy(ref)}]})
                definitions.append(body)
            encoded = inner(definitions, {"text": {"$mvg_ref": 13}})
            with self.subTest(marker=marker), patch.object(compact, "MAX_EXPANDED_BYTES", 50_000):
                compact._json_preflight(encoded)
                with patch.object(wire, "_restore_lossless_value", side_effect=AssertionError("join reached")):
                    with self.assertRaisesRegex(ValueError, "exceeds"):
                        wire.decode(envelope(encoded))

    def test_lines_auxiliary_allocation_is_bounded_before_decoder(self):
        encoded = inner([], {"text": {"$mvg_lines": [[1, "\n" * 30]]}})
        with patch.object(compact, "MAX_EXPANDED_NODES", 25):
            compact._json_preflight(encoded)
            with patch.object(wire, "_restore_lossless_value", side_effect=AssertionError("splitlines reached")):
                with self.assertRaisesRegex(ValueError, "lines_resource_bound"):
                    wire.decode(envelope(encoded))

    def test_boolean_forward_unused_and_mixed_markers_keep_original_rejections(self):
        cases = [inner([], {"$mvg_ref": False}), inner([{"$mvg_ref": 0}], {}),
            inner(["unused"], {}), inner([], {"$mvg_ref": 0, "ordinary": True})]
        for encoded in cases:
            with self.subTest(encoded=encoded), \
                 patch.object(wire, "_restore_lossless_value", side_effect=AssertionError("decoder reached")):
                with self.assertRaisesRegex(ValueError, "mvg_lossless_"):
                    wire.decode(envelope(encoded))

    def test_literal_markers_and_nested_envelopes_keep_local_namespaces(self):
        nested = legacy.lossless_context({"same": ["inner complete text " * 8] * 3})
        value = {"literal": {"$mvg_ref": 999, "$mvg_concat": ["raw"], "$mvg_lines": "data",
            "$mvg_source": {"unknown": True}, "$mvg_object": [["key", False]]},
            "nested": nested, "originals": [False, 0, None, "\u4e2d\u6587\r\n"]}
        encoded = wire.encode(value)
        self.assertEqual(encoded["encoded"], legacy.lossless_context(value))
        self.assertEqual(wire.text(wire.decode(encoded)), wire.text(value))

    def test_original_content_digest_and_canonical_comparison_remain_active(self):
        encoded = legacy.lossless_context({"source": "original"})
        damaged = deepcopy(encoded)
        damaged["content_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "mvg_lossless_content_changed"):
            wire.restore_lossless_context(damaged)
        noncanonical = deepcopy(encoded)
        noncanonical["value"]["source"] = {"$mvg_concat": ["ori", "ginal"]}
        with self.assertRaisesRegex(ValueError, "mvg_lossless_encoding_changed"):
            wire.restore_lossless_context(noncanonical)


class WirePipelineTests(unittest.TestCase):
    def test_span_reservation_uses_the_original_token_and_line_rules(self):
        samples = ["[" + "x" * 150 + "]", '"' + "[" + "x" * 150 + "]" + '"',
            '"escaped\\\n[' + "x" * 150 + "]", "line\r\n" + "x" * 100 + "\u2028tail",
            "{" + "[" + "x" * 150 + "]}" + "\n"]
        for sample in samples:
            with self.subTest(sample=sample):
                lines, volume, _count = wire._source_plan(sample, compact._EncodingWork())
                expected = legacy._spans(sample) if len(sample) >= 128 else []
                self.assertEqual(volume, sum(end - start for start, end in expected))
                self.assertEqual(lines, len(sample.splitlines(keepends=True)))

    def test_input_size_and_depth_fail_before_legacy_factoring(self):
        with patch.object(compact, "MAX_EXPANDED_BYTES", 512), \
             patch.object(wire, "lossless_context", side_effect=AssertionError("factoring reached")):
            with self.assertRaisesRegex(ValueError, "input exceeds"):
                wire.encode({"source": "x" * 100})
        value = {"x": 0}
        for _ in range(6):
            value = {"child": value}
        with patch.object(compact, "MAX_DEPTH", 4), \
             patch.object(wire, "lossless_context", side_effect=AssertionError("factoring reached")):
            with self.assertRaisesRegex(ValueError, "depth_bound"):
                wire.encode(value)

    def test_factor_subtree_work_is_reserved_before_legacy_serialization(self):
        value = {"leaf": "complete original " * 20}
        for _ in range(6):
            value = {"child": value}
        with patch.object(compact, "MAX_ENCODING_WORK", 12_000), \
             patch.object(wire, "lossless_context", side_effect=AssertionError("wire(node) reached")):
            with self.assertRaisesRegex(ValueError, "encoding work exceeds"):
                wire.encode(value)

    def test_restore_gates_canonical_factor_between_existing_primitives(self):
        encoded = legacy.lossless_context({"source": "complete original " * 10})
        decode = wire._restore_lossless_value
        calls = []
        def decoded(value):
            calls.append("decode")
            return decode(value)
        def refused(value, work):
            calls.append("factor-reservation")
            raise ValueError("policy reservation refused")
        with patch.object(wire, "_restore_lossless_value", side_effect=decoded), \
             patch.object(wire, "_factor_reservation", side_effect=refused), \
             patch.object(wire, "lossless_context", side_effect=AssertionError("canonical allocation reached")):
            with self.assertRaisesRegex(ValueError, "policy reservation refused"):
                wire.restore_lossless_context(encoded)
        self.assertEqual(calls, ["decode", "factor-reservation"])

    def test_render_decode_share_one_counter_and_match_legacy_wire_bytes(self):
        value = {"unknown": [{"typed": [False, 0, 0.0, None]}],
            "source": "first line\r\nsecond line\u4e2d\u6587\n", "literal": {"$mvg_ref": 3}}
        plain = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        self.assertEqual(wire.render("header", value), "header\n" + plain)
        expected = {"schema_version": wire.SCHEMA, "materials_identity": wire.codec.canonical_digest(value),
            "materials_bytes_sha256": wire.codec.raw_digest(plain.encode("utf-8")), "encoded": legacy.lossless_context(value)}
        self.assertEqual(wire.render("header", value, wire.SCHEMA),
            "header " + wire.INSTRUCTION + "\n" + legacy.wire(expected))
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            work = compact._EncodingWork()
            with patch.object(compact, "_EncodingWork", side_effect=AssertionError("pipeline budget reset")):
                prompt = wire.render("header", value, wire.CURRENT_SCHEMA, compact_schema=schema, work=work)
                restored = wire.read_prompt(prompt, wire.CURRENT_SCHEMA, work=work)
            self.assertEqual(wire.text(restored), plain)
            self.assertLess(work.remaining, work.limit)

    def test_wire_identity_type_order_and_digest_tampering_remain_rejected(self):
        value = {"first": False, "second": 0}
        encoded = wire.encode(value)
        for field in ("materials_identity", "materials_bytes_sha256"):
            changed = deepcopy(encoded)
            changed[field] = "tampered"
            with self.assertRaisesRegex(ValueError, "materials_changed"):
                wire.decode(changed)
        changed = deepcopy(encoded)
        changed["encoded"] = legacy.lossless_context({"second": 0, "first": False})
        with self.assertRaisesRegex(ValueError, "materials_changed"):
            wire.decode(changed)
        changed["encoded"] = legacy.lossless_context({"first": 0, "second": False})
        with self.assertRaisesRegex(ValueError, "materials_changed"):
            wire.decode(changed)


if __name__ == "__main__":
    unittest.main()
