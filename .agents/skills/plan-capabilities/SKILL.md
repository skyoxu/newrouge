---
name: plan-capabilities
description: Generate and apply post-Chapter-5 Capability grouping from authoritative GDD/Requirement evidence using three genuinely isolated same-model candidates and an independent anonymous review. Use only after the explicit GDD-related Chapter 3-5 scope is ready.
---

# Plan Capabilities

## Role

Create the derived Capability organization after the relevant Chapter 3-5 scope has converged. Capability is a human-readable navigation and grouping layer for MVG planning; it never owns Taskmaster status, never edits Requirement statements, and never blocks game/runtime execution.

## Portable granularity policy

- Do not target a fixed Capability count or copy another project's count, titles, IDs, or boundaries.
- Generate from current user-visible outcomes and end-to-end journey handoffs first.
- Split when a distinct outcome, owner, lifecycle, or independently reviewable handoff is evidenced.
- Merge when multiple Requirements are only implementation steps of one outcome.
- Treat Requirement density, singleton Capabilities, and large buckets as review signals, not automatic errors.
- A one-Requirement Capability is valid only when the Requirement has an independently meaningful outcome or boundary.
- Review must compare human comprehension, journey continuity, source fidelity, and handoff cost; quantity is never a score or tie-breaker.

## Hard boundaries

- Authoritative inputs are the cumulative source set, full Source Block Ledger, reviewed Requirements, task/Acceptance/contract semantics, and explicit Chapter 5 readiness scope.
- Source transport must be lossless. JSON whitespace minification is allowed; dropping task descriptions, Acceptance, tests, Source Block text or Requirement fields to fit a request is forbidden. Before invoking a model, validate prepared file hashes, exact batch bodies/IDs and aggregate serialized input limits. ID coverage alone is not evidence that full source content was supplied.
- The three initial candidates must use fresh sessions, the same model, the same prompt bytes, and the same blinded analysis bundle.
- Formal generation requires an isolation runner that reports workspace-only reads and no outside-workspace access. If no such runner exists, stop after prepare/validation; never emulate independence in one chat.
- Old formal Capability answers and task `capability_refs` are excluded from the candidate analysis view. Capability/module organization that is present in the authoritative GDD remains visible. An explicitly supplied diagnostic reference may be used only to explain migration differences; it must not anchor a new project's grouping.
- The review is a fourth fresh isolated session. It sees anonymous A/B/C candidates in a reproducible shuffled order and never sees the private mapping. If a valid current formal Capability file exists, prepare freezes it as `candidates/D.json` for the review only; D is explicitly the incumbent and may be selected. The incumbent is never copied into candidate-generation analysis input. If no valid incumbent exists, the review remains the original A/B/C flow and cannot select D.
- Do not merge the three by default. A valid outcome may be `no_valid_winner`.
- Applying Capability may update only derived Capability artifacts, task `capability_refs`, Capability topology edges, topology hashes, and a capability-only Chapter 5 fingerprint rebind. It must not change task IDs, statuses, Acceptance, subtasks, Requirement text, or task intent identity.

## Primary workflow

1. Prepare a blinded, hash-bound analysis bundle:
   `py -3 scripts/python/plan_capabilities.py prepare --run-id <id> --task-id <id> [--task-id <id> ...]`
2. Inspect `logs/ci/capability-planning/<id>/analysis-input/analysis-index.json`. A draft may use `--allow-unready-draft`, but formal candidate generation refuses an unready scope.
   Prepare checks every task sink of the current ledger source round, including active Requirement mappings and legitimate non-task sinks. A single ready task cannot hide another task of that round. Unrelated unchanged historical sources do not become an unconditional readiness task list; the model input remains cumulative.
3. Generate three candidates through the configured isolation runner:
   `py -3 scripts/python/dev_cli.py plan-capabilities --stage generate --run-id <id>`
4. Run independent review. When the current formal Capability baseline is present, the reviewer compares A/B/C against the frozen incumbent D and may retain D; otherwise it compares only A/B/C:
   `py -3 scripts/python/dev_cli.py plan-capabilities --stage review --run-id <id>`
5. Preview historical ID alignment:
   `py -3 scripts/python/plan_capabilities.py preview-alignment --run-id <id>`
   Reuse an exact Requirement-membership match automatically only when both the candidate and historical match are unique. Changed membership or multiple identical-member nodes requires explicit reviewed candidate decisions and historical retain/retire decisions. Legal Requirement multi-membership remains supported; stable IDs must be unique.
