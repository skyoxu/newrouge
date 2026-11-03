"""Shared strict JSON identities and read-only B-route reference verification.

This module proves content/reference identity only. Full record schemas, adoption,
Task eligibility, publication, and runtime acceptance belong to later services.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from _planning_skill_common import canonical_sha


CODEC_VERSION = "newrouge.b-route-json.v1"
PLAN_SCHEMA = "newrouge.b-route-plan.v1"
_WINDOWS = os.name == "nt"


class ReasonCode(str, Enum):
    OK = "ok"
    INVALID_JSON = "invalid_json"
    INVALID_UTF8 = "invalid_utf8"
    DUPLICATE_KEY = "duplicate_key"
    NON_FINITE_NUMBER = "non_finite_number"
    INVALID_TYPE = "invalid_type"
    UNKNOWN_SCHEMA = "unknown_schema"
    UNKNOWN_CODEC_VERSION = "unknown_codec_version"
    INVALID_REFERENCE = "invalid_reference"
    INVALID_DIGEST = "invalid_digest"
    UNKNOWN_VERIFICATION_MODE = "unknown_verification_mode"
    UNKNOWN_ENTITY = "unknown_entity"
    REVISION_MISMATCH = "revision_mismatch"
    SCHEMA_MISMATCH = "schema_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    IDENTITY_UNPROVABLE = "identity_unprovable"
    UNSAFE_PATH = "unsafe_path"
    PATH_UNPROVABLE = "path_unprovable"
    FILE_NOT_FOUND = "file_not_found"
    READ_ERROR = "read_error"
    FILE_CHANGED = "file_changed"
    INVALID_ARGUMENT = "invalid_argument"
    REQUIRED_GOVERNANCE_MISSING = "required_governance_missing"
    INPUT_STALE = "input_stale"
    UNPUBLISHED = "unpublished"
    PENDING = "pending"
    CONFLICT = "conflict"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SEMANTIC_ERROR = "semantic_error"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_ENUM = "invalid_enum"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    SCHEMA_RESOURCE_ERROR = "schema_resource_error"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    UNSUPPORTED_LOCATOR = "unsupported_locator"
    DUPLICATE_OWNER = "duplicate_owner"
    MAPPING_MISMATCH = "mapping_mismatch"
    DIGEST_CYCLE = "digest_cycle"


class Stage(str, Enum):
    DECODE = "decode"
    CONTENT = "content"
    REFERENCE = "reference"
    PATH = "path"
    TARGET = "target"
    SCHEMA = "schema"
    BUNDLE = "bundle"


@dataclass(frozen=True)
class Diagnostic:
    reason_code: ReasonCode
    stage: Stage | None = None
    entity_id: str | None = None
    expected: Any = None
    actual: Any = None
    resume_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code.value,
            "stage": self.stage.value if self.stage is not None else None,
            "entity_id": self.entity_id,
            "expected": self.expected,
            "actual": self.actual,
            "resume_ref": self.resume_ref,
        }


class CodecError(ValueError):
    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.reason_code.value)


def _fail(code: ReasonCode, stage: Stage, *, expected: Any = None,
          actual: Any = None, entity_id: str | None = None) -> None:
    raise CodecError(Diagnostic(code, stage, entity_id, expected, actual))


def _string(value: Any, stage: Stage) -> str:
    if type(value) is not str or not value.strip():
        _fail(ReasonCode.INVALID_TYPE, stage, expected="nonempty string", actual=type(value).__name__)
    return value


def _positive_integer(value: Any, stage: Stage) -> int:
    if type(value) is not int or value < 1:
        _fail(ReasonCode.INVALID_TYPE, stage, expected="positive integer", actual=type(value).__name__)
    return value


def validate_task_id(value: Any) -> int:
    """Validate the existing master ID/taskmaster_id type without coercion."""
    return _positive_integer(value, Stage.CONTENT)


def validate_business_id(value: Any) -> str:
    """Keep business-view IDs as original nonempty, unpadded strings."""
    result = _string(value, Stage.CONTENT)
    if result != result.strip():
        _fail(ReasonCode.INVALID_TYPE, Stage.CONTENT, expected="unpadded business ID", actual="padded string")
    return result


def validate_json_value(value: Any) -> None:
    """Reject Python-only values, nonfinite numbers, invalid Unicode, and cycles."""
    active: set[int] = set()

    def visit(item: Any) -> None:
        kind = type(item)
        if item is None or kind in (bool, int):
            return
        if kind is float:
            if not math.isfinite(item):
                _fail(ReasonCode.NON_FINITE_NUMBER, Stage.DECODE, expected="finite number", actual="nonfinite number")
            return
        if kind is str:
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                _fail(ReasonCode.INVALID_UTF8, Stage.DECODE, expected="Unicode scalar string", actual="unpaired surrogate")
            return
        if kind not in (dict, list):
            _fail(ReasonCode.INVALID_TYPE, Stage.DECODE, expected="JSON value", actual=kind.__name__)
        if id(item) in active:
            _fail(ReasonCode.INVALID_JSON, Stage.DECODE, expected="acyclic JSON", actual="cycle")
        active.add(id(item))
        try:
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _fail(ReasonCode.INVALID_TYPE, Stage.DECODE, expected="string object key", actual=type(key).__name__)
                    visit(key)
                    visit(child)
            else:
                for child in item:
                    visit(child)
        finally:
            active.remove(id(item))

    try:
        visit(value)
    except RecursionError:
        _fail(ReasonCode.INVALID_JSON, Stage.DECODE, expected="supported JSON depth", actual="excessive depth")


def strict_json_loads(data: bytes | str) -> Any:
    """Decode strict UTF-8 JSON, including nested duplicate/overflow checks."""
    if type(data) is bytes:
        try:
            data = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(ReasonCode.INVALID_UTF8, Stage.DECODE, expected="UTF-8", actual="invalid byte sequence")
    elif type(data) is not str:
        _fail(ReasonCode.INVALID_TYPE, Stage.DECODE, expected="bytes or string", actual=type(data).__name__)

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                _fail(ReasonCode.DUPLICATE_KEY, Stage.DECODE, expected="unique object keys", actual="duplicate key")
            output[key] = value
        return output

    def reject_constant(_value: str) -> None:
        _fail(ReasonCode.NON_FINITE_NUMBER, Stage.DECODE, expected="finite number", actual="nonfinite literal")

    try:
        value = json.loads(data, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except CodecError:
        raise
    except (ValueError, RecursionError):
        _fail(ReasonCode.INVALID_JSON, Stage.DECODE, expected="JSON document", actual="invalid syntax or depth")
    validate_json_value(value)
    return value


def raw_digest(data: bytes) -> str:
    if type(data) is not bytes:
        _fail(ReasonCode.INVALID_TYPE, Stage.CONTENT, expected="bytes", actual=type(data).__name__)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any, *, codec_version: str = CODEC_VERSION) -> str:
    if codec_version != CODEC_VERSION or type(codec_version) is not str:
        _fail(ReasonCode.UNKNOWN_CODEC_VERSION, Stage.CONTENT, expected=CODEC_VERSION, actual="unsupported codec version")
    validate_json_value(value)
    try:
        return canonical_sha(value)
    except (ValueError, OverflowError, RecursionError):
        _fail(ReasonCode.INVALID_JSON, Stage.CONTENT, expected="canonicalizable JSON", actual="serialization failed")


@dataclass(frozen=True)
class SchemaIdentityAdapter:
    entity_field: str
    revision_field: str

    def identity(self, record: dict[str, Any]) -> tuple[str, int]:
        return (_string(record.get(self.entity_field), Stage.TARGET),
                _positive_integer(record.get(self.revision_field), Stage.TARGET))


# This is the sole schema identity owner. Story 1.4 extends these entries here.
# None means known schema, but no approved entity/revision adapter exists yet.
SCHEMA_IDENTITY_REGISTRY = MappingProxyType({
    "newrouge.b-route-policy.v1": SchemaIdentityAdapter("policy_id", "policy_revision"),
    PLAN_SCHEMA: SchemaIdentityAdapter("plan_id", "revision"),
    "newrouge.b-route-binding.v1": SchemaIdentityAdapter("plan_id", "binding_revision"),
    "newrouge.b-route-origins.v1": SchemaIdentityAdapter("origins_id", "revision"),
    "newrouge.b-route-commit.v1": SchemaIdentityAdapter("operation_id", "revision"),
    "newrouge.b-route-catalog.v1": SchemaIdentityAdapter("catalog_id", "revision"),
    "newrouge.b-route-verification-scope.v1": None,
})


def _schema(value: Any, stage: Stage) -> str:
    result = _string(value, stage)
    if result not in SCHEMA_IDENTITY_REGISTRY:
        _fail(ReasonCode.UNKNOWN_SCHEMA, stage, expected="registered schema_version", actual="unregistered schema_version")
    return result


def _record_identity(value: Any) -> tuple[str, str, int]:
    if type(value) is not dict:
        _fail(ReasonCode.INVALID_TYPE, Stage.CONTENT, expected="record object", actual=type(value).__name__)
    schema = _schema(value.get("schema_version"), Stage.CONTENT)
    adapter = SCHEMA_IDENTITY_REGISTRY[schema]
    if adapter is None:
        _fail(ReasonCode.IDENTITY_UNPROVABLE, Stage.TARGET, expected="approved identity adapter", actual="adapter unavailable")
    entity_id, revision = adapter.identity(value)
    return schema, entity_id, revision


def validate_reference_path(value: Any) -> str:
    """Validate POSIX repository spelling, also rejecting Windows aliases/devices."""
    path = _string(value, Stage.PATH)
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        _fail(ReasonCode.INVALID_UTF8, Stage.PATH, expected="UTF-8 path", actual="unpaired surrogate")
    if path.startswith("/") or any(char in path for char in '\\:<>"|?*') or any(ord(char) < 32 for char in path):
        _fail(ReasonCode.UNSAFE_PATH, Stage.PATH, expected="repository-relative POSIX path", actual="absolute or nonportable path")
    depth = 0
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                _fail(ReasonCode.UNSAFE_PATH, Stage.PATH, expected="path within repository", actual="root escape")
            continue
        if part.endswith((" ", ".")) or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", part):
            _fail(ReasonCode.UNSAFE_PATH, Stage.PATH, expected="portable file component", actual="Windows alias or device")
        depth += 1
    return path


def resolve_reference_path(root: Path, value: str) -> Path:
    path = validate_reference_path(value)
    try:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            _fail(ReasonCode.PATH_UNPROVABLE, Stage.PATH, expected="repository directory", actual="not a directory")
        candidate = base
        for part in path.split("/"):
            if part in ("", "."):
                continue
            candidate = (candidate / part).resolve(strict=True)
            if not candidate.is_relative_to(base):
                _fail(ReasonCode.UNSAFE_PATH, Stage.PATH, expected="resolved path within repository", actual="root-external target")
        return candidate
    except FileNotFoundError:
        _fail(ReasonCode.FILE_NOT_FOUND, Stage.PATH, expected="existing reference target", actual="missing path")
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, CodecError):
            raise
        _fail(ReasonCode.PATH_UNPROVABLE, Stage.PATH, expected="provable contained path", actual="resolution failed")


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _cross_stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Compare path and descriptor observations using matching field semantics."""
    if not _WINDOWS:
        return _stat_identity(info)
    # CPython 3.12 Windows path stat uses creation time for ctime, while fstat
    # can expose ChangeTime. Keep ctime in same-source checks and compare the
    # explicit birthtime across sources; never infer missing birthtime from it.
    birthtime = getattr(info, "st_birthtime_ns", None)
    if type(birthtime) is not int:
        _fail(ReasonCode.PATH_UNPROVABLE, Stage.PATH,
              expected="Windows birthtime identity", actual="birthtime unavailable")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, birthtime


