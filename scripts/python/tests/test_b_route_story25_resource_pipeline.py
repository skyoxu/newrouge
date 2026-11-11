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


def _original_text_metric(text, work):
    _metric, _utf8_size = compact._metric, compact._utf8_size
    size = 6 * len(text) + 2
    _metric(size)
    encoded_size = _utf8_size(text, work) + 2
    work.spend(encoded_size + len(text))
    text.encode("utf-8", errors="strict")
    encoded_size += sum(1 if char in '\\"\b\t\n\f\r' else 5 if ord(char) < 32 else 0 for char in text)
    return _metric(size, wire_size=encoded_size)


class TextMetricFusionTests(unittest.TestCase):
    def test_old_metric_oracle_matches_all_ascii_and_unicode_width_escape_boundaries(self):
        codes = list(range(128)) + [128, 255, 256, 2047, 2048, 0xD7FF, 0xE000,
            0xFFFE, 0xFFFF, 0x10000, 0x1F642, 0x10FFFF, 0x2028, 0x2029]
        texts = ['', ''.join(map(chr, range(32))), '"\\/\b\t\n\f\r\0', ''.join(map(chr, codes))]
        texts.extend(chr(code) for code in codes)
        for text in texts:
            with self.subTest(codes=[ord(char) for char in text]):
                expected = _original_text_metric(text, compact._EncodingWork())
                actual = compact._text_metric(text, compact._EncodingWork())
                self.assertEqual(expected, actual); self.assertEqual(7, len(actual))
                wire_bytes = len(json.dumps(text, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
                size = 6 * len(text) + 2
                self.assertEqual((size, 1, 1, size, 1, wire_bytes, wire_bytes), actual)

    def test_random_unicode_strings_preserve_every_metric_field_and_json_utf8_width(self):
        import random
        rng = random.Random(281818)
        boundaries = [0, 1, 7, 8, 9, 10, 11, 12, 13, 14, 31, 32, 34, 39, 47, 92,
                      127, 128, 2047, 2048, 0xD7FF, 0xE000, 0xFFFF, 0x10000, 0x10FFFF]
        for number in range(300):
            parts = []
            for _ in range(rng.randrange(65)):
                code = rng.choice(boundaries) if rng.randrange(2) else rng.randrange(0x110000)
                if 0xD800 <= code <= 0xDFFF:
                    code = 0xE000
                parts.append(chr(code))
            text = ''.join(parts)
            with self.subTest(number=number):
                actual = compact._text_metric(text, compact._EncodingWork())
                self.assertEqual(_original_text_metric(text, compact._EncodingWork()), actual)
                self.assertEqual(len(json.dumps(text, ensure_ascii=False, allow_nan=False).encode('utf-8')), actual[5])
                self.assertEqual(actual[5], actual[6])

    def test_surrogates_and_resource_rejection_preserve_error_order_without_partial_metric(self):
        for text in ['\ud800', '\udbff', '\udc00', '\udfff', '\ud83d\ude42',
                     'valid\ud800suffix', '\u4e2d\U0001f642\udfff']:
            errors = []
            for owner in (_original_text_metric, compact._text_metric):
                work = compact._EncodingWork()
                with self.assertRaisesRegex(ValueError, 'JSON data must be encodable as strict UTF-8') as caught:
                    owner(text, work)
                errors.append(str(caught.exception))
                self.assertEqual(len(text), work.limit - work.remaining)
            self.assertEqual(errors[0], errors[1])
        class NoScan(str):
            def __iter__(self):
                raise AssertionError('character scan preceded resource refusal')
        for name, limit in [('MAX_EXPANDED_BYTES', 19), ('MAX_EXPANDED_NODES', 0), ('MAX_DEPTH', 0)]:
            for owner in (_original_text_metric, compact._text_metric):
                work = compact._EncodingWork()
                with patch.object(compact, name, limit), \
                     patch.object(work, 'spend', side_effect=AssertionError('work preceded metric refusal')):
                    with self.assertRaisesRegex(ValueError, 'Compact input exceeds'):
                        owner(NoScan('abc'), work)
        for owner in (_original_text_metric, compact._text_metric):
            with patch.object(compact, 'MAX_EXPANDED_BYTES', 20):
                self.assertEqual(20, owner('abc', compact._EncodingWork())[0])
        for remainder in (0, 2, 3, 4):
            work = compact._EncodingWork(); work.spend(work.remaining - remainder)
            with self.subTest(remainder=remainder), \
                 patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    compact._text_metric('abc', work)
                self.assertGreaterEqual(work.remaining, 0)
        work = compact._EncodingWork(); work.spend(work.remaining - 1)
        with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            compact._text_metric('', work)
        work = compact._EncodingWork(); work.spend(work.remaining - 2)
        self.assertEqual((2, 1, 1, 2, 1, 2, 2), compact._text_metric('', work))
        self.assertEqual(0, work.remaining)

    def test_single_prepaid_scan_removes_discard_encoding_and_never_resets_account(self):
        text = '\0\b\t\n\f\r"\\ASCII\x7f\u0080\u07ff\u0800\uffff\U00010000\U0010ffff'
        old_work = compact._EncodingWork(); new_work = compact._EncodingWork()
        old_counts, new_counts = [], []
        class ObservedText(str):
            def __new__(cls, value, counts):
                result = super().__new__(cls, value); result.counts = counts; return result
            def __iter__(self):
                self.counts.append('scan')
                for char in super().__iter__():
                    self.counts.append('character')
                    yield char
            def encode(self, *args, **kwargs):
                self.counts.append('encode')
                return super().encode(*args, **kwargs)
        expected = _original_text_metric(ObservedText(text, old_counts), old_work)
        with patch.object(compact, '_utf8_size', side_effect=AssertionError('second UTF8 scan')), \
             patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            actual = compact._text_metric(ObservedText(text, new_counts), new_work)
        self.assertEqual(expected, actual)
        self.assertEqual(2, old_counts.count('scan')); self.assertEqual(1, old_counts.count('encode'))
        self.assertEqual(1, new_counts.count('scan')); self.assertEqual(0, new_counts.count('encode'))
        self.assertEqual(2 * len(text), old_counts.count('character'))
        self.assertEqual(len(text), new_counts.count('character'))
        self.assertEqual(2 * len(text) + len(text.encode('utf-8')) + 2, old_work.limit - old_work.remaining)
        self.assertEqual(len(text) + 2, new_work.limit - new_work.remaining)
        early = compact._EncodingWork(); early.spend(early.remaining - len(text) + 1)
        counts = []
        with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            compact._text_metric(ObservedText(text, counts), early)
        self.assertEqual([], counts)

    def test_all_versions_canonical_atomic_and_cold_noncanonical_checks_match_old_metric(self):
        values = [{'controls': ''.join(map(chr, range(32))) + '"\\/\x7f',
                   'unicode': '\u0080\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff',
                   'ordered': {'z': False, 'a': 0, 'one': 1.0, 'zero': -0.0},
                   'rows': [{'complete-original-key': [0, 1, True]}] * 3},
                  {'source': 'Complete original visible source.\n' * 5,
                   'literal': {'$mvg_ref': 'R7'}, 'different_order': [{'z': True, 'a': 1}, {'a': 1, 'z': True}]}]
        for number, value in enumerate(values):
            for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
                with self.subTest(number=number, schema=schema):
                    with patch.object(compact, '_text_metric', _original_text_metric):
                        expected = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, compact.dumps(value, schema=schema))
                    work = compact._EncodingWork()
                    with patch.object(compact, '_EncodingWork', side_effect=AssertionError('atomic account reset')):
                        body, restored = compact.produce_canonical_roundtrip(value, schema, work=work)
                    self.assertEqual(expected, body); self.assertEqual(wire.text(value), wire.text(restored))
                    cold = compact._EncodingWork()
                    with patch.object(compact, '_EncodingWork', side_effect=AssertionError('cold account reset')):
                        actual = compact.loads(body, work=cold)
                    self.assertEqual(wire.text(value), wire.text(actual))
                    with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                        compact.loads(body + ' ')


def _original_share(value, work=None):
    """Select visible definitions by deterministic character savings, not a tokenizer."""
    from collections import Counter
    _work, _walk, _literal, _children, _repr = compact._work, compact._walk, compact._literal, compact._children, compact._repr
    work = _work(work)
    counts = Counter()
    def count_string(node):
        if type(node) is str:
            counts[node] += 1
    _walk(value, count_string, work)
    strings = []
    for string, count in counts.items():
        if (count >= 2 and len(string) >= 16 and (count - 1) * len(_repr(string, work))
                > count * len(_literal((None, len(strings)), work)) + 1):
            strings.append(string)
    work.spend(len(strings))
    indices = {string: index for index, string in enumerate(strings)}
    def encode_strings(node):
        if type(node) is str and node in indices:
            return (None, indices[node])
        return _children(node, encode_strings, work)
    encoded = encode_strings(value)
    counts = Counter()
    def count_container(node):
        if type(node) in (dict, list, tuple):
            key = _literal(node, work)
            work.spend(2 * len(key) + 1)
            counts[key] += 1
    _walk(encoded, count_container, work)
    work.spend(len(counts))
    selected = {key for key, count in counts.items() if count >= 2 and len(key) >= 24
        and (count - 1) * len(key) > count * len(_literal((False, len(counts)), work)) + 1}
    definitions, identities = [], {}
    def encode_shared(node):
        key = _literal(node, work) if type(node) in (dict, list, tuple) else None
        if key is not None:
            work.spend(2 * len(key) + 1)
        if key in selected:
            if key not in identities:
                definition = _children(node, encode_shared, work)
                identities[key] = len(definitions)
                definitions.append(definition)
            return (False, identities[key])
        return _children(node, encode_shared, work)
    return strings, definitions, encode_shared(encoded)


class ShareLiteralCacheTests(unittest.TestCase):
    def test_original_share_oracle_matches_typed_ordered_wrappers_and_alias_identities(self):
        shared = {'complete-original-key': [False, 0, 1, 1.0, 0.0, -0.0]}
        values = [{'z': {'z': False, 'a': 0}, 'a': {'a': 0, 'z': False}},
                  [(), (), (0,), [0], (None, 0), (False, 0), (0, 0)],
                  {'quoted': "'\\\n\0\u4e2d\U0001f642", 'literal': '(False,0)', 'digest': 'sha256:' + 'a' * 64},
                  [shared, shared, deepcopy(shared), {'@': [0, []]}]]
        for value in values:
            expected = _original_share(value)
            actual = compact._share(value)
            self.assertEqual(compact._literal(expected), compact._literal(actual))
        aliased = [shared, shared]
        copied = [deepcopy(shared), deepcopy(shared)]
        self.assertEqual(compact._literal(compact._share(aliased)), compact._literal(compact._share(copied)))

    def test_exact_literal_groups_preserve_selection_boundaries_and_definition_order(self):
        #1000 distinct fillers keep the original reference-benefit denominator
        # at1002 keys. Literal lengths24/25 do not beat2*12+1;26 does.
        for length, selected_count in ((18, 0), (19, 0), (20, 1)):
            child = {'k' * length: 0}
            value = [{'f': number} for number in range(1000)] + [child, child]
            expected, actual = _original_share(value), compact._share(value)
            self.assertEqual(compact._literal(expected), compact._literal(actual))
            self.assertEqual(selected_count, len(actual[1]))
        child = {'complete-original-key': 0}
        parent = [child, child, 0]
        value = [parent, parent, child]
        expected, actual = _original_share(value), compact._share(value)
        self.assertEqual(compact._literal(expected), compact._literal(actual))
        self.assertEqual(2, len(actual[1]))
        self.assertEqual(compact._literal(child), compact._literal(actual[1][0]))
        self.assertEqual(compact._literal([(False, 0), (False, 0), 0]), compact._literal(actual[1][1]))
        self.assertEqual(compact._literal([(False, 1), (False, 1), (False, 0)]), compact._literal(actual[2]))

    def test_second_pass_reuses_real_first_keys_without_rendering_or_discounting_hash_work(self):
        child = {'complete-original-key': 0}
        parent = [child, child, 0]
        value = [parent, parent, child]
        literal = compact._literal
        def observed_run(owner):
            work = compact._EncodingWork(); spend = work.spend
            renders, charges = [], []
            def observed_literal(node, current=None):
                caller = sys._getframe(1).f_code.co_name
                text = literal(node, current)
                renders.append((caller, text, current))
                return text
            def observed_spend(amount=1, **kwargs):
                charges.append((sys._getframe(1).f_code.co_name, amount))
                return spend(amount, **kwargs)
            work.spend = observed_spend
            try:
                with patch.object(compact, '_literal', new=observed_literal), \
                     patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                    result = owner(value, work)
            finally:
                del work.spend
            self.assertTrue(all(current is work for _, _, current in renders))
            return result, renders, charges
        expected, old_renders, old_charges = observed_run(_original_share)
        actual, new_renders, new_charges = observed_run(compact._share)
        self.assertEqual(literal(expected), literal(actual))
        old_first = [text for caller, text, _ in old_renders if caller == 'count_container']
        new_first = [text for caller, text, _ in new_renders if caller == 'count_container']
        old_second = [text for caller, text, _ in old_renders if caller == 'encode_shared']
        self.assertEqual(old_first, new_first); self.assertTrue(old_second)
        self.assertFalse(any(caller == 'encode_shared' for caller, _, _ in new_renders))
        first_reserves = [2 * len(text) + 1 for text in old_first]
        self.assertTrue(all(amount > 16 for amount in first_reserves))
        self.assertEqual(first_reserves, [amount for caller, amount in old_charges if caller == 'count_container'])
        self.assertEqual(first_reserves, [amount for caller, amount in new_charges if caller == 'count_container' and amount > 16])
        second_reserves = [2 * len(text) + 1 for text in old_second]
        self.assertEqual(second_reserves, [amount for caller, amount in old_charges if caller == 'encode_shared'])
        self.assertEqual([amount for reserve in second_reserves for amount in (8, reserve)],
                         [amount for caller, amount in new_charges if caller == 'encode_shared'])

    def test_budget_memory_and_cleanup_failures_preserve_primary_and_never_reset_or_return_partial(self):
        value = [{'complete-original-key': 0}] * 3
        def assert_clean(error):
            current = error.__traceback__
            frames = []
            while current is not None:
                if current.tb_frame.f_code.co_name == '_share':
                    frames.append(current.tb_frame)
                current = current.tb_next
            self.assertTrue(frames)
            for frame in frames:
                self.assertEqual({}, frame.f_locals['by_id'])
                self.assertEqual({}, frame.f_locals['counts'])
        for target, reserve in (('count_container', 16), ('count_container', 6), ('encode_shared', 8)):
            work = compact._EncodingWork(); spend = work.spend; failed = []
            def interrupted_spend(amount=1, **kwargs):
                if failed:
                    raise AssertionError('cleanup spent after primary refusal')
                if sys._getframe(1).f_code.co_name == target and amount == reserve:
                    spend(work.remaining - amount + 1)
                    failed.append(True)
                return spend(amount, **kwargs)
            work.spend = interrupted_spend
            try:
                with self.subTest(target=target, reserve=reserve), \
                     patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                    try:
                        compact._share(value, work)
                    except ValueError as error:
                        self.assertRegex(str(error), 'encoding work exceeds')
                        self.assertTrue(failed); assert_clean(error)
                    else:
                        self.fail('A refused share returned partial output')
            finally:
                del work.spend
        for stage in ('count_container', 'encode_shared'):
            failure = MemoryError('fixed synthetic share interruption at ' + stage)
            literal, children = compact._literal, compact._children
            seen = []
            def interrupted_literal(node, current=None):
                if sys._getframe(1).f_code.co_name == stage:
                    seen.append(True)
                    if len(seen) == 2:
                        raise failure
                return literal(node, current)
            def interrupted_children(node, transform, current=None):
                if sys._getframe(1).f_code.co_name == stage:
                    raise failure
                return children(node, transform, current)
            with patch.object(compact, '_literal', new=interrupted_literal), \
                 patch.object(compact, '_children', new=interrupted_children):
                try:
                    compact._share(value)
                except MemoryError as error:
                    self.assertIs(failure, error); assert_clean(error)
                else:
                    self.fail('An interrupted share returned partial output')

    def test_full_version_canonical_atomic_and_cold_noncanonical_checks_match_original_share(self):
        values = [{'ordered': {'z': False, 'a': 0, 'one': 1.0, 'zero': -0.0},
                   'rows': [{'complete-original-key': [0, 1, True]}] * 3,
                   'literal': {'$mvg_ref': 'R7'}, 'source': 'Complete visible source.\n' * 5},
                  {'rows': [{'first': '\0\u4e2d\U0001f642', 'second': '(None,0)'}] * 4,
                   'different_order': [{'z': True, 'a': 1}, {'a': 1, 'z': True}]}]
        for number, value in enumerate(values):
            for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
                with self.subTest(number=number, schema=schema):
                    with patch.object(compact, '_share', _original_share):
                        expected = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, compact.dumps(value, schema=schema))
                    work = compact._EncodingWork()
                    with patch.object(compact, '_EncodingWork', side_effect=AssertionError('atomic account reset')):
                        body, restored = compact.produce_canonical_roundtrip(value, schema, work=work)
                    self.assertEqual(expected, body); self.assertEqual(wire.text(value), wire.text(restored))
                    cold = compact._EncodingWork()
                    with patch.object(compact, '_EncodingWork', side_effect=AssertionError('cold account reset')):
                        actual = compact.loads(body, work=cold)
                    self.assertEqual(wire.text(value), wire.text(actual))
                    with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                        compact.loads(body + ' ')


