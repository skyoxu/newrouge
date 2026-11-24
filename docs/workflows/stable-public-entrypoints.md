# Stable Public Entrypoints

This document lists the stable, recommended script entrypoints for day-to-day use.
Use it when you need to decide which command to run next.
Use `docs/workflows/script-entrypoints-index.md` when you need the full executable inventory, direct deps, transitive deps, or full argument scan.

## Selection Rules

- Prefer these entrypoints before reaching for lower-level helper scripts.
- If a script is not listed here, it is usually one of these:
  - a lower-level building block already wrapped by a stable entrypoint
  - a rare audit / migration / maintenance command
  - a one-off repair or template sync tool
- Do not manually stitch `scripts/sc/test.py + scripts/sc/acceptance_check.py + scripts/sc/llm_review.py` when `scripts/sc/run_review_pipeline.py` already covers the same task path.

## B Route Governance (Accepted; Not Enabled)

[ADR-0040: B route stages, authority and activation](../adr/ADR-0040-b-route-stages-authority-and-activation.md) is Accepted following independent source review under the user’s explicit delegation after the full proposal was presented. Governance adoption, implementation delivery and migration activation have separate admission conditions. 现有 A 入口保持有效；显式 B 的来源、原生规划、审计和 operation 阶段见
[原生规划导航](b-route-native-planning-status.md)，不由此切换默认路线。

The target order is 3A source audit, 3B formal adoption without Task/readiness/real scenes, 3C Task handoff, 4–5 binding/readiness, 6 one Task, applicable 7, then Flow/cumulative closeout. These are responsibilities, not three new commands. Default B waits for later consumers, recovery counterexamples and real reward evidence from both paths. A freeze, final A exit and reviewed compensation each follow the ADR conditions; this navigation does not activate them.

## Explicit B-route planning context (implemented slice; not enabled by default)

`py -3 scripts/python/dev_cli.py b-route-adoption --stage inspect --operation-id <original-id> --context`
reads the original retained operation. Use `--stage read --context` for the
validated published operation's plan/binding/revision references; its original
reader retains coordination metadata writes. See [adoption owner](b-route-adoption.md)
and [retained native status](b-route-native-planning-status.md) for exact boundaries.
The native status route still validates the original run and can recover a
checkpoint; it is not a substitute read-only formal reader. No new Task, latest
context selector, model invocation or 2.9 reuse API is supplied by these views.
Original A entrypoints remain below. Default B and full Story 2.10 remain unaccepted.

## Repo Bootstrap And Recovery

### `py -3 scripts/python/dev_cli.py run-prototype-workflow --prototype-file docs/prototypes/<your-file>.md`

Use when:
- you want a Day 1 -> Day 5 prototype lane router instead of manually chaining prototype commands
- the prototype record already follows `docs/prototypes/TEMPLATE.md` or `docs/prototypes/TEMPLATE.zh-CN.md`
- you want explicit confirmation pauses before execution continues

Prerequisites:
- a prototype file path, or enough `--set key=value` inputs to satisfy required fields
- `--godot-bin` only becomes required before Day 5 Godot-side verification

Why this is stable:
- it is the top-level prototype lane router
- it pauses for missing required fields instead of guessing through them
- it writes lightweight active state under `logs/ci/active-prototypes/*.active.json` for resume after context compression
- it stops at Day 5 and leaves Day 6 / Day 7 evidence review and discard/archive/promote judgment to the operator


### `py -3 scripts/python/dev_cli.py run-local-hard-checks`

Use when:
- first full validation after copying the template into a new repo
- before commit or before PR when you want the repo-level hard path
- reproducing the local order before debugging CI

Prerequisites:
- `py -3`
- `.NET 8 SDK`
- optional `--godot-bin` for GdUnit and strict smoke

Why this is stable:
- it is the repo-level hard-check entrypoint
- it writes sidecars and latest pointers
- bootstrap/maintenance use refreshes `project-health` before the hard chain; Chapter 6 must pass `--skip-project-health` to preserve the no-refresh boundary

### `py -3 scripts/python/dev_cli.py project-health-scan`

Use when:
- immediately after cloning or syncing template upgrades
- after renaming repo identity, paths, and project files
- when you want a deterministic repo-health snapshot before task work starts

Prerequisites:
- `py -3`

Why this is stable:
- it is the repo bootstrap stop-loss point
- it writes the canonical latest repo-health records

### `py -3 scripts/python/dev_cli.py serve-project-health`

Use when:
- you want a stable local browser URL for the project-health page
- you want the dashboard to stay open while rerunning repo-health commands

Prerequisites:
- local machine only; do not use in CI
- binds to `127.0.0.1`

Why this is stable:
- it is the recommended local serving entrypoint for `project-health`

### `py -3 scripts/python/dev_cli.py generate-image --prompt-file <file> --out <png>`

Use when:
- a repo-local skill or workflow needs one stable OpenAI-compatible image generation bridge
- you need `generate2dmap` or `generate2dsprite` to call the repository instead of a repo-specific wrapper
- you want a deterministic `--dry-run` manifest before spending image-generation cost

Prerequisites:
- `py -3`
- the OpenAI Python SDK available in the active Python environment for real image generation
- `AIARTMIRROR_API_KEY` set for real requests, with optional `AIARTMIRROR_BASE_URL`, `AIARTMIRROR_IMAGE_MODEL`, and `AIARTMIRROR_IMAGE_GROUP`

