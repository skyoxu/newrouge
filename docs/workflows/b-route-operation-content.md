# Offline operation content binding

Status: isolated support component only. This does not start or complete Story
2.6, complete Story 2.5, adopt a plan, or enable the B route. It changes no formal
specification, status, public CLI, or journal integration.

## Owner and scope

`scripts/python/_b_route_operation_content.py` supplies an in-memory primitive
for binding an explicit operation ID to complete request content. It supports the
same-ID/same-content requirement in
[`planning-records.md`](../../_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md),
under its shared apply and recovery protocol. Governance and activation remain
with [ADR-0040](../adr/ADR-0040-b-route-stages-authority-and-activation.md);
formal record schemas remain with the
[record contract](b-route-record-contract.md).

The shared `_b_route_codec` owns business-ID validation, strict JSON parsing,
raw digest, canonical digest, codec version, and structured errors. This module
defines no JSON serializer, canonicalization policy, or business schema.

## API and replay behavior

The frozen dataclass `FrozenOperationContent` has exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `operation_id` | `str` | Explicit ID accepted by `validate_business_id` |
| `codec_version` | `str` | Shared `CODEC_VERSION` |
| `request_raw` | `bytes` | Original complete UTF-8 JSON object bytes |
| `request_raw_digest` | `str` | Shared `raw_digest(request_raw)` |
| `request_digest` | `str` | Shared canonical digest of the complete parsed object |

`freeze_content(operation_id, request_raw)` accepts strict `bytes` and a
top-level JSON object, preserving the original bytes and every field. Unknown
fields are included; there is no whitelist, projection, field removal, default
insertion, or inferred scope. Empty objects are valid at this content-only layer.

`verify_replay(existing, operation_id, request_raw)` first verifies the exact
dataclass type, every stored field type, stored ID, known codec version, stored
raw JSON object, and both stored digest values. Only then does it validate the
incoming request. Valid requests with a different ID or canonical digest raise
shared `CodecError` with `ReasonCode.CONFLICT`. Equivalent content returns the
original `existing` object, retaining its original raw bytes and raw digest even
when incoming whitespace, object key order, or Unicode escaping differs.

Unknown stored codecs fail with `UNKNOWN_CODEC_VERSION`; digest corruption fails
with `DIGEST_MISMATCH`. Type and decode errors use the shared diagnostic codes.
Diagnostics describe the failed condition without embedding raw request content.
Invalid incoming requests are rejected before comparing IDs or content.

Canonical equality follows the current shared codec exactly. Array order,
boolean versus number, integer versus float, Unicode normalization form, and
case can affect identity. Numeric or escape spellings that parse to the same
codec representation can replay. No additional normalization is applied.

## Limits and verification

This is content integrity checking, not authentication. A caller that replaces
raw bytes and both digests consistently has supplied a new internally consistent
binding; there is no trusted external anchor here. A valid changed stored ID is
detected against the supplied replay ID, not by a signature. Frozen dataclasses
prevent ordinary assignment but are revalidated because construction or bypassed
assignment can still supply invalid values.

No files are written, locks acquired, IDs allocated, scopes inferred, model or
network calls made, or authority granted. Persistence, concurrency, resource
budgets, business-schema validation, journal recovery, publication, and caller
integration require their owning services. Request size/depth remains subject to
the existing codec and Python limits. The canonical digest is not a replacement
for the original-byte digest.

Run only the focused stdlib suite from this isolated worktree:

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B scripts/python/tests/test_b_route_operation_content.py
```

The suite uses only in-memory fixtures and no shared scratch directory. It
covers object identity reuse, original bytes, full unknown-field binding,
conflicts, every stored field's type and value tampering, old-before-new
validation, strict parsing, and inherited canonical semantics.
