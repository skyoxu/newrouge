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
- Generate journeys from the explicitly selected Capability version, then identify observable cross-Capability/system boundaries. Task IDs supply ownership, Acceptance, contract and test evidence only; Task enumeration must not create runtime API obligations. Test/governance Tasks remain evidence-only even when referenced by legacy handoffs. Data-only contracts are not executable entrypoints.
- Preserve source-named sending/receiving systems and map their real task owners, including shared ownership. Assert the same interaction in flows, entrypoints and planned tests; task labels alone do not establish a system boundary.
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
   When `--manifest` points to an existing manifest, its coverage scope is frozen at prepare: required flow IDs, Requirements, Tasks, tests, source paths and contract refs are the cumulative target. A pilot manifest does not expand into full-project coverage; out-of-scope model output is rejected deterministically.
   Prepare copies existing baseline flow/contract/test dependencies and task refs. It also writes immutable `coverage-skeleton.json` and an intentionally empty `entrypoint-skeleton.json`; the coverage skeleton contains every active delivery Requirement and is non-droppable, while entrypoints are later derived from Capability flow boundaries rather than Task placeholders. Add any other existing implementation, test, verification or reviewed authority with repeated `--evidence-ref <repo-file>`. Every claimed existing dependency must be readable in this fixed bundle and remain unchanged through apply. If a new dependency was omitted, prepare a new run with that explicit ref; never bind fresh evidence after review. Not-yet-created planned paths remain implementation obligations.
3. Generate three independent proposals and evaluate them:
   `py -3 scripts/python/plan_mvg.py generate --run-id <id> --llm-backend codex-cli`
   The exact `capabilities.v1.json` supplied to `prepare` is the sole Capability SSoT. GDD, task views, contracts, tests and an existing MVG manifest are auxiliary evidence and cannot create or reassign Capability membership. Generation creates `candidate-1`, `candidate-2`, and `candidate-3`; each candidate has its own prepared bundle, workspace and fresh isolated model context. Bounded sections (flows, coverage, entrypoints and tests) are merged only inside that candidate. Each candidate gets one fresh generation invocation; a malformed or deterministically invalid candidate is rejected rather than repaired by copying another candidate. Runner-level output-schema enforcement and local identity/routing/reference/full-proposal validators remain mandatory.
   A separate isolated selection reviewer evaluates anonymous A/B/C candidates. When a valid current MVG manifest exists, it is projected as incumbent D and evaluated alongside A/B/C; D may be retained. The reviewer must return a complete comparative report with tradeoffs, rationale and evidence references, and the selected label must be marked `viable`. Selection rows carry a unique stable rank in ascending order; rank 1 is the selected winner and is the only bounded fallback ordering used after a semantic block. The selected proposal is written to `proposal.json`; candidate and selection evidence remain under the durable run directory.
   Segment routing is enforced before model output is merged: a frozen flow request and its handoffs use that flow's incumbent test IDs, and its test request uses the same exact flow/test domain in the CLI output schema, inline prompt and local routing validator. The global manifest ID set is an accounting boundary, not a segment's permitted output domain. An empty frozen test domain permits no test rows. For a new manifest, generated flow/test IDs are prefix-constrained and tests may reference only the actual flows from their routed scope. These rules apply to fresh responses and reused segments; prompt instructions do not substitute for CLI enforcement.
   Coverage segment `authority_ref` and `verification_ref` fields are limited to immutable prepared source/reference paths (optionally with anchors) by the CLI schema and the segment reference gate. A Requirement ID is not a file reference. Invalid coverage references trigger bounded section correction before candidate merge; deferred coverage still requires reviewed authority and independent semantic approval.
4. Run a new isolated semantic reviewer against the selected proposal and a bounded projection of the immutable prepared inputs:
   `py -3 scripts/python/plan_mvg.py review --run-id <id> --runner scripts/python/openai_isolated_model_runner.py`
   Use `copilot_isolated_model_runner.py` when that is the configured backend. Never substitute the generating session's self-review. The projection retains source context and hash-bound excerpts of referenced evidence; it is not a full code review or runtime proof. Deterministic validation continues to use the complete prepared bundle. A blocked review preserves the proposal; resolve findings in a revised proposal before reviewing again, rather than repeating review on an unchanged blocked proposal.
5. Deterministically validate complete Requirement-to-flow/other-verification/reviewed-deferral accounting, real task/Capability membership and executable boundary evidence for each handoff flow, and the original initial manifest or cumulative delta. Do not require one entrypoint per Task. The entrypoint skeleton is intentionally empty; entrypoint requests are routed by Capability journeys with handoffs/source paths, and the independent reviewer checks actual runtime boundary completeness:
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

Apply also journals the approved trace and manifest together. Re-running the same apply recovers interruption and preserves subsequent legitimate obligation bindings. Independent review execution has at most ten persisted fresh invocations per run. Transport, identity, and JSON/runner failures may retry and persist an `error_type`; an actual blocked semantic verdict permits at most one fresh review of the next ranked viable candidate, while preserving the original blocked review and never re-reviewing that unchanged proposal. Re-running an already valid review reuses its evidence. Review inputs are supplied through the bounded review workspace/evidence projection so transport limits do not turn an oversized input bundle into a semantic verdict; referenced evidence excerpts retain a larger head/tail window and file hashes, while the complete immutable prepared bundle remains the deterministic validation authority. The projection runs deterministic preflight before the first model call and adaptively shrinks excerpts when needed; input-size or preparation failures create no Review attempt and do not consume the ten-attempt budget. Resuming an older run backfills missing `error_type` values from its persisted error text without changing the historical verdict.

Each fixed proposal has a hash-bound `semantic-review-publication-<proposal-sha256>.json` checkpoint containing its verdict and execution receipt. Re-run review to finish interrupted publication without another invocation. Before that checkpoint exists, require the completed attempt's original output hash, runner/analysis identities and receipt to match before reuse. Unknown target edits or corrupt checkpoints block recovery. Completed records preserve earlier blocked verdicts when a repaired proposal is reviewed within the same ten-attempt limit. Finish any pending publication against its original proposal before revision. Drafts and invalid semantic accounting never gain formal approval by replaying publication.

Generation execution now has three persisted fresh candidate contexts, not three retries of one proposal. A candidate's sections run in its own ephemeral workspace using the selected backend's environment-default model configuration; Windows timeout cleanup terminates the complete child process tree. Selection has a bounded three-attempt transport/schema budget and never merges candidates. The independent semantic Review remains a separate ten-attempt budget. Identity/transport failures do not consume downstream review or regenerate Capability. Preserve valid candidate/selection evidence and resume review/validation/apply only.