6. Apply only after review/alignment:
   `py -3 scripts/python/plan_capabilities.py apply --run-id <id> --alignment-override <reviewed.json> --confirm`
7. After a successful apply, the Knowledge page workflow refreshes the Chapter 5 workspace topology from the applied Capability projection and its rebound task-scoped readiness evidence. The refresh must reach a stable workspace snapshot before the Capability job is published as complete; failure leaves the job failed/recoverable and does not report stale Knowledge as refreshed. This step is local workspace state only: it does not publish canonical Knowledge, scan the game, or change Taskmaster authority.
8. Validate semantic topology and inspect the per-task Chapter 5 rebind results. Any fingerprint change beyond `capability_refs` blocks automatic rebind and blocks formal MVG planning until the affected Chapter 5 task is reconciled normally. MVG preparation should consume the newly selected Capability job/hash and the refreshed workspace topology.

## Isolation runner contract

Default verified runner: `scripts/python/codex_isolated_model_runner.py`. It uses the authenticated Codex CLI session and its environment-default model configuration, with no model tools. Capability planning fails closed when Codex CLI is unavailable; it does not fall back to Copilot or the OpenAI API. The web workflow and `dev_cli plan-capabilities` use this same default. An explicit `--runner` remains available for controlled tests and operator-directed overrides; `SC_KNOWLEDGE_PLANNING_RUNNER` does not change the web Capability runner.

A custom runner may be supplied, but it must answer `--describe` with schema `newrouge.isolated-model-runner.v1`, including:

- `filesystem_scope = workspace_only`
- `fresh_session_per_invocation = true`
- `can_read_outside_workspace = false`
- `model_tools = []`
- exact `model`

Invocation contract:

`<runner> --workspace <dir> --prompt-file <file> --output <file> --timeout-sec <seconds>`

The runner may use Codex, an OpenAI-hosted sandbox, WSL/container isolation, or another approved executor, but the Skill never upgrades a native read-anywhere sandbox to “isolated” by assertion.

## Recovery and cost

### Input integrity and context limits

New runs default to a 2,700-second cumulative active-time allowance per candidate and a 2,700-second invocation timeout. The shared active-time allowance is 13,500 seconds for three candidates, independent review and alignment; it is a ceiling, not an expected duration or billed cost. Explicit CLI overrides remain supported. Existing run budgets are preserved.

Independent source/task analysis requests omit the full preparation index, batch inventory and unrelated task state. A stable bundle identity and shared attachments remain visible. Each task chunk retains complete task-view rows and receives complete related master/readiness rows, Requirement objects and linked Source Blocks, selected strictly by declared IDs. Missing declared references block dispatch; absent references are not guessed. Global authority hashes and complete coverage are still checked by machine, and final synthesis retains global context and validated analyses. Context limits are measured after this projection; no source text is truncated.

Built-in Capability transports verify every batch hash and compare each complete Source Block/Requirement object with the prepared authority, including repeated Requirement rows spanning batches. Missing batches, duplicate blocks, altered bodies or prepared-file drift block generation. Sanitized task views retain every field other than the explicitly recorded prior-Capability blinding; the former Codex task-field whitelist is removed.

After full authority validation, source-batch dispatch excludes blocks owned exclusively by cancelled/retired/superseded master tasks when no active Requirement references the block. Ownership must come from structured task IDs or an exact first-cell `T<id>` identity in a task-baseline table row; retirement prose alone is insufficient. Unknown ownership/status preserves the block. Dispatch bodies, output schemas and per-batch coverage use the same projection. Integrity receipts retain every excluded block ID, owner status, body hash and reason. The full ledger and final source accounting remain intact; synthesis records exclusions as retired with no Capability ownership rather than requesting model analysis of historical bodies.

The Codex runner checks each complete dispatch, including task/readiness context, wrappers, its current batch or synthesis stage, candidate repair seed or anonymous review candidates, and its coverage checklist. It enforces a 1 MiB transport limit and a conservative default 96,000-token input allowance. Counting uses the larger of `o200k_base` and `cl100k_base` plus 10% headroom; without `tiktoken`, the UTF-8 byte count is a conservative upper bound. This is an operator safety allowance, not model-capacity discovery. `SC_CAPABILITY_MAX_INPUT_TOKENS` or runner `--max-input-tokens` may set a verified allowance for the environment default model; do not increase it blindly or explicitly switch the model. Keep output/reasoning/system capacity outside that allowance.

