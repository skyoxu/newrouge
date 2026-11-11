"""Behavioral evidence for the offline complete-request binding primitive."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _b_route_codec as codec
from _b_route_operation_content import FrozenOperationContent, freeze_content, verify_replay


class OperationContentTests(unittest.TestCase):
    def setUp(self):
        self.operation_id = "OP-7"
        self.raw = b'{ "known": 1, "unknown": {"nested":[true,null,"keep"]} }\n'
        self.frozen = freeze_content(self.operation_id, self.raw)

    def assert_reason(self, reason, function, *args):
        with self.assertRaises(codec.CodecError) as caught:
            function(*args)
        self.assertEqual(caught.exception.diagnostic.reason_code, reason)
        return caught.exception.diagnostic

    def test_exact_frozen_api_and_original_bytes(self):
        self.assertEqual([field.name for field in fields(FrozenOperationContent)],
                         ["operation_id", "codec_version", "request_raw",
                          "request_raw_digest", "request_digest"])
        self.assertEqual(self.frozen.operation_id, self.operation_id)
        self.assertEqual(self.frozen.codec_version, codec.CODEC_VERSION)
        self.assertIs(self.frozen.request_raw, self.raw)
        self.assertEqual(self.frozen.request_raw_digest, codec.raw_digest(self.raw))
        self.assertEqual(self.frozen.request_digest,
                         codec.canonical_digest(codec.strict_json_loads(self.raw)))
        with self.assertRaises(FrozenInstanceError):
            self.frozen.request_raw = b'{}'

    def test_identical_replay_returns_original_object(self):
        self.assertIs(verify_replay(self.frozen, self.operation_id, self.raw), self.frozen)

    def test_format_and_recursive_key_reordering_keep_original_object_and_raw(self):
        original = b'{"z":{"b":2,"a":1},"a":3}\r\n'
        frozen = freeze_content("OP", original)
        replay = b' { "a":3, "z": { "a":1, "b":2 } } '
        self.assertNotEqual(codec.raw_digest(original), codec.raw_digest(replay))
        result = verify_replay(frozen, "OP", replay)
        self.assertIs(result, frozen)
        self.assertIs(result.request_raw, original)

    def test_complete_unknown_fields_are_preserved_and_bound(self):
        self.assertEqual(codec.strict_json_loads(self.frozen.request_raw),
                         {"known": 1, "unknown": {"nested": [True, None, "keep"]}})
        for raw in (b'{"known":1}', b'{"known":1,"unknown":{"nested":[true,null,"changed"]}}',
                    b'{"known":1,"unknown":{"nested":[true,null,"keep"]},"extra":0}'):
            with self.subTest(raw=raw):
                self.assert_reason(codec.ReasonCode.CONFLICT, verify_replay,
                                   self.frozen, self.operation_id, raw)

    def test_empty_object_has_no_business_schema_requirement(self):
        frozen = freeze_content("OP", b'{}')
        self.assertIs(verify_replay(frozen, "OP", b' { }\n'), frozen)

    def test_valid_request_changes_and_different_ids_conflict(self):
        for operation_id, raw in (("OP-8", self.raw), ("op-7", self.raw),
                                  (self.operation_id, b'{"known":2}')):
            with self.subTest(operation_id=operation_id, raw=raw):
                self.assert_reason(codec.ReasonCode.CONFLICT, verify_replay,
                                   self.frozen, operation_id, raw)

    def test_business_ids_are_validated_without_coercion(self):
        for value in (None, True, 7, "", " ", " OP", "OP "):
            with self.subTest(value=value):
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, freeze_content, value, b'{}')
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   self.frozen, value, b'{}')
        self.assertEqual(freeze_content("OP-é", b'{}').operation_id, "OP-é")

    def test_strict_bytes_only_for_freeze_and_replay(self):
        class BytesSubclass(bytes):
            pass

        for value in ('{}', bytearray(b'{}'), memoryview(b'{}'), {}, None, BytesSubclass(b'{}')):
            with self.subTest(kind=type(value).__name__):
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, freeze_content, "OP", value)
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   self.frozen, self.operation_id, value)

    def test_top_level_must_be_an_object(self):
        for raw in (b'[]', b'[{}]', b'null', b'true', b'1', b'"object"'):
            with self.subTest(raw=raw):
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, freeze_content, "OP", raw)
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   self.frozen, self.operation_id, raw)

    def test_strict_decode_errors_are_inherited_for_both_entrypoints(self):
        cases = ((b'\xff', codec.ReasonCode.INVALID_UTF8),
                 (b'{"x":"\\ud800"}', codec.ReasonCode.INVALID_UTF8),
                 (b'{"x":1,"x":2}', codec.ReasonCode.DUPLICATE_KEY),
                 (b'{"x":{"a":1,"a":2}}', codec.ReasonCode.DUPLICATE_KEY),
                 (b'{"x":NaN}', codec.ReasonCode.NON_FINITE_NUMBER),
                 (b'{"x":Infinity}', codec.ReasonCode.NON_FINITE_NUMBER),
                 (b'{"x":-Infinity}', codec.ReasonCode.NON_FINITE_NUMBER),
                 (b'{"x":1e999}', codec.ReasonCode.NON_FINITE_NUMBER),
                 (b'{broken}', codec.ReasonCode.INVALID_JSON))
        for raw, reason in cases:
            with self.subTest(raw=raw):
                self.assert_reason(reason, freeze_content, "OP", raw)
                self.assert_reason(reason, verify_replay, self.frozen, self.operation_id, raw)

    def test_every_frozen_field_type_is_rechecked_before_new_request(self):
        invalid = {"operation_id": 1, "codec_version": None, "request_raw": '{}',
                   "request_raw_digest": b'sha256:invalid', "request_digest": False}
        for field, value in invalid.items():
            with self.subTest(field=field):
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   replace(self.frozen, **{field: value}), "OP", b'\xff')

    def test_every_frozen_field_value_tampering_fails_closed(self):
        cases = (("operation_id", "OTHER", codec.ReasonCode.CONFLICT),
                 ("operation_id", " padded", codec.ReasonCode.INVALID_TYPE),
                 ("codec_version", "future.v99", codec.ReasonCode.UNKNOWN_CODEC_VERSION),
                 ("request_raw", b'{}', codec.ReasonCode.DIGEST_MISMATCH),
                 ("request_raw_digest", "sha256:" + "0" * 64, codec.ReasonCode.DIGEST_MISMATCH),
                 ("request_digest", "sha256:" + "0" * 64, codec.ReasonCode.DIGEST_MISMATCH))
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                self.assert_reason(reason, verify_replay, replace(self.frozen, **{field: value}),
                                   self.operation_id, self.raw)

    def test_existing_integrity_and_codec_precede_new_request_validation(self):
        for field, value, reason in (
            ("codec_version", "future", codec.ReasonCode.UNKNOWN_CODEC_VERSION),
            ("request_raw", b'\xff', codec.ReasonCode.INVALID_UTF8),
            ("request_raw", b'[]', codec.ReasonCode.INVALID_TYPE),
            ("request_raw_digest", "invalid", codec.ReasonCode.DIGEST_MISMATCH),
            ("request_digest", "invalid", codec.ReasonCode.DIGEST_MISMATCH),
        ):
            with self.subTest(field=field):
                self.assert_reason(reason, verify_replay, replace(self.frozen, **{field: value}),
                                   None, b'{broken}')

    def test_format_tampering_of_stored_raw_requires_matching_raw_digest(self):
        alternate = b'{"unknown":{"nested":[true,null,"keep"]},"known":1}'
        self.assert_reason(codec.ReasonCode.DIGEST_MISMATCH, verify_replay,
                           replace(self.frozen, request_raw=alternate), self.operation_id, alternate)

    def test_non_frozen_existing_objects_are_rejected(self):
        for value in (None, {}, self.raw, object()):
            with self.subTest(kind=type(value).__name__):
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   value, self.operation_id, self.raw)

    def test_manually_constructed_invalid_existing_is_rejected(self):
        existing = FrozenOperationContent("OP", codec.CODEC_VERSION, b'{}', "bad", "bad")
        self.assert_reason(codec.ReasonCode.DIGEST_MISMATCH, verify_replay, existing, "OP", b'{}')

    def test_bypassed_field_deletion_fails_with_a_shared_diagnostic(self):
        for field in fields(FrozenOperationContent):
            with self.subTest(field=field.name):
                damaged = replace(self.frozen)
                object.__delattr__(damaged, field.name)
                self.assert_reason(codec.ReasonCode.INVALID_TYPE, verify_replay,
                                   damaged, self.operation_id, self.raw)

    def test_array_order_is_content(self):
        frozen = freeze_content("OP", b'{"a":[1,2]}')
        self.assert_reason(codec.ReasonCode.CONFLICT, verify_replay, frozen, "OP", b'{"a":[2,1]}')

    def test_booleans_and_numbers_remain_distinct(self):
        for before, after in ((b'true', b'1'), (b'false', b'0'), (b'1', b'1.0')):
            with self.subTest(before=before, after=after):
                frozen = freeze_content("OP", b'{"x":' + before + b'}')
                self.assert_reason(codec.ReasonCode.CONFLICT, verify_replay, frozen,
                                   "OP", b'{"x":' + after + b'}')

    def test_numeric_spelling_follows_existing_codec(self):
        for before, after in ((b'1.0', b'1e0'), (b'0', b'-0')):
            with self.subTest(before=before, after=after):
                frozen = freeze_content("OP", b'{"x":' + before + b'}')
                self.assertIs(verify_replay(frozen, "OP", b'{"x":' + after + b'}'), frozen)

    def test_unicode_escape_spelling_matches_without_normalizing_content(self):
        original = '{"é":"中😀"}'.encode("utf-8")
        frozen = freeze_content("OP", original)
        escaped = b'{"\\u00e9":"\\u4e2d\\ud83d\\ude00"}'
        self.assertIs(verify_replay(frozen, "OP", escaped), frozen)
        for changed in ('{"e\\u0301":"中😀"}', '{"É":"中😀"}'):
            with self.subTest(changed=changed):
                self.assert_reason(codec.ReasonCode.CONFLICT, verify_replay,
                                   frozen, "OP", changed.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
