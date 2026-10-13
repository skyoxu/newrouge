---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-newrouge-2026-10-11/prd.md
  - _bmad-output/planning-artifacts/prds/prd-newrouge-2026-10-11/addendum.md
  - _bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/SPEC.md
  - _bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/capability-baseline.md
  - _bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/workflow-state-machine.md
  - _bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/requirement-accounting.md
  - _bmad-output/planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md
  - workflow.md
  - .agents/skills/plan-mvg/SKILL.md
  - docs/workflows/mvg-integration-acceptance.md
---

# NewRouge MVG Workflow Migration - Epic Breakdown

## Overview

This document decomposes the finalized MVG Capability-increment PRD, SPEC, and Architecture Spine into implementation-ready stories. It covers workflow migration only; it does not expand the GDD, Requirements, Taskmaster triplet, game runtime, or the existing 133-task scope.

## Requirements Inventory

### Functional Requirements

- FR-001: Generate three isolated MVG increment candidates for one frozen Capability at a time and advance only after that Capability is selected and merged.
- FR-002: Compare admitted increments and atomically merge the selected increment into the cumulative MVG with replayable, hash-bound receipts.
- FR-003: Preserve accepted routes, handoffs, tests, outcomes, and mappings while extending cumulative journeys.
- FR-004: Allow one Requirement to participate in multiple distinct flows without treating route membership as duplicate completion.
- FR-005: Keep one authoritative Requirement verification disposition and deduplicated evidence accounting.
- FR-006: Reject incomplete, truncated, identity-mismatched, or otherwise unusable inputs before model generation or semantic admission.
- FR-007: Apply deterministic schema, identity, reference, routing, handoff, and cumulative-delta gates before semantic admission.
- FR-008: Repair stable hard issues locally at most three times, then restart a clean lineage without failed-context contamination.
- FR-009: Repair current-increment conflicts by default and create an explicit evidence-backed reopen plan only for real global hard conflicts.
- FR-010: Run a final global consistency audit after all Capability increments and distinguish planning completion from runtime acceptance.
- FR-011: Persist preparation, generation, repair, admission, selection, merge, recovery, reopen, and audit evidence for deterministic recovery.
- FR-012: Preserve GDD/Requirement/Taskmaster authority and the existing 133-task scope; derived planning artifacts cannot rewrite authoritative sources.

### NonFunctional Requirements

- NFR-001: Determinism and replayability: identical hash-bound inputs and transaction identity must produce an idempotent recovery result.
- NFR-002: Isolation: candidate and clean-restart contexts must not reuse failed proposals, prompts, findings, workspaces, or unadmitted artifacts.
- NFR-003: Bounded execution: each lineage has a 64-call stop-loss and each run has an explicit positive `mvg.run_invocation_limit` (default 192).
- NFR-004: Fail-closed integrity: missing, stale, malformed, or conflicting authority/evidence blocks the affected stage instead of being repaired by prompt text.
- NFR-005: Auditability: every state transition and model attempt records IDs, hashes, error class, timing, and source identity under `logs/**`.
- NFR-006: Platform/toolchain compatibility: preserve the Windows repository target and repository CI toolchain policy.

### Additional Requirements

- The exact Capability file, source revision, hash, and order are frozen before generation; current baseline is the 11-Capability `capabilities.v1.json`.
- The accepted MVG is a read-only seed, not a fourth candidate or a substitute for missing admitted candidates.
- Architecture AD-1 through AD-10 are binding implementation invariants; AD-1, AD-5 through AD-9 require coordinated migration from current behavior.
- Route membership, authoritative verification, and evidence references use separate stable keys.
- The coordinator owns lifecycle state and atomic selected checkpoints; workers return typed receipts.
- Existing entrypoints remain stable; workflow.md §5.4, the plan-mvg Skill, validators, and acceptance documentation must be updated with the migration.
- Chapter 5 readiness, complete evidence transport, isolated runner behavior, and runtime acceptance remain explicit authority boundaries.

### UX Design Requirements

