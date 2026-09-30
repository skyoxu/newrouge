# Capability and MVG Planning Acceptance

Requirement: `REQ-CAPABILITY-MVG-SKILLS-001`

Status: implementation repaired; current-revision production acceptance is tracked on PR #251. The earlier production run below predates the six-defect audit and is not proof of those repairs.

This document maps the implementation to AC01-AC26 and records the controlled real-model acceptance required by the requirement. It does not claim gameplay runtime acceptance, human playtest approval, or KCP publication.

## Historical production-model acceptance (before audit repair)

GitHub Actions run: `Planning Production Acceptance #36734641027`

Result: **PASS**

The run used the isolated Harbor Relay fixture, with non-contiguous Taskmaster IDs `7` and `42`, real Chapter 5 readiness, no pre-existing derived Capability answer, and a real model-backed production path.

Observed evidence from the run:

- Backend: `copilot-cli` because `OPENAI_API_KEY` was not available in the runner.
- Actual accepted candidate model: `gpt-6-luna`.
- Independent review model: `gpt-6-luna`.
- Valid candidate count: exactly `3`.
- Selected winner: `candidate-2`.
- Candidate generation uses fresh no-tools isolated invocations; mismatched actual-model attempts are discarded before a candidate can become valid.
- Capability winner was ID-aligned and applied inside the isolated fixture.
- Chapter 5 readiness remained valid for both fixture tasks after Capability application.
- MVG Planning was invoked independently against the applied Capability file; it did not call Capability generation.
- MVG proposal SHA-256: `sha256:c63c2921d949c374ec05bca6c394fa12860d721323f17ec35250edf5e995ce51`.
- MVG validation returned `formal_applicable=true`.
- The production acceptance intentionally did not apply the MVG manifest and reports `runtime_verified=false`.
- Model request billing amount was not exposed by the backend, so no monetary cost is invented. Copilot request count was not observable as an exact model-request count and is reported accordingly.
- The complete acceptance evidence artifact was uploaded as `planning-production-acceptance-36734641027`.

## AC01-AC26

| AC | Result | Evidence |
| --- | --- | --- |
| AC01 Chapter 3-5 without new Capability | PASS | Harbor fixture builds Source Blocks, reviewed Requirements, task triplet and real Chapter 5 readiness before any Capability file exists. |
| AC02 partial Chapter 5 scope | PASS | Both prepare entrypoints derive the full current source round and reject missing task sinks; valid non-task sinks remain supported without requiring unrelated historical tasks. Production-entry fixtures cover omission of task 42 despite task 7 being ready. |
| AC03 three-process isolation | PASS | Isolated runner contract requires workspace-only input, fresh session per invocation, no outside reads and `model_tools=[]`; real acceptance produced three valid candidates under that contract. |
| AC04 large GDD / complete accounting | PASS | Capability input batching accounts for every Source Block and Requirement, records batch hashes, never truncates an oversized block, and requires a continuation-capable runner for multiple batches. Portability tests cover non-six dynamic batches and oversized input. |
| AC05 candidate failure / no valid winner | PASS | Candidate generation has bounded retries and budgets; invalid candidates stay attempts only. Review supports `no_valid_winner` and never fabricates a winner. |
| AC06 independent anonymous review | PASS | A fourth fresh runner invocation receives reproducibly shuffled aliases A/B/C, not original candidate order; one complete winner is selected, with bounded evidence-based corrections only. |
| AC07 Capability apply / later add identity | PASS | Stable exact-membership IDs are reused; changed membership requires explicit alignment. Apply only updates derived Capability refs/topology and guarded readiness rebind. Task-intent portability tests prove regrouping does not change mature intent ID/key. |
| AC08 upstream omission / multi-membership | PASS | Candidate validation requires every active delivery Requirement to be grouped or explicitly ungrouped, requires rationale for multi-membership, and reports upstream gaps rather than mutating Requirements. |
| AC09 MVG independent execution | PASS | `plan_mvg.py` consumes an explicit Capability path and has no Capability-generation call. The real acceptance invoked MVG only after Capability had already been applied. |
| AC10 flow many-to-many / coverage | PASS | MVG prompt and validation allow flows across multiple Capabilities and Capabilities across multiple flows, with Requirement coverage, non-journey obligations and explicit gaps; one-Capability-one-flow conversion is forbidden. |
| AC11 initial / cumulative planning | PASS | Initial candidate is validated with the normal manifest validator; existing manifests are converted to guarded add/update/retain/retire deltas and preserve old obligations by default. |
| AC12 missing task/contract/test | PASS | Unknown task/capability/requirement refs and nonexistent verified entrypoints block; complete planned entrypoints/tests remain implementation obligations, genuine unresolved upstream gaps remain draft, and tests are never promoted to passed by planning. |
| AC13 evidence truthfulness | PASS | Planning input includes referenced production/test/contract files; evidence levels remain distinct; plan validation does not create `runtime_verified`. Real acceptance explicitly reports `runtime_verified=false`. |
| AC14 refresh layering | PASS | Task/status/reference edits do not automatically rerun Capability/MVG; source/semantic changes are handled by explicit impact/replanning paths and runtime revision changes invalidate runtime evidence separately. |
| AC15 interruption/drift/retry | PASS | Capability apply journals all target and readiness projections before writing, blocks consumers while pending, resumes process termination, and rejects subsequent external target edits. MVG validates all original authority/bundle/baseline identities before any manifest write. Existing run IDs cannot reset budgets by prepare. |
| AC16 UI/publication separation | PASS | Formal Capability writes semantic-topology artifacts only; Workspace/Main and planned/runtime publication boundaries remain owned by existing topology/KCP consumers. Planning does not publish KCP or claim runtime success. |
| AC17 cross-project | PASS | Harbor Relay acceptance fixture uses a different game domain and non-contiguous IDs 7/42, with no newrouge task-number semantics. |
| AC18 post-apply readiness rebind | PASS | Capability apply performs capability-only fingerprint rebind and blocks when anything beyond Capability refs changes. Real production acceptance verifies both fixture tasks remain current/READY. |
| AC19 upstream semantic correction | PASS | Skill records gaps and routes Requirement corrections through Chapter 5 finding -> Chapter 3 formal projection -> task preview -> affected Chapter 4/5 recheck; planners do not rewrite upstream semantic authority. |
| AC20 planned entrypoint before Chapter 6 | PASS | Planned entrypoint requires real owner task, target path/symbol, inputs, state, assertions and implementation acceptance; nonexistent files cannot be marked `existing_verified`. |
| AC21 old/new consumer migration | PASS | Portability acceptance documents legacy replay isolation and current consumers; semantic topology, Chapter 5, task normalizer and Knowledge continue to consume the current relation shape without frozen replay overriding it. |
| AC22 blinding / review order | PASS | Prior derived `capability_ref(s)/id/title` fields are scrubbed from analysis inputs; authoritative source classification remains visible. Anonymous review order is hash-seeded and reproducible while the alias mapping stays outside the review workspace. |
| AC23 budget exhaustion / recovery | PASS | Candidate/review retry limits, per-candidate and total active-time budgets, observable request limit, process-tree timeout termination and persisted budget state are implemented. When exact request/cost accounting is unavailable it is reported unavailable instead of invented. |
| AC24 final handoff after MVG apply | PASS | Both Chapter 6 entrypoints consume the durable applied trace, require current obligation bindings, and cannot bypass by omitting the flag. The lane consumes its bound real milestone handoff; the handoff itself hashes the applied manifest. An ordinary binding resolves applicability and current readiness without a fake milestone handoff. |
| AC25 source-authored Capability classification | PASS | Authoritative source text is copied unchanged into the blinded bundle and classification signals are retained; only old derived answers are removed. |
| AC26 real MVG production path | PASS | Run #36734641027 consumed the actual selected/applied Capability, generated a real MVG proposal with Copilot CLI, and passed the existing plan/formal validator. No mock/preloaded manifest substituted for this chain. |

