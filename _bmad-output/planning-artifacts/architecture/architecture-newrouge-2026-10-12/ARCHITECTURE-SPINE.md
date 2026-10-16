---
name: newrouge-mvg-planning
type: architecture-spine
purpose: build-substrate
altitude: feature
paradigm: deterministic staged pipeline with explicit state machine and append-only evidence ledger
scope: MVG Capability-increment planning, admission, selection, cumulative merge, recovery, and global audit
status: final
created: 2026-10-12
updated: 2026-10-16
binds:
  - CAP-1
  - CAP-2
  - CAP-3
  - CAP-4
  - CAP-5
  - CAP-6
  - CAP-7
  - CAP-8
  - CAP-9
sources:
  - ../../prds/prd-newrouge-2026-10-11/prd.md
  - ../../../specs/spec-mvg-capability-increment-planning-and-admission-optimization/SPEC.md
  - ../../../specs/spec-mvg-capability-increment-planning-and-admission-optimization/workflow-state-machine.md
  - ../../../specs/spec-mvg-capability-increment-planning-and-admission-optimization/requirement-accounting.md
  - ../../../../workflow.md
  - ../../../../.agents/skills/plan-mvg/SKILL.md
  - ../../../../docs/workflows/mvg-integration-acceptance.md
companions: []
---

# Architecture Spine — NewRouge MVG Planning

> **Incremental target, 2026-10-16.** Existing code implements Capability-local selection, atomic selected checkpoints, Requirement accounting and durable budgets. This update adds lifecycle subprocesses, completed-only cross-run recovery, progressive Knowledge projection and clear. These additions are target behavior until their implementation and targeted tests pass.

## Design Paradigm

The workflow is a deterministic staged pipeline governed by an explicit state machine. Each stage consumes an immutable, hash-bound envelope and emits an append-only receipt; only the coordinator can advance state or mutate the accepted cumulative baseline. The evidence ledger is the audit substrate, not a second source of product authority.

## Invariants & Rules

### AD-1 — Coordinator owns lifecycle state [TARGET]

- **Binds:** CAP-1, CAP-2, CAP-5, CAP-6; `plan_mvg.py`
- **Prevents:** Independently implemented stages inventing incompatible transitions, retries, or terminal states.
- **Rule:** A single run coordinator owns run, Capability checkpoint, dispatch reservations, recovery publication and terminal state. Workers own only their private candidate state and return typed results/receipts; they cannot advance the shared selected sequence. The coordinator independently validates the complete returned candidate and proof before selection.

### AD-2 — Capability authority and readiness are immutable inputs [ADOPTED]

- **Binds:** CAP-1, CAP-4; capability baseline and Chapter 5 readiness preparation.
- **Prevents:** A candidate silently consuming a different Capability version, task scope, Requirement set, or readiness snapshot.
- **Rule:** `capabilities.v1.json`, its hash/source revision, the selected Chapter 5 readiness snapshot, and prepared evidence inventory are frozen before generation. Any identity drift blocks the run and requires a new preparation.

### AD-3 — Candidate lineage isolation is mandatory [ADOPTED]

- **Binds:** CAP-1, CAP-5; generation, repair, and replacement workers.
- **Prevents:** Failed model context or unadmitted artifacts contaminating another candidate or a clean restart.
- **Rule:** Each candidate lifecycle executes in its own OS subprocess and workspace. Generation/repair and independent semantic admission use distinct fresh model invocations. Only complete admitted proposals, identities, proof/receipt references and usage records return to the parent; failure/context history stays audit-only. The parent services file-backed reservation requests before worker model dispatch and rejects unbound outputs. Candidate jobs may execute sequentially; process isolation does not require parallel paid calls. A new Capability receives structured accepted state and relevant boundaries, never earlier model conversation.

### AD-4 — Deterministic gates precede semantic admission [ADOPTED]

- **Binds:** CAP-4; schema, preflight, reference, coverage, handoff, and cumulative-delta validators.
- **Prevents:** Semantic review being used to repair malformed JSON, missing identity, truncated evidence, illegal selectors, or invalid cross-references.
- **Rule:** Complete transport/preflight and deterministic machine validation must pass before an independent semantic admission call. A machine-rejected proposal is not selectable and is never presented as a semantic verdict.

### AD-5 — Selected checkpoint identity is deterministic [TARGET]

