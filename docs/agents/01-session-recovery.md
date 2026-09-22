# Session Recovery

Use compact recovery first. Historical logs are evidence, not current instructions.

## Canonical recovery

1. Identify the explicit task/branch from the user request, current Taskmaster triplet, or an explicitly bound execution plan. Do not infer it from the newest file timestamp.
2. Run:
   - `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only`
   - for Chapter 6 go/no-go: `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only`
3. Read the compact fields first: `reason`, `run_type`, `reuse_mode`, `artifact_integrity`, `recommended_action`, `recommended_action_why`, `forbidden_commands`, `Chapter6 blocked by`, and approval/reuse/stop-loss summaries.
4. Expand only the evidence required for the next decision:
   - `latest.json` when the canonical pointer needs inspection.
   - `summary.json` for producer result details.
   - `repair-guide.*` for deterministic repair actions.
   - `agent-review.*` for reviewer findings/disposition.
   - `run-events.jsonl` only when turn/event ordering or incremental movement matters.
   - `execution-context.json` when git/profile/handoff identity matters.
5. Read an Execution Plan or Decision Log only when the current task/recovery payload/user request explicitly binds it, or when a required persistent plan must be created/resumed.

## Fail-closed rules

- A dry-run/planned-only bundle is evidence only and must not become a recovery producer.
- `artifact_integrity`, missing/corrupt sidecars, unknown approval state, or stale Chapter 5 readiness must not default to continue.
- If direct source material is required and missing, read the authoritative Task/Requirement/Acceptance/ADR/Overlay/Contract source; do not infer it from summaries.
- If active-task and latest disagree, trust the validated producer pointer from the canonical recovery helpers and treat drift as a bug.
- Do not pay for another 6.7/6.8 before compact recovery has ruled out reuse, stop-loss, or a narrower repair path.

## Direct source fallback

When Knowledge shadow/handoff is missing, stale, invalid, or returns `fallback_required`, continue from direct authoritative sources. Do not refresh the global Knowledge catalog as a recovery side effect.

## Recovery questions

- What explicit task/run is being resumed?
- Is the latest producer bundle valid and complete?
- Does Chapter 5 readiness allow execution?
- Can deterministic evidence be reused?
- Is the next action 6.7, 6.8, inspect, fork, pause, record residual, or return to an earlier owner?
- Is a persistent Execution Plan explicitly required for cross-session/ordered migration work?
- Which exact additional artifact is needed to answer the next question?