Why this is stable:
- it is the repo-level image-generation bridge used by installed asset skills
- it defaults to `gpt-image-2` and writes an explicit manifest contract for prompt, model, and output settings
- `--dry-run` validates skill-to-repo wiring without calling the remote image endpoint

### `py -3 scripts/python/dev_cli.py resume-task --task-id <id>`

Default recovery read (compact first): `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only`
Automation variant: `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only --recommendation-format json`
- Example compact JSON: `docs/workflows/examples/sc-resume-task-compact.example.json`
- Example compact stdout: `docs/workflows/examples/sc-resume-task-compact.stdout.example.txt`

Use when:
- resuming a task after context reset
- returning to a task after another session or another day
- you need the recommended recovery command set first, before deeper inspection

Prerequisites:
- task triplet available
- task-scoped sidecars exist if the task has already run through the pipeline

Why this is stable:
- it is the canonical task recovery entrypoint
- it consumes active-task sidecars, inspect output, and recovery docs
- it is the first place to read `reason`, `run_type`, `reuse_mode`, `artifact_integrity`, and `diagnostics` before deciding between `6.7` and `6.8`
- it now surfaces `Chapter6 next action`, `Chapter6 can skip 6.7`, `Chapter6 can go to 6.8`, and `Chapter6 blocked by`
- `Chapter6 blocked by` now explicitly distinguishes `rerun_guard`, `llm_retry_stop_loss`, `sc_test_retry_stop_loss`, `waste_signals`, `recent_failure_summary`, and `artifact_integrity`, so recovery can choose between full-stop, narrow llm-only follow-up, known-unit-root-cause stop, repeated-failure-family stop-loss, stale-bundle fallback, or root-cause-first repair
- it now also emits a `Chapter6 stop-loss note`, so the recovery summary explains why a fresh full `6.7` would be wasteful
- it now surfaces approval contract fields (`Approval required action`, `Approval status`, `Approval decision`, `Approval reason`) so recovery can distinguish `pause`, `fork`, `resume`, and inspect-first approval failures without reopening the whole pipeline
- it also surfaces `recommended_action_why`, and `recommended_action = needs-fix-fast` is the cue to prefer targeted closure over another full rerun

### `py -3 scripts/python/dev_cli.py inspect-run --kind <kind> [--task-id <id>]`

Default recovery read (compact first): `py -3 scripts/python/dev_cli.py inspect-run --kind <kind> [--task-id <id>] --recommendation-only`
Automation variant: `py -3 scripts/python/dev_cli.py inspect-run --kind <kind> [--task-id <id>] --recommendation-only --recommendation-format json`

Use when:
- `resume-task` is still not enough
- you need to inspect the latest pipeline or local-hard-checks sidecar set directly
- you are debugging run artifacts rather than continuing normal delivery

Prerequisites:
- existing sidecar outputs under `logs/ci/**`

Why this is stable:
- it is the canonical sidecar inspection entrypoint
- it now exposes `latest_summary_signals` and `chapter6_hints` in one place for rerun/stop-loss decisions
- `chapter6_hints.blocked_by` now covers `rerun_guard`, `llm_retry_stop_loss`, `sc_test_retry_stop_loss`, `waste_signals`, `recent_failure_summary`, and `artifact_integrity`
- inspection is also where you confirm `planned_only_incomplete` / `artifact_integrity`, repeated same-family failures via `recent_failure_summary`, approval contract states (`pending|approved|denied|invalid|mismatched`), and whether the next move should be inspect-first instead of reopening `6.7`
- when automatic latest resolution sees a newer dry-run-only pipeline pointer, it now skips that candidate and falls back to the newest real recoverable run
- when automatic latest resolution sees a newer planned-only terminal bundle, it also skips that evidence-only candidate and falls back to the newest real producer run

### `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id>`

Default recovery read (compact first): `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only`
Automation variant: `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only --recommendation-format json`
- Example compact JSON: `docs/workflows/examples/sc-chapter6-route-compact.example.json`
- Example compact stdout: `docs/workflows/examples/sc-chapter6-route-compact.stdout.example.txt`

Use when:
- you already have recovery artifacts and need a cheap go/no-go decision before reopening `6.7`
- you need to decide whether `6.8` is worth paying for this round
- you want a stable route for `repo-noise-stop`, `fix-deterministic`, `run-6.8`, `run-6.7`, or residual recording

Prerequisites:
- task-scoped recovery artifacts under `logs/ci/**`

Why this is stable:
- it reads recovery artifacts first, instead of relying on operator memory
- it classifies high-confidence `repo-noise` vs `task-issue` for the first failed `6.7` round
- it only recommends `6.8` when current edits hit the previous reviewer anchors
- explicit residual recording writes eligible deferred findings to `docs/technical-debt.md`; Decision Log and Execution Plan remain reserved for actual policy/authority decisions or durable coordination
- `scripts/sc/llm_review_needs_fix_fast.py` now consumes the same route preflight before spending deterministic / LLM budget when prior review artifacts exist; run `chapter6-route --recommendation-only` manually when you want the cheapest read-only go/no-go before touching 6.8.


### `py -3 scripts/python/dev_cli.py run-chapter7-ui-wiring --delivery-profile <profile>`

Use when:
- Chapter 6 has already closed the currently completed task slice and you want the top-level Chapter 7 UI wiring route
- you need one stable entrypoint that collects done-task inputs and validates the governed UI wiring GDD artifact
- you want a cheap self-check before editing `docs/gdd/ui-gdd-flow.md`