- **Binds:** CAP-2, CAP-6; selection, merge, apply, and recovery.
- **Prevents:** Partial cumulative MVG writes, stale candidate application, or replaying one increment twice.
- **Rule:** A selected checkpoint transaction identity is `sha256(canonical_json({schema_version, run_id, capability_id, order_index, base_sha256, proposal_sha256, selection_receipt_sha256}))`. Persist the complete identity tuple before merge writes; the checkpoint payload must contain the same tuple. Recovery locates by this identity and verifies byte-canonical payload equality. The coordinator writes the selected delta and checkpoint atomically; failure leaves the prior accepted baseline unchanged. Replaying an identical transaction is a no-op; the same identity with different payload blocks.

### AD-6 — Route membership and verification ownership are separate [TARGET]

- **Binds:** CAP-3; manifest coverage, Knowledge summaries, and migration validators.
- **Prevents:** A Requirement referenced by multiple flows being counted as multiple completions or being rejected as an invalid duplicate solely because routes differ.
- **Rule:** Route membership uses `(requirement_id, flow_id)`; authoritative verification uses `requirement_id`; evidence references use `(requirement_id, evidence_id)`. Shared evidence may serve multiple routes only with its covered behavior recorded. Duplicate keys are structural errors. Until the proposal/manifest migration is complete, existing `coverage_table` remains the current one-row-per-Requirement projection; migration preserves its disposition as the authoritative record and projects the prior flow owner into route membership.
- **Projection:** `flow` and `other_verification` are satisfied only with their required authoritative evidence; `deferred` is accounted but not satisfied and must retain its authority; `source_gap` is neither satisfied nor complete and blocks planning completion. Reports must expose accounted and satisfied separately.

### AD-7 — Bounded repair and explicit budget termination [TARGET]

- **Binds:** CAP-5; repair, replacement, and run accounting.
- **Prevents:** Infinite retries, silent budget expansion, and classifying execution exhaustion as semantic rejection.
- **Rule:** A stable hard issue receives at most three repairs. The existing 64-call stop-loss belongs to each stable run-level candidate slot/chain across replacements and Capabilities, not an OS process or replacement lineage ID. Each run binds positive `mvg.run_invocation_limit` (default 192); later budget changes require explicit policy and measurement. Coordinator reserves one unit immediately before dispatch; pre-dispatch failures consume none and dispatched failures remain charged. Worker restart never resets counts. Cross-run completed-result adoption consumes no model calls; unfinished work starts fresh and historical charges remain auditable. Exhaustion is an execution state, never a semantic finding.

### AD-8 — Selection admits only complete candidate sets [TARGET]

- **Binds:** CAP-1, CAP-2; comparative selection and Capability progression.
- **Prevents:** A hard-invalid candidate winning by default, an incumbent masking generation failure, or a later Capability consuming an incomplete baseline.
- **Rule:** Exactly three admitted candidates are required for a Capability selection. The accepted baseline is a read-only seed, not a fourth candidate or fallback. Fewer than three admitted candidates produces `selection_blocked_insufficient_admitted_candidates` and does not advance.

### AD-9 — Global audit owns explicit reopen decisions [TARGET]

- **Binds:** CAP-2, CAP-6; final audit and conflict recovery.
- **Prevents:** Local overlap being treated as a global conflict or historical selections being silently rewritten.
- **Rule:** Current-increment repair is the default. Only a source-backed real hard conflict identified by global audit may create a reopen plan. A reopened checkpoint invalidates every later checkpoint in the ordered cumulative ancestry; a narrower closure is allowed only after deterministic rebase proof shows its exact base hash and accepted-predecessor set remain valid. Persist the computed closure and replacement order. The plan records evidence, affected Capability/flow, invalidated downstream increments, and replacement selections; unresolved conflict blocks planning completion.

### AD-10 — Planning and runtime authority remain separate [ADOPTED]

- **Binds:** CAP-6 and all workflow stages.
- **Prevents:** Planning artifacts mutating game runtime state, Taskmaster status, GDD authority, or claiming runtime verification.
- **Rule:** The MVG workflow owns planning evidence and manifest projections only. GDD/Requirements, Taskmaster triplets, Contracts, tests, and runtime acceptance retain their owning authority. `runtime_verified` can be produced only by formal MVG runtime acceptance.

### AD-11 — Relevant complete inputs and clean selection [ADOPTED]