No separate UX design contract was supplied. The implementation must preserve existing CLI/Knowledge entrypoints and expose progress/errors from durable receipts without making UI state authoritative.

### FR Coverage Map

FR-001: Epic 1 - Capability-scoped candidate generation and admission
FR-002: Epic 2 - Comparative selection and cumulative checkpoint merge
FR-003: Epic 2 - Cumulative baseline preservation and replay
FR-004: Epic 3 - Requirement route membership projection
FR-005: Epic 3 - Verification and evidence accounting projection
FR-006: Epic 1 - Frozen input envelope and complete transport gate
FR-007: Epic 1 - Deterministic admission gates
FR-008: Epic 1 - Bounded repair and clean lineage restart
FR-009: Epic 4 - Global conflict audit and explicit reopen closure
FR-010: Epic 4 - Final audit and planning/runtime boundary
FR-011: Epic 2 and Epic 4 - Checkpoint and operational evidence ledger
FR-012: Epic 4 - Authority and scope boundary enforcement

## Epic List

### Epic 1: Clean Capability Candidate Admission

Workflow maintainers can generate and admit three complete, isolated candidates for one frozen Capability without malformed inputs, hard-invalid proposals, or failed-context contamination entering selection. **FRs covered:** FR-001, FR-006, FR-007, FR-008.

### Epic 2: Safe Increment Selection and Cumulative Checkpoints

Workflow maintainers can select one admitted increment per Capability and apply it atomically to the cumulative MVG with deterministic identity, replay safety, and stale-baseline protection. **FRs covered:** FR-002, FR-003, FR-011.

### Epic 3: Correct Requirement Route and Verification Accounting

Planning consumers can distinguish multi-flow Requirement membership from one authoritative verification disposition and shared evidence without inflating completion counts or losing legacy coverage data. **FRs covered:** FR-004, FR-005.

### Epic 4: Bounded Runs, Global Audit, and Authority-Safe Completion

Operators can recover or stop bounded runs, review source-backed cross-Capability conflicts, explicitly reopen affected ancestry, and report planning completion separately from runtime acceptance while preserving authoritative project scope. **FRs covered:** FR-009, FR-010, FR-011, FR-012.

## Epic 1: Clean Capability Candidate Admission

### Story 1.1: Freeze the Capability input envelope

As a workflow maintainer,
I want each run to bind the exact Capability snapshot, Chapter 5 readiness, Requirement scope, evidence inventory, and accepted predecessor,
So that every candidate consumes the same complete authority.

**Acceptance Criteria:**

**Given** a requested Capability run,
**When** preparation completes,
**Then** the run stores source paths, hashes, revision, order index, readiness identity, and prepared evidence inventory in an immutable input envelope.
**And** any source drift, missing readiness, missing required evidence, or reordering blocks generation and reports the mismatched identity.

**Given** auxiliary evidence exceeds one request envelope,
**When** bounded inspection is used,
**Then** all contiguous parts are hash-bound and reassembled deterministically without clipping, summarizing away source text, or reusing another run's receipt.

### Story 1.2: Enforce isolated candidate admission

As a workflow maintainer,
I want each of the three candidate slots to have an isolated lineage and deterministic machine gate before semantic admission,
So that only structurally valid candidates can be compared.

**Acceptance Criteria:**

**Given** a prepared Capability envelope,
**When** candidate generation starts,
**Then** candidate-1, candidate-2, and candidate-3 receive independent lineage IDs, workspaces, invocation receipts, and prepared copies.
**And** no candidate can read another candidate's prompt, proposal, findings, workspace, or unadmitted artifact.

**Given** a generated proposal,
**When** the local gate runs,
**Then** schema, IDs, selectors, references, flow/test bindings, handoffs, Requirement membership, source hashes, and cumulative delta checks run before semantic admission.
**And** a machine-rejected proposal is excluded from selection and is not presented as a semantic verdict.

### Story 1.3: Repair hard issues and restart cleanly

As a workflow maintainer,
I want stable hard issues repaired serially with a three-attempt limit and clean replacement lineages,
So that failures cannot loop indefinitely or contaminate later candidates.

