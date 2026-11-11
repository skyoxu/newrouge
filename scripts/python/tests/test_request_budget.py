"""Context admission must retain conservative bounds in either counter mode."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _capability_input_integrity import measure_request


class RequestBudgetTests(unittest.TestCase):
    def test_missing_tokenizer_accepts_exact_utf8_boundary_with_reserve(self):
        with patch.dict(sys.modules, {'tiktoken': None}):
            report = measure_request('a' * 5494, max_bytes=10000,
                                     max_input_tokens=30000, reserved_tokens=24506)
        self.assertEqual('utf8_byte_upper_bound', report['token_counter'])
        self.assertEqual(5494, report['input_token_estimate'])
        self.assertEqual({}, report['token_counts'])
        self.assertFalse(report['truncation_allowed'])

    def test_missing_tokenizer_rejects_one_byte_over_reserved_boundary(self):
        with patch.dict(sys.modules, {'tiktoken': None}):
            with self.assertRaisesRegex(ValueError,
                    'runner_context_budget_exceeded:estimated_input_tokens=5495;'
                    'continuation_reserve=24506;limit=30000;.*'
                    'token_counter=utf8_byte_upper_bound'):
                measure_request('a' * 5495, max_bytes=10000,
                                max_input_tokens=30000, reserved_tokens=24506)

    def test_missing_tokenizer_counts_utf8_bytes_instead_of_characters(self):
        with patch.dict(sys.modules, {'tiktoken': None}):
            report = measure_request('\u6d4b\u8bd5', max_bytes=6, max_input_tokens=8,
                                     reserved_tokens=2)
            with self.assertRaisesRegex(ValueError, 'estimated_input_tokens=6;'):
                measure_request('\u6d4b\u8bd5', max_bytes=6, max_input_tokens=7,
                                reserved_tokens=2)
        self.assertEqual(2, report['request_chars'])
        self.assertEqual(6, report['request_bytes'])

    def test_tokenizer_uses_larger_encoding_and_rounds_headroom_up(self):
        encodings = {name: SimpleNamespace(encode=Mock(return_value=list(range(count))))
                     for name, count in [('o200k_base', 11), ('cl100k_base', 12)]}
        get_encoding = Mock(side_effect=encodings.__getitem__)
        tokenizer = SimpleNamespace(get_encoding=get_encoding)
        with patch.dict(sys.modules, {'tiktoken': tokenizer}):
            report = measure_request('full untruncated payload', max_bytes=100,
                                     max_input_tokens=20, reserved_tokens=6)
            with self.assertRaisesRegex(ValueError,
                    'estimated_input_tokens=14;.*'
                    r'token_counter=max\(o200k_base,cl100k_base\)\+10_percent'):
                measure_request('full untruncated payload', max_bytes=100,
                                max_input_tokens=19, reserved_tokens=6)
        self.assertEqual({'o200k_base': 11, 'cl100k_base': 12}, report['token_counts'])
        self.assertEqual(14, report['input_token_estimate'])
        for encoding in encodings.values():
            encoding.encode.assert_called_with('full untruncated payload', disallowed_special=())

    def test_tokenizer_cannot_override_encoded_byte_limit(self):
        tokenizer = SimpleNamespace(get_encoding=Mock())
        with patch.dict(sys.modules, {'tiktoken': tokenizer}):
            with self.assertRaisesRegex(ValueError, 'runner_input_too_large:'):
                measure_request('\u6d4b\u8bd5', max_bytes=5, max_input_tokens=100)
        tokenizer.get_encoding.assert_not_called()

    def test_unavailable_encoding_data_does_not_silently_change_counter(self):
        tokenizer = SimpleNamespace(get_encoding=Mock(side_effect=OSError('encoding data unavailable')))
        with patch.dict(sys.modules, {'tiktoken': tokenizer}):
            with self.assertRaisesRegex(OSError, 'encoding data unavailable'):
                measure_request('complete payload', max_bytes=100, max_input_tokens=100)


if __name__ == '__main__':
    unittest.main()
