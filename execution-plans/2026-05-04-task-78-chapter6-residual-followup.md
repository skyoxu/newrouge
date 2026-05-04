# Task 78 Chapter6 Residual Follow-up

## Goal
Close outstanding reviewer `Needs Fix` for Task 78 without wasting additional full reruns.

## Entry Conditions
- Read residual decision log first:
  - `decision-logs/2026-05-04-task-78-chapter6-residual-needs-fix.md`
- Resume summary:
  - `py -3 scripts/python/dev_cli.py resume-task --task-id 78 --recommendation-only --recommendation-format json`
- Route summary:
  - `py -3 scripts/python/dev_cli.py chapter6-route --task-id 78 --recommendation-only --recommendation-format json`

## Planned Fix Scope
- Align T78 acceptance semantics with test evidence for:
  - preview readability assertions
  - independent presentation feedback observability assertions
  - reduced-motion/headless-safe observability path
  - SFX hook and missing-audio no-op assertions

## Verification Commands
1. `py -3 scripts/sc/build.py tdd --task-id 78 --stage refactor --delivery-profile fast-ship --security-profile host-safe`
2. `py -3 scripts/sc/run_review_pipeline.py --task-id 78 --resume`
3. If approval sidecar appears again, follow approval state machine strictly.

## Stop-Loss Rule
- If recovery returns `recent_failure_summary` again with no new reviewer movement, do not reopen full reruns; update residual records with new evidence only.
