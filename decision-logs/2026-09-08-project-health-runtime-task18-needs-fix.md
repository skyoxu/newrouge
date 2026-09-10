# Decision Log

- Title: Task 18 runtime verification preserves existing acceptance failures
- Date: 2026-09-08
- Status: accepted
- Supersedes: n/a
- Superseded by: n/a
- Branch: feat/project-health-local-scan
- Git Head: 14e2d3297830d6a34382c97a21d962ec3e063440
- Why now: Isolated local-main verification completed for task 18
- Context: 87 tests ran; 85 passed and 2 task acceptance audits failed
- Decision: Keep task 18 runtime_failed/static evidence and do not weaken game or acceptance tests
- Consequences: task 18 cannot become runtime_verified until architecture and test-strategy evidence are repaired
- Recovery impact: fix the referenced acceptance checks, then rerun task 18 main verification
- Validation: logs/ci/project-health-knowledge/runtime/reports/3e4a3b5431524cfcbed1b557d4b0e563/run-summary.json
- Related ADRs: ADR-0035
- Related execution plans: `execution-plans/2026-09-08-project-health-runtime-task18.md`
- Related task id(s): 18
- Related run id: d6b09e8e24964d50ae41d8e901f0a355
- Related latest.json: `logs/ci/project-health-knowledge/runtime/latest.json`
- Related pipeline artifacts: `logs/ci/project-health-knowledge/runtime/task-18-522f22fb010240398c0b109a811ac97f.json`

Needs Fix: `test_architecture_audit_covers_required_boundaries` misses `no_scene_responsibility_overflow`; `test_test_strategy_audit_has_required_evidence` misses `test_layering`.