Prerequisites:
- task triplet available
- `docs/gdd/ui-gdd-flow.md` exists or is about to be created as the governed Chapter 7 artifact

Why this is stable:
- it is the top-level Chapter 7 UI wiring orchestrator
- it runs the collector, optional writer, validator, and artifact-manifest validator in fixed order
- `--write-doc` also produces `docs/gdd/ui-gdd-flow.candidates.json` as the machine-readable candidate sidecar
- `--create-tasks` also runs `create_chapter7_tasks_from_ui_candidates.py` and can parameterize `--repo-label`, `--back-story-id`, and `--gameplay-story-id`
- `docs/workflows/chapter7-profile-guide.md` is the operator-facing reference for repo-local profile overrides and template seeds
- `--chapter7-profile-path` lets business repos override bucket mapping, task identity, labels, refs, headings, and surface defaults without forking the scripts; the template example lives at `docs/workflows/templates/chapter7-profile.template.json`
- it writes `logs/ci/<date>/chapter7-ui-wiring/summary.json` as the canonical Chapter 7 execution summary
- it also writes `inputs.snapshot.json`, `closure-summary.json`, `task-status-patch-preview.json`, `task-status-patch-preview.md`, `task-status-patch.json`, `artifact-manifest.json`, and `artifact-manifest-validation.json` for deterministic rerun, closure inspection, and write-back planning

### `py -3 scripts/python/dev_cli.py run-chapter7-backlog-gap --design-doc-path <doc> --epics-doc-path <doc> --duplicate-audit-path <doc>`

Use when:
- you want to decide whether Chapter 7 should create new `T47+` backlog items or stay in wiring-only closure
- you need a cheap comparison between BMAD design/epics text and the current task triplet before generating new tasks
- you want an explicit recommendation before paying for candidate task creation

Prerequisites:
- task triplet available
- design / epics / duplicate-audit docs exist

Why this is stable:
- it is the top-level backlog-gap analyzer for Chapter 7
- it emits a machine-readable summary and recommendation instead of relying on manual judgment
- it helps separate "already covered by T1-T46" from "not clearly covered and may justify T47+"

### `py -3 scripts/python/dev_cli.py apply-chapter7-status-patch --patch <path>`

Use when:
- you want to apply the machine-readable status patch contract produced by Chapter 7 closure analysis
- you need a dry-run preview before mutating `.taskmaster/tasks/*.json`
- you want one deterministic write path instead of hand-editing task status views

Prerequisites:
- an existing `task-status-patch.json` contract produced by `run-chapter7-ui-wiring`

Why this is stable:
- it is the public write-back entrypoint for Chapter 7 task status reconciliation
- `--dry-run` lets you preview all operations without writing
- it records an explicit summary of applied and failed operations

### `py -3 scripts/python/dev_cli.py plan-capabilities --stage <stage> --run-id <id>`

Use when:
- the affected Chapter 5 scope is stable and you need the formal derived Capability map
- you need three isolated same-model candidates plus independent anonymous selection
- you need historical Capability ID alignment and controlled `capability_refs` rebinding

Why this is stable:
- formal generation fails closed unless the external runner proves workspace-only fresh-session isolation
- candidates are bound to one blinded analysis identity
- the review is a separate anonymous A/B/C run
- apply is restricted to derived Capability surfaces and capability-only Chapter 5 rebinds
- for explicit task-free B-route planning alongside post-Chapter-5 A usage, pass `--input-stage 3b --planning-contract <contract.json>` (and `--planning-profile 3b-capabilities-v1` on downstream stages); see [b-route-native-planning-status.md](b-route-native-planning-status.md)

Owning Skill: `.agents/skills/plan-capabilities/SKILL.md`.

### `py -3 scripts/python/dev_cli.py plan-mvg --stage <stage> --run-id <id>`

Use when:
- one explicit Capability version has been selected/applied
- you need an initial MVG manifest or a cumulative reviewed delta
- you need player-journey flows, entrypoint plans, task/contract/test ownership and anti-weakening validation

Why this is stable:
- every original source/task/contract/test/readiness input and the prepared manifest (including absence) is hash-bound
- use `--stage review --runner <isolated-runner>` for an independent semantic review before formal validation/apply
- an existing manifest evolves through `update_mvg_baseline.py` semantics instead of replacement
- planned entrypoints cannot masquerade as existing files, and planning never claims runtime verification
- `--stage audit` checks the selected chain and declared source conflicts locally; `reopen-plan --audit <run-relative-path> --audit-sha256 <hash>` and `reopen --plan <run-relative-path> --plan-sha256 <hash>` explicitly reopen the full affected successor closure. Exact evidence/hash bindings and cumulative budgets remain mandatory; any apply journal blocks reopening. Declaration fields and recovery rules are owned by `docs/workflows/mvg-integration-acceptance.md`.
- both Chapter 6 entrypoints consume the durable trace and require current final obligation bindings; the lane automatically consumes its bound milestone handoff even when the optional flag is omitted
- ordinary tasks use `--stage rebind-handoff --task-id <id>` to bind current readiness and resolve applicability without creating a fake milestone handoff
- for a task that is actually owned by a milestone change plan, use `--stage rebind-handoff --task-id <id> --change-plan <path> --handoff-out <path>`; this reuses the existing milestone handoff contract instead of inventing a planning-owned handoff
- for explicit task-free B-route planning alongside post-Chapter-5 A usage, pass `--input-stage 3b --planning-contract <contract.json>` (and `--planning-profile 3b-mvg-v1` on `generate`, `verify-selection`, `review`, `validate`, and `status`; invoke `--stage audit` explicitly without `--input-stage 3b`); see [b-route-native-planning-status.md](b-route-native-planning-status.md)

