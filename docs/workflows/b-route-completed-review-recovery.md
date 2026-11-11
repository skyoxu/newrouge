# Completed 3B review recovery

This narrow recovery continues an existing Capability candidate after a completed
independent review fails the per-obligation source-citation gate. It does not
accept that review, make an unknown request retryable, allocate a new candidate
seed, or grant formal adoption, readiness, or runtime verification.

The native owner is `scripts/python/_b_route_review_recovery.py`. The controlled
task controller calls `prepare_known_review_retry` only after the original three
generation/generation/review reservations are all demonstrably completed. The
original review must contain no semantic blockers and must fail precisely the
source-support check. Both generated drafts, their complete requests, returned
protocols, receipts, seed, lineage, and charged reservations are verified before
the same append ledger enters its existing review-only branch.

The next request uses the next reservation ordinal in the same run, slot,
generation, and execution. It receives the complete fixed proposal and original
review obligations. It receives no desired verdict or repaired model output.
The producer schema binds each check ID to its own allowed source set; the
canonical coverage, uniqueness, findings, semantic, and source-support gates
remain unchanged. A successful review still requires normal candidate admission,
all other independent candidates, and native comparative selection.

The current producer uses a versioned indexed carrier. Each check ID is the
zero-based position in the complete delivered obligations array; source indices
refer to the complete delivered qualified-source array. The producer schema
constrains each check to its own source positions. The host validates the exact
carrier before mapping only these positions back to their original IDs. It keeps
the model's verdicts, rationale, findings, input metadata, check order, and source
order unchanged. Both raw execution and the decoded canonical review remain
verifiable. Invalid, duplicated, missing, or conflicting checks fail the original
canonical gates; decoding does not repair them. Compact schema-file JSON retains
every value and permits the complete native wrapper to fit the original limit.

Original paid receipts remain auditable even when their output cannot qualify a
candidate. `verify_reserved_call` may recognize the exact retained failed-review
binding for historical accounting. Ordinary admission material verification does
not enable this exception. Neither a different binding nor the old failed review
can become a new admission proof.

## Source identities

The original prepared input and runtime descriptor remain original evidence.
They are not rewritten to claim that later implementation bytes executed earlier
requests. A `newrouge.b-route-planning-run.v2` run carries an explicit committed
source transition; the original v1 writer rejects it before a new reservation.

The historical verifier's subprocess response is an identity witness. Native
requests are reconstructed from the exact prepared raw bytes, preserving nested
object insertion order as required by the recorded request-byte hashes. Canonical
JSON equality alone cannot replace that materialization source.

`_b_route_execution_transition.py` verifies both complete production source
manifests, a precise file-change allowlist, and unchanged canonical semantic
owners. Every prepared-input load invokes the frozen original native verifier
with current source, audit, context, environment, and original prepared inputs.
Historical generation verification is retained under its original source
identity. Its original evidence remains byte-bound; it is not represented as a
fresh execution under the new source. New generation, review, and selection
materials bind the distinct execution source-transition digest. Admission proofs
and handoffs disclose the full transition alongside the legacy runtime base.

The proof describes official runtime configuration and complete input/output
bindings. It does not attest the provider's backend model, hidden reasoning,
physical request count, or billing.

## Persistence and resource limits

The coordinator lock and exclusive durable claim precede recovery state changes.
An immutable record retains the original run, append ledger, control-file bytes,
failed review, generation evidence, and original immutable file manifest. A
committed marker is required before dispatch. Partial transactions fail closed.
The worker receives a new lifecycle directory while all earlier artifacts remain
in place. Original reservation numbers, candidate/lineage charges, native
96-request run and 64-request lineage limits, and active-time pools remain in
force.

A source-identity amendment is available only before any request has used the
first recovery source: the original three completed calls must still be exact,
with no new worker or fourth-call sandbox. It creates a separate immutable
amendment record and committed marker, retains the earlier record and host
failure, and preserves both original and intervening active time. It is not a
way to replay an uncertain request or refresh an exhausted budget.

One further recovery covers a terminal worker that failed input preparation
before reserving a request. It requires the original three completed calls,
unchanged proposal and scope, a cost-only mailbox, the known terminal worker
result, and no fourth-call sandbox. It archives the entire old worker and stage
cost, retains the actual parent run/append snapshots and committed chain, and uses
a distinct worker lifecycle and stage-cost directory. It preserves issue-attempt
counters, charges, clocks, candidate, generation, and execution. An unknown or new
reservation cannot use this path.

For the controlled Story 2.5 campaign, the host also preserves the existing 55
paid-or-unknown slots before Capability. A native pre-reservation funding check
stops before Capability call 44, preserving a complete 192-call MVG allocation
inside the original 290-slot campaign. Successful Capability qualification is
required before that MVG allocation is funded; unused or unknown historical
requests are never refunded.

Relevant offline contracts are covered by `test_b_route_execution_transition.py`,
`test_b_route_review_recovery.py`, and `test_b_route_review_source_policy.py`.
Those tests do not replace real high-configured candidate admission and selection.
