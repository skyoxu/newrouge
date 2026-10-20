# Capability Planning branch review

Base: `1cfc506b1dc0992245cec42f467c45f6246d27e0` on `fix/capability-synthesis-input-integrity`.
Status: **Needs Fix for formal runner assurance**. The deterministic repairs below are verified; this is not a real-model acceptance receipt.

## Actual entry paths

The supplied Windows path maps to `scripts/python/dev_cli.py`. `plan-capabilities` is a CLI subcommand, not an HTTP request handler. Its path is `dev_cli -> dev_cli_builders -> plan_capabilities.py`.

The repository Knowledge page posts `action=capability` to `/api/knowledge/planning`. `_project_health_planning.run_job` invokes `plan_capabilities.py` directly through `invoke`, with the sequence `prepare -> generate -> review -> align -> apply`, then refreshes Knowledge. Both entry paths use the same planner and Codex runner, but the page does not pass through `dev_cli.py`.

## Reproduced and repaired

| Severity | Defect | Repair and evidence |
| --- | --- | --- |
| P1 | Review synthesis receives candidate-generation instructions. Staged review also asks for candidate drafts, conflicting with the review report contract. | Separate review synthesis instructions and validate every review draft with the existing review validator. A runner-level fake transport test consumes all evidence batches and produces the review report. |
| P2 | A batch correction retry appends new text after first-request preflight, then dispatches without measuring the new prompt and output schema. | Both Codex and OpenAI paths remeasure before request reservation/transport. Oversized correction tests prove only the first request is charged and dispatched. |
| P2 | Synthesis planning uses measured tokens but not actual analysis bytes. Token-light, byte-heavy outputs can fit the plan and then fail the transport despite being splittable. | Partition against both actual serialized analysis bytes and tokens. Preserve every analysis and continue to check the complete actual prompt before dispatch. |
| P2 | The public CLI cannot invoke `align`; it also depends on cwd and the Windows launcher for its child script, and its retry default differs from the page's direct planner default. | Expose and forward `align`; locate the child/default runner by absolute path and reuse the active Python interpreter. Align the default candidate retry limit at 2. A subprocess test launches the absolute entrypoint from an unrelated directory. |

The four initial regression counterexamples failed against the unmodified implementation before the corresponding repairs. Existing state budgets, model selection settings, source data, task authority, apply journal and formal Capability outputs were not rewritten.

## Remaining formal blockers

**P1: isolation and same-model receipts are asserted, not established.** `codex_isolated_model_runner._run_codex_request` and its non-batched path invoke `codex exec -s read-only -C <workspace>` without disabling command tools, MCP/plugins, inherited instructions or other input channels. Its description nevertheless asserts `model_tools=[]`, `filesystem_scope=workspace_only`, and `can_read_outside_workspace=false`. A working-directory flag and read-only write restrictions do not prove this contract. The descriptor and receipt also hardcode `codex-cli-default`, so the planner's equality check cannot establish the actual model identity across candidates/review.

This review did not silently replace the default backend, change authentication, invent a CLI-wide no-tools flag, or mark the runner isolated based on unit mocks. Closing this item requires a supported, verified text-only transport or a verified restricted runner for the installed Windows Codex version, plus actual model identity receipts and an adversarial outside-workspace-read check. The existing Skill already requires these properties. Official configuration reference: https://learn.chatgpt.com/docs/config-file/config-reference (`features.shell_tool`, MCP tool settings and project instruction configuration).

**Real execution evidence is unavailable here.** The clean pushed checkout has the canonical 139 Source Blocks and 127 Requirements, but does not contain `logs/ci/task-generation/source-manifest.v1.json`, the local source/semantic evidence copies, or `logs/ci/chapter5/readiness/`. No authenticated standalone Codex CLI is available in this environment. Consequently this review cannot reproduce the user's Windows model run, certify its semantic grouping quality, or synthesize missing Chapter 5 readiness. Missing evidence must be restored from the real local run or regenerated through its owning workflow, never replaced with a fabricated ready state.

## Algorithm assessment

Lossless authoritative input checks, independent source/task batches, measured-output replanning, complete prior drafts, anonymous comparative review and journaled apply are sensible mechanisms. The repairs address concrete request-admission and output-contract errors without changing the grouping criteria or targeting a fixed Capability count.

There is no deterministic optimal clustering algorithm here: the model infers grouping from outcomes, boundaries and evidence. Exact ID coverage proves accounting, not semantic understanding. Sequential cumulative synthesis can still exhibit order sensitivity and lose nuance when earlier analyses are represented only by a prior draft; final comparative review and a real-model acceptance sample remain necessary. These limitations are not claimed fixed by transport tests.

## Parameter and operation checks

- `prepare`: explicit task scope must cover the current source round and pass Chapter 5 readiness. `--allow-unready-draft` never authorizes formal generation.
- New default budgets: 80000 source-batch characters (owned by the planner), 2700 active seconds per candidate, 13500 shared active seconds, 96 shared model dispatches; candidate retries 2 and review retries 1. These are ceilings, not a promise of completion time. Persisted runs keep their existing budgets.
- `generate`, `review`, `align`: public CLI forwards the selected runner and `--timeout-sec` (2700 by default). The runner still uses the configured default model; no model switch was introduced.
- `preview-alignment` produces a deterministic preview. `align` obtains reviewed decisions. `apply` still requires `--confirm` and must consume the reviewed override when there are nontrivial alignment decisions.
- Reuse the same run ID for recovery; never prepare over an existing run.

Example on the Windows checkout after updating the branch and restoring real readiness evidence:

```powershell
py -3 C:/buildgame/newrouge/scripts/python/dev_cli.py plan-capabilities --stage align --run-id <existing-run-id>
py -3 C:/buildgame/newrouge/scripts/python/dev_cli.py plan-capabilities --stage apply --run-id <existing-run-id> --alignment-override logs/ci/capability-planning/<existing-run-id>/alignment-preview.json --confirm
```

These commands are operator examples, not evidence that the remaining runner blocker is closed. A new page click requests a new job; it is not equivalent to explicit CLI recovery of an existing run.

## Verification

- Targeted regression: **206 passed, 1 skipped, 31 deselected; 14 subtests passed**. `regression.xml` and `regression.log` are adjacent evidence files. The skipped case depends on an unpushed Windows real-model failure artifact.
- Coverage includes Capability input integrity, staged synthesis, candidate/incumbent contracts, CLI dispatch from another cwd, OpenAI/Copilot shared helpers, Knowledge HTTP behavior, the mocked Capability-to-MVG consumer chain, and Capability review recovery.
- The final selection deliberately excludes tests named `test_mvg_*`. An earlier unmodified-branch run had 14 failures in MVG review recovery: its `prepared_mvg` fixture lacks protocol-required `requirement_evidence` and `requirement_verification`, causing validation to stop before review. This is a pre-existing adjacent fixture issue, not a passing test or a production validator relaxed by this patch.
- `git diff --check` passes.
- No real model requests, Windows execution, engine runs, or formal Capability apply were performed on the user's project.
