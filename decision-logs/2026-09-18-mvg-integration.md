# MVG integration evidence boundary

- Title: Keep MVG acceptance bounded and separate from task-state authority
- Date: 2026-09-18
- Status: Implemented and verified within the reward pilot scope
- Supersedes: None
- Superseded by: None
- Branch: feat/mvg-integration-acceptance
- Git Head: 43bee5d048d2d2c8285432b17900c0ccde014a62
- Why now: Per-task gates do not prove behavior across the combined commits.
- Context: User chose functional tasks, profile-based review, human gameplay evaluation and MVG knowledge refresh.
- Decision: Add opt-in manifest and isolated runtime evidence; explicit mappings never exclude required tests; mutation remains optional.
- Consequences: Reward pilot is a narrow example, not full MVG coverage. Input tests do not prove mouse geometry, focus navigation, save/reload or subjective quality.
- Recovery impact: Use the matching run summary and input digest. Do not reuse planned-only output as runtime evidence. Windows run evidence is scoped to the integrated input version; it is not task-status authorization.
- Validation: Python failure-path tests and real manifest plan pass. Seeded mutation baseline: 3 passed; both boundary mutants killed by one assertion each. Godot C# build: 0 warnings/errors. Linux direct Godot diagnostic: reward journey 1 passed; disconnected-input challenge failed at the expected assertion (exit 100). Windows formal runner passed (runtime_verified=true), including the disconnected-input challenge, in Actions run 35334091880. Full recovery-doc validation passed on Windows. Full recovery-doc validation on Linux reports pre-existing Windows drive-letter paths as missing; both new documents validate individually.
- Related ADRs: `docs/adr/ADR-0037-mvg-integration-evidence.md`
- Related execution plans: `execution-plans/2026-09-18-mvg-integration.md`
- Related task id(s): n/a - infrastructure work only; no task status writes.
- Related run id: 20260918T102043Z-0bbc8abd; GitHub Actions 35334091880.
- Related latest.json: n/a - task review pipeline remains unchanged.
- Related pipeline artifacts: `logs/ci/mvg-acceptance/`, `logs/ci/mvg-mutation/`

CI evidence: https://github.com/skyoxu/newrouge/actions/runs/35334091880

Artifact: mvg-integration-evidence (10542590266). Existing broad quality/smoke checks remain separate from this pilot result.

## Review repairs

Resolved review findings: workflow gate registration (P1), exact report identity/counts, reward amount/idempotency assertions and recommendation revision binding (P2). Repair on the same branch; retain all existing gates. Evidence: logs/ci/mvg-repair/.

Repair evidence: the new actual-entry replay test first failed (two cards after two identical claims), then passed after rejecting already-resolved typed rewards. Local Godot reward suites: 3 passed, zero failures/skips. Exact gold assertions, report identity/count checks, revision-bound comparison and shared prewarm implemented. Workflow enforcement now reports zero violations. Windows MVG rerun 35336807426 passed; this includes exact report matching, both Godot suites with shared prewarm, and the disconnected-input challenge. Full PR check statuses remain GitHub authority.

All four review findings are implemented. The additionally reproduced typed reward replay bug is fixed at the actual settlement entry. No existing gate was disabled; recovery-document validation remains in the existing quality bundle.
