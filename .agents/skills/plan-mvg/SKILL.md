---
name: plan-mvg
description: Plan an initial or cumulative MVG integration manifest from one explicitly selected Capability version plus authoritative GDD/Requirement/task/Acceptance/contract/test evidence. Use after Capability application and the required Chapter 5 readiness checks; never invokes Capability generation.
---

# Plan MVG

## Role

Design cumulative player-journey integration coverage after Capability planning. This Skill is independently callable and consumes one explicit Capability file/version. It does not run or modify `plan-capabilities`.

## Boundaries

- GDD and reviewed Requirements remain semantic authority; Capability is a derived navigation index.
- Require an explicit Capability path and explicit target manifest path. Never select “latest” implicitly.
- A flow may span many Capabilities; a Capability may participate in many flows. Do not mechanically create one flow per Capability.
- Real task IDs, owners, contracts and existing tests must be verified from repository inputs. Missing objects become gaps; never invent them.
- Planned entrypoints may target not-yet-created implementation paths only when a real owner task, target symbol/path, inputs/state/assertions and implementation acceptance are explicit.
- Existing verified entrypoints must point to files that exist now.
- `implemented` means a test implementation exists. This Skill never writes `passed` or `runtime_verified`.
- `coverage.blocking_task_ids` comes from the prepared Taskmaster master table, including the existing dedicated integration-owner exclusion. Planned entrypoints/tests and absent runtime evidence never change task status or invent task blockers. Dotnet selectors are class names, not filter expressions.
- Reserve `gaps` for unresolved upstream semantics, real owners, Acceptance or required real contracts. Valid planned entrypoints/tests and absent runtime evidence are implementation/manual obligations, not upstream gaps. Preserve them as planned and document their boundary; never disguise a genuine gap to approve a plan.
- Existing cumulative flows/tests remain unless a reviewed specification explicitly authorizes update/retire/coverage weakening. The same guarded `update_mvg_baseline.py` contract is used for apply.

## Primary workflow

1. Prepare the exact input identity:
   `py -3 scripts/python/plan_mvg.py prepare --run-id <id> --capabilities docs/planning/semantic-topology/capabilities.v1.json --manifest docs/testing/mvg/<manifest>.json --task-id <id> [...]`
2. Include every actual task sink of the current source round. Prepare derives the round from added/changed ledger sources (all sources for a cumulative re-plan with no delta), checks active delivery Requirements and legitimate non-task sinks, and requires current Chapter 5 evidence. An omitted task blocks even when every supplied task is ready. `--allow-unready-draft` is for gap inspection only.
   Prepare copies existing baseline flow/contract/test dependencies and task refs. Add any other existing implementation, test, verification or reviewed authority with repeated `--evidence-ref <repo-file>`. Every claimed existing dependency must be readable in this fixed bundle and remain unchanged through apply. If a new dependency was omitted, prepare a new run with that explicit ref; never bind fresh evidence after review. Not-yet-created planned paths remain implementation obligations.
3. Generate the proposal:
   `py -3 scripts/python/plan_mvg.py generate --run-id <id> --llm-backend codex-cli`
4. Run a new isolated semantic reviewer against the fixed proposal and full prepared inputs:
   `py -3 scripts/python/plan_mvg.py review --run-id <id> --runner scripts/python/openai_isolated_model_runner.py`
   Use `copilot_isolated_model_runner.py` when that is the configured backend. Never substitute the generating session's self-review. A blocked review preserves the proposal; repair the specific stage and review again.
5. Deterministically validate complete Requirement-to-flow/other-verification/reviewed-deferral accounting, every flow task's entrypoint, real task/Capability membership, and the original initial manifest or cumulative delta:
   `py -3 scripts/python/plan_mvg.py validate --run-id <id>`
6. Apply only after independent review and validation. Source, task master/views, Acceptance, referenced contracts/tests/ADRs, Chapter 5 evidence and original manifest identities must still match prepare:
   `py -3 scripts/python/plan_mvg.py apply --run-id <id> --confirm`
7. Resolve final obligation bindings before Chapter 6. Keep current milestone change plans under `docs/planning/milestones/`. For each actual milestone owner, rebuild the existing Chapter 5→6 handoff against current readiness and the applied MVG manifest:
   `py -3 scripts/python/plan_mvg.py rebind-handoff --run-id <id> --task-id <task> --change-plan <reviewed-plan.json> --out <handoff.json>`
   For an ordinary task, verify applicability and bind its current Chapter 5 readiness without creating a milestone handoff:
   `py -3 scripts/python/plan_mvg.py rebind-handoff --run-id <id> --task-id <task>`
   This ordinary route fails closed if an applicable milestone plan exists.

For an existing manifest, the Skill computes a reviewed delta and passes it through `update_mvg_baseline.py` logic; it does not overwrite the old baseline directly. For a first manifest, it validates the same runner schema before creation.

## Evidence and handoff

The durable run is under `logs/ci/mvg-planning/<run-id>/`. The applied trace sidecar is under `docs/testing/mvg/planning/<run-id>.json`; it is planning provenance, not another runtime-test state authority.

The applied trace records per-task obligation bindings and is consumed by both `chapter6-route` and the single-task lane. Omitting `--milestone-handoff` cannot bypass pending obligations. A milestone handoff itself binds the baseline manifest hash; later manifest/readiness/plan changes invalidate the binding. Ordinary bindings use current Chapter 5 readiness and create no synthetic milestone handoff. Planning and rebind keep `runtime_verified=false`; runtime evidence belongs to the MVG runner/Chapter 6 acceptance path.

Use the MVG runner's newline-normalized content hash for committed manifests, milestone plans and milestone handoffs. Git LF/CRLF conversion preserves those bindings; content edits invalidate them. Keep prepared authority snapshots, readiness and interrupted-apply journal checks byte-exact.

## Refresh rules

Task status or small reference edits do not automatically regenerate Capability or MVG planning. A new code revision invalidates runtime evidence when appropriate, not the planning manifest by itself. Capability rename/regrouping triggers MVG reference/behavior impact review, not automatic wholesale flow regeneration.

Never prepare over an existing run ID: resume its incomplete stage, or choose a new ID for changed source inputs. Deltas are computed against the prepared manifest copy, never silently rebased onto a later manifest.

Apply also journals the approved trace and manifest together. Re-running the same apply recovers interruption and preserves subsequent legitimate obligation bindings. Independent review execution has at most three persisted fresh invocations per run; transport/identity/JSON failures may retry, but an actual blocked semantic verdict stops without seeking another approving reviewer. Re-running an already valid review reuses its evidence.

Each fixed proposal has a hash-bound `semantic-review-publication-<proposal-sha256>.json` checkpoint containing its verdict and execution receipt. Re-run review to finish interrupted publication without another invocation. Unknown target edits or corrupt checkpoints block recovery. Completed records preserve earlier blocked verdicts when a repaired proposal is reviewed within the same three-attempt limit. Finish any pending publication against its original proposal before revision. Drafts and invalid semantic accounting never gain formal approval by replaying publication.

Generation execution also has three persisted fresh attempts. Identity/transport failures do not consume downstream review or regenerate Capability, and re-invoking the stage cannot reset that budget. Preserve a valid generated proposal and resume review/validation/apply only.
