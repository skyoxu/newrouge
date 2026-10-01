# Capability and MVG Planning Acceptance

Requirement: `REQ-CAPABILITY-MVG-SKILLS-001`

Status: **complete**. The merged-main follow-up implementation `741badf84fcf8fe8bd9c664fbef8a1ff328a7b21` passes Windows Quality, Windows Smoke, MVG Integration and real production-model acceptance. PR #253 closes the one P1 and four P2 defects found against main `75346cbda0ce96ed801fe05242ef7f04e2af056c`. Historical acceptance records below remain scoped to their original revisions.

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

## Audit-repair production-model acceptance

Code revision: `5271f65ef7c906f224f39aa50e41183b50e6b4de`.

Production run: [36765025379](https://github.com/skyoxu/newrouge/actions/runs/36765025379), **PASS**.

Artifact: `planning-production-acceptance-36765025379-attempt-1`, ID `11120062665`, digest `sha256:06c785eef50f91cd0d9fc91385c8ea2c35e4f889e46601ca930a440ef2464dd0`.

- Exactly three valid fresh no-tools candidates; all use actual model `mai-code-1.1-flash`, each accepted on its first attempt. Anonymous review uses the same actual model and selects `candidate-3`.
- Capability apply preserves current Chapter 5 readiness for real fixture Tasks `7` and `42`.
- Independently generated MVG proposal SHA-256: `sha256:14390707885b897d1362522b15fb169442af796a63804ee3f128e679aa824186`.
- A separate fresh semantic reviewer approves both delivery Requirements and the cross-system player journey with zero findings. Review file SHA-256: `sha256:7f99110ae84f4bf43106290f6c09ed4d4e5b6f248d83daea86b07c947ce66c36`.
- Deterministic final validation returns `formal_applicable=true`, zero errors and zero unresolved gaps.
- Six fresh invocation-owned model-event evidence records are retained. The accepted candidate model identities and both MVG file hashes were verified from the downloaded artifact.
- Acceptance intentionally does not apply the MVG manifest and reports `runtime_verified=false`; formal apply and final obligation bindings are exercised by the deterministic repair regressions.

Repository gates for the same code revision: [Windows Quality](https://github.com/skyoxu/newrouge/actions/runs/36765023945) **PASS**, [Windows Smoke](https://github.com/skyoxu/newrouge/actions/runs/36765023968) **PASS**, [MVG Integration](https://github.com/skyoxu/newrouge/actions/runs/36765023912) **PASS**. This completion record changes documentation only; executable implementation and business authorities remain at the verified revision.

## AC01-AC26

| AC | Result | Evidence |
| --- | --- | --- |
| AC01 Chapter 3-5 without new Capability | PASS | Harbor fixture builds Source Blocks, reviewed Requirements, task triplet and real Chapter 5 readiness before any Capability file exists. |
| AC02 partial Chapter 5 scope | PASS | Both prepare entrypoints derive the full current source round and reject missing task sinks; valid non-task sinks remain supported without requiring unrelated historical tasks. Production-entry fixtures cover omission of task 42 despite task 7 being ready. |
| AC03 three-process isolation | PASS | Isolated runner contract requires workspace-only input, fresh session per invocation, no outside reads and `model_tools=[]`; real acceptance produced three valid candidates under that contract. |
| AC04 large GDD / complete accounting | PASS | Capability input batching accounts for every Source Block and Requirement, records batch hashes, never truncates an oversized block, and requires a continuation-capable runner for multiple batches. Portability tests cover non-six dynamic batches and oversized input. |
| AC05 candidate failure / no valid winner | PASS | Candidate generation has bounded retries and budgets; invalid candidates stay attempts only. Review supports `no_valid_winner` and never fabricates a winner. |
| AC06 independent anonymous review | PASS | A fourth fresh same-actual-model invocation receives reproducibly shuffled aliases A/B/C; complete findings/comparison and resolvable source refs are required. Selected/no-winner reports and bounded corrections are identity-bound and reused without another call; corrupt evidence blocks reuse/apply. |
| AC07 Capability apply / later add identity | PASS | Stable exact-membership IDs are reused; changed membership requires explicit alignment. Apply only updates derived Capability refs/topology and guarded readiness rebind. Task-intent portability tests prove regrouping does not change mature intent ID/key. |
| AC08 upstream omission / multi-membership | PASS | Candidate validation requires every active delivery Requirement to be grouped or explicitly ungrouped, requires rationale for multi-membership, and reports upstream gaps rather than mutating Requirements. |
| AC09 MVG independent execution | PASS | `plan_mvg.py` consumes an explicit Capability path and has no Capability-generation call. The real acceptance invoked MVG only after Capability had already been applied. |
| AC10 flow many-to-many / coverage | PASS | MVG prompt and validation allow flows across multiple Capabilities and Capabilities across multiple flows, with Requirement coverage, non-journey obligations and explicit gaps; one-Capability-one-flow conversion is forbidden. |
| AC11 initial / cumulative planning | PASS | Initial candidate is validated with the normal manifest validator; existing manifests are converted to guarded add/update/retain/retire deltas and preserve old obligations by default. |
| AC12 missing task/contract/test | PASS | Unknown task/capability/requirement refs and nonexistent verified entrypoints block; complete planned entrypoints/tests remain implementation obligations, genuine unresolved upstream gaps remain draft, and tests are never promoted to passed by planning. |
| AC13 evidence truthfulness | PASS | Every claimed existing source/contract/test/entrypoint/verification/authority must be readable and hash-bound in prepared input, including explicit additional refs and baseline dependencies. Missing copies/drift block formal apply. Planned paths remain legal and never create `runtime_verified`. |
| AC14 refresh layering | PASS | Task/status/reference edits do not automatically rerun Capability/MVG; source/semantic changes are handled by explicit impact/replanning paths and runtime revision changes invalidate runtime evidence separately. |
| AC15 interruption/drift/retry | PASS | Capability apply journals all target and readiness projections before writing, blocks consumers while pending, resumes process termination, and rejects subsequent external target edits. MVG validates all original authority/bundle/baseline identities before any manifest write. Existing run IDs cannot reset budgets by prepare. |
| AC16 UI/publication separation | PASS | Formal Capability writes semantic-topology artifacts only; Workspace/Main and planned/runtime publication boundaries remain owned by existing topology/KCP consumers. Planning does not publish KCP or claim runtime success. |
| AC17 cross-project | PASS | Harbor Relay acceptance fixture uses a different game domain and non-contiguous IDs 7/42, with no newrouge task-number semantics. |
| AC18 post-apply readiness rebind | PASS | Capability apply performs capability-only fingerprint rebind and blocks when anything beyond Capability refs changes. Real production acceptance verifies both fixture tasks remain current/READY. |
| AC19 upstream semantic correction | PASS | Skill records gaps and routes Requirement corrections through Chapter 5 finding -> Chapter 3 formal projection -> task preview -> affected Chapter 4/5 recheck; planners do not rewrite upstream semantic authority. |
| AC20 planned entrypoint before Chapter 6 | PASS | Planned entrypoint requires real owner task, target path/symbol, inputs, state, assertions and implementation acceptance; nonexistent files cannot be marked `existing_verified`. |
| AC21 old/new consumer migration | PASS | Portability acceptance documents legacy replay isolation and current consumers; semantic topology, Chapter 5, task normalizer and Knowledge continue to consume the current relation shape without frozen replay overriding it. |
| AC22 blinding / review order | PASS | Prior derived `capability_ref(s)/id/title` fields are scrubbed from analysis inputs; authoritative source classification remains visible. Anonymous review order is hash-seeded and reproducible while the alias mapping stays outside the review workspace. |
| AC23 budget exhaustion / recovery | PASS | Durable attempts and active-time/request reservations precede candidate/review calls. Caught interruption terminates/reaps the runner and settles observed time; hard loss retains unknown reservations and consumed attempts. Limits survive resume; valid review reuse costs no new call. Unavailable request/billing counts remain explicitly unavailable. |
| AC24 final handoff after MVG apply | PASS | Both Chapter 6 entrypoints consume current durable applied obligations and require real milestone or ordinary readiness bindings. Manifest/plan/handoff hashes share runtime newline normalization; Git LF/CRLF preserves binding, real content edits block. Snapshot/readiness/apply-journal checks remain byte-exact. |
| AC25 source-authored Capability classification | PASS | Authoritative source text is copied unchanged into the blinded bundle and classification signals are retained; only old derived answers are removed. |
| AC26 real MVG production path | PASS | Audit-repair run #36765025379 consumes the actual selected/applied Capability, independently generates a real MVG proposal, performs a separate fresh semantic review and passes deterministic/formal validation. No mock/preloaded manifest substitutes for this chain. |

## Six-defect audit repair verification

`scripts/python/tests/test_planning_audit_repair.py` reproduces the original six failures and verifies their corrected production entrypoints. Additional cases cover false membership, missing/stale independent review, source/task/master/contract/test/readiness/manifest drift, ordinary versus milestone applicability, omitted handoff flags, manifest-bound handoff staleness, interruption during topology/readiness writes, idempotent resume and preservation of subsequent user edits.

The final three-document regression set contains 215 passing tests, including 23 focused repair tests and both isolated runner contracts. MVG generation includes the bound Taskmaster master table and authoritative statuses in every fresh invocation; bounded full-output corrections preserve status-derived blockers and class-name test selectors. Planned implementation and missing runtime evidence are not upstream gaps or Taskmaster status changes. Capability generation binds the common actual model only from an accepted candidate's real receipt; failed invocations cannot pin the configured auto-routing label as an actual model, and missing receipts or later different-model candidates remain rejected.

The Copilot adapter also reads documented `assistant.usage` and executed `session.shutdown.modelMetrics` evidence. A selected/configured model alone cannot prove execution, and multiple executed models in one invocation are rejected. CI acceptance artifacts include the workflow attempt number to retain separate attempts. When CLI stdout omits identity, the adapter reads only this invocation's fresh private session event log before cleanup, retains model-event diagnostics without message/reasoning text, and rejects multiple session logs. Cached/selected model names alone cannot prove execution. Runtime cleanup also covers timeouts. Event authority: https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md; session-log authority: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference.

The clean CRLF checkout passes `validate_semantic_topology.py --worktree --require-available` for 139 source blocks and 127 active Requirements. Both Git and worktree topology checks are in the hard bundle. The repaired production workflow's independent isolated MVG semantic reviewer and final validator passed in run #36765025379; the historical run above is not new repair evidence.

## Merged-main audit follow-up

Verified implementation: `741badf84fcf8fe8bd9c664fbef8a1ff328a7b21`, [PR #253](https://github.com/skyoxu/newrouge/pull/253).

Production run [36819370222](https://github.com/skyoxu/newrouge/actions/runs/36819370222): **PASS**. Artifact `planning-production-acceptance-36819370222-attempt-1`, ID `11142329584`, digest `sha256:5477067f5a0e3c78a7455a83b53639d40eb16d982c49778baffe2728f66cb7bc`.

- Three valid fresh no-tools candidates use actual model `gpt-6-luna`; accepted attempts are 1/1/2. The independent anonymous review uses the same actual model, selects alias B / `candidate-3`, and applies bounded corrections. The downloaded report, all candidate hashes, runner/receipt identities and corrected candidate pass replay validation without another model call.
- Capability apply preserves real Chapter 5 READY evidence for fixture Tasks 7/42. Exact model-request count and billing remain unavailable rather than invented; observed active time and consumed runner attempts are retained separately.
- Independent MVG generation uses three bounded attempts. Proposal file SHA-256 is `sha256:0812036f17906d8d7642efc0a0c40f687ea534e8c16dc000c982678e2f731fe6`. A separate fresh reviewer using `mai-code-1.1-flash` approves with zero findings; review SHA-256 is `sha256:ad489c85f7f3bbe6d823ea36a8b1a1f0fbadc8820c1909780596fb49e6c9afb2`. Downloaded identity/accounting replay returns zero errors.
- Final deterministic validation returns `formal_applicable=true`, zero errors and zero unresolved gaps. This controlled acceptance does not apply the MVG manifest and records `runtime_verified=false`; apply/obligation recovery is tested by production-entry deterministic fixtures.

Same-revision gates: [Windows Quality](https://github.com/skyoxu/newrouge/actions/runs/36819370219) **PASS** (938 Python tests, hard bundle 0/25 failures), [Windows Smoke](https://github.com/skyoxu/newrouge/actions/runs/36819370226) **PASS**, [MVG Integration](https://github.com/skyoxu/newrouge/actions/runs/36819370213) **PASS**. Local three-document core: 232 passing tests, including 16 new main-audit tests and a source-to-reviewed-semantics fixture regression.

Earlier blocked model evidence is retained in the execution plan with artifact IDs and digests. The specific repairs resolve qualified evidence IDs and clarify the isolated fictional fixture's payload origin/result/retry source semantics. No blocked semantic reviewer is rerun to seek a different approval; no test/gate or budget is disabled/reset. The newrouge business GDD, source declarations, Taskmaster IDs/statuses and game code are unchanged.

The current repair addresses five production-boundary gaps, with counterexamples and positive recovery paths in `scripts/python/tests/test_planning_main_audit_fixes.py`:

| Finding | Priority | Corrected behavior | Requirement coverage |
| --- | --- | --- | --- |
| F01 existing verification outside prepared input | P1 | Every claimed existing source/contract/test/entrypoint/verification/authority must be copied and hash-bound at prepare. Existing baseline dependencies are copied automatically; repeated `--evidence-ref` prepares additional files. Missing copies or post-review drift block formal apply. Planned absent paths remain legal. | AC13, AC15 |
| F02 lost candidate/review attempts on interruption | P2 | Durable attempts and budget reservations precede invocation. Caught interruption settles observed time; hard process loss preserves conservative reservations. Request reservations survive unavailable receipts without being reported as observed requests or billing. | AC23 |
| F03 repeated valid review consumes another call | P2 | Valid selected/no-winner reports are reused with exact candidate, analysis, prompt, mapping, runner, receipt and correction identities. Corruption blocks instead of requesting another approval. Apply rechecks the bound result. | AC06, AC15, AC23 |
| F04 Git line endings invalidate final obligations | P2 | Manifest, milestone-plan and handoff content identities share the runtime runner's LF normalization. LF/CRLF checkout conversion passes; actual content changes block. Snapshot/readiness/journal bytes retain strict checks. | AC24; portability AC11 |
| F05 incomplete review report can select | P2 | Require all five findings arrays, nonempty comparative tradeoffs/rationale, corrections and resolvable authoritative evidence refs, including correction refs. Empty findings arrays are accepted. | AC06 |

Local focused and three-document regression results are recorded in the execution plan. New regressions run in both the hard gate bundle and the real-model workflow's deterministic smoke stage. Mocked runner receipts in unit fixtures prove deterministic consumers only; the separate CI chain is required for production-model evidence.

## Alignment and review-publication re-audit repair

Baseline: merged main `5bc0e670f8ffca520f4fb87b4f42dd8fe38101cf` (#253). The controlling three documents are unchanged. The re-audit identified R01 (P1, ambiguous identical-member nodes could collide on one stable ID) and R02 (P2, loss between final verdict and metadata publication could block Capability recovery or rerun MVG review).

| Finding | Repaired boundary | Regression evidence |
| --- | --- | --- |
| R01 / AC07 | Auto-reuse requires one candidate and one historical membership match. Reviewed overrides must name known, unique decisions; candidate stable IDs must be unique and historical retain/retire choices consistent. Apply validates the complete projected topology before creating a formal-write journal. | Same-member ambiguity, colliding/unknown/duplicate overrides and invalid topology block; explicit historical retention/retirement with legal multi-membership applies successfully. |
| R02 / AC15, AC23 | Persist verdict, receipt, private mapping and corrections before multi-file publication. Resume recorded writes without another reviewer or budget reset; unknown target/checkpoint edits block. MVG keeps separate immutable completed records for revised proposals and shares the original three-invocation limit. | Publication interruptions before/after final report, metadata, corrections and checkpoint completion recover; no-winner, blocked verdict, malformed accounting and draft boundaries persist; a pending record cannot be bypassed by revising a proposal. |

The initial ten-test run fails on unmodified merged main (six failures, three errors). Two additional counterexamples reproduce loss after a completed attempt but before publication exists; recovery now binds the original output/metadata and reuses it without another invocation. Publication status participates in the checkpoint checksum, so a forged pending marker cannot authorize restoration over subsequent target deletion. All current regressions run in the hard gate bundle and deterministic production smoke. The isolated acceptance fixture's topology manifest uses the real production schema/identity fields without changing its contract or source obligations. Platform and fresh real-model evidence are recorded in `execution-plans/2026-10-01-planning-alignment-review-recovery.md` when CI completes.

The strengthened implementation passes 30 new/274 core tests. Production run 36845534237 preserves one blocked independent verdict: the generated plan omitted the explicit source-named service-to-terminal interaction and its test assertion. Artifact 11152719135, digest `sha256:08f9ae256ad4a62ab34b1728a7bcfc1b88a718ddb74f77ce3f58fb7fc0e520bc`, retains that evidence. The generator now preserves named sending/receiving systems and real task ownership even when roles share a task, and explicitly carries the same interaction into planned test scenarios. The source, real contract, reviewer and budgets are unchanged; approval requires a fresh materially corrected chain.

Verified implementation before the final identity-copy repair: `a67a048e88599268fb181a0422785114d02c5a14`, [PR #255](https://github.com/skyoxu/newrouge/pull/255). [Production 36847620516](https://github.com/skyoxu/newrouge/actions/runs/36847620516) **PASS**, artifact `11154531435`, digest `sha256:02bcd1ebb81a40510f7b94e49b1101c76b4cededb17f4e370450e39b13caad73`. Three fresh Capability candidates and their anonymous review use actual `gpt-6-luna`, selecting `candidate-1`; Tasks 7/42 remain READY after apply. MVG generation uses two bounded attempts, followed by one separate fresh `gpt-6-luna` review: approved, zero errors/gaps, `formal_applicable=true`. No MVG manifest is applied and `runtime_verified=false`. Downloaded review/publication consumer replay succeeds without another model invocation, budget change or completed-publication write; it does not assert original-workspace freshness replay.

Same-implementation [Windows Quality](https://github.com/skyoxu/newrouge/actions/runs/36847620638) **PASS** (968 Python tests, hard bundle 0/25 failures), [Windows Smoke](https://github.com/skyoxu/newrouge/actions/runs/36847620738) **PASS**, [MVG Integration](https://github.com/skyoxu/newrouge/actions/runs/36847620559) **PASS**. Production deterministic smoke has 103 passing tests; local core has 274. Generator run 36846454889/artifact 11154230470 retains all three wrong-field outputs; the prompt now names literal `rationale` and explains the `coverage_rationale_missing` error label. No validator accepts a new alias and no attempt budget is extended or reset. The execution plan preserves both specific blocked cases and their digests.

Documentation-only closeout `75eca5ce` triggers another fresh production chain. Run `36849699351` correctly rejects an approved semantic report whose proposal hash omits two characters; artifact `11154659573`, digest `sha256:973041ef538f25ceb8a9b18c9286f94fe5e9b1b6e63abf119c9a979138bfd022`, preserves the raw report and single consumed review. The reviewer prompt now requires verbatim copying of both host-supplied identities. Two negative identity regressions preserve the invalid report and consumed budget at publication/completed-attempt recovery boundaries without another invocation. Validation remains strict; no identity is repaired after review. Final local recovery/core counts are 32/276. Final-head CI evidence is recorded in PR #255 and the delivery report.

Controlled CI acceptance requests one fixed Copilot model (default `gpt-6-luna`, overridable with `SC_PLANNING_COPILOT_MODEL`). Public runner `auto` support remains available. Auto-routing run 36851834049/artifact 11155669475 exhausts the unchanged candidate budget because its actual models differ; that bounded stop is retained rather than rerun. Actual receipt identity still decides whether all accepted candidates/reviewer use the same model. The acceptance-only setting avoids relying on random routing convergence and does not relax identity, semantic or budget gates.

## Implementation surfaces

- `.agents/skills/plan-capabilities/SKILL.md`
- `.agents/skills/plan-mvg/SKILL.md`
- `scripts/python/plan_capabilities.py`
- `scripts/python/plan_mvg.py`
- `scripts/python/_planning_skill_common.py`
- `scripts/python/_capability_alignment.py`
- `scripts/python/_planning_review_publication.py`
- `scripts/python/openai_isolated_model_runner.py`
- `scripts/python/copilot_isolated_model_runner.py`
- `scripts/python/planning_acceptance_fixture.py`
- `scripts/python/run_planning_production_acceptance.py`
- `.github/workflows/planning-production-acceptance.yml`

## Completion boundary

R01/R02 and the final identity-copy prompt repair are implemented. The earlier recorded revision passes all four workflows; the final-head workflows must pass before merge. Final CI is recorded in PR #255 without another documentation-only synchronization. Planning completion does not imply gameplay runtime verification, human acceptance, or merge to `main`.
