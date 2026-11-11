"""Exact cached/uncached paths of the installed residual literal codec.

Both names below reference ONE real module. Baseline calls create fresh work
without an owner retained context, so they use its original scanner path. This
is branch equivalence, not an independent historical implementation oracle.
The separate Root diagnostic retains the byte-pinned old-source comparison.
No copied codec source, dynamic module loader or historical fixture is needed.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as candidate

# Every baseline operation below uses a fresh no-context account. Keep the
# alias explicit: these are two branches of one implementation, not old/new
# separately loaded modules. Scanner patches are sequential and restored.
baseline = candidate


def measured_work(value):
    """Unit owner seam derives its own actual graph metric in the same account."""
    work = candidate._EncodingWork()
    measured = candidate._json_preflight(value, work)
    work._residual_retained = measured[:3]
    return work


class ResidualScanCacheTests(unittest.TestCase):
    def test_all_schema_literals_are_byte_exact_between_cached_and_uncached(self):
        prefix = 'Complete visible literal and original ordering. ' * 8
        rng = random.Random(538177)
        values = [
            {'r': {'marker': 'compact-text-phrase'}, 'types': [None, False, 0, 0.0],
             'data': [prefix, prefix + 'A', prefix + 'B', prefix, '\u4e2d\u6587\n\\"']},
            {'sha': 'sha256:' + '0' * 64, 'lines': ['\0' * 96, '\0' * 96 + 'tail']},
            {'phrases': [prefix + ''.join(rng.choice('abc') for _ in range(12))
                         for _ in range(12)]},
        ]
        for schema in (baseline.SCHEMA, baseline.CURRENT_SCHEMA,
                       baseline.ATOM_SCHEMA, baseline.RESIDUAL_SCHEMA):
            for value in values:
                with self.subTest(schema=schema, value=value):
                    original = baseline.dumps(value, schema=schema)
                    work = measured_work(value) if schema == candidate.RESIDUAL_SCHEMA else candidate._EncodingWork()
                    changed = candidate.dumps(value, schema=schema, work=work)
                    self.assertEqual(original, changed)
                    self.assertEqual(value, baseline.loads(changed))

    def test_repeated_leaf_scans_once_instead_of_once_per_occurrence(self):
        prefix = 'same complete repeated literal prefix ' * 8
        values = [prefix] * 8 + [prefix + 'A', prefix + 'B']
        original_counts, candidate_counts = Counter(), Counter()
        # Both aliases share this class. Capture its genuine unpatched
        # method once, then install each counter in a separate with block.
        scanner = candidate._LiteralMatcher.finditer

        def count_old(matcher, text):
            original_counts[text] += 1
            yield from scanner(matcher, text)

        def count_new(matcher, text):
            candidate_counts[text] += 1
            yield from scanner(matcher, text)

        with patch.object(baseline._LiteralMatcher, 'finditer', count_old):
            expected = baseline._residual_text([], values, [], baseline._EncodingWork())
        with patch.object(candidate._LiteralMatcher, 'finditer', count_new):
            actual = candidate._residual_text([], values, [], measured_work(values))
        self.assertEqual(expected, actual)
        self.assertEqual(1, candidate_counts[prefix])
        self.assertGreater(original_counts[prefix], candidate_counts[prefix])
        self.assertEqual({text: 1 for text in set(values)}, dict(candidate_counts))

    def test_unselected_overlapping_winner_still_consumes_original_greedy_span(self):
        short = 'a' * 64
        long = short + '\0' * 64
        # Long is an adjacent-LCP candidate and wins twice, but repr escaping
        # makes it unprofitable. Short wins three separate leaves and is selected.
        # A selected-only matcher would incorrectly replace short inside long.
        values = [long, long + 'tail', short, short, short]
        original = baseline._residual_text([], values, [], baseline._EncodingWork())
        actual = candidate._residual_text([], values, [], measured_work(values))
        self.assertEqual(original, actual)
        phrases, encoded = actual
        self.assertIn(short, phrases)
        self.assertNotIn(long, phrases)
        self.assertEqual(values[:2], encoded[:2])
        self.assertEqual([(candidate._TEXT_PHRASE, phrases.index(short))] * 3, encoded[2:])

    def test_no_selected_phrase_preserves_original_identity_and_discards_cache(self):
        values = ['\0' * 96, '\0' * 96 + 'tail']
        phrases = []
        result, encoded = candidate._residual_text(phrases, values, [], measured_work(values))
        self.assertIs(phrases, result)
        self.assertIs(values, encoded)
        self.assertEqual(baseline._residual_text([], values, [], baseline._EncodingWork()),
                         (result, encoded))

    def test_retained_owner_headroom_refuses_cache_before_key_or_span_allocation(self):
        text = 'x' * 128
        work = candidate._EncodingWork()
        # Represents a real owner live measurement in the isolated unit seam.
        # Production derives it at materials._live, never from a packet field.
        work._residual_retained = (candidate.MAX_EXPANDED_BYTES - 64, 1, 1)
        with patch.object(candidate._ResidualScanCache, '__init__',
                          side_effect=AssertionError('fixed cache metadata allocated')):
            self.assertIsNone(candidate._ResidualScanCache(work, len(text)))
            values = [text, text + 'tail', text]
            self.assertEqual(baseline._residual_text([], values, [], baseline._EncodingWork()),
                             candidate._residual_text([], values, [], work))

    def test_scanner_headroom_refuses_wrapper_before_owner_plus_fixed_plus_winners_overflow(self):
        text = 'x' * 150
        values = [text, text + 'tail', text]
        work = candidate._EncodingWork()
        work._residual_retained = (candidate.MAX_EXPANDED_BYTES - 5000, 1, 1)
        # The genuine original max scanner fits with owner_live, but its new
        # fixed wrapper would not. No wrapper/row may survive into fallback.
        self.assertLess(32 * max(map(len, values)) + 2, 5000)
        self.assertGreater(256 + 32 * max(map(len, values)) + 2, 5000)
        with patch.object(candidate._ResidualScanCache, '__init__',
                          side_effect=AssertionError('wrapper allocated without scanner headroom')):
            self.assertIsNone(candidate._ResidualScanCache(work, max(map(len, values))))
            self.assertEqual(baseline._residual_text([], values, [], baseline._EncodingWork()),
                             candidate._residual_text([], values, [], work))

    def test_pending_row_span_bound_discards_before_new_tuple_and_uses_original_scan(self):
        text = 'x' * 128
        work = candidate._EncodingWork()
        work._residual_retained = (0, 0, 1)
        matcher = candidate._LiteralMatcher([text], work)
        # The key/list plus scanner fit, but the full logical winner tuple does
        # not. The candidate must leave no published partial cache row.
        with patch.object(candidate, 'MAX_EXPANDED_BYTES', 5800):
            cache = candidate._ResidualScanCache(work, len(text))
            expected = [(0, len(text), text)]
            self.assertEqual(expected, list(cache.capture(text, matcher)))
            self.assertEqual({}, cache.rows)
            self.assertEqual(expected, list(cache.replay(text, matcher)))
            self.assertEqual({}, cache.rows)
            cache.close()

    def test_node_limit_and_later_large_scan_clear_retained_rows_before_fallback(self):
        text = 'x' * 128
        larger = text * 4
        work = candidate._EncodingWork()
        work._residual_retained = (0, 0, 1)
        matcher = candidate._LiteralMatcher([text], work)
        with patch.object(candidate, 'MAX_EXPANDED_NODES', 521):
            cache = candidate._ResidualScanCache(work, len(larger))
            self.assertEqual([(0, 128, text)], list(cache.capture(text, matcher)))
            self.assertIn(text, cache.rows)
            # Original scanner is allowed, but the new retained cache may not
            # coexist with its wider winners list. Drop the cache first.
            self.assertEqual([(i, i + 128, text) for i in range(0, 512, 128)],
                             list(cache.replay(larger, matcher)))
            self.assertEqual({}, cache.rows)
        cache.close()

    def test_shared_work_exhaustion_returns_no_partial_graph_and_never_resets(self):
        prefix = 'original shared bounded account ' * 8
        values = [prefix, prefix + 'tail', prefix]
        original = deepcopy(values)
        full = measured_work(values)
        before = full.remaining
        expected = candidate._residual_text([], values, [], full)
        spent = before - full.remaining
        for reserve in (0, 27, 59, spent - 1, spent):
            with self.subTest(reserve=reserve):
                work = measured_work(values)
                work.spend(work.remaining - reserve)
                actual = None
                with patch.object(candidate, '_EncodingWork', side_effect=AssertionError('reset')):
                    if reserve < spent:
                        with self.assertRaisesRegex(ValueError, 'charged=.*reserve=.*remaining='):
                            actual = candidate._residual_text([], values, [], work)
                        self.assertIsNone(actual)
                    else:
                        actual = candidate._residual_text([], values, [], work)
                        self.assertEqual(expected, actual)
                        self.assertEqual(0, work.remaining)
                self.assertEqual(original, values)

    def test_memory_error_primary_survives_prepaid_cache_cleanup(self):
        prefix = 'original visible residual prefix ' * 8
        values = [prefix, prefix + 'tail', prefix]
        created = []
        real = candidate._ResidualScanCache

        class Interrupted(real):
            def __init__(self, work, max_scan_chars):
                super().__init__(work, max_scan_chars)
                created.append(self)

            def replay(self, text, pattern):
                yield from super().replay(text, pattern)
                raise MemoryError('original allocation interruption')

        with patch.object(candidate, '_ResidualScanCache', Interrupted):
            with self.assertRaisesRegex(MemoryError, 'original allocation interruption'):
                candidate._residual_text([], values, [], measured_work(values))
        self.assertTrue(created)
        self.assertTrue(all(cache.rows is None or not cache.rows for cache in created))

    def test_consumer_work_refusal_closes_generators_with_exception_traceback_retained(self):
        prefix = 'complete consumer interruption prefix ' * 8
        values = [prefix, prefix + 'tail', prefix]
        failures = []  # Deliberately retain exceptions and all their tracebacks.
        for phase, caller, amount in (
                ('capture', '_residual_text', 2 * len(prefix) + 14),
                ('replay', 'replace', 2 * len(prefix) + 6)):
            with self.subTest(phase=phase):
                seen, caches, pending = [], [], []
                real_method = getattr(candidate._ResidualScanCache, phase)

                def record(cache, text, pattern):
                    generator = real_method(cache, text, pattern)
                    seen.append(generator)
                    caches.append(cache)
                    return generator

                class RefuseConsumer(candidate._EncodingWork):
                    armed = False

                    def spend(self, charge=1, *, phase=None):
                        if (self.armed and charge == amount
                                and sys._getframe(1).f_code.co_name == caller):
                            self.armed = False
                            for generator in seen:
                                frame = generator.gi_frame
                                if frame is not None and type(frame.f_locals.get('row')) is list:
                                    pending.append(frame.f_locals['row'])
                            # Exhaust through the real account, then let its
                            # genuine error occur in the outer consumer spend.
                            super().spend(self.remaining)
                        return super().spend(charge, phase=phase)

                work = RefuseConsumer()
                work._residual_retained = candidate._json_preflight(values, work)[:3]
                work.armed = True
                failure = None
                with patch.object(candidate._ResidualScanCache, phase, record):
                    try:
                        candidate._residual_text([], values, [], work)
                    except ValueError as error:
                        failure = error
                        failures.append(error)
                self.assertIsNotNone(failure)
                self.assertIn('remaining=0', str(failure))
                self.assertTrue(seen)
                self.assertTrue(all(generator.gi_frame is None for generator in seen))
                self.assertTrue(all(cache.rows is None or not cache.rows for cache in caches))
                if phase == 'capture':
                    self.assertTrue(pending)
                    self.assertTrue(all(not row for row in pending))
        self.assertEqual(2, len(failures))

    def test_cache_is_action_local_and_unowned_generic_encoding_cannot_enable_it(self):
        values = ['exact action-local literal ' * 8] * 3
        work = measured_work(values)
        previous = work._residual_retained
        created = []
        real = candidate._ResidualScanCache

        class Observed(real):
            def __init__(self, account, max_scan_chars):
                super().__init__(account, max_scan_chars)
                created.append(self)

        with patch.object(candidate, '_ResidualScanCache', Observed):
            candidate._residual_text([], values, [], work)
            candidate._residual_text([], values, [], work)
        self.assertEqual(2, len(created))
        self.assertIsNot(created[0], created[1])
        self.assertTrue(all(not cache.rows for cache in created))
        self.assertEqual(previous, work._residual_retained)
        value = {'text': values}
        with patch.object(candidate, '_ResidualScanCache', side_effect=AssertionError('unowned cache')):
            self.assertEqual(baseline.dumps(value, schema=baseline.RESIDUAL_SCHEMA),
                             candidate.dumps(value, schema=candidate.RESIDUAL_SCHEMA))
        self.assertFalse(hasattr(candidate, '_residual_scan_cache'))


if __name__ == '__main__':
    unittest.main()
