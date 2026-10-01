# Knowledge planning actions

- Title: knowledge-planning-actions
- Status: done
- Branch: feat/knowledge-planning-actions
- Git Head: 10293691b0538c945fd0a69a44cee687cf8a14a3
- Goal: Add main-commit Capability generation and existing-Capability MVG generation to the loopback Knowledge pages.
- Scope: Local authenticated planning endpoints, committed main execution input, page controls and bounded result feedback.
- Current step: Complete; publish the reviewed branch and PR.
- Last completed step: Implemented both buttons and verified 243 related regressions plus encoding and workflow gates.
- Stop-loss: Fix deterministic gate failures before rerunning the full Windows pipeline; preserve planning attempts and do not repeat model generation while source identity or Chapter 3/5 evidence is invalid.
- Next action: Merge the reviewed PR, update local main, and restart the Project Health service.
- Recovery command: py -3 -m unittest scripts.python.tests.test_project_health_planning -v
- Open questions: None; local generated views retain source main revision and explicit unpublished planning provenance.
- Exit criteria: Both buttons execute existing stages, reject unsupported source identity, refresh their data, preserve compact success/error feedback and pass relevant regressions.
- Related ADRs: ADR-0038
- Related decision logs: n/a
- Related task id(s): n/a (workflow UI maintenance)
- Related run id: knowledge-planning-actions
- Related latest.json: n/a (generation never reads scan snapshots as inputs)
- Related pipeline artifacts: logs/ci/knowledge-planning-actions/**

- [x] Lock main baseline and inspect applicable contracts.
- [x] Prepare a real Git main checkout; reject directory/archive/scan/workspace source fallback.
- [x] Preserve unchanged authoritative inputs and reuse existing Capability/MVG stages and readiness gates.
- [x] Add authenticated asynchronous actions, bounded status and duplicate-operation protection.
- [x] Refresh Capability/MVG data with explicit local planning provenance; do not advance canonical publication or runtime success.
- [x] Verify failure, stale main, existing Capability, preserved verdict and UI feedback paths.
- [x] Commit, publish PR and report validation limits.

Authority is the latest local refs/heads/main commit. A normal Git checkout supplies model input; no project-health/KCP snapshot, archive extraction or current feature worktree is selected as generation source. The planners' own isolated read-only model input bundles remain their execution contract. Derived artifacts and Chapter 5 evidence are validated by the existing planners. Result views may show a successful locally generated plan at the exact main revision without claiming a Git commit, KCP publication or runtime verification.

Validation: `regression.log` records 136 passing planning/topology/HTTP/frontend tests; `project-health-regression.log` records 107 passing Project Health tests. Node executes real page scripts against deterministic DOM/HTTP fixtures, including both button refreshes, polling, token use, source revision, bounded failure feedback and local-generated runtime blocking. Git fixtures cover dirty feature inputs, CRLF conversion, changing main, existing committed Capability and recovery without new candidates. Python/JavaScript syntax checks, `git diff --check`, UTF-8 and workflow-gate enforcement pass. Models use explicitly deterministic fixtures; no new paid real-model or Godot execution is claimed. Existing prompts, independent-review contracts and planning validators are unchanged.
