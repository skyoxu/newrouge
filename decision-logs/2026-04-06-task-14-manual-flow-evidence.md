# task14-manual-flow-evidence

- Title: task14-manual-flow-evidence
- Date: 2026-04-06
- Status: proposed
- Supersedes: none
- Superseded by: none
- Branch: task/T14
- Git Head: feb35f794a8a8b3ecec95991ce615dbf731f834d
- Why now: Chapter-6 execution for Task 14 produced reusable deterministic evidence, but latest LLM review still reports semantic coverage gaps.
- Context: Task 14 main menu behavior has deterministic green in sc-test/acceptance-check while needs-fix remains in llm-review findings.
- Decision: Mark Task 14 done under `fast-ship` after deterministic gates stayed green and 6.8 reduced remaining review debt to P2-only items. Keep unresolved P2 findings explicit in repository-managed execution-plan/decision-log artifacts instead of spending another 6.8 loop on low-severity evidence hardening.
- Consequences: Deterministic gates stay reproducible, Task 14 can leave the active lane, and the remaining P2 items stay auditable with concrete follow-up entry points.
- Recovery impact: Next operator can resume from latest pipeline artifacts and continue only the Task 14 P2 evidence-hardening work without rebuilding context.
- Validation: Verified by `sc-build-tdd`, `sc-review-pipeline`, targeted GdUnit reruns, and `sc-needs-fix-fast` outputs on 2026-04-06.
- Related ADRs: ADR-0032, ADR-0010
- Related execution plans: execution-plans/2026-04-06-task-14-chapter6-execution.md
- Related task id(s): `14`
- Related run id: `5b55ab7bbcc44fdbae649e02f00e2506`
- Related latest.json: `logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json`
- Related pipeline artifacts: `logs/ci/2026-04-06/sc-review-pipeline-task-14-5b55ab7bbcc44fdbae649e02f00e2506`

## Remaining P2 Needs Fix

1. `ACC:T14.8` quit evidence is still weaker than the desired result-boundary proof.
   - Current state: tests prove `ui.menu.quit` emission, quit intent, and task-local quit seam invocation.
   - Gap: reviewer still wants the test seam to stand in for the real quit requester boundary more explicitly, instead of only proving intent-level behavior.
   - Follow-up direction: replace the current callback-style seam with a single task-scoped quit requester/adapter seam and assert that the real quit branch delegates to it.
   - Evidence:
     - `logs/ci/2026-04-06/sc-needs-fix-fast-task-14/round-1/review-code-reviewer.md`
     - `logs/ci/2026-04-06/sc-needs-fix-fast-task-14/round-1/review-security-auditor.md`
     - `Tests.Godot/tests/UI/test_main_menu_events.gd`
     - `Game.Godot/Scripts/UI/MainMenu.cs`

2. Task-level acceptance wording and evidence anchors still contain low-severity drift.
   - Current state: runtime behavior and deterministic evidence are green.
   - Gap: some Task 14 acceptance lines in `.taskmaster/tasks/tasks_back.json` and `.taskmaster/tasks/tasks_gameplay.json` remain broad or stale relative to the concrete test anchors and runtime scene path wording.
   - Follow-up direction: tighten acceptance text to the actual task-scoped test anchors and remove or downgrade non-semantic audit items from the semantic acceptance set.
   - Evidence:
     - `.taskmaster/tasks/tasks_back.json`
     - `.taskmaster/tasks/tasks_gameplay.json`
     - `logs/ci/2026-04-06/sc-needs-fix-fast-task-14/round-1/review-code-reviewer.md`
     - `logs/ci/2026-04-06/sc-needs-fix-fast-task-14/round-1/review-security-auditor.md`

## Done Rationale

- `workflow.md` fast-mode guidance allows a task to stop after a single 6.8 loop once deterministic gates are stable and only P2/P3 evidence-strength issues remain.
- Latest deterministic pipeline status is `ok`:
  - `logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json`
- Latest targeted GdUnit evidence is green:
  - `logs/e2e/2026-04-06/t14-p1-green-rerun4/run-summary.json`
  - `logs/e2e/2026-04-06/t14-proof-rerun7/run-summary.json`
