# Chapter 3 semantic reconciliation plan

## Current checkpoint

- Branch: `chapter3-init-20260926`
- Source ledger: 3,156 blocks across 83 batches.
- Conservative projection: 575 active Requirements, projection gate passed.
- Candidate coverage: passed.
- Persisted Taskmaster closure: blocked because existing task views have no `semantic_refs`.
- Stable planning topology was not promoted during this run.
- An explicit Taskmaster mention audit found 6 single-task mentions, 26 aggregate mentions, and 543 requirements with no direct task mention. See `logs/ci/task-generation/task-semantic-ref-review.v1.json`.
- The trial metadata write was reverted after the persisted closure gate showed that the generated `INT-*` candidate IDs are not real task IDs. The existing task triplet baseline was re-attested as passed after restoration.
- A separate batch preparation from the versioned source set produced 85 batches, all 3,270 blocks marked `review_required`. Its first batch is documented in `logs/ci/task-generation/chapter3-source-set-batch-0001-review.md`.

## Next actions

1. Reconcile the versioned source set against the current ledger. The independent source-set build contains 25 sources and 3,270 blocks; the current ledger contains 26 sources and 3,156 blocks. Decide whether the two extra sources should be declared or explicitly retired, and include the missing `_bmad-output/gdd.md`.
2. Rebuild ledger/projection from the corrected source set and review every affected batch with UTF-8 terminal output. Batch 0001 findings for both source inventories are in `logs/ci/task-generation/chapter3-batch-0001-review.md` and `logs/ci/task-generation/chapter3-source-set-batch-0001-review.md`.
3. Build a review table mapping each validated active Requirement to an existing Taskmaster task or an explicitly governed non-task sink.
   - Use `py -3 scripts/python/reconcile_task_semantic_refs.py` to refresh the read-only mention audit. Task mentions are hints, not approved mappings.
   - Review the six single-task mentions first, then the aggregate mentions. The 543 without direct mentions require source and acceptance review.
4. Reject mappings that only match by keyword or implementation overlap; retain source and acceptance evidence for each accepted mapping.
5. Reconcile the generated `INT-*` candidates with existing Taskmaster IDs, then compile a metadata-only triplet patch preserving existing IDs, status, priority, ownership, acceptance, and refs. Persisted closure requires candidate identities and semantic refs to match the real task views.
6. Run triplet validators, persisted-task semantic closure, and attestation.
7. Only after all gates pass, run `refresh-knowledge --write-planning-artifacts` and compare the resulting topology with `main`.

## Artifacts

- Candidate patch: `logs/ci/task-generation/task-triplet.patch.json`
- Projection: `logs/ci/task-generation/semantic-requirements.v1.json`
- Closure report: `logs/ci/task-generation/semantic-conservation-report.json`
- Refresh summary: `logs/ci/project-health-knowledge/topology/workspace-last-attempt.json`
