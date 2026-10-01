# Capability alignment and review publication recovery

- Title: planning-alignment-review-recovery
- Status: In progress
- Branch: fix/planning-alignment-review-recovery
- Git Head: 5bc0e670f8ffca520f4fb87b4f42dd8fe38101cf
- Goal: Repair R01 (P1 ambiguous stable identity) and R02 (P2 interrupted review publication) from the merged-main three-document re-audit.
- Scope: Derived Capability alignment/preflight and Capability/MVG review publication; isolated acceptance fixture metadata and owning instructions.
- Current step: Submit the repair and verify Windows/real-model CI.
- Last completed step: All 30 focused regressions pass, including completed-attempt recovery, original-output drift and unpublished-proposal revision guards.
- Stop-loss: Preserve business/source/Taskmaster authority, blocked verdicts and consumed attempts; do not reset budgets or weaken gates.
- Next action: Complete regressions, run the unified local hard-check harness once, submit a repair PR and inspect Windows/real-model CI.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_review_recovery -v`
- Open questions: None; platform and production execution remain validation obligations.
- Exit criteria: Both findings pass negative and positive recovery paths, all three-document regressions pass, Windows and real-model CI pass.
- Related ADRs: n/a (implements existing identity and recovery contracts)
- Related decision logs: n/a (no authority or budget policy change)
- Related task id(s): n/a (workflow repair)
- Related run id: PR #255; initial production 36844178194, Windows smoke 36844178146 and MVG integration 36844178280 PASS
- Related latest.json: n/a (explicit repair evidence paths)
- Related pipeline artifacts: `logs/ci/planning-review-recovery/**`

Baseline: main squash merge #253, tree d51ed81447ef411a1099f686fe1358cf05177908. The controlling documents remain Chapter 3 closeout v2, portability v2 and Capability/MVG creation v3.

- [x] Preserve initial ten-test red evidence: six failures and three errors on merged main.
- [x] Require explicit decisions for ambiguous historical/candidate membership and reject colliding IDs before formal writes.
- [x] Validate the complete projected semantic topology before the apply journal.
- [x] Persist hash-bound multi-file review publication and recover the recorded verdict/receipt/corrections.
- [x] Complete legal multi-membership, corruption, blocked/draft and revised-proposal regressions.
- [x] Run three-document regressions and local checks; synchronize owning instructions.
- [ ] Verify Windows/platform and real-model CI.
- [ ] Publish the repair PR and final CI/evidence record.

Responsibility split: new alignment and review-publication helpers remain below 400 lines and reduce existing oversized planners. The fixture correction uses the production topology-manifest schema and identity fields; it changes no fictional contract, reviewed obligation or reviewer rule.

Local validation: 269 core tests pass. Both semantic-topology validations pass for 139 blocks and 127 active delivery Requirements with zero issues. The unified local harness initially stops before any gate because Linux has no Windows `py` launcher; an external scratch launcher then executes the real Python checks. Existing Windows-only unit behavior (`cmd`, `ctypes.windll`, Windows path/rollback) and historical absolute Windows recovery-evidence paths block the Linux hard bundle. No gate/test is disabled. The new execution plan validates independently. The existing Windows workflows provide platform/.NET/Godot evidence; the production workflow provides fresh actual-model evidence.

Initial implementation c1c67678 passed real production, MVG integration and Windows smoke. Supplementary regressions then found the adjacent settled-attempt/pre-publication window: Capability and MVG both called another reviewer despite retaining the completed output. `completed-attempt-red.log` preserves those failures. Recovery now requires the original output hash and execution metadata, reuses the same receipt/result/corrections, and preserves the already settled budget. Final validation/CI must use the strengthened implementation rather than treating the first pass as final evidence.

Strengthened implementation fe3a2f9b passes 30 new/274 core regressions and production deterministic smoke (103 tests). Actual production run 36845534237 is correctly BLOCKED by the independent reviewer: the generated proposal preserves request/result/retry data but omits the source-required explicit relay-service-to-score-terminal interaction and its domain-integration test assertion. Artifact 11152719135 (digest sha256:08f9ae256ad4a62ab34b1728a7bcfc1b88a718ddb74f77ce3f58fb7fc0e520bc) retains the fixed proposal, single blocked verdict and execution evidence. The material repair adds a generic generator instruction to preserve source-named producer/consumer system roles, map each to real ownership even when roles share a task, and assert the same interaction in flows, entrypoints and planned test scenarios. Existing bounded-generation prompt-forwarding tests cover this instruction. Reviewer gates, input authority, contract and attempt budgets remain unchanged; a fresh chain must pass before closeout.

Run 36846454889 at afb78d86 preserves the required source roles but correctly exhausts three generator attempts: each uses coverage_rationale rather than the validator's rationale field. Artifact 11154230470 (digest sha256:3a2ec6d50fc19a4b0e0f8869d59eedba07912a5257f45df9f42a633e8976fa54) retains all three outputs. The prompt's prose "coverage rationale" and the error label coverage_rationale_missing left the literal JSON field ambiguous. The narrow repair explicitly names rationale in both initial/correction prompts and explains the error label; validator acceptance and attempt limits stay unchanged. The existing bounded-generation regression now reproduces that wrong field and checks the exact schema instruction in every replacement prompt.
