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
- Existing cumulative flows/tests remain unless a reviewed specification explicitly authorizes update/retire/coverage weakening. The same guarded `update_mvg_baseline.py` contract is used for apply.

## Primary workflow

1. Prepare the exact input identity:
   `py -3 scripts/python/plan_mvg.py prepare --run-id <id> --capabilities docs/planning/semantic-topology/capabilities.v1.json --manifest docs/testing/mvg/<manifest>.json --task-id <id> [...]`
2. If the explicit task scope is not currently Chapter-5-ready, formal prepare blocks. `--allow-unready-draft` may be used only to inspect gaps.
3. Generate the proposal:
   `py -3 scripts/python/plan_mvg.py generate --run-id <id> --llm-backend codex-cli`
4. Deterministically validate real tasks/contracts/tests, Requirement/Capability refs, entrypoint truthfulness, and the actual initial manifest or cumulative delta:
   `py -3 scripts/python/plan_mvg.py validate --run-id <id>`
5. Apply only after validation:
   `py -3 scripts/python/plan_mvg.py apply --run-id <id> --confirm`

For an existing manifest, the Skill computes a reviewed delta and passes it through `update_mvg_baseline.py` logic; it does not overwrite the old baseline directly. For a first manifest, it validates the same runner schema before creation.

## Evidence and handoff

The durable run is under `logs/ci/mvg-planning/<run-id>/`. The applied trace sidecar is under `docs/testing/mvg/planning/<run-id>.json`; it is planning provenance, not another runtime-test state authority.

After apply, always inspect current Chapter 5 readiness for involved tasks and rebuild the applicable milestone handoff when obligations/owner/contracts changed. The apply summary intentionally reports `runtime_verified=false` and `handoff_rebind_required=true`. Chapter 6 must not consume the new obligations until that final handoff binding is valid.

## Refresh rules

Task status or small reference edits do not automatically regenerate Capability or MVG planning. A new code revision invalidates runtime evidence when appropriate, not the planning manifest by itself. Capability rename/regrouping triggers MVG reference/behavior impact review, not automatic wholesale flow regeneration.
