# Agents Docs Index

Purpose: keep [AGENTS.md](../../AGENTS.md) short and move durable guidance here.

## Read Order After Context Reset

1. [01-session-recovery.md](01-session-recovery.md)
2. [13-rag-sources-and-session-ssot.md](13-rag-sources-and-session-ssot.md)
3. [02-repo-map.md](02-repo-map.md)
4. [14-startup-stack-and-template-structure.md](14-startup-stack-and-template-structure.md)
5. [03-persistent-harness.md](03-persistent-harness.md)
6. [../workflows/run-protocol.md](../workflows/run-protocol.md)
7. [07-agent-to-agent-review.md](07-agent-to-agent-review.md)
8. If a task-scoped run already exists, `logs/ci/active-tasks/task-<id>.active.md`
9. Then run `py -3 scripts/python/dev_cli.py resume-task --task-id <id>` for the full recovery summary
10. Newest files in `execution-plans/` and `decision-logs/`
11. `logs/ci/<date>/sc-review-pipeline-task-<task>/latest.json` only when the recovery summary still needs deeper inspection

## By Topic
- Project overview, startup, stack, and legacy AGENTS background sections:
  - [14-startup-stack-and-template-structure.md](14-startup-stack-and-template-structure.md)
  - [08-project-basics.md](08-project-basics.md)
  - [../../README.md](../../README.md)
  - [../PROJECT_DOCUMENTATION_INDEX.md](../PROJECT_DOCUMENTATION_INDEX.md)
- Harness, recovery, and review handoff:
  - [13-rag-sources-and-session-ssot.md](13-rag-sources-and-session-ssot.md)
  - [01-session-recovery.md](01-session-recovery.md)
  - [03-persistent-harness.md](03-persistent-harness.md)
  - [../workflows/run-protocol.md](../workflows/run-protocol.md)
  - [../workflows/harness-boundary-matrix.md](../workflows/harness-boundary-matrix.md)
  - [07-agent-to-agent-review.md](07-agent-to-agent-review.md)
- Closed-loop testing, quality gates, and Definition of Done:
  - [15-security-release-health-and-runtime-ops.md](15-security-release-health-and-runtime-ops.md)
  - [04-closed-loop-testing.md](04-closed-loop-testing.md)
  - [09-quality-gates-and-done.md](09-quality-gates-and-done.md)
  - [../testing-framework.md](../testing-framework.md)
- Architecture, ADRs, and template rules:
  - [05-architecture-guardrails.md](05-architecture-guardrails.md)
  - [10-template-customization.md](10-template-customization.md)
  - [16-directory-responsibilities.md](16-directory-responsibilities.md)
  - [../workflows/template-bootstrap-checklist.md](../workflows/template-bootstrap-checklist.md)
  - [../workflows/template-upgrade-protocol.md](../workflows/template-upgrade-protocol.md)
  - [../workflows/prototype-lane.md](../workflows/prototype-lane.md)
  - [../architecture/ADR_INDEX_GODOT.md](../architecture/ADR_INDEX_GODOT.md)
- AGENTS maintenance and information architecture:
  - [11-agents-construction-principles.md](11-agents-construction-principles.md)
  - [13-rag-sources-and-session-ssot.md](13-rag-sources-and-session-ssot.md)
- Execution discipline, implementation stop-loss, and script-size guardrails:
  - [12-execution-rules.md](12-execution-rules.md)

## Repository State Files
- `execution-plans/` stores current execution intent and checkpoints.
- `decision-logs/` stores decisions that changed architecture, workflow, or guardrails.
- `logs/ci/active-tasks/task-<id>.active.md` is the shortest task-scoped recovery pointer.
- `py -3 scripts/python/dev_cli.py resume-task --task-id <id>` is the preferred full recovery entry because it summarizes the latest run plus matching `execution-plans/` and `decision-logs/`.
- `logs/ci/<date>/sc-review-pipeline-task-<task>/latest.json` points to the latest local pipeline artifacts, including `summary.json`, `execution-context.json`, `repair-guide.*`, and `agent-review.*` when generated.