Owning Skill: `.agents/skills/plan-mvg/SKILL.md`.

## Task Delivery Loop

### `py -3 scripts/python/dev_cli.py run-single-task-chapter6 --task-id <id> --godot-bin "$env:GODOT_BIN" --delivery-profile <profile>`

Use when:
- you want one top-level Chapter 6 orchestrator instead of manually stitching `6.3 -> 6.9`
- you want recovery-first routing before paying for `6.7` or `6.8`
- you want the shared repository P1 must-fix floor across `playable-ea`, `fast-ship`, and `standard`, with optional stricter `--fix-through P2|P3`

Prerequisites:
- task triplet available
- `GODOT_BIN` for engine-side steps and repo-level hard checks

Why this is stable:
- it is the single-task Chapter 6 top-level entrypoint
- it always starts from `resume-task` and `chapter6-route` instead of assuming a fresh run
- its lane / stop-loss / needs-fix decision now comes from one internal route-evaluation pass, which reduces drift between plan rendering and runtime execution when Chapter 6 rules keep growing
- it only jumps directly to `6.8` when recovery artifacts already prove that this is the cheapest valid lane
- by default it records residual `P2/P3` findings instead of repeatedly paying for the same-shape closure loop
- it keeps `6.9` behind the same orchestrator, so repo-level hard checks are still part of the normal closeout path

When supplying Chapter 6 `--frozen-context`, `--impact-report` and `--revision`,
the orchestrator pauses before Review (including fork) with
`review_context_required`. Continue through the Review entrypoint with independently
prepared Review artifacts, following `docs/workflows/knowledge-context-freeze.md`.
This split path still requires the normal post-review routing and `6.9` hard checks.
For `--self-check` with a valid Chapter 6 handoff, `status = ok` means the
preview completed successfully; `plan_status = blocked`, `stop_reason =
review_context_required`, `pending_step` and `next_action` describe the expected
runtime pause. The preview stops at the pending Review step and includes the
validated handoff arguments in that command; it does not plan post-Review or
`6.9` steps as part of the same invocation.

### `py -3 scripts/sc/run_review_pipeline.py --task-id <id> --godot-bin "$env:GODOT_BIN" --delivery-profile <profile>`

Use when:
- running the full task path for one task
- you want `sc-test`, acceptance, and LLM review under one run id
- you want repair guidance, active-task sidecars, and technical debt sync

Prerequisites:
- task triplet available
- `GODOT_BIN` for engine-side stages
- LLM runtime if you do not pass `--skip-llm-review`

Why this is stable:
- it is the Chapter 6.7 review entrypoint; the Chapter 6 daily-loop entrypoint is `dev_cli.py run-single-task-chapter6`
- it replaces manually stitching lower-level review commands together
- it now carries rerun stop-loss signals so repeated full reruns are blocked when deterministic is already green or when recent `sc-test` failures share the same fingerprint
- it now consumes the same `chapter6-route` signal before a fresh full rerun, so `inspect-first`, `repo-noise-stop`, `fix-deterministic`, and `run-6.8` recommendations are enforced before refactor preflight and downstream cost
- `--resume` and `--fork` also enforce the approval sidecar contract before step execution: pending approval pauses recovery, approved approval redirects to `--fork`, denied approval redirects to `--resume`, and invalid or mismatched approval evidence forces inspection first
- when the review transport must be piloted explicitly, pass `--llm-backend codex-cli|openai-api`; the flag now propagates through the internal `sc-llm-review` stage instead of forcing operators to bypass `run_review_pipeline.py`
- when the same invocation already proved a known `sc-test` unit root cause, it records `diagnostics.sc_test_retry_stop_loss` and stops the same-run retry instead of paying that cost again
- exceptional overrides stay explicit: `--allow-full-rerun` and `--allow-repeat-deterministic-failures`
- a fresh run now inherits the latest task-scoped profile lock unless you explicitly pass `--reselect-profile`
- `--llm-base` now defaults to `origin/main`
- `--dry-run` still writes a local `summary.json` / `execution-context.json` / `repair-guide.*` in its own `out_dir`, but it no longer publishes `latest.json` or `active-task` sidecars, so it cannot pollute task recovery pointers
- producer runs that end as `planned-only` / `planned_only_incomplete` are not valid recovery baselines for reopening `6.7` or `6.8`; they are evidence only

### `py -3 scripts/python/run_single_task_light_lane_batch.py --task-id-start <start> --task-id-end <end> --delivery-profile <profile> --max-tasks-per-shard <n>`

Use when:
- you want to run workflow 5.1 across a long task range without manually splitting directories
- you want isolated shard `out-dir`s plus one coordinator summary and one merged summary
- you want to avoid `last_task_id` / resume pollution caused by reusing the same `out-dir` for overlapping reruns
- you want one preset like `stable-batch` or `long-batch` instead of manually restating every rolling/backoff flag

Prerequisites:
- task triplet available
- Chapter 5.0 run-start, independent Extraction B and global reconciliation completed before task-local repair; re-reconcile changed inputs before final readiness/Knowledge promotion
- LLM runtime for semantics-related steps

