# Architecture Reality Review

**Artifact:** `../ARCHITECTURE-SPINE.md`  
**Review lens:** Brownfield and technology reality  
**Verdict:** Needs Fix

The spine captures several target requirements from the new MVG SPEC, but labels them `[ADOPTED]` and `final` while the repository's owning workflow/skill still specify different selection behavior and the implementation retains the whole-candidate lifecycle. The technology table also mixes a local host snapshot with repository and CI versions. Resolve these authority and transition boundaries before treating the spine as the current architecture contract.

## Findings

### R1. Candidate selection contradicts the current owning workflow and Skill

**Location:** `ARCHITECTURE-SPINE.md`, AD-8; `workflow.md` 5.4; `.agents/skills/plan-mvg/SKILL.md`, Primary workflow.

AD-8 requires exactly three admitted candidates for each Capability selection and says the accepted baseline is never a candidate. The current owning workflow and Skill instead say all Capability increments are appended and admitted first, then three candidates plus an eligible incumbent D enter whole-set ranking. The new SPEC explicitly changes this by making the accepted MVG read-only and not a fourth candidate. The spine therefore agrees with the new SPEC but directly contradicts two existing owning sources that it lists as inputs.

**Evidence:** `workflow.md:790`; `.agents/skills/plan-mvg/SKILL.md:43,56`; `SPEC.md` Constraints, incumbent rule.

**Required resolution:** Reconcile the SPEC decision into `workflow.md` and the Skill (or revise the SPEC if incumbent D remains intended) and record the transition boundary. Until those owners agree, AD-8 cannot be treated as the unambiguous adopted contract.

### R2. Per-Capability selection/checkpoint is presented as adopted while code still selects whole candidates

**Location:** `ARCHITECTURE-SPINE.md`, AD-1, AD-5, AD-8, and Deferred item 4.

The live implementation appends and validates Capability increments into each candidate's private `accepted` chain and persists `capability-append/append-ledger.json`; comparative selection happens only after the candidate has processed all scoped Capabilities. There is no selected per-Capability checkpoint that becomes the next Capability's shared accepted baseline. The spine acknowledges a future migration from the whole-candidate append lifecycle to per-Capability selection checkpoints in Deferred item 4, but AD-5/AD-8 are marked adopted and describe that target as current lifecycle ownership.

**Evidence:** `scripts/python/_mvg_capability_append.py:80-112,233-240`; `scripts/python/plan_mvg.py:4645-4704,5216-5237`; `workflow.md:788-790`; `.agents/skills/plan-mvg/SKILL.md:31,43`.

**Required resolution:** Mark these as target decisions pending migration, or attach an explicit migration stage and compatibility boundary. Distinguish candidate-local append checkpoints from coordinator-selected cumulative baseline checkpoints so readers do not infer that the latter already exist.

### R3. The 192-call run-wide budget has no matching implementation enforcement

**Location:** `ARCHITECTURE-SPINE.md`, AD-7.

AD-7 states every run binds `mvg.run_invocation_limit` (default 192) across candidates and Capabilities. The implementation enforces a durable 64-call limit per candidate lineage and allows bounded replacement rounds, but the inspected coordinator has no shared run invocation counter or configured `mvg.run_invocation_limit`. Consequently, replacement lineages can each consume another lineage budget and aggregate run calls can exceed 192. The new SPEC requires this run-wide cap, while the existing Skill/workflow currently describe the 64-call lineage stop-loss and replacement cap only.

**Evidence:** `scripts/python/plan_mvg.py:59-60,1076-1104,5216-5238`; `scripts/python/_mvg_capability_append.py:80-108,242-244`; `SPEC.md` Constraints and `workflow.md:789`.

**Required resolution:** Treat 192 as a planned invariant until a run-scoped counter is wired through generation, inspection, repairs, semantic calls, and replacements. Update the owning Skill/workflow with the aggregate budget and failure state at the same time; otherwise state the current 64-per-lineage contract as the implemented boundary.

### R4. Stack versions are host observations, not the repository/CI version contract

**Location:** `ARCHITECTURE-SPINE.md`, Stack.

The table labels Python 3.13.1 and .NET 8.0.415 as the planning/repository runtimes, but the MVG integration CI uses Python 3.12 and .NET 8.0.x. The repository pins the .NET SDK baseline to 8.0.401 with `rollForward: latestPatch`; this host resolves that policy to 8.0.415. Thus both values can be valid observations, but the table does not say which is a local verification snapshot and which version must reproduce in CI. The label ".NET repository/test runtime" also names an SDK version as a runtime.

**Evidence:** `global.json:1-5`; `.github/workflows/mvg-integration.yml:64-72`; local `py -3 --version` returned `Python 3.13.1`; local `dotnet --version` returned `8.0.415`.

**Required resolution:** Label these as host-observed SDK versions with date, then separately identify the supported CI/toolchain contract (Python 3.12 for MVG integration, .NET 8.0.x / `global.json` roll-forward policy). Avoid implying Python 3.13.1 is the compatibility baseline.

### R5. Route membership and verification are separated in the model but not yet in the current proposal projection

**Location:** `ARCHITECTURE-SPINE.md`, AD-6 and Consistency Conventions.

AD-6 adopts three distinct keys: route membership `(requirement_id, flow_id)`, authoritative verification `requirement_id`, and evidence reference `(requirement_id, evidence_id)`. The current proposal projection still centers one `coverage_table` row per Requirement, with a single `flow_id` and verification fields on that row; there is no separate persisted route-membership projection using the AD-6 key. This makes the rule a target migration contract, not a brownfield description. The architecture defers shared-evidence disposition and route-scope fields, but does not defer introducing the separate projection itself.

**Evidence:** `scripts/python/plan_mvg.py:1658-1667,1879-1884,2244-2294`; `_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/requirement-accounting.md`, Stable keys and migration rule.

**Required resolution:** State that AD-6 requires a schema/projection migration and identify its owner and compatibility behavior for existing `coverage_table` rows. Keep the current one-row coverage semantics explicit until that migration is implemented and validated.

## Verified alignments

- Chapter 5 readiness is a real prepare-time gate. `plan_mvg.py` derives explicit round scope, loads readiness for task sinks plus the global witness, writes `readiness-summary.json`, hashes it and the source readiness/reconciliation artifacts, and rechecks source freshness before formal stages. AD-2 is directionally accurate; the spine's deferred exact artifact schema is reasonable as long as it does not imply a single readiness file is the only bound input.
- The 64-call candidate limit and three-repair/restart behavior exist in the append implementation. The discrepancy is the additional 192-call run-wide cap, not those lineage-local bounds.
- The planning/runtime authority boundary agrees with the Skill: planning/rebind does not set `runtime_verified`; runtime acceptance owns that evidence.

## Sources checked

- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md`
- `_bmad-output/planning-artifacts/prds/prd-newrouge-2026-10-11/prd.md`
- `_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/SPEC.md`
- `_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/workflow-state-machine.md`
- `_bmad-output/specs/spec-mvg-capability-increment-planning-and-admission-optimization/requirement-accounting.md`
- `workflow.md` Chapter 5 and 5.4
- `.agents/skills/plan-mvg/SKILL.md`
- `docs/workflows/mvg-integration-acceptance.md`
- `scripts/python/plan_mvg.py`, `scripts/python/_mvg_capability_append.py`, and `global.json`
