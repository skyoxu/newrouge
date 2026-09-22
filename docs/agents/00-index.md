# Agents Docs Index

Purpose: keep [AGENTS.md](../../AGENTS.md) short and move durable guidance here.

## Read Order After Context Reset

Do not preload the whole documentation stack. Route from the current task.

1. Read root `AGENTS.md` for global invariants and the task router.
2. If the task is recovery, run `resume-task --recommendation-only` first; for Chapter 6 add `chapter6-route --recommendation-only`.
3. If the task is not recovery, open only the owning workflow/doc listed in the root route table.
4. Read direct authoritative sources required by that task: Task/Requirement/Acceptance, related ADR/Overlay/Contract, or an explicitly bound plan/decision.
5. Expand run sidecars only when the compact recovery fields do not support the next decision. Read `run-events.jsonl` only for event/turn ordering.
6. Never select the newest Execution Plan or Decision Log merely because it is newest.

Recovery shortcut:
- `resume-task --recommendation-only` and `inspect-run --recommendation-only` should expose the same canonical compact recovery semantics; disagreement is a bug.
- `chapter6-route --recommendation-only` is the cheapest Chapter 6 go/no-go router.
- `planned-only`, `artifact_integrity`, stale readiness, or damaged/unknown sidecars are fail-closed.
- Knowledge shadow is optional. On `fallback_required`, read direct authority instead of refreshing global Knowledge.

## Chapter 6 Fast-Ship Card

Use this when you need the cheapest safe daily loop for a single task. Full details live in [workflow.md](../../workflow.md).

1. `py -3 scripts/python/dev_cli.py resume-task --task-id <id>`
   - Quick recommendation-only read: `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only`
2. Before paying for another `6.7` or `6.8`, run `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only`
3. `py -3 scripts/sc/check_tdd_execution_plan.py --task-id <id> --tdd-stage red-first --verify unit --execution-plan-policy draft`
4. `6.4 -> 6.5 -> 6.6` in order, keeping the first red run as light as possible
5. `6.5` hard-requires the latest clean `6.4 red-first` summary, and `6.6` hard-requires the latest clean `6.5 green` summary.
6. `py -3 scripts/sc/run_review_pipeline.py --task-id <id> --godot-bin "$env:GODOT_BIN" --delivery-profile fast-ship`
7. Before rerunning `6.7` or `6.8`, read `summary.json`, `latest.json`, `repair-guide.md`, `run-events.jsonl`, and the child step summaries first
8. Check `reason`, `run_type`, `reuse_mode`, `artifact_integrity`, and `diagnostics` in `latest.json` or `summary.json` first; pay attention to `rerun_guard`, `reuse_decision`, `acceptance_preflight`, `llm_timeout_memory`, and stop-loss signals.
9. Read `Chapter6 next action`, `Chapter6 can skip 6.7`, `Chapter6 can go to 6.8`, and `Chapter6 blocked by` before paying for another full rerun.
10. Treat `Chapter6 blocked by=rerun_guard` as a stop-loss signal, `llm_retry_stop_loss` as a narrow LLM-only follow-up, `sc_test_retry_stop_loss` as a known-unit-root-cause stop marker, `waste_signals` as a hint that you should stop paying engine-lane cost before fixing the unit/root cause failure, and `artifact_integrity` as a signal to trust the last real bundle before any rerun choice.
11. If recovery shows `run_type = planned-only` or `reason = planned_only_incomplete`, treat the bundle as a `planned-only terminal bundle`; read evidence from it, but do not reopen `6.7` or `6.8` from it.
12. Only run `6.8` when the current edits directly hit the previous reviewer anchors.
13. If deterministic already passed and only `sc-llm-review` failed, prefer the narrow path that reuses deterministic and reruns only LLM; do not reopen a full `6.7` unless you explicitly need `--allow-full-rerun`.
14. Task semantics edits are not true docs-only clean reuse; they may reuse `sc-test`, but should still rerun `acceptance_check`.
15. If the latest two `6.7` runs stopped at the same `sc-test` failure fingerprint, fix the root cause before retrying; only override this with `--allow-repeat-deterministic-failures`.
16. Fresh `6.7` runs inherit the latest same-task `delivery/security profile` lock; only switch profiles with explicit `--reselect-profile`.
17. If `sc-test` fails twice in the same run, stop resuming and fix the root cause before starting a new run.
18. Use targeted reviewers in `6.8`: code -> `code-reviewer`, semantics / acceptance / overlay -> `semantic-equivalence-auditor`, security -> `security-auditor`.
19. If two `6.8` rounds return the same `Needs Fix` category, severity, and anchors, stop and record instead of paying for a third similar rerun.
20. Treat `status=ok` as clean only when the child `sc-llm-review` summary has no `Needs Fix`, no `Unknown`, and no timeout; if a round shows `failure_kind = timeout-no-summary`, treat it as observation gap, not clean.