def read_reference_bytes(root: Path, path: str) -> bytes:
    """Read a contained regular file and detect observed replacement/read drift.

    This check does not supply isolation from uncooperative concurrent writers.
    """
    try:
        resolved = resolve_reference_path(root, path)
        before = resolved.stat()
        if not stat.S_ISREG(before.st_mode):
            _fail(ReasonCode.READ_ERROR, Stage.PATH, expected="regular file", actual="nonregular target")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(resolved, flags), "rb", buffering=0) as stream:
            opened = os.fstat(stream.fileno())
            data = stream.read()
            after = os.fstat(stream.fileno())
            current = resolve_reference_path(root, path)
            current_info = current.stat()
            # Metadata can remain equal after a write; read the raw handle again.
            stream.seek(0)
            confirmed = stream.read()
            final = os.fstat(stream.fileno())
            if (confirmed != data or current != resolved or _stat_identity(before) != _stat_identity(current_info)
                    or _stat_identity(opened) != _stat_identity(after)
                    or _stat_identity(after) != _stat_identity(final)
                    or _cross_stat_identity(before) != _cross_stat_identity(opened)
                    or _cross_stat_identity(final) != _cross_stat_identity(current_info)):
                _fail(ReasonCode.FILE_CHANGED, Stage.PATH, expected="stable observed file identity", actual="file changed during read")
        return data
    except CodecError:
        raise
    except OSError:
        _fail(ReasonCode.READ_ERROR, Stage.PATH, expected="readable reference target", actual="file read failed")


