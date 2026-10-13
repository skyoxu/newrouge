# Architecture Reality Review (Final)

**Artifact:** `../ARCHITECTURE-SPINE.md`  
**Review lens:** Brownfield and technology reality  
**Verdict:** Pass after one classification fix

The revision closes the earlier R1-R5 clarity gaps: it identifies itself as target architecture pending migration, marks the changed checkpoint/accounting/budget/selection/audit rules as `[TARGET]`, preserves current whole-candidate plus optional incumbent-D behavior as the deployed workflow, makes the coverage-table migration explicit, and separates CI compatibility from the locally resolved .NET SDK. Chapter 5 readiness is appropriately retained as a frozen prepare input with its concrete schema and identity fields deferred.

## Resolved Finding

### F1. AD-1 is still labeled adopted although the append worker advances and persists its own accepted chain

**Location:** `ARCHITECTURE-SPINE.md`, AD-1.

AD-1 initially labeled coordinator ownership `[ADOPTED]`, while `run_capability_append()` owns and persists each candidate's private accepted chain. The spine now labels the coordinator-selected checkpoint rule `[TARGET]` and explicitly distinguishes the current candidate-local ledger from the future shared selected baseline.

**Evidence:** `scripts/python/_mvg_capability_append.py:80-112,233-244`; `scripts/python/plan_mvg.py:4645-4704`.

**Resolution:** Closed. AD-1 is `[TARGET]`; its rule and current-behavior note describe the two ownership levels separately.

## Prior Findings Status

| Prior finding | Result |
| --- | --- |
| R1: incumbent D and selection contract | Closed as a current/target boundary. The spine states the existing workflow and Skill remain current until the migration updates them. |
| R2: whole-candidate append vs per-Capability checkpoint | Closed. The opening notice and Deferred section identify the migration, while AD-5/AD-8 are target rules. |
| R3: 192-call run budget | Closed as a status ambiguity. AD-7 is `[TARGET]`, and the opening notice says target-only rules are not deployed. |
| R4: Python/.NET version policy | Closed. Python 3.12 is identified as MVG CI compatibility; .NET policy and observed host resolution are distinct. |
| R5: route/verification projection | Closed. AD-6 is `[TARGET]` and explicitly preserves current one-row `coverage_table` semantics pending migration. |
| F1: AD-1 coordinator ownership label | Closed. AD-1 is `[TARGET]` and distinguishes candidate-local accepted chains from the target selected checkpoint. |

## Sources Checked

- `_bmad-output/planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md`
- Prior review `reviews/review-reality.md`
- MVG PRD and SPEC, including state-machine and requirement-accounting companions
- `workflow.md` Chapter 5 and 5.4
- `.agents/skills/plan-mvg/SKILL.md`
- `scripts/python/plan_mvg.py`, `scripts/python/_mvg_capability_append.py`, `.github/workflows/mvg-integration.yml`, and `global.json`
