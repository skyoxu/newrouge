# Requirement Route and Verification Accounting

## Separate concerns

`requirement_route_memberships` records that a Requirement participates in a flow. `requirement_verification` records the single authoritative disposition for that Requirement. Route membership is not a second completion and cannot overwrite the Requirement source.

## Stable keys

| Record | Stable key | Rule |
|---|---|---|
| Route membership | `(requirement_id, flow_id)` | One row per pair; duplicate pair is a structural error. |
| Authoritative verification | `requirement_id` | Exactly one authoritative disposition for each Requirement. |
| Verification evidence reference | `(requirement_id, evidence_id)` | Shared evidence is deduplicated; report its covered behavior and routes. |

## Required behavior

- The same Requirement may appear in different flows when each flow explains its observable role.
- Shared evidence may support several routes, but route count never increases completion count.
- Unknown Requirements, invalid flow IDs, duplicate membership keys, or missing authoritative records are rejected.
- Existing `coverage_table` data is migrated without loss: its unique verification record remains authoritative, and prior ownership becomes route membership or owner metadata.
- Each route-specific test reference is explicit when behavior differs; identical evidence may be shared only when its covered behavior is recorded.

## Admission checks

Before semantic admission, deterministic validation must confirm complete IDs, flow/test bidirectional references, handoff producer/consumer/owner, prepared Contract identity, entrypoint symbols, selector class names, source hashes, and cumulative delta replay. Semantic review only assesses meaning and route continuity after those checks pass.
