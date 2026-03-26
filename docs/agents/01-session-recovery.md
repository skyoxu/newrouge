# Session Recovery

Use this file after a context reset.

## Recovery Order
1. Read `AGENTS.md`.
2. Read [00-index.md](00-index.md).
3. Read [02-repo-map.md](02-repo-map.md).
4. Read the newest files in `execution-plans/` and `decision-logs/`.
5. Read `git log --oneline --decorate -n 10`.
6. If a task-scoped local review pipeline already exists, read `logs/ci/active-tasks/task-<id>.active.md` first.
7. Then run `py -3 scripts/python/dev_cli.py resume-task --task-id <id>`.
8. Use the generated recovery summary to identify the latest run, recommended action, candidate commands, and matched recovery docs.
9. Only if the summary is insufficient, open `logs/ci/<date>/sc-review-pipeline-task-<task>/latest.json` directly.
10. From that latest index, open `summary.json`, `execution-context.json`, and `repair-guide.md`.
11. If `agent_review_json_path` or `agent_review_md_path` exists in `latest.json`, read that next before rerunning anything.

## What To Trust First
- `decision-logs/`: architecture and workflow decisions already made.
- `execution-plans/`: the current plan, stop-loss, and next step.
- `logs/ci/active-tasks/task-<id>.active.md`: the shortest task-scoped recovery pointer.
- `py -3 scripts/python/dev_cli.py resume-task --task-id <id>`: the preferred task-scoped recovery summary because it aggregates the latest run, matching recovery docs, and candidate commands.
- `summary.json`: the exact pipeline result.
- `execution-context.json`: git branch, head, recent log, and recovery pointers.
- `repair-guide.json` and `repair-guide.md`: deterministic next actions after a failed pipeline step.
- `agent-review.json` and `agent-review.md`: normalized reviewer verdict built from the producer artifacts.

## Minimum Recovery Questions
- What task or branch is active now?
- What was the last failing step?
- Was the failure in `sc-test`, `sc-acceptance-check`, or `sc-llm-review`?
- Did `agent-review.json` already classify the outcome as `pass`, `needs-fix`, or `block`?
- Is there an active execution plan that should be resumed instead of replaced?
- Did a decision log already lock the expected behavior?
