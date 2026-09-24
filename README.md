# newrouge (Godot 4.5.1 + C#)

`newrouge` is a Windows-only single-player game project built with Godot 4.5.1 and C# (.NET 8).

## Project Posture

- Delivery profile: `fast-ship`
- Security profile: `host-safe`
- Primary runtime: Windows desktop only
- Primary PRD-ID: `PRD-NEWROUGE-GAME-0001`

## Quick Links

- Workflow and chapter order: `workflow.md`
- Task-scoped routing: `AGENTS.md`
- Agents index: `docs/agents/00-index.md`
- Session recovery: `docs/agents/01-session-recovery.md`
- Project docs index: `docs/PROJECT_DOCUMENTATION_INDEX.md`
- Repository knowledge routing: `docs/agents/13-rag-sources-and-session-ssot.md`
- Knowledge Control Plane: `knowledge/README.md`
- Project health dashboard: `docs/workflows/project-health-dashboard.md`
- Stable public entrypoints: `docs/workflows/stable-public-entrypoints.md`
- Script entrypoints index: `docs/workflows/script-entrypoints-index.md`
- Prototype lane: `docs/workflows/prototype-lane.md`
- Prototype lane playbook: `docs/workflows/prototype-lane-playbook.md`
- Prototype TDD guide: `docs/workflows/prototype-tdd.md`
- Chapter 7 UI Wiring GDD: `docs/gdd/ui-gdd-flow.md`
- Chapter 7 Profile: `docs/workflows/chapter7-profile.json`
- Chapter 7 Profile Guide: `docs/workflows/chapter7-profile-guide.md`

## Quick Start (Windows)

1. Install Godot .NET 4.5.1 and .NET 8 SDK.
2. Set Godot binary path in shell:
   - PowerShell: `$env:GODOT_BIN = "C:\Godot\Godot_v4.5.1-stable_mono_win64.exe"`
3. Restore and build:
   - `dotnet restore NewRouge.sln`
   - `dotnet build NewRouge.sln -c Debug`
4. Optional local hard checks:
   - `py -3 scripts/python/dev_cli.py run-local-hard-checks --godot-bin "$env:GODOT_BIN"`

## Recovery First

When resuming a task after a reset or another session, do not guess from scattered logs first.

1. Read `AGENTS.md` and select the route for the current task.
2. Run `py -3 scripts/python/dev_cli.py resume-task --task-id <task-id> --recommendation-only`.
3. For Chapter 6 continuation, run `py -3 scripts/python/dev_cli.py chapter6-route --task-id <task-id> --recommendation-only`.
4. Only if the compact recommendation is insufficient, expand the selected run with `inspect-run --kind pipeline --task-id <task-id>` and the directly referenced authority/evidence. See `docs/agents/01-session-recovery.md`.

Before paying for another full `6.7`, read these signals first:

- `Latest reason`
- `Latest run type`
- `Latest reuse mode`
- `Latest artifact integrity`
- `Chapter6 blocked by`
- `Chapter6 stop-loss note`
- `recommended_action_why`
- `chapter6_route_lane` / `repo_noise_reason` from project-health or active-task when available

Recovery stop-loss rules:

- `run_type = planned-only` or `reason = planned_only_incomplete`: treat the bundle as evidence only; do not reopen `6.7` or `6.8` from it
- `Chapter6 blocked by = artifact_integrity`: fall back to the previous real producer bundle before any rerun choice
- `rerun_guard`: deterministic cost should not be paid again blindly
- `llm_retry_stop_loss`: prefer narrow LLM-only closure, not another full rerun
- `sc_test_retry_stop_loss`: same-run unit retry already proved wasteful; fix unit root cause first
- `waste_signals`: engine-lane cost was already wasted after a known unit/root-cause failure
- `recommended_action = needs-fix-fast`: deterministic evidence is already good enough and you should close targeted anchors instead of paying for another full rerun.

## Core Repositories and Files

- Taskmaster triplet:
  - `.taskmaster/tasks/tasks.json`
  - `.taskmaster/tasks/tasks_back.json`
  - `.taskmaster/tasks/tasks_gameplay.json`
- PRD input:
  - `.taskmaster/docs/prd.txt`
  - `docs/prd/**`
