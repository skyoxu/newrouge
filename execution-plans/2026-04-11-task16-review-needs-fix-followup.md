# Task 16 review-needs-fix follow-up

- Title: Task 16 review-needs-fix follow-up
- Status: paused
- Branch: task/T16
- Goal: close remaining reviewer needs-fix without violating rerun_guard or approval state-machine contracts.
- Scope: Task 16 run 50472dadff5745f79dd7401371bc6d19 after turn-6.
- Completed steps:
  - deterministic root cause fixed (CharacterSelect scene/script + Task16 gdunit tests)
  - standalone `sc-test --task-id 16 --run-id 50472...` green
  - pipeline resume to turn-5 completed deterministic + acceptance steps green
  - reviewer findings inspected and corresponding test-strengthening patches landed
- Current step: stop-loss pause on rerun_guard with inspect-first routing.
- Last completed step: turn-6 resume inspection.
- Stop-loss:
  - do not force full rerun while `chapter6-route` keeps `preferred_lane=inspect-first`
  - do not enter 6.8 unless route explicitly reports `preferred_lane=run-6.8`
- Next action:
  - py -3 scripts/python/dev_cli.py resume-task --task-id 16 --recommendation-only --recommendation-format json
  - py -3 scripts/python/dev_cli.py chapter6-route --task-id 16 --recommendation-only --recommendation-format json
  - py -3 scripts/python/dev_cli.py inspect-run --task-id 16 --recommendation-only --recommendation-format json
- Optional final convergence (only when explicitly approved):
  - py -3 scripts/sc/run_review_pipeline.py --task-id 16 --resume --allow-full-rerun
- Evidence paths:
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/summary.json
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/repair-guide.md
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/run-events.jsonl
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/agent-review.md
  - logs/ci/2026-04-11/sc-llm-review-task-16/review-code-reviewer.md
- Exit criteria:
  - reviewer verdict no longer `needs-fix`
  - `resume-task` / `chapter6-route` no longer require needs-fix loop

## Update after controlled full-rerun attempt
- Executed once: `run_review_pipeline --resume --allow-full-rerun`.
- Outcome: no convergence; turn-7 still returns `review-needs-fix` with same reviewer bundle.
- Follow-up guard:
  - keep `inspect-first` lane
  - do not enter 6.8 unless route flips to `preferred_lane=run-6.8`
  - do not keep chaining `--resume` without new routing signal.

