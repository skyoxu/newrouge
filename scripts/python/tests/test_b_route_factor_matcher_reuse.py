"""Short independent greedy oracle; historical byte-pinned oracle stays in Task."""
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_compact_literal as codec


def greedy(text, phrases):
    choices = sorted(set(phrases), key=lambda item: (-len(item), item))
    offset = 0
    while offset < len(text):
        phrase = next((item for item in choices if text.startswith(item, offset)), None)
        if phrase is None:
            offset += 1
        else:
            end = offset + len(phrase)
            yield offset, end, phrase
            offset = end


def factor_oracle(phrases):
    """Short strings only: naive matcher, original visible-definition decisions."""
    order = sorted(range(len(phrases)), key=lambda index: (len(phrases[index]), index))
    earlier, definitions = {}, []
    for number, index in enumerate(order):
        text, pieces, offset = phrases[index], [], 0
        shorter = [item for item in earlier if len(item) < len(text)]
        for start, end, phrase in greedy(text, shorter):
            if offset < start:
                pieces.append(text[offset:start])
            pieces.append((codec._TEXT_PHRASE, earlier[phrase]))
            offset = end
        if offset < len(text):
            pieces.append(text[offset:])
        definition = pieces[0] if len(pieces) == 1 else (codec._TEXT_CONCAT, pieces)
        definitions.append(definition if len(codec._atom_literal(definition)) < len(repr(text)) else text)
        earlier[text] = number
    return definitions, [(codec._TEXT_PHRASE, order.index(index)) for index in range(len(phrases))]


class FactorMatcherReuseTests(unittest.TestCase):
    def compare(self, phrases):
        refs = [(codec._TEXT_PHRASE, index) for index in range(len(phrases))]
        self.assertEqual(factor_oracle(phrases), codec._factor_phrases(phrases, refs, codec._EncodingWork()))

    def test_exhaustive_shorter_only_greedy_and_self_exclusion(self):
        phrases = [''.join(row) for length in range(1, 6) for row in itertools.product('ab', repeat=length)]
        choices = sorted((item for item in phrases if len(item) < 5), key=lambda item: (-len(item), item))
        matcher = codec._LiteralMatcher(choices, codec._EncodingWork())
        for text in phrases:
            self.assertEqual(list(greedy(text, [item for item in phrases if len(item) < len(text)])),
                             list(matcher.finditer(text, exclude_full=True)), text)
        self.assertEqual([(0, 3, 'aba')], list(matcher.finditer('aba')))

    def test_definition_order_unicode_overlap_duplicates(self):
        phrases = ['\u4e2d', '\u4e2d\u4e2d', '\u4e2d\u4e2d\n', 'a', 'ab', 'aba', 'ba', 'ab', '\0', '\0a']
        for rows in (phrases, phrases[::-1], phrases[3:] + phrases[:3]):
            self.compare(rows)

    def test_empty_and_single_length_do_not_construct_union(self):
        for rows in ([], ['only'], ['aaa', 'bbb', 'aaa']):
            with patch.object(codec, '_LiteralMatcher', side_effect=AssertionError('unneeded union')):
                self.compare(rows)

    def test_factor_uses_exactly_one_matcher(self):
        real, calls = codec._LiteralMatcher, []
        class Observed(real):
            def __init__(self, *args):
                calls.append(tuple(args[0]))
                super().__init__(*args)
        phrases = ['x' * length for length in range(16, 30)]
        with patch.object(codec, '_LiteralMatcher', Observed):
            self.compare(phrases)
        self.assertEqual(1, len(calls))
        self.assertEqual(tuple(reversed(phrases[:-1])), calls[0])

    def test_shared_account_refusal_and_scanner_cleanup(self):
        phrases = ['q' * length for length in range(16, 24)]
        work = codec._EncodingWork()
        codec._factor_phrases(phrases, [], work)
        charged = work.limit - work.remaining
        before = list(phrases)
        for remaining in (0, 7, charged - 1):
            account = codec._EncodingWork()
            account.spend(account.remaining - remaining)
            with patch.object(codec, '_EncodingWork', side_effect=AssertionError('account reset')):
                with self.assertRaises(ValueError):
                    codec._factor_phrases(phrases, [], account)
            self.assertEqual(before, phrases)
        scanner, closed = codec._LiteralMatcher.finditer, []
        def interrupted(matcher, text, **kwargs):
            try:
                for span in scanner(matcher, text, **kwargs):
                    yield span
                    raise MemoryError('scanner seam')
            finally:
                closed.append(True)
        with patch.object(codec._LiteralMatcher, 'finditer', interrupted):
            with self.assertRaisesRegex(MemoryError, 'scanner seam'):
                codec._factor_phrases(phrases, [], codec._EncodingWork())
        self.assertTrue(closed)

    def test_public_v3_v4_roundtrip_preserves_exact_types_and_order(self):
        value = {'z': ['visible complete text ' * 8 + str(index) for index in range(6)] * 2,
                 'a': [None, False, 0, 0.0, '\u4e2d\U0001f680\n\0']}
        for schema in (codec.ATOM_SCHEMA, codec.RESIDUAL_SCHEMA):
            restored = codec.loads(codec.dumps(value, schema=schema))
            self.assertEqual(value, restored)
            self.assertEqual(list(value), list(restored))
            self.assertIs(type(restored['a'][1]), bool)
            self.assertIs(type(restored['a'][2]), int)
            self.assertIs(type(restored['a'][3]), float)


if __name__ == '__main__':
    unittest.main(verbosity=2)