Why this is stable:
- it is the top-level batch coordinator for workflow 5.1
- it wraps the existing light-lane runner instead of duplicating lower-level semantics logic
- merged/top-level summaries surface extract-failure signatures and failure families for faster batch triage
- top-level `summary.json` now also emits `preferred_lane`, `recommended_action`, `recommended_command`, `forbidden_commands`, `latest_reason`, and `recommended_action_why`
- batch recommendations are batch-aware: timeout/model/soft-step reruns point to failed task ids instead of suggesting a single-task command
- merge-validation failures and rolling stop-loss cutovers route to `inspect-first` or `split-batch` instead of implying a blind full rerun
- it supports rolling `warn|degrade|stop` behavior when cumulative extract failure rate becomes untrustworthy
- it can also back off automatically after one shard times out heavily by increasing next-shard LLM timeout and reducing next-shard size
- it can warn or stop on repeated extract failure families and emits `family_hotspots` / `quarantine_ranges` for later targeted reruns

### `py -3 scripts/python/run_single_task_light_lane.py --task-ids <id> --delivery-profile <profile> [--no-align-apply]`

Use when:
- a task needs workflow 5.1 semantics stabilization but you do not want to hand-stitch the lower-level commands
- you want resilient execution with task resume, timeout retry, extract-failure skip policy, and optional batch extract-first mode
- you want one rolling summary/log directory for a single task or a small ad-hoc batch

Prerequisites:
- task triplet available
- Chapter 5.0 run-start, independent Extraction B and global reconciliation completed before task-local repair; re-reconcile changed inputs before final readiness/Knowledge promotion
- LLM runtime for semantics-related steps

Why this is stable:
- it is the direct wrapper for workflow 5.1 single-task / small-batch runs
- its `summary.json` now emits `preferred_lane`, `recommended_action`, `recommended_command`, `forbidden_commands`, `latest_reason`, and `recommended_action_why` for recovery-aware reruns
- it supports read-only lane mode (`--no-align-apply`), `extract-first` batch mode, and resume from `summary.json`

### `py -3 scripts/python/merge_single_task_light_lane_summaries.py --date <YYYY-MM-DD>`

Use when:
- you split a full workflow 5.1 run into multiple `single-task-light-lane-v2*` directories
- you want one merged summary with transparent per-task source mapping

Prerequisites:
- one or more light-lane summary files already exist

Why this is stable:
- it provides the post-batch merge/report entrypoint for split workflow 5.1 runs
- it writes transparent source metadata instead of a path-only source list
- it hard-fails when merged completeness validation detects untrusted input coverage

### `py -3 scripts/sc/llm_generate_tests_from_acceptance_refs.py --task-id <id> --tdd-stage red-first --verify <mode>`

Use when:
- acceptance `Refs:` point to missing `.cs` or `.gd` tests
- you want strict red-first test creation before implementation
- you need ACC anchors inserted into generated tests

Prerequisites:
- task triplet available
- LLM runtime
- `--godot-bin` when verification includes Godot-side checks

Why this is stable:
- it is the recommended acceptance-to-test scaffold entrypoint
- it already includes deterministic naming and strict-red guards
- when test-generation transport must be piloted explicitly, pass `--llm-backend codex-cli|openai-api`; the flag now covers both primary-ref selection and per-file generation without bypassing this entrypoint

### `py -3 scripts/sc/check_tdd_execution_plan.py --task-id <id> --tdd-stage red-first --verify auto --execution-plan-policy <mode>`

Use when:
- you need to determine whether durable recovery/coordination requires an Execution Plan before TDD
- the task is known cross-session, has ordered behavior slices or partial work to recover, crosses an authority migration stage, or is a staged large refactor/MVG/workflow-control-plane change
- you want a `required | recommended | none` decision without treating test-file count, mixed `.cs/.gd`, anchors, or verify mode as plan triggers

Prerequisites:
- task triplet available

Why this is stable:
- it separates durable coordination needs from ordinary implementation complexity
- `recommended` is advisory; only `required` can create or require a matching active plan under the selected policy

### `py -3 scripts/python/dev_cli.py run-prototype-tdd --slug <slug> --stage <red|green|refactor> ...`

Use when:
- the work is still in prototype lane but you want a disciplined red/green/refactor loop
- you want prototype evidence without entering the formal Taskmaster pipeline
- you need a lightweight note under `docs/prototypes/` plus local logs under `logs/ci/**`

Prerequisites:
- at least one verification target such as `--dotnet-target` or `--gdunit-path`, unless you intentionally use `--create-record-only`
- `--godot-bin` when prototype verification includes Godot-side checks

Why this is stable:
- it is the recommended prototype-lane TDD entrypoint
- it keeps prototype evidence separate from Chapter 6 producer artifacts
- it pairs with `docs/workflows/prototype-lane-playbook.md` and `docs/workflows/prototype-tdd.md`

### `py -3 scripts/sc/build.py tdd --stage <red|green|refactor>`

Use when:
- you want the deterministic TDD orchestration path
- you are already inside an implementation loop and need stage-specific gating

Prerequisites:
- task triplet available for task-aware checks
- `.NET 8 SDK`
- `--godot-bin` if your stage triggers engine-side checks

Why this is stable:
- it is the main build-side TDD orchestrator, not a one-off helper

