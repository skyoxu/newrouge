# Task23-NeedsFix-Followup

- Title: Task23-NeedsFix-Followup
- Status: active
- Branch: task/T23
- Git Head: 31d43c8b58ffbeee62c837fe5975f79516dc8fff
- Goal: Close Task 23 unresolved soft-review needs-fix with auditable follow-up while keeping deterministic gates green.
- Scope: Task 23 acceptance wording convergence and rerun sequence in fast mode.
- Current step: Registered carry-over item and apply schema-compliant recovery metadata for CI hard gate.
- Last completed step: Added Task 23 needs-fix decision log and execution follow-up linkage.
- Stop-loss: Do not change gameplay logic or unrelated tasks; only adjust Task 23 wording/tests and recovery records.
- Next action: Re-run deterministic and semantic-only review for Task 23 after metadata fix is committed.
- Recovery command: `py -3 scripts/sc/llm_review.py --task-id 23 --security-profile host-safe --review-profile bmad-godot --review-template scripts/sc/templates/llm_review/bmad-godot-review-template.txt --semantic-gate warn --agents semantic-equivalence-auditor --base origin/main --diff-mode full --timeout-sec 1200 --agent-timeout-sec 600 --uncommitted`
- Open questions: Whether to fully converge semantic wording now or keep deferred under fast mode.
- Exit criteria: `validate_recovery_docs` passes and Task 23 has deterministic green plus recorded/closed soft-review strategy.
- Related ADRs: `docs/adr/ADR-0010-translation-keys-and-i18n-conventions.md`
- Related decision logs: `decision-logs/2026-04-03-task23-needs-fix-register.md`
- Related task id(s): `23`
- Related run id: `23913335951`
- Related latest.json: `logs/ci/2026-04-03/sc-review-pipeline-task-23/latest.json`
- Related pipeline artifacts: `logs/ci/2026-04-03/sc-llm-review-task-23/summary.json`, `logs/ci/2026-04-03/sc-acceptance-check-task-23/summary.json`

## Goal

Close the remaining soft-review `Needs Fix` for semantic wording scope without changing already-green deterministic behavior.

## Entry Conditions

- Trigger when one of the following is true:
  - switch to strict semantic gate (`--llm-strict` or equivalent),
  - prepare branch for final protected-branch merge quality pass,
  - run a dedicated semantics cleanup batch.

## Commands

1. Re-run semantic-only review:
   - `py -3 scripts/sc/llm_review.py --task-id 23 --security-profile host-safe --review-profile bmad-godot --review-template scripts/sc/templates/llm_review/bmad-godot-review-template.txt --semantic-gate warn --agents semantic-equivalence-auditor --base origin/main --diff-mode full --timeout-sec 1200 --agent-timeout-sec 600 --uncommitted`
2. If still `Needs Fix`, tighten acceptance wording in:
   - `.taskmaster/tasks/tasks_gameplay.json` (Task 23 acceptance lines)
3. Re-check deterministic baseline:
   - `py -3 scripts/sc/run_review_pipeline.py --task-id 23 --security-profile host-safe --skip-llm-review --llm-base origin/main --llm-diff-mode full`
4. Re-run full soft review when needed:
   - `py -3 scripts/sc/llm_review.py --task-id 23 --security-profile host-safe --review-profile bmad-godot --review-template scripts/sc/templates/llm_review/bmad-godot-review-template.txt --semantic-gate warn --agents code-reviewer,security-auditor,test-automator,semantic-equivalence-auditor --base origin/main --diff-mode full --timeout-sec 1500 --agent-timeout-sec 600 --uncommitted`

## Linked Decision Log

- `decision-logs/2026-04-03-task23-needs-fix-register.md`