- **Binds:** CAP-1, CAP-4, CAP-5; worker preparation and ranking.
- **Prevents:** Process separation retaining the same duplicated/unrelated model input or leaking candidate failures into selection.
- **Rule:** Coordinator retains full frozen inputs for global machine checks. Candidate models consume complete current authority and directly affected cumulative flows/handoffs/shared-Requirement constraints with hash-bound source inventory. Unrelated raw files and all predecessor conversation are excluded. Existing lossless transport remains mandatory for oversized relevant sources; no clipping. Ranking uses fresh model context and clean machine-verified A/B/C outputs plus relevant comparison context, not candidate workspaces or failure logs. Ranking cannot introduce another semantic veto.

### AD-12 — Completed-only, individual-content recovery [ADOPTED]

- **Binds:** CAP-2, CAP-7; checkpoint, registry and new-run imports.
- **Prevents:** Git commits causing wholesale regeneration, restoring unfinished contexts, or copying an incompatible cumulative snapshot.
- **Rule:** Match by canonical full individual Capability JSON object hash; normalize object key order/JSON encoding layout, preserve array order and value/type changes. Git/catalog metadata are provenance only. Changed hash always regenerates; no similarity matching. Registry eligibility requires an atomically committed checkpoint, current clear epoch and no reopen/invalidation revocation. AD-9 invalidation atomically revokes affected entries and descendants in the same epoch; all lookup paths check revocation, including restart. Same-hash adoption verifies original proof/receipt integrity, prepared dependency compatibility and deterministic delta replay on the current base; on incompatibility regenerate current Capability. Preserve original proof identity and record a new adoption receipt binding source transaction, Capability hash, current base/result and verification. Never rewrite a historical proof or copy its whole cumulative snapshot over a new base. No candidates, repairs, inspections or ranking intermediates are restored on a new execution; atomic-commit uncertainty is still resolved from run.json.

### AD-13 — Committed-prefix projection is immediately visible [ADOPTED]

- **Binds:** CAP-6, CAP-8; Knowledge overview and progress.
- **Prevents:** Hiding successful increments until whole-run apply or claiming partial results are globally complete.
- **Rule:** After each commit/adoption, expose a hash-bound projection of the accepted prefix with completed/total, current item and new/reused provenance. Poll/read reconstructs it from committed coordinator state, never worker files. Progress remains visibly readable while mutation controls are locked; the existing full-page operation overlay must not obscure the increment display. Failure/restart preserves the prefix. Partial planning cannot authorize apply, runtime execution or planning_complete without final global machine audit.

### AD-14 — Clear is a persistent, locked invalidation [ADOPTED]

- **Binds:** CAP-7, CAP-8, CAP-9; API, UI and recovery registry.
- **Prevents:** Old latest/attempt pointers or late worker publication reviving cleared generated results.
- **Rule:** Under the existing authenticated operation lock, clear atomically advances a persistent project-local MVG epoch. Every recovery lookup and publication checks that epoch. In-progress generation/acceptance blocks clear. Remove current generated-display/recovery eligibility while retaining audit and Git-owned regression/runtime/Capability/task authorities. Page shows zero generated completions immediately; old logs and fallback pointers cannot become eligible without a new generation in the current epoch. No recursive audit deletion is required.

### Dependency direction

```mermaid
flowchart LR
  A[Prepared authority and readiness] --> B[Run coordinator]
  B --> C[Candidate lineage workers]
  C --> D[Deterministic machine gates]
  D --> E[Independent semantic admission]
  E --> F[Comparative selection]
  F --> G[Atomic cumulative checkpoint]
  G --> B
  G --> H[Global consistency audit]
  H --> I[Runtime acceptance]
  J[Taskmaster and GDD authorities] --> A
  K[Evidence ledger] -. receipts and hashes .-> B
  K -. receipts and hashes .-> H
```

The arrows are dependency direction. `I` never writes back into planning selection, and `C` never depends on another unadmitted `C` worker.

### Target lifecycle state projection

| Aggregate | States | Allowed forward transitions |
| --- | --- | --- |
| Run | `prepared`, `running`, `blocked`, `planning_complete` | `prepared -> running`; `running -> blocked` or `planning_complete`; blocked resumes only with matching input identity and unused bound budget. |
| Candidate slot | `empty`, `active`, `admitted`, `retired`, `execution_blocked` | `empty -> active`; `active -> admitted`, `retired`, or `execution_blocked`; a replacement gets a new lineage ID, never reopens a retired lineage. |
| Lineage | `generating`, `repairing`, `admitted`, `retired`, `blocked` | `generating -> repairing` on a hard issue; `repairing -> generating` for a new charged attempt; after three failed repairs `repairing -> retired`; a clean lineage starts separately from immutable roots. |
| Capability checkpoint | `pending`, `selected`, `merged`, `reopen_pending`, `invalidated` | `pending -> selected` only with three admitted candidates; `selected -> merged` atomically; global hard conflict may move an ancestor to `reopen_pending` and every later descendant to `invalidated`. |

