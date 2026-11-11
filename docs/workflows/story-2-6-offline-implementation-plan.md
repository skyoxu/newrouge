# Story 2.6 offline implementation boundary

Base: `5f7546f93ba81041f9e8b1453afeb837a2e0f140`.
R11 offline integration base: `b65879246036b73e7b05ed013807aab32e50b3b8`.
The R11 work is explicitly authorized implementation in progress; formal
qualification remains blocked on actual current Story 2.5/1.5/1.6 and Step 4/5.
R10 and all native runs remain preserved. Only the Story 2.6 files/hunks are
imported; Story 2.7 projection/image-classifier primitives are excluded.
This plan implements offline prepare/reserve/inspect support under the user's
delegation. It does not activate B, declare Story 2.5 complete, authorize a model
request, or admit the retained unknown v15 result. Formal Story 2.6 acceptance
still requires current Story 2.5/1.5/1.6 evidence.

Authority: original requirements BR-05/13/14; epics Story 2.6 AC1--5;
architecture `planning-records.md`; ADR-0040. The native selected-run owner,
source proof, protection owner, codec, schema registry and legacy journal remain
authorities. The operation is an auxiliary local envelope, not a seventh formal
record. No formal plan, policy, catalog, Task, binding or manifest is written.

## Fixed storage interface

The existing `_planning_apply_journal` owner adds `validate_operation_request`,
`prepare_operation(root, *, operation_id, request_raw, frozen)`,
`reserve_operation(root, *, operation_id)`, `read_operation(root, *, operation_id)`,
and `operation_inventory(root)`. These are storage primitives; the adoption
service owns eligibility, semantic validation, leases and allocation. No storage
API dispatches a model or applies a formal target.

Store: `logs/ci/b-route-operations/operations/<sha256(UTF8 operation_id)>/operation.json`.
Index: `logs/ci/b-route-operations/pending.json`. The envelope is written first;
the index second. Missing/mismatched index or orphan records are an explicit
conflict, never automatically repaired or ignored. A genuinely empty store has
no operation files and no index. Both prepared and reserved records retain their
allocation claims. Same ID + canonical-equivalent complete request returns the
original envelope/bytes/allocations after complete integrity verification; an
existing damaged operation never gets replaced or reallocated.

Envelope `schema_version=newrouge.b-route-adoption-operation.v1` contains exactly:
`codec_version`, `operation_id`, `state` (prepared|reserved), `request_raw_base64`,
`request_raw_digest`, `request_digest`, `frozen`, `frozen_digest` and schema_version.
`frozen` contains exactly `request` (complete decoded request), `allocations`
(JSON object), `scope_ids` (sorted distinct nonempty strings), `authority_refs`
(raw-bound reference array), and `targets` (fully resolved target array).
`frozen_digest` covers all frozen fields; `request_digest` covers the complete
decoded request. State is mutable only prepared -> reserved. Read/inspect never
creates a directory, rewrites bytes or repairs the index. No completion state is
introduced. Public flags remain formal_adoption/readiness/runtime_verified=false.

Each target contains exactly path, schema_version, before_raw_digest (null or
tagged digest), after_payload, after_raw_digest, verification_mode. The after
bytes use the existing journal owner's JSON indentation/newline serializer.
References contain path, schema_version, raw_digest. Reparse/outside/ambiguous
Windows paths and duplicate target identities fail closed before persistence.

The request has required schema_version (`newrouge.b-route-adoption-request.v1`),
operation_id, material and candidate review_ref, plus optional host_review_ref.
The optional field keeps historical storage readable; current public prepare /
reserve require a complete verified host review. Its subject excludes its own
reference, then the complete request and frozen closure bind the actual raw proof. Material contains exactly planner
(capabilities|mvg), run_id, handoff_ref, protection_ref, authority_refs,
identity_alignment, target_templates and lineage_refs. Identity alignment has
plan, binding, requirements, flows, tasks. Its domain-specific rows and target
templates are interpreted by the single adoption owner; the auxiliary schema
must retain them as complete JSON, never strip unknown data for identity.
Review and protection references must be revalidated by their owners; a caller
setting an approved boolean is insufficient.

## Allocation and public service

`_b_route_adoption.prepare(root, *, operation_id, request_ref)` reads one complete
strict request; `reserve(root, *, operation_id)` accepts no replacement payload;
`inspect(root, *, operation_id)` is read-only. The source run must be an actual
selected 3B run, loaded using the original run owner and full current prepared,
admission, selector, input and recovery checks. No completed event is fabricated.

Allocation happens only under the shared short metadata/scope lease after all
review/protection/before-input checks. New plan/Requirement/Flow IDs are opaque
host allocations, collision-checked against all committed and pending claims.
Existing IDs require explicit reviewed correspondence and current references;
Task IDs are reused only through the current Task join and are never allocated.
Plan and binding revisions are separate monotone positive counters. A new
operation does not silently replace an existing plan or imply Task completion.

## Locks and ownership

Metadata/scopes use the existing operation lease adapter and existing coordinator
lock, with stable SHA256 directory keys. The shared scope owner connects legacy
Capability apply (extract recursion into its internal implementation), MVG apply
(inside existing activity protection), and writable handoff rebinding. Unknown
legacy/new pending scope blocks conservatively. Never hold metadata while waiting
for a run/activity lock or during model work. MVG recovery activity and epoch
protection remain in their original namespace; no default other-project store is
probed by adoption. Any incomplete all-writer integration keeps public prepare /
reserve closed rather than claiming mutual exclusion.

Owners: journal/schema module and its dedicated tests; scope/legacy wiring and
its dedicated tests; root owns adoption service, thin CLI, dev_cli route, docs and
integration. Independent owners use separate short worktrees; root integrates
reviewed commits. Tests are synthetic/offline and cannot grant real qualification.

## Host review continuation at 7987acf4

`_b_route_adoption_review` owns a complete operation-bound subject, strict verdict
schema, mechanically recomputed preservation subset, and replay of independently
completed official high/no-tools execution. Public review-prepare creates an
immutable nondurable preview; review-complete produces the host proof without
model dispatch. Public prepare/reserve first validate this distinct proof, then
repeat native eligibility and instantiate/recheck the exact reviewed proposal.
Original candidate review_ref is never promoted to host review. The shared
operation schema merely gains optional host_review_ref, not a new formal entity.

Semantic execution replay stays outside the global metadata lease. Supporting
raw bytes/current policy and the actual current subject are rechecked under the
existing complete scopes before persistence. No review-specific budget or model
dispatcher is introduced. An externally governed completed review may be consumed;
the retained v15 unknown request, its IDs and all reservations remain untouched.
Formal admission still needs actual current native prerequisites and applicable
review evidence; synthetic eligibility/protocol fixtures provide offline checks.
