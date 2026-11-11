"""Offline, in-memory binding of operation IDs to complete request content.

This primitive provides no persistence, business-schema validation, allocation,
locking, publication, or authority. The shared codec owns all JSON semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

from _b_route_codec import (
    CODEC_VERSION,
    CodecError,
    Diagnostic,
    ReasonCode,
    Stage,
    canonical_digest,
    raw_digest,
    strict_json_loads,
    validate_business_id,
)


@dataclass(frozen=True)
class FrozenOperationContent:
    operation_id: str
    codec_version: str
    request_raw: bytes
    request_raw_digest: str
    request_digest: str


def _fail(code: ReasonCode, expected: str, actual: str) -> None:
    raise CodecError(Diagnostic(code, Stage.CONTENT, expected=expected, actual=actual))


def _require_type(value: object, kind: type, field: str) -> None:
    if type(value) is not kind:
        _fail(ReasonCode.INVALID_TYPE, field + ": " + kind.__name__, type(value).__name__)


def freeze_content(operation_id: str, request_raw: bytes) -> FrozenOperationContent:
    """Freeze original bytes and the codec identity of the entire JSON object."""
    validate_business_id(operation_id)
    _require_type(request_raw, bytes, "request_raw")
    request = strict_json_loads(request_raw)
    _require_type(request, dict, "request")
    return FrozenOperationContent(
        operation_id=operation_id,
        codec_version=CODEC_VERSION,
        request_raw=request_raw,
        request_raw_digest=raw_digest(request_raw),
        request_digest=canonical_digest(request),
    )


def verify_replay(
    existing: FrozenOperationContent, operation_id: str, request_raw: bytes
) -> FrozenOperationContent:
    """Validate the old binding first, then reuse it only for the same request.

    Successful canonical-equivalent replay returns the original object and raw
    bytes. A frozen dataclass is not a trust boundary: recheck every field before
    considering any new request, including manually constructed instances.
    """
    _require_type(existing, FrozenOperationContent, "existing")
    for field, kind in (
        ("operation_id", str),
        ("codec_version", str),
        ("request_raw", bytes),
        ("request_raw_digest", str),
        ("request_digest", str),
    ):
        _require_type(getattr(existing, field, None), kind, field)
    validate_business_id(existing.operation_id)
    if existing.codec_version != CODEC_VERSION:
        _fail(ReasonCode.UNKNOWN_CODEC_VERSION, CODEC_VERSION, "unsupported codec version")

    confirmed = freeze_content(existing.operation_id, existing.request_raw)
    if existing.request_raw_digest != confirmed.request_raw_digest:
        _fail(ReasonCode.DIGEST_MISMATCH, "intact request_raw_digest", "raw digest mismatch")
    if existing.request_digest != confirmed.request_digest:
        _fail(ReasonCode.DIGEST_MISMATCH, "intact request_digest", "canonical digest mismatch")

    incoming = freeze_content(operation_id, request_raw)
    if incoming.operation_id != existing.operation_id:
        _fail(ReasonCode.CONFLICT, "same operation ID", "different operation ID")
    if incoming.request_digest != existing.request_digest:
        _fail(ReasonCode.CONFLICT, "same complete request content", "different request content")
    return existing
