# Adoption operation and host review

本入口按 stage 使用原 owner：review-prepare/review-complete 和 prepare/reserve/inspect
保留正式采纳为 false；apply/verify/publish/read 与 recover 沿用 commit owner。只有
已校验 committed publication 可以返回 formal_adoption=true。当前原生资格与保护证据仍
必须满足。入口不会创建 Task、启用默认 B、自行执行模型、退还预留或重发未知请求；
readiness/runtime_verified 始终为 false。完整顺序与恢复见[原生规划导航](b-route-native-planning-status.md)。

## One public route

```powershell
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage review-prepare --operation-id OP-1 --request logs/ci/reviewed/request.json
py -3 scripts/python/b_route_adoption.py --root . --stage review-complete --operation-id OP-1
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage prepare --operation-id OP-1 --request logs/ci/reviewed/with-host-review.json
py -3 scripts/python/b_route_adoption.py --root . --stage reserve --operation-id OP-1
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage inspect --operation-id OP-1
```

Only review-prepare, review-segmented-preflight and prepare accept --request. The candidate admission remains
review_ref. Attach the returned distinct host_review_ref to the final request;
there is no caller-approved boolean or environment bypass. Both direct/dev_cli
entries and parser dispatch use the same service. All block results use the
single codec diagnostic (reason_code, stage, entity_id, expected, actual,
resume_ref) and exit 2. New review artifacts are auxiliary logs, not a seventh
formal record/schema identity or a separate planning database.

## Explicit same-context observation

Append `--context` to either existing `inspect` or `read` command. It is rejected
on every writing stage. Default outputs remain unchanged. `inspect --context`
keeps the original operation ID, state, scope/allocation IDs, request/frozen
digests and exact owner resume_ref; an original blocked diagnostic stays blocked.
It performs no repair, native resume, reserve, new allocation or reuse.

`read --context` keeps the original protected committed reader. It displays
plan/binding references and revisions from the same schema-validated receipt
buffer used to select the original operation scopes, binds that receipt's raw
bytes and rechecks them before return. No latest-run lookup, context database or
new identity is created. The original reader may initialize ordinary local lock
metadata; formal records are never written or repaired by this observation.

```powershell
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage inspect --operation-id OP-1 --context
py -3 scripts/python/dev_cli.py b-route-adoption --root . --stage read --operation-id OP-1 --context
```

This CLI-only view is `newrouge.b-route-context-view.v1`, not a new persisted
formal record or proof. Published-prefix visibility does not establish global
planning completion. Completed-unit reuse, epoch/reopen and 2.9 unit resume are
explicitly unsupported through this context observation entrypoint. Use the retained native status
owner for its existing recorded clocks/counts/unknowns; its outer status can
recover a checkpoint and is not entirely read-only. The existing A workflow is
retained, and no command activates default B or establishes Story 2.10 acceptance.


For a compensation-resolved operation, `read` keeps the existing resolved-by
route. `read --context` refuses to present that successor as the original receipt
and returns the original owner successor resume reference; no receipt or reuse
authority is invented. Qualified/compensation delivery selection remains limited
to review-prepare and the explicit offline review-segmented-preflight described below.

### Offline compensation segment preflight

`py -3 scripts/python/dev_cli.py b-route-adoption --root <target> --stage review-segmented-preflight --operation-id <new-compensation-id> --request <complete-request.json> --compensation-review-delivery newrouge.b-route-qualified-compensation-review-delivery.v3`

The deterministic CLI derives current published-history materials, freezes a
separate plan/input archive under logs/ci/b-route-compensation-segments, and
checks each full node request against70000 input/96000 input-plus-reserve/1MiB.
The existing compensation output reserve is2000. Repeating the command with
unchanged actual inputs verifies and reuses its offline archive; it does not
retry a model or a business operation. A capacity block returns exit2 with the
measurement and next-node reference retained. This stage does not return a
host_review_ref or runner command and never dispatches/reserves/applies.

The initial conservative closure retains every frame, document and required
check. Safe further semantic decomposition and real segmented execution remain
pending; byte-upper-bound refusal is not a measured tokenizer result. The explicit
lossless segment-input.v1 is not accepted as an old one-turn execution proof.
See [ADR-0057](../adr/ADR-0057-compensation-segmented-cli-preflight.md).

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

## Compensation review materials contract

Compensation keeps the complete persisted v2 host subject and every original
current_files byte. [ADR-0050](../adr/ADR-0050-b-route-compensation-review-materials.md)
versions its model presentation as materials/roles/presentation v1 and its
verdict/proof as explicit compensation v2. A self-contained semantic DAG keeps
all historical subject fields, current/original/new effects and scope, formal
plans/sources, Task status/Acceptance/history and B mappings. Exact semantic
bytes are shared once with every owner/use retained. Owner-verified protocol
and rendered carriers remain bound host evidence; their role never hides a
semantic use at the same path. Unknown or missing ownership fails closed.

