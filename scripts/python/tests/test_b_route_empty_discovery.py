"""Repository properties for empty/short substring discovery elimination.

The independent old-source differential remains in Root evidence; this module
imports only the installed codec and contains no Task source/baseline dependency.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as codec


def owner_unit_work(value):
    work = codec._EncodingWork()
    # A measured unit graph, never a caller approval or production owner claim.
    work._residual_retained = codec._json_preflight(value, work)[:3]
    return work


class EmptyDiscoveryTests(unittest.TestCase):
    def test_public_v3_v4_boundaries_unicode_types_and_order_roundtrip(self):
        value = {'texts': ['x' * 63, 'x' * 64, 'x' * 65, 'x' * 65, '',
                           '\u4e2d' * 63, '\u4e2d' * 64, '\u4e2d' * 65, '\u4e2d' * 65, '\U0001f680' * 65],
                 'ordered': [{'a': 1, 'b': 2}, {'b': 2, 'a': 1}],
                 'typed': [None, True, False, 1, 1.0, -0.0, 0.0, 'None']}
        before = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        for schema in (codec.ATOM_SCHEMA, codec.RESIDUAL_SCHEMA):
            with self.subTest(schema=schema):
                generic = codec.dumps(value, schema=schema)
                owned = codec.dumps(value, schema=schema, work=owner_unit_work(value))
                self.assertEqual(generic.encode('utf8'), owned.encode('utf8'))
                self.assertEqual(before, json.dumps(codec.loads(owned), ensure_ascii=False, separators=(',', ':')))
                self.assertEqual(before, json.dumps(value, ensure_ascii=False, separators=(',', ':')))

    def test_first_complete_candidate_retained_and_only_required_epochs_queried(self):
        a, b, c = 'A' * 65, 'B' * 64, 'C' * 63
        value = [a, a, b, b, c, '']
        events = []
        real = codec._SubstringIndex
        class Observed(real):
            def lengths_for_leaf(self, text, prefix_size, work, *, epoch):
                events.append(('query', text, epoch))
                return super().lengths_for_leaf(text, prefix_size, work, epoch=epoch)
            def append(self, text, work, *, epoch):
                events.append(('append', text, epoch))
                return super().append(text, work, epoch=epoch)
        with patch.object(codec, '_SubstringIndex', Observed):
            phrases, encoded = codec._pack_text(value, owner_unit_work(value), schema=codec.ATOM_SCHEMA)
        self.assertIn(a, phrases)
        self.assertEqual([('append', a, 0), ('query', b, 1), ('append', b, 1)], events)
        self.assertEqual(value, codec._unpack_text(encoded, phrases))
        for short in ([], [''], ['x' * 63] * 2):
            events.clear()
            with patch.object(codec, '_SubstringIndex', Observed):
                phrases, encoded = codec._pack_text(short, owner_unit_work(short), schema=codec.ATOM_SCHEMA)
            self.assertEqual([], events)
            self.assertEqual(short, codec._unpack_text(encoded, phrases))

    def test_every_new_guard_debits_the_original_account_and_input_is_unchanged(self):
        value = ['A' * 65, 'B' * 64, 'C' * 63, '']
        before = codec._literal(value)
        work = owner_unit_work(value)
        original_spend = work.spend
        charges = []
        def observed(*args, **kwargs):
            remaining = work.remaining
            result = original_spend(*args, **kwargs)
            if kwargs.get('phase', '').startswith('compact.text.discovery.'):
                charges.append((kwargs['phase'], args[0], remaining - work.remaining))
            return result
        with patch.object(work, 'spend', observed):
            codec._pack_text(value, work)
        self.assertEqual(3, sum(phase.endswith('length_guard') for phase, _, _ in charges))
        self.assertEqual(2, sum(phase.endswith('first_guard') for phase, _, _ in charges))
        self.assertTrue(all(amount == delta == 32 for _, amount, delta in charges))
        self.assertEqual(160, sum(delta for _, _, delta in charges))
        self.assertEqual(before, codec._literal(value))

    def test_primary_work_refusal_and_MemoryError_are_never_retried_or_reset(self):
        value = ['A' * 65, 'B' * 64, 'C' * 63]
        before = codec._literal(value)
        full = owner_unit_work(value)
        start = full.remaining
        expected = codec._pack_text(value, full)
        charged = start - full.remaining
        for available in (charged - 1, charged):
            work = owner_unit_work(value)
            work.spend(work.remaining - available)
            with patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
                if available < charged:
                    with self.assertRaisesRegex(ValueError, 'Compact encoding work exceeds'):
                        codec._pack_text(value, work)
                else:
                    self.assertEqual(expected, codec._pack_text(value, work))
                    self.assertEqual(0, work.remaining)
        primary = MemoryError('required long-leaf query')
        events = []
        real = codec._SubstringIndex
        class Refused(real):
            def lengths_for_leaf(self, text, prefix_size, work, *, epoch):
                events.append(('query', text, epoch))
                raise primary
            def append(self, text, work, *, epoch):
                events.append(('append', text, epoch))
                return super().append(text, work, epoch=epoch)
        work = owner_unit_work(value)
        with patch.object(codec, '_SubstringIndex', Refused), \
                patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
            with self.assertRaises(MemoryError) as raised:
                codec._pack_text(value, work)
        self.assertIs(primary, raised.exception)
        self.assertEqual([('append', value[0], 0), ('query', value[1], 1)], events)
        self.assertEqual(before, codec._literal(value))


if __name__ == '__main__':
    unittest.main(verbosity=2)
