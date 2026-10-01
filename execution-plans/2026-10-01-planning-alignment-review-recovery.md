# Capability alignment and review publication recovery

- Title: planning-alignment-review-recovery
- Status: Implemented; final CI tracked in PR #255
- Branch: fix/planning-alignment-review-recovery
- Git Head: 7743a7271f2727d2d9578760fb52d5b0f1163e1e
- Goal: Repair R01 (P1 ambiguous stable identity) and R02 (P2 interrupted review publication) from the merged-main three-document re-audit.
- Scope: Derived Capability alignment/preflight and Capability/MVG review publication; isolated acceptance fixture metadata and owning instructions.
- Current step: Validate the final identity-copy prompt repair; preserve every prior production result and record final CI in PR #255 without another documentation-only synchronization.
- Last completed step: Verified 30 new/274 core regressions, Windows hard gates and fresh real-model approval plus retained-result consumer replay.
- Stop-loss: Preserve business/source/Taskmaster authority, blocked verdicts and consumed attempts; do not reset budgets or weaken gates.
- Next action: Verify final-head workflows before review for merge.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_review_recovery -v`
- Open questions: Final-head actual-model validation is required after the identity-copy repair.
- Exit criteria: Both findings pass negative and positive recovery paths, all three-document regressions pass, Windows and real-model CI pass.
- Related ADRs: n/a (implements existing identity and recovery contracts)
- Related decision logs: n/a (no authority or budget policy change)
- Related task id(s): n/a (workflow repair)
- Related run id: PR #255; production 36847620516, Windows quality 36847620638, Windows smoke 36847620738 and MVG integration 36847620559 PASS
- Related latest.json: n/a (explicit repair evidence paths)
- Related pipeline artifacts: `logs/ci/planning-review-recovery/**`

Baseline: main squash merge #253, tree d51ed81447ef411a1099f686fe1358cf05177908. The controlling documents remain Chapter 3 closeout v2, portability v2 and Capability/MVG creation v3.

- [x] Preserve initial ten-test red evidence: six failures and three errors on merged main.
- [x] Require explicit decisions for ambiguous historical/candidate membership and reject colliding IDs before formal writes.
- [x] Validate the complete projected semantic topology before the apply journal.
- [x] Persist hash-bound multi-file review publication and recover the recorded verdict/receipt/corrections.
- [x] Complete legal multi-membership, corruption, blocked/draft and revised-proposal regressions.
- [x] Run three-document regressions and local checks; synchronize owning instructions.
- [x] Verify Windows/platform and real-model CI.
- [x] Publish the repair PR and final CI/evidence record.

Responsibility split: new alignment and review-publication helpers remain below 400 lines and reduce existing oversized planners. The fixture correction uses the production topology-manifest schema and identity fields; it changes no fictional contract, reviewed obligation or reviewer rule.

Local validation: 274 core tests pass. Both semantic-topology validations pass for 139 blocks and 127 active delivery Requirements with zero issues. The unified local harness initially stops before any gate because Linux has no Windows `py` launcher; an external scratch launcher then executes the real Python checks. Existing Windows-only unit behavior (`cmd`, `ctypes.windll`, Windows path/rollback) and historical absolute Windows recovery-evidence paths block the Linux hard bundle. No gate/test is disabled. The new execution plan validates independently. The existing Windows workflows provide platform/.NET/Godot evidence; the production workflow provides fresh actual-model evidence.

Initial implementation c1c67678 passed real production, MVG integration and Windows smoke. Supplementary regressions then found the adjacent settled-attempt/pre-publication window: Capability and MVG both called another reviewer despite retaining the completed output. `completed-attempt-red.log` preserves those failures. Recovery now requires the original output hash and execution metadata, reuses the same receipt/result/corrections, and preserves the already settled budget. Final validation/CI must use the strengthened implementation rather than treating the first pass as final evidence.

Strengthened implementation fe3a2f9b passes 30 new/274 core regressions and production deterministic smoke (103 tests). Actual production run 36845534237 is correctly BLOCKED by the independent reviewer: the generated proposal preserves request/result/retry data but omits the source-required explicit relay-service-to-score-terminal interaction and its domain-integration test assertion. Artifact 11152719135 (digest sha256:08f9ae256ad4a62ab34b1728a7bcfc1b88a718ddb74f77ce3f58fb7fc0e520bc) retains the fixed proposal, single blocked verdict and execution evidence. The material repair adds a generic generator instruction to preserve source-named producer/consumer system roles, map each to real ownership even when roles share a task, and assert the same interaction in flows, entrypoints and planned test scenarios. Existing bounded-generation prompt-forwarding tests cover this instruction. Reviewer gates, input authority, contract and attempt budgets remain unchanged; a fresh chain must pass before closeout.

Run 36846454889 at afb78d86 preserves the required source roles but correctly exhausts three generator attempts: each uses coverage_rationale rather than the validator's rationale field. Artifact 11154230470 (digest sha256:3a2ec6d50fc19a4b0e0f8869d59eedba07912a5257f45df9f42a633e8976fa54) retains all three outputs. The prompt's prose "coverage rationale" and the error label coverage_rationale_missing left the literal JSON field ambiguous. The narrow repair explicitly names rationale in both initial/correction prompts and explains the error label; validator acceptance and attempt limits stay unchanged. The existing bounded-generation regression now reproduces that wrong field and checks the exact schema instruction in every replacement prompt.

Final implementation a67a048e: all four workflows PASS. Windows Quality runs 968 Python tests with zero failures and hard bundle 0/25 failures; Smoke and MVG Integration PASS. Production run 36847620516 passes all 103 deterministic smoke tests and the actual model chain. Artifact 11154531435, digest sha256:02bcd1ebb81a40510f7b94e49b1101c76b4cededb17f4e370450e39b13caad73. Three fresh valid Capability candidates and their anonymous reviewer use actual gpt-6-luna; candidate-1 is selected. Both fixture Tasks 7/42 remain Chapter 5 READY after apply. MVG generation uses two bounded attempts; a separate fresh gpt-6-luna semantic reviewer approves in one invocation. Final validation has zero errors/gaps and formal_applicable=true. Manifest application/runtime verification remain outside this planning acceptance (both false).

Downloaded Capability review/publication replay succeeds without a model call or budget change; MVG review identity/accounting and completed publication replay pass with no writes. This is a retained-consumer replay, not a full freshness replay of the original CI workspace, whose original authority files are not all included in the artifact. Both blocked production artifacts remain preserved; no reviewing run or budget was reset. Final local core suite passes 274 tests. This closeout edits only this plan and the owning acceptance record; executable code remains at a67a048e.

Documentation-only closeout 75eca5ce triggers a fresh chain because pull-request path filters consider the whole PR diff. Run 36849699351 correctly blocks the independent reviewer's mistyped proposal hash: sha256:c5b342... instead of the prompt's sha256:c5c2b342.... Artifact 11154659573 (digest sha256:973041ef538f25ceb8a9b18c9286f94fe5e9b1b6e63abf119c9a979138bfd022) preserves the approved semantic content, invalid identity and single consumed review attempt. The prompt now explicitly requires verbatim copying of both host-supplied identities. Two negative regressions cover analysis/proposal identity mistakes at publication and completed-attempt boundaries, preserving the raw invalid report, blocking formal approval and making no repeat invocation. No identity normalization, verdict correction, validator change or budget reset is introduced. Final CI evidence is maintained in the PR and delivery report to avoid triggering another fresh production chain solely to record its result.

Identity-copy implementation 0e531c08 passes actual production run 36851376096/artifact 11155783305 (digest sha256:10ad73899918ae96ac0cad5162815b7af2c982608234538b2566e873c42051ed). Documentation-format revision 7743a727 then correctly stops candidate generation in run 36851834049: auto routes candidate-1 to mai-code-1.1-flash and candidate-2 to gpt-6-luna until its configured budget is exhausted. Artifact 11155669475 (digest sha256:ffcc534431de4147a422cb020de12872b2bcb71e3e98e5bc9c80692cb56c849d) preserves all attempts. Stop-loss alternatives: keep auto and its legitimate bounded block; request a configured fixed model for controlled production acceptance; or add cross-run model-pinning machinery. Choose the narrow fixed-model acceptance configuration, defaulting to the already observed gpt-6-luna and configurable with SC_PLANNING_COPILOT_MODEL. This changes only this acceptance job, leaves public runner auto support intact, and still requires actual execution receipts to agree. No retries or same-model validator are changed; final production must prove the explicitly requested model works.