Historical v1 proof under the same installed policy uses its exact original
prompt/schema/request and original runtime or mechanical owner. Cross-policy
proof is rejected without re-signing, rewriting or arbitrary historical code
import. The old failed TEMP archive is diagnostic evidence only. New proof
binds full subject, materials, roles, presentation, exact schema/output and real
runner request; it makes no claim that the model read old protocol raw bytes.
Artifacts outside w/ do not become duplicate runner workspace payload files.
The fixed newrouge.b-route-compensation-review-delivery.v1 marker carries the
complete packet directly through the existing compact-v3 codec and complete
decoder instructions. It has no legacy mvg-lossless envelope or failure fallback.
The owner reader retains canonical re-encoding, digest, closed AST and expansion
gates for every cold input. Warm rendering uses produce_canonical_roundtrip:
a metered private stable JSON snapshot, the genuine original producer, every
primitive decoder gate and exact ordered/type-preserving snapshot equivalence
share one unchanged 100M work account. There is no external body/approval/witness
or canonical-skip API. Caller mutations, partial production and resource refusal
fail closed; the helper finally compares the actual full packet and restored
value too. Cold loads/read_prompt still perform full canonical re-encoding, and
the existing v3 body/header and proof bindings are preserved. Its decoder, owner and resource counter
are included in policy pins. The earlier first-generation double-factor failure
is retained; its unpersisted canonical packet size is unknown, and capacity still
requires Root's final-source measurement. Full verification and
encoding finish before WRITER; proof support pins use the validated buffers.
Original byte/token/transcript/codec budgets, admission, unknown and campaign
fences continue unchanged. Root must measure capacity and execute regressions
against the final frozen source; author static checks do not qualify execution.

## Explicit compensation multi-segment review

For a new published-history compensation request, use the existing adoption CLI
with `--stage review-segmented-prepare --operation-id <id> --request <request-ref>`.
Preparation derives and freezes the genuine owner plan and complete originals;
it does not reserve funds, run a model or create a business operation. Inspect
the returned per-node measurements. Literal readiness excludes future parent
outputs, which are measured in full before each actual reservation.

The explicit `review-segmented-execute` stage accepts `--model-request-budget`
as an operator-specified logical call ceiling for this exact operation/plan's
entire lifetime. Supply it only after applicable real authorization and cumulative
budget/unknown accounting are established. There is no default; it is not a
funding grant, old campaign balance or new pool. It must cover the complete finite
plan, is saved once, and cannot be reset or increased on reentry. Every intent,
including failed/unknown, occupies its fixed slot. Each runner still gets budget1.

Without that parameter, execute verifies completed nodes then returns
`authorization_required` before the first new intent/call. `review-segmented-resume`
only replays the completed prefix and returns ready at an undispatched node.
Neither needs a fiscal issuer. An intent without an independently verified complete
publication remains pending/unknown even when execution/output/result files exist;
no retry/refund or replacement ID is invented. After genuine verified execution,
`review-complete` seals the distinct semantic proof. It proves no monetary funds
or old ledger settlement. Business prepare/reserve/commit/recover remain separate.
No preparation or DATA test establishes model approval.

### One explicit completed-refusal repair

For the known published-history two-closure family, the same public CLI supports
`review-segmented-repair-prepare`, `review-segmented-repair-execute` and
`review-segmented-repair-resume`. Prepare requires `--original-source-root` with
the exact original public source DATA; it never executes that source. Execute
requires `--model-request-budget 1` and `--review-authorization-source` recording
the actual operator authorization. The existing original limit2 and both calls
remain occupied; the separate one-call repair makes the cumulative bound3.
This is not a funding grant or automatic retry. A second repair is unsupported.

Only complete official original protocols with an approved business prefix and
a completed explicit governance refusal qualify. Unfinished/transport-unknown
turns cannot qualify. The owner verifies exact business/decoder equivalence and
current-before semantics, derives and measures the complete new request, writes
the additional allowance/intent once, and dispatches one independent high/no-tools
review. A repair intent without completed publication blocks reentry. Original
records and source preimages remain intact.

`review-complete` seals the explicit segmented proof.v2 only after genuine new
approval, full protocol/source/input replay and complete proof binding. That
proof routes through the original saved/history/before-view and compensation
commit consumers. It explicitly distinguishes the retained old-source business
review and fresh current-source governance review. See [ADR-0060](../adr/ADR-0060-one-time-compensation-review-repair.md).

[ADR-0058](../adr/ADR-0058-compensation-multisegment-consumer.md) specifies the
proved two-closure family, complete RPC measurement, lossless identity spelling and original budget constraints.
[ADR-0059](../adr/ADR-0059-compensation-logical-call-limit.md) removes the
unnecessary fixed issuer and defines the logical limit and pure replay boundary. Other families keep a complete closure. The CLI
owns partition, sequence, capacity and continuation; the LLM only reviews content.
