# Session Recovery

Use this file after a context reset.

Preferred command: `py -3 scripts/python/dev_cli.py resume-task --task-id <id>`. For a quick next-step read, prefer `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only` first.

## Recovery Order
1. Read `AGENTS.md` and identify the current task scope.
2. For a task recovery, run `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only` before opening detailed artifacts.
3. If Chapter 6 routing is relevant, run `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only`.
4. Read the specific Task/Acceptance/ADR/Contract or explicit plan/decision bound to the current work. Do not choose a plan or decision merely because it is newest in its directory.
5. Expand the selected run only when the compact recommendation cannot answer the next-step question. Prefer `latest.json` → `summary.json` / `execution-context.json` / `repair-guide.md`; read append-only events only when event ordering or turn history is needed.
6. Treat `logs/ci/active-tasks/task-<id>.active.md` as a compact pointer, not higher authority than the producer bundle.
7. If `active-task` and `latest.json` disagree, trust the validated producer `latest.json`; if artifact integrity is broken, inspect or fall back to the previous real producer bundle rather than continuing from a damaged sidecar.
8. Do not use `run_review_pipeline.py --dry-run` as a recovery pointer producer; dry-run artifacts are local evidence and do not publish the canonical latest/active-task pointer.
9. If required direct authority cannot be located, stop the affected operation rather than filling the gap from a summary or unrelated historical file.

## What To Trust First
- `decision-logs/`: architecture and workflow decisions already made.
- `execution-plans/`: the current plan, stop-loss, and next step.
- `summary.json`: the exact pipeline result.
- `latest.json`: the fastest pointer for deciding whether to resume `6.7`, switch to `6.8`, or stop because rerun guard already triggered.
- `execution-context.json`: git branch, head, recent log, and recovery pointers.
- `repair-guide.json` and `repair-guide.md`: deterministic next actions after a failed pipeline step.
- `agent-review.json` and `agent-review.md`: normalized reviewer verdict built from the producer artifacts.

## Minimum Recovery Questions
- What task or branch is active now?
- Did `latest.json` already say this is `deterministic_ok_llm_not_clean`, so the next move should be `6.8` instead of reopening a full `6.7`?
- Did `latest.json.diagnostics.rerun_guard` already block another full rerun?
- Did `latest.json.diagnostics.llm_retry_stop_loss` already prove that deterministic was green and only the first long LLM wait timed out?
- Did `latest.json.diagnostics.sc_test_retry_stop_loss` already prove the run should stop retrying the same known unit failure?
- Did `latest.json.diagnostics.reuse_decision` or `reuse_mode` already show that deterministic artifacts can be reused?
- Did `active-task` already classify the block as `rerun_guard`, `llm_retry_stop_loss`, `sc_test_retry_stop_loss`, `waste_signals`, or `recent_failure_summary`?
- Did the latest recoverable bundle actually complete, or did `artifact_integrity` already tell you the pointer is stale/incomplete?
- Did recovery already show `run_type = planned-only` or `reason = planned_only_incomplete`, meaning the bundle is evidence-only and must not be used to reopen `6.7` or `6.8`?
- Did `Chapter6 blocked by = artifact_integrity` already tell you to fall back to the previous real producer bundle before any rerun choice?
- Did `recommended_action_why`, `Chapter6 stop-loss note`, or `recommended_action = needs-fix-fast` already tell you that a targeted closure is cheaper than another full `6.7`?
- What was the last failing step?
- Was the failure in `sc-test`, `sc-acceptance-check`, or `sc-llm-review`?
- Did `agent-review.json` already classify the outcome as `pass`, `needs-fix`, or `block`?
- Is there an active execution plan that should be resumed instead of replaced?
- Did a decision log already lock the expected behavior?
