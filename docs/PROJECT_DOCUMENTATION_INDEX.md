# Project Documentation Index (lastking)

This file is the top-level navigation for project docs.

## Start Order After Context Reset

1. `README.md`
2. `docs/agents/00-index.md`
3. `docs/PROJECT_DOCUMENTATION_INDEX.md`
4. `docs/agents/13-rag-sources-and-session-ssot.md`
5. `DELIVERY_PROFILE.md`
6. `docs/testing-framework.md`
7. Newest file in `execution-plans/`
8. Newest file in `decision-logs/`
9. If available: `logs/ci/<date>/sc-review-pipeline-task-<task>/latest.json`

## Authoritative Sources

- Taskmaster triplet: `.taskmaster/tasks/tasks.json`, `.taskmaster/tasks/tasks_back.json`, `.taskmaster/tasks/tasks_gameplay.json`
- PRD: `.taskmaster/docs/prd.txt`, `docs/prd/**`
- ADR: `docs/adr/ADR-*.md`, `docs/architecture/ADR_INDEX_GODOT.md`
- Base architecture: `docs/architecture/base/**`
- Overlay slices: `docs/architecture/overlays/PRD-lastking-T2/08/**`
- Testing rules: `docs/testing-framework.md`
- Delivery/run protocol: `DELIVERY_PROFILE.md`, `docs/workflows/run-protocol.md`, `docs/workflows/local-hard-checks.md`

## Workflow Docs

- Upgrade guide: `docs/workflows/business-repo-upgrade-guide.md`
- Template upgrade protocol: `docs/workflows/template-upgrade-protocol.md`
- Project health dashboard: `docs/workflows/project-health-dashboard.md`
- Local hard checks: `docs/workflows/local-hard-checks.md`

## Evidence and Logs

- CI and local evidence: `logs/ci/<YYYY-MM-DD>/`
- Review pipeline artifact entry: `logs/ci/<YYYY-MM-DD>/sc-review-pipeline-task-<task>/latest.json`