State changes are coordinator-owned. Only the atomically committed run.json pointer plus its verified checkpoint chain authorizes completed state. Events are append-only audit/notification hints, never a substitute commit point; an event emitted before a failed pointer commit cannot authorize recovery or display. A committed pointer without its later event remains recoverable after deterministic verification.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Identity | Every run, Capability snapshot, candidate lineage, proposal, receipt, checkpoint, and evidence bundle has a stable ID plus content hash. |
| State mutation | Workers are append-only; coordinator-only atomic checkpoint writes; stale baseline hashes fail closed. |
| Error classes | Distinguish preparation/transport/runner errors, deterministic machine issues, semantic hard issues, budget exhaustion, and global conflicts. |
| Recovery | Reuse only exact hash-bound accepted artifacts allowed by the state machine; new page runs and clean restarts do not reuse failed context. |
| Content key | Individual full Capability canonical hash; Git/catalog hashes never substitute, and no similarity fallback. |
| Publication | Local epoch plus committed checkpoint/adoption receipt; partial display grants no whole-run or runtime approval. |
| Requirement accounting | Route membership and authoritative verification use separate projections and stable keys defined in `requirement-accounting.md`. |
| Evidence | Full source text, ranges, citations, receipts, and reassembly proofs remain available under `logs/**`; summaries cannot replace source evidence. |
| Naming | Preserve existing entrypoints and artifact names; new stage/state names must use the stable enums in the implementation contract. |

## Stack

| Name | Version |
| --- | --- |
| Python CI compatibility | 3.12 (MVG integration workflow) |
| .NET SDK repository policy | 8.0.401 with `latestPatch` roll-forward (`global.json`); host resolved 8.0.415 on 2026-10-12 |
| Host platform | Windows-only repository target; version supplied by CI/host policy |

## Structural Seed

```text
scripts/python/
  plan_mvg.py                         # coordinator and stage entrypoints
  _mvg_capability_append.py           # lineage append state machine
  _mvg_capability_generation.py       # proposal schema and machine projection
  _mvg_planning_review.py             # deterministic planning/review validation
scripts/python/tests/                 # contract, append, transport, and recovery tests
docs/testing/mvg/                     # cumulative manifest and acceptance fixtures
logs/ci/mvg-planning/<run-id>/         # run ledger, evidence, receipts, and recovery state
docs/planning/semantic-topology/      # selected Capability authority
```

The tree is a seed, not a second ownership registry. Existing code owns detailed schemas and file layout once the architecture is implemented.

## Capability → Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| CAP-1 candidate sequencing | `plan_mvg.py`, `_mvg_capability_append.py` | AD-1, AD-2, AD-3, AD-8 |
| CAP-2 cumulative merge and checkpoint | coordinator apply/merge path and MVG manifest ledger | AD-5, AD-9 |
| CAP-3 route and verification accounting | proposal validator, coverage projection, Knowledge summary | AD-6, AD-10 |
| CAP-4 transport and admission gates | generation/preflight/review validators and isolated runner | AD-2, AD-4 |
| CAP-5 repair, restart, and budgets | append ledger, repair router, run accounting | AD-3, AD-7 |
| CAP-6 global audit and runtime boundary | final validation, acceptance manifest, runtime acceptance harness | AD-9, AD-10 |
| CAP-7 completed-only recovery | coordinator checkpoint and local recovery registry | AD-5, AD-12, AD-14 |
| CAP-8 progressive display | Knowledge MVG overview and polling UI | AD-10, AD-13 |
| CAP-9 clear | authenticated Knowledge operation and local epoch | AD-12, AD-14 |

## Deferred

- Candidate parallel scheduling is deferred; subprocess isolation and durable coordinator reservation apply even with sequential execution.
- A budget-policy increase is deferred until the relevant-input/subprocess design has measured stage costs; this update does not silently raise limits.
- Runtime/game behavior and deployment topology remain owned by existing workflows. Reuse is local to this project, not a distributed cache or service.
