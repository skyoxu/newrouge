# Project Health Knowledge Integration

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

See `decision-logs/2026-09-07-project-health-impact-limits.md` for the existing unsupported generic parameter and stale publication findings. Extend the formal parser under targeted fixtures and validate with real frozen KCP evidence; do not reuse an exploratory preview as a formal handoff. Runtime Godot verification and broad automatic task-to-code inference remain outside static attachment guarantees.
