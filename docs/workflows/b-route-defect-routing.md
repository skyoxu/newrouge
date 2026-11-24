# B Route Defect Routing, Anti-Disguise Guard, and Governed Handoff

This document defines the owner boundary for Story 3.10 defect routing (`scripts/python/_b_route_defect_routing.py` and CLI `scripts/python/check_b_route_defect_routing.py`, exposed via `dev_cli.py b-route-defect-routing`, and wired into `resume_task.py`, `chapter6_route.py`, and `run_single_task_chapter6_lane.py`).

## Entrypoint and Zero-Write Guarantee

- Public CLI: `py -3 -B scripts/python/dev_cli.py b-route-defect-routing --task-id <id> [--root <root>] [--run-dir <dir>] [--defect-input <json>] [--delta-intents <json>] [--fix-through P1|P2|P3] [--report <logs/ci/.../*.json>]`
- Direct owner: `scripts/python/check_b_route_defect_routing.py`
- Pure read-only by default: zero disk writes unless `--report` targets a new non-reparse `logs/ci/.../*.json` path. Never auto-executes 3A/3B replanning, never writes `.taskmaster/tasks/*.json`, never allocates permanent Task IDs, and never refreshes global Knowledge.
- Invariants: `runtime_verified=false`, `default_b_enabled=false`, `flow_completed=false`, `cumulative_milestone_completed=false`, and `global_knowledge_refresh="forbidden"` unconditionally.

## Routing Contracts

1. **Pure Implementation Defect Reuse (`IMPL_REUSE`)**:
   - Evaluates live Story 3.8/3.9 gate and recovery state (`evaluate_chapter6_recovery`, `evaluate_chapter6_gate`, `resolve_input_set`).
   - When gameplay definitions, production contracts (`Game.Core/Contracts/**`), ADRs/Overlays, state ownership, handoff/binding design, Task definition projection, and verification obligations are unchanged AND Chapter 5 readiness + Stage-5 obligations are valid, classifies `defect_class="pure_implementation"` (`local_repair_allowed=true`, `reruns_3a_3b=false`).
   - Cites committed 3B `plan_refs`, `binding_refs`, `applicable_flow_closure`, `input_set_digest`, `readiness_path`, required local self-checks, and applicable regressions; never skips Chapter 5 readiness or applicable regressions and never blindly reruns 3A/3B.
2. **Definition / Contract / Ownership / Handoff / Obligation Return & Anti-Disguise (`DEF_RETURN`)**:
   - Any change or declared gap touching sources/ledger (`3A`), gameplay/Flow/ownership/non-Flow applicability (`3B`), Task mapping/split/merge (`3C`), production contracts/ADRs/Overlays/Stage-4 bindings (`4`), or MVG manifests/`other_verification_refs`/Chapter 5 obligations (`5`) sets `local_repair_allowed=false` and emits a structured `governed_handoff` to the earliest `owning_stage` (`3A..5`).
   - Hard anti-disguise checks immediately block with a six-field `Diagnostic`: weakening or deleting `Acceptance` or `Refs:` / `test_refs`; free-text `N/A` / `mvg_applicable=false` / `flow_applicable=false` labels; flipping `status` to `done` while failing/blocked; deleting bound test files or adding `[Fact(Skip=...)]`/`[Theory(Skip=...)]`/`[Ignore]` skip attributes; or weakening cumulative MVG manifests (`update_mvg_baseline._weakens_baseline`).
3. **Governed Business-View Delta Validation (`DELTA_GOV`)**:
   - `validate_repair_task_delta` validates repair task deltas under Story 3.1/3.2 governance without touching `.taskmaster/tasks/*.json` or allocating permanent Task IDs.
   - Blocks synonymous duplicate repair tasks covering the same `(flow_ids, requirement_ids, part_kinds, role)` or high-overlap repair titles without genuinely new requirements; preserves mature Task IDs, `done` status/history, cumulative MVG manifests, and accurate M:N `Task <-> Flow` mappings; blocks old `done` from covering new obligations (`requires_chapter6_reverification=true`); and computes `invalidated_bindings` and `invalidated_readiness_tasks`.
4. **Recurrence Pinpointing, Valid Upstream Reuse, and Anti-Masking (`RECUR_BUDGET`)**:
   - Consumes Story 3.9 `scan_durable_recovery_signals` across all durable `logs/ci/*` runs to pinpoint recurring failure signatures, preserve cumulative retry budgets and failure history, and report `return_stage`.
   - Reuses valid committed 3A/3B/4/5 artifacts across unrelated `git HEAD`, unrelated scope/catalog, or other Task status changes.
   - Blocks masking failures through repeated 3B candidate generation (`candidate_generation_masking_blocked=true`) or global Knowledge refresh (`global_knowledge_refresh="forbidden"`), and never impersonates Flow or cumulative milestone completion.
5. **Honest Verification Breakdown, Needs Fix / P1 Floor, and Telemetry (`REPORT_FLOOR`)**:
   - Separates `local_verification`, `runtime_verification` (`runtime_verified=false`), `manual_obligations`, and `incomplete_obligations` (kept `pending`/`blocked`, never silently dropped).
   - Enforces `Needs Fix` and the `P1` must-fix floor (rejecting `P0` below floor).
   - Records measured telemetry (`active_elapsed_seconds`, `model_invocation_count`, `durable_model_invocation_count`, `reused_upstream_artifacts`, `rework_count`).
