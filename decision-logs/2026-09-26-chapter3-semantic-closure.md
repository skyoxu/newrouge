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
