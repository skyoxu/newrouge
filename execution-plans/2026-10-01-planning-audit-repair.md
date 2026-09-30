# Planning acceptance audit repair

Owner: PR #251. Starting revision: 86164cfff58046f121038e2fe0409e1f1af818cb.

- Title: planning-audit-repair
- Status: In progress
- Branch: fix/planning-audit-repair
- Git Head: 86164cfff58046f121038e2fe0409e1f1af818cb
- Goal: Close the six production-entry defects in the three-document implementation audit.
- Scope: Planning validation, durable apply recovery and Chapter 6 obligation gates; no business-source/task changes.
- Current step: Run repository checks and current-revision production acceptance.
- Last completed step: All six original defects reproduce in RED and pass; 19 focused repair tests and the final 48-test topology/planning set pass.
- Stop-loss: Preserve user edits and prepared identities; never bypass pending transactions, semantic review or stale handoffs.
- Next action: Inspect CI for the next repaired revision; the first repair production run 36754458273 blocked on missing Copilot model identity at MVG review. Retry remains bounded and never weakens the identity check.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_audit_repair -v`
- Open questions: None; Windows runtime validation uses existing CI because this workspace has no .NET/Godot binaries.
- Exit criteria: Current implementation passes repository gates and the real isolated Capability-to-MVG production chain.
- Related ADRs: none; implements existing approved requirement boundaries.
- Related decision logs: none; no new policy or irreversible decision.
- Related task id(s): n/a (workflow implementation; no business-task status edits)
- Related run id: n/a (CI run assigned after push)
- Related latest.json: n/a (repo-level repair; logs are under logs/ci/planning-audit-repair/)
- Related pipeline artifacts: `logs/ci/planning-audit-repair/**`

Scope: implement the six production-entry defects identified against the Chapter 3 closeout v2, workflow portability v2, and Capability/MVG creation v3 requirements. Preserve authoritative sources, Taskmaster statuses, task IDs and Chapter 3 source declarations.

- [x] A01: normalize ledger source text hashes consistently across Git and CRLF workspaces.
- [x] A02: check all task and non-task sinks of the current source round before formal planning.
- [x] A03: enforce complete Requirement verification accounting and an independent MVG semantic review.
- [x] A04: bind MVG proposals/deltas to every prepared authority input and the original manifest.
- [x] A05: consume persisted MVG obligation bindings at Chapter 6 entry; bind actual milestone handoffs to the applied manifest.
- [x] A06: journal Capability apply and recover interrupted writes and readiness rebinding without overriding external edits.
- [ ] Run focused negative/positive tests and appropriate repository checks.
- [ ] Update workflow instructions, acceptance evidence and PR #251; inspect CI for the pushed revision.

Validation evidence belongs under logs/ci/planning-audit-repair/. Real model acceptance must use the isolated production fixture and must distinguish planning evidence from runtime verification. No game execution is required by this repair.