@dataclass(frozen=True)
class TypedReference:
    path: str
    schema_version: str
    entity_id: str
    revision: int
    digest: str
    verification_mode: str
    codec_version: str | None

    def __post_init__(self) -> None:
        validate_json_value([self.path, self.schema_version, self.entity_id, self.revision,
                             self.digest, self.verification_mode, self.codec_version])
        validate_reference_path(self.path)
        _schema(self.schema_version, Stage.REFERENCE)
        _string(self.entity_id, Stage.REFERENCE)
        _positive_integer(self.revision, Stage.REFERENCE)
        if type(self.digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest) is None:
            _fail(ReasonCode.INVALID_DIGEST, Stage.REFERENCE, expected="sha256:<64 lowercase hex digits>", actual="invalid digest")
        if type(self.verification_mode) is not str or self.verification_mode not in ("raw", "canonical"):
            _fail(ReasonCode.UNKNOWN_VERIFICATION_MODE, Stage.REFERENCE, expected="raw or canonical", actual="unsupported verification mode")
        if self.verification_mode == "canonical":
            if type(self.codec_version) is not str or self.codec_version != CODEC_VERSION:
                _fail(ReasonCode.UNKNOWN_CODEC_VERSION, Stage.REFERENCE, expected=CODEC_VERSION, actual="missing or unsupported codec version")
        elif self.codec_version is not None:
            _fail(ReasonCode.INVALID_REFERENCE, Stage.REFERENCE, expected="null codec_version for raw bytes", actual="codec supplied for raw bytes")

    @classmethod
    def from_value(cls, value: Any) -> TypedReference:
        validate_json_value(value)
        fields = {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}
        if type(value) is not dict or set(value) != fields:
            _fail(ReasonCode.INVALID_REFERENCE, Stage.REFERENCE, expected="complete typed reference fields", actual="missing or unknown reference fields")
        return cls(**value)


