# Workflow optimization v2 execution plan

- Title: Workflow optimization v2 execution plan
- Status: active
- Branch: feat/workflow-optimization-v2-impl
- Git Head: bd016396db2c70fa22c6374bd2bb34ab923fb455
- Goal: Implement the uploaded workflow optimization v2 contract without rebuilding capabilities already present after PR #218.
- Scope: Root context routing; residual/technical-debt and execution-plan policy; Chapter 6 single-reviewer+lenses; acceptance verification surfaces and causal RED; recovery-policy convergence and final validation.
- Current step: Phase E compatibility/documentation closure; formal CI pending.
- Last completed step: Phases A-D implemented on this branch; Phase E shared execution-permission projection and current documentation sync implemented.
- Stop-loss: Do not alter Chapter 3→4→5→6→7 authority order, Taskmaster status ownership, Contract SSoT, Chapter 5 readiness execution ban, persistent harness recovery protocol, or global Knowledge publication boundaries. Record out-of-scope defects instead of widening the initiative.
- Next action: Open the implementation PR, run Windows Quality/Smoke, fix any hard-regression failures, then record final evidence and remaining live-model/human limitations.
- Recovery command: py -3 -m unittest scripts.sc.tests.test_review_technical_debt scripts.sc.tests.test_check_tdd_execution_plan scripts.python.tests.test_chapter6_route
- Open questions: Internal schema layout for verification_surface metadata will be selected during Phase D against actual task/acceptance structures; no second Acceptance authority may be introduced.
- Exit criteria: All required scenarios A1-A4, K1-K3, B1-B5, C1-C5, D1-D7, E1-E4 are covered by targeted regression/integration evidence; required Windows Quality/Smoke are green; no P0/P1 or explicit fix-through must-fix finding remains; unverified live-model/human evidence is called out rather than inferred.
- Related ADRs: Existing ADRs only unless a policy/authority/irreversible contract change requires a new or superseding ADR.
- Related decision logs: None required at start; create only for actual workflow/authority/policy decisions.
- Related task id(s): Workflow/harness maintenance initiative (no gameplay Taskmaster ownership transfer).
- Related run id: n/a
- Related latest.json: n/a
- Related pipeline artifacts: Targeted unittest logs and GitHub Actions runs for this branch.

## Phase 0 baseline

- Baseline named by implementation plan: 2e2fbdd15afcfedcf93416e0d60cd6cad4a2dfaf.
- Actual implementation base: bd016396db2c70fa22c6374bd2bb34ab923fb455 (PR #218 merged).
- Reuse rather than rebuild:
  - Chapter 5 readiness blocks Chapter 6 execution and Review.
  - Chapter 6 diagnostics survive blocked readiness.
  - Review abort survives stale/missing readiness and legacy runs without marathon-state.json.
  - Single-task Chapter 6 orchestration consumes execution_allowed and blocks subprocess dispatch.
  - Persistent harness run/turn/events, resume/fork/abort, profile lock, approval, rerun guard, deterministic reuse, stop-loss and 6.9 --skip-project-health remain authoritative.
  - MVG isolation/mutation infrastructure already exists and will be reused.
- Required deltas confirmed:
  - AGENTS/session recovery still globally preload unrelated documents.
  - Technical debt writer still expects top-level summary.results instead of the actual sc-llm-review child summary.
  - Residual route still creates decision/execution-plan scaffolds.
  - Execution-plan policy still escalates from file/test-count heuristics.
  - Multi-agent reviewer contracts/prompt allocation remain in place.
  - Acceptance verification surfaces are not a first-class anchor contract.
  - RED verification still needs causal-failure hardening.

## Phase checkpoints

### A — Context routing
- Replace global preload with task-route table while retaining global invariants/authority/protected operations.
- Make recovery compact-first and expand sidecars/events only when needed.
- Preserve direct-authority and optional Knowledge handoff paths.

### B — Residual / Technical Debt / Execution Plan
- Adapt pipeline child review summary into stable debt findings.
- Preserve unreviewed existing debt and use finding identity for idempotent updates.
- Do not auto-create Decision Log/Execution Plan for residual findings.
- Enforce P1 floor for playable-ea/fast-ship/standard and reject weaker explicit P0 threshold.
- Replace complexity-count plan triggers with recovery/ordered-slice/migration/large-staged-work triggers.

### C — Single Reviewer + Lenses
- One model reviewer with Spec Compliance, Edge Case, Verification Gap plus optional surface focuses.
- Required semantics/Acceptance remain available regardless of former agent name.
- Normalize severity through one adapter; keep explicit completed/incomplete/failed state.
- Narrow 6.8 by finding/surface and strengthen repeated-finding signature.

### D — Verification Surface / RED
- Add core-behavior, godot-scene, player-journey and human-experience metadata to existing Acceptance authority structures.
- Preserve old refs/anchors compatibility.
- Separate implementation eligibility from final acceptance; human pending never becomes pass.
- Remove timeout/nonzero fallback from RED; require target-test identity and causal assertion failure.
- Reuse targeted MVG mutation; do not create global mutation policy.

### E — Recovery convergence / final closure
- Reconcile recommendation producers/consumers so same evidence and decision point project the same common policy.
- Keep stage-specific actions distinct and preserve producer evidence authority.
- Run targeted matrix plus Windows Quality/Smoke and representative real paths; record live-model/human limitations explicitly.


## Implementation evidence before formal CI

- Phase A:
  - `AGENTS.md` task-scoped route table replaces global preload.
  - `docs/agents/01-session-recovery.md` uses compact recommendation-first recovery.
- Phase B:
  - Technical Debt adapter consumes the real `sc-llm-review` child `summary_file`, assigns stable finding ids and preserves unreviewed debt.
  - Chapter 6 residual recording writes only `docs/technical-debt.md`.
  - P1 is the default must-fix floor; explicit P0 is rejected; stricter P2/P3 thresholds propagate into residual eligibility.
  - Execution Plan required/recommended/none is driven by explicit durable coordination signals rather than file/test counts.
- Phase C:
  - Default model reviewer is one `code-reviewer` with Spec Compliance / Edge Case / Verification Gap lenses.
  - Acceptance semantic input is no longer assigned by reviewer persona and cannot be silently dropped on budget pressure.
  - Review completion state is separate from findings/verdict.
  - Legacy severity maps through one adapter to P0-P4; 6.8 repeat detection uses finding claim/anchor/action identity.
- Phase D:
  - Optional `acceptance_verification` metadata on existing task views supports core-behavior / godot-scene / player-journey / human-experience.
  - Classified surface failures are a normal Acceptance hard failure; human pending/failed does not pass.
  - RED no longer accepts timeout/missing report/generic non-zero as behavior evidence.
  - Existing targeted MVG mutation infrastructure is reused and remains opt-in.
- Phase E:
  - Shared `route_execution_policy` centralizes Chapter 5 readiness execution permission while stage-specific routing stays separate.
  - Current workflow/profile/SC/Agent/Skill docs are being synchronized; historical multi-reviewer artifacts remain read-only.

Formal Windows CI, representative real task paths, and a real live-model reviewer invocation remain pending and must not be inferred from mock/unit coverage.
