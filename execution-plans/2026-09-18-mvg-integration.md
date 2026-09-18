# MVG integration implementation

- Title: MVG integration evidence and reward pilot
- Status: Completed implementation and scoped verification
- Branch: feat/mvg-integration-acceptance
- Git Head: 703b5db6ac80d8c368bb0f3d0b25c093de37664e
- Goal: Verify integrated task behavior without adding heavy per-task review.
- Scope: Manifest, ownership validation, isolated runner, reward tests, conservative recommendations, optional mutation and chapter documentation.
- Current step: All review repairs implemented; Windows MVG pilot verified. Track full PR checks on GitHub before merging.
- Last completed step: Windows MVG Integration Pilot run 35336807426 passed after the review repairs.
- Stop-loss: Do not count missing/skipped reports, compilation failure or timeout as acceptance or mutation detection.
- Next action: Review PR #180 and remaining existing repository checks; extend the pilot manifest for actual full-MVG scope.
- Recovery command: py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode plan
- Open questions: Reward pilot does not represent the whole MVG. Broad checks are tracked on PR #180; no merge authorization.
- Exit criteria: Scoped tests pass, execution limits documented, branch pushed without merging.
- Related ADRs: `docs/adr/ADR-0037-mvg-integration-evidence.md`
- Related decision logs: `decision-logs/2026-09-18-mvg-integration.md`
- Related task id(s): n/a - infrastructure work; pilot references existing business tasks without changing status.
- Related run id: 20260918T102043Z-0bbc8abd; GitHub Actions 35334091880.
- Related latest.json: n/a - no task review pipeline run or authority changes.
- Related pipeline artifacts: `logs/ci/mvg-acceptance/`, `logs/ci/mvg-mutation/`

Windows evidence: https://github.com/skyoxu/newrouge/actions/runs/35334091880

Review repair runtime evidence: https://github.com/skyoxu/newrouge/actions/runs/35336807426
