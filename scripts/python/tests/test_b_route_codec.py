"""Story 1.3 behavioral evidence; fixture writes never touch production data."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _b_route_codec as codec
from _planning_skill_common import canonical_sha


DIAGNOSTIC_FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


class CodecFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "repository"
        self.root.mkdir()
        self.record = {"schema_version": codec.PLAN_SCHEMA, "plan_id": "PLAN-7", "revision": 2,
                       "extensions": {"schema_version": "arbitrary.extension.v9", "label": "é中"}}
        self.path = "plans/PLAN-7/2.json"
        self.dump(self.path, self.record)

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def dump(self, path, value):
        return self.write(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")

    def reference(self, *, mode="canonical", **changes):
        value = {"path": self.path, "schema_version": codec.PLAN_SCHEMA, "entity_id": "PLAN-7",
                 "revision": 2, "digest": codec.canonical_digest(self.record), "verification_mode": mode,
                 "codec_version": codec.CODEC_VERSION if mode == "canonical" else None}
        if mode == "raw":
            value["digest"] = codec.raw_digest((self.root / self.path).read_bytes())
        value.update(changes)
        return value

    def assert_reason(self, result, code):
        self.assertFalse(result.ok)
        self.assertIs(result.diagnostic.reason_code, code)
        self.assertEqual(set(result.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)
        self.assertFalse(result.to_dict()["schema_validated"])
        self.assertFalse(result.to_dict()["target_verified"])

    def assert_error(self, function, value, code):
        with self.assertRaises(codec.CodecError) as caught:
            function(value)
        self.assertIs(caught.exception.diagnostic.reason_code, code)
        self.assertEqual(set(caught.exception.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)

    def snapshot(self, root=None):
        base = root or self.root
        return {path.relative_to(base).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                if path.is_file() else None for path in base.rglob("*")}


class StrictJsonTests(CodecFixtures):
    def test_duplicate_keys_are_rejected_at_every_depth_and_escape_spelling(self):
        for text in ('{"x":1,"x":2}', '{"a":{"x":1,"x":2}}',
                     '[{"x":1,"x":2}]', '{"x":1,"\\u0078":2}'):
            with self.subTest(text=text):
                self.assert_error(codec.strict_json_loads, text, codec.ReasonCode.DUPLICATE_KEY)

    def test_nonfinite_literals_and_exponent_overflow_are_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            for text in (token, '{"nested":[' + token + "]}"):
                with self.subTest(text=text):
                    self.assert_error(codec.strict_json_loads, text, codec.ReasonCode.NON_FINITE_NUMBER)

    def test_invalid_utf8_and_unpaired_surrogates_are_rejected(self):
        for data in (b'"\xff"', b'"\xc0\xaf"', b'"\xed\xa0\x80"', b'"\xf4\x90\x80\x80"'):
            with self.subTest(data=data):
                self.assert_error(codec.strict_json_loads, data, codec.ReasonCode.INVALID_UTF8)
        self.assert_error(codec.strict_json_loads, '"\\ud800"', codec.ReasonCode.INVALID_UTF8)

    def test_invalid_syntax_is_distinct_from_identity_difference(self):
        for data in (b"", b"{", b'{"a":1,}', b"{}{}", b"\xef\xbb\xbf{}"):
            with self.subTest(data=data):
                self.assert_error(codec.strict_json_loads, data, codec.ReasonCode.INVALID_JSON)

    def test_strict_decoder_accepts_json_values_but_record_boundary_requires_object(self):
        self.assertEqual(codec.strict_json_loads('[null,true,false,1,1.5,"text"]'),
                         [None, True, False, 1, 1.5, "text"])
        for value in (None, True, 1, 1.5, [], "true"):
            with self.subTest(value=value):
                self.assert_reason(codec.verify_content(value), codec.ReasonCode.INVALID_TYPE)
        self.assert_error(codec.strict_json_loads, {}, codec.ReasonCode.INVALID_TYPE)

    def test_memory_values_reject_python_types_nonstring_keys_and_nonfinite_values(self):
        for value in ({1: "a"}, {True: "a"}, {None: "a"}, {"x": (1, 2)},
                      {"x": {1, 2}}, {"x": b"bytes"}, {"x": object()}):
            with self.subTest(value=repr(value)):
                self.assert_error(codec.canonical_digest, value, codec.ReasonCode.INVALID_TYPE)
        for value in (float("nan"), float("inf"), -float("inf")):
            self.assert_error(codec.canonical_digest, {"x": value}, codec.ReasonCode.NON_FINITE_NUMBER)
        self.assert_error(codec.canonical_digest, {"x": "\udfff"}, codec.ReasonCode.INVALID_UTF8)

    def test_cycles_are_rejected_but_repeated_acyclic_objects_are_allowed(self):
        cycle = []
        cycle.append(cycle)
        self.assert_error(codec.canonical_digest, cycle, codec.ReasonCode.INVALID_JSON)
        shared = {"x": 1}
        self.assertEqual(codec.canonical_digest([shared, shared]), codec.canonical_digest([{"x": 1}, {"x": 1}]))

    def test_unknown_top_level_schema_is_rejected_without_rejecting_extensions(self):
        self.assertTrue(codec.verify_content(self.record).ok)
        for schema in ("newrouge.b-route-plan.v999", "unknown"):
            value = dict(self.record, schema_version=schema)
            self.assert_reason(codec.verify_content(value), codec.ReasonCode.UNKNOWN_SCHEMA)
        for schema in (None, 1, True, [], {}, ""):
            self.assert_reason(codec.verify_content(dict(self.record, schema_version=schema)), codec.ReasonCode.INVALID_TYPE)

    def test_plan_identity_fields_are_strict_and_never_inferred(self):
        for field, invalid in (("plan_id", (None, True, 7, 1.0, "", "  ", [], {})),
                               ("revision", (None, True, False, "2", 2.0, 0, -1, [], {}))):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    self.assert_reason(codec.verify_content(dict(self.record, **{field: value})), codec.ReasonCode.INVALID_TYPE)
            missing = dict(self.record)
            del missing[field]
            self.assert_reason(codec.verify_content(missing), codec.ReasonCode.INVALID_TYPE)
        original = dict(self.record, plan_id="  original ID  ")
        self.assertEqual(codec.verify_content(original).entity_id, "  original ID  ")

    def test_existing_task_and_business_id_types_are_not_coerced(self):
        self.assertEqual(codec.validate_task_id(17), 17)
        for value in (True, False, "17", 17.0, 0, -1, None):
            with self.subTest(value=value):
                self.assert_error(codec.validate_task_id, value, codec.ReasonCode.INVALID_TYPE)
        self.assertEqual(codec.validate_business_id("BACK-017"), "BACK-017")
        self.assertEqual(codec.validate_business_id("17"), "17")
        for value in (17, True, None, "", "  ", " BACK-17", "BACK-17 "):
            self.assert_error(codec.validate_business_id, value, codec.ReasonCode.INVALID_TYPE)


class IdentityTests(CodecFixtures):
    def test_canonical_goldens_match_the_existing_algorithm(self):
        goldens = [({}, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
                   ([], "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
                   ({"text": "é中", "a": [1, 1.0, True, None]},
                    "a352d6d1458b6e56a82148e1a3aae7871be58cd2ef547a18d5947507b369cd15")]
        for value, digest in goldens:
            with self.subTest(value=value):
                self.assertEqual(codec.canonical_digest(value), "sha256:" + digest)
                self.assertEqual(codec.canonical_digest(value), canonical_sha(value))

    def test_key_order_and_json_formatting_change_only_raw_identity(self):
        first = json.dumps(self.record, ensure_ascii=False, indent=2).encode("utf-8")
        second = json.dumps(dict(reversed(list(self.record.items()))), ensure_ascii=True,
                            separators=(",", ":")).encode("ascii") + b"\r\n"
        left, right = codec.verify_content(first), codec.verify_content(second)
        self.assertTrue(left.ok and right.ok)
        self.assertEqual(left.content_identity.canonical_digest, right.content_identity.canonical_digest)
        self.assertNotEqual(left.content_identity.raw_digest, right.content_identity.raw_digest)
        self.assertEqual(left.content_identity.raw_digest, "sha256:" + hashlib.sha256(first).hexdigest())
        self.assertEqual(left.content_identity.codec_version, codec.CODEC_VERSION)

    def test_array_type_unicode_and_string_content_changes_keep_semantic_differences(self):
        pairs = [([1, 2], [2, 1]), (1, 1.0), (1, True), (0, False), (None, "null"),
                 ("é", "e\u0301"), ("x", " x"), ("x", "x "), ("a b", "a  b"),
                 ([1, 1], [1]), ({"a": 1}, {"a": 2}), (0.0, -0.0)]
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                self.assertNotEqual(codec.canonical_digest(first), codec.canonical_digest(second))

    def test_memory_content_has_no_invented_raw_identity(self):
        result = codec.verify_content(self.record)
        self.assertTrue(result.ok)
        self.assertIsNone(result.content_identity.raw_digest)
        self.assertEqual(result.content_identity.canonical_digest, canonical_sha(self.record))
        self.assert_error(codec.raw_digest, "text", codec.ReasonCode.INVALID_TYPE)

    def test_unknown_codec_is_rejected_at_the_pure_api_boundary(self):
        for version in (None, True, 1, "", "newrouge.b-route-json.v999"):
            with self.subTest(version=version):
                with self.assertRaises(codec.CodecError) as caught:
                    codec.canonical_digest(self.record, codec_version=version)
                self.assertIs(caught.exception.diagnostic.reason_code, codec.ReasonCode.UNKNOWN_CODEC_VERSION)


class ReferenceTests(CodecFixtures):
    def test_raw_and_canonical_references_verify_exact_plan_identity(self):
        for mode in ("raw", "canonical"):
            value = self.reference(mode=mode)
            typed = codec.TypedReference.from_value(value)
            for reference in (value, typed, json.dumps(value).encode("utf-8")):
                with self.subTest(mode=mode, input_type=type(reference).__name__):
                    result = codec.verify_reference(self.root, reference)
                    self.assertTrue(result.ok, result.to_dict())
                    self.assertEqual((result.entity_id, result.revision), ("PLAN-7", 2))
                    self.assertTrue(result.to_dict()["target_verified"])

    def test_every_reference_field_is_explicit_and_unknown_fields_are_rejected(self):
        reference = self.reference()
        for field in reference:
            value = dict(reference)
            del value[field]
            with self.subTest(field=field):
                self.assert_reason(codec.verify_reference(self.root, value), codec.ReasonCode.INVALID_REFERENCE)
        self.assert_reason(codec.verify_reference(self.root, dict(reference, private_id="PLAN-7")),
                           codec.ReasonCode.INVALID_REFERENCE)
        for value in (None, True, 1, [], "{}"):
            self.assert_reason(codec.verify_reference(self.root, value), codec.ReasonCode.INVALID_REFERENCE)

    def test_reference_identity_types_are_strict(self):
        for field, values in (("entity_id", (None, True, 7, "", " ", [], {})),
                              ("revision", (None, True, False, "2", 2.0, 0, -1)),
                              ("schema_version", (None, True, 1, "", [], {})),
                              ("path", (None, True, 1, "", [], {}))):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_reason(codec.verify_reference(self.root, self.reference(**{field: value})),
                                       codec.ReasonCode.INVALID_TYPE)

    def test_digest_modes_and_codec_versions_are_validated_without_defaults(self):
        for digest in (None, True, "", "0" * 64, "md5:" + "0" * 32,
                       "sha256:" + "A" * 64, "sha256:" + "0" * 63, "sha256:" + "g" * 64):
            self.assert_reason(codec.verify_reference(self.root, self.reference(digest=digest)), codec.ReasonCode.INVALID_DIGEST)
        for mode in (None, True, "", "immutable_bytes", "task_definition_projection", "RAW"):
            self.assert_reason(codec.verify_reference(self.root, self.reference(verification_mode=mode)),
                               codec.ReasonCode.UNKNOWN_VERIFICATION_MODE)
        for version in (None, True, 1, "", "unknown.v1"):
            self.assert_reason(codec.verify_reference(self.root, self.reference(codec_version=version)),
                               codec.ReasonCode.UNKNOWN_CODEC_VERSION)
        self.assert_reason(codec.verify_reference(self.root, self.reference(mode="raw", codec_version=codec.CODEC_VERSION)),
                           codec.ReasonCode.INVALID_REFERENCE)

    def test_unknown_schema_entity_revision_and_digest_have_distinct_diagnostics(self):
        cases = [(self.reference(schema_version="unknown.v1"), codec.ReasonCode.UNKNOWN_SCHEMA),
                 (self.reference(entity_id="PLAN-UNKNOWN"), codec.ReasonCode.UNKNOWN_ENTITY),
                 (self.reference(revision=3), codec.ReasonCode.REVISION_MISMATCH),
                 (self.reference(digest="sha256:" + "0" * 64), codec.ReasonCode.DIGEST_MISMATCH)]
        for reference, reason in cases:
            with self.subTest(reason=reason):
                result = codec.verify_reference(self.root, reference)
                self.assert_reason(result, reason)
                self.assertIsNotNone(result.diagnostic.expected)
                self.assertIsNotNone(result.diagnostic.actual)

    def test_schema_mismatch_is_distinct_from_a_missing_adapter(self):
        policy_schema = "newrouge.b-route-policy.v1"
        self.assert_reason(codec.verify_reference(self.root, self.reference(schema_version=policy_schema)),
                           codec.ReasonCode.SCHEMA_MISMATCH)
        self.dump(self.path, {"schema_version": policy_schema})
        self.assert_reason(codec.verify_reference(self.root, self.reference()), codec.ReasonCode.SCHEMA_MISMATCH)

    def test_known_schemas_without_adapters_cannot_claim_verified_identity(self):
        expected = {"newrouge.b-route-policy.v1", codec.PLAN_SCHEMA, "newrouge.b-route-binding.v1",
                    "newrouge.b-route-origins.v1", "newrouge.b-route-commit.v1", "newrouge.b-route-catalog.v1",
                    "newrouge.b-route-verification-scope.v1"}
        self.assertEqual(set(codec.SCHEMA_IDENTITY_REGISTRY), expected)
        for schema in sorted(expected - {codec.PLAN_SCHEMA}):
            record = {"schema_version": schema, "plan_id": "PLAN-7", "revision": 2}
            self.dump(self.path, record)
            with self.subTest(schema=schema):
                self.assert_reason(codec.verify_content(record), codec.ReasonCode.IDENTITY_UNPROVABLE)
                reference = self.reference(schema_version=schema, digest=codec.canonical_digest(record))
                self.assert_reason(codec.verify_reference(self.root, reference), codec.ReasonCode.IDENTITY_UNPROVABLE)
        with self.assertRaises(TypeError):
            codec.SCHEMA_IDENTITY_REGISTRY["private.v1"] = None

    def test_raw_reference_detects_reformatting_while_canonical_reference_survives(self):
        raw = self.reference(mode="raw")
        canonical = self.reference()
        self.write(self.path, json.dumps(self.record, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
        self.assert_reason(codec.verify_reference(self.root, raw), codec.ReasonCode.DIGEST_MISMATCH)
        self.assertTrue(codec.verify_reference(self.root, canonical).ok)
        changed = dict(self.record, extensions={"label": "changed"})
        self.dump(self.path, changed)
        self.assert_reason(codec.verify_reference(self.root, canonical), codec.ReasonCode.DIGEST_MISMATCH)

    def test_reference_dataclass_cannot_bypass_initial_validation(self):
        with self.assertRaises(codec.CodecError):
            codec.TypedReference(**self.reference(revision=True))
        for field in ("path", "entity_id"):
            with self.subTest(field=field):
                with self.assertRaises(codec.CodecError) as caught:
                    codec.TypedReference(**self.reference(**{field: "bad\ud800value"}))
                self.assertIs(caught.exception.diagnostic.reason_code, codec.ReasonCode.INVALID_UTF8)
        reference = codec.TypedReference.from_value(self.reference())
        with self.assertRaises(FrozenInstanceError):
            reference.revision = 999


class PathTests(CodecFixtures):
    def test_windows_and_posix_escape_spellings_are_rejected_lexically_on_every_host(self):
        paths = ["/tmp/plan.json", "../plan.json", "plans/../../plan.json", "C:/plan.json", "C:plan.json",
                 "C:\\plan.json", "\\\\server\\share\\plan.json", "//server/share/plan.json",
                 "https://example.invalid/plan.json", "file:///plan.json", "plan.json:stream", "plans\\plan.json",
                 "plans/plan\x00.json", "NUL", "CON.json", "COM1", "plans/AUX.txt", "plans/name.", "plans/name "]
        for path in paths:
            with self.subTest(path=path):
                self.assert_reason(codec.verify_reference(self.root, self.reference(path=path)), codec.ReasonCode.UNSAFE_PATH)

    def test_legal_relative_paths_unicode_spaces_and_internal_parent_steps_are_allowed(self):
        self.assertTrue(codec.verify_reference(self.root, self.reference(path="./plans/PLAN-7/../PLAN-7/2.json")).ok)
        unicode_path = "plans/Unicode é 中/plan with spaces.json"
        self.dump(unicode_path, self.record)
        self.assertTrue(codec.verify_reference(self.root, self.reference(path=unicode_path)).ok)

    def test_missing_directories_and_nonregular_targets_return_public_diagnostics(self):
        self.assert_reason(codec.verify_reference(self.root, self.reference(path="plans/missing.json")), codec.ReasonCode.FILE_NOT_FOUND)
        self.assert_reason(codec.verify_content_file(self.root, "plans"), codec.ReasonCode.READ_ERROR)
        self.assert_reason(codec.verify_content_file(self.root / "missing-root", self.path), codec.ReasonCode.FILE_NOT_FOUND)

    def make_symlink(self, source, target, *, directory=False):
        try:
            source.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Symlink creation unavailable: " + type(error).__name__)

    def test_provably_internal_file_and_directory_symlinks_are_allowed(self):
        self.make_symlink(self.root / "file-link.json", self.root / self.path)
        self.make_symlink(self.root / "directory-link", self.root / "plans", directory=True)
        for path in ("file-link.json", "directory-link/PLAN-7/2.json"):
            self.assertTrue(codec.verify_reference(self.root, self.reference(path=path)).ok)

    def test_external_symlinks_are_rejected_even_when_later_parent_steps_return_inside(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        (outside / "external.json").write_bytes((self.root / self.path).read_bytes())
        self.make_symlink(self.root / "outside-file.json", outside / "external.json")
        self.make_symlink(self.root / "outside-directory", outside, directory=True)
        for path in ("outside-file.json", "outside-directory/external.json",
                     "outside-directory/../repository/" + self.path):
            with self.subTest(path=path):
                self.assert_reason(codec.verify_reference(self.root, self.reference(path=path)), codec.ReasonCode.UNSAFE_PATH)

    def test_broken_and_cyclic_links_do_not_produce_success(self):
        self.make_symlink(self.root / "broken.json", self.root / "missing.json")
        self.make_symlink(self.root / "cycle-a", self.root / "cycle-b")
        self.make_symlink(self.root / "cycle-b", self.root / "cycle-a")
        self.assert_reason(codec.verify_reference(self.root, self.reference(path="broken.json")), codec.ReasonCode.FILE_NOT_FOUND)
        self.assert_reason(codec.verify_reference(self.root, self.reference(path="cycle-a")), codec.ReasonCode.PATH_UNPROVABLE)

    def test_read_failure_uses_diagnostic_without_exposing_exception_details(self):
        with patch.object(codec.os, "open", side_effect=PermissionError("SECRET FILE CONTENT")):
            result = codec.verify_content_file(self.root, self.path)
        self.assert_reason(result, codec.ReasonCode.READ_ERROR)
        self.assertNotIn("SECRET", json.dumps(result.to_dict()))

    def test_result_preserves_the_original_path_for_success_and_failure(self):
        path = "./plans/PLAN-7/../PLAN-7/2.json"
        for result in (codec.verify_content_file(self.root, path),
                       codec.verify_reference(self.root, self.reference(path=path)),
                       codec.verify_reference(self.root, self.reference(path=path, entity_id="missing"))):
            self.assertEqual(result.to_dict()["path"], path)
        self.assertIsNone(codec.verify_content(self.record).to_dict()["path"])
        self.assertEqual(codec.verify_content_file(self.root, "missing.json").to_dict()["path"], "missing.json")

    def test_surrogate_path_is_rejected_before_operating_system_io(self):
        self.assert_reason(codec.verify_content_file(self.root, "bad\ud800.json"), codec.ReasonCode.INVALID_UTF8)

    def test_observed_file_drift_is_rejected(self):
        original = os.fstat
        calls = 0

        def observe(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.root / self.path).write_bytes(b"changed during read")
            return original(descriptor)

        with patch.object(codec.os, "fstat", side_effect=observe):
            result = codec.verify_reference(self.root, self.reference())
        self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)


class ReadIdentityRegressionTests(CodecFixtures):
    def verify_sampled_identity(self, *, windows=True, path_changes=None, fd_changes=None):
        """Exercise the reader with the distinct Windows timestamp semantics."""
        target = (self.root / self.path).resolve(strict=True)
        original_stat = Path.stat
        info = original_stat(target)
        common = {field: getattr(info, field) for field in
                  ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")}
        path_samples = [dict(common, st_ctime_ns=100, st_birthtime_ns=100) for _ in range(2)]
        fd_samples = [dict(common, st_ctime_ns=200, st_birthtime_ns=100) for _ in range(3)]
        for samples, changes in ((path_samples, path_changes), (fd_samples, fd_changes)):
            for index, fields in (changes or {}).items():
                samples[index].update(fields)
                for field in tuple(samples[index]):
                    if samples[index][field] == "missing":
                        del samples[index][field]
        path_calls = fd_calls = 0

        def observe_path(path, *args, **kwargs):
            nonlocal path_calls
            if path != target:
                return original_stat(path, *args, **kwargs)
            sample = path_samples[min(path_calls, len(path_samples) - 1)]
            path_calls += 1
            return SimpleNamespace(**sample)

        def observe_fd(_descriptor):
            nonlocal fd_calls
            sample = fd_samples[min(fd_calls, len(fd_samples) - 1)]
            fd_calls += 1
            return SimpleNamespace(**sample)

        with patch.object(codec, "_WINDOWS", windows), patch.object(Path, "stat", observe_path), \
                patch.object(codec.os, "fstat", side_effect=observe_fd):
            result = codec.verify_content_file(self.root, self.path)
        self.assertEqual(path_calls, 2, "Path stat injection must cover both observations")
        self.assertEqual(fd_calls, 3, "Descriptor stat injection must cover all three observations")
        return result

    def test_stable_windows_creation_and_change_times_are_compared_by_source(self):
        self.assertTrue(self.verify_sampled_identity().ok)

    def test_stable_rewrites_remain_readable_without_changing_birth_identity(self):
        target = self.root / self.path
        birthtime = getattr(target.stat(), "st_birthtime_ns", None)
        for attempt in range(12):
            record = dict(self.record, rewrite=attempt)
            self.dump(self.path, record)
            result = codec.verify_content_file(self.root, self.path)
            with self.subTest(attempt=attempt):
                self.assertTrue(result.ok, result.diagnostic.to_dict())
                self.assertEqual(result.content_identity.canonical_digest, codec.canonical_digest(record))
                self.assertEqual(getattr(target.stat(), "st_birthtime_ns", None), birthtime)

    def test_windows_cross_source_identity_rejects_each_comparable_field_difference(self):
        info = (self.root / self.path).stat()
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_birthtime_ns"):
            changed = (100 if field == "st_birthtime_ns" else getattr(info, field)) + 1
            with self.subTest(field=field):
                result = self.verify_sampled_identity(fd_changes={index: {field: changed} for index in range(3)})
                self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)

    def test_same_source_identity_keeps_every_original_field_including_ctime(self):
        info = (self.root / self.path).stat()
        for source in ("path", "fd"):
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
                original = (100 if source == "path" else 200) if field == "st_ctime_ns" else getattr(info, field)
                changes = {1: {field: original + 1}}
                with self.subTest(source=source, field=field):
                    result = self.verify_sampled_identity(**{source + "_changes": changes})
                    self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)

    def test_final_descriptor_observation_rejects_late_ctime_changes(self):
        self.assert_reason(self.verify_sampled_identity(fd_changes={2: {"st_ctime_ns": 201}}),
                           codec.ReasonCode.FILE_CHANGED)

    def test_missing_or_invalid_windows_birthtime_cannot_claim_proven_identity(self):
        for source, indexes in (("path", range(2)), ("fd", range(3))):
            for value in ("missing", None, True, 100.0, "100"):
                changes = {index: {"st_birthtime_ns": value} for index in indexes}
                with self.subTest(source=source, value=value):
                    result = self.verify_sampled_identity(**{source + "_changes": changes})
                    self.assert_reason(result, codec.ReasonCode.PATH_UNPROVABLE)

    def test_posix_cross_source_comparison_still_rejects_ctime_difference(self):
        self.assert_reason(self.verify_sampled_identity(windows=False), codec.ReasonCode.FILE_CHANGED)

    def change_bytes_preserving_size_and_mtime(self):
        target = self.root / self.path
        before = target.stat()
        original = target.read_bytes()
        changed = original.replace(b"PLAN-7", b"PLAN-8")
        self.assertNotEqual(original, changed)
        self.assertEqual(len(original), len(changed))
        target.write_bytes(changed)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(target.stat().st_size, before.st_size)
        self.assertEqual(target.stat().st_mtime_ns, before.st_mtime_ns)

    def test_same_size_in_place_overwrite_with_restored_mtime_is_rejected(self):
        original_fstat = os.fstat
        observations = []

        def observe(descriptor):
            if len(observations) == 1:
                self.change_bytes_preserving_size_and_mtime()
            info = original_fstat(descriptor)
            observations.append(info)
            return info

        with patch.object(codec.os, "fstat", side_effect=observe):
            result = codec.verify_content_file(self.root, self.path)
        self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)
        self.assertEqual(observations[0].st_mtime_ns, observations[1].st_mtime_ns)
        self.assertNotEqual(observations[0].st_ctime_ns, observations[1].st_ctime_ns)

    def test_same_size_overwrite_during_final_path_resolution_is_rejected(self):
        original_resolve = codec.resolve_reference_path
        calls = 0

        def resolve(root, path):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.change_bytes_preserving_size_and_mtime()
            return original_resolve(root, path)

        with patch.object(codec, "resolve_reference_path", side_effect=resolve):
            result = codec.verify_content_file(self.root, self.path)
        self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)

    def test_same_size_replacement_with_restored_mtime_cannot_pass(self):
        original_resolve = codec.resolve_reference_path
        target = self.root / self.path
        original_bytes = target.read_bytes()
        calls = 0
        replaced = False

        def resolve(root, path):
            nonlocal calls, replaced
            calls += 1
            if calls == 2:
                before = target.stat()
                replacement = target.with_name("replacement.json")
                replacement.write_bytes(original_bytes.replace(b"PLAN-7", b"PLAN-8"))
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.assertEqual(replacement.stat().st_size, before.st_size)
                self.assertEqual(replacement.stat().st_mtime_ns, before.st_mtime_ns)
                os.replace(replacement, target)
                replaced = True
            return original_resolve(root, path)

        with patch.object(codec, "resolve_reference_path", side_effect=resolve):
            result = codec.verify_content_file(self.root, self.path)
        if replaced:
            self.assert_reason(result, codec.ReasonCode.FILE_CHANGED)
        else:
            # Windows may deny replacement while the read handle is still open.
            self.assert_reason(result, codec.ReasonCode.READ_ERROR)
            self.assertEqual(target.read_bytes(), original_bytes)


class ResultAndCliTests(CodecFixtures):
    def test_diagnostics_have_six_fields_and_explicit_inapplicable_nulls(self):
        empty = codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE).to_dict()
        self.assertEqual(set(empty), DIAGNOSTIC_FIELDS)
        for field in DIAGNOSTIC_FIELDS - {"reason_code"}:
            self.assertIsNone(empty[field])
        success = codec.verify_content(self.record)
        failure = codec.verify_content(b"{broken SECRET}")
        self.assertTrue(success.ok)
        for result in (success, failure):
            diagnostic = result.to_dict()["diagnostic"]
            self.assertEqual(set(diagnostic), DIAGNOSTIC_FIELDS)
            self.assertIsNone(diagnostic["resume_ref"])
        self.assertIsNone(failure.diagnostic.entity_id)
        self.assertNotIn("SECRET", json.dumps(failure.to_dict()))

    def test_content_and_reference_claims_remain_narrow(self):
        content = codec.verify_content(self.record).to_dict()
        reference = codec.verify_reference(self.root, self.reference()).to_dict()
        self.assertEqual(content["verification_kind"], "content")
        self.assertEqual(reference["verification_kind"], "reference")
        self.assertNotEqual(content["claim"], reference["claim"])
        self.assertFalse(content["target_verified"])
        self.assertTrue(reference["target_verified"])
        for value in (content, reference):
            self.assertFalse(value["schema_validated"])
            for forbidden in ("adopted", "task_eligible", "committed", "runtime_passed"):
                self.assertNotIn(forbidden, value)

    def test_api_does_not_modify_records_tasks_historical_proofs_or_publish_pointers(self):
        for path in (".taskmaster/tasks/tasks.json", ".taskmaster/tasks/tasks_back.json",
                     ".taskmaster/tasks/tasks_gameplay.json", "docs/planning/b-route/catalog.v1.json",
                     "logs/historical/frozen-proof.json", "Game.Core/Contracts/Existing.cs"):
            self.write(path, b"Original immutable fixture bytes\r\n")
        before = self.snapshot()
        self.assertTrue(codec.verify_content_file(self.root, self.path).ok)
        self.assertTrue(codec.verify_reference(self.root, self.reference()).ok)
        self.assertFalse(codec.verify_reference(self.root, self.reference(entity_id="missing")).ok)
        self.assertEqual(self.snapshot(), before)

    def prepare_cli(self):
        source = Path(__file__).resolve().parents[1]
        copied = self.workspace / "isolated-cli"
        copied.mkdir()
        for name in ("verify_b_route_reference.py", "_b_route_codec.py", "_planning_skill_common.py"):
            shutil.copyfile(source / name, copied / name)
        return copied / "verify_b_route_reference.py"

    def run_cli(self, script, *arguments):
        # Omit -B deliberately: the entry point itself must suppress bytecode.
        completed = subprocess.run([sys.executable, str(script), *arguments], cwd=self.workspace,
                                   text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(completed.stderr, "")
        value = json.loads(completed.stdout)
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        self.assertEqual(set(value["diagnostic"]), DIAGNOSTIC_FIELDS)
        self.assertFalse(value["schema_validated"])
        return completed, value

    def test_cli_content_reference_positive_negative_and_zero_writes_without_dash_b(self):
        script = self.prepare_cli()
        self.dump("canonical-reference.json", self.reference())
        self.dump("raw-reference.json", self.reference(mode="raw"))
        self.dump("bad-reference.json", self.reference(digest="sha256:" + "0" * 64))
        self.write("duplicate.json", b'{"schema_version":"x","schema_version":"y"}')
        before = self.snapshot(self.workspace)
        commands = [("content", "--path", self.path, True, "content", "ok"),
                    ("reference", "--reference", "canonical-reference.json", True, "reference", "ok"),
                    ("reference", "--reference", "raw-reference.json", True, "reference", "ok"),
                    ("reference", "--reference", "bad-reference.json", False, "reference", "digest_mismatch"),
                    ("content", "--path", "duplicate.json", False, "content", "duplicate_key"),
                    ("content", "--path", "missing.json", False, "content", "file_not_found")]
        for mode, flag, path, expected_ok, kind, reason in commands:
            with self.subTest(mode=mode, path=path):
                completed, value = self.run_cli(script, mode, "--repo-root", str(self.root), flag, path)
                self.assertEqual(completed.returncode, 0 if expected_ok else 1)
                self.assertEqual(value["ok"], expected_ok)
                self.assertEqual(value["verification_kind"], kind)
                self.assertEqual(value["diagnostic"]["reason_code"], reason)
        self.assertEqual(self.snapshot(self.workspace), before)
        self.assertEqual(list(self.workspace.rglob("__pycache__")), [])
        self.assertEqual(list(self.workspace.rglob("*.pyc")), [])

    def test_cli_argument_failures_are_json_and_no_write_option_exists(self):
        script = self.prepare_cli()
        for arguments in ([], ["unknown"], ["content"], ["reference"],
                          ["content", "--repo-root", str(self.root), "--path", self.path, "--write"]):
            with self.subTest(arguments=arguments):
                completed, value = self.run_cli(script, *arguments)
                self.assertNotEqual(completed.returncode, 0)
                self.assertFalse(value["ok"])
                self.assertEqual(value["diagnostic"]["reason_code"], "invalid_argument")
                self.assertIsNone(value["diagnostic"]["stage"])
                expected_kind = arguments[0] if arguments and arguments[0] in ("content", "reference") else None
                self.assertEqual(value["verification_kind"], expected_kind)
                if expected_kind is None:
                    self.assertIsNone(value["claim"])

    def test_codec_and_cli_direct_imports_have_no_engine_model_or_database_dependencies(self):
        folder = Path(__file__).resolve().parents[1]
        allowed = {"__future__", "hashlib", "json", "math", "os", "re", "stat", "dataclasses", "enum",
                   "pathlib", "types", "typing", "_planning_skill_common", "sys", "argparse", "_b_route_codec"}
        for name in ("_b_route_codec.py", "verify_b_route_reference.py"):
            tree = ast.parse((folder / name).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module.split(".")[0])
            self.assertLessEqual(imported, allowed)


@unittest.skipUnless(os.name == "nt", "Actual Windows I/O evidence requires a Windows host")
class WindowsIoTests(CodecFixtures):
    def test_windows_actual_unicode_file_io_and_case_lookup(self):
        path = "Windows Unicode é 中/Plan With Spaces.json"
        self.dump(path, self.record)
        self.assertTrue(codec.verify_reference(self.root, self.reference(path=path)).ok)
        alternate = path.swapcase()
        if not (self.root / alternate).is_file():
            self.skipTest("This Windows directory has case-sensitive lookup enabled")
        self.assertTrue(codec.verify_reference(self.root, self.reference(path=alternate)).ok)

    def make_junction(self, link, target):
        completed = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)

    def test_windows_actual_internal_junction_is_allowed_and_external_junction_rejected(self):
        self.make_junction(self.root / "inside-junction", self.root / "plans")
        self.assertTrue(codec.verify_reference(self.root, self.reference(path="inside-junction/PLAN-7/2.json")).ok)
        outside = self.workspace / "external"
        outside.mkdir()
        (outside / "plan.json").write_bytes((self.root / self.path).read_bytes())
        self.make_junction(self.root / "outside-junction", outside)
        self.assert_reason(codec.verify_reference(self.root, self.reference(path="outside-junction/plan.json")),
                           codec.ReasonCode.UNSAFE_PATH)

    def test_windows_actual_exclusive_file_occupation_cannot_be_reported_as_success(self):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateFileW(str(self.root / self.path), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            result = codec.verify_reference(self.root, self.reference())
            self.assertFalse(result.ok)
            self.assertIn(result.diagnostic.reason_code, (codec.ReasonCode.READ_ERROR, codec.ReasonCode.PATH_UNPROVABLE))
            self.assertEqual(set(result.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)
        finally:
            kernel32.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
