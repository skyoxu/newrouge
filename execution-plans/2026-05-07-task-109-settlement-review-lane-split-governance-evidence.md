# Task 109 Settlement Review Lane Split Governance Evidence

- Title: Task 109 settlement review lane split governance evidence
- Status: active
- Branch: task/T109
- Git Head: 191a9cb3a9d8d0c52aa03befc3eccfb346ea3335
- Goal: Keep settlement review closure narrow by splitting owner-surface closure, reward/relic metadata, and resume evidence into independent lanes.
- Scope: Governance evidence only. No gameplay implementation is introduced in this artifact.
- Current step: Align Task 109 acceptance/test evidence with executable governance checks.
- Last completed step: Added Task0109 governance evidence tests and aligned task metadata refs for red-first acceptance test generation.
- Stop-loss: Do not treat settlement governance evidence as gameplay completion evidence.
- Next action: py -3 scripts/sc/llm_generate_tests_from_acceptance_refs.py --task-id 109 --tdd-stage red-first --verify unit
- Recovery command: `py -3 scripts/sc/run_review_pipeline.py --task-id 109 --fork`
- Open questions: none recorded yet
- Exit criteria: Task 109 governance evidence remains lane-split and passes Chapter 6 recovery routing plus local hard checks without new P0/P1 findings.
- Related ADRs: `ADR-0010`, `ADR-0025`, `ADR-0032`
- Related decision logs: `decision-logs/2026-05-07-task-109-chapter6-residual-needs-fix.md`
- Related task id(s): `91`, `107`, `109`, `113`
- Related run id: `fc1012e585f241858ed57a5134a48754`
- Related latest.json: `logs/ci/2026-05-07/sc-review-pipeline-task-109/latest.json`
- Related pipeline artifacts: `logs/ci/2026-05-07/sc-review-pipeline-task-109-fc1012e585f241858ed57a5134a48754`
- Related audit doc: `docs/gdd/t1-t69-m1-wiring-audit.md`
- Related test evidence: `Game.Core.Tests/Tasks/Task0109SettlementReviewLaneSplitEvidenceTests.cs`

## Lane Split

- One-to-one mapping:
  - Owner-surface closure lane: owned by Task 91.
  - Reward/relic metadata lane: owned by Task 107.
  - Resume evidence lane: owned by Task 113.
- Narrow execution rule: each closure or re-review cycle targets exactly one lane and must not combine the three lanes in a single cycle.
- Independent re-review: each lane remains independently reviewable.
- Not-a-prerequisite rule: reviewing one lane does not require prior closure of the other two lanes.

## Governance Constraint

- Task 109 completion criteria are governance-only and do not include gameplay feature implementation.
- If Task 109 is not workflow-selected, settlement implementation task states stay unchanged.
- Governance artifacts must not record forward-advancing implementation state for Task 91, Task 107, or Task 113.