def _original_visible_dp(text, originals, work):
    """Prove a full plaintext is exactly made from already visible original leaves."""
    starts = {}
    for fragment in originals:
        work.spend(len(fragment) + 1)
        if fragment:
            starts.setdefault(fragment[0], []).append(fragment)
    reachable = {len(text)}
    for offset in range(len(text) - 1, -1, -1):
        work.spend()
        for fragment in starts.get(text[offset], ()):
            work.spend(len(fragment) + 1)
            if offset + len(fragment) in reachable and text.startswith(fragment, offset):
                reachable.add(offset)
                break
    return 0 in reachable


class VisibleAliasPruningTests(unittest.TestCase):
    def test_original_dp_oracle_matches_empty_unicode_nul_and_exhaustive_short_cases(self):
        from itertools import combinations, product
        fragments = ['', 'a', 'b', 'aa', 'ab', 'ba', 'bb']
        texts = [''] + [''.join(parts) for size in range(1, 5) for parts in product('ab', repeat=size)]
        for count in range(4):
            for originals in combinations(fragments, count):
                for text in texts:
                    self.assertEqual(_original_visible_dp(text, originals, compact._EncodingWork()),
                                     compact._visible_text(text, originals, compact._EncodingWork()), (text, originals))
        for text, originals in [('', ()), ('', ('', 'oversized')), ('a', ('',)),
                ('\u4e2d\U0001f642\0\u4e2d', ('\u4e2d', '\U0001f642\0')),
                ('\u4e2d\U0001f642\0x', ('\u4e2d', '\U0001f642\0')),
                ('e\u0301\u00e9', ('e\u0301', '\u00e9'))]:
            with self.subTest(text=text, originals=originals):
                self.assertEqual(_original_visible_dp(text, originals, compact._EncodingWork()),
                                 compact._visible_text(text, originals, compact._EncodingWork()))

    def test_unreachable_end_and_oversized_fragments_skip_only_impossible_comparisons(self):
        work = compact._EncodingWork(); work.spend(work.remaining - 1000)
        calls = []
        class ObservedText(str):
            def startswith(self, fragment, offset=0, *args):
                calls.append((fragment, offset))
                return super().startswith(fragment, offset, *args)
        originals = ('abc', 'ab', 'cd', 'a' * 10000 + 'z', '')
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            self.assertTrue(compact._visible_text(ObservedText('abcd'), originals, work))
        self.assertEqual([('cd', 2), ('ab', 0)], calls)
        self.assertGreater(work.remaining, 0); self.assertLess(work.remaining, 1000)
        original_work = compact._EncodingWork(); original_work.spend(original_work.remaining - 1000)
        with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            _original_visible_dp('abcd', originals, original_work)
        self.assertTrue(_original_visible_dp('abcd', originals, compact._EncodingWork()))

    def test_overlap_alternatives_and_full_alias_coverage_preserve_original_dp(self):
        cases = [('abcd', ('abc', 'ab', 'cd'), True),
                 ('abcd', ('abc', 'ab', 'ce'), False),
                 ('abcdef', ('abcd', 'ab', 'cdef', 'ef'), True),
                 ('aaaab', ('aaa', 'aa', 'ab'), True),
                 ('abc', ('abcd', ''), False),
                 ('abcabc', ('abca', 'abc', 'bc'), True),
                 ('prefix-gap-suffix', ('prefix-', 'suffix'), False)]
        for text, originals, expected in cases:
            with self.subTest(text=text, originals=originals):
                self.assertIs(expected, _original_visible_dp(text, originals, compact._EncodingWork()))
                self.assertIs(expected, compact._visible_text(text, originals, compact._EncodingWork()))

    def test_same_account_reserves_full_actual_comparisons_and_refuses_without_partial_boolean(self):
        work = compact._EncodingWork(); spend = work.spend
        charges, comparisons = [], []
        def observed(amount=1, **kwargs):
            charges.append(amount)
            return spend(amount, **kwargs)
        class ObservedText(str):
            def startswith(self, fragment, offset=0, *args):
                comparisons.append(len(charges) - 1)
                return super().startswith(fragment, offset, *args)
        with patch.object(work, 'spend', side_effect=observed), \
             patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            self.assertTrue(compact._visible_text(ObservedText('ab'), ('ab',), work))
        self.assertEqual(1, len(comparisons))
        comparison = comparisons[0]
        self.assertEqual(len('ab') + 1, charges[comparison])
        for refusal in (0, 1, comparison, comparison + 1, len(charges) - 1):
            remainder = sum(charges[:refusal]) + charges[refusal] - 1
            current = compact._EncodingWork(); current.spend(current.remaining - remainder)
            reached = []
            class RefusedText(str):
                def startswith(self, fragment, offset=0, *args):
                    reached.append((fragment, offset))
                    return super().startswith(fragment, offset, *args)
            with self.subTest(refusal=refusal), \
                 patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    compact._visible_text(RefusedText('ab'), ('ab',), current)
            self.assertEqual(0 if refusal <= comparison else 1, len(reached))
            self.assertGreaterEqual(current.remaining, 0)
        failure = MemoryError('fixed synthetic visibility interruption')
        class InterruptedText(str):
            def startswith(self, *args):
                raise failure
        with self.assertRaises(MemoryError) as caught:
            compact._visible_text(InterruptedText('ab'), ('ab',), compact._EncodingWork())
        self.assertIs(failure, caught.exception)
        import base64
        source = 'abc' * 400
        value = {'visible': source, 'encoded': base64.b64encode(source.encode()).decode()}
        with patch.object(compact, '_visible_text', side_effect=failure), \
             patch.object(compact, '_atom_literal', side_effect=AssertionError('partial body reached')):
            with self.assertRaises(MemoryError) as public_error:
                compact.dumps(value, schema=compact.ATOM_SCHEMA)
        self.assertIs(failure, public_error.exception)

    def test_all_version_canonical_bytes_cold_roundtrip_and_noncanonical_refusal_match_original_dp(self):
        import base64
        left, right = 'left original source line\n' * 40, 'right original source line\n' * 40
        unicode_fragment = '\u03b1\0\u4e2d\U0001f642' * 110
        values = [{'fragments': [left, right], 'alias': base64.b64encode((left + right).encode()).decode(),
                   'ordered': {'z': False, 'a': 0, 'b': 1.0, 'zero': -0.0}},
                  {'fragments': ['a' * 900, 'b' * 900],
                   'not_full_alias': base64.b64encode(('a' * 900 + 'b' * 900 + 'q').encode()).decode()},
                  {'fragments': [unicode_fragment, unicode_fragment],
                   'alias': base64.b64encode((unicode_fragment * 2).encode()).decode()}]
        for number, value in enumerate(values):
            for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
                with self.subTest(number=number, schema=schema):
                    with patch.object(compact, '_visible_text', _original_visible_dp):
                        expected = compact.dumps(value, schema=schema)
                    body = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, body)
                    self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
                    with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                        compact.loads(body + ' ')