**Acceptance Criteria:**

**Given** one stable hard issue,
**When** repair is attempted,
**Then** no more than three bounded repairs are accepted for that issue, each repair is bound to the current proposal hash and issue scope, and machine validation reruns after each repair.

**Given** the third repair fails,
**When** the lineage is retired,
**Then** a replacement lineage reads only immutable prepared inputs and accepted predecessors, receives a new lineage ID, and cannot read the retired context.
**And** the Capability is never silently skipped; fewer than three admitted candidates blocks selection.

## Epic 2: Safe Increment Selection and Cumulative Checkpoints

### Story 2.1: Select only a complete admitted candidate set

As a workflow maintainer,
I want each Capability selection to compare exactly three admitted increments,
So that hard-invalid or missing candidates cannot be hidden by an incumbent or default winner.

**Acceptance Criteria:**

**Given** fewer than three admitted candidates for the current Capability,
**When** selection is requested,
**Then** the Capability enters `selection_blocked_insufficient_admitted_candidates`, no baseline advances, and the recovery evidence is preserved.

**Given** three admitted candidates,
**When** comparative selection runs,
**Then** every candidate is viable and a losing candidate is rejected only for comparative rank, never for a late semantic hard issue.
**And** the accepted cumulative baseline is treated as a read-only seed, not a fourth candidate or fallback.

### Story 2.2: Commit a deterministic selected checkpoint

As a workflow coordinator,
I want the selected Capability delta and its checkpoint to commit atomically with a deterministic transaction identity,
So that partial writes and duplicate application are impossible.

**Acceptance Criteria:**

**Given** a selected proposal,
**When** the coordinator prepares a merge,
**Then** it derives the checkpoint ID from schema version, run ID, Capability ID, order index, base hash, proposal hash, and selection receipt hash.
**And** the persisted payload contains the same tuple before any cumulative mutation is exposed.

**Given** an apply failure or stale base hash,
**When** the merge is interrupted or retried,
**Then** the prior accepted baseline remains unchanged and the checkpoint is recoverable or blocked with an explicit reason.

### Story 2.3: Make checkpoint replay and recovery idempotent

As a workflow maintainer,
I want recovery to verify checkpoint identity and canonical payload equality,
So that resuming a run cannot apply an increment twice or accept a different payload under the same identity.

**Acceptance Criteria:**

**Given** an existing checkpoint transaction with identical canonical payload,
**When** recovery replays it,
**Then** the operation is a no-op and the next Capability receives the recorded accepted baseline.

**Given** the same transaction ID with different payload, missing receipt, or changed predecessor hash,
**When** recovery inspects it,
**Then** recovery fails closed and records the identity conflict without mutating the accepted manifest.

## Epic 3: Correct Requirement Route and Verification Accounting

### Story 3.1: Persist multi-flow Requirement route membership

As a planning consumer,
I want one Requirement to appear in multiple flows with explicit route-specific meaning,
So that shared behavior is represented without creating duplicate Requirements.

**Acceptance Criteria:**

**Given** a Requirement participates in two distinct flows,
**When** the proposal projection is built,
**Then** it stores one row per unique `(requirement_id, flow_id)` pair with each flow's observable role.
**And** duplicate pairs, unknown Requirements, and invalid flow IDs are rejected deterministically.

**Given** an existing legacy `coverage_table` row,
**When** migration runs,
**Then** the former owner is projected into route membership/owner metadata without losing the unique authoritative verification record.

### Story 3.2: Separate authoritative verification and shared evidence

As a planning consumer,
I want one authoritative disposition per Requirement and deduplicated evidence references,
So that shared evidence supports multiple routes without inflating completion.

**Acceptance Criteria:**

**Given** evidence supports multiple routes for one Requirement,
**When** accounting is computed,
**Then** evidence is keyed by `(requirement_id, evidence_id)`, its covered behavior and routes are recorded, and completion is counted once.

