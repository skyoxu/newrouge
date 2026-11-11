# Adoption operation and host review

Story 2.6 exposes owned review preparation/completion and offline operation
prepare/reserve/inspect. It never applies a formal target, publishes a catalog,
creates a Task, activates default B, dispatches a model, refunds a reservation or
recovers an unknown request. Current native 2.5/1.5/1.6 evidence remains required.
All public results retain formal_adoption/readiness/runtime_verified=false.

## One public route

```powershell
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage review-prepare --operation-id OP-1 --request logs/ci/reviewed/request.json
py -3 scripts/python/b_route_adoption.py --root . --stage review-complete --operation-id OP-1
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage prepare --operation-id OP-1 --request logs/ci/reviewed/with-host-review.json
py -3 scripts/python/b_route_adoption.py --root . --stage reserve --operation-id OP-1
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage inspect --operation-id OP-1
```

Only review-prepare and prepare accept --request. The candidate admission remains
review_ref. Attach the returned distinct host_review_ref to the final request;
there is no caller-approved boolean or environment bypass. Both direct/dev_cli
entries and parser dispatch use the same service. All block results use the
single codec diagnostic (reason_code, stage, entity_id, expected, actual,
resume_ref) and exit 2. New review artifacts are auxiliary logs, not a seventh
formal record/schema identity or a separate planning database.

## Review subject and provenance

The owner `_b_route_adoption_review` binds the operation ID, complete normalized
request, candidate/protection/authority references, exact symbolic target
request and concrete nondurable preview, allocations, scopes, before bytes,
related prior records, full native content/prepared sources/protection, affected
catalog relationships and status-independent Task definitions. Additional
explicit authority/lineage files retain full UTF-8 text and raw bytes. Captured
execution histories are revalidated by their native owners; their raw identities
stay in the preview proof closure instead of being duplicated as semantic prose.
Projection/allocation/schema/execution implementation bytes and Python version
participate in the policy identity. Any policy, request, source, target, Task
meaning, scope or semantic evidence drift invalidates the review.

The host review reference is excluded from its own subject to avoid a hash cycle;
its exact file and all supporting raw references are then bound in the complete
operation request and frozen authority closure. Canonical-equivalent request
formatting uses the original reviewed serializer order and allocation proposals.
A review preview is not durable identity assignment; no operation/index claim is
created until public prepare has repeated the actual native chain and review
checks and rechecked committed/pending collisions under shared leases.

## Mechanical and independent semantic review

The machine owner re-proves a documented narrow subset: one plan target, no
binding or Task scope, exact native projection to newly allocated Flow identities
and new/source-owned Requirement identities; or a same-plan revision whose ten
semantic fields are exactly unchanged under reviewed reuse. Extra authorities
must already belong to the prepared input, and the plan has exactly the original
candidate admission proof. Arbitrary binding, correspondence meaning changes,
non-plan targets, removed obligations or other semantic edits do not enter this
subset. Classification is recomputed by the verifier, never trusted from a flag.

For other operations review-prepare writes immutable subject.json, w/prompt.txt,
w/schema.json and request.txt under logs/ci/b-route-adoption-reviews/<operation
SHA256>. It describes an official Codex runner command and required OS execution
capture, but DOES NOT execute it or create a new budget. Existing governed
campaign/dispatch authority must separately authorize any actual invocation.
The command description includes required_environment with
NEWROGUE_CODEX_REASONING_EFFORT=high for the separately governed process; this
owner does not modify global settings. The retained v15 unknown fence remains
in force; do not dispatch or retry it.

review-complete consumes an already completed execution.json and w/output.json
from that same owned review directory. It checks the exact fixed command, OS
completion/stdout receipt, complete runner frame/schema/output, official returned
runtime configuration, requested+returned high, no tools, one fresh ephemeral
thread/turn, and independence from all captured native candidate threads.
The shared protocol replay owner revalidates raw bytes; verdict checks account
for every fixed obligation exactly once and reject missing/duplicate/unknown
checks, hidden findings, incomplete output or any unresolved finding. Actual
provider model/reasoning and physical requests remain unknown; runtime settings
are never called provider attestation. The verifier can consume an existing
captured review without another model invocation.