class _OriginalScanIndex:
    """Independent full previous-leaf scan, never a SAM/suffix-link oracle."""
    def __init__(self, work):
        work.spend()
        self.leaves = []

    def append(self, text, work, *, epoch):
        if epoch != len(self.leaves):
            raise AssertionError('oracle leaf order')
        work.spend(len(text) + 1)
        self.leaves.append(text)

    def longest(self, text, offset, prefix_size, work, *, epoch):
        if epoch != len(self.leaves):
            raise AssertionError('oracle query epoch')
        if len(text) - offset < prefix_size:
            return 0
        key = text[offset:offset + prefix_size]
        locations = [(index, start) for index, leaf in enumerate(self.leaves)
                     for start in range(max(0, len(leaf) - prefix_size + 1))
                     if leaf.startswith(key, start)]
        return PrefixCandidateScanTests.original_scan(text, offset, self.leaves, locations, prefix_size, work)

    def lengths_for_leaf(self, text, prefix_size, work, *, epoch):
        # Deliberately repeat the original complete scan at every position.
        # No suffix links, interval propagation or production bulk algorithm.
        return [self.longest(text, offset, prefix_size, work, epoch=epoch)
                for offset in range(len(text))]


class PrefixCandidateScanTests(unittest.TestCase):
    @staticmethod
    def original_scan(text, offset, texts, locations, prefix_size, work):
        # Exact original candidate/LCP loop, retained as an independent oracle.
        best = 0
        for earlier, start in locations:
            work.spend()
            source = texts[earlier]
            length = prefix_size
            while (offset + length < len(text) and start + length < len(source)
                    and text[offset + length] == source[start + length]):
                work.spend()
                length += 1
            best = max(best, length)
        return best

    def test_candidate_maxima_match_original_for_overlap_unicode_ties_and_suffix_bounds(self):
        leaves = ['a' * 160, 'a' * 80 + 'b' + 'a' * 79,
                  'ab' * 90, 'ab' * 65 + 'ac', '\u4e2d\U0001f642' * 80, 'x' * 16]
        work = compact._EncodingWork()
        index, oracle = compact._SubstringIndex(work), _OriginalScanIndex(compact._EncodingWork())
        for epoch, text in enumerate(leaves):
            for offset in (0, 1, len(text) // 2):
                with self.subTest(epoch=epoch, offset=offset):
                    self.assertEqual(oracle.longest(text, offset, 16, compact._EncodingWork(), epoch=epoch),
                                     index.longest(text, offset, 16, work, epoch=epoch))
            index.append(text, work, epoch=epoch)
            oracle.append(text, compact._EncodingWork(), epoch=epoch)

    def test_all_version_canonical_packets_match_original_scan_and_cold_roundtrip(self):
        value = {'ordered': {'z': False, 'a': 0, 'b': -0.0},
            'sources': ['a' * 160, 'a' * 80 + 'b' + 'a' * 79, '\u4e2d\U0001f642' * 80],
            'rows': [{'same': 'ab' * 90}, {'same': 'ab' * 90}], 'literal': 'P1 R2 D3'}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            with self.subTest(schema=schema):
                with patch.object(compact, '_SubstringIndex', _OriginalScanIndex):
                    original_body = compact.dumps(value, schema=schema)
                body = compact.dumps(value, schema=schema)
                self.assertEqual(original_body, body)
                self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
                with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                    compact.loads(body + ' ')

    def test_repeated_queries_use_original_account_without_new_counter(self):
        text = 'a' * 512
        build_work = compact._EncodingWork()
        index = compact._SubstringIndex(build_work)
        oracle = _OriginalScanIndex(compact._EncodingWork())
        for epoch in range(40):
            index.append(text, build_work, epoch=epoch)
            oracle.append(text, compact._EncodingWork(), epoch=epoch)
        work = compact._EncodingWork(); work.spend(work.remaining - 10000)
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('budget reset')):
            self.assertEqual(512, index.longest(text, 0, 16, work, epoch=40))
        original_work = compact._EncodingWork(); original_work.spend(original_work.remaining - 10000)
        with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            oracle.longest(text, 0, 16, original_work, epoch=40)
        self.assertGreater(work.remaining, 0)

    def test_near_miss_retains_later_longest_witness_with_counted_queries(self):
        leaves = ['a' * 64 + 'q', 'a' * 32, 'a' * 100 + 'q', 'a' * 64 + 'r']
        build = compact._EncodingWork(); index = compact._SubstringIndex(build)
        for epoch, text in enumerate(leaves):
            index.append(text, build, epoch=epoch)
        work = compact._EncodingWork(); work.spend(work.remaining - 1000)
        self.assertEqual(100, index.longest('a' * 120 + 'z', 0, 16, work, epoch=4))
        self.assertGreater(work.remaining, 0)
        self.assertLess(work.remaining, 1000)

    def test_query_position_checks_and_budget_refusals_return_no_partial_match(self):
        build = compact._EncodingWork(); index = compact._SubstringIndex(build)
        index.append('a' * 96, build, epoch=0)
        for remaining in (0, 1, 2, 8, 30):
            work = compact._EncodingWork(); work.spend(work.remaining - remaining)
            with self.subTest(remaining=remaining), \
                 patch.object(compact, '_EncodingWork', side_effect=AssertionError('budget reset')):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    index.longest('a' * 96, 0, 16, work, epoch=1)
                self.assertGreaterEqual(work.remaining, 0)


