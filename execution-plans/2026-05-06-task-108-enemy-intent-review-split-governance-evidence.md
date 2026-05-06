# Task 108 Enemy Intent Review Split Governance Evidence

- Title: Task 108 enemy intent review split governance evidence
- Status: active
- Branch: task/T108
- Git Head: b847b3f3a9399ef70e715ea29e857b6eb31bc665
- Goal: Keep enemy intent review closure narrow by separating preview generation lane and enemy turn resolution lane.
- Scope: Governance evidence only. No gameplay implementation is introduced in this artifact.
- Current step: Maintain governance lane-split evidence for Task 108 while Chapter 6 remains in inspect-first/residual-followup state.
- Last completed step: Added Task0108 governance evidence tests and aligned Task108 acceptance/test refs to executable evidence checks.
- Stop-loss: Do not reopen full 6.7 while chapter6-route stays inspect-first and six_eight_worthwhile=false; follow residual protocol first.
- Next action: py -3 scripts/python/dev_cli.py chapter6-route --task-id 108 --recommendation-only
- Recovery command: `py -3 scripts/sc/run_review_pipeline.py --task-id 108 --resume`
- Open questions: none recorded yet
- Exit criteria: Governance evidence remains structurally valid and Chapter 6 route changes from inspect-first to an executable closure lane.
- Related ADRs: `ADR-0010`, `ADR-0025`, `ADR-0032`
- Related decision logs: `decision-logs/2026-05-06-task-108-chapter6-residual-needs-fix.md`
- Related task id(s): `76`, `105`, `108`
- Related run id: `1ade7768fd52468ab441dfcf553d2681`
- Related latest.json: `logs/ci/2026-05-06/sc-review-pipeline-task-108/latest.json`
- Related pipeline artifacts: `logs/ci/2026-05-06/sc-review-pipeline-task-108-1ade7768fd52468ab441dfcf553d2681`
- Related audit doc: `docs/gdd/t1-t69-m1-wiring-audit.md`
- Related light-lane summary: `logs/ci/2026-05-06/sc-build-tdd/summary.json`

## Lane Split

- Preview generation lane: owned by Task 76, covers deterministic generation and display-surface mapping for enemy intent preview.
- Enemy turn resolution lane: owned by Task 105, covers displayed-intent execution and no-repeat guardrails.
- Independent re-review: Task 76 and Task 105 remain independently re-reviewable; closure evidence for one lane does not require reopening the other lane.
- Not-a-prerequisite rule: reviewing Task 76 must not require prior review closure of Task 105, and reviewing Task 105 must not require prior review closure of Task 76.
- No-repeat verification: a recombined enemy-intent review lane is invalid for this split; duplicate combined-lane verification is invalid evidence.

## Governance Constraint

- If Task 108 is not workflow-selected, implementation state for Task 76 and Task 105 must remain unchanged.
- Task 108 completion criteria are satisfied by governance planning and review evidence only.