**Given** a Requirement has `flow`, `other_verification`, `deferred`, or `source_gap` disposition,
**When** the report is projected,
**Then** `accounted` and `satisfied` are exposed separately using the architecture mapping, and `source_gap` blocks planning completion.

### Story 3.3: Validate accounting during admission and final audit

As a workflow maintainer,
I want route membership and verification projections checked at admission, replay, and final audit,
So that no migration or candidate can silently weaken Requirement authority.

**Acceptance Criteria:**

**Given** a proposal or cumulative delta,
**When** accounting validation runs,
**Then** all active Requirements have exactly one authoritative disposition, all route pairs are unique, all evidence references resolve to prepared sources, and flow/test references remain bidirectional.

**Given** a legacy projection and the migrated projection,
**When** the compatibility fixture is replayed,
**Then** authoritative dispositions and completion counts are conserved while route membership becomes separately queryable.

## Epic 4: Bounded Runs, Global Audit, and Authority-Safe Completion

### Story 4.1: Enforce run-level budget and durable recovery states

As an operator,
I want model invocation budgets reserved and recorded at dispatch boundaries,
So that execution cost is bounded and interruptions are recoverable without free retries.

**Acceptance Criteria:**

**Given** a new run,
**When** preparation finishes,
**Then** a positive `mvg.run_invocation_limit` and its source are persisted; the default is 192 when no explicit value is supplied.

**Given** a model dispatch is about to occur,
**When** the coordinator reserves the invocation,
**Then** preparation failures before dispatch consume no unit, while timeout, malformed output, or transport failure after dispatch consumes one unit.
**And** lineage exhaustion produces a distinct retired state and run exhaustion produces `run_blocked_budget_exhausted` with recovery evidence.

### Story 4.2: Audit conflicts and compute explicit reopen closure

As a workflow maintainer,
I want global audit to distinguish ordinary overlap from source-backed hard conflict,
So that only justified conflicts reopen history and all affected cumulative descendants are handled safely.

**Acceptance Criteria:**

**Given** repeated Requirements, shared Contracts, or overlapping flows without contradictory authority,
**When** global audit runs,
**Then** the result is reported as non-conflict and no historical checkpoint is reopened.

**Given** source-backed contradictory authority is found,
**When** an explicit reopen plan is created,
**Then** it records evidence, affected Capability/flow, invalidated descendants, replacement order, and selected replacements.
**And** every later cumulative descendant is invalidated unless deterministic rebase proves its exact base hash and accepted-predecessor set unchanged.

### Story 4.3: Publish authority-safe planning completion

As an operator,
I want final reports and owning documentation to distinguish planning completion from runtime acceptance,
So that a valid MVG plan never claims the game has been runtime-verified.

**Acceptance Criteria:**

**Given** all Capability checkpoints, proofs, selections, merges, and the final machine audit are valid,
**When** planning completion is reported,
**Then** the report exposes passed items, hard conflicts, pending obligations, evidence gaps, and runtime acceptance status separately.

**Given** a run attempts to mutate GDD, Requirements, Taskmaster status, game code, or runtime acceptance state,
**When** the authority boundary is checked,
**Then** the operation is rejected and the event is logged under `logs/**`.

**And** `workflow.md` §5.4, `.agents/skills/plan-mvg/SKILL.md`, and MVG acceptance documentation describe the migrated target/current boundary consistently.

## Final Validation

- FR-001 through FR-012 each map to at least one story; FR-011 intentionally spans checkpoint and audit stories.
- All six SPEC capabilities remain represented by the four Epics; no Capability ID was changed.
- Stories are scoped to one workflow slice and contain testable Given/When/Then criteria.
- Story dependencies follow the migration order and do not require a future story within the same Epic.
- Architecture AD-1 through AD-10 are covered; target-only behavior is not described as already deployed.
- The three Architecture Deferred items remain implementation design decisions rather than invented story contracts.
- No story expands GDD, Requirements, Taskmaster scope, or game runtime behavior.
- Readiness result: ready for implementation planning with the four-Epic migration sequence; implementation must resolve Deferred items before freezing their corresponding schemas.