class SubstringAutomatonTests(unittest.TestCase):
    @staticmethod
    def make(leaves):
        work = compact._EncodingWork()
        index, oracle = compact._SubstringIndex(work), _OriginalScanIndex(compact._EncodingWork())
        for epoch, text in enumerate(leaves):
            index.append(text, work, epoch=epoch)
            oracle.append(text, compact._EncodingWork(), epoch=epoch)
        return index, oracle, work

    def test_oracle_maxima_cover_unicode_nul_duplicates_ties_and_boundaries(self):
        prefix = 'same-prefix-1234'
        leaves = [prefix, prefix + 'a', prefix + 'a' * 48, prefix + 'a' * 49,
                  prefix + '\0tail', prefix + '\u4e2d\U0001f642' * 30, prefix + 'a' * 48]
        index, oracle, work = self.make(leaves)
        queries = [prefix[:15], prefix, prefix + 'a' * 47 + 'b', prefix + 'a' * 49,
                   prefix + '\0taim', prefix + '\u4e2d\U0001f642' * 29 + '\u6587']
        for query in queries:
            for offset in (0, 1, len(query)):
                with self.subTest(query=query, offset=offset):
                    self.assertEqual(oracle.longest(query, offset, 16, compact._EncodingWork(), epoch=len(leaves)),
                                     index.longest(query, offset, 16, work, epoch=len(leaves)))

    def test_every_leaf_greedy_candidates_equal_full_original_scan(self):
        texts = ['a' * 140 + 'q', 'a' * 120 + 'r', 'ab' * 60,
                 'a' * 96 + 'z', 'ab' * 40 + 'cd' * 20, '\u4e2d\U0001f642' * 60]
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        oracle = _OriginalScanIndex(compact._EncodingWork())
        for epoch, text in enumerate(texts):
            actual, expected = [], []
            for owner, target in ((index, actual), (oracle, expected)):
                offset = 0
                while offset + 64 <= len(text):
                    best = owner.longest(text, offset, 16, work, epoch=epoch)
                    if best >= 64:
                        target.append((offset, text[offset:offset + best])); offset += best
                    else:
                        offset += 1
            self.assertEqual(expected, actual)
            index.append(text, work, epoch=epoch)
            oracle.append(text, work, epoch=epoch)

    def test_leaf_publication_never_admits_current_text_or_cross_separator_join(self):
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        self.assertEqual(0, index.longest('abc', 0, 0, work, epoch=0))
        index.append('ab', work, epoch=0)
        index.append('cd', work, epoch=1)
        self.assertEqual(1, index.longest('bc', 0, 0, work, epoch=2))
        self.assertEqual(2, index.longest('abcd', 0, 0, work, epoch=2))
        with self.assertRaisesRegex(ValueError, 'epoch'):
            index.longest('abcd', 0, 0, work, epoch=1)
        self.assertEqual(2, index.epoch)

    def test_duplicate_and_periodic_leaves_preserve_the_exact_substring_language(self):
        leaves = ['aba', 'bab', 'aba', '', 'abab', 'baba']
        index, oracle, work = self.make(leaves)
        for query in ['ababab', 'babab', 'ababa', 'aa', 'bb', '', 'aba\0bab']:
            self.assertEqual(oracle.longest(query, 0, 0, compact._EncodingWork(), epoch=len(leaves)),
                             index.longest(query, 0, 0, work, epoch=len(leaves)))

    def test_random_small_corpora_and_exhaustive_queries_match_independent_oracle(self):
        from itertools import product
        import random
        words = [''] + [''.join(parts) for size in range(1, 4) for parts in product('ab', repeat=size)]
        queries = [''] + [''.join(parts) for size in range(1, 5) for parts in product('ab', repeat=size)]
        corpora = [(first, second) for first in words for second in words]
        rng = random.Random(261128)
        corpora.extend(tuple(''.join(rng.choice('ab\0\u4e2d') for _ in range(rng.randrange(8)))
                             for _ in range(4)) for _ in range(50))
        for leaves in corpora:
            index, oracle, work = self.make(leaves)
            for query in queries:
                for offset in (0, len(query) // 2, len(query)):
                    self.assertEqual(oracle.longest(query, offset, 0, compact._EncodingWork(), epoch=len(leaves)),
                                     index.longest(query, offset, 0, work, epoch=len(leaves)), (leaves, query, offset))

    def test_clone_construction_preserves_language_and_link_length_invariants(self):
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        original = compact._SubstringIndex._state; cloned = []
        def observed(owner, length, link, copy_from, current):
            if copy_from is not None:
                cloned.append(len(copy_from))
            return original(owner, length, link, copy_from, current)
        with patch.object(compact._SubstringIndex, '_state', observed):
            index.append('abb', work, epoch=0)
        self.assertTrue(cloned)
        self.assertEqual(len(index.edges), len(index.links)); self.assertEqual(len(index.edges), len(index.lengths))
        self.assertLessEqual(len(index.edges), 2 * (len('abb') + 1) + 1)
        for state in range(1, len(index.links)):
            self.assertTrue(0 <= index.links[state] < len(index.links))
            self.assertLess(index.lengths[index.links[state]], index.lengths[state])
        for query in ['abb', 'bb', 'ab', 'bba', 'bab']:
            expected = max((len(query[:length]) for length in range(len(query) + 1) if query[:length] in 'abb'), default=0)
            self.assertEqual(expected, index.longest(query, 0, 0, work, epoch=1))

    def test_budget_interruptions_poison_append_before_any_partial_epoch_publication(self):
        for remaining in (0, 1, 5, 10, 20, 60):
            build = compact._EncodingWork(); index = compact._SubstringIndex(build)
            index.append('prior', build, epoch=0)
            work = compact._EncodingWork(); work.spend(work.remaining - remaining)
            with self.subTest(remaining=remaining):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    index.append('ab' * 30, work, epoch=1)
                self.assertTrue(index.failed); self.assertEqual(1, index.epoch)
                with self.assertRaisesRegex(ValueError, 'Incomplete substring index'):
                    index.longest('prior', 0, 0, compact._EncodingWork(), epoch=1)
                with self.assertRaisesRegex(ValueError, 'Incomplete substring index'):
                    index.append('', compact._EncodingWork(), epoch=1)

    def test_clone_copy_budget_failure_poisoned_graph_cannot_be_reused(self):
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        original = compact._SubstringIndex._state; clones = []
        def refuse_clone(owner, length, link, copy_from, current):
            if copy_from is not None:
                clones.append(len(copy_from)); current.spend(current.remaining)
            return original(owner, length, link, copy_from, current)
        with patch.object(compact._SubstringIndex, '_state', refuse_clone), self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            index.append('abb', work, epoch=0)
        self.assertTrue(clones); self.assertTrue(index.failed); self.assertEqual(0, index.epoch)
        with self.assertRaisesRegex(ValueError, 'Incomplete substring index'):
            index.longest('abb', 0, 0, compact._EncodingWork(), epoch=0)

    def test_query_and_constructor_budget_errors_never_allocate_new_counter_or_return_partial(self):
        for remaining in (0, 1, 8, 12):
            work = compact._EncodingWork(); work.spend(work.remaining - remaining)
            with self.subTest(phase='constructor', remaining=remaining), self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact._SubstringIndex(work)
        index, _, _ = self.make(['a' * 96])
        for remaining in (0, 1, 9, 20, 60):
            work = compact._EncodingWork(); work.spend(work.remaining - remaining)
            with self.subTest(phase='query', remaining=remaining), \
                 patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    index.longest('a' * 96, 0, 16, work, epoch=1)
                self.assertGreaterEqual(work.remaining, 0)
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            index.append('abb', work, epoch=0)
            self.assertEqual(3, index.longest('abb', 0, 0, work, epoch=1))

    def test_positions_epochs_empty_leaves_and_prefix_normalization_boundaries(self):
        index, _, work = self.make(['', 'x' * 65])
        for length in (15, 16, 63, 64, 65):
            query = 'x' * length
            self.assertEqual(length if length >= 16 else 0, index.longest(query, 0, 16, work, epoch=2))
        self.assertEqual(0, index.longest('x', 1, 16, work, epoch=2))
        for offset, prefix, epoch in [(-1, 16, 2), (2, 16, 2), (False, 16, 2), (0, -1, 2), (0, True, 2), (0, 16, 1)]:
            with self.subTest(offset=offset, prefix=prefix, epoch=epoch), self.assertRaisesRegex(ValueError, 'position and epoch'):
                index.longest('x', offset, prefix, work, epoch=epoch)

    def test_state_edge_memory_is_action_local_with_integer_symbols_and_no_source_slices(self):
        observed = []; real_index = compact._SubstringIndex
        def created(current):
            value = real_index(current); observed.append(value); return value
        value = {'complete': ['same-prefix-1234' + 'a' * 64, 'same-prefix-1234' + 'b' * 64]}
        with patch.object(compact, '_SubstringIndex', side_effect=created):
            first = compact.dumps(value, schema=compact.ATOM_SCHEMA)
            second = compact.dumps(value, schema=compact.ATOM_SCHEMA)
        self.assertEqual(first, second); self.assertEqual(2, len(observed)); self.assertIsNot(observed[0], observed[1])
        for index in observed:
            self.assertFalse(hasattr(index, '__dict__'))
            self.assertEqual({'edges', 'links', 'lengths', 'last', 'epoch', 'failed'}, set(index.__slots__))
            for edges in index.edges:
                self.assertTrue(all(type(symbol) is int and -1 <= symbol <= 0x10ffff
                                    and type(target) is int and 0 <= target < len(index.edges) for symbol, target in edges.items()))

    def test_all_versions_full_canonical_bytes_and_cold_noncanonical_rejection_match_original(self):
        import random
        rng = random.Random(281313)
        values = [{'ordered': {'z': True, 'a': 1, 'b': 1.0}, 'types': [False, None, -0.0],
                   'data': ['abab' * 30, 'baba' * 30, '\0\u4e2d\U0001f642' * 24], 'literal': {'$mvg_ref': 'P7'}}]
        values.extend({'number': number, 'leaves': [''.join(rng.choice('ab\0\u4e2d') for _ in range(90)) for _ in range(4)]}
                      for number in range(6))
        for value in values:
            for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
                with self.subTest(number=value.get('number'), schema=schema):
                    with patch.object(compact, '_SubstringIndex', _OriginalScanIndex):
                        expected = compact.dumps(value, schema=schema)
                    body = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, body)
                    self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
                    with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                        compact.loads(body + ' ')
        with self.assertRaises(ValueError):
            compact.dumps({'invalid': '\ud800'}, schema=compact.ATOM_SCHEMA)

    def test_poison_on_unexpected_append_failure_preserves_original_exception(self):
        work = compact._EncodingWork(); index = compact._SubstringIndex(work)
        failure = MemoryError('fixed synthetic allocation interruption')
        with patch.object(compact._SubstringIndex, '_extend', side_effect=failure):
            with self.assertRaises(MemoryError) as caught:
                index.append('abc', work, epoch=0)
        self.assertIs(failure, caught.exception); self.assertTrue(index.failed); self.assertEqual(0, index.epoch)
        with self.assertRaisesRegex(ValueError, 'Incomplete substring index'):
            index.longest('abc', 0, 0, compact._EncodingWork(), epoch=0)
        with patch.object(compact._SubstringIndex, '_extend', side_effect=failure), \
             patch.object(compact, '_atom_literal', side_effect=AssertionError('partial body reached')):
            with self.assertRaises(MemoryError) as public_error:
                compact.dumps({'source': 'complete original source ' * 8}, schema=compact.ATOM_SCHEMA)
        self.assertIs(failure, public_error.exception)


class BulkSubstringQueryTests(unittest.TestCase):
    def test_all_positions_equal_original_scan_for_unicode_nul_ties_and_prefix_boundaries(self):
        leaves = ['', 'ab' * 40, 'baba' * 20, '\0\u4e2d\U0001f642' * 25, 'ab' * 40]
        index, oracle, work = SubstringAutomatonTests.make(leaves)
        for text in ['', 'a', 'ab' * 45 + 'z', '\0\u4e2d\U0001f642' * 30 + '\0', 'baba\0ab']:
            for prefix in (0, 1, 15, 16, 63, 64, 1000):
                with self.subTest(text=text, prefix=prefix):
                    expected = oracle.lengths_for_leaf(text, prefix, compact._EncodingWork(), epoch=len(leaves))
                    actual = index.lengths_for_leaf(text, prefix, work, epoch=len(leaves))
                    self.assertEqual(expected, actual)
                    self.assertEqual([index.longest(text, offset, prefix, work, epoch=len(leaves))
                                      for offset in range(len(text))], actual)

    def test_exhaustive_and_random_leaf_epochs_match_independent_all_position_oracle(self):
        from itertools import product
        import random
        words = [''] + [''.join(parts) for size in range(1, 4) for parts in product('ab', repeat=size)]
        queries = [''] + [''.join(parts) for size in range(1, 5) for parts in product('ab', repeat=size)]
        rng = random.Random(281414)
        corpora = [(first, second) for first in words for second in words]
        corpora.extend(tuple(''.join(rng.choice('ab\0\u4e2d\U0001f642') for _ in range(rng.randrange(12)))
                             for _ in range(4)) for _ in range(40))
        for leaves in corpora:
            index, oracle, work = SubstringAutomatonTests.make([])
            for epoch, leaf in enumerate(leaves):
                for text in queries + [leaf]:
                    for prefix in (0, 2, 16):
                        self.assertEqual(oracle.lengths_for_leaf(text, prefix, compact._EncodingWork(), epoch=epoch),
                                         index.lengths_for_leaf(text, prefix, work, epoch=epoch), (leaves, epoch, text, prefix))
                index.append(leaf, work, epoch=epoch)
                oracle.append(leaf, work, epoch=epoch)

    def test_every_greedy_candidate_equals_full_scan_without_current_leaf_or_separator_join(self):
        leaves = ['a' * 140 + 'q', 'a' * 120 + 'r', 'ab' * 60, 'a' * 96 + 'z',
                  'ab' * 40 + 'cd' * 20, '\u4e2d\U0001f642' * 60]
        index, oracle, work = SubstringAutomatonTests.make([])
        for epoch, text in enumerate(leaves):
            expected = oracle.lengths_for_leaf(text, 16, compact._EncodingWork(), epoch=epoch)
            actual = index.lengths_for_leaf(text, 16, work, epoch=epoch)
            self.assertEqual(expected, actual)
            candidates = []
            for lengths in (expected, actual):
                offset, found = 0, []
                while offset + 64 <= len(text):
                    best = lengths[offset]
                    if best >= 64:
                        found.append((offset, text[offset:offset + best])); offset += best
                    else:
                        offset += 1
                candidates.append(found)
            self.assertEqual(candidates[0], candidates[1])
            index.append(text, work, epoch=epoch); oracle.append(text, work, epoch=epoch)
        isolated, _, isolated_work = SubstringAutomatonTests.make(['ab', 'cd'])
        self.assertEqual([2, 1, 2, 1], isolated.lengths_for_leaf('abcd', 0, isolated_work, epoch=2))
        self.assertEqual([0, 0], isolated.lengths_for_leaf('zz', 0, isolated_work, epoch=2))
        self.assertEqual(2, isolated.epoch)

    def test_all_version_whole_canonical_and_cold_rejections_use_original_oracle_not_point_queries(self):
        value = {'ordered': {'z': True, 'a': 1, 'b': 1.0}, 'types': [False, None, -0.0],
                 'data': ['abab' * 40, 'baba' * 40, '\0\u4e2d\U0001f642' * 30, 'abab' * 40],
                 'literal': {'$mvg_ref': 'P7'}}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            with self.subTest(schema=schema):
                with patch.object(compact, '_SubstringIndex', _OriginalScanIndex):
                    expected = compact.dumps(value, schema=schema)
                with patch.object(compact._SubstringIndex, 'longest', side_effect=AssertionError('point-query restart')):
                    body = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, body)
                    self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
                    with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                        compact.loads(body + ' ')

    def test_periodic_near_miss_bulk_queries_fit_fixed_remainder_that_point_restarts_exhaust(self):
        index, _, _ = SubstringAutomatonTests.make(['ab' * 31 + 'ac'])
        text = 'ab' * 4096 + 'z'
        expected = [min(63 if offset % 2 == 0 else 62, len(text) - 1 - offset)
                    for offset in range(len(text))]
        expected = [length if length >= 16 else 0 for length in expected]
        work = compact._EncodingWork(); work.spend(work.remaining - 500000)
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            self.assertEqual(expected, index.lengths_for_leaf(text, 16, work, epoch=1))
        self.assertGreater(work.remaining, 0); self.assertLess(work.remaining, 500000)
        point_work = compact._EncodingWork(); point_work.spend(point_work.remaining - 500000)
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                for offset in range(len(text)):
                    index.longest(text, offset, 16, point_work, epoch=1)

    def test_budget_and_unexpected_interruptions_return_no_partial_table_or_graph_changes(self):
        index, _, _ = SubstringAutomatonTests.make(['a' * 96])
        before = deepcopy((index.edges, index.links, index.lengths, index.last, index.epoch, index.failed))
        for remaining in (0, 1, 9, 14, 110, 200, 1000):
            work = compact._EncodingWork(); work.spend(work.remaining - remaining)
            with self.subTest(remaining=remaining), patch.object(compact, '_EncodingWork', side_effect=AssertionError('new counter')):
                with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                    index.lengths_for_leaf('a' * 96, 16, work, epoch=1)
            self.assertEqual(before, (index.edges, index.links, index.lengths, index.last, index.epoch, index.failed))
        work = compact._EncodingWork(); spend = work.spend; calls = []
        failure = MemoryError('synthetic bulk interruption')
        def interrupted(amount=1):
            calls.append(amount)
            if len(calls) == 12:
                raise failure
            return spend(amount)
        with patch.object(work, 'spend', side_effect=interrupted), self.assertRaises(MemoryError) as caught:
            index.lengths_for_leaf('a' * 96, 16, work, epoch=1)
        self.assertIs(failure, caught.exception)
        self.assertEqual(before, (index.edges, index.links, index.lengths, index.last, index.epoch, index.failed))
        self.assertEqual([96 - offset for offset in range(81)] + [0] * 15,
                         index.lengths_for_leaf('a' * 96, 16, work, epoch=1))

    def test_leaf_tables_are_independent_and_invalid_or_poisoned_epochs_fail_closed(self):
        index, _, work = SubstringAutomatonTests.make(['aba', 'abb'])
        first = index.lengths_for_leaf('abab', 0, work, epoch=2)
        self.assertEqual([3, 2, 2, 1], first)
        first[0] = 999
        self.assertEqual([3, 2, 2, 1], index.lengths_for_leaf('abab', 0, work, epoch=2))
        self.assertEqual([], index.lengths_for_leaf('', 0, work, epoch=2))
        for text, prefix, epoch in [(b'ab', 0, 2), ('ab', False, 2), ('ab', -1, 2), ('ab', 0, False), ('ab', 0, 1)]:
            with self.subTest(text=text, prefix=prefix, epoch=epoch), self.assertRaisesRegex(ValueError, 'current leaf and epoch'):
                index.lengths_for_leaf(text, prefix, work, epoch=epoch)
        with patch.object(compact._SubstringIndex, '_extend', side_effect=MemoryError('append interruption')):
            with self.assertRaises(MemoryError):
                index.append('next', work, epoch=2)
        with self.assertRaisesRegex(ValueError, 'Incomplete substring index'):
            index.lengths_for_leaf('aba', 0, work, epoch=2)