## Task Metadata And Architecture Integrity

### `py -3 scripts/python/task_links_validate.py`

Use when:
- validating ADR / Chapter / Overlay backlinks
- checking front matter and task semantic link integrity

### `py -3 scripts/python/check_tasks_all_refs.py`

Use when:
- validating refs completeness across task triplet views
- confirming task metadata and linked assets are coherent

### `py -3 scripts/python/validate_task_master_triplet.py`

Use when:
- validating triplet structural consistency
- auditing task mapping, link, layer, and dependency shape

### `py -3 scripts/python/validate_contracts.py`

Use when:
- validating domain contracts under the template rules
- checking naming, XML docs, namespace rules, and overlay backlinks

### `py -3 scripts/python/check_domain_contracts.py`

Use when:
- a business repo keeps extra domain-level contract checks outside the generic template validator
- you want the domain-specific contract stop-loss entrypoint

Stop-loss:
- this script may be a lighter or repo-specific supplement; do not treat it as a replacement for `validate_contracts.py`

### `py -3 scripts/python/sync_task_overlay_refs.py --prd-id <PRD-ID> --write`

Use when:
- task overlay refs drift from overlay docs
- you need to refresh triplet overlay linkage after overlay authoring or regeneration

Prerequisites:
- task triplet available
- real PRD / overlay roots
- write review after execution

Why this is stable:
- it is already part of the documented overlay/task maintenance path

### `py -3 scripts/sc/llm_generate_overlays_batch.py ...`

Use when:
- scaffolding or repairing Overlay 08 pages from PRD inputs
- migrating a business repo toward the current overlay authoring flow

Prerequisites:
- PRD inputs and business-local `PRD-ID`
- LLM runtime

Why this is stable:
- it is the batch overlay generation entrypoint referenced by the current upgrade docs and workflows

## Lower-Level But Still Public

These remain public and workflow-facing, but they are usually invoked through higher-level entrypoints first:

- `scripts/sc/acceptance_check.py`
- `scripts/sc/llm_review.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; keep `codex-cli` as the default until the API path is explicitly piloted
- `scripts/sc/test.py`
- `scripts/sc/llm_extract_task_obligations.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; use it only when piloting semantic extract transport directly instead of through a higher-level wrapper
- `scripts/sc/llm_align_acceptance_semantics.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; keep `codex-cli` as the default unless the repo is intentionally validating the API path
- `scripts/sc/llm_fill_acceptance_refs.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; `--self-check` remains deterministic and is the first stop-loss before a real write run
- `scripts/sc/llm_check_subtasks_coverage.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; this is useful when semantic preflight transport is being piloted in isolation
- `scripts/sc/llm_semantic_gate_all.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api` while preserving `--model-reasoning-effort`
- `scripts/sc/llm_generate_tests_from_acceptance_refs.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; both primary-ref selection and per-file generation follow the same backend
- `scripts/sc/llm_generate_red_test.py`
  - supports backend selection via `--llm-backend codex-cli|openai-api`; use it when you want the narrower red-test drafting helper without opening the broader acceptance-test generation flow
- `scripts/python/run_gate_bundle.py`
- `scripts/python/run_dotnet.py`
- `scripts/python/run_gdunit.py`
- `scripts/python/smoke_headless.py`
- `scripts/python/quality_gates.py`
- `scripts/python/ci_pipeline.py`

Use them directly when you are isolating one failing stage or intentionally bypassing the higher-level orchestrator for debugging.

## Relationship To Other Docs

- `workflow.md`
  - day-to-day operator sequence
- `workflow.example.md`
  - bootstrap example for a fresh business repo copied from the template
- `docs/workflows/script-entrypoints-index.md`
  - full recurring entrypoint inventory with direct deps, transitive deps, and argument scan
- `docs/workflows/local-hard-checks.md`
  - contract for the repo-level hard harness
- `docs/workflows/project-health-dashboard.md`
  - repo-health records and local dashboard behavior
- `scripts/sc/README.md`
  - deeper `sc-*` runtime behavior and examples\n

## Milestone incremental entrypoints

- `scripts/python/build_source_ledger.py --mode add`: consumes the versioned cumulative source set and a declared source delta.
- `scripts/python/compile_task_triplet.py`: previews explicit create/update/reuse/retire task-view operations; `--write` is conflict- and fingerprint-guarded.
- `scripts/python/milestone_incremental_handoff.py`: validates a reviewed milestone change plan and binds one task to current Chapter 5 readiness.
- Milestone change plans review each changed source block and name one cumulative `baseline_manifest`. Handoff validation checks the bound block hashes, target/owner/contract consumers and old flow regressions in that manifest; semantic judgments still require review of the complete GDD.
- `scripts/python/update_mvg_baseline.py`: previews/applies an explicit add/update/retain/retire delta to an existing MVG manifest.
- `scripts/python/run_mvg_acceptance.py`: remains the runtime entrypoint and records the exact manifest SHA/baseline lineage.

`dev-cli run-single-task-chapter6` forwards both `--milestone-handoff` and `--milestone-regression-summary` to the lane. Regression evidence requires the exact current HEAD/manifest and a clean current worktree.

These are additive modes of the existing Chapter workflow, not a second milestone framework.

