# Task 14 Chapter6 Execution

- Title: Task 14 Chapter6 Execution
- Status: completed
- Branch: task/T14
- Git Head: feb35f794a8a8b3ecec95991ce615dbf731f834d
- Goal: Deliver Task 14 main menu acceptance in chapter-6 order (new run / continue / quit / overwrite confirmation).
- Scope: Fix blocking tests and menu behavior only; avoid unrelated gameplay changes.
- Current step: none
- Last completed step: 6.8 needs-fix review recorded as P2-only follow-up; task marked done under fast-ship.
- Stop-loss: If deterministic gates fail with unrelated regressions, record in decision-log and avoid broad refactor.
- Next action: none for Task 14 completion; only reopen if the recorded P2 evidence-hardening items are prioritized later.
- Recovery command: `py -3 scripts/sc/run_review_pipeline.py --task-id 14 --resume`
- Open questions: none
- Exit criteria: satisfied for fast-ship completion; deterministic gates are green and remaining P2 needs-fix is explicitly logged in the linked decision-log.
- Related ADRs: ADR-0032, ADR-0010
- Related decision logs: decision-logs/2026-04-06-task-14-manual-flow-evidence.md
- Related task id(s): `14`
- Related run id: `5b55ab7bbcc44fdbae649e02f00e2506`
- Related latest.json: `logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json`
- Related pipeline artifacts: `logs/ci/2026-04-06/sc-review-pipeline-task-14-5b55ab7bbcc44fdbae649e02f00e2506`
- Historical blocking run retained for audit linkage: `logs/ci/2026-04-06/sc-review-pipeline-task-14-98971061b3f54dd88e8fc2849170eaca`

## Manual Flow Notes

- New Run flow: when autosave exists, overwrite confirmation must appear and default to cancel.
- Continue flow: continue is available only with a valid autosave snapshot.
- Evidence linkage: logs are tracked under `logs/ci/2026-04-06/sc-review-pipeline-task-14-*/`.
- Remaining needs-fix (LLM): only P2 evidence-hardening for `ACC:T14.8` and low-severity acceptance wording drift remains; see `decision-logs/2026-04-06-task-14-manual-flow-evidence.md`.

## Completion Snapshot

- Deterministic pipeline: `ok`
  - `logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json`
- Targeted GdUnit reruns:
  - `logs/e2e/2026-04-06/t14-p1-green-rerun4/run-summary.json`
  - `logs/e2e/2026-04-06/t14-proof-rerun7/run-summary.json`
- Latest 6.8 review posture:
  - `logs/ci/2026-04-06/sc-needs-fix-fast-task-14/summary.json`
  - Remaining verdict: P2-only follow-up, no remaining P1 blocker

## Follow-up Entry

If Task 14 P2 needs-fix is reopened later, start from:

1. `py -3 scripts/sc/llm_review_needs_fix_fast.py --task-id 14 --delivery-profile fast-ship --rerun-failing-only --max-rounds 1`
2. Harden `ACC:T14.8` by replacing the current quit callback seam with a task-scoped quit requester boundary.
3. Tighten stale Task 14 acceptance wording in `.taskmaster/tasks/tasks_back.json` and `.taskmaster/tasks/tasks_gameplay.json`.
