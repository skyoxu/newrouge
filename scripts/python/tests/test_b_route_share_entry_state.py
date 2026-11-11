"""Small share properties; the pinned historical differential remains in Task."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as codec


def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class ShareEntryStateTests(unittest.TestCase):
    def test_equal_distinct_and_repeated_identities_restore_exact_types_and_copies(self):
        first = {'flag': True, 'items': list(range(20))}
        typed = [{'flag': flag, 'items': list(range(20))}
                 for flag in (1, 1.0, False, -0.0, 0.0, None, 'None')]
        value = {'rows': [first, deepcopy(first), first] + typed * 2,
                 'ordered': [{'a': 1, 'b': 2}, {'b': 2, 'a': 1}] * 2}
        before = ordered(value)
        strings, definitions, encoded = codec._share(value, codec._EncodingWork())
        restored = codec._unshare(encoded, strings, definitions)
        self.assertEqual(before, ordered(restored))
        self.assertEqual(before, ordered(value))
        self.assertTrue(definitions)
        self.assertIs(type(restored['rows'][0]['flag']), bool)
        self.assertIs(type(restored['rows'][3]['flag']), int)
        self.assertIs(type(restored['rows'][4]['flag']), float)
        restored['rows'][0]['items'].append('changed')
        self.assertEqual(list(range(20)), restored['rows'][1]['items'])
        self.assertEqual(list(range(20)), first['items'])

    def test_overlapping_definitions_are_backward_only_and_fully_restore(self):
        leaf = {'items': list(range(28)), 'label': 'complete nested material'}
        parent = {'left': leaf, 'right': deepcopy(leaf), 'number': 9}
        value = {'parents': [parent, deepcopy(parent), parent], 'children': [leaf, deepcopy(leaf)]}
        strings, definitions, encoded = codec._share(value, codec._EncodingWork())
        self.assertGreaterEqual(len(definitions), 2)
        def check(node, limit):
            if type(node) is tuple and len(node) == 2 and node[0] is False:
                self.assertIs(type(node[1]), int)
                self.assertGreaterEqual(node[1], 0)
                self.assertLess(node[1], limit)
            elif type(node) is dict:
                for child in node.values():
                    check(child, limit)
            elif type(node) in (list, tuple):
                for child in node:
                    check(child, limit)
        for index, definition in enumerate(definitions):
            check(definition, index)
        check(encoded, len(definitions))
        self.assertEqual(ordered(value), ordered(codec._unshare(encoded, strings, definitions)))

    def test_same_account_refusal_never_resets_or_mutates_caller(self):
        value = {'rows': [{'items': list(range(24)), 'flag': False}] * 5}
        before = ordered(value)
        full = codec._EncodingWork()
        expected = codec._share(value, full)
        charged = full.limit - full.remaining
        for remaining in (0, 7, charged - 1, charged):
            account = codec._EncodingWork()
            account.spend(account.remaining - remaining)
            with patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
                if remaining < charged:
                    with self.assertRaises(ValueError):
                        codec._share(value, account)
                else:
                    self.assertEqual(expected, codec._share(value, account))
                    self.assertEqual(0, account.remaining)
            self.assertEqual(before, ordered(value))

    def test_public_v2_v3_v4_are_deterministic_and_type_order_exact(self):
        value = {'rows': [{'flag': False, 'items': list(range(16)), 'text': '\u4e2d\U0001f680\n\0'}] * 6,
                 'types': [None, False, True, 0, 0.0, -0.0],
                 'ordered': {'z': 3, 'a': 1}, 'reference': {'$mvg_ref': 7}}
        before = ordered(value)
        for schema in (codec.CURRENT_SCHEMA, codec.ATOM_SCHEMA, codec.RESIDUAL_SCHEMA):
            with self.subTest(schema=schema):
                text = codec.dumps(value, schema=schema)
                self.assertEqual(text, codec.dumps(value, schema=schema))
                self.assertEqual(before, ordered(codec.loads(text)))
                self.assertEqual(before, ordered(value))


if __name__ == '__main__':
    unittest.main(verbosity=2)