## Six-defect audit repair verification

`scripts/python/tests/test_planning_audit_repair.py` reproduces the original six failures and verifies their corrected production entrypoints. Additional cases cover false membership, missing/stale independent review, source/task/master/contract/test/readiness/manifest drift, ordinary versus milestone applicability, omitted handoff flags, manifest-bound handoff staleness, interruption during topology/readiness writes, idempotent resume and preservation of subsequent user edits.

The final three-document regression set contains 211 passing tests, including 23 focused repair tests and both isolated runner contracts. MVG generation includes the bound Taskmaster master table and authoritative statuses in every fresh invocation; bounded full-output corrections preserve status-derived blockers and class-name test selectors. Planned implementation and missing runtime evidence are not upstream gaps or Taskmaster status changes. Capability generation binds the common actual model only from an accepted candidate's real receipt; failed invocations cannot pin the configured auto-routing label as an actual model, and missing receipts or later different-model candidates remain rejected.

The Copilot adapter also reads documented `assistant.usage` and executed `session.shutdown.modelMetrics` evidence. A selected/configured model alone cannot prove execution, and multiple executed models in one invocation are rejected. CI acceptance artifacts include the workflow attempt number to retain separate attempts. Event authority: https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md.

The clean CRLF checkout passes `validate_semantic_topology.py --worktree --require-available` for 139 source blocks and 127 active Requirements. Both Git and worktree topology checks are in the hard bundle. The current production workflow includes an independent isolated MVG semantic reviewer before formal validation. Read its current-revision outcome from PR #251 and retained Actions artifacts; the historical run above is not new repair evidence.

## Implementation surfaces

- `.agents/skills/plan-capabilities/SKILL.md`
- `.agents/skills/plan-mvg/SKILL.md`
- `scripts/python/plan_capabilities.py`
- `scripts/python/plan_mvg.py`
- `scripts/python/_planning_skill_common.py`
- `scripts/python/openai_isolated_model_runner.py`
- `scripts/python/copilot_isolated_model_runner.py`
- `scripts/python/planning_acceptance_fixture.py`
- `scripts/python/run_planning_production_acceptance.py`
- `.github/workflows/planning-production-acceptance.yml`

## Completion boundary

This requirement is complete when the current PR HEAD keeps the production acceptance workflow and the repository gates green. Planning completion does not imply gameplay runtime verification, human acceptance, or merge to `main`.
