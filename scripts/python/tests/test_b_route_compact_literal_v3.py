"""Focused offline v3 reference-atom tests; no runner, model or native workspace."""

import ast
import base64
import copy
import importlib.util
import json
from pathlib import Path
import unittest


_SPEC = importlib.util.spec_from_file_location(
    "compact_literal_v3_under_test",
    Path(__file__).resolve().parents[1] / "_b_route_compact_literal.py",
)
codec = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(codec)


def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def materials():
    text = "Complete original material with exact spelling and punctuation. " * 4
    return {
        "rows": [{"original_text": text, "original_values": [2, True, None]} for _ in range(12)],
        "values": [text] * 12,
        "reference": {"$mvg_ref": 7},
        "all_types": [False, True, None, 1, 1.0, -0.0, -1, "R7", "S0", "D0"],
        "ordered": {"z": "\u4e2d\u6587\U0001f680\r\n\t\x00", "a": [3, 2, 1]},
    }


class CompactLiteralV3Tests(unittest.TestCase):
    def packet(self, value):
        return codec.dumps(value, schema=codec.ATOM_SCHEMA)

    def test_full_roundtrip_visible_atoms_and_exact_json_types(self):
        value = materials()
        text = self.packet(value)
        restored = codec.loads(text)
        self.assertEqual(ordered(restored), ordered(value))
        names = {node.id for node in ast.walk(ast.parse(text, mode="eval")) if type(node) is ast.Name}
        self.assertIn("R7", names)
        self.assertTrue(any(name.startswith("S") for name in names))
        self.assertTrue(any(name.startswith("D") for name in names))
        self.assertIs(type(restored["all_types"][0]), bool)
        self.assertIs(type(restored["all_types"][3]), int)
        self.assertIs(type(restored["all_types"][4]), float)
        self.assertEqual(list(restored["ordered"]), ["z", "a"])
        restored["rows"][0]["original_values"].append("changed")
        self.assertEqual(restored["rows"][1]["original_values"], [2, True, None])

    def test_old_empty_goldens_and_default_remain_unchanged(self):
        digest = "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
        v1 = "{'schema_version':'newrouge.b-route-compact-literal.v1','keysets':[],'value':{},'sha256':'" + digest + "'}"
        v2 = "{'schema_version':'newrouge.b-route-compact-literal.v2','keysets':[],'strings':[],'shared':[],'value':{},'sha256':'" + digest + "'}"
        self.assertEqual(codec.dumps({}), v1)
        self.assertEqual(codec.dumps({}, schema=codec.SCHEMA), v1)
        self.assertEqual(codec.dumps({}, schema=codec.CURRENT_SCHEMA), v2)
        self.assertEqual(codec.loads(v1), {})
        self.assertEqual(codec.loads(v2), {})
        self.assertEqual(codec.CURRENT_SCHEMA, "newrouge.b-route-compact-literal.v2")

    def test_literal_reference_keys_and_noninteger_reference_children(self):
        value = {
            "R7": "R7",
            "S0": "S0",
            "D0": "D0",
            "r": 7,
            "~r": False,
            "@": "literal",
            "references": [{"$mvg_ref": child} for child in [False, True, -1, 1.0, "R7", [7], {"a": 1}]],
        }
        self.assertEqual(ordered(codec.loads(self.packet(value))), ordered(value))

    def test_unknown_names_expressions_and_noncanonical_atoms_rejected(self):
        text = self.packet({"reference": {"$mvg_ref": 7}})
        self.assertIn("R7", text)
        for replacement in ["r7", "R", "RTrue", "R07", "R_7", "R7()", "R7.value", "R7[0]", "R7+0"]:
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                codec.loads(text.replace("R7", replacement))
        # The legacy tuple has the same restored value; v3 still requires one canonical spelling.
        with self.assertRaisesRegex(ValueError, "Noncanonical"):
            codec.loads(text.replace("R7", "(7,)"))
        # v1/v2 never accept the new Name grammar, even with the original object digest.
        for version in [codec.SCHEMA, codec.CURRENT_SCHEMA]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                codec.loads(text.replace(codec.ATOM_SCHEMA, version))

    def test_string_and_subtree_range_forward_cycle_and_usage_rejected(self):
        text = self.packet(materials())
        node = ast.parse(text, mode="eval").body
        packet = codec._parse(node, codec.ATOM_SCHEMA)
        self.assertTrue(packet["strings"])
        self.assertTrue(packet["shared"])
        for mutation in ["string-range", "subtree-forward", "subtree-cycle", "unused-string", "unused-subtree"]:
            changed = copy.deepcopy(packet)
            if mutation == "string-range":
                changed["value"] = (None, len(changed["strings"]))
            elif mutation in ("subtree-forward", "subtree-cycle"):
                changed["shared"][0] = (False, 1 if mutation == "subtree-forward" else 0)
            elif mutation == "unused-string":
                changed["strings"].append("unused original data")
            else:
                changed["shared"].append(["unused original subtree"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                codec.loads(codec._atom_literal(changed))

    def test_digest_type_order_and_character_tampering_rejected(self):
        text = self.packet({"reference": {"$mvg_ref": 1}, "numbers": [1, 1.0, True], "text": "source\r\n"})
        for changed in [text.replace("R1", "R2"), text.replace("[1,1.0,True]", "[True,1.0,True]"),
                        text.replace("source\\r\\n", "source\\n")]:
            self.assertNotEqual(changed, text)
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                codec.loads(changed)

    def test_visible_phrases_restore_complete_distinct_strings(self):
        phrase = "Retain the complete original event sequence, exact source bytes and independent observations. "
        value = {"rows": ["original-prefix-" + str(index) + ": " + phrase + " tail-" + str(index)
                          for index in range(12)]}
        text = self.packet(value)
        names = {node.id for node in ast.walk(ast.parse(text, mode="eval")) if type(node) is ast.Name}
        self.assertTrue(any(name.startswith("P") for name in names))
        self.assertIn("phrases", text)
        self.assertIn("Retain the complete original", text)
        self.assertEqual(ordered(codec.loads(text)), ordered(value))

    def test_base64_is_derived_only_from_exact_visible_original_text(self):
        plain = ("Complete visible original source line; preserve its precise spelling and CRLF.\r\n" * 16)
        raw = base64.b64encode(plain.encode("utf-8")).decode("ascii")
        value = {"plain": plain, "raw_base64": raw, "tail": [False, 1, 1.0]}
        text = self.packet(value)
        names = {node.id for node in ast.walk(ast.parse(text, mode="eval")) if type(node) is ast.Name}
        self.assertIn("B", names)
        self.assertEqual(ordered(codec.loads(text)), ordered(value))
        self.assertNotIn(raw, text)
        # No visible source witness: ordinary base64 is preserved literally.
        self.assertIn(raw, self.packet({"raw_base64": raw}))
        changed = base64.b64encode((plain[:-1] + "X").encode("utf-8")).decode("ascii")
        changed_text = self.packet({"plain": plain, "raw_base64": changed})
        self.assertIn(changed, changed_text)
        self.assertEqual(codec.loads(changed_text)["raw_base64"], changed)

    def test_visible_text_grammar_is_closed_and_phrase_table_complete(self):
        text = self.packet({"value": "exact original text"})
        packet = codec._parse(ast.parse(text, mode="eval").body, codec.ATOM_SCHEMA)
        for expression in ["P0", "(C,'x',1)", "(B,False)", "(B,'x','y')", "(C,)", "P0()"]:
            changed = copy.deepcopy(packet)
            changed["value"] = "PLACEHOLDER"
            malformed = codec._atom_literal(changed).replace("'PLACEHOLDER'", expression)
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                codec.loads(malformed)
        changed = copy.deepcopy(packet)
        changed["phrases"] = ["unused visible phrase"]
        with self.assertRaisesRegex(ValueError, "Unused visible phrase"):
            codec.loads(codec._atom_literal(changed))

    def test_short_visible_phrase_remains_complete_without_forcing_a_dictionary(self):
        phrase = "complete exact source fragment"
        value = {"rows": [str(index) + ":" + phrase + ":" + str(index) for index in range(12)]}
        text = self.packet(value)
        parsed = codec._parse(ast.parse(text, mode="eval").body, codec.ATOM_SCHEMA)
        self.assertEqual(parsed["phrases"], [])
        self.assertEqual(ordered(codec.loads(text)), ordered(value))

    def test_phrase_dag_reuses_only_existing_earlier_visible_definitions(self):
        phrase = "Complete visible source witness with exact bytes, observations and original event ordering. " * 2
        phrases = [phrase + "retained suffix", phrase]
        original = [(codec._TEXT_PHRASE, 0), (codec._TEXT_PHRASE, 1)]
        definitions, value = codec._factor_phrases(phrases, original)
        self.assertEqual(definitions[0], phrase)
        self.assertEqual(definitions[1], (codec._TEXT_CONCAT,
                                        [(codec._TEXT_PHRASE, 0), "retained suffix"]))
        self.assertEqual(codec._unpack_text(value, definitions), phrases)

    def test_phrase_dag_forward_cycle_nontext_duplicate_and_unused_rejected(self):
        p = codec._TEXT_PHRASE
        c = codec._TEXT_CONCAT
        b = codec._TEXT_BASE64
        cases = [
            ([(p, 0)], "Invalid or forward"),
            ([(p, 1), "future"], "Invalid or forward"),
            ([(p, True)], "Invalid or forward"),
            ([(b, "not a phrase definition")], "require literal text"),
            ([False], "require literal text"),
            (["literal", (c, [(p, 0), ""])], "duplicate"),
            (["unused literal"], "Unused visible phrase"),
        ]
        for definitions, diagnostic in cases:
            with self.subTest(definitions=definitions), self.assertRaisesRegex(ValueError, diagnostic):
                codec._unpack_text("original payload", definitions)

    def test_full_digest_decimal_atoms_preserve_all_256_bits_and_legacy_spelling(self):
        zero = "sha256:" + "0" * 64
        one = "sha256:" + "0" * 63 + "1"
        maximum = "sha256:" + "f" * 64
        value = {"identities": [zero, one, maximum],
                 "literal_text": ["0" * 64, "sha256:" + "F" * 64, "prefix " + one, one + "\n"],
                 "types": [False, 0, 0.0, True, 1]}
        text = self.packet(value)
        names = {node.id for node in ast.walk(ast.parse(text, mode="eval")) if type(node) is ast.Name}
        self.assertTrue({"H0", "H1", "H" + str((1 << 256) - 1)} <= names)
        self.assertEqual(ordered(codec.loads(text)), ordered(value))
        for schema in [codec.SCHEMA, codec.CURRENT_SCHEMA]:
            legacy = codec.dumps({"digest": one}, schema=schema)
            self.assertIn(one, legacy)
            self.assertEqual(codec.loads(legacy), {"digest": one})
            self.assertFalse(any(type(node) is ast.Name for node in ast.walk(ast.parse(legacy, mode="eval"))))

    def test_digest_atom_rejects_sign_bool_noncanonical_and_overflow(self):
        text = self.packet({"digest": "sha256:" + "0" * 64})
        self.assertIn("H0", text)
        for replacement in ["H00", "H01", "HTrue", "HFalse", "H+0", "H-1", "H1.0", "H1e3",
                            "H" + str(1 << 256), "H" + "9" * 79, "H0()", "H0.value"]:
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                codec.loads(text.replace("H0", replacement))


if __name__ == "__main__":
    unittest.main()
