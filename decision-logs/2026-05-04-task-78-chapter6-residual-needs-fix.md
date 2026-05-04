# Task78-Chapter6-Residual-NeedsFix

- Title: Task78-Chapter6-Residual-NeedsFix
- Date: 2026-05-04
- Status: accepted
- Supersedes: none
- Superseded by: none
- Branch: task/T78
- Git Head: 729ba3d3b5c2a66588785287a97845211835825e
- Why now: GitHub run 25313610499 failed hard gate on recovery-doc schema fields, despite task pipeline closure.
- Context: Task 78 chapter6 loop reached pass locally, but historical residual docs lacked mandatory metadata headers required by `validate_recovery_docs.py`.
- Decision: Backfill required metadata headers in Task 78 residual execution plan and decision log files using UTF-8.
- Consequences: Hard gate can validate recovery docs; no runtime logic change is introduced.
- Recovery impact: Future resume/recovery will have schema-compliant residual records and clearer audit trail.
- Validation: `py -3 scripts/python/validate_recovery_docs.py --dir all`
- Related ADRs: ADR-0010, ADR-0025, ADR-0032
- Related execution plans: `execution-plans/2026-05-04-task-78-chapter6-residual-followup.md`
- Related task id(s): `78`
- Related run id: `25313610499`
- Related latest.json: `logs/ci/2026-05-04/sc-review-pipeline-task-78/latest.json`
- Related pipeline artifacts: `logs/ci/2026-05-04/gh-run-25313610499/ci-logs/2026-05-04/gate-bundle/runs/gh-25313610499-a1/hard/summary.json`, `logs/ci/2026-05-04/gh-run-25313610499/ci-logs/2026-05-04/gate-bundle/runs/gh-25313610499-a1/hard/validate_recovery_docs.log`

## Context
- Task: `78`
- Latest run: `4e117591e5724673894f3b3fd028aafa`
- Recovery lane: `inspect-first`
- Stop condition: `blocked_by=recent_failure_summary`, `six_eight_worthwhile=no`, `residual_recording=eligible`

## Residual Findings
- Reviewer verdict remains `Needs Fix` in `sc-llm-review` (code-reviewer and security-auditor findings).
- Deterministic checks are green, but review semantics are not closed.

## Evidence
- `logs/ci/2026-05-04/sc-review-pipeline-task-78/latest.json`
- `logs/ci/2026-05-04/sc-review-pipeline-task-78-4e117591e5724673894f3b3fd028aafa/agent-review.json`
- `logs/ci/2026-05-04/sc-llm-review-task-78/review-code-reviewer.md`
- `logs/ci/2026-05-04/sc-llm-review-task-78/review-security-auditor.md`
- `logs/ci/2026-05-04/sc-review-pipeline-task-78-4e117591e5724673894f3b3fd028aafa/run-events.jsonl`

## Decision
- Pause Chapter 6 progression and record residual instead of repeating reruns.
- Next session must repair reviewer-requested acceptance semantics/tests before reopening review pipeline.