For OpenAI and Codex formal generation, each Source Block/Requirement batch is sent in a fresh isolated request with no `previous_response_id` or accumulated transcript. Each batch is validated for exact body/ID coverage before the next request. Synthesis uses one request when all analyses fit; otherwise it consumes ordered groups of complete analyses in bounded stages. Each later stage receives the complete previous draft, and machine checks full candidate structure and ID accounting before the next stage. Only the last stage can publish a selectable candidate. Synthesis does not replay raw Source Blocks. Preflight estimates analysis sizes to check dispatch safety; after each validated model response, the complete packed output is measured, and synthesis is replanned against actual sizes before any synthesis call. An estimate is never a post-generation rejection threshold. True transport/context limits still fail closed without truncation. Codex exposes `--preflight` so deterministic input rejection occurs before any model invocation. These checks prove transport and accounting, not model understanding. Copilot single-batch Capability input uses the same lossless/body/context checks; its multi-batch boundary remains unsupported.

Codex exposes `--preflight`, `supports_input_preflight=true` and a per-dispatch request budget. The planner runs preflight before reserving any candidate/review invocation budget. Codex request counts mean CLI dispatches, not provider retries or billing. Deterministic input rejection stops immediately; retrying the three candidates cannot repair it. The workspace `runner-input-integrity.json` and execution receipt record full request identity, source/Requirement coverage and budget measurements. A preflight report is excluded from model-visible files so checking first does not alter the subsequent prompt.

Oversized input preserves the current Capability and all prepared evidence, with no shortened replacement or implicit fallback. Supporting larger projects requires an explicitly designed bounded semantic ingestion/projection stage with source conservation and cross-batch boundary validation; it must not be implemented as hidden excerpts or summaries falsely called full input. These guards prove what bytes/objects were supplied, not that a model understood every sentence.

Run state is durable under `logs/ci/capability-planning/<run-id>/`. Re-run the incomplete stage only. Existing valid candidates are evidence and should not be discarded just because a later stage failed. Candidate retries and total active-time budgets are operator-configured by the runner; never claim model-request counts or monetary cost when the runner cannot observe them.

Persist each candidate/review attempt and its active-time/request reservation before invocation. A caught interruption settles observed active time; process loss keeps the unknown invocation's reservation and consumed attempt. Reservations constrain later calls but are not observed cost, billing or paused wall time. Never reset them on resume.

Re-running review reuses a valid report bound to the original analysis bundle, all candidate hashes (including the incumbent hash when present), prompt, anonymous mapping, runner and execution receipt. Preserve `no_valid_winner` as well as a selected winner. A changed report, input, receipt or corrected candidate blocks reuse and apply; do not invoke another reviewer to bypass it. Require all five findings arrays, comparative tradeoffs, rationale, corrections and resolvable authoritative evidence refs. Empty findings arrays are legal; missing findings fields are not. If valid candidates exist but review, alignment, or apply is interrupted, preserve the completed prefix and expose a recoverable stage; never convert durable candidate/review evidence into a terminal failure. A later review invocation may make one fresh isolated attempt after the per-call retry allowance is exhausted, still bounded by the same cumulative budget. Recovery must re-check the authoritative input fingerprint and every persisted identity before resuming; a changed Git commit alone does not invalidate the run.

Review publishes its anonymous mapping, verdict, execution metadata and any corrected candidate through `review/publication.json`. Re-run review after interruption to finish that same recorded publication without another model call or resetting attempts/budgets. Before the publication checkpoint exists, reuse only a completed attempt whose original output and archived metadata still match their persisted identities. Unknown target edits or checkpoint drift block recovery; preserve the files for inspection. An unchanged no-winner verdict remains no-winner.

Do not prepare over an existing run ID. Before apply, the complete formal projection and readiness rebind are persisted in `apply-journal.json`. A pending pointer blocks Chapter 5/6 consumers during incomplete writes. Resume by re-running the same `apply --confirm`; it accepts only original or journal-owned target bytes and unchanged authority inputs, preserves subsequent external edits, and never regenerates candidates/review/alignment. A completed apply is idempotent. Keep the run directory until recovery completes; do not delete the pending pointer to bypass the gate.

Before creating the apply journal, validate all alignment decisions and the complete projected Source Block/Requirement/Capability/Task/Acceptance topology. Duplicate stable IDs, missing or contradictory historical decisions and invalid references block before any formal write. Inspect `formal-projection-validation.json` for a successful preflight.

## Upstream correction

If a candidate or reviewer finds a missing/conflicting Requirement, record the source block and affected Requirement/Task. Fix it through the existing Chapter 5 semantic decision and Chapter 3 projection/candidate preview path, then re-check affected Chapter 4/5 surfaces. This Skill never edits the upstream semantic authority itself.