class AtomicCanonicalProducerTests(unittest.TestCase):
    def test_genuine_all_version_producer_returns_identical_bytes_in_one_account(self):
        value = {'ordered': {'z': True, 'a': 1, 'b': 1.0}, 'types': [False, None, -0.0],
                 'source': 'Complete original source.\r\n' * 3, 'literal': {'$mvg_ref': 'R7'}}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            expected = compact.dumps(value, schema=schema)
            work = compact._EncodingWork()
            bounded, observed = compact._bounded_packet, []
            def completed(text, version, current=None):
                observed.append(current)
                return bounded(text, version, current)
            # Replacing the public symbol cannot supply a fake atomic producer.
            with self.subTest(schema=schema), \
                 patch.object(compact, '_bounded_packet', side_effect=completed), \
                 patch.object(compact, 'dumps', side_effect=AssertionError('external producer symbol used')), \
                 patch.object(compact, '_EncodingWork', side_effect=AssertionError('account reset')):
                body, restored = compact.produce_canonical_roundtrip(value, schema, work=work)
            self.assertEqual(expected, body)
            self.assertEqual(wire.text(value), wire.text(restored))
            self.assertEqual([work], observed)
            self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
            restored['ordered']['z'] = False
            self.assertIs(value['ordered']['z'], True)

    def test_external_body_approval_and_transferable_witness_have_no_api(self):
        value = {'original': True}
        for key in ('text', 'body', 'approved', 'producer', 'witness', 'skip_canonical'):
            with self.subTest(key=key), self.assertRaises(TypeError):
                compact.produce_canonical_roundtrip(value, **{key: True})
        body, _ = compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)
        with self.assertRaises(TypeError):
            compact.loads(body, witness={'approved': True})
        with self.assertRaises(ValueError):
            compact.produce_canonical_roundtrip(body)

    def test_snapshot_and_post_producer_refusals_never_reset_work_or_return_half_output(self):
        value = {'source': 'Complete material ' * 4}
        work = compact._EncodingWork()
        work.spend(work.remaining - 1)
        with patch.object(compact.json, 'loads', side_effect=AssertionError('snapshot copy reached')):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA, work=work)
        bounded, completed = compact._bounded_packet, []
        work = compact._EncodingWork()
        def exhaust(text, schema, current=None):
            result = bounded(text, schema, current)
            completed.append(current)
            current.spend(current.remaining - 1)
            return result
        with patch.object(compact, '_bounded_packet', side_effect=exhaust), \
             patch.object(compact, '_EncodingWork', side_effect=AssertionError('account reset')):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA, work=work)
        self.assertEqual([work], completed)
        self.assertLessEqual(work.remaining, 1)
        with patch.object(compact, '_bounded_packet', side_effect=ValueError('deliberate incomplete producer')), \
             patch.object(compact, '_decode_complete', side_effect=AssertionError('decode after incomplete producer')):
            with self.assertRaisesRegex(ValueError, 'incomplete producer'):
                compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)

    def test_private_snapshot_survives_caller_mutation_but_never_authorizes_changed_input(self):
        value = {'ordered': {'z': True, 'a': 1}, 'source': 'Original material'}
        original = deepcopy(value)
        expected = compact.dumps(value, schema=compact.ATOM_SCHEMA)
        parse, bounded, produced = compact.json.loads, compact._bounded_packet, []
        def copy_then_mutate(text):
            snapshot = parse(text)
            value['ordered']['z'] = 1  # Python equality alone would miss this.
            value['source'] = 'Unknown later material'
            return snapshot
        def observe(text, schema, current=None):
            result = bounded(text, schema, current)
            produced.append(result)
            return result
        with patch.object(compact.json, 'loads', side_effect=copy_then_mutate), \
             patch.object(compact, '_bounded_packet', side_effect=observe):
            with self.assertRaisesRegex(ValueError, 'snapshot/input ordered JSON changed'):
                compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)
        self.assertEqual([expected], produced)
        self.assertNotEqual(original['source'], value['source'])
        self.assertIs(type(value['ordered']['z']), int)

    def test_post_decode_type_order_and_signed_zero_changes_are_not_equal_witnesses(self):
        for kind in ('boolean_integer', 'integer_float', 'order', 'signed_zero'):
            value = {'z': True, 'a': 1, 'zero': -0.0}
            decode = compact._decode_complete
            def changed(*args, **kwargs):
                restored, schema = decode(*args, **kwargs)
                if kind == 'boolean_integer':
                    restored['z'] = 1
                elif kind == 'integer_float':
                    restored['a'] = 1.0
                elif kind == 'signed_zero':
                    restored['zero'] = 0.0
                else:
                    restored = dict(reversed(list(restored.items())))
                return restored, schema
            with self.subTest(kind=kind), patch.object(compact, '_decode_complete', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'snapshot/input ordered JSON changed'):
                    compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)

    def test_retained_snapshot_budget_precedes_copy_and_original_type_gates_remain(self):
        value = {'source': 'Original material'}
        metric = compact._json_preflight(value)
        with patch.object(compact, 'MAX_EXPANDED_BYTES', metric[0] + 1), \
             patch.object(compact.json, 'loads', side_effect=AssertionError('unreserved private copy')):
            with self.assertRaisesRegex(ValueError, 'atomic.snapshot.retained_cache'):
                compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)
        cyclic = {}; cyclic['cycle'] = cyclic
        for invalid in (cyclic, {'source': object()}, {'number': float('inf')}, {'text': '\ud800'}):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(ValueError):
                compact.produce_canonical_roundtrip(invalid, compact.ATOM_SCHEMA)

    def test_cold_all_versions_still_reencode_and_reject_noncanonical_after_warm_action(self):
        value = {'source': 'Original material', 'types': [False, 0, 1.0]}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            body, _ = compact.produce_canonical_roundtrip(value, schema)
            work = compact._EncodingWork()
            with self.subTest(schema=schema), patch.object(compact, 'dumps', wraps=compact.dumps) as canonical:
                with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                    compact.loads(body + ' ', work=work)
                self.assertEqual(1, canonical.call_count)
                self.assertIs(work, canonical.call_args.kwargs['work'])

    def test_complete_primitive_decoder_rejects_partial_unknown_and_damaged_producer_output(self):
        value = {'source': 'Original material'}
        bounded = compact._bounded_packet
        for kind in ('partial', 'unknown_field', 'digest'):
            def damaged(text, schema, current=None):
                body = bounded(text, schema, current)
                if kind == 'partial':
                    return body[:-1]
                if kind == 'unknown_field':
                    return "{'unknown':True," + body[1:]
                self.assertIn('Original material', body)
                return body.replace('Original material', 'Changed material')
            with self.subTest(kind=kind), patch.object(compact, '_bounded_packet', side_effect=damaged):
                with self.assertRaises(ValueError):
                    compact.produce_canonical_roundtrip(value, compact.ATOM_SCHEMA)


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



def _residual_reference(phrases, value):
    """Independent P/C data oracle for the residual pass, never a codec import."""
    resolved = []
    def restore(node):
        if type(node) is tuple and len(node) == 2 and node[0] == 'compact-text-phrase':
            if type(node[1]) is not int or not 0 <= node[1] < len(resolved):
                raise AssertionError('forward or invalid independent phrase')
            return resolved[node[1]]
        if type(node) is tuple and len(node) == 2 and node[0] == 'compact-text-concat':
            pieces = [restore(part) for part in node[1]]
            if any(type(part) is not str for part in pieces):
                raise AssertionError('non-text independent piece')
            return ''.join(pieces)
        if type(node) is list:
            return [restore(part) for part in node]
        if type(node) is dict:
            return {key: restore(part) for key, part in node.items()}
        if type(node) is tuple:
            return tuple(restore(part) for part in node)
        return node
    for phrase in phrases:
        resolved.append(restore(phrase))
    if len(set(resolved)) != len(resolved):
        raise AssertionError('duplicate independent phrase')
    return restore(value)


