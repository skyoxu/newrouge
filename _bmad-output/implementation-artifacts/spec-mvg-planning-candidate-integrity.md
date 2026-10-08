---
title: 'MVG Planning Candidate Integrity'
type: 'bugfix'
created: '2026-10-08'
status: 'in-review'
baseline_commit: '7cce922514f6b7bce12e70f688d1da0445247858'
review_loop_iteration: 0
context:
  - '{project-root}/.agents/skills/plan-mvg/SKILL.md'
  - '{project-root}/workflow.md'
  - '{project-root}/docs/workflows/mvg-integration-acceptance.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The page-driven MVG workflow can reuse a job tied to an older Capability, reject a valid incumbent because it is projected outside the frozen manifest scope, and discard valid candidates on retry. Review, candidate validity, and cumulative-range semantics also have consistency gaps.

**Approach:** Make each run explicitly bound to its selected Capability identity and define existing-manifest scope as a reviewed cumulative boundary. Keep candidate sets independent and compare complete sets, while making incumbent projection, resume, review-to-proposal accounting, and apply gates agree on the same frozen inputs.

## Boundaries & Constraints

**Always:** Capability remains the sole Capability SSoT; GDD/Requirements remain semantic authority and tasks/tests/contracts are evidence. Keep three isolated complete candidates, whole-set LLM selection with the current MVG eligible as incumbent when valid, independent semantic review, deterministic validation, guarded cumulative apply, default environment model, and local-only derived results. Preserve existing user work. Use regression tests before implementation.

**Ask First:** None. Existing frozen manifest scope remains the cumulative scope for this run; this fix must not silently widen it or create a second manifest lifecycle.

**Never:** Do not generate Capability as part of MVG, merge candidate fragments, weaken independent review, bypass baseline anti-weakening checks, mark runtime verified, commit or push, or alter game code/task status.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Capability changes after a prior MVG attempt | Same manifest, newer valid Capability job/hash | Start or resume only a run bound to the current Capability identity | Reject stale result reuse |
| Existing manifest has narrower scope than current Requirements | Frozen scope and broader semantic catalog | Incumbent projection and candidates are evaluated only against the frozen in-scope Requirements; outside Requirements remain explicitly excluded | Invalid baseline remains non-selectable with a clear reason |
| Some candidates validate; another fails | Durable candidate files and metadata | Retry resumes verified candidates and generates only missing/invalid candidates | Reject changed hashes or stale input identities |
| Review disagrees with proposal accounting | Structurally valid review with mismatched verdict/disposition/route | Review gate blocks before Validate/Apply | Persist precise mismatch findings |
| Selected candidate is semantically blocked | Other valid candidates remain | Preserve original review; allow bounded fallback to the next ranked candidate with a fresh independent review | Never re-review an unchanged blocked proposal |
| Existing flow semantic fields change | Same flow identity but changed outcome/Requirement/Capability mapping | Changes require explicit reviewed delta authority | Block silent semantic rewrite |
| Candidate is valid but not formally applicable | Draft/unresolved obligations | Exclude it from viable selection | Report formal blockers before review |

</frozen-after-approval>

## Code Map

- `scripts/python/_project_health_planning.py` -- `create_job`, `selected_result`, and `run_job` bind workspace revision, Capability parent job, manifest identity, resume/recovery, and page action stages. Ensure a prior MVG job is reusable only for the same current Capability identity.
- `scripts/python/plan_mvg.py` -- `prepare` snapshots inputs; `_manifest_planning_scope` defines frozen cumulative scope; `preserve_frozen_manifest_baseline` and `build_delta` govern incumbent changes; `generate` creates candidates, incumbent D, and whole-set selection; `validate_proposal`, `review`, `validate`, and `apply` enforce gates.
- `scripts/python/_mvg_planning_review.py` -- `coverage_errors`, `semantic_review_errors`, and `review_execution_errors` validate requirement accounting and isolated review evidence. Bind per-Requirement reviewer verdicts to the exact proposal disposition and route.
- `scripts/python/tests/test_project_health_planning.py` -- page-job identity and recoverability tests.
- `scripts/python/tests/test_mvg_planning_contract.py` and `scripts/python/tests/test_mvg_segment_scope.py` -- frozen scope, candidate, review-accounting, and baseline contract tests.
- `.agents/skills/plan-mvg/SKILL.md`, `workflow.md` 5.4, and `docs/workflows/mvg-integration-acceptance.md` -- public workflow contract; keep implementation and documented behavior aligned.

## Tasks & Acceptance

**Execution:**
- [x] Add failing job lifecycle tests for Capability hash/job binding, stale retry invalidation, and reuse of valid MVG candidates; then implement minimal identity and recovery fixes.
- [x] Add failing scope/incumbent tests for narrower manifests and existing flow semantic changes; make incumbent comparison consistent with frozen scope and require reviewed deltas for changed semantic fields.
- [x] Add failing review consistency tests covering verdict/disposition, route, sink and evidence mismatches; enforce agreement before approval can pass.
- [x] Add failing candidate gate/fallback tests; require formal applicability before selection and permit only bounded next-ranked candidate review after a semantic block.
- [x] Run focused MVG planning suites and the broader planning regression; update owning documentation for the exact resulting behavior.

**Acceptance Criteria:**
- Given a newer selected Capability identity, when the page starts MVG planning, then an older job/result cannot be reused as if it consumed that Capability.
- Given an existing manifest with a smaller frozen scope, when incumbent D is projected, then it is evaluated only for that exact scope and can be retained if otherwise valid.
- Given a candidate with incomplete formal applicability, when candidates are selected, then it is not marked viable.
- Given durable valid candidates and a failed sibling, when the page resumes, then valid candidates are reused only after hash, validation, and input identity checks.
- Given a semantic review inconsistent with proposal coverage, when review is evaluated, then Validate and Apply remain blocked with precise mismatch errors.
- Given an approved incumbent-preservation workflow, when existing flow semantic fields change, then apply requires explicit reviewed authority and cannot silently rewrite them.
- Given the selected candidate receives a semantic block, when another ranked candidate is viable, then it receives a new independent review within a bounded fallback policy; the blocked proposal is not re-reviewed unchanged.
- All existing guarded-delta, independent-context, no-runtime-claim, and local-derived-output behavior remains intact.

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_project_health_planning scripts.python.tests.test_mvg_planning_contract scripts.python.tests.test_mvg_segment_scope -v` -- expected: all focused regression tests pass.
- `py -3 -m unittest discover -s scripts/python/tests -p "test_*mvg*.py" -v` -- expected: all MVG regression tests pass.

**Manual checks:** Inspect the page job's Capability hash/job ID and selected manifest scope in persisted local evidence; confirm a generated planning result remains `runtime_verified=false` and does not alter task statuses.

## Spec Change Log
