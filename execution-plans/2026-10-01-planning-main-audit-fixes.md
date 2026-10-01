# Main planning audit fixes

- Title: planning-main-audit-fixes
- Status: Completed
- Branch: fix/planning-main-audit
- Git Head: 741badf84fcf8fe8bd9c664fbef8a1ff328a7b21
- Goal: Repair the one P1 and four P2 defects reproduced in the main three-document audit.
- Scope: Prepared MVG evidence, Capability interruption/review recovery, report validation and cross-checkout manifest identities.
- Current step: Complete; the final implementation passes all four CI workflows. This checkpoint updates evidence documentation only.
- Last completed step: Verified real corrected-winner/review replay and MVG semantic approval; 232 core tests and 938 Windows hard-bundle tests pass.
- Stop-loss: Preserve task/business authorities, original snapshots and valid model evidence; do not reset budgets or bypass stale-input gates.
- Next action: Review PR #253 for merge; no implementation action remains.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_main_audit_fixes -v`
- Open questions: None; Windows and real-model validation are complete at the recorded implementation revision.
- Exit criteria: All five counterexamples and positive recovery paths pass; Windows and real production acceptance pass on the final implementation.
- Related ADRs: n/a (repairs the existing requirement contract; no new architectural decision)
- Related decision logs: n/a (no new policy or irreversible authority decision)
- Related task id(s): n/a (workflow repair, no business task edits)
- Related run id: PR #253; 36819370222 (production PASS); 36819370219 (Windows quality PASS); 36819370226 (Windows smoke PASS); 36819370213 (MVG integration PASS)
- Related latest.json: n/a (workflow repair uses the explicit PR and evidence paths below)
- Related pipeline artifacts: `logs/ci/planning-main-audit-fixes/**`

Baseline audit: main 75346cbd; Chapter 3 closeout v2, portability v2, Capability/MVG creation v3. No source declaration, GDD, Taskmaster status or game implementation change is authorized by this repair scope.

- [x] F01: Reject unprepared existing verification dependencies and post-review drift before MVG formal apply.
- [x] F02: Persist Capability candidate/review attempts and budget reservations before model invocation; settle interruption safely.
- [x] F03: Reuse an identity-bound valid Capability review without another invocation.
- [x] F04: Use normalized manifest content identity across trace, handoff and Chapter 6; retain byte-exact apply journals.
- [x] F05: Validate complete Capability review reports and resolvable source evidence.
- [x] Run focused and three-document regressions; synchronize owning instructions and acceptance evidence.
- [x] Push the repair, open a PR and verify Windows/MVG/real-model CI evidence.

Verification: the initial eight counterexamples failed on unmodified main (`logs/ci/planning-main-audit-fixes/red.log`). The final core three-document suite passes 232 tests (`three-document-regressions.log`), including 16 main-audit tests and one additional source-to-reviewed-semantics fixture regression. They cover all five findings, valid reuse/corrections/no-winner, corrupt cache/input/receipt, planned paths, baseline dependencies and process-loss/request reservations. A real subprocess case proves a caught runner interruption terminates and reaps the child before budget settlement; Windows taskkill has a checked parent-kill fallback. Existing journal interruption tests still pass. No newrouge business/source/Taskmaster authority is changed.

Local hard-check harness was run once. Its 933-test bundle passes all new planning tests, but eight existing Windows-specific tests fail on Linux (`cmd`, `ctypes.windll`, Windows path/rollback behavior). Recovery-doc validation also encounters historical absolute Windows evidence paths on Linux; this plan's initially incomplete n/a fields were corrected and its standalone validation now passes. No tests/gates are disabled. .NET/Godot are unavailable locally; final platform validation is delegated to the existing Windows PR workflows. Both Git/worktree semantic-topology checks pass with 139 blocks, 127 active Requirements and zero issues; gate-bundle documentation consistency and diff whitespace checks pass.

Production run 36817602089 at 50d6f1bf passed all 71 deterministic smoke tests and Capability stages, but its independent MVG reviewer correctly blocked an entrypoint that accepted only completed transfer/contract data without a completion/failure signal or recovery-policy mapping. The fixed proposal and single blocked review are preserved in artifact 11142246654 (digest sha256:fbc3019ea0b71510b76609308ee9210858ce2e002f952c6b4b8ee18b8e6bc186) and locally under `logs/ci/planning-main-audit-fixes/failed-production/`. No approving-review retry is requested. The material repair strengthens the generic generator prompt to identify request versus result/failure inputs, owned state transitions and recovery-policy effects for each handoff; no fixture contract, source semantics or reviewer approval rule is changed. A fresh acceptance chain on the repaired prompt must pass before completion.

Run 36818090165 at cfa0835d then exposed a reference-format false rejection: valid Capability reports used `analysis-input/...json: ReqID/SourceBlockID, ...` or `batch.json:ID` rather than bare file paths. Artifact 11142835250 (digest sha256:5e16c054bbdd75993e0a249121d0e0071a6b663d41f53cb7857d8719f2ab3340) retains both bounded attempts. The reference parser now resolves qualified IDs against the exact ledger/Requirement/model-batch file and rejects unknown or wrong-file IDs. The reviewer prompt documents the accepted reference formats and required arrays/comparison. Production-entry positive/reuse and wrong-file/unknown-ID negatives pass; both retained real reports now pass deterministic reference validation. No review budget is reset.

Run 36818755312 at 84587679 passed Capability reference validation but MVG review correctly exposed an actual fictional-fixture source ambiguity: unconditional retryable failure was not reconciled with RetryAllowed=false, and required handoff payload values had no declared origin. Artifact 11141953727 (digest sha256:823fb383977182c61539fc32bb00bc71381940a4847e65b4b0687d2f6e0b4424) retains the blocked fixed proposal/review. The fixture generator now declares selected-route RouteId/CargoUnits, constructs accepted requests with RetryAllowed=true, and describes the separate completion/failure input and required retry transition. The existing contract stays unchanged. This is an upstream clarification of an isolated fictional fixture, not a newrouge business-source/GDD/Taskmaster change. A regression proves the clarified statements reach reviewed Chapter 5 semantics and real task/readiness links. Reviewer gates and attempt budgets stay intact.

Final implementation 741badf8: production run 36819370222 PASS, artifact 11142329584, digest sha256:5477067f5a0e3c78a7455a83b53639d40eb16d982c49778baffe2728f66cb7bc. Three valid no-tools candidates and their anonymous review use actual model gpt-6-luna; selected candidate-3 uses bounded corrections. Downloaded review/correction replay validates without another model call. MVG generation has three bounded attempts; the separate fresh mai-code-1.1-flash semantic reviewer approves with zero findings, and final validation returns formal_applicable=true with zero errors/gaps. Runtime remains unverified and the acceptance does not apply the MVG manifest. Same-code Windows Quality (938 tests; hard bundle 0/25 failures), Smoke and MVG Integration all PASS. Owning acceptance documentation records full run URLs and model file hashes. This final checkpoint edits only this plan and the owning acceptance record; executable code remains at the verified revision.