Protocol replay occurs outside the metadata lease. Supporting bytes and policy
are rechecked at the persistence boundary. Partial/mismatched/blocked artifacts
remain in place and never become a reviewed operation; no implicit retry, ID
replacement, artifact repair, budget release or new review namespace occurs.

## Native projection, binding and lineage

The single typed projector is documented in b-route-native-plan-projection.md.
It preserves structured Graph semantics and binds native_candidate_ref to the
actual verified handoff #/proposal/content and raw digest. Complete original
native denominators/dependencies/unresolved/implementation-object provenance
remain available in that reference. A structurally valid replacement proof or
semantic Graph edit is rejected before operation persistence.

Binding allocation requires exactly one binding target (none requires none).
Use the exact plan_ref marker {"$adopted_plan_ref": true} to derive the shared
canonical PlanRef after rendering opaque host IDs and the complete plan. Two
passes preserve original target order and verify full path/schema/identity/
revision/digest/codec. Existing plan and binding revision counters are independent;
Task IDs come only from the current protected join and are never newly assigned.

New plans cannot invent historical mappings. Replans verify actual prior/current
typed domains, unique complete retained identities and matching Flow rationale.
Command/state identity is preserved; unsupported inferred renaming is rejected.
Same-ID same-request replay retains bytes and allocations; changes are conflicts.

## Evidence boundary

### Protection reference roles

Current protection verification supports
`newrouge.b-route-protection-snapshot.v2` with v2 inventory reference roles and
an exact complete match to the installed inventory owner's rule identity.
Task `evidence_refs` are historical debug attachments: their original references,
Task identities, present raw bytes or explicit missing observations and warnings
remain in the archive and review subject. A missing attachment alone does not
make the current protection capture incomplete. The owner rebuilds roles from
original Task and manifest bytes; callers cannot downgrade a current input by
labelling it historical or suppress a missing observation by re-signing hashes.

