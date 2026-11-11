"""Structural share owner regression controls; no historical source dependency."""
import builtins
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as codec


def _work():
    account = codec._EncodingWork()
    # Unit owner context only. The owner still adds both actual input floors.
    account._residual_retained = codec._json_preflight({}, account)[:3]
    return account


def _cache(value):
    return codec._ShareLiteralKeys(_work(), value, value, {}, {})


def _nodes(value):
    if type(value) in (dict, list, tuple):
        yield value
        for child in value.values() if type(value) is dict else value:
            yield from _nodes(child)


class StructuralShareTests(unittest.TestCase):
    def test_typed_literal_groups_lengths_and_canonical_child_references(self):
        leaf = {'text': '\0\u4e2d\U0001f680\\\'"', 'items': [False, 1, -0.0]}
        value = [leaf, leaf, deepcopy(leaf), {'a': 1, 'b': 2}, {'b': 2, 'a': 1},
                 [], (), (7,), (None, 4), (False, 4), [None, 4], [True], [1], [1.0],
                 [-0.0], [0.0], [None], ['None'], ['x' * 19], ['x' * 20]]
        cache = _cache(value)
        try:
            cache.prepare(value)
            nodes = list(_nodes(value))
            literals = [codec._literal(node) for node in nodes]
            keys = [cache.by_id[id(node)][0] for node in nodes]
            self.assertEqual(len(set(literals)), len(cache.counts))
            for index, key in enumerate(keys):
                self.assertEqual(len(literals[index]), len(key))
                for other, text in zip(keys, literals):
                    self.assertEqual(literals[index] == text, key == other)
                    if literals[index] == text:
                        self.assertIs(key, other)
                for offset in range(0, len(key.parts), 2):
                    if key.parts[offset] == 5:
                        child = key.parts[offset + 1]
                        self.assertIs(child, cache.counts[child][0])
            self.assertEqual((23, 24), tuple(len(cache.by_id[id(node)][0]) for node in value[-2:]))
            original = leaf['text']
            self.assertTrue(any(part is original for part in cache.by_id[id(leaf)][0].parts))
        finally:
            cache.close()

    def test_collision_uses_typed_equality_signed_zero_and_charged_hash_comparison(self):
        value = [[True], [1], [1.0], [-0.0, 0.0], [0.0, -0.0]]
        cache = _cache(value)
        def collision(key):
            key._work.spend(2)
            return 0
        try:
            with patch.object(codec._ShareStructuralKey, '__hash__', collision):
                cache.prepare(value)
                self.assertEqual(len({codec._literal(node) for node in _nodes(value)}), len(cache.counts))
                left, right = (cache.by_id[id(node)][0] for node in value[-2:])
                self.assertEqual(len(left), len(right))
                with patch.object(codec.math, 'copysign', wraps=codec.math.copysign) as sign:
                    self.assertNotEqual(left, right)
                    self.assertEqual(2, sign.call_count)
                before = cache.work.remaining
                self.assertEqual(left, left)
                self.assertLess(cache.work.remaining, before)
                cache.work.spend(cache.work.remaining)
                with self.assertRaises(ValueError):
                    left == right
                with self.assertRaises(ValueError):
                    hash(left)
        finally:
            cache.close()  # Cleanup cannot spend after refusal.
        self.assertEqual(({}, {}, [], 0, 0),
                         (cache.counts, cache.by_id, cache.order, cache.pending_size, cache.pending_nodes))

    def test_key_decline_restores_acquired_pending_before_abandon_or_close(self):
        value = []
        for dimension in ('bytes', 'nodes'):
            cache = _cache(value)
            cache._reserve(256, 4)
            policy, limit = (('MAX_EXPANDED_BYTES', cache.base[0] + cache.size + 256 + 1024 + 512 - 1)
                             if dimension == 'bytes' else
                             ('MAX_EXPANDED_NODES', cache.base[1] + cache.nodes + 4 + 32 + 16 - 1))
            try:
                with self.subTest(dimension=dimension), patch.object(codec, policy, limit):
                    with self.assertRaises(codec._ShareKeyCapacity) as raised:
                        cache._build(value)
                self.assertIs(cache.capacity_error, raised.exception)
                self.assertEqual((256, 4), (cache.pending_size, cache.pending_nodes))
                self.assertEqual(({}, {}), (cache.counts, cache.by_id))
                self.assertFalse(cache.closed or cache.fallback)
                cache.capacity_error.__traceback__ = None
            finally:
                cache._release(256, 4)
                cache.close()

    def test_insert_collision_accounts_for_new_record_after_lookup_miss(self):
        first, second = [], ()
        real_eq = codec._ShareStructuralKey.__eq__
        for short_by in (1, 0):
            cache = _cache([first, second])
            hashes, comparisons = [], []
            def collision(key):
                key._work.spend(2)
                hashes.append(id(key))
                return 0
            def compare(left, right):
                comparisons.append((cache.pending_size, cache.pending_nodes))
                return real_eq(left, right)
            with self.subTest(short_by=short_by), \
                    patch.object(codec._ShareStructuralKey, '__hash__', collision), \
                    patch.object(codec._ShareStructuralKey, '__eq__', compare):
                cache._build(first)
                hashes.clear()
                comparisons.clear()
                retained = cache.size, cache.nodes
                cache._reserve(128, 2)
                limit = cache.base[0] + cache.size + 128 + 1024 + 512 + 384 + 1024 - short_by
                try:
                    with patch.object(codec, 'MAX_EXPANDED_BYTES', limit):
                        if short_by:
                            with self.assertRaises(codec._ShareKeyCapacity):
                                cache._build(second)
                            cache.capacity_error.__traceback__ = None
                        else:
                            cache._build(second)
                    self.assertEqual([(128 + 1024 + 512, 2 + 32 + 16),
                                      (128 + 1024 + 512 + 384, 2 + 32 + 16 + 6)], comparisons)
                    self.assertEqual(2, len(hashes))
                    self.assertEqual(hashes[0], hashes[1])
                    self.assertEqual((128, 2), (cache.pending_size, cache.pending_nodes))
                    self.assertEqual(1 if short_by else 2, len(cache.counts))
                    if short_by:
                        self.assertEqual(retained, (cache.size, cache.nodes))
                        self.assertNotIn(id(second), cache.by_id)
                    else:
                        self.assertEqual((retained[0] + 512 + 384 + 256, retained[1] + 16 + 6 + 4),
                                         (cache.size, cache.nodes))
                finally:
                    cache._release(128, 2)
                    cache.close()

    def test_string_length_formula_fees_no_repr_and_no_publication_on_work_refusal(self):
        # Private scalar seams do not relax the public strict-UTF-8 JSON gate.
        for raw in ('', 'plain', "'", '"', "'''\"", "'\"\"\"", '\0\n\r\t\\',
                    '\u4e2d\U0001f680\u200b\U000e0001', '\ud800\udfff'):
            cache, parts = _cache([raw]), []
            meter = codec._EncodingWork()
            bound = codec._repr_size(raw, meter)
            before = cache.work.remaining
            try:
                with self.subTest(raw=builtins.repr(raw)), \
                        patch.object(codec, 'repr', side_effect=AssertionError('string repr allocated'), create=True), \
                        patch.object(cache, '_reserve', side_effect=AssertionError('string repr reserved')):
                    length = cache._atom(parts, raw)
                self.assertEqual(len(builtins.repr(raw)), length)
                self.assertEqual(bound - (raw.count('"') if raw.count('"') else raw.count("'")), length)
                self.assertIs(raw, parts[1])
                self.assertEqual(32 + meter.limit - meter.remaining + 2 * len(raw) + 12 + bound,
                                 before - cache.work.remaining)
                self.assertEqual((0, 0), (cache.pending_size, cache.pending_nodes))
            finally:
                cache.close()
        raw = "'''\""
        for stage in ('quote_scan', 'bound'):
            cache, parts = _cache([raw]), []
            meter = codec._EncodingWork()
            bound = codec._repr_size(raw, meter)
            quote = 2 * len(raw) + 12
            charge = quote if stage == 'quote_scan' else bound
            cache.work.remaining = 32 + meter.limit - meter.remaining + charge - 1
            if stage == 'bound':
                cache.work.remaining += quote
            try:
                with self.subTest(stage=stage), \
                        patch.object(codec, 'repr', side_effect=AssertionError('string repr allocated'), create=True):
                    with self.assertRaises(ValueError):
                        cache._atom(parts, raw)
                self.assertEqual([], parts)
                self.assertEqual(charge - 1, cache.work.remaining)
            finally:
                cache.close()

    def test_removed_string_temporary_preserves_actual_structure_room_and_nonstr_refusals(self):
        raw = 'visible material ' * 1024
        cache = _cache([raw])
        limit = cache.base[0] + cache.size + 1152 + 576 + 384 + 256
        try:
            with patch.object(codec, 'MAX_EXPANDED_BYTES', limit), \
                    patch.object(codec, 'repr', side_effect=AssertionError('string repr allocated'), create=True):
                key = cache._build([raw])
                self.assertIs(raw, key.parts[1])
                self.assertEqual(len(builtins.repr(raw)) + 2, len(key))
            self.assertLessEqual(cache.base[0] + cache.peak_size, limit)
        finally:
            cache.close()
        for failure in ('room', 'memory'):
            cache, parts = _cache([7]), []
            primary = MemoryError('nonstring repr primary')
            try:
                with self.subTest(failure=failure):
                    if failure == 'room':
                        limit = cache.base[0] + cache.size + 6 * codec._scalar_bytes(7) + 128 - 1
                        with patch.object(codec, 'MAX_EXPANDED_BYTES', limit), \
                                patch.object(codec, 'repr', side_effect=AssertionError('repr before room'), create=True):
                            with self.assertRaises(codec._ShareKeyCapacity):
                                cache._atom(parts, 7)
                        cache.capacity_error.__traceback__ = None
                    else:
                        with patch.object(codec, 'repr', side_effect=primary, create=True):
                            with self.assertRaises(MemoryError) as raised:
                                cache._build([7])
                            self.assertIs(primary, raised.exception)
                self.assertEqual([], parts)
                self.assertEqual((0, 0), (cache.pending_size, cache.pending_nodes))
                self.assertFalse(cache.fallback)
            finally:
                cache.close()

    def test_capacity_restart_clears_structural_maps_and_preserves_marker_interning(self):
        raw = 'complete-original-string-' * 3
        value = [raw, (' ' + raw)[1:], [1, 2, 3], [1, 2, 3]]
        with patch.object(codec, '_ShareLiteralKeys', return_value=None):
            expected = codec._share(value, _work())
        observed, real, test = [], codec._ShareLiteralKeys, self
        class Capacity(real):
            def __init__(self, *args):
                super().__init__(*args)
                observed.append(self)
            def prepare(self, encoded):
                test.assertIs(encoded[0], encoded[1])
                test.assertEqual((None, 0), encoded[0])
                self._build(encoded[2])
                self.by_id.pop(id(encoded[2]))  # Completed counts-only orphan.
                self._room(codec.MAX_EXPANDED_BYTES, 1)
            def abandon(self, error):
                test.assertEqual((0, 0), (self.pending_size, self.pending_nodes))
                super().abandon(error)
                test.assertEqual(({}, {}, []), (self.counts, self.by_id, self.order))
        with patch.object(codec, '_ShareLiteralKeys', Capacity):
            actual = codec._share(value, _work())
        self.assertEqual(codec._literal(expected), codec._literal(actual))
        self.assertTrue(observed[0].fallback and observed[0].closed)

    def test_all_four_canonical_bodies_match_uncached_branch_and_cold_rejects(self):
        value = {'rows': [{'text': 'complete original material ' * 4, 'items': [False, 1, -0.0]}] * 3,
                 'ordered': [{'a': 1, 'b': 2}, {'b': 2, 'a': 1}],
                 'typed': [True, 1, 1.0, -0.0, 0.0, None, 'None'], 'text': '\0\u4e2d\U0001f680'}
        observed, real = [], codec._ShareLiteralKeys
        class Observed(real):
            def __init__(self, *args):
                super().__init__(*args)
                observed.append(self)
        for schema in (codec.SCHEMA, codec.CURRENT_SCHEMA, codec.ATOM_SCHEMA, codec.RESIDUAL_SCHEMA):
            with self.subTest(schema=schema):
                expected_work, actual_work = _work(), _work()
                with patch.object(codec, '_ShareLiteralKeys', return_value=None), \
                        patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
                    expected = codec.dumps(value, schema=schema, work=expected_work)
                with patch.object(codec, '_ShareLiteralKeys', Observed), \
                        patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
                    actual = codec.dumps(value, schema=schema, work=actual_work)
                self.assertEqual(expected, actual)
                cold = codec._EncodingWork()
                with patch.object(codec, '_EncodingWork', side_effect=AssertionError('cold account reset')):
                    restored = codec.loads(actual, work=cold)
                self.assertEqual(json.dumps(value), json.dumps(restored))
                with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                    codec.loads(actual + ' ')
        self.assertEqual(3, len(observed))  # V1 does not use subtree sharing.
        self.assertTrue(all(cache.closed and not cache.fallback and cache.builds for cache in observed))


if __name__ == '__main__':
    unittest.main(verbosity=2)
