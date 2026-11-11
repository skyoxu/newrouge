"""Offline tuple transport contracts; actual-request check is explicitly opt-in."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("tuplecompact_under_test",
    Path(__file__).resolve().parents[1] / "_b_route_compact_literal.py")
compact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact)


def literal(value):
    if type(value) is dict:
        return "{" + ",".join(repr(k) + ":" + literal(v) for k, v in value.items()) + "}"
    if type(value) is list:
        return "[" + ",".join(literal(v) for v in value) + "]"
    if type(value) is tuple:
        return "(" + ",".join(literal(v) for v in value) + ("," if len(value) == 1 else "") + ")"
    return repr(value)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def fixture():
    return {"rows": [{"long_original_field_name": i, "another_original_field_name": [i, False]}
        for i in range(12)], "tail": {"unknown_future_field": "complete"}}


class TupleCompactV2Tests(unittest.TestCase):
    def packet(self):
        return ast.literal_eval(compact.dumps(fixture(), schema=compact.CURRENT_SCHEMA))

    def reject(self, packet):
        with self.assertRaises(ValueError):
            compact.loads(literal(packet))

    def test_versioned_tuple_roundtrip_and_legacy_golden(self):
        self.assertEqual(compact.CURRENT_SCHEMA, "newrouge.b-route-compact-literal.v2")
        value = fixture()
        legacy = compact.dumps(value)
        self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(),
            "b22ee82219532bd6f90aa0f9a5443a936bd860c0a49022f1df10bfd706ad0f6e")
        self.assertEqual(compact.dumps(value, schema=compact.SCHEMA), legacy)
        self.assertEqual(compact.instruction(), compact.INSTRUCTION)
        packet = self.packet()
        self.assertIs(type(packet["value"]["rows"][0]), tuple)
        self.assertEqual(packet["value"]["rows"][0], (0, 0, [0, False]))
        self.assertEqual(packet["keysets"], ast.literal_eval(legacy)["keysets"])
        self.assertEqual(json_text(compact.loads(literal(packet))), json_text(value))
        self.assertEqual(compact.loads(legacy), value)
        self.assertEqual(compact.dumps(value), legacy)

    def test_json_types_order_aliases_and_fresh_containers(self):
        keys = ["@", "~@", "r", "~r", "$mvg_ref", "$mvg_object", "$mvg_lines", "$mvg_source", "~", ""]
        value = {"z": [None, True, False, 0, -37, 1.0, -0.0, 1e-200],
            "keys": {key: [key, {key: "中文\x00\r\n\\'\""}] for key in keys},
            "rows": fixture()["rows"], "last": "(0,[True]) is original string data"}
        before = json_text(value)
        text = compact.dumps(value, schema=compact.CURRENT_SCHEMA)
        result = compact.loads(text)
        self.assertEqual(json_text(result), before)
        self.assertIs(type(result["z"][1]), bool)
        self.assertIs(type(result["z"][3]), int)
        self.assertIs(type(result["z"][5]), float)
        self.assertEqual(math.copysign(1, result["z"][6]), -1)
        result["rows"][0]["another_original_field_name"].append("changed")
        self.assertEqual(json_text(compact.loads(text)), before)
        self.assertEqual(json_text(value), before)

    def test_source_tuples_subclasses_cycles_and_unknown_versions_rejected(self):
        class Integer(int):
            pass
        cycle = {}
        cycle["self"] = cycle
        for schema in (None, compact.CURRENT_SCHEMA):
            for value in ({"tuple": (0, [])}, {"value": Integer(1)}, {"value": float("nan")}, cycle):
                with self.subTest(schema=schema, value_type=type(value).__name__), self.assertRaises(ValueError):
                    compact.dumps(value, schema=schema)
        for schema in ("unknown", 1, [], False):
            with self.assertRaises(ValueError):
                compact.dumps({}, schema=schema)

    def test_mixed_record_versions_indices_arity_and_execution_rejected(self):
        packet = self.packet()
        packet["schema_version"] = compact.SCHEMA
        self.reject(packet)  # v1 may never gain tuple syntax.
        packet = self.packet()
        packet["value"]["rows"][0] = {"@": [0, [0, [0, False]]]}
        self.reject(packet)  # v2 may never accept old transport spelling.
        for index in (-1, 1, True, False, 0.0, "0", None):
            packet = self.packet()
            packet["value"]["rows"][0] = (index, [0, [0, False]])
            self.reject(packet)
        for record in ((), (0,), (0, [], 1), (0, []), (0, [1]), (0, [1, 2, 3]), (0, {})):
            packet = self.packet()
            packet["value"]["rows"][0] = record
            self.reject(packet)
        with patch("builtins.eval", side_effect=AssertionError("Never evaluate input")), \
             patch("os.system", side_effect=AssertionError("Never execute input")):
            for expression in ("__import__('os').system('bad')", "[x for x in []]", "(lambda:0)()", "1+1"):
                packet = self.packet()
                text = literal(packet).replace("(0,0,[0,False])", expression, 1)
                with self.assertRaises(ValueError):
                    compact.loads(text)

    def test_integrity_tables_aliases_and_canonical_spelling_enforced(self):
        for mutation in ("digest", "table", "unused", "duplicate", "alias", "value", "ordinary-record"):
            packet = self.packet()
            if mutation == "digest": packet["sha256"] = "sha256:" + "0" * 64
            elif mutation == "table": packet["keysets"][0].reverse()
            elif mutation == "unused": packet["keysets"].append(["unused"])
            elif mutation == "duplicate": packet["keysets"].append(packet["keysets"][0][:])
            elif mutation == "alias": packet["value"]["~bad"] = 1
            elif mutation == "value": packet["value"]["tail"]["unknown_future_field"] = "changed"
            else:
                packet["value"]["rows"] = [dict(zip(packet["keysets"][0], row[1:])) for row in packet["value"]["rows"]]
                packet["keysets"] = []
            with self.subTest(mutation=mutation): self.reject(packet)
        text = compact.dumps(fixture(), schema=compact.CURRENT_SCHEMA)
        for changed in (text + " ", "(" + text + ")", text + " # comment", text.replace("(0,", "(0, ", 1),
                text.replace("'tail'", "'\\x74ail'"), text.replace("'keysets':", "'keysets':[],'keysets':", 1)):
            with self.assertRaises(ValueError): compact.loads(changed)

    def sharing_fixture(self):
        child = {"payload": ["Visible repeated identifier-0123456789", True, 1, 1.0, -0.0],
            "nested": {"second": "Exact original rationale remains visible.", "first": None}}
        return {"items": [deepcopy(child) for _ in range(12)], "$mvg_ref": child,
            "r": child, "~r": child, "@": [None, False, 0]}

    def test_ref_singletons_and_visible_string_subtree_sharing_are_distinct(self):
        value = self.sharing_fixture()
        text = compact.dumps(value, schema=compact.CURRENT_SCHEMA)
        packet = ast.literal_eval(text)
        self.assertTrue(packet["strings"])
        self.assertTrue(packet["shared"])
        self.assertIn("Visible repeated identifier-0123456789", packet["strings"])
        result = compact.loads(text)
        self.assertEqual(json_text(result), json_text(value))
        result["items"][0]["payload"].append("new")
        self.assertNotIn("new", result["items"][1]["payload"])
        self.assertEqual(json_text(compact.loads(text)), json_text(value))
        for child in [None, False, True, 0, -1, 1.0, [], [None, False], {}, {"@": [0, []]}, {"$mvg_ref": False}]:
            original = {"$mvg_ref": child, "r": child, "~r": child}
            self.assertEqual(json_text(compact.loads(compact.dumps(original, schema=compact.CURRENT_SCHEMA))), json_text(original))

    def test_shared_reference_type_bounds_forward_self_cycles_and_unused_rejected(self):
        base = ast.literal_eval(compact.dumps(self.sharing_fixture(), schema=compact.CURRENT_SCHEMA))
        for tag in (None, False):
            for index in (True, False, -1, 999999, 0.0, "0", None):
                changed = deepcopy(base)
                changed["value"] = (tag, index)
                with self.subTest(tag=tag, index=index): self.reject(changed)
        for definitions in ([(False, 0)], [(False, 1), ["later"]], [(False, 1), (False, 0)]):
            changed = deepcopy(base)
            changed["shared"] = definitions
            changed["value"] = (False, 0)
            self.reject(changed)
        for field, extra in (("strings", "unused visible string"), ("shared", ["unused subtree"])):
            changed = deepcopy(base)
            changed[field].append(extra)
            self.reject(changed)
        for field in ("strings", "shared"):
            changed = deepcopy(base)
            changed[field].append(deepcopy(changed[field][0]))
            self.reject(changed)
        for field, wrong in (("strings", [1]), ("shared", [1]), ("strings", {}), ("shared", None)):
            changed = deepcopy(base)
            changed[field] = wrong
            self.reject(changed)

    def test_tuple_tags_empty_keysets_and_noncanonical_pool_spellings_rejected(self):
        base = ast.literal_eval(compact.dumps(self.sharing_fixture(), schema=compact.CURRENT_SCHEMA))
        for record in ((), (True, 0), (None,), (False, 0, 1), ("s", 0), (None, 0, 1)):
            changed = deepcopy(base)
            changed["value"] = record
            self.reject(changed)
        changed = deepcopy(base)
        changed["keysets"].append([])
        self.reject(changed)
        # Valid old two-field spelling is not the finalized flat v2 spelling.
        changed = self.packet()
        changed["value"]["rows"][0] = (0, [0, [0, False]])
        self.reject(changed)
        text = compact.dumps(self.sharing_fixture(), schema=compact.CURRENT_SCHEMA)
        # Reversing definitions or replacing a required pooled value keeps no alternate canonical form.
        changed = deepcopy(base)
        changed["strings"].reverse()
        self.reject(changed)
        for altered in (text.replace("(False,", "(0,", 1), text.replace("(None,", "(False,", 1)):
            with self.assertRaises(ValueError): compact.loads(altered)

    def test_wire_opt_in_keeps_outer_contract_and_legacy_render_exact(self):
        import _b_route_planning_wire as wire
        value = {"original": fixture(), "wire_delivery": wire.CURRENT_SCHEMA}
        prefix = "Preserve all complete governed evidence. No tools."
        expected = (prefix + " " + compact.INSTRUCTION +
            " After restoring the compact packet, decode its complete B-route envelope. " + wire.INSTRUCTION +
            "\n" + compact.dumps(wire.encode(value, wire.CURRENT_SCHEMA)))
        self.assertEqual(wire.render(prefix, value, wire.CURRENT_SCHEMA), expected)
        current = wire.render(prefix, value, wire.CURRENT_SCHEMA, compact_schema=compact.CURRENT_SCHEMA)
        self.assertEqual(wire.read_prompt(current, wire.CURRENT_SCHEMA), value)
        self.assertEqual(compact.loads(current.split("\n", 1)[1])["schema_version"], wire.CURRENT_SCHEMA)
        self.assertEqual(wire.render(prefix, value, wire.CURRENT_SCHEMA), expected)
        for delivery in (None, wire.SCHEMA):
            with self.assertRaises(ValueError):
                wire.render(prefix, value, delivery, compact_schema=compact.CURRENT_SCHEMA)

    @unittest.skipUnless(os.environ.get("NR25_TUPLE_ACTUAL_REQUEST"), "Explicit actual owned request path required")
    def test_complete_actual_failed_request_roundtrip_and_policy_wrapper_budget(self):
        import _b_route_planning_wire as wire
        from _capability_input_integrity import measure_request
        from openai_isolated_model_runner import workspace_payload
        from _planning_skill_common import canonical_sha
        request = Path(os.environ["NR25_TUPLE_ACTUAL_REQUEST"])
        prompt_path = request / "prompt-5-r.txt"
        old_prompt = prompt_path.read_text(encoding="utf-8")
        materials = wire.read_prompt(old_prompt, wire.CURRENT_SCHEMA)
        restored = wire.read_prompt(wire.render("Complete originals", materials, wire.CURRENT_SCHEMA,
            compact_schema=compact.CURRENT_SCHEMA), wire.CURRENT_SCHEMA)
        self.assertEqual(json_text(restored), json_text(materials))
        header = old_prompt.split("\n", 1)[0]
        self.assertIn(compact.INSTRUCTION, header)
        business_instruction = header.split(" " + compact.INSTRUCTION, 1)[0]
        self.assertEqual(wire.render(business_instruction, materials, wire.CURRENT_SCHEMA), old_prompt)
        current_materials = deepcopy(materials)
        current_materials["input_compact_policy"] = compact.CURRENT_SCHEMA
        current_materials["materials_identity"] = canonical_sha({k: v for k, v in current_materials.items()
            if k != "materials_identity"})
        current_prompt = wire.render(business_instruction, current_materials, wire.CURRENT_SCHEMA,
            compact_schema=compact.CURRENT_SCHEMA)
        self.assertEqual(json_text(wire.read_prompt(current_prompt, wire.CURRENT_SCHEMA)), json_text(current_materials))
        unchanged = deepcopy(current_materials)
        del unchanged["input_compact_policy"]
        unchanged["materials_identity"] = materials["materials_identity"]
        self.assertEqual(json_text(unchanged), json_text(materials))
        workspace = workspace_payload(request, prompt_path=prompt_path, output_path=request / "r.json", max_bytes=1048576)
        schema = json.loads((request / "output-schema.json").read_bytes())
        wrapper = lambda prompt: json_text({"prompt": prompt, "output_schema": schema})
        old = measure_request(wrapper(workspace), max_bytes=1048576, max_input_tokens=96000)
        self.assertEqual(old["input_token_estimate"], 94657)
        with self.assertRaisesRegex(ValueError, "runner_context_budget_exceeded"):
            measure_request(wrapper(workspace), max_bytes=1048576, max_input_tokens=96000, reserved_tokens=2000)
        current_workspace = current_prompt.rstrip() + workspace[len(old_prompt.rstrip()):]
        current = measure_request(wrapper(current_workspace), max_bytes=1048576, max_input_tokens=96000, reserved_tokens=2000)
        self.assertLess(current["input_token_estimate"], old["input_token_estimate"])
        self.assertEqual(current["token_counter"], "max(o200k_base,cl100k_base)+10_percent")
        self.assertFalse(current["truncation_allowed"])
        print("TUPLE_ACTUAL_MEASURE=" + json.dumps({"old": old, "current_with_policy": current}))