## B 路线只读迁移预检

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-preflight --root <root> --epics <epics> --protection-input <input> --candidate <carrier> --intents <intents> --run-id <fresh-id>`。直接 owner 为 `scripts/python/preflight_b_route_migration.py`，参数相同。单 JSON stdout，0 为可审阅机器预览、1 为输入／迁移阻断、2 为参数／新输出目录失败；无 apply，仅全新 logs，不创建 pycache。明确候选原 bytes、三联及累计义务、语义未核验与真实未启用边界见[owner 说明](b-route-migration-preflight.md)。旧 pending 仍导航原 Capability apply，预检不会执行恢复。

## B 路线 3A 来源准备与记账

`py -3 scripts/python/dev_cli.py b-route-sources --stage prepare|account` 与直接入口 `scripts/python/account_b_route_sources.py` 共用唯一 owner。必须显式提供 root／run／scope／attempt；prepare 另需 source-set，account 另需 prepared／candidate。两者只输出单个 JSON，退出码为 0／1／2，禁止字节码写入，仅排他创建全新 logs。独立审计／复验沿用此入口的 `--stage audit|verify`，分别显式消费 accounted／audit-ref，均需 runner／expected-model；执行、语义阻断、synthetic 与真实证明、持久预算及复用合同见[来源审计 owner](b-route-source-audit.md)。准备和完整记账均不授予独立审计或正式采纳；现行 A 有效。载体、原字节身份、容量、漂移、事件及 Windows 验证见[来源记账 owner](b-route-source-accounting.md)。

## B 路线 3C 只读任务变更预览

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-task-preview --root <root> --plan-id <plan-id> --scope-id <scope-id> --audit-ref <3a-report> --run-id <fresh-id> [--protection-ref <path>] [--manifest <path>] [--change-intents <path>]`。直接 owner 为 `scripts/python/preview_b_route_task_changes.py`，参数相同。单行 JSON stdout，退出码 0 为稳定可审阅预览、1 为 3A/3B/语义/保护/漂移阻断、2 为参数或目录冲突；仅独占写入全新 logs，不写三联或正式规划、不分配永久 Task ID、不创建 pycache。详见[3C 预览 owner 说明](b-route-task-preview.md)。

## B 路线 3C 受治理三联编译与绑定

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-task-compile --root <root> --stage prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover --operation-id <op-id> [--request <request.json>]`。直接 owner 为 `scripts/python/compile_b_route_tasks.py`，参数相同。`prepare` 仅分配永久 `taskmaster_id` 与 `NG/GM` 并锁三联投影；`apply` 初入旧+新资源锁重读活三联并合并活 `status`/`subtasks[].status` 封存入 `commit.json` 与 receipt，`publish` 末推 `catalog.v1.json`；事件写 `logs/ci/b-route-task-compilation/<op>/events.jsonl`，不授 readiness/runtime/默认 B，进 Chapter 6 仍需 Chapter 4–5。详见[3C 编译 owner 说明](b-route-task-compilation.md)。

## B 路线统一 Task 来源与适用计划解析

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-task-origin --task-id <id> [--root <root>] [--operation <op>] [--report <logs/ci/.../*.json>]`。直接 owner 为 `scripts/python/resolve_b_route_task_origin.py`，参数相同。无 `--report` 时 100% 零目录/锁/文件创建（不调 `initialize_lock_namespace`）；先验 pending 与已提交 `policy`/`catalog`/`origins` 全反向关系，分类为 `B`、`A`、`explicit_not_enabled_a` 或 `blocked`，汇总完整适用计划/绑定/处置/Flow 闭包与 `applicable_set_digest`；退出码 0/1/2，恒不授予实施权、readiness 或默认 B。详见[Task 来源解析 owner 说明](b-route-task-origin-resolution.md)。

## B 路线 Chapter 4 生产契约与四部分实施定义细化

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding --root <root> --stage preview|prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover --operation-id <op-id> [--request <request.json>]`。直接 owner 为 `scripts/python/refine_b_route_chapter4_binding.py`，参数相同。经 `published_bundle` 与 Story 3.3 `resolve_task_origin` 核验目标 Task 全为 `B` 后，细化生产命令、只读状态与唯一所有者、C# 适配、控件/场景绑定、UI 人工区与测试义务；仅显式 `public_changes` 经 base64 原始字节 `public-sync-journal.json` + `public-sync.pending.json` 前滚写入 BCL 契约、`EventTypes.cs` 与 sha256 增量合并 Overlay，再经 `_b_route_commit` 发布 `stage="4"` 绑定、`task-origins.v1.json` 与 `commits/<op>.json` 并末推 `catalog.v1.json`；事件写 `logs/ci/b-route-chapter4-binding/<op>/events.jsonl`，恒定 `readiness=false`/`runtime_verified=false`/`default_b_enabled=false`。详见[Chapter 4 绑定细化 owner 说明](b-route-chapter4-binding.md)。

## B 路线共同 InputSet 与新鲜度解析

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-input-set --task-id <id> [--root <root>] [--operation <op>] [--candidate-binding <path>] [--baseline <path>] [--lock-mode none|scope] [--max-attempts 1..5] [--report <logs/ci/.../*.json>]`。直接 owner 为 `scripts/python/resolve_b_route_input_set.py`，参数相同。默认 `--lock-mode none` 且无 `--report` 时零目录/零文件/零锁创建；先调 Story 3.3 验证来源、pending 与适用集，汇总来源/Ledger/Requirement、plan/binding 修订（支持显式 `--candidate-binding` 单槽替换并标 `uses_candidate_binding=true`）、Stage-4 语义、Task 投影（仅排 `status` 与直接 `subtasks[].status`）、ADR/Overlay/Contracts、解耦活 `status` 的 MVG manifest 或合法非 Flow `other_verification`、传递依赖闭包（拒绝未知/循环）与 policy/codec/环境计算 `input_set_digest`；对比基线输出失效项与最早 `return_stage`（`3A`..`5`），`--lock-mode scope` 经 `guarded_input_set` 仅持业务 scope 租约（`review_only=True`、无全局写锁）并进入/重验；恒定不授予实施权、readiness、runtime_verified 或默认 B。详见[InputSet 与新鲜度 owner 说明](b-route-input-set-resolution.md)。

