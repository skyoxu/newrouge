"""Focused, offline tests for the independent compact data literal codec."""

import ast
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch


_SPEC = importlib.util.spec_from_file_location(
    "compact_literal_under_test",
    Path(__file__).resolve().parents[1] / "_b_route_compact_literal.py",
)
codec = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(codec)


def literal(value):
    """Spell mutated fixtures independently without adding whitespace."""
    if type(value) is dict:
        return "{" + ",".join(repr(k) + ":" + literal(v) for k, v in value.items()) + "}"
    if type(value) is list:
        return "[" + ",".join(literal(v) for v in value) + "]"
    return repr(value)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def repeated_fixture():
    return {
        "rows": [
            {"long_original_field_name": i, "another_original_field_name": [i, False]}
            for i in range(12)
        ],
        "tail": {"unknown_future_field": "complete"},
    }


class CompactLiteralTests(unittest.TestCase):
    def packet(self, value=None):
        return ast.literal_eval(codec.dumps(repeated_fixture() if value is None else value))

    def reject(self, packet):
        with self.assertRaises(ValueError):
            codec.loads(literal(packet))

    def test_schema_and_empty_object_golden(self):
        self.assertEqual(codec.SCHEMA, "newrouge.b-route-compact-literal.v1")
        self.assertIn(codec.SCHEMA, codec.INSTRUCTION)
        self.assertEqual(
            codec.dumps({}),
            "{'schema_version':'newrouge.b-route-compact-literal.v1','keysets':[],"
            "'value':{},'sha256':'sha256:44136fa355b3678a1146ad16f7e8649e"
            "94fb4fc21fe77e8310c060f61caaff8a'}",
        )
        self.assertEqual(codec.loads(codec.dumps({})), {})

    def test_complete_nested_json_types_characters_and_order(self):
        value = {
            "z": [None, True, False, 0, -37, 1.0, -0.0, 1.25e-200, 1.7976931348623157e308],
            "unknown_future_field": {
                "second": "\u4e2d\u6587\U0001f680\u00e9e\u0301\x00\t\r\n\\'\"\u2028",
                "first": [{"b": 2, "a": 1}, [], {}],
            },
            "a": "True False None {'@':[0,[]]} is only string data",
        }
        restored = codec.loads(codec.dumps(value))
        self.assertEqual(json_text(restored), json_text(value))
        self.assertIs(type(restored["z"][1]), bool)
        self.assertIs(type(restored["z"][3]), int)
        self.assertIs(type(restored["z"][5]), float)
        self.assertEqual(math.copysign(1, restored["z"][6]), -1)
        self.assertEqual(list(restored), ["z", "unknown_future_field", "a"])
        self.assertEqual(list(restored["unknown_future_field"]), ["second", "first"])

    def test_every_alias_and_marker_collision_at_multiple_depths(self):
        keys = ["$mvg_ref", "$mvg_object", "$mvg_lines", "$mvg_source", "r", "o",
                "l", "s", "@", "~", "~r", "~~r", "~@", "~$mvg_ref", "$record",
                "$record_literal", "$mvg_concat", "schema_version", ""]
        leaf = {key: [key, {key: False}] for key in keys}
        value = {key: copy.deepcopy(leaf) for key in keys}
        self.assertEqual(json_text(codec.loads(codec.dumps(value))), json_text(value))
        packet = self.packet({key: index for index, key in enumerate(keys)})
        self.assertEqual(list(packet["value"])[:10], ["r", "o", "l", "s", "~r", "~o",
                                                      "~l", "~s", "~@", "~~"])

    def test_repeated_ordered_keys_are_complete_records(self):
        value = repeated_fixture()
        packet = self.packet(value)
        self.assertEqual(packet["keysets"], [["long_original_field_name", "another_original_field_name"]])
        self.assertEqual(packet["value"]["rows"][7], {"@": [0, [7, [7, False]]]})
        self.assertEqual(json_text(codec.loads(literal(packet))), json_text(value))

    def test_keyset_first_traversal_order_and_order_distinction(self):
        first = {"long_first_field": 1, "long_second_field": 2}
        reverse = {"long_second_field": 2, "long_first_field": 1}
        value = {"items": [first, reverse] * 8}
        packet = self.packet(value)
        self.assertEqual(packet["keysets"], [list(first), list(reverse)])
        self.assertEqual(json_text(codec.loads(literal(packet))), json_text(value))

    def test_nonbeneficial_and_single_keysets_are_not_selected(self):
        self.assertEqual(self.packet({"rows": [{"a": 1}] * 12})["keysets"], [])
        self.assertEqual(self.packet({"long_unique_key_name": 1})["keysets"], [])

    def test_determinism_and_no_shared_mutable_objects(self):
        shared = {"nested": []}
        value = {"a": shared, "b": shared}
        before = copy.deepcopy(value)
        text = codec.dumps(value)
        self.assertEqual(text, codec.dumps(copy.deepcopy(value)))
        one, two = codec.loads(text), codec.loads(text)
        one["a"]["nested"].append("changed")
        self.assertEqual(one["b"]["nested"], [])
        self.assertEqual(two, before)
        self.assertEqual(value, before)

    def test_digest_uses_original_ordered_compact_utf8_json(self):
        value = {"second": "\u4e2d\u6587", "first": 1.0}
        expected = "sha256:" + hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()
        self.assertEqual(self.packet(value)["sha256"], expected)
        self.assertNotEqual(codec.dumps(value), codec.dumps(dict(reversed(list(value.items())))))

    def test_invalid_input_types_keys_nonfinite_and_cycles(self):
        class IntSubclass(int):
            pass

        class DictSubclass(dict):
            pass

        invalid = [[], None, DictSubclass(), {1: "key"}, {True: "key"}, {"v": ()},
                   {"v": set()}, {"v": b"bytes"}, {"v": 1j}, {"v": IntSubclass(2)},
                   {"v": float("nan")}, {"v": float("inf")}, {"v": float("-inf")}]
        cycle = {}
        cycle["self"] = cycle
        invalid.append(cycle)
        for value in invalid:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                codec.dumps(value)

    def test_lone_surrogates_are_rejected_by_strict_utf8(self):
        for value in ({"v": "\ud800"}, {"\udfff": None}, {"v": "\ud800\udc00"}):
            with self.subTest(value=ascii(value)), self.assertRaises(ValueError):
                codec.dumps(value)

    def test_duplicate_keys_rejected_before_merging(self):
        text = codec.dumps({"x": 1})
        invalid = [text.replace("'value':{'x':1}", "'value':{'x':0,'x':1}"),
                   text.replace("'value':{'x':1}", "'value':{'\\x78':0,'x':1}"),
                   text.replace("'keysets':[]", "'keysets':[],'keysets':[]")]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                codec.loads(candidate)

    def test_noncanonical_literal_spellings_rejected(self):
        text = codec.dumps({"x": [True, None, 1.0]})
        invalid = [" " + text, text + "\n", "(" + text + ")", text + " # comment",
                   text.replace(":", ": ", 1), text.replace("'x'", '"x"'),
                   text.replace("'x'", "'\\x78'"), text.replace("1.0", "1e0"),
                   text.replace("'x'", "'x' ''")]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                codec.loads(candidate)

    def test_packet_fields_version_and_top_level_are_closed(self):
        for version in ("unknown.v1", [codec.SCHEMA], 1, None):
            packet = self.packet()
            packet["schema_version"] = version
            self.reject(packet)
        packet = self.packet()
        packet["extra"] = None
        self.reject(packet)
        packet = self.packet()
        del packet["sha256"]
        self.reject(packet)
        for candidate in ("[]", "None", "{'schema_version':'legacy.v1'}", 1, b"{}"):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                codec.loads(candidate)

    def test_digest_and_value_tampering_rejected(self):
        for digest in ("sha256:" + "0" * 64, "SHA256:bad", "", 1, None):
            packet = self.packet()
            packet["sha256"] = digest
            self.reject(packet)
        packet = self.packet()
        packet["value"]["tail"]["unknown_future_field"] = "changed"
        self.reject(packet)
        packet = self.packet({"z": 1, "a": 2})
        packet["value"] = {"a": 2, "z": 1}
        self.reject(packet)

    def test_invalid_duplicate_and_unused_tables_rejected(self):
        for tables in (None, {}, ["bad"], [[1]], [["x", "x"]], [["@"]], [["~bad"]]):
            packet = self.packet()
            packet["keysets"] = tables
            self.reject(packet)
        packet = self.packet()
        packet["keysets"].append(packet["keysets"][0].copy())
        self.reject(packet)
        packet = self.packet()
        packet["keysets"].append(["unused_field"])
        self.reject(packet)

    def test_table_reordering_and_field_tampering_rejected(self):
        value = {"rows": ([{"long_first_field": 1}] * 12
                          + [{"another_long_field": 2}] * 12)}
        packet = self.packet(value)
        self.assertEqual(len(packet["keysets"]), 2)
        packet["keysets"].reverse()
        self.reject(packet)
        packet = self.packet()
        packet["keysets"][0][0] = "changed_field_name"
        self.reject(packet)

    def test_invalid_record_indices_and_field_lengths_rejected(self):
        for index in (-1, 1, True, False, 0.0, "0", None):
            packet = self.packet()
            packet["value"]["rows"][0]["@"][0] = index
            self.reject(packet)
        for values in ([], [1], [1, 2, 3], {}, None):
            packet = self.packet()
            packet["value"]["rows"][0]["@"][1] = values
            self.reject(packet)

    def test_malformed_record_and_reserved_key_mixing_rejected(self):
        for record in (None, 0, {}, [], [0], [0, [], 1]):
            packet = self.packet()
            packet["value"]["rows"][0] = {"@": record}
            self.reject(packet)
        packet = self.packet()
        packet["value"]["rows"][0]["extra"] = None
        self.reject(packet)

    def test_noncanonical_alias_and_restored_key_collisions_rejected(self):
        for value in ({"~x": 1}, {"$mvg_ref": 1}, {"r": 1, "$mvg_ref": 2},
                      {"~r": 1, "r": 2, "$mvg_ref": 3}):
            packet = self.packet({"x": 1})
            packet["value"] = value
            self.reject(packet)

    def test_alternative_valid_hash_packet_still_requires_canonical_form(self):
        packet = self.packet()
        keys = packet["keysets"][0]
        for index, row in enumerate(packet["value"]["rows"]):
            packet["value"]["rows"][index] = dict(zip(keys, row["@"][1]))
        packet["keysets"] = []
        self.reject(packet)
        packet = self.packet({"x": 1})
        packet = dict(reversed(list(packet.items())))
        self.reject(packet)

    def test_non_json_literal_types_and_syntax_rejected(self):
        for expression in ("(1,2)", "{1,2}", "b'bytes'", "1j", "1+2j", "1e999",
                           "-1e999", "{1:'key'}", "{True:'key'}", "{'x':1,**{}}",
                           "+1", "...", "nan"):
            packet = codec.dumps({"x": 1})
            candidate = packet.replace("'value':{'x':1}", "'value':{'x':" + expression + "}")
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                codec.loads(candidate)

    def test_calls_attributes_and_comprehensions_never_execute(self):
        expressions = ["__import__('os').system('compact_literal_sentinel')",
                       "(lambda:1)()", "[x for x in [1]]", "{}.clear()",
                       "().__class__", "{'x':x for x in [1]}"]
        with patch("os.system") as system:
            for expression in expressions:
                with self.subTest(expression=expression), self.assertRaises(ValueError):
                    codec.loads(expression)
            system.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