@dataclass(frozen=True)
class ContentIdentity:
    raw_digest: str | None
    canonical_digest: str
    codec_version: str = CODEC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {"raw_digest": self.raw_digest, "canonical_digest": self.canonical_digest,
                "codec_version": self.codec_version}


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    verification_kind: str | None
    diagnostic: Diagnostic
    content_identity: ContentIdentity | None = None
    entity_id: str | None = None
    revision: int | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verification_kind": self.verification_kind,
            "claim": self.verification_kind + "_identity_only" if self.verification_kind is not None else None,
            "schema_validated": False,
            "target_verified": self.ok and self.verification_kind == "reference",
            "diagnostic": self.diagnostic.to_dict(),
            "content_identity": self.content_identity.to_dict() if self.content_identity is not None else None,
            "entity_id": self.entity_id,
            "revision": self.revision,
            "path": self.path,
        }


def failure_result(kind: str | None, diagnostic: Diagnostic, *, path: str | None = None) -> VerificationResult:
    return VerificationResult(False, kind, diagnostic, path=path)


def _decode_content(data: Any) -> tuple[Any, ContentIdentity]:
    if type(data) in (bytes, str):
        value = strict_json_loads(data)
        source = data if type(data) is bytes else data.encode("utf-8")
    else:
        value, source = data, None
        validate_json_value(value)
    identity = ContentIdentity(raw_digest(source) if source is not None else None, canonical_digest(value))
    return value, identity


