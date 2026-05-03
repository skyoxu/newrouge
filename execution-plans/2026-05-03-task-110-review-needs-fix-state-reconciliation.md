# Execution Plan - Task 110 Needs-Fix State Reconciliation

## Goal
Reconcile `review-needs-fix` sidecar state with reviewer markdown `Verdict: OK` outputs without violating Chapter6 stop-loss.

## Current Block
- `blocked_by=recent_failure_summary`
- Full rerun is currently forbidden/redundant by inspect recommendation basis.

## Next Steps
1. Inspect child artifact summary:
   - `logs/ci/2026-05-03/sc-review-pipeline-task-110-506ff95e5abc457bb4f794b20b50b73f/child-artifacts/sc-llm-review/summary.json`
2. Compare `review_verdict` source fields used by artifact-reviewer vs markdown final verdict files.
3. Identify mismatch contract (field mapping or stale carry-over) and patch pipeline/reconciliation script.
4. Re-run only the minimal reconciliation path and verify `resume-task --recommendation-only` returns non-needs-fix state.

## Evidence Paths
- `logs/ci/2026-05-03/sc-review-pipeline-task-110-506ff95e5abc457bb4f794b20b50b73f/**`
- `logs/ci/2026-05-03/sc-llm-review-task-110/**`