## B 路线 Stage-5 真实 MVG 义务与合法其他验证依据绑定

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations --root <root> --stage preview|prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover --operation-id <op-id> [--request <request.json>]`。直接 owner 为 `scripts/python/bind_b_route_stage5_obligations.py`，参数相同。承接已提交 Stage-4/5 绑定（禁止跳 Stage 4），经 Story 3.3 `resolve_task_origin` 与 Story 3.5 `resolve_input_set`（含候选单槽与 pre-sync）核验，守恒 `task_id` 集/Stage-4 四部分/对象与 `STAGE4_OBL_PREFIX`；为 Flow/交接/回归与触达 Flow 的非 Flow 绑有效 manifest（含可选经 `update_mvg_baseline` 防削弱审阅与 `public-sync-journal.json` 同步的 delta），仅在 3B applicability 理由、`adoption_proof_refs`、真实 `other_verification_refs` 与零 Flow 影响齐备时免造 Flow/manifest，未知影响按累计范围保守扩大并分列三类；验三类角色与无自锁、共享去重、旧 `done` 标 `requires_reverification=true`（不复制 `status` 入权威）与审阅减义务；经 `_b_route_commit` 发布 `stage="5"` 绑定并末推 `catalog.v1.json`，恒定 `readiness=false`/`runtime_verified=false`/`default_b_enabled=false`。详见[Stage-5 义务绑定 owner 说明](b-route-stage5-obligations.md)。

## B 路线 Chapter 5 同源核对与有效 Readiness

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness --root <root> --stage reconcile|verify|check-readiness --task-id <id> [--decisions <path>] [--operation <op>] [--audit-ref <path>] [--out <logs/...>] [--readiness-out <logs/...>] [--reconciliation <path>] [--readiness <path>] [--lock-mode none|scope] [--no-latest] [--dry-run] [--record-technical-debt] [--require-full-audit-proof]`。直接 owner 为 `scripts/python/reconcile_b_route_chapter5_readiness.py`，参数相同。经 Story 3.3 `resolve_task_origin` 判 `B`、Story 3.5 `guarded_input_set` 持业务 scope 租约（`review_only=True`、无全局写锁）且全部适用绑定均为已提交 `stage="5"`（否则归因 `4`/`5`）后，只读复用 3A 来源证明并独立核对 Chapter 5 同源语义（`acceptance_links`、`authority_decisions`、`dependency_decisions`、`overlap_decisions`、三类角色无自锁、合法未 `done`/`planned` 对象与测试、旧 `done` 标 `requires_chapter6_reverification=true`、P0/P1 底线与 `docs/technical-debt.md` P2..P4 记债），冻结 `input_set_digest`/`applicable_set_digest`/`scope_ids`/`plan_refs`/`binding_refs`/`reconciliation_sha256` 并桥接 `load_task_readiness` 与 `refresh_chapter_knowledge`（无 B 痕迹保 A，存 B 痕迹走 B 禁落 legacy）；单行 JSON stdout，退出码 0/1/2，恒定 `runtime_verified=false`/`default_b_enabled=false`。详见[Chapter 5 readiness owner 说明](b-route-chapter5-readiness.md)。

## B 路线 Chapter 6 统一实施门禁

稳定入口：`py -3 -B scripts/python/dev_cli.py b-route-chapter6-gate --task-id <id> [--root <root>] [--operation <op>] [--lock-mode none|scope] [--expected-input-set-digest <sha256:...>] [--report <logs/ci/.../*.json>]`。直接 owner 为 `scripts/python/check_b_route_chapter6_gate.py`，参数相同。默认 `--lock-mode none` 且无 `--report` 时严格零写盘；公共 CLI（`dev_cli.py run-single-task-chapter6`/`run-acceptance-preflight`/`chapter6-knowledge`/`publish-chapter6-semantics`）、直接 `run_single_task_chapter6_lane.py`、`_mvg_obligations.py` 及全部 Code Map 内部脚本共用 3.3→3.5 `guarded_input_set`→3.6 `stage="5"` 义务（或零影响非 Flow `other_verification_refs`）→3.7 readiness 统一门禁，拒绝非 ASCII `task_id` 与自由 `N/A` 标签，排除 `docs/planning/b-route/schemas/**` 误判，经密钥哈希与 OS 字节锁实测凭据支持父子业务 scope 租约重入（不持全局写锁、禁信伪造环境变量）并在每步副作用前复验漂移/pending；状态写经短锁写 `tasks.json` 唯一权威并验定义投影不变，强制 `--skip-project-health` 禁隐式刷 Knowledge，恒定 `runtime_verified=false`/`default_b_enabled=false`。详见[Chapter 6 统一实施门禁 owner 说明](b-route-chapter6-gate.md)。