- Architecture:
  - `docs/architecture/base/**`
  - `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/**`
- ADR index:
  - `docs/architecture/ADR_INDEX_GODOT.md`
- Repository knowledge control plane:
  - `knowledge/README.md`
  - `docs/agents/13-rag-sources-and-session-ssot.md`
  - `.agents/skills/maintain-knowledge-base/SKILL.md`

## Commands

- Repository bootstrap/maintenance hard checks (may refresh Project Health):
  - `py -3 scripts/python/dev_cli.py run-local-hard-checks --godot-bin "<godot-bin>"`
  - `py -3 scripts/python/dev_cli.py run-local-hard-checks --godot-bin "$env:GODOT_BIN"`
- Knowledge Control Plane:
  - `py -3 scripts/python/build_knowledge_catalog.py`
  - `py -3 scripts/python/publish_knowledge_catalog.py --publish`
  - `py -3 scripts/python/publish_knowledge_catalog.py --check`
  - `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated`
  - Shadow/freeze behavior: `docs/workflows/knowledge-context-shadow.md`, `docs/workflows/knowledge-context-freeze.md`
- Chapter 6 pre-commit hard checks (no global Knowledge/Project Health refresh):
  - `py -3 scripts/python/dev_cli.py run-local-hard-checks --skip-project-health --godot-bin "<godot-bin>"`
- Task recovery (compact first):
  - `py -3 scripts/python/dev_cli.py resume-task --task-id <task-id> --recommendation-only`
  - `py -3 scripts/python/dev_cli.py inspect-run --kind pipeline --task-id <task-id>`
  - `py -3 scripts/python/dev_cli.py chapter6-route --task-id <task-id> --recommendation-only`
- Gate bundle only:
  - `py -3 scripts/python/run_gate_bundle.py --mode hard --task-files .taskmaster/tasks/tasks_back.json .taskmaster/tasks/tasks_gameplay.json`
- Chapter 3 task triplet baseline:
  - interactive run start: `py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter3 --trigger-run-id <run-id> --begin-run`
  - scripted top-level guard: `py -3 scripts/python/dev_cli.py run-chapter3-guarded --trigger-run-id <run-id> --triplet-status-on-success <passed|blocked|unknown> -- <command...>`
  - `py -3 scripts/python/build_source_ledger.py --mode <init|add> --prd-path <path> --gdd-path <path> --epics-path <path> --stories-path <path>`
  - `py -3 scripts/python/project_semantics_from_sources.py prepare --max-blocks-per-batch 40 --max-chars-per-batch 24000` → approved Chapter 3 model/Skill explicitly reviews every batch/block
  - `py -3 scripts/python/project_semantics_from_sources.py compile && py -3 scripts/python/validate_semantic_conservation.py --stage projection`
  - `py -3 scripts/python/normalize_task_intents.py --mode <init|add> && py -3 scripts/python/generate_task_candidates_from_sources.py --mode <init|add> && py -3 scripts/python/enrich_task_candidates.py`
  - `py -3 scripts/python/audit_task_candidate_coverage.py && py -3 scripts/python/validate_semantic_conservation.py --stage closure`
  - `py -3 scripts/python/compile_task_triplet.py --mode <init|add>`
  - after triplet rebuild + semantic tier backfill: `py -3 scripts/python/attest_chapter3_triplet_baseline.py`
  - run end: `py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter3 --trigger-run-id <run-id> --refresh-local --triplet-status <passed|blocked|unknown>`
- Chapter 4 overlays and contracts:
  - `py -3 scripts/python/sync_task_overlay_refs.py --prd-id <PRD-ID> --write`
  - `py -3 scripts/python/validate_overlay_execution.py --prd-id <PRD-ID> --strict-refs`
