# B Route Page Trigger, Five-Entrypoint Parity, and Epic 3 -> Epic 4 Handoff

This document defines the owner boundary for Story 3.12 (`scripts/python/_b_route_entrypoint_parity.py` and CLI `scripts/python/check_b_route_entrypoint_parity.py`, exposed via `dev_cli.py b-route-entrypoint-parity`, and wired into `scripts/python/_project_health_http.py` and `scripts/python/project_health_runtime.py`).

## Entrypoints and Zero-Write Guarantee

- Public CLI: `py -3 -B scripts/python/dev_cli.py b-route-entrypoint-parity [--task-id <id>] [--epic3-handoff] [--root <root>] [--operation <op>] [--report <logs/ci/.../*.json>] [--handoff-report <logs/ci/.../*.json>]`
- Direct CLI owner: `scripts/python/check_b_route_entrypoint_parity.py` (identical flags).
- Loopback page service: `POST /api/knowledge/b-route` in `scripts/python/_project_health_http.py` (protected by the same loopback `Host`, `Origin`, `X-Project-Health-Token`, bounded JSON, and single-flight `operation` lock as `/api/knowledge/runtime`).
- Runtime and MVG pre-flight guards:
  - `scripts/python/project_health_runtime.py` invokes `enforce_runtime_task_gate` and `acquire_runtime_scope_leases` BEFORE snapshot preparation or Godot execution.
  - `scripts/python/_project_health_http.py:run_mvg_manifest` invokes `enforce_mvg_manifest_gate` BEFORE calling `run-mvg-acceptance`.
  - Pure legacy-A repositories (zero B-route traces/markers) pass through cleanly without behavioral regression.
- Zero-write default: strictly zero disk writes unless `--report` or `--handoff-report` targets a new non-existent, non-reparse `logs/ci/.../*.json` path (`write_report` rejects existing paths with `conflict` and stamps `report_path` inside the payload before exclusive `"xb"` creation).
- Invariants: `flow_completed=false`, `runtime_verified=false`, `default_b_enabled=false`, and `self_done_required=false` unconditionally.

## Parity and Governance Contracts

1. **Shared Page Gate and Zero-Publication Guard (`PAGE_SHARED_GATE`)**:
   - `POST /api/knowledge/b-route` (`action in ("gate", "execute", "resume", "route")`) and `project_health_runtime.py` always evaluate live Story 3.8 gate, live Story 3.9 recovery, live Story 3.10 defect routing, and live `.taskmaster/tasks/tasks.json` Task + transitive dependency eligibility.
   - Client-supplied cache fields (`cached_readiness`, `cached_input_set_digest`, `cached_status`, `cached_gate`, `precomputed_ready`) are ignored and explicit bypass flags (`skip_live_gate`, `trust_latest_json`, `trust_scan_snapshot`, `summary_authorization`) are rejected with `conflict`. `logs/ci/project-health-knowledge/latest.json` snapshots never authorize B-route execution.
   - Execution acquires the exact same Story 3.8 business-scope lease (`acquire_chapter6_gate_lease`) across all applicable `scope_ids` without global writer locking.
   - `preview=true`, `recommendation_only=true`, and `mode="workspace"` snapshot and assert zero creation, mutation, or advancement of `docs/knowledge/published/current.json`, `docs/knowledge/published/last-known-good.json`, `logs/ci/project-health-knowledge/latest.json`, `logs/ci/project-health-knowledge/runtime/latest.json`, or `refs/heads/main`.
2. **Five-Entrypoint Decision and Side-Effect Parity (`PARITY_APPLICABLE`)**:
   - `evaluate_entrypoint_parity` checks `cli`, `direct`, `resume`, `route`, and `page` in read-only/pre-effect inspection mode and asserts identical normalized `route`, `admitted`, `public_reason_code`, `blocked_by`, `return_stage`, `applicable_set_digest`, `input_set_digest`, `scope_ids`, `flow_completed=false`, `default_b_enabled=false`, and `self_done_required=false`.
   - Covers legal Flow B-tasks, legal non-Flow B-tasks (`other_verification_refs`, zero fabricated manifest or business API), integration-only owner B-tasks, and frozen-A / `explicit_not_enabled_a` tasks.
3. **Pre-Effect Tamper Rejection Parity (`TAMPER_BEFORE_FX`)**:
   - All five entrypoints and direct underlying modules reject BEFORE any side effect on deleted `task-origins.v1.json` or missing origin slice, deleted bound MVG manifest, blank/missing non-Flow rationale or `other_verification_refs`, damaged `apply-journal.json` / `public-sync-journal.json`, severed Stage-4/5 binding, new committed plan joining a shared Task (`applicable_set_digest` drift invalidating old readiness), and unprovable / `unknown` / `blocked` origins (never falling back to legacy A, including pre-existing legacy `pending` tasks).
4. **Windows Status Advancement and Concurrency Controls (`WIN_CONCURRENCY`)**:
   - Completed 3C/Stage-4/Stage-5 journal replay after legitimate Task status advancement (`in-progress` -> `done`) is a strict no-op preserving the newer live status.
   - Incomplete (`in_progress`/`pending`) journal recovery verifies exact raw preimage digests and halts with `conflict` without overwriting concurrent mutations or post-edits.
   - Relevant Task definition projection changes invalidate `InputSet` (`return_stage="3C"`), while irrelevant non-projection metadata changes preserve and reuse `input_set_digest`.
   - Shared Tasks spanning multiple applicable plans lock the full union of `scope_ids` atomically; unresolved relevant pending journals or candidates remain blocked even if ephemeral lock/marker files are deleted.
5. **Honest Epic 3 -> Epic 4 Handoff (`EPIC3_HANDOFF`)**:
   - `build_epic3_to_epic4_handoff` verifies all Epic 3 consumers, CLI commands, Skills, `AGENTS.md`, and owning docs, while explicitly marking unimplemented Epic 4 / Epic 5 capabilities (`selective_verification_scope_runner`, `complete_b_route_knowledge_progress_display`, `reward_slice_end_to_end_pilot_executed`, `full_repository_b_migration_completed`, `cumulative_full_mvg_runtime_verified`) as `false`.
