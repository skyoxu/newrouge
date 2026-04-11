# task16-review-needs-fix-rerun-guard-stoploss

- Title: task16-review-needs-fix-rerun-guard-stoploss
- Date: 2026-04-11
- Status: proposed
- Supersedes: none
- Superseded by: none
- Branch: task/T16
- Why now: Task 16 Chapter 6 turn-6 remains `review-needs-fix` while recovery route reports `preferred_lane=inspect-first` and `summary.chapter6_hints.blocked_by=rerun_guard`.
- Context:
  - deterministic checks are green in current run (`sc-test` and `sc-acceptance-check` both `ok` in turn-5)
  - approval sidecar is `denied`, allowed actions are `resume | inspect`
  - repeated `--resume` on turn-6 did not rerun `sc-llm-review`; reviewer verdict stayed `needs-fix`
- Decision: stop-loss first. Do not force full rerun or enter 6.8 unless route explicitly flips to `preferred_lane=run-6.8` or an explicit final convergence override is approved.
- Consequences: Task 16 cannot be marked done in this turn because `review-needs-fix` is still open in pipeline artifacts.
- Recovery impact: Keep following recommendation-first loop (`resume-task` / `chapter6-route` / `inspect-run`) and use residual recording until route allows a bounded closure lane.
- Validation:
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/summary.json
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/repair-guide.md
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/run-events.jsonl
  - logs/ci/2026-04-11/sc-review-pipeline-task-16-50472dadff5745f79dd7401371bc6d19/agent-review.json
  - logs/ci/2026-04-11/sc-llm-review-task-16/review-code-reviewer.md
  - logs/ci/2026-04-11/sc-llm-review-task-16/review-security-auditor.md
  - logs/ci/2026-04-11/sc-llm-review-task-16/review-semantic-equivalence-auditor.md
- Related execution plans: execution-plans/2026-04-11-task16-review-needs-fix-followup.md
- Related task id(s): 16
- Related run id: 50472dadff5745f79dd7401371bc6d19

## Update after one controlled full-rerun attempt
- Attempted command: `py -3 scripts/sc/run_review_pipeline.py --task-id 16 --resume --allow-full-rerun`
- Result: pipeline `status=ok` but reviewer still `needs-fix` on turn-7, with unchanged `sc-llm-review` findings.
- Recovery route stayed unchanged:
  - `recommended_action=needs-fix-fast`
  - `preferred_lane=inspect-first`
  - `six_eight_worthwhile=no`
  - `blocked_by=approval_denied`
- Stop-loss remains active: no additional blind reruns in this run.

