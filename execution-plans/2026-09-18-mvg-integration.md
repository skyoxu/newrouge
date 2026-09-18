# MVG integration implementation

- Title: MVG integration evidence and reward pilot
- Status: In progress
- Branch: feat/mvg-integration-acceptance
- Git Head: 43bee5d048d2d2c8285432b17900c0ccde014a62
- Goal: Verify integrated task behavior without adding heavy per-task review.
- Scope: Manifest, ownership validation, isolated runner, reward tests, conservative recommendations, optional mutation and chapter documentation.
- Current step: Repair the P1/P2 review findings and verify Windows CI.
- Last completed step: Windows MVG Integration Pilot run 35334091880 passed, including the disconnected-input challenge.
- Stop-loss: Do not count missing/skipped reports, compilation failure or timeout as acceptance or mutation detection.
- Next action: Review PR #180 and remaining existing repository checks; extend the pilot manifest for actual full-MVG scope.
- Recovery command: py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode plan
- Open questions: Reward pilot does not represent the whole MVG; existing broad quality/smoke jobs were still running when this evidence was recorded.
- Exit criteria: Scoped tests pass, execution limits documented, branch pushed without merging.
- Related ADRs: `docs/adr/ADR-0037-mvg-integration-evidence.md`
- Related decision logs: `decision-logs/2026-09-18-mvg-integration.md`
- Related task id(s): n/a - infrastructure work; pilot references existing business tasks without changing status.
- Related run id: 20260918T102043Z-0bbc8abd; GitHub Actions 35334091880.
- Related latest.json: n/a - no task review pipeline run or authority changes.
- Related pipeline artifacts: `logs/ci/mvg-acceptance/`, `logs/ci/mvg-mutation/`

Windows evidence: https://github.com/skyoxu/newrouge/actions/runs/35334091880
