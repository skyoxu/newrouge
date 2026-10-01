# Capability alignment and review publication recovery

- Title: planning-alignment-review-recovery
- Status: In progress
- Branch: fix/planning-alignment-review-recovery
- Git Head: 5bc0e670f8ffca520f4fb87b4f42dd8fe38101cf
- Goal: Repair R01 (P1 ambiguous stable identity) and R02 (P2 interrupted review publication) from the merged-main three-document re-audit.
- Scope: Derived Capability alignment/preflight and Capability/MVG review publication; isolated acceptance fixture metadata and owning instructions.
- Current step: Submit the repair and verify Windows/real-model CI.
- Last completed step: All 25 new regressions and 269 three-document core tests pass; Git/worktree topology and gate documentation consistency pass.
- Stop-loss: Preserve business/source/Taskmaster authority, blocked verdicts and consumed attempts; do not reset budgets or weaken gates.
- Next action: Complete regressions, run the unified local hard-check harness once, submit a repair PR and inspect Windows/real-model CI.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_review_recovery -v`
- Open questions: None; platform and production execution remain validation obligations.
- Exit criteria: Both findings pass negative and positive recovery paths, all three-document regressions pass, Windows and real-model CI pass.
- Related ADRs: n/a (implements existing identity and recovery contracts)
- Related decision logs: n/a (no authority or budget policy change)
- Related task id(s): n/a (workflow repair)
- Related run id: n/a (PR not created yet)
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
