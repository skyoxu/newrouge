# B Route Target-Slice Chapter 7 UI Closure and Evidence Reuse

This document defines the owner boundary for Story 3.11 target-slice Chapter 7 UI closure (`scripts/python/_b_route_chapter7_slice.py` and CLI `scripts/python/check_b_route_chapter7_slice.py`, exposed via `dev_cli.py b-route-chapter7-slice`, and wired into `run_chapter7_ui_wiring.py`, `run_chapter7_backlog_gap.py`, and `apply_chapter7_status_patch.py`).

## Entrypoint and Zero-Write Guarantee

- Public CLI: `py -3 -B scripts/python/dev_cli.py b-route-chapter7-slice [--flow-id <id>] [--slice <bucket>] [--task-id <id>] [--root <root>] [--profile <json>] [--evidence-dir <dir>] [--ui-evidence <json>] [--gap-input <json>] [--operation <op>] [--report <logs/ci/.../*.json>]`
- Direct owner: `scripts/python/check_b_route_chapter7_slice.py` (exact same flags). Related adapted entrypoints: `dev_cli.py run-chapter7-ui-wiring [--slice <bucket>] [--flow-id <id>] [--chapter7-profile-path <path>]`, `dev_cli.py run-chapter7-backlog-gap [--slice <bucket>] [--flow-id <id>] [--chapter7-profile-path <path>] [--ui-evidence <json>]`, and `dev_cli.py apply-chapter7-status-patch --patch <path> [--repo-root <root>] [--dry-run]`.
- Pure read-only by default: zero disk writes unless `--report` targets a new non-existent, non-reparse `logs/ci/.../*.json` path (`write_report` rejects existing files with `conflict` and sets `report_path` inside the payload before exclusive `"xb"` creation). Never mutates `.taskmaster/tasks/*.json`, never allocates permanent Task IDs, and never triggers implicit global Knowledge refresh (`global_knowledge_refresh="not_performed"`).
- Invariants: `runtime_verified=false`, `default_b_enabled=false`, `flow_all_required_obligations_completed=false`, `flow_completed=false`, `cumulative_milestone_completed=false`, `downstream_flow_obligations_preserved=true`, and `cumulative_milestone_obligations_preserved=true` unconditionally.

## Closure Contracts

1. **Target Flow / Slice Scope Without Waiting for Whole Game (`SLICE_SCOPE`)**:
   - Evaluates ONLY the selected target Flow / slice Tasks and committed bindings via Story 3.8 `evaluate_chapter6_gate` and Story 3.5 `resolve_input_set`; unrelated game Tasks or unrelated profile buckets never need to be `done`.
   - Consumes Flow/binding-declared UI obligations (scene entry/return, real engine input, feedback, four-part bindings, manual visual/feel obligations) alongside `docs/workflows/chapter7-profile.json`.
   - Returns `ui_applicability="not_applicable"` (`ok=true`) ONLY for committed non-UI / non-Flow scopes with substantive rationale and live `adoption_proof_refs` / `other_verification_refs` and zero scene/UI implementation objects. Blank or undeclared UI fields fail closed (`missing_required_field` / `semantic_error`, `return_stage="3B"` or `"4"`).
2. **Chapter 6 UI Evidence Reuse Matched to Current InputSet & Test Identity (`EVIDENCE_REUSE`)**:
   - Matches Chapter 6 / runtime UI evidence strictly against the owning Task's current live `input_set_digest`, committed `binding_refs` / condition / revision, and live test file SHA-256 (`test_identity_matched=true`).
   - Reuses verified implementations and obligations (`reused_ui_obligations`), preserving original `task_id`, `flow_id`, `binding_ref`, and raw `evidence_path` + `evidence_sha256` without proposing synonymous duplicate Tasks.
   - Rejects stale `InputSet`, mismatched condition/binding, static-wiring-only (`static_wiring`), and method-call-only (`method_call_only` / `Game.Core.Tests/**`) evidence from satisfying real engine input obligations (`rejected_evidence`).
3. **Honest Scene/Adapter Wiring, Empty/Skipped Evidence, and Manual/Flow Separation (`HONEST_WIRING`)**:
   - Deterministically inspects `.tscn` scenes (including recursive `instance=ExtResource(...)` child scenes) and attached `.cs`/`.gd` adapters (with comments/strings stripped) for broken owner-relative node paths (`GetNode<T>` / `.` / `..` / `%UniqueName`), broken `[connection]` signals or missing handler methods (allowing optional C# access modifiers and built-in Godot `Node` methods), Godot node/C# subclass type mismatches (e.g., `Label` vs `Button`), and lifecycle mismatches (missing script attachment, scene-tree access in C# constructor, unconditional `QueueFree()` in `_Ready()`).
   - Keeps `planned` and unexecuted `implemented` target-scoped bound test refs as `pending`, flags empty/skipped tests (`[Fact(Skip=...)]`, `[IgnoreUntil]`, `skip_test(`, `do_skip(`, zero tests) and failed/skipped runtime evidence as `failed` (`ok=false`), and never treats static wiring or `planned` refs as runtime `passed`.
   - Keeps manual visual/feel/layout/animation obligations independent (`manual_items`, `auto_clearable=false`) and never claims Flow full completion from partial UI closure.
4. **Governed Gap Routing, Business-View Deltas, Protected Status Patch, and Native `.tscn` Preservation (`GOV_GAP_PATCH`)**:
   - Routes UI definition/contract/ownership/binding gaps to exact `owning_stage` (`3A..5`) via Story 3.10 `_b_route_defect_routing`.
   - Emits read-only Story 3.1/3.2 business-view delta candidates (`newrouge.b-route-task-change-intents.v1` with `"operations"`, `task_id=null`, `task_triplet_written=false`), rejecting permanent ID allocation and synonymous duplicates across all three triplet files and intra-batch entries.
   - `run_chapter7_ui_wiring.py --create-tasks` on active B-route repos emits governed delta candidates (`rc=2`) and validates `artifact-manifest.json` instead of writing `.taskmaster/tasks/*.json`; `apply_chapter7_status_patch.py [--repo-root <root>]` checks all three triplet views inside `scope_guard` and forbids clearing mature `done`/`completed`/`complete` Task status on active B-route repos (`reason_code="conflict"`).
   - Preserves native `.tscn` human-authored manual layout/theme/animation regions (including `layout_mode`, `anchors_preset`, `size_flags_*`, and `[sub_resource]` `Animation`/`Theme`/`StyleBox*` body hashes), blocking patches that clobber them.
5. **Traceable Target-Slice Handoff and Zero Implicit Global Knowledge Refresh (`HANDOFF_NOKCP`)**:
   - Emits `handoff` (`newrouge.b-route-chapter7-handoff.v1`) separating `verified_items`, `pending_items`, `manual_items`, and `blocked_items` with non-null `binding_ref`, `task_id`, `flow_id`, and `evidence_ref` (`path` + `raw_digest`) on every item.
   - Preserves downstream Flow and cumulative milestone closure responsibilities and never invokes global Knowledge refresh.
