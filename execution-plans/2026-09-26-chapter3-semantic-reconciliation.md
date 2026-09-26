# Chapter 3 semantic reconciliation plan

## Current checkpoint

- Branch: `chapter3-init-20260926`
- Source ledger: 3,156 blocks across 83 batches.
- Conservative projection: 575 active Requirements, projection gate passed.
- Candidate coverage: passed.
- Persisted Taskmaster closure: blocked because existing task views have no `semantic_refs`.
- Stable planning topology was not promoted during this run.

## Next actions

1. Build a review table mapping each active Requirement to an existing Taskmaster task or an explicitly governed non-task sink.
2. Reject mappings that only match by keyword or implementation overlap; retain source and acceptance evidence for each accepted mapping.
3. Compile a metadata-only triplet patch preserving existing IDs, status, priority, ownership, acceptance, and refs.
4. Run triplet validators, persisted-task semantic closure, and attestation.
5. Only after all gates pass, run `refresh-knowledge --write-planning-artifacts` and compare the resulting topology with `main`.

## Artifacts

- Candidate patch: `logs/ci/task-generation/task-triplet.patch.json`
- Projection: `logs/ci/task-generation/semantic-requirements.v1.json`
- Closure report: `logs/ci/task-generation/semantic-conservation-report.json`
- Refresh summary: `logs/ci/project-health-knowledge/topology/workspace-last-attempt.json`
