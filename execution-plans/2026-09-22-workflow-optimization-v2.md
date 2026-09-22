# Workflow Optimization v2 Execution Plan

- Title: Workflow optimization and game-validation refactor v2
- Status: active
- Branch: feat/workflow-optimization-v2
- Git Head: bd016396db2c70fa22c6374bd2bb34ab923fb455
- Source baseline: 2e2fbdd15afcfedcf93416e0d60cd6cad4a2dfaf
- Goal: Implement the seven workflow-optimization directions from newrouge-workflow-optimization-implementation-plan-v2.md without changing the Chapter 3→4→5→6→7 authority order or weakening existing readiness, recovery, hard-check, Taskmaster, Contract, or Knowledge boundaries.
- Scope: Repository workflow/control-plane code, review orchestration, residual debt handling, execution-plan policy, Acceptance verification metadata, RED verification, documentation and targeted regressions. No new gameplay feature scope.
- Current step: Phase 0 — baseline/delta audit against current main after PR #218.
- Last completed step: PR #218 compatibility and semantic-proof closure is merged at bd016396db2c70fa22c6374bd2bb34ab923fb455.
- Stop-loss: Do not replace existing recovery protocols, task status authority, Knowledge authority, Contract SSoT, 6.8 final-pass, 6.9 hard checks, MVG isolation/mutation framework, or Windows/Godot validation with a parallel framework.
- Next action: Complete Phase 0 delta map, then implement Phase A context routing.
- Recovery command: `git switch feat/workflow-optimization-v2`

## Phase 0 — Baseline and delta audit

Status: in-progress

Known current-state deltas already verified:
- Chapter 5 readiness blocks Chapter 6 route and the single-task orchestrator dispatch path.
- Review abort remains available under stale/missing readiness and supports legacy runs without marathon-state.json.
- Persistent Harness, run/turn events, resume/fork/abort, approval, rerun guards, deterministic reuse, stop-loss and no-refresh Chapter 6 hard checks already exist and must be reused.
- Existing Technical Debt writer currently expects top-level `results`, while Review pipeline summary primarily exposes child `steps[].summary_file`; this remains a Phase B delta.
- Existing RED verification still accepts an arbitrary non-zero verification result when no compile error is detected; this remains a Phase D delta.
- Delivery profiles still use multi-agent reviewer rosters; this remains a Phase C delta.

Evidence / commands:
- Current main: `bd016396db2c70fa22c6374bd2bb34ab923fb455`.
- PR #218 final Windows Quality Gate: success; hard bundle 598 tests, 24/24 hard gates.
- PR #218 final Windows Smoke: success.

## Phase A — Context routing

Status: pending

Target:
- Root AGENTS becomes a compact project/global-invariants/router document.
- Remove unconditional multi-file preload and “latest plan/decision is current task” assumptions.
- Align session recovery and relevant workflow/Skill docs with compact recovery → expand only needed evidence.
- Preserve direct-authority and optional Knowledge shadow/handoff routes.

## Phase B — Residual and Execution Plan policy

Status: pending

Target:
- Adapt Review pipeline child result into Technical Debt findings with stable finding identity and narrow-review retention.
- P0/P1 must-fix floor; playable-ea/fast-ship/standard default P1; reject explicit threshold below P1.
- Residuals write Technical Debt only; no automatic Decision Log + Execution Plan pair.
- Execution Plan required by persistence/coordination/authority migration, not file/test counts.

## Phase C — Single Reviewer + Lenses

Status: pending

Target:
- Chapter 6.7/6.8 use one model reviewer with Spec Compliance, Edge Case and Verification Gap lenses plus bounded surface focuses.
- Required Acceptance/semantic context must not depend on a semantic-equivalence reviewer persona.
- Review result distinguishes completed/incomplete/failed and supports stable findings, uncertainty and disposition.
- Needs-fix repeat signature is finding/action based, not reviewer identity based.
- Revalidate Phase B adapter against new review output.

## Phase D — Verification surfaces and causal RED

Status: pending

Target:
- Extend existing Acceptance authority to represent core-behavior, godot-scene, player-journey and human-experience evidence.
- Preserve legacy anchors; classify new/modified data fail-closed when ambiguous.
- Human pending permits implementation preflight only, never Acceptance pass.
- Remove non-zero-without-compile-error RED fallback; require target-test evidence and expected assertion failure.
- Reuse existing targeted MVG mutation probe; no default whole-repo mutation.

## Phase E — Recovery convergence and final closure

Status: pending

Target:
- Consolidate only genuinely common recovery policy so recommendation views agree at the same evidence/decision point.
- Preserve stage-specific actions, read-only recommendation semantics, schema strictness, no-refresh boundaries and invalidation rules.
- Run targeted matrix, hard gates, Windows/Godot checks available in CI, and representative real-path integrations.
- Record any unavailable live-model/manual-experience validation explicitly rather than substituting mocks.

## Checkpoints

### 2026-09-22 Phase 0 start
- Branch created from merged #218 main.
- Execution Plan created before control-plane writes, as required for this multi-stage workflow/harness refactor.
