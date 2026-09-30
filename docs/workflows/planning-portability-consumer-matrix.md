# Planning Portability Consumer and Acceptance Matrix

This document is the owning evidence map for **REQ-WORKFLOW-PORTABILITY-001**. It records the production consumers that must remain compatible when Capability is optional/post-Chapter-5 and when task numbering, source batching, or game semantics differ between projects.

## Consumer matrix

| Consumer | Input contract | Legacy / project-specific input still read? | Migration / retirement rule | Regression evidence |
| --- | --- | --- | --- | --- |
| `project_semantics_from_sources.py` | Source Block Ledger + reviewed Requirement candidate data | Historical `newrouge.*` schema names remain valid contract names; business task numbers are not semantic authority | Preserve schema compatibility; semantic classification comes from source/review evidence | `test_chapter3_semantic_conservation.py` batching, multi-sink and no-Capability cases |
| `normalize_task_intents.py` | Validated semantic anchors; Capability refs optional | Existing intent IDs/keys are reused only from prior task intent evidence | Capability regrouping may refresh `capability_refs` but cannot redefine mature task identity | `test_workflow_portability.py` Capability regrouping, sparse IDs and cross-project same-number/different-semantics cases |
| candidate/triplet/export route | Intent/candidate/task triplet | `review_frozen_task_projection.py`, `reconcile_frozen_task_candidates.py`, `build_gdd_from_task_baseline.py` are historical repair tools only | Normal add does not call the historical replay route | `workflow.md` Chapter 3 route plus Chapter 3 closeout route tests |
| `chapter5_semantic_reconciliation.py` | Source ledger, semantic Requirements, task/Acceptance/authority evidence | Does not require current-cycle Capability | Requirement corrections return through Chapter 3 projection/task preview; Capability planner never edits authority | `test_chapter5_semantic_reconciliation.py` orphan, drift and readiness fingerprint coverage |
| semantic topology validator/refresh | source-blocks / semantic-requirements / capabilities / topology edges | Capability remains optional until formal Capability planning | New Capability application updates only derived relationships and topology lineage | Capability planning contract tests plus `validate_semantic_topology.py` gates |
| `update_mvg_baseline.py` | Existing manifest + reviewed delta | Existing manifests are cumulative baseline authority | ID rewrite, conflicting operations and deterministic weakening require valid reviewed authority | `test_workflow_portability.py` and `test_mvg_planning_contract.py` |
| Chapter 7 profile / task creation | Generic structural defaults + explicit project profile | newrouge task/module mappings live only in project profile/example fixtures | Project business sections replace generic sections unless inheritance is explicit | `test_workflow_portability.py`, `test_chapter7_ui_wiring.py` |
| Knowledge topology/scenes | Formal topology + formal MVG manifest + main/workspace/runtime identity | Historical artifacts may be viewed but cannot overwrite formal current results | Keep Main/Workspace and planned/runtime evidence separate | existing project-health knowledge/runtime tests |
| legacy capability review replay | historical `capability-review.v1.json` | Read-only historical evidence only | New Capability planning writes new run evidence and formal selection lineage; historical replay cannot overwrite the new result | `plan-capabilities` stage contract and docs |

## Acceptance mapping

| AC | Evidence / status |
| --- | --- |
| AC01 newrouge baseline migration | Chapter 3 closeout record is complete; task triplet/topology checks passed; current PR does not rewrite mature task status/Acceptance/subtasks as part of portability changes. |
| AC02 second same-stack project fixture | `test_workflow_portability.py::test_second_project_fixture_uses_sparse_ids_without_newrouge_semantics` and sparse-ID fixture. |
| AC03 same number, different semantics | Same synthetic task ID `TASK-0007` is functional/gameplay in one fixture and non-functional/architecture in another; classification follows semantic input, not the number. |
| AC04 non-six batching / large input | Existing Chapter 3 semantic conservation tests assert dynamic batch counts; Capability input batching is budget-driven and records oversize blocks instead of silent truncation. |
| AC05 multi-to-many / no Capability | Existing Chapter 3 semantic tests cover multiple Capability membership and non-task sinks; portability test covers multiple Requirements grouped without Capability. |
| AC06 Chapter 7 profile isolation | Generic profile contains no business task IDs; project business sections replace defaults; empty structures remain empty. |
| AC07 scope and ID conflict | Chapter 7 profile validation rejects duplicate task ownership and missing buckets/fallback; normal task ID allocation skips collisions. |
| AC08 post-Capability add identity | Portability regression preserves ID and intent_key when only Capability grouping changes. |
| AC09 MVG delta negative cases | ID rewrite, duplicate/conflicting operations and unreviewed weakening are rejected. |
| AC10 source governance | Chapter 3 closeout preserves active/retired source declarations; task-derived baseline remains explicit historical repair input only. |
| AC11 evidence refresh | Existing Chapter 5 readiness fingerprint and project-health Main/Workspace/runtime tests remain authority. |
| AC12 normal entry vs historical tools | `workflow.md` explicitly removes fixed 133/six-batch historical replay from the normal new-GDD route. |
| AC13 Requirement correction loop | Chapter 5 finding -> Chapter 3 projection/task preview -> affected Chapter 4/5 recheck remains the owning correction route; planning Skills do not edit Requirement authority. |
| AC14 old/new artifact migration | Historical capability review remains read-only; new formal Capability/topology output uses controlled apply and semantic topology validation. |

## Completion rule

This matrix is evidence mapping, not a substitute for tests. A portability change is complete only when the referenced tests and repository gates pass on the PR head.
