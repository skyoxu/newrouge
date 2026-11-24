# B Route Chapter 6 Live Recovery and Route Revalidation

This document defines the owner boundary for live Chapter 6 recovery and route revalidation (`scripts/python/_b_route_chapter6_recovery.py`, wired into `resume_task.py`, `chapter6_route.py`, `_chapter6_recovery_common.py`, `inspect_run.py`, `run_single_task_chapter6_lane.py`, `scripts/sc/run_review_pipeline.py`, and `scripts/sc/llm_review_needs_fix_fast.py`).

## Scope and Invariants

- Every recommendation, route, inspect, resume, or fork entrypoint revalidates live Story 3.8 unified gate inputs (`InputSet`, Chapter 5 `readiness`, Stage-5 obligations, pending/damaged markers and journals, and live Task/dependency eligibility) before recommending or resuming work.
- Cached `ready`/`ok` fields in `summary.json`, `latest.json`, `active-task`, or stale readiness artifacts never bypass live revalidation.
- `--recommendation-only` on `resume-task`, `chapter6-route`, and `inspect-run` is strictly zero-write: it never repairs `active-task`, never writes `docs/technical-debt.md` (even when `--record-residual` is supplied), and never writes output summary files.
- Pure `explicit_not_enabled_a` repositories preserve compact golden JSON and stdout output compatibility with zero B-route lock or artifact writes.
- `runtime_verified` and `default_b_enabled` are unconditionally `false`.

## Recovery Contracts

1. **Stale Inputs, Pending Journals, and Post-Edit Preservation**:
   - Source, contract, overlay, binding, or plan drift, plus `capability-apply.pending.json`, unfinished legacy apply journals, or pending/damaged B-route operation journals block recovery fail-closed with the six-field `Diagnostic`, `reason_code`, exact `return_stage` (`3A..5`), or original journal `resume_ref`.
   - Unknown scopes block fail-closed.
   - Pre-image/post-image checks (`before_sha256` / `after_sha256` vs live bytes) detect user post-edits on unfinished journal targets and halt with `conflict` + `resume_ref` without overwriting post-edits or auto-applying.
   - Capability model-evidence recovery and file-apply journal recovery retain their separate Epic 2 owner contracts (`plan_capabilities.apply` vs `plan_mvg.apply`).
   - Old A qualification or old `done` status never masks new B obligations (`requires_chapter6_reverification=true`, `old_done_covers_new_obligations=false`).
2. **Status-Only and Unrelated Scope/HEAD Reuse**:
   - Advancing only `.taskmaster/tasks/tasks.json` `status` (preserving `protection.task_definition_projection`), changing an unrelated scope, changing an unrelated `catalog.v1.json` entry, or moving `git HEAD` preserves committed outputs without rewriting historical journal `after` snapshots.
   - Live Task and dependency eligibility is recomputed from live `tasks.json` (reverting a required `keep` dependency from `done` to `in-progress` blocks dynamically; current Task being `pending`/`in-progress` is never rejected because `self_done_required=false`).
   - Reuse is never determined solely from `task_id`, `git HEAD`, or whole-file `tasks.json` hash.
3. **Run Frozen InputSet and Public Lock Order**:
   - Explicit B-route recovery execution freezes `recovery-input-set.json` in `out_dir` under public lock order (short `metadata` lock -> sorted union of prior + live business `scope_ids`; never holding `metadata` or global `writer:planning` across execution, reusing verified Story 3.8 parent-child lease receipts when inherited).
   - If a prior run's frozen `input_set_digest`, `applicable_set_digest`, `scope_ids`, or `binding_revisions` differs from live state (e.g., binding replacement or a new plan joining a shared Task), resuming or forking that run stops immediately without mixing half-old steps and half-new definitions.
4. **Anti-Whitewashing of Failure Budgets, Stop-Loss, and Story 2.9 Epoch/Reopen Revocations**:
   - `scan_durable_recovery_signals` scans all durable `logs/ci/*/sc-review-pipeline-task-<id>*` and `logs/ci/*/sc-needs-fix-fast-task-<id>*` directories chronologically across all date folders.
   - Deleting `active-task` or `latest.json`, opening a new `run_id`, switching entrypoints, or rebuilding Knowledge never clears `rerun_guard`, `sc_test_retry_stop_loss`, `llm_retry_stop_loss`, `waste_signals`, deterministic failure budgets, or Story 2.9 `epoch`/`reopen` revocations unless real product/test source files changed.
