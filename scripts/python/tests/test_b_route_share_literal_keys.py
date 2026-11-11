"""Postorder keys versus this module's retained uncached branch.

These are repository properties, not an independent historical implementation.
The pinned Root eight-case old-source oracle is retained separately in evidence.
Unit owner context comes from a real measured JSON shadow; it grants no producer,
native, or complete owner-action qualification.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as codec


def _shadow(node):
    if type(node) is tuple:
        return {'typed_tuple': [_shadow(child) for child in node]}
    if type(node) is list:
        return [_shadow(child) for child in node]
    if type(node) is dict:
        return {key: _shadow(child) for key, child in node.items()}
    return node


def _owner_work(value):
    account = codec._EncodingWork()
    account._residual_retained = codec._json_preflight(_shadow(value), account)[:3]
    return account


class ShareLiteralKeysTests(unittest.TestCase):
    def test_cached_fallback_exact_first_preorder_typed_alias_and_public_bytes(self):
        leaf = {'items': list(range(18)), 'flag': False}
        parent = [leaf, leaf, deepcopy(leaf)]
        value = {'parents': [parent, parent, deepcopy(parent)],
                 'typed': [(), (7,), (None, 4), (False, 4), [None, 4], True, 1, 1.0, -0.0, 0.0, None, 'None'],
                 'ordered': [{'a': 1, 'b': 2}, {'b': 2, 'a': 1}] * 2}
        before = codec._literal(value)
        instances, expected_order = [], []
        real_cache, real_children, real_walk = codec._ShareLiteralKeys, codec._children, codec._walk
        depth = [0]
        test = self
        class Observed(real_cache):
            def __init__(self, *args):
                super().__init__(*args)
                instances.append(self)
            def prepare(self, encoded):
                result = super().prepare(encoded)
                first = {}
                def visit(node):
                    if type(node) in (dict, list, tuple):
                        text = codec._literal(node)
                        first.setdefault(text, None)
                        test.assertIs(self.by_id[id(node)], self.counts[text])
                        test.assertIs(self.by_id[id(node)][0], next(key for key in self.counts if key == text))
                        for child in node.values() if type(node) is dict else node:
                            visit(child)
                visit(encoded)
                expected_order[:] = first
                return result
        def children(node, transform, work=None):
            # Preserve the already typed aliases at this unit-only boundary.
            # Both branches use the same seam; the public check below is unpatched.
            return node if transform.__name__ == 'encode_strings' else real_children(node, transform, work)
        def walked(node, visit, work=None):
            depth[0] += 1
            try:
                return real_walk(node, visit, work)
            finally:
                depth[0] -= 1
                if depth[0] == 0 and visit.__name__ == 'count_cached':
                    test.assertEqual(expected_order, [entry[0] for entry in instances[-1].order])
        with patch.object(codec, '_children', children):
            expected = codec._share(value, codec._EncodingWork())  # No context: preserved uncached branch.
            with patch.object(codec, '_ShareLiteralKeys', Observed), patch.object(codec, '_walk', walked):
                actual = codec._share(value, _owner_work(value))
        self.assertEqual(codec._literal(expected), codec._literal(actual))
        self.assertEqual(before, codec._literal(value))
        self.assertIs(value['parents'][0], value['parents'][1])
        self.assertIs(value['parents'][0][0], value['parents'][0][1])
        self.assertTrue(instances)
        self.assertTrue(all(c.closed and not c.fallback and c.builds > 0 for c in instances))
        public = {'rows': [leaf, deepcopy(leaf), leaf], 'ordered': value['ordered'], 'text': '\u4e2d\U0001f680\n\0'}
        expected = codec.dumps(public, schema=codec.RESIDUAL_SCHEMA)
        actual = codec.dumps(public, schema=codec.RESIDUAL_SCHEMA, work=_owner_work(public))
        self.assertEqual(expected, actual)
        self.assertEqual(json.dumps(public), json.dumps(codec.loads(actual)))

    def test_owner_and_both_actual_floors_add_and_capacity_falls_back_before_allocation(self):
        value = {'text': 'x' * 128, 'items': list(range(12))}
        account = _owner_work(value)
        retained = account._residual_retained
        cache = codec._ShareLiteralKeys(account, value, value, {}, {})
        self.assertIsNotNone(cache)
        self.assertEqual(retained[0] + sum(row[0] for row in cache.input_floor), cache.base[0])
        self.assertEqual(retained[1] + sum(row[1] for row in cache.input_floor), cache.base[1])
        self.assertEqual(cache.input_floor[0], cache.input_floor[1])  # Same graph counted twice, no discount.
        self.assertGreater(cache.base[0], retained[0])
        cache.close()
        self.assertEqual(({}, {}, []), (cache.counts, cache.by_id, cache.order))
        account = codec._EncodingWork()
        account._residual_retained = (codec.MAX_EXPANDED_BYTES - codec._ShareLiteralKeys.FIXED_BYTES + 1, 1, 1)
        with patch.object(codec._ShareLiteralKeys, '__init__', side_effect=AssertionError('allocated after capacity decline')):
            declined = codec._share(value, account)
        self.assertEqual(codec._literal(codec._share(value)), codec._literal(declined))
        instances, real = [], codec._ShareLiteralKeys
        class Observed(real):
            def __init__(self, *args):
                super().__init__(*args)
                instances.append(self)
        account = codec._EncodingWork()
        account._residual_retained = (codec.MAX_EXPANDED_BYTES - 5000, 1, 1)  # Explicit negative capacity seam.
        with patch.object(codec, '_ShareLiteralKeys', Observed):
            actual = codec._share({}, account)
        self.assertEqual(codec._share({}), actual)
        self.assertEqual(1, len(instances))
        self.assertTrue(instances[0].fallback and instances[0].closed)
        self.assertEqual(1, instances[0].capacity_misses)
        self.assertIsNone(instances[0].capacity_error.__traceback__)
        self.assertEqual(({}, {}, []), (instances[0].counts, instances[0].by_id, instances[0].order))

    def test_work_refusal_keeps_primary_exception_closes_and_never_retries_or_resets(self):
        value = {'items': list(range(16))}
        before = codec._literal(value)
        account = _owner_work(value)
        instances, real, real_walk = [], codec._ShareLiteralKeys, codec._walk
        class Refused(real):
            def __init__(self, *args):
                super().__init__(*args)
                instances.append(self)
            def prepare(self, encoded):
                self.work.spend(self.work.remaining + 1)  # Original real spend raises, no fabricated refusal.
        def walked(node, visit, work=None):
            if visit.__name__ == 'count_container':
                raise AssertionError('work refusal retried uncached')
            return real_walk(node, visit, work)
        remaining = account.remaining
        with patch.object(codec, '_ShareLiteralKeys', Refused), patch.object(codec, '_walk', walked), \
                patch.object(codec, '_EncodingWork', side_effect=AssertionError('work account reset')):
            with self.assertRaises(ValueError):
                codec._share(value, account)
        self.assertLess(account.remaining, remaining)
        self.assertEqual(1, len(instances))
        self.assertTrue(instances[0].closed)
        self.assertFalse(instances[0].fallback)
        self.assertEqual(0, instances[0].capacity_misses)
        self.assertEqual(({}, {}, []), (instances[0].counts, instances[0].by_id, instances[0].order))
        self.assertEqual(before, codec._literal(value))

    def test_primary_MemoryError_is_not_capacity_retry_and_pending_buffers_are_cleared(self):
        value = {'items': list(range(16))}
        before = codec._literal(value)
        account = _owner_work(value)
        instances, real, real_walk = [], codec._ShareLiteralKeys, codec._walk
        primary = MemoryError('postorder join primary')
        calls = []
        class Observed(real):
            def __init__(self, *args):
                super().__init__(*args)
                instances.append(self)
        def broken_join(parts, work):
            calls.append(work)
            raise primary
        def walked(node, visit, work=None):
            if visit.__name__ == 'count_container':
                raise AssertionError('MemoryError retried uncached')
            return real_walk(node, visit, work)
        with patch.object(codec, '_ShareLiteralKeys', Observed), patch.object(codec, '_join', broken_join), \
                patch.object(codec, '_walk', walked), patch.object(codec, '_EncodingWork', side_effect=AssertionError('work reset')):
            with self.assertRaises(MemoryError) as raised:
                codec._share(value, account)
        self.assertIs(primary, raised.exception)
        self.assertEqual([account], calls)
        self.assertEqual(1, len(instances))
        cache = instances[0]
        self.assertTrue(cache.closed)
        self.assertFalse(cache.fallback)
        self.assertEqual((0, 0, 0), (cache.capacity_misses, cache.pending_size, cache.pending_nodes))
        self.assertEqual(({}, {}, []), (cache.counts, cache.by_id, cache.order))
        self.assertEqual(before, codec._literal(value))


if __name__ == '__main__':
    unittest.main(verbosity=2)