def _small_material_packet():
    """Closed delivery-only data, not a host review, receipt or qualification."""
    import _b_route_compensation_review_materials as materials
    source = {'schema_version': materials.OLD_SUBJECT, 'operation_id': 'unit-visible-delivery',
              'content': ['complete source ' * 16, False, 0, 0.0, -0.0, None]}
    digest = wire.codec.canonical_digest(source)
    material = {'schema_version': materials.MATERIALS, 'full_subject_digest': digest,
        'frames': [{'subject_digest': digest, 'operation_id': source['operation_id'],
                    'subject_schema': materials.OLD_SUBJECT, 'semantic_fields': source,
                    'previous_subject': None, 'files': []}], 'documents': []}
    roles = {'schema_version': materials.ROLES, 'full_subject_digest': digest, 'files': []}
    presentation = {'schema_version': materials.PRESENTATION, 'claim': materials.CLAIM,
        'full_subject_digest': digest, 'materials_digest': wire.codec.canonical_digest(material),
        'roles_digest': wire.codec.canonical_digest(roles), 'policy_identity': 'unit-unqualified-policy',
        'required_checks': ['complete delivery-only data']}
    return {'schema_version': materials.PACKET, 'presentation': presentation, 'roles': roles, 'materials': material}


class ResidualLiteralV4Tests(unittest.TestCase):
    def test_complete_digest_leaves_keep_h_atoms_when_an_ordinary_prefix_is_shared(self):
        zero = 'sha256:' + '0' * 64
        one = 'sha256:' + '0' * 63 + '1'
        # The old heuristic incorrectly compared 140 original characters with
        # a 72-character prefix definition although the original is H0/H1.
        digests = [zero, one]
        phrases, encoded = compact._residual_text([], digests, [], compact._EncodingWork())
        self.assertEqual([], phrases); self.assertIs(digests, encoded)
        self.assertEqual('[H0,H1]', compact._atom_literal(encoded))
        prefix = 'sha256:' + '0' * 63
        values = [zero, one, prefix + 'ordinary-left', prefix + 'ordinary-right']
        phrases, encoded = compact._residual_text([], values, [], compact._EncodingWork())
        self.assertIn(prefix + 'ordinary-', phrases)
        self.assertEqual(values, _residual_reference(phrases, encoded))
        self.assertEqual(values, compact._unpack_text(encoded, phrases))
        self.assertEqual(zero, encoded[0]); self.assertEqual(one, encoded[1])
        self.assertTrue(compact._atom_literal(encoded).startswith('[H0,H1,'))
        # Even when an exact ordinary 70-character prefix is selected, a
        # complete digest must not be replaced on the second pass either.
        values = [zero, one, prefix, prefix + '!']
        phrases, encoded = compact._residual_text([], values, [], compact._EncodingWork())
        self.assertIn(prefix, phrases)
        self.assertEqual(values, _residual_reference(phrases, encoded))
        self.assertEqual('[H0,H1]', compact._atom_literal(encoded[:2]))

    def test_old_three_version_canonical_bytes_match_exact_pre_v4_selector_oracle(self):
        values = [{}, {'typed': [False, True, 0, 1, 0.0, -0.0, None, 1.25e-5],
            '~r': {'$mvg_ref': 7}, '@': 'literal', 'unicode': '\0\n\u4e2d\U0001f642'},
            {'rows': [{'raw': 'visible original prefix ' * 8, 'n': index % 2} for index in range(8)]}]
        for value in values:
            for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
                with self.subTest(schema=schema), patch.object(compact, '_residual_text',
                        side_effect=AssertionError('new v4 pass reached old producer')):
                    expected = _pre_v4_dumps(value, schema=schema)
                    body = compact.dumps(value, schema=schema)
                    self.assertEqual(expected, body)
                    self.assertEqual(wire.text(value), wire.text(compact.loads(body)))
                    self.assertEqual(schema, compact._decode_complete(body, compact._EncodingWork())[1])
        self.assertEqual('newrouge.b-route-compact-literal.v3', compact.ATOM_SCHEMA)
        self.assertEqual('newrouge.b-route-compact-literal.v4', compact.RESIDUAL_SCHEMA)

    def test_exact_duplicate_prefix_containment_overlap_and_unicode_boundaries_restore_every_character(self):
        prefix = 'aB09+/==' * 24
        for values in ([prefix, prefix + 'tail'], [prefix, prefix, 'suffix'],
                       [prefix, prefix + '\0\u4e2d\U0001f642', '!' + prefix + prefix],
                       ['a' * 128 + 'b', 'a' * 128 + 'c', '!' + 'a' * 256],
                       ['z' * 63, 'z' * 63 + 'tail'], ['q' * 64, 'q' * 64 + 'tail']):
            with self.subTest(lengths=list(map(len, values))):
                original = deepcopy(values)
                phrases, encoded = compact._residual_text([], values, [], compact._EncodingWork())
                self.assertEqual(original, values)
                self.assertEqual(original, _residual_reference(phrases, encoded))
                self.assertEqual(original, compact._unpack_text(encoded, phrases))
                if values[0] == prefix:
                    self.assertIn(prefix, phrases)
                    self.assertLess(len(compact._atom_literal(encoded)), len(compact._atom_literal(values)))

    def test_existing_definition_indices_and_no_candidate_graphs_are_unchanged(self):
        old = 'old visible text ' * 8
        prefix = 'new exact prefix ' * 12
        phrases = [old]
        values = [('compact-text-phrase', 0), prefix, prefix + 'tail', ('compact-text-phrase', 0)]
        result, encoded = compact._residual_text(phrases, values, [old], compact._EncodingWork())
        self.assertEqual(old, result[0]); self.assertEqual([old], phrases)
        self.assertEqual([old, prefix, prefix + 'tail', old], _residual_reference(result, encoded))
        self.assertEqual(('compact-text-phrase', 0), encoded[0])
        for value in ([], ['unique leaf ' * 8], [old, old + 'suffix']):
            original = deepcopy(value)
            result, encoded = compact._residual_text(phrases, value, [old], compact._EncodingWork())
            self.assertEqual(original, _residual_reference(result, encoded))
            if value != [old, old + 'suffix']:
                self.assertIs(phrases, result); self.assertIs(value, encoded)

    def test_adjacent_prefix_candidates_match_independent_all_pairs_oracle(self):
        import random
        rng = random.Random(28419)
        matcher = compact._LiteralMatcher
        for _ in range(30):
            texts = [('a' * 64 + ''.join(rng.choice('abc') for _ in range(12))) for _ in range(9)]
            texts.extend([texts[0], texts[1] + 'end', 'different ' * 8])
            expected = set()
            counts = {}
            for text in texts:
                counts[text] = counts.get(text, 0) + 1
            for text, count in counts.items():
                if count >= 2 and len(text) >= 64:
                    expected.add(text)
            unique = list(counts)
            for index, left in enumerate(unique):
                for right in unique[index + 1:]:
                    length = 0
                    while length < min(len(left), len(right)) and left[length] == right[length]:
                        length += 1
                    if length >= 64:
                        expected.add(left[:length])
            seen = []
            def capture(choices, work):
                seen.append(list(choices))
                return matcher(choices, work)
            with patch.object(compact, '_LiteralMatcher', side_effect=capture):
                phrases, encoded = compact._residual_text([], texts, [], compact._EncodingWork())
            self.assertEqual([sorted(expected, key=lambda text: (-len(text), text))], seen)
            self.assertEqual(texts, _residual_reference(phrases, encoded))

    def test_one_original_account_exact_budget_and_memory_interruptions_return_no_partial_graph(self):
        prefix = 'prepaid original prefix ' * 12
        values = [prefix, prefix + 'end']
        full = compact._EncodingWork()
        expected = compact._residual_text([], values, [], full)
        spent = full.limit - full.remaining
        for reserve in (0, 23, spent - 1, spent):
            work = compact._EncodingWork(); work.spend(work.remaining - reserve)
            result = None
            with patch.object(compact, '_EncodingWork', side_effect=AssertionError('counter reset')):
                if reserve < spent:
                    with self.assertRaisesRegex(ValueError, 'charged=.*reserve=.*remaining='):
                        result = compact._residual_text([], values, [], work)
                    self.assertIsNone(result)
                else:
                    result = compact._residual_text([], values, [], work)
                    self.assertEqual(expected, result); self.assertEqual(0, work.remaining)
        with patch.object(compact, '_LiteralMatcher', side_effect=MemoryError('original primary')):
            with self.assertRaisesRegex(MemoryError, 'original primary'):
                compact._residual_text([], values, [], compact._EncodingWork())
        self.assertEqual([prefix, prefix + 'end'], values)

    def test_adversarial_repeated_prefixes_fail_closed_before_matcher_allocation(self):
        values = ['a' * 512 + chr(65 + index) for index in range(32)]
        work = compact._EncodingWork(); work.spend(work.remaining - 1000)
        with patch.object(compact, '_LiteralMatcher', side_effect=AssertionError('late allocation reached')):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact._residual_text([], values, [], work)
        self.assertLess(work.remaining, 1000)
        self.assertEqual(100000000, compact.MAX_ENCODING_WORK)

    def test_v4_complete_canonical_atomic_and_cold_preserve_types_order_and_signed_zero(self):
        value = {'first': {'~r': 0, '$mvg_ref': 3}, 'typed': [False, 0, 0.0, -0.0, True, None],
                 'texts': ['a' * 128, 'a' * 128 + 'tail', '\0\n\u4e2d\U0001f642']}
        original = wire.text(value)
        work = compact._EncodingWork()
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('atomic counter reset')):
            body, restored = compact.produce_canonical_roundtrip(value, schema=compact.RESIDUAL_SCHEMA, work=work)
        self.assertEqual(original, wire.text(restored)); self.assertEqual(original, wire.text(value))
        cold = compact._EncodingWork()
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('cold counter reset')):
            restored = compact.loads(body, work=cold)
        self.assertEqual(original, wire.text(restored))
        self.assertEqual(body, compact.dumps(restored, schema=compact.RESIDUAL_SCHEMA))
        self.assertEqual([bool, int, float, float, bool, type(None)], [type(x) for x in restored['typed']])
        self.assertEqual('-0.0', repr(restored['typed'][3]))
        for changed in (body + ' ', body[:-1], body[:-1] + ",'unknown':0}"):
            with self.subTest(changed=changed[-30:]), self.assertRaises(ValueError):
                compact.loads(changed)
        for value in ({'tuple': (1, 2)}, {'bad': float('inf')}, {'bad': '\ud800'}):
            with self.assertRaises(ValueError):
                compact.dumps(value, schema=compact.RESIDUAL_SCHEMA)

    def test_new_and_legacy_delivery_pairs_roundtrip_and_reject_mixed_header_decoder_and_body(self):
        import _b_route_compensation_review_materials as materials
        packet = _small_material_packet()
        prompt = materials.render('Review all complete unit materials.', packet)
        self.assertTrue(prompt.startswith(materials.DELIVERY + ' '))
        self.assertEqual(wire.text(packet), wire.text(materials.read_prompt(prompt)))
        legacy_body = compact.dumps(packet, schema=compact.ATOM_SCHEMA)
        legacy_header = materials.LEGACY_DELIVERY + ' Review all complete unit materials. ' + compact.instruction(compact.ATOM_SCHEMA)
        legacy_prompt = legacy_header + '\n' + legacy_body
        self.assertEqual(wire.text(packet), wire.text(materials.read_prompt(legacy_prompt)))
        current_header, current_body = prompt.split('\n', 1)
        changed = [current_header + '\n' + legacy_body, legacy_header + '\n' + current_body,
            current_header.replace(materials.DELIVERY, materials.LEGACY_DELIVERY, 1) + '\n' + current_body,
            current_header.replace(compact.RESIDUAL_SCHEMA, compact.ATOM_SCHEMA, 1) + '\n' + current_body,
            legacy_header.replace(compact.ATOM_SCHEMA, compact.RESIDUAL_SCHEMA, 1) + '\n' + legacy_body,
            prompt.replace(materials.DELIVERY, 'unknown.delivery', 1), prompt + ' ', legacy_prompt + ' ']
        for text in changed:
            with self.assertRaises(wire.codec.CodecError):
                materials.read_prompt(text)
        for text in (prompt, legacy_prompt):
            work = compact._EncodingWork(); work.spend(work.remaining - 1)
            with patch.object(compact, '_EncodingWork', side_effect=AssertionError('delivery reset')):
                with self.assertRaises(wire.codec.CodecError):
                    materials.read_prompt(text, work=work)

    def test_v4_original_primitive_usage_digest_and_canonical_refusals_are_not_skipped(self):
        value = {'leaf': 'original text'}
        for definitions, encoded in ([['duplicate', 'duplicate'], 'original text'],
                [[('compact-text-phrase', 0)], ('compact-text-phrase', 0)],
                [['unused complete text'], 'original text']):
            packet = {'schema_version': compact.RESIDUAL_SCHEMA, 'keysets': [], 'strings': [],
                'shared': [], 'phrases': definitions, 'value': {'leaf': encoded}, 'sha256': compact._digest(value)}
            with self.assertRaises(ValueError):
                compact.loads(compact._atom_literal(packet))
        body = compact.dumps(value, schema=compact.RESIDUAL_SCHEMA)
        for changed in (body.replace('H', 'H0', 1), body.replace(compact.RESIDUAL_SCHEMA, 'unknown.literal', 1)):
            with self.assertRaises(ValueError):
                compact.loads(changed)


