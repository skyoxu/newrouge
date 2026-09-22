# Workflow optimization v2 execution plan

- Title: Workflow optimization v2 execution plan
- Status: active
- Branch: feat/workflow-optimization-v2-impl
- Git Head: implementation freeze `b419b08bf089a0ea61810a62ef675e7983e02acd` (this plan update is evidence-only and advances the branch head).
- Goal: Implement the uploaded workflow optimization v2 contract without rebuilding capabilities already present after PR #218.
- Scope: Root context routing; residual/technical-debt and execution-plan policy; Chapter 6 single-reviewer+lenses; acceptance verification surfaces and causal RED; recovery-policy convergence and final validation.
- Current step: Final Windows Quality/Smoke/MVG validation for the implementation freeze; authenticated live-model reviewer integration remains required when a runnable backend is available.
- Last completed step: Phases A-E implementation and hard-regression closure landed through `b419b08bf089a0ea61810a62ef675e7983e02acd`, including downstream preload removal, explicit incomplete Review Contract regressions, and TRX-bound causal unit RED evidence.
- Stop-loss: Do not alter Chapter 3→4→5→6→7 authority order, Taskmaster status ownership, Contract SSoT, Chapter 5 readiness execution ban, persistent harness recovery protocol, or global Knowledge publication boundaries. Record out-of-scope defects instead of widening the initiative.
- Next action: Require latest-head Windows Quality/Smoke/MVG success. Then run one authenticated live-model code-reviewer input/output integration check against the Single Reviewer + lenses contract; if no backend is available, keep that item explicitly unverified and do not mark this plan done.
- Recovery command: py -3 -m unittest scripts.sc.tests.test_review_technical_debt scripts.sc.tests.test_check_tdd_execution_plan scripts.python.tests.test_chapter6_route
- Open questions: Internal schema layout for verification_surface metadata will be selected during Phase D against actual task/acceptance structures; no second Acceptance authority may be introduced.
- Exit criteria: All required scenarios A1-A4, K1-K3, B1-B5, C1-C5, D1-D7, E1-E4 are covered by targeted regression/integration evidence; required Windows Quality/Smoke are green; no P0/P1 or explicit fix-through must-fix finding remains; unverified live-model/human evidence is called out rather than inferred.
- Related ADRs: Existing ADRs only unless a policy/authority/irreversible contract change requires a new or superseding ADR.
- Related decision logs: None required at start; create only for actual workflow/authority/policy decisions.
- Related task id(s): Workflow/harness maintenance initiative (no gameplay Taskmaster ownership transfer).
- Related run id: n/a — this is a repository workflow/harness maintenance initiative, not a gameplay Task pipeline run; formal evidence is attached to PR/CI runs instead.
- Related latest.json: n/a — no Task-scoped producer run owns this maintenance initiative, so there is no canonical pipeline latest pointer to resume.
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

## Phase A-E closure record

### Phase A — context routing

- `AGENTS.md` is a route table rather than a fixed preload stack; cross-domain work composes the required routes.
- `docs/agents/01-session-recovery.md` is compact recommendation-first and expands events/sidecars only when the decision requires them.
- `workflow.md` no longer reintroduces `docs/agents/00-index.md` as a global preload; the hard routing test protects this downstream boundary.
- `scripts/python/tests/test_agent_context_routing.py` hardens A2/A3/K3: Chapters 3/4/5/7 do not inherit Chapter 6 recovery preload, cross-domain Architecture/Contract + Testing/MVG sources remain composable, and bounded Knowledge cannot silently widen after RED.
- Fresh Chapter 6 tasks continue through the existing no-latest preflight path; recovery keeps recommendation-only read semantics.

### Phase B — residual / debt / plan policy

- `_technical_debt.py` adapts the real `sc-llm-review` child `summary_file`, preserves unreviewed findings, and updates by stable finding identity.
- Residual recording writes the existing `docs/technical-debt.md`; it no longer auto-creates Decision Log + Execution Plan pairs.
- P1 is the delivery floor for playable-ea/fast-ship/standard; explicit weaker P0 is rejected and stricter P2/P3 fix-through remains binding.
- `_execution_plan_policy.py` now uses durable recovery/coordination signals. `recommended` is advisory/non-blocking; test-file count, mixed file types and verify weight do not mechanically require a plan.

### Phase C — Single Reviewer + lenses