def _content(data: Any) -> tuple[Any, ContentIdentity, tuple[str, str, int]]:
    value, identity = _decode_content(data)
    return value, identity, _record_identity(value)


def verify_content(data: Any) -> VerificationResult:
    try:
        _value, identity, (_schema_id, entity_id, revision) = _content(data)
        return VerificationResult(True, "content", Diagnostic(ReasonCode.OK, Stage.CONTENT, entity_id), identity, entity_id, revision)
    except CodecError as error:
        return failure_result("content", error.diagnostic)


def verify_content_file(root: Path, path: str) -> VerificationResult:
    try:
        result = verify_content(read_reference_bytes(root, path))
        return VerificationResult(result.ok, result.verification_kind, result.diagnostic,
                                  result.content_identity, result.entity_id, result.revision, path)
    except CodecError as error:
        return failure_result("content", error.diagnostic, path=path if type(path) is str else None)


def verify_reference(root: Path, reference: Any) -> VerificationResult:
    path = None
    try:
        if type(reference) in (bytes, str):
            reference = strict_json_loads(reference)
        if type(reference) is dict and type(reference.get("path")) is str:
            path = reference["path"]
        ref = reference if type(reference) is TypedReference else TypedReference.from_value(reference)
        path = ref.path
        value, identity = _decode_content(read_reference_bytes(root, ref.path))
        if type(value) is not dict:
            _fail(ReasonCode.INVALID_TYPE, Stage.CONTENT, expected="record object", actual=type(value).__name__)
        schema = _schema(value.get("schema_version"), Stage.CONTENT)
        if schema != ref.schema_version:
            _fail(ReasonCode.SCHEMA_MISMATCH, Stage.TARGET, expected=ref.schema_version, actual=schema, entity_id=ref.entity_id)
        _schema_id, entity_id, revision = _record_identity(value)
        if entity_id != ref.entity_id:
            _fail(ReasonCode.UNKNOWN_ENTITY, Stage.TARGET, expected=ref.entity_id, actual=entity_id, entity_id=ref.entity_id)
        if revision != ref.revision:
            _fail(ReasonCode.REVISION_MISMATCH, Stage.TARGET, expected=ref.revision, actual=revision, entity_id=entity_id)
        actual = identity.raw_digest if ref.verification_mode == "raw" else identity.canonical_digest
        if actual != ref.digest:
            _fail(ReasonCode.DIGEST_MISMATCH, Stage.TARGET, expected=ref.digest, actual=actual, entity_id=entity_id)
        return VerificationResult(True, "reference", Diagnostic(ReasonCode.OK, Stage.REFERENCE, entity_id), identity, entity_id, revision, path)
    except CodecError as error:
        return failure_result("reference", error.diagnostic, path=path)
