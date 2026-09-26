# Chapter 3 semantic closure decision

## Decision

Keep the conservative semantic projection as the current workspace candidate and do not write the generated 293-task triplet patch into `.taskmaster/tasks/`.

## Evidence

- Projection conservation: `logs/ci/task-generation/semantic-conservation-report.json` reports `stage=projection`, `status=passed`.
- Candidate sink coverage: `logs/ci/task-generation/coverage-report.json` reports `status=ok`, `missing_blocking=0`.
- Closure computed from generated candidates: `status=passed` before persisted-task verification.
- Persisted Taskmaster views currently contain no `semantic_refs`; the refresh gate therefore reports `persisted_task_semantic_coverage_not_passed`.
- Proposed write patch: `logs/ci/task-generation/task-triplet.patch.json` contains 293 gameplay creates and no back-view operations. This is a structural rewrite, not a safe metadata-only reconciliation.

## Rationale

The generated patch is derived from coarse semantic candidates and has not been reviewed against mature task lifecycle, acceptance, ownership, or duplicate boundaries. Writing it would replace the existing Taskmaster authority without sufficient review.

## Follow-up

Create a reviewed many-to-one mapping from the 575 active Requirements to existing Taskmaster tasks, then compile a metadata-only patch that preserves task IDs and lifecycle fields. Re-run persisted-task closure before promoting planning topology artifacts.

## 2026-09-26 source and projection audit

The first bounded batch review found a simulated projection false positive under `Excludes` and multiple omitted delivery statements. The ledger source inventory also differs from the versioned `chapter3-source-set.json`. Source wording is valid UTF-8; an initial terminal display encoding error was corrected. See `logs/ci/task-generation/chapter3-batch-0001-review.md`.

The next run must first reconcile the authoritative source inventory and review the new bounded batches. The 575 current Requirements are not approved semantic facts; mapping them to mature tasks before that correction would create false traceability.

## Open Needs Fix: build-diversity threshold

The correct-source batch 0006 review found `_bmad-output/gdd.md:381` requiring at least three baseline archetypes per character to reliably clear difficulties 1-3, while `_bmad-output/gdd.md:390` lists a KPI of at least two viable archetypes per character. The latter can be a weaker monitoring floor, but that role is not explicit. Keep the KPI unresolved until product design clarifies whether it is a monitoring metric or acceptance gate. Evidence: `logs/ci/task-generation/chapter3-source-set-batches-0005-0006-review.md`; repair entry: `execution-plans/2026-09-26-chapter3-semantic-reconciliation.md`.

## Resolution: use the KPI floor

The product owner directed the v1 build-diversity threshold to follow the KPI table: at least two viable archetypes per character. ADR-0039 records the threshold change. GDD and epic statements have been aligned; the changed Source Blocks require a new ledger and projection review before the Chapter 3 candidate can be promoted.

## Resolved Needs Fix: M1 normal-enemy balance-test gate

`docs/gdd/m1-playable-setup.md:92` says to add at least two normal enemies before balance testing, while `docs/gdd/m1-playable-setup.zh-CN.md:90` says this is recommended. The Chinese block `SB-8C9677F64415600E` remains `unresolved` with Product design as owner until the acceptance strength is confirmed. Do not promote the candidate as semantically conserved before that decision. Evidence: `logs/ci/task-generation/chapter3-kpi-batches-0017-0018-review.md`; repair entry: `execution-plans/2026-09-26-chapter3-semantic-reconciliation.md`.

The product owner confirmed that adding two normal enemies is advice, not an M1 acceptance gate. The English GDD now says so explicitly, matching the Chinese GDD. In the refreshed candidate, changed English block `SB-1AAD67E9B68A71D5` is reviewed as non-delivery context, and the Chinese block is reviewed as duplicate guidance rather than unresolved. This resolves the wording conflict but does not complete Chapter 3: BATCH-0021 onward remains unreviewed. Evidence: `logs/ci/task-generation/chapter3-kpi-advisory-review.md`.