- Chapter 6 model review defaults to one `code-reviewer` with Spec Compliance / Edge Case / Verification Gap.
- Required Acceptance semantic input is reviewer-independent and cannot be silently dropped to manufacture a clean result.
- Invalid Review Contract JSON or a contract missing a required lens is explicitly rejected by hard regression; timeout/invalid/missing-lens outcomes therefore remain incomplete/failed rather than clean.
- Findings use stable identity/claim/anchor/required-action signatures; two different findings from the same reviewer are not repeat stop-loss.
- Deterministic changed-path surface focus selects at most three relevant methods (Save/Load, Contract/EventBus, UI/Scene, State Machine, Security, Performance). These are methods, not personas, and are recorded in reviewer artifacts.
- `--final-pass` means complete deterministic evidence plus the single reviewer’s complete applicable lenses/changed-surface review; it does not restore the historical model persona roster.

### Phase D — verification surfaces / causal RED

- Existing task-view Acceptance authority carries optional `acceptance_verification`; mixed anchors use obligation-level entries and preserve the parent anchor.
- `core-behavior`, `godot-scene`, `player-journey`, and `human-experience` have distinct evidence rules. Human pending/failed is non-passing; passed human evidence is revision-bound.
- Legacy `.cs/.gd` Acceptance refs produce read-only migration candidates using the existing allowed-test-path policy. Mixed, subjective, or ambiguous rows remain `needs-confirmation`; candidate inference never writes task authority.
- Causal RED requires the current `sc-test` run identity, the selected target test identity, and a target assertion failure. Timeout, compile/environment failure, missing reports, zero tests, and unrelated unit/GdUnit failures are rejected.
- Unit RED causality now prefers the current run's `tests.trx` failed testcase identity plus assertion message, with legacy `failure_excerpt` only as a compatibility fallback when TRX evidence is unavailable.
- Existing correct tests are reused as regressions: when all bound test files already exist, red-first does not call the primary-ref LLM selector or manufacture a RED.
- GREEN prerequisite is obligation-aware: pure human-experience may start implementation from explicit manual preflight/pending evidence; any automated or unclassified obligation still requires the machine RED chain.
- MVG critical/full keeps producer/consumer tasks as done prerequisites, while a dedicated owner-only integration task does not require itself to be done for the same MVG run. Existing m1-critical/m1-full/reward-pilot blocker sets are unchanged.

### Phase E — recovery convergence

- `_chapter6_recovery_common.py` remains the common execution-permission and compact recovery projection layer; Chapter 5 readiness fails closed before execution.
- Resume/inspect compact projection has a hard parity regression for action/blocked/approval/forbidden fields.
- Approval, planned-only terminal bundles, artifact integrity, rerun guard, deterministic reuse invalidation and code/task-semantics invalidation keep their existing producer-authority semantics.
- 6.9 remains `run-local-hard-checks --skip-project-health`; target-test success cannot override a later repository/hard-check regression failure.

## Acceptance matrix snapshot

| IDs | Evidence status |
| --- | --- |
| A1-A4 | Covered by existing fresh-task/recovery tests plus hard context-routing contract. Recommendation-only remains read-only by default. |
| K1-K3 | Knowledge fallback and handoff tests remain hard-gated; new routing regression forbids mid-TDD semantic Locator widening. |
| B1-B5 | Covered by Technical Debt adapter/preservation/error tests, P1/fix-through tests, and required/recommended/none plan-policy tests. |
| C1-C5 | Covered by prompt-shaping, review-contract, finding-signature, timeout/incomplete, single-reviewer normalization, surface-focus and final-pass tests. |
| D1-D7 | Covered by target-bound RED tests, generator existing-regression test, verification-surface/mixed/human tests, MVG scope/runtime tests, and owner-only integration-task regression. |
| E1-E4 | Covered by compact recovery parity, readiness/approval/artifact-integrity tests, snapshot/change invalidation tests, and hard-check fail-fast behavior. |

## Formal validation evidence and limits

- Confirmed earlier implementation checkpoint `9eead8913aebb1c4907941352acbf6412a9394db`: Windows Quality Gate #872 success, Windows Smoke #872 success, MVG Integration #70 success.
- The final closure deltas after that checkpoint are intentionally not inferred from the earlier green run. Latest-head Windows Quality/Smoke/MVG must be green before this plan can move past formal CI validation.
- Windows Smoke is the authoritative dedicated Godot/GdUnit/headless smoke signal. Soft-gate warnings in Quality remain non-authoritative for gameplay runtime completion.
- No authenticated live-model reviewer input/output integration run is recorded yet for the final Single Reviewer contract. Unit/mock prompt tests do not satisfy that requirement.
- This remains intentionally unverified in the absence of a runnable authenticated `codex-cli` or `openai-api` backend; do not mark the plan done or infer model integration success from deterministic CI.
- This workflow-maintenance initiative does not create human gameplay approval on behalf of a product task. Human-experience semantics are validated through the evidence contract and isolated fixtures; a real feature still requires its own bound human evidence when applicable.
