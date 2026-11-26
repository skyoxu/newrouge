---
name: workflow-chapter7-ui-wiring-closure
description: Run the fixed Chapter 7 UI wiring closure workflow from workflow.md. Use when a business repo needs UI/GDD closure after Chapter 6, chapter7 profile overrides, UI wiring GDD generation, candidate sidecars, artifact manifests, hard gates, task generation, or idempotent Chapter 7 readiness checks.
---

# Workflow Chapter 7 UI Wiring Closure

## Role

Operate Chapter 7 from `workflow.md` idempotently for a business repository that is a sibling of the template repository.

## Operating Contract

- Treat `workflow.md` as the normative workflow source.
- Treat business-repo logs as empirical evidence, not policy overrides.
- Use Python with UTF-8 for documentation reads and writes.
- Keep generated code, scripts, tests, comments, and log messages in English.
- Do not modify the business repo unless the user explicitly asks for that change.
- Do not rerun expensive steps before reading existing recovery artifacts.

## Repository Layout

Template and business repositories are siblings under one parent directory, for example `<parent>/godotgame`, `<parent>/<business-repo-a>`, and `<parent>/<business-repo-b>`.

## Purpose

Use this skill to convert completed domain and gameplay capabilities into player-facing UI wiring and governed Chapter 7 artifacts.

## Default Lane

Start with self-check, then write-doc, then create-tasks only after the candidate sidecar and artifact manifest are valid.

## Primary Command Or Action

- Legacy / full-repo self-check: `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile <profile> --self-check`
- B-route target-slice read-only UI closure (zero-write default, no whole-game wait, no global Knowledge refresh): `py -3 -B scripts/python/dev_cli.py b-route-chapter7-slice [--flow-id <flow-id>] [--slice <bucket>] [--task-id <id>] [--root <root>] [--profile <json>] [--evidence-dir <dir>] [--ui-evidence <json>] [--gap-input <json>] [--operation <op>] [--report <logs/ci/.../*.json>]`
- Target-slice Chapter 7 orchestrator / backlog-gap options: pass `--slice <bucket>` (repeatable) and/or `--flow-id <flow-id>` (plus `--chapter7-profile-path <path>` and `--ui-evidence <json>` on `run-chapter7-backlog-gap`) to `dev_cli.py run-chapter7-ui-wiring` and `dev_cli.py run-chapter7-backlog-gap` (on active B-route repos, `--create-tasks` emits a read-only Story 3.1/3.2 governed delta candidate with `operations` instead of writing `.taskmaster/tasks/*.json`, and `dev_cli.py apply-chapter7-status-patch --patch <path> [--repo-root <root>]` preserves mature `done` status across all triplet views). See `docs/workflows/b-route-chapter7-slice.md`.

## Evidence Rule

Chapter 7 currently has little or no business-repo runtime history. Use workflow.md, chapter7-profile.json, the profile guide, and generated manifests as the stable source until real logs exist.

## Required Reading

1. Read the relevant Chapter 7 section in the template repo `workflow.md`.
2. Optionally read `references/business-repos/<repo>.md` only as empirical validation evidence when the target business repo has a generated reference.
3. If that optional evidence file is missing or stale, run `py -3 scripts/python/update_workflow_chapter_skills.py <repo>` from the template repo.

## Idempotent Procedure

1. Confirm Chapter 6 has no unrecorded P0/P1 Needs Fix.
2. Confirm real task triplet files exist before treating the Chapter 7 gate as complete.
3. Use a Chapter 7 profile override for policy-level business repo differences instead of forking scripts.
4. Run self-check before write-doc.
5. Validate UI GDD, candidates, artifact manifest, and hard gate outputs before task creation.
6. Stop when backlog-gap evidence says candidate tasks are already covered.

## Stop-Loss Signals

- Existing `forbidden_commands` blocks the command about to be run.
- `artifact_integrity`, `planned_only_incomplete`, or planned-only run type appears in recovery evidence.
- Route evidence recommends inspect-first, record-residual, fix-deterministic, repo-noise-stop, or pause.
- The same deterministic failure fingerprint appears repeatedly.
- The next action would duplicate work already covered by task, overlay, candidate, or manifest evidence.

## Business Evidence References

Generated evidence may live under `references/business-repos/<repo>.md`. These files are optional regression evidence from known business repositories; they must not define production generation rules.

## Maintenance

Refresh optional evidence after new business-repo logs are generated:

```powershell
py -3 scripts/python/update_workflow_chapter_skills.py <business-repo>
py -3 scripts/python/update_workflow_chapter_skills.py <business-repo-a>,<business-repo-b>
```

## Explicit B-route verification, defect routing, and completion boundaries (existing A lane remains default until Epic 5)

- Chapter 7 target-slice closure (`py -3 -B scripts/python/dev_cli.py b-route-chapter7-slice`, `docs/workflows/b-route-chapter7-slice.md`) shares the live Chapter 6 gate (`py -3 -B scripts/python/dev_cli.py b-route-chapter6-gate`, `docs/workflows/b-route-chapter6-gate.md`), recovery boundary (`docs/workflows/b-route-chapter6-recovery.md`), and defect return-stage routing (`py -3 -B scripts/python/dev_cli.py b-route-defect-routing`, `docs/workflows/b-route-defect-routing.md`). Durable journal recovery remains strictly distinct from model resume, and Stage 3A/3B/3C planning remains distinct from Chapter 4–7 implementation/UI closure.
- End-to-end UI and Flow verification consumes sealed `VerificationScope` (`py -3 -B scripts/python/dev_cli.py b-route-verification-scope`, `docs/workflows/b-route-verification-scope.md`) via `py -3 -B scripts/python/dev_cli.py run-mvg-acceptance --verification-scope <scope.json>` (`docs/workflows/b-route-scope-runner.md`, `docs/workflows/b-route-evidence-reuse.md`) and evaluates Task-local vs target-Flow vs cumulative `full-MVG` milestone completion separately via `py -3 -B scripts/python/dev_cli.py b-route-completion-verdict` (`docs/workflows/b-route-completion-verdict.md`). Chapter 7 slice closure never triggers global Knowledge refresh, never publishes `workspace_preview`/`workspace` state to `knowledge/indexes/current.json`, `last-known-good.json`, or `refs/heads/main`, and keeps `runtime_verified=false` and `default_b_enabled=false`.
