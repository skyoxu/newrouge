# Task 23 Needs-Fix Follow-up Plan

Date: 2026-04-03  
Task: `23`  
Status: `deferred in fast mode, tracked for semantic convergence`

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

