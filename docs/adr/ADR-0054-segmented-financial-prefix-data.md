# ADR-0054: Segmented financial-prefix DATA contract

- Status: Accepted
- Date: 2026-11-10
- Scope: Supplied-DATA validation only; no financial or default-route activation.
- Extends: [ADR-0042](ADR-0042-shared-segmented-planning-protocol.md)

## Decision

The segmented financial journal needs a versioned multi-node grammar. The old
one-host claim/intent/outcome parser remains unchanged for its original records.
The new executable DATA contract is
`scripts/python/_b_route_segmented_fiscal_prefix.py`; its version constants and
closed field checks are authoritative for this auxiliary format, not formal
planning-record identity or game-domain contracts.

The grammar binds one complete ordered schedule claim, its ordered native-bound
intent/outcome prefix and an optional retained STOP. It retains the complete hold,
charges each distinct intent once, rejects advancement past an unsettled intent,
and preserves deterministic cold replay. Original ADR-0042 campaign, native,
lineage, time and context limits remain unchanged. This does not turn a finite
schedule into a legacy full-profile grant or upgrade old artifacts.

## Authority boundary

Success proves consistency of the supplied bytes and independently supplied
inventory/expected claim only. The caller must obtain those observations from
the actual owner. The function cannot discover a withheld live member, authenticate
the live financial graph, qualify a native result or mint an opaque grant.
Its dispatch, append, redispatch, live-member, native-qualification and grant
flags remain false, including at a complete prefix.

Actual financial admission, the original allocation lease, preclaim checks,
durable publication, own-allocation CAS, born/proof versions, per-node callbacks
and controlled resume still require separate genuine owner integration. No
production allocation, model dispatch, refund, formal adoption, readiness or
default B activation is introduced here.

## Verification

The focused neutral byte-graph tests are
`scripts/python/tests/test_b_route_segmented_fiscal_prefix.py`. They cover complete
Capability/MVG schedules, every settled/unsettled prefix, STOP, corruption,
identity/budget drift and cold replay. Their synthetic data establishes no actual
financial or model qualification. Current execution evidence belongs in logs;
the migration plan records exact source epochs and validation status.