## Chapter 7 Fast-Ship Card

Use this after Chapter 6 has closed the current completed backlog slice and you need the cheapest governed path for UI wiring planning.

1. `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile fast-ship --self-check`
2. `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile fast-ship --write-doc`
3. `py -3 scripts/python/dev_cli.py run-chapter7-backlog-gap --design-doc-path <doc> --epics-doc-path <doc> --duplicate-audit-path <doc> --self-check`
4. `py -3 scripts/python/collect_ui_wiring_inputs.py`
5. `py -3 scripts/python/validate_chapter7_ui_wiring.py`
6. `py -3 scripts/python/validate_chapter7_artifact_manifest.py --manifest logs/ci/<date>/chapter7-ui-wiring/artifact-manifest.json`
7. `docs/gdd/ui-gdd-flow.md` is the governed Chapter 7 artifact and `docs/gdd/ui-gdd-flow.candidates.json` is the machine-readable candidate backlog sidecar.
8. `docs/workflows/chapter7-profile-guide.md` explains the repo-local profile, override fields, and template seeds.
9. `logs/ci/<date>/chapter7-ui-wiring/closure-summary.json`, `task-status-patch-preview.json`, and `task-status-patch.json` are the closure and write-back sidecars.

## By Topic
- Project overview, startup, stack, and legacy AGENTS background sections:
  - [14-startup-stack-and-template-structure.md](14-startup-stack-and-template-structure.md)
  - [08-project-basics.md](08-project-basics.md)
  - [../../README.md](../../README.md)
  - [../PROJECT_DOCUMENTATION_INDEX.md](../PROJECT_DOCUMENTATION_INDEX.md)
- Harness, recovery, and review handoff:
  - [13-rag-sources-and-session-ssot.md](13-rag-sources-and-session-ssot.md)
  - [01-session-recovery.md](01-session-recovery.md)
  - [03-persistent-harness.md](03-persistent-harness.md)
  - [../workflows/run-protocol.md](../workflows/run-protocol.md)
  - [../workflows/harness-boundary-matrix.md](../workflows/harness-boundary-matrix.md)
  - [07-agent-to-agent-review.md](07-agent-to-agent-review.md)
- Closed-loop testing, quality gates, and Definition of Done:
  - [15-security-release-health-and-runtime-ops.md](15-security-release-health-and-runtime-ops.md)
  - [04-closed-loop-testing.md](04-closed-loop-testing.md)
  - [09-quality-gates-and-done.md](09-quality-gates-and-done.md)
  - [../testing-framework.md](../testing-framework.md)
- Architecture, ADRs, and template rules:
  - [05-architecture-guardrails.md](05-architecture-guardrails.md)
  - [10-template-customization.md](10-template-customization.md)
  - [16-directory-responsibilities.md](16-directory-responsibilities.md)
  - [../workflows/template-bootstrap-checklist.md](../workflows/template-bootstrap-checklist.md)
  - [../workflows/template-upgrade-protocol.md](../workflows/template-upgrade-protocol.md)
  - [../workflows/prototype-lane.md](../workflows/prototype-lane.md)
  - [../gdd/ui-gdd-flow.md](../gdd/ui-gdd-flow.md)
  - [../architecture/ADR_INDEX_GODOT.md](../architecture/ADR_INDEX_GODOT.md)
- AGENTS maintenance and information architecture:
  - [11-agents-construction-principles.md](11-agents-construction-principles.md)
  - [13-rag-sources-and-session-ssot.md](13-rag-sources-and-session-ssot.md)
- Execution discipline, implementation stop-loss, and script-size guardrails:
  - [12-execution-rules.md](12-execution-rules.md)

## Repository State Files
- `execution-plans/` stores current execution intent and checkpoints.
- `decision-logs/` stores decisions that changed architecture, workflow, or guardrails.
- Unresolved `Needs Fix` must be recorded in `decision-logs/` first, then linked from `execution-plans/` with concrete next-step commands and evidence paths.
- `logs/ci/active-tasks/task-<id>.active.md` is the shortest task-scoped recovery pointer.
- `py -3 scripts/python/dev_cli.py resume-task --task-id <id>` is the preferred full recovery entry because it summarizes the latest run plus matching `execution-plans/` and `decision-logs/`.
- `logs/ci/<date>/sc-review-pipeline-task-<task>/latest.json` points to the latest local pipeline artifacts, including `summary.json`, `execution-context.json`, `repair-guide.*`, and `agent-review.*` when generated.

## Prototype And Game Type Guides
- `docs/game-type-guides/README.md` stores the extracted 24 BMAD/GDS game type guides.
- `.agents/skills/prototype-7day-playable-godot-zh/SKILL.md` routes the Chinese 7-day playable prototype lane.
