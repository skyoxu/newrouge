# Main planning audit fixes

- Title: planning-main-audit-fixes
- Status: In Progress
- Branch: fix/planning-main-audit
- Git Head: 75346cbda0ce96ed801fe05242ef7f04e2af056c
- Goal: Repair the one P1 and four P2 defects reproduced in the main three-document audit.
- Scope: Prepared MVG evidence, Capability interruption/review recovery, report validation and cross-checkout manifest identities.
- Current step: Run repository hard checks, inspect the final diff, then open the repair PR for Windows and real-model CI.
- Last completed step: Repair all five defects and interrupt-time runner cleanup; 230 three-document regressions pass, including 15 new production-entry tests.
- Stop-loss: Preserve task/business authorities, original snapshots and valid model evidence; do not reset budgets or bypass stale-input gates.
- Next action: Preserve the local check result, push the implementation and collect PR CI evidence.
- Recovery command: `py -3 -m unittest scripts.python.tests.test_planning_main_audit_fixes -v`
- Open questions: None; Windows and real model validation use repository CI.
- Exit criteria: All five counterexamples and positive recovery paths pass; Windows and real production acceptance pass on the final implementation.
- Related ADRs: n/a (repairs the existing requirement contract; no new architectural decision)
- Related decision logs: n/a (no new policy or irreversible authority decision)
- Related task id(s): n/a (workflow repair, no business task edits)
- Related run id: PR #253; first revision production run 36817314309 PASS; final revision CI pending
- Related latest.json: n/a (workflow repair uses the explicit PR and evidence paths below)
- Related pipeline artifacts: `logs/ci/planning-main-audit-fixes/**`

Baseline audit: main 75346cbd; Chapter 3 closeout v2, portability v2, Capability/MVG creation v3. No source declaration, GDD, Taskmaster status or game implementation change is authorized by this repair scope.

- [x] F01: Reject unprepared existing verification dependencies and post-review drift before MVG formal apply.
- [x] F02: Persist Capability candidate/review attempts and budget reservations before model invocation; settle interruption safely.
- [x] F03: Reuse an identity-bound valid Capability review without another invocation.
- [x] F04: Use normalized manifest content identity across trace, handoff and Chapter 6; retain byte-exact apply journals.
- [x] F05: Validate complete Capability review reports and resolvable source evidence.
- [x] Run focused and three-document regressions; synchronize owning instructions and acceptance evidence.
- [ ] Push the repair, open a PR and verify Windows/MVG/real-model CI evidence.

Verification: the initial eight counterexamples failed on unmodified main (`logs/ci/planning-main-audit-fixes/red.log`). After implementation, the core three-document suite passes 230 tests (`three-document-regressions.log`). Fifteen new tests cover all five findings, valid reuse/corrections/no-winner, corrupt cache/input/receipt, planned paths, baseline dependencies and process-loss/request reservations. An additional real subprocess case proves a caught runner interruption terminates and reaps the child before budget settlement; Windows taskkill has a checked parent-kill fallback. Existing journal interruption tests still pass. No business/source/Taskmaster authority is changed.

Local hard-check harness was run once. Its 933-test bundle passes all new planning tests, but eight existing Windows-specific tests fail on Linux (`cmd`, `ctypes.windll`, Windows path/rollback behavior). Recovery-doc validation also encounters historical absolute Windows evidence paths on Linux; this plan's initially incomplete n/a fields were corrected and its standalone validation now passes. No tests/gates are disabled. .NET/Godot are unavailable locally; final platform validation is delegated to the existing Windows PR workflows. Both Git/worktree semantic-topology checks pass with 139 blocks, 127 active Requirements and zero issues; gate-bundle documentation consistency and diff whitespace checks pass.
