# B Route Chapter 6 Unified Execution Gate

This document defines the owner boundary for the unified Chapter 6 execution gate (`scripts/python/_b_route_chapter6_gate.py` and `scripts/python/check_b_route_chapter6_gate.py`, exposed via `dev_cli.py b-route-chapter6-gate`).

## Entrypoint

```powershell
py -3 -B scripts/python/dev_cli.py b-route-chapter6-gate --task-id <id> [--root .] [--operation <op>] [--lock-mode none|scope] [--expected-input-set-digest sha256:<hex>] [--report logs/ci/.../report.json]
```

- Default behavior is strictly read-only (`--lock-mode none`, no `--report`), creating zero files or directories.
- `runtime_verified` and `default_b_enabled` are unconditionally `false`.

## Unified Gate Chain

All Chapter 6 public CLI entrypoints (`dev_cli.py run-single-task-chapter6`, `run-acceptance-preflight`, `chapter6-knowledge`, `publish-chapter6-semantics`), direct orchestrator (`run_single_task_chapter6_lane.py`), `_mvg_obligations.check_task_obligations`, and Code Map internal scripts (`check_tdd_execution_plan.py`, `llm_generate_tests_from_acceptance_refs.py`, `build/tdd.py`, `run_review_pipeline.py`, `llm_review_needs_fix_fast.py`, `_llm_review_engine.py`, `acceptance_check.py`, `test.py`, `update_task_test_refs_from_acceptance_refs.py`, `apply_chapter7_status_patch.py`, `run_single_task_light_lane.py`) consume the same gate decision:

1. **Strict ASCII Task ID**: Accepts only ASCII positive integers matching `^[1-9][0-9]*$` (rejects non-ASCII digits such as superscript numerals). Excludes static `docs/planning/b-route/schemas/**` from B-route presence detection.
2. **Story 3.3 Origin Classification** (`resolve_task_origin`):
   - `blocked` or unstable -> fail closed immediately with the six-field `Diagnostic`, `reason_code`, and `return_stage` (`3A..5`). Deleting B governance, manifests, or markers, adding freeform `N/A` / `mvg:N/A` labels, or calling internal scripts directly never falls back to legacy A.
   - `explicit_not_enabled_a` -> verifies zero orphan B readiness/reconciliation markers, zero `capability-apply.pending.json`, and zero unfinished legacy apply journals, then preserves original A behavior without creating B lock artifacts.
   - `A` (frozen A) -> verifies `policy.frozen_a_refs`, zero overlapping unapplied B operations, zero `capability-apply.pending.json`, original A Chapter 5 readiness (`load_task_readiness`), and legacy MVG obligations within the frozen boundary.
   - `B` -> executes the full chain below.
3. **Story 3.5 Common InputSet & Business-Scope Leases** (`resolve_input_set` / `guarded_input_set`):
   - Does not require the target Task to already be `done` (`self_done_required=false`), and prevents `integration_only_owner` self-lock.
   - Enforces the shared lock order (short `metadata` lock -> sorted business `scope_ids`), never holding `writer:planning` during long model/test execution so unrelated scopes proceed concurrently.
   - Parent-to-child reentrancy uses an authenticated receipt under `logs/ci/b-route-chapter6-leases/` verified by contained non-reparse path, secret SHA-256, live `owner_pid`, and non-blocking OS byte-lock (`coordinator_lock`) probe on every claimed scope. Forged environment variables, dead parents, or unlocked scopes are rejected fail-closed.
   - Every boundary revalidation (`revalidate_boundary`) stops execution before model calls, file writes, or test steps when `input_set_digest` drifts or a pending operation appears.
4. **Story 3.6 Stage-5 Obligations** (`extract_stage5_semantics`):
   - Requires committed `stage == "5"` bindings across all applicable plans.
   - Accepts Flow obligations with valid raw-digest-verified MVG manifests and three responsibility categories (`existing_required`, `current_new`, `out_of_scope_future`), OR legal zero-MVG-impact non-Flow tasks with substantive 3B `applicability` rationale, verified `adoption_proof_refs`, and live on-disk `other_verification_refs`.
   - Surfaces `requires_chapter6_reverification=true` (`old_done_covers_new_obligations=false`) when an already `done` Task gains new obligations or planned tests.
5. **Story 3.7 Chapter 5 Readiness** (`verify_b_route_chapter5_readiness`):
   - Requires `ok=true`, `fresh=true`, `closure_allowed=true`, and exact digest/scope equality with live Story 3.3 and Story 3.5 outputs.

## Protected State Writes, Quality Floor, and Observability

- **Task Status Writes**: `write_taskmaster_status_guarded` updates `.taskmaster/tasks/tasks.json` (sole Task status authority) under a short `scope_guard`, verifying `protection.task_definition_projection` before == after.
- **`test_refs` Sync**: `guard_task_test_refs_sync` performs zero disk writes when unchanged and blocks Chapter 6 `test_refs` mutation on B-route/blocked Tasks (`conflict`, `return_stage="3C"`).
- **Triplet Restore Guard**: `scripts/sc/acceptance_check.py` never runs `git checkout` on `.taskmaster/tasks/**` in B-route repos.
- **Legacy Light Lane Guard**: `scripts/python/run_single_task_light_lane.py` blocks before model/write steps on B-route or B-blocked Tasks.
- **Local Quality & Stop-Loss**: Preserves TDD red/green/refactor, `Needs Fix`, P1 must-fix floor (`fix-through P0` rejected), `rerun_guard`, `llm_retry_stop_loss`, `sc_test_retry_stop_loss`, `waste_signals`, and durable marathon/budget history. Local Chapter 6 execution never triggers full MVG, never promotes local PASS/`planned`/empty/skipped reports to `runtime_verified`, and always enforces `--skip-project-health` (zero implicit global Knowledge refresh).
- **Events**: Appends deterministic JSONL records (`execution`, `reuse`, `rework`, `blocked_gate`, `boundary_drift_stopped`) to `chapter6-gate-events.jsonl` under `logs/ci/...`.