def _pre_v4_dumps(value: dict, *, schema=None, work=None) -> str:
    """Return the deterministic packet literal for a complete JSON object.

    Reject non-JSON values, subclasses and cycles with ValueError. No caller
    containers are retained or modified. Runtime depth/integer limits still apply.
    """
    SCHEMA, CURRENT_SCHEMA, ATOM_SCHEMA = compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA
    def _schema(value):
        if value is None:
            return SCHEMA
        if type(value) is not str or value not in (SCHEMA, CURRENT_SCHEMA, ATOM_SCHEMA):
            raise ValueError("Unsupported compact literal schema")
        return value
    _work = compact._work
    _json_preflight = compact._json_preflight
    _copy_aliased = compact._copy_aliased
    _keysets = compact._keysets
    _pack = compact._pack
    _share = compact._share
    _pack_text = compact._pack_text
    _bounded_packet = compact._bounded_packet
    _atom_literal = compact._atom_literal
    _digest = compact._digest
    _literal = compact._literal
    schema = _schema(schema)
    work = _work(work)
    work.phase = "compact.encode"
    if type(value) is not dict:
        raise ValueError("The top-level value must be an object")
    try:
        _json_preflight(value, work)
        aliased = _copy_aliased(value, set(), work)
        tables = _keysets(aliased, work)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            tables = [keys for keys in tables if keys]
        work.spend(sum(len(keys) + 1 for keys in tables))
        indices = {tuple(keys): index for index, keys in enumerate(tables)}
        packed = _pack(aliased, indices, schema, work)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            strings, definitions, packed = _share(packed, work)
            if schema == ATOM_SCHEMA:
                phrases, encoded = _pack_text([strings, definitions, packed], work)
                strings, definitions, packed = encoded
                return _bounded_packet(_atom_literal({"schema_version": schema, "keysets": tables,
                    "strings": strings, "shared": definitions, "phrases": phrases,
                    "value": packed, "sha256": _digest(value, work)}, work), schema, work)
            render = _atom_literal if schema == ATOM_SCHEMA else _literal
            return _bounded_packet(render({"schema_version": schema, "keysets": tables,
                "strings": strings, "shared": definitions, "value": packed, "sha256": _digest(value, work)}, work), schema, work)
        return _bounded_packet(_literal({
            "schema_version": schema,
            "keysets": tables,
            "value": packed,
            "sha256": _digest(value, work),
        }, work), schema, work)
    except RecursionError as exc:
        raise ValueError("JSON data exceeds the runtime nesting limit") from exc
    except UnicodeError as exc:
        raise ValueError("JSON data must be encodable as strict UTF-8") from exc


