---
name: plan-capabilities
description: Generate and apply post-Chapter-5 Capability grouping from authoritative GDD/Requirement evidence using three genuinely isolated same-model candidates and an independent anonymous review. Use only after the explicit GDD-related Chapter 3-5 scope is ready.
---

# Plan Capabilities

## Role

Create the derived Capability organization after the relevant Chapter 3-5 scope has converged. Capability is navigation and grouping only; it never owns Taskmaster status and never edits Requirement statements.

## Hard boundaries

- Authoritative inputs are the cumulative source set, full Source Block Ledger, reviewed Requirements, task/Acceptance/contract semantics, and explicit Chapter 5 readiness scope.
- The three initial candidates must use fresh sessions, the same model, the same prompt bytes, and the same blinded analysis bundle.
- Formal generation requires an isolation runner that reports workspace-only reads and no outside-workspace access. If no such runner exists, stop after prepare/validation; never emulate independence in one chat.
- Old formal Capability answers and task `capability_refs` are excluded from the candidate analysis view. Capability/module organization that is present in the authoritative GDD remains visible.
- The review is a fourth fresh isolated session. It sees anonymous A/B/C candidates in a reproducible shuffled order and never sees the private mapping.
- Do not merge the three by default. A valid outcome may be `no_valid_winner`.
- Applying Capability may update only derived Capability artifacts, task `capability_refs`, Capability topology edges, topology hashes, and a capability-only Chapter 5 fingerprint rebind. It must not change task IDs, statuses, Acceptance, subtasks, Requirement text, or task intent identity.

## Primary workflow

1. Prepare a blinded, hash-bound analysis bundle:
   `py -3 scripts/python/plan_capabilities.py prepare --run-id <id> --task-id <id> [--task-id <id> ...]`
2. Inspect `logs/ci/capability-planning/<id>/analysis-input/analysis-index.json`. A draft may use `--allow-unready-draft`, but formal candidate generation refuses an unready scope.
   Prepare checks every task sink of the current ledger source round, including active Requirement mappings and legitimate non-task sinks. A single ready task cannot hide another task of that round. Unrelated unchanged historical sources do not become an unconditional readiness task list; the model input remains cumulative.
3. Generate three candidates through the configured isolation runner:
   `py -3 scripts/python/dev_cli.py plan-capabilities --stage generate --run-id <id>`
4. Run independent anonymous review:
   `py -3 scripts/python/dev_cli.py plan-capabilities --stage review --run-id <id>`
5. Preview historical ID alignment:
   `py -3 scripts/python/plan_capabilities.py preview-alignment --run-id <id>`
   Exact Requirement-membership matches reuse IDs automatically. Any changed membership is unresolved until an explicit reviewed alignment decision is supplied.
6. Apply only after review/alignment:
   `py -3 scripts/python/plan_capabilities.py apply --run-id <id> --alignment-override <reviewed.json> --confirm`
7. Validate semantic topology and inspect the per-task Chapter 5 rebind results. Any fingerprint change beyond `capability_refs` blocks automatic rebind and blocks formal MVG planning until the affected Chapter 5 task is reconciled normally.

## Isolation runner contract

Default verified runner: `scripts/python/openai_isolated_model_runner.py`. It serializes only UTF-8 files inside the prepared candidate/review workspace into a text-only OpenAI API request and exposes no model tools. Set `OPENAI_API_KEY` and optionally `SC_OPENAI_MODEL` / `OPENAI_MODEL`. The stable `dev_cli plan-capabilities` command uses this runner by default.

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

Run state is durable under `logs/ci/capability-planning/<run-id>/`. Re-run the incomplete stage only. Existing valid candidates are evidence and should not be discarded just because a later stage failed. Candidate retries and total active-time budgets are operator-configured by the runner; never claim model-request counts or monetary cost when the runner cannot observe them.

Persist each candidate/review attempt and its active-time/request reservation before invocation. A caught interruption settles observed active time; process loss keeps the unknown invocation's reservation and consumed attempt. Reservations constrain later calls but are not observed cost, billing or paused wall time. Never reset them on resume.

Re-running review reuses a valid report bound to the original analysis bundle, all three candidate hashes, prompt, anonymous mapping, runner and execution receipt. Preserve `no_valid_winner` as well as a selected winner. A changed report, input, receipt or corrected candidate blocks reuse and apply; do not invoke another reviewer to bypass it. Require all five findings arrays, comparative tradeoffs, rationale, corrections and resolvable authoritative evidence refs. Empty findings arrays are legal; missing findings fields are not.

Do not prepare over an existing run ID. Before apply, the complete formal projection and readiness rebind are persisted in `apply-journal.json`. A pending pointer blocks Chapter 5/6 consumers during incomplete writes. Resume by re-running the same `apply --confirm`; it accepts only original or journal-owned target bytes and unchanged authority inputs, preserves subsequent external edits, and never regenerates candidates/review/alignment. A completed apply is idempotent. Keep the run directory until recovery completes; do not delete the pending pointer to bypass the gate.

## Upstream correction

If a candidate or reviewer finds a missing/conflicting Requirement, record the source block and affected Requirement/Task. Fix it through the existing Chapter 5 semantic decision and Chapter 3 projection/candidate preview path, then re-check affected Chapter 4/5 surfaces. This Skill never edits the upstream semantic authority itself.