Required current sources, native evidence, Task joins and definitions, cumulative
obligations, protected before/after/rollback inputs, authority, scope, currentness
and no-overwrite checks retain their own gates. A file needed by one of those
owners remains required even if it is also a historical Task attachment. Unsafe
or unreadable historical paths and observed drift still fail closed. No Task
status or historical attachment establishes native qualification or runtime
acceptance. v1 protection/inventory artifacts keep their original interpretation.
Old, missing, modified or replaced rules remain unsupported even after relabeling
and re-signing a complete archive. Use a new v2 capture for current material;
the reader never automatically upgrades an old receipt. Rule matching and raw
reconstruction check supported archive semantics, not collection-event provenance
or physical execution of a new capture. Ordinary JSON hashes and collection
metadata are not provenance attestations. Fresh currentness remains the separate
responsibility of current capture/compare and each consuming operation's gates.
See the [reference role contract](b-route-baseline-inventory.md#v2-引用角色合同)
and [ADR-0049 proposal](../adr/ADR-0049-b-route-reference-roles.md).

### Frozen continued-native reader in R11

For an explicit continued run.v2, capture uses the isolated
`_b_route_frozen_native_reader` at the preserved R10 production commit
dc245b3b3d14abd512879369b30692536dfac4fd. Every independent public action
performs a fresh native capture under the existing activity and coordinator
locks. The child does not reacquire those locks, dispatch a model, repair a
counter, write evidence or reinterpret an old proof under R11 rules. The old
run.v1 path keeps its original native owner checks.

The returned complete original handoff/prepared values and native source/run
identity are retained. Full eligibility file, directory membership and absence
pins (including external preserved source/currentness dependencies) participate
in the review subject. The reader implementation participates in policy identity.
Closing verification rechecks the complete within-action closure; it is not a
persisted approval or a cache reusable across public actions or model work.
Incomplete dependency capture must fail closed rather than downgrade freshness.

Before a managed review/prepare/reserve action captures native inputs, the same
scope owner initializes only the fixed `b-route-operations/locks/metadata` and
`locks/scopes` parent namespace. Dynamic scope directories and byte locks remain
owned by the original guard. This timing prevents the action's first lock-root
creation from invalidating its own captured parent-directory membership; it
creates no operation, index, pending claim or reservation. Inspect and inventory
remain read-only. Scope/metadata ownership, native audit, absence and exact
directory checks are unchanged, including rejection of newly observed deep
directory drift. No old capture is rewritten and ADR-0049 reference roles are
not relaxed by this infrastructure initialization.

The review owner likewise initializes only its fixed
`logs/ci/b-route-adoption-reviews` parent before review captures native inputs.
Per-operation directories and subject/proof files are still created only by the
original persistence owner. This keeps an unobserved review output namespace
from changing a captured ancestor between review actions; any actually observed
deep directory or unrelated drift remains a conflict. Late initialization cannot
repair an old capture. Existing immutable subjects and their policy identity are
not rewritten, stripped or automatically upgraded, and no new operation or
reader request is started by this initialization.

The continued branch never calls current R11 planning.load_prepared against the
historical preparation. R10 source epochs, paid failed/unknown liabilities,
partial and p1 paths, exact schemas and high runtime settings retain their
original identities. Independent candidate/source/review, protection, Task,
catalog and ordered scope gates remain required. This offline integration does
not establish current Story 2.5 completion or formal Story 2.6 acceptance.

Positive tests explicitly replace only native eligibility with synthetic fixture
capture; semantic protocol fixtures construct bytes and never contact a provider.
The host owner, strict schemas, protocol parser, storage and leases remain real
in those tests. Such checks cannot confer actual native qualification. Inspect is
read-only, creates no bytecode/logs or repaired index, and grants no admission.
Formal Story 2.6 acceptance requires the complete current native prerequisites
and actual applicable host review evidence; prepared/reserved is not publication.

## Binding-only catalog heads

A current scope may publish its plan through a binding_ref with an empty
plan_refs array. Current plan identity is derived from that verified binding's
plan_ref, using the plan revision (never the independent binding revision).
Review context includes a head selected by either plan_refs or binding_refs.
Thus valid binding-only heads are retained for reuse and dependency scope,
without inventing an unpublished plan or omitting affected relationships.

## Existing semantic execution adapter

After the existing outer campaign/controller has established actual native
prerequisites and authorized the exact new review invocation under its current
budget, it can use `_planning_skill_common.run_isolated_model` with the returned
owned workspace, prompt/schema/output paths, timeout_sec=1800,
wall_timeout_sec=1800, model_request_budget=1, execution_log=execution_capture_ref
and suppress_bytecode=True, using the repository codex_isolated_model_runner.py.
The required high setting is per-process. This is the existing capture adapter;
no new executor, automatic retry or budget is added by the review owner. Its
captured command exactly matches runner_command. This document does not authorize
an invocation while the retained campaign/unknown fence prevents it.

## R47 review repair boundaries

Target path templates retain literal text, escaped braces and only the simple
`{plan_id}`, `{plan_revision}` and `{binding_revision}` allocation fields. Index
or attribute traversal, conversion and nonempty format specifications are rejected
before formatting, including huge widths. An empty specification (`{plan_id:}`)
is accepted as output-equivalent to the simple field (`{plan_id}`). This narrows
the repair author's interpretation; it does not change the user's contract.
Existing valid simple templates serialize as before. CLI JSON escapes non-ASCII characters while retaining their exact values.

Host review policy freshness includes the actual source/protection/inventory,
shared Graph and reader lifetime dependencies. Saved reviews under an earlier
policy are rejected, never re-signed. Nullable codec resume references remain
valid; inspect still returns its actual operation reference. This repair adds no
lease-acquisition requirement from the deferred B9 question.

The existing maintained deterministic gate now includes adoption/operation,
candidate/record and repair modules plus the self-contained native-reader
classes/methods, retaining raw/source/absence/glob closing negatives. Six existing
pinned R22 source-owner integration methods remain separate Root selectors. Future
OperationScopeTests use retained owned TEMP sites and never remove existing sq-*
checkout evidence. Root owns actual execution and acceptance; author static
checks do not establish a current pass. See ADR-0051 and the repair author method
matrix for the exact new source epoch and unexecuted validation plan.