def _owner_view_packet(count=1, *, role='semantic:original_operation', suffix='\n'):
    """Transport-only data: no native receipt/proof or business qualification."""
    import base64
    import _b_route_compensation_review_materials as materials
    import _planning_apply_journal as journal
    frames, documents, entries = [], [], []
    previous = None
    for index in range(count):
        operation_id = 'unit-json2-original-' + str(index)
        request = {'text': ('complete source ' * (8 + 12 * index)) + '\0\n\u4e2d\U0001f642',
                   'typed': [False, 0, 0.0, -0.0, None, 1.25e-5]}
        request_raw = (json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        frozen = {'request': request, 'targets': []}
        operation = {'schema_version': 'newrouge.b-route-adoption-operation.v1',
            'codec_version': wire.codec.CODEC_VERSION, 'operation_id': operation_id, 'state': 'reserved',
            'request_raw_base64': base64.b64encode(request_raw).decode('ascii'),
            'request_raw_digest': wire.codec.raw_digest(request_raw), 'request_digest': wire.codec.canonical_digest(request),
            'frozen': frozen, 'frozen_digest': wire.codec.canonical_digest(frozen)}
        subject = {'schema_version': materials.COMP_SUBJECT, 'producer': 'compensation',
                   'operation_id': 'unit-json2-current-' + str(index),
                   'request': {'compensates': {'operation_id': operation_id}}, 'original_operation': operation}
        identity = wire.codec.canonical_digest(subject)
        text = json.dumps(operation, ensure_ascii=False, indent=2, allow_nan=False) + suffix
        raw = text.encode('utf-8'); digest = wire.codec.raw_digest(raw)
        document = {'raw_digest': digest, 'raw_bytes': len(raw), 'text': text}
        path = journal._operation_ref(operation_id)
        use = {'role': role, 'owner': operation['schema_version'], 'ref': path, 'source': path, 'subject_digest': identity}
        entry = {'subject_digest': identity, 'path': path, 'raw_digest': digest, 'raw_bytes': len(raw),
                 'roles': [role], 'document_ref': digest, 'owner_uses': [use], 'semantic_frame_ref': None}
        frames.append({'subject_digest': identity, 'operation_id': subject['operation_id'],
            'subject_schema': materials.COMP_SUBJECT, 'semantic_fields': subject, 'previous_subject': previous, 'files': [entry]})
        documents.append(document); entries.append(entry); previous = identity
    material = {'schema_version': materials.MATERIALS, 'full_subject_digest': previous,
                'frames': frames, 'documents': sorted(documents, key=lambda row: row['raw_digest'])}
    roles = {'schema_version': materials.ROLES, 'full_subject_digest': previous,
             'files': sorted(deepcopy(entries), key=lambda row: (row['subject_digest'], row['path']))}
    presentation = {'schema_version': materials.PRESENTATION, 'claim': materials.CLAIM,
        'full_subject_digest': previous, 'materials_digest': wire.codec.canonical_digest(material),
        'roles_digest': wire.codec.canonical_digest(roles), 'policy_identity': 'unit-data-only-not-a-proof',
        'required_checks': ['complete transport data']}
    return {'schema_version': materials.PACKET, 'presentation': presentation, 'roles': roles, 'materials': material}


def _unit_transport(packet, work=None):
    import _b_route_compensation_review_materials as materials
    work = compact._EncodingWork() if work is None else work
    original, metric = materials._ordered(packet, work)
    digest = materials._ordered_digest(original, metric[5], work, (metric,), (metric[5],))
    return materials._transport_envelope(packet, digest, work, (metric,), (metric[5],))


class OwnerTransportEnvelopeTests(unittest.TestCase):
    def test_cold_executes_full_original_compact_d_and_e_then_rederives_owner_plan(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        prompt = materials.render('Read every original field.', packet)
        decoder, encoder, planner = compact._decode_complete, compact._ATOMIC_PRODUCER, materials._select_view
        calls = []
        def decode(text, work, *, retained=None):
            calls.append(('D', work, retained))
            return decoder(text, work, retained=retained)
        def encode(value, *, schema, work):
            calls.append(('E', work, schema))
            return encoder(value, schema=schema, work=work)
        def plan(value, work, metrics=(), buffers=()):
            calls.append(('plan', work, None))
            return planner(value, work, metrics, buffers)
        work = compact._EncodingWork()
        with patch.object(compact, '_decode_complete', side_effect=decode), \
             patch.object(compact, '_ATOMIC_PRODUCER', side_effect=encode), \
             patch.object(materials, '_select_view', side_effect=plan):
            restored = materials.read_prompt(prompt, work=work)
        self.assertEqual(['D', 'E', 'plan'], [row[0] for row in calls])
        self.assertTrue(all(row[1] is work for row in calls))
        self.assertGreater(calls[0][2][0], 0)
        self.assertEqual(compact.RESIDUAL_SCHEMA, calls[1][2])
        self.assertEqual(wire.text(packet), wire.text(restored))

    def test_ordered_packet_digest_and_signed_zero_cannot_use_sorted_semantic_digest_as_substitute(self):
        import _b_route_compensation_review_materials as materials
        base = _unit_transport(_owner_view_packet())
        changed = deepcopy(base)
        core = changed['packet_core']
        changed['packet_core'] = {key: core[key] for key in reversed(core)}
        # Sorted material/role identities stay the same, but whole Packet1 order
        # is part of the transport's original ordered identity.
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(changed, compact._EncodingWork())
        changed = deepcopy(base); i = changed['views'][0]['source'][2]
        operation = changed['packet_core']['materials']['frames'][i]['semantic_fields']['original_operation']
        operation['frozen']['request']['typed'][3] = 0.0
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(changed, compact._EncodingWork())

    def test_one_view_preserves_full_visible_source_packet_raw_text_types_and_order(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        before = wire.text(packet)
        envelope = _unit_transport(packet)
        self.assertEqual(1, len(envelope['views']))
        view = envelope['views'][0]
        i, j = view['source'][2], view['destination'][2]
        source = envelope['packet_core']['materials']['frames'][i]['semantic_fields']['original_operation']
        self.assertIs(packet['materials']['frames'][i]['semantic_fields']['original_operation'], source)
        self.assertEqual(json.dumps(source, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                         packet['materials']['documents'][j]['text'])
        self.assertEqual({'schema_version': materials.PLACEHOLDER, 'view': 0},
                         envelope['packet_core']['materials']['documents'][j]['text'])
        restored = materials._read_transport(envelope, compact._EncodingWork())
        self.assertEqual(before, wire.text(restored)); self.assertEqual(before, wire.text(packet))
        self.assertEqual(materials.PACKET, restored['schema_version'])
        prompt = materials.render('Read ALL original material data.', packet)
        self.assertTrue(prompt.startswith(materials.DELIVERY + ' '))
        self.assertEqual(before, wire.text(materials.read_prompt(prompt)))

    def test_zero_views_and_different_owner_role_preserve_original_literal_text(self):
        import _b_route_compensation_review_materials as materials
        for packet in (_small_material_packet(), _owner_view_packet(role='semantic:declared_source'),
                       _owner_view_packet(suffix='\r\n')):
            with self.subTest(subject=packet['materials']['full_subject_digest']):
                materials.validate(packet)
                envelope = _unit_transport(packet)
                self.assertEqual([], envelope['views'])
                self.assertIs(packet, envelope['packet_core'])
                self.assertEqual(wire.text(packet), wire.text(materials._read_transport(envelope, compact._EncodingWork())))

    def test_largest_exact_owned_document_and_stable_plan_are_derived_not_client_chosen(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet(2)
        envelope = _unit_transport(packet)
        self.assertEqual(1, envelope['views'][0]['source'][2])
        self.assertEqual(wire.text(envelope), wire.text(_unit_transport(packet)))
        # Removing all views while retaining the original valid packet is an
        # exact but noncanonical owner plan and must still be refused.
        wrong = deepcopy(envelope); wrong['packet_core'] = deepcopy(packet); wrong['views'] = []
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(wrong, compact._EncodingWork())
        # A lower-ranked exact owner view also cannot replace the unique plan.
        lower = next(row for row in materials._source_relations(packet, compact._EncodingWork()) if row[0] == 0)
        view = materials._view_row(lower[0], lower[1], compact._EncodingWork())
        wrong['views'] = [view]
        wrong['packet_core'] = materials._core_with_text(packet, lower[1],
            {'schema_version': materials.PLACEHOLDER, 'view': 0}, compact._EncodingWork())
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(wrong, compact._EncodingWork())

    def test_legacy_delivery_one_three_and_two_four_remain_real_canonical_reads(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        for marker, schema in ((materials.LEGACY_DELIVERY, compact.ATOM_SCHEMA),
                               (materials.V2_DELIVERY, compact.RESIDUAL_SCHEMA)):
            header = marker + ' Complete original legacy data. ' + compact.instruction(schema)
            prompt = header + '\n' + compact.dumps(packet, schema=schema)
            self.assertEqual(wire.text(packet), wire.text(materials.read_prompt(prompt)))
            with self.assertRaises(wire.codec.CodecError):
                materials.read_prompt(prompt + ' ')
        self.assertEqual('newrouge.b-route-compact-literal.v4', compact.RESIDUAL_SCHEMA)

    def test_new_marker_transport_and_compact_schema_are_never_silently_interchanged(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        current = materials.render('Read every field.', packet)
        header, body = current.split('\n', 1)
        previous = materials.V2_DELIVERY + ' Read every field. ' + compact.instruction(compact.RESIDUAL_SCHEMA)
        legacy = materials.LEGACY_DELIVERY + ' Read every field. ' + compact.instruction(compact.ATOM_SCHEMA)
        for changed in (previous + '\n' + body, legacy + '\n' + body,
                        header + '\n' + compact.dumps(packet, schema=compact.RESIDUAL_SCHEMA),
                        header.replace(materials.TRANSPORT_INSTRUCTION, 'unknown owner decoder', 1) + '\n' + body,
                        header.replace(compact.RESIDUAL_SCHEMA, compact.ATOM_SCHEMA, 1) + '\n' + body,
                        current.replace(materials.DELIVERY, 'unknown.delivery', 1), current + ' '):
            with self.assertRaises(wire.codec.CodecError):
                materials.read_prompt(changed)

    def test_unknown_missing_duplicate_version_kind_and_placeholder_fields_reject(self):
        import _b_route_compensation_review_materials as materials
        base = _unit_transport(_owner_view_packet())
        cases = []
        row = deepcopy(base); row['extra'] = None; cases.append(row)
        row = deepcopy(base); del row['views']; cases.append(row)
        row = deepcopy(base); row['schema_version'] = 'unknown.transport'; cases.append(row)
        row = deepcopy(base); row['views'].append(deepcopy(row['views'][0])); cases.append(row)
        row = deepcopy(base); row['views'][0]['extra'] = None; cases.append(row)
        row = deepcopy(base); row['views'][0]['kind'] = 'unknown.kind'; cases.append(row)
        for marker in ({'schema_version': materials.PLACEHOLDER, 'view': True},
                       {'schema_version': materials.PLACEHOLDER, 'view': 1},
                       {'schema_version': 'unknown.placeholder', 'view': 0},
                       {'view': 0, 'schema_version': materials.PLACEHOLDER}, None, ''):
            row = deepcopy(base); j = row['views'][0]['destination'][2]
            row['packet_core']['materials']['documents'][j]['text'] = marker; cases.append(row)
        for changed in cases:
            with self.assertRaises(wire.codec.CodecError):
                materials._read_transport(changed, compact._EncodingWork())

    def test_paths_boolean_indexes_overlap_cycle_missing_source_and_owner_tampering_reject(self):
        import _b_route_compensation_review_materials as materials
        base = _unit_transport(_owner_view_packet())
        cases = []
        for source in (['materials', 'frames', True, 'semantic_fields', 'original_operation'],
                       ['materials', 'frames', -1, 'semantic_fields', 'original_operation'],
                       ['materials', 'frames', 9999, 'semantic_fields', 'original_operation'],
                       ['materials', 'documents', 0, 'text'], ['..', 'external'],
                       ['materials', 'frames', 0, 'semantic_fields', 'missing']):
            row = deepcopy(base); row['views'][0]['source'] = source; cases.append(row)
        for destination in (['materials', 'documents', False, 'text'], ['materials', 'documents', -1, 'text'],
                            ['materials', 'documents', 9999, 'text'], ['materials', 'frames', 0, 'semantic_fields']):
            row = deepcopy(base); row['views'][0]['destination'] = destination; cases.append(row)
        row = deepcopy(base); i = row['views'][0]['source'][2]
        row['packet_core']['materials']['frames'][i]['files'][0]['roles'] = ['semantic:declared_source']; cases.append(row)
        row = deepcopy(base); i = row['views'][0]['source'][2]
        row['packet_core']['materials']['frames'][i]['files'][0]['owner_uses'][0]['owner'] = 'unverified'; cases.append(row)
        for changed in cases:
            with self.assertRaises(wire.codec.CodecError):
                materials._read_transport(changed, compact._EncodingWork())

    def test_original_packet_digest_raw_digest_type_order_and_current_input_are_not_waived(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        base = _unit_transport(packet)
        changed = deepcopy(base); changed['original_packet_ordered_digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(changed, compact._EncodingWork())
        changed = deepcopy(base); j = changed['views'][0]['destination'][2]
        changed['packet_core']['materials']['documents'][j]['raw_bytes'] = 1
        with self.assertRaises(wire.codec.CodecError):
            materials._read_transport(changed, compact._EncodingWork())
        producer = compact._ATOMIC_PRODUCER
        original = wire.text(packet)
        def mutate_caller(value, *, schema, work):
            body = producer(value, schema=schema, work=work)
            packet['presentation']['required_checks'].append('changed after snapshot')
            return body
        with patch.object(compact, '_ATOMIC_PRODUCER', side_effect=mutate_caller):
            with self.assertRaises(wire.codec.CodecError):
                materials.render('Read every field.', packet)
        self.assertNotEqual(original, wire.text(packet))

    def test_private_envelope_mutation_or_bad_producer_never_returns_partial_prompt(self):
        import _b_route_compensation_review_materials as materials
        producer = compact._ATOMIC_PRODUCER
        def mutate_private(value, *, schema, work):
            value['views'] = []
            return producer(value, schema=schema, work=work)
        for side_effect in (mutate_private, lambda *args, **kwargs: '[]', lambda *args, **kwargs: None):
            output = None
            with patch.object(compact, '_ATOMIC_PRODUCER', side_effect=side_effect):
                with self.assertRaises((wire.codec.CodecError, ValueError)):
                    output = materials.render('Read every field.', _owner_view_packet())
            self.assertIsNone(output)

    def test_formatter_preflight_uses_actual_graph_not_claimed_lengths_before_allocation(self):
        import _b_route_compensation_review_materials as materials
        source = {'x': [0, 0, 0, 0]}
        with patch.object(compact, 'MAX_EXPANDED_BYTES', 200), \
             patch.object(json, 'dumps', side_effect=AssertionError('formatter allocated')):
            with self.assertRaises(ValueError):
                materials._json2(source, compact._EncodingWork())
        # The live retained graph, not the tiny source alone, must be paid.
        with patch.object(compact, 'MAX_EXPANDED_BYTES', 1000), \
             patch.object(json, 'dumps', side_effect=AssertionError('live overflow allocated')):
            with self.assertRaises(ValueError):
                materials._json2({}, compact._EncodingWork(), metrics=((990, 1, 1),))

    def test_same_original_account_early_work_refusal_and_memoryerror_preserve_primary(self):
        import _b_route_compensation_review_materials as materials
        packet = _owner_view_packet()
        work = compact._EncodingWork()
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('warm account reset')):
            prompt = materials.render('Read every field.', packet, work=work)
        self.assertLess(work.remaining, work.limit)
        cold = compact._EncodingWork()
        with patch.object(compact, '_EncodingWork', side_effect=AssertionError('cold account reset')):
            restored = materials.read_prompt(prompt, work=cold)
        self.assertEqual(wire.text(packet), wire.text(restored))
        for limit in (0, 64):
            work = compact._EncodingWork(); work.spend(work.remaining - limit)
            with patch.object(json, 'dumps', side_effect=AssertionError('early allocation reached')):
                with self.assertRaises(wire.codec.CodecError):
                    materials.render('Read every field.', packet, work=work)
        with patch.object(compact, '_ATOMIC_PRODUCER', side_effect=MemoryError('original primary')):
            with self.assertRaisesRegex(MemoryError, 'original primary'):
                materials.render('Read every field.', packet)

    def test_unicode_control_float_json2_bytes_and_original_encoded_cap_remain_exact(self):
        import _b_route_compensation_review_materials as materials
        values = [{'a': ''.join(map(chr, range(32))) + '"\\\u007f\u0080\u07ff\u0800\uffff\U00010000\U0010ffff',
                   'typed': [False, 0, 0.0, -0.0, None, 1.25e-5]}, {'b': [], 'a': {}}]
        for value in values:
            text, raw, bound = materials._json2(value, compact._EncodingWork())
            expected = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
            self.assertEqual(expected, raw); self.assertEqual(expected.decode(), text)
            self.assertLessEqual(len(raw), bound)
        for value in ({'bad': '\ud800'}, {'bad': float('nan')}, {'bad': (1, 2)}):
            with self.assertRaises(ValueError):
                materials._json2(value, compact._EncodingWork())
        with self.assertRaises(wire.codec.CodecError) as caught:
            materials.render('A' * (compact.MAX_ENCODED_BYTES + 1), _small_material_packet())
        self.assertIn('Compact encoded bytes exceed ', caught.exception.diagnostic.actual)

if __name__ == "__main__":
    unittest.main()