- Chapter 5 semantic reconciliation and readiness:
  - interactive run start: `py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter5 --trigger-run-id <run-id> --begin-run`
  - scripted lifecycle guard: `py -3 scripts/python/dev_cli.py run-chapter5-guarded --trigger-run-id <run-id> -- <command...>`
  - Follow `workflow.md` 5.0: independent Extraction B (`prepare` → explicit review of every source block → `compile`), global audit, task reconciliation, then `check-readiness`.
  - Fresh readiness is required before Chapter 6; a task-local light lane does not replace this gate. Reconcile again after any task/authority correction, then finish the run with the bound reconciliation/readiness refresh.
  - `py -3 scripts/python/backfill_semantic_review_tier.py --mode conservative --write`
  - `py -3 scripts/python/validate_semantic_review_tier.py --mode conservative`
  - `py -3 scripts/python/preflight_acceptance_extract_guard.py --task-id <task-id>`
  - `py -3 scripts/python/run_single_task_light_lane.py --task-id <task-id> --godot-bin <godot-bin>`
- Chapter 7 UI wiring closure:
  - `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile <profile> --self-check`
  - `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile <profile> --write-doc --create-tasks`
  - `py -3 scripts/python/dev_cli.py run-chapter7-backlog-gap --design-doc-path <doc> --epics-doc-path <doc> --duplicate-audit-path <doc>`
- Chapter 6 daily loop (top-level entry):
  - `py -3 scripts/python/dev_cli.py run-single-task-chapter6 --task-id <task-id> --godot-bin "<godot-bin>" --delivery-profile fast-ship`
- Chapter 6.7 task review pipeline:
  - `py -3 scripts/sc/run_review_pipeline.py --task-id <task-id> --godot-bin "<godot-bin>"`
  - `py -3 scripts/sc/run_review_pipeline.py --task-id <task-id> --godot-bin "$env:GODOT_BIN"`
- Prototype lane:
  - `py -3 scripts/python/dev_cli.py run-prototype-tdd --slug <slug> --stage red --dotnet-target Game.Core.Tests/Game.Core.Tests.csproj --filter <Expr>`
  - `py -3 scripts/python/dev_cli.py run-prototype-tdd --slug <slug> --create-record-only --hypothesis "<what are you proving>"`

## Engineering Rules

- Contracts SSoT: `Game.Core/Contracts/**`
- Contract code stays BCL-only, no `Godot.*` references.
- Domain logic in `Game.Core/**`; engine integration in `Game.Godot/**`.
- Logs and evidence go to `logs/**`.
- Keep docs and tasks aligned through ADR + Base + Overlay + Task refs.
- Repository Knowledge Control Plane is derived routing infrastructure; source documents remain authoritative.

## Chapter Workflow, MVG and Knowledge

Users continue to select a Chapter Skill and supply the relevant sources or task ID. The chapter order remains 3 → 4 → 5 → 6 → 7. Chapter 3 now conserves source semantics before task generation; Chapter 5 establishes current readiness before implementation; Chapter 6 routes and reuses evidence internally. Blocked/stale readiness requires returning to Chapter 5, and a new formal task from Chapter 7 follows the same readiness/development loop.

- [MVG integration acceptance](docs/workflows/mvg-integration-acceptance.md): tests belong to existing tasks/handoff owners and are implemented during Chapter 6. The separate `run-mvg-acceptance` runner/CI verifies their combination on one snapshot. Default `m1-critical` is not full M1 acceptance; `m1-full` remains blocked while Task 59/60 are pending.
- [Knowledge and topology](docs/workflows/project-health-knowledge.md): the UI shows Source → Requirement → optional Capability → Task → Acceptance and Chapter 3/5 workspace attempts. It has no dedicated MVG manifest/flow/handoff/result view. Task verification buttons do not substitute for MVG acceptance.\n

### Incremental milestones

Later GDD milestones reuse the existing Chapter 3→6 and MVG lifecycle. The cumulative source declaration is `docs/workflows/chapter3-source-set.json` and stable intent IDs are recorded in `docs/workflows/chapter3-intent-ids.json`. Review the task triplet preview before `--write`. Reviewed task/change handoffs use `scripts/python/milestone_incremental_handoff.py`; Chapter 6 consumes passed current-revision MVG evidence for declared regressions via `--milestone-regression-summary` on a clean current worktree. Task export preserves existing master lifecycle state, and declared source retirements remain effective across runs. Cumulative integration manifests are evolved with `scripts/python/update_mvg_baseline.py`. See `workflow.md` and `docs/workflows/mvg-integration-acceptance.md`.
