# Project Health Knowledge Integration

- Title: Project Health Knowledge Integration
- Status: active
- Branch: feat/project-health-knowledge-impact
- Git Head: 814a1e010579c24a543d26115f3cb2d337bcd355
- Goal: Add main-only knowledge and Impact investigation to the existing local health service.
- Scope: CLI/API, GDD configuration, SSOT task pagination and static scene attachment evidence.
- Current step: Repair required recovery metadata after PR 166 CI failure.
- Last completed step: Local feature tests and HTTP smoke passed; CI identified missing recovery metadata.
- Stop-loss: Do not weaken recovery validation or treat exploratory results as formal handoff evidence.
- Next action: Validate both recovery directories and rerun PR CI; separately complete native Windows and Godot verification.
- Recovery command: py -3 scripts/python/validate_recovery_docs.py --dir all
- Open questions: Native Windows lifecycle, runtime Godot proof and full formal Impact coverage remain unverified.
- Exit criteria: Required recovery metadata validates and PR CI passes without disabling gates.
- Related ADRs: docs/adr/ADR-0036-project-health-investigation.md
- Related decision logs: decision-logs/2026-09-07-project-health-impact-limits.md
- Related task id(s): n/a - repository tooling, not a gameplay Taskmaster task
- Related run id: 34104776509
- Related latest.json: logs/ci/project-health-knowledge/latest.json
- Related pipeline artifacts: logs/ci/2026-09-07/gate-bundle/runs/gh-34104776509-a1/hard/summary.json

## Scope

Add a local second-level knowledge/Impact investigation page to workflow 2.4. Keep chapter skills and task authority unchanged. Main-only snapshots, task pagination/details, GDD configuration and conservative Godot evidence are included.

## Validation

- `py -3 -m unittest discover -s scripts/sc/tests -p "test_project_health*.py"`
- `py -3 -m unittest discover -s scripts/python/tests -p "test_impact_analyzer.py"`
- `py -3 scripts/python/project_health_knowledge.py scan`
- Query Chinese reward requirements and select the RewardScene file target.
- Evidence: `logs/ci/project-health-knowledge/latest.json`, `logs/ci/project-health-knowledge/queries/`.

## Observed Results (2026-09-07)

- Project-health suite: 31 passed. Impact suite: 112 passed (historical BOM audit baseline fetched before rerun).
- JavaScript syntax and Git whitespace checks passed.
- Real main scan: 133 tasks; 111 done, 16 pending, 6 cancelled. Scene mapping: 1 declared/static-checked attachment (task 115), 73 candidates, 59 unmapped.
- Real HTTP smoke: dashboard/page/assets/status/tasks page 7/task 115 returned 200; page 7 contained 13 tasks. Chinese reward query found 23 knowledge candidates; selected RewardScene target resolved to its script and Reward.tscn attachment.
- 515 unsupported method signatures were explicitly omitted in exploration. No formal report was created from this partial result.
- Validation ran under Linux/Python 3.12. Native Windows detached-service lifecycle and Godot runtime execution were not tested.

## Follow-up Repair Entry

The first PR run failed only `validate_recovery_docs`: these recovery files lacked the required template metadata. Earlier Windows quality failures in runs 34029458288 / 34029167695 involved an Impact reparse-path error-code assertion; run 34024233592 involved concurrent CLI publication error codes. Sharing the hard-bundle step does not imply a shared root cause. This repair adds metadata without weakening the validator. Future delivery checks must include `py -3 scripts/python/validate_recovery_docs.py --dir all`, not only focused feature tests.

See `decision-logs/2026-09-07-project-health-impact-limits.md` for the existing unsupported generic parameter and stale publication findings. Extend the formal parser under targeted fixtures and validate with real frozen KCP evidence; do not reuse an exploratory preview as a formal handoff. Runtime Godot verification and broad automatic task-to-code inference remain outside static attachment guarantees.
