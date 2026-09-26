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
- Correct-source batch 0001 now has 38 explicitly reviewed blocks and 25 atoms in the separate audit candidate. The remaining 3,232 blocks are still `review_required`; projection compilation stops at batch 0002 as expected.
- Correct-source batch 0002 now has 40 explicitly reviewed blocks and 8 atoms. The two batches total 78/3,270 reviewed blocks; 3,192 remain. Compilation now stops at batch 0003. See `logs/ci/task-generation/chapter3-source-set-batch-0002-review.md`.
- Correct-source batches 0003 and 0004 add 79 reviewed blocks and 39 atoms. The four batches total 157/3,270 reviewed blocks; 3,113 remain. See `logs/ci/task-generation/chapter3-source-set-batches-0003-0004-review.md`.
- Correct-source batches 0005 and 0006 add 80 reviewed blocks and 27 atoms. The six batches total 237/3,270 reviewed blocks; 3,033 remain. Batch 0006 retains one unresolved build-diversity KPI conflict between source lines 381 and 390. See `logs/ci/task-generation/chapter3-source-set-batches-0005-0006-review.md`.

## Next actions

1. Reconcile the versioned source set against the current ledger. The independent source-set build contains 25 sources and 3,270 blocks; the current ledger contains 26 sources and 3,156 blocks. Decide whether the two extra sources should be declared or explicitly retired, and include the missing `_bmad-output/gdd.md`.
2. Rebuild ledger/projection from the corrected source set and review every affected batch with UTF-8 terminal output. Batch 0001 findings for both source inventories are in `logs/ci/task-generation/chapter3-batch-0001-review.md` and `logs/ci/task-generation/chapter3-source-set-batch-0001-review.md`.
   - Resolve the batch 0006 build-diversity threshold: confirm whether the two-archetype KPI is a monitoring floor or an acceptance criterion. Preserve the three-archetype difficulty 1-3 requirement until the owner decision is recorded. Evidence: `logs/ci/task-generation/chapter3-source-set-batches-0005-0006-review.md`.
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
