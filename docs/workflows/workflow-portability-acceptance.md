# Workflow Portability Acceptance Map

This document maps REQ-WORKFLOW-PORTABILITY-001 to executable repository evidence. It is an acceptance index, not a second source of task/readiness truth.

## Consumer migration matrix

| Consumer | Input contract | Old-format handling | Current migration / retirement rule | Regression evidence |
| --- | --- | --- | --- | --- |
| source ledger / semantic projection | source-set, source-manifest, source-blocks, reviewed semantic requirements | historical task-derived GDD remains explicit opt-in only | normal add keeps declared sources and requires explicit retirement | `test_chapter3_semantic_conservation.py` source-set and batching cases |
| task intent / candidate / triplet | semantic requirements with optional Capability refs | no FR/NFR-T#### or one-to-one requirement is required | existing intent identity is reused by Requirement partition; Capability refs are derived | `test_workflow_portability.py`, `test_workflow_portability_acceptance.py` |
| Chapter 5 reconciliation/readiness | complete source scope, Extraction B, task views, authority bytes | no dependency on historical six-batch replay | independent reconciliation remains valid before Capability generation; capability-only rebind is narrow | `test_chapter5_semantic_reconciliation.py`, planning acceptance fixture |
| semantic topology refresh / validator | source blocks, requirements, capabilities, edges, manifest hashes | legacy checkout can be reported unmapped without rewriting it | new multi-membership relations remain explicit; stale hashes fail closed | `test_semantic_topology.py`, `test_chapter3_capability_projection.py` |
| Capability planning | explicit ready task scope plus blinded authoritative snapshot | old `capability-review.v1` is not a candidate input | old formal Capability is used only after review for ID alignment | `test_capability_planning_contract.py`, real planning production acceptance |
| MVG updater / planner / runner | explicit Capability version, manifest/delta, task/contract/test evidence | existing manifest is cumulative baseline | update cannot rewrite IDs; weakening needs reviewed real authority; runtime evidence remains manifest-bound | `test_workflow_portability.py`, `test_mvg_planning_contract.py`, MVG Integration CI |
| Chapter 7 profile / collector / creator | generic structural defaults + explicit project profile + task triplet | historical newrouge mapping lives only in explicit profile/fixture | business sections replace generic sections; invalid refs/collisions fail; excluded tasks are reported | `test_chapter7_ui_wiring.py`, `test_workflow_portability_acceptance.py` |
| Knowledge topology/scenes | formal topology, main/workspace identity, formal MVG manifest/runtime snapshot | old missing topology is explicit legacy/unmapped | workspace never claims Main authority; runtime and planning freshness remain separate | `test_semantic_topology.py`, project-health MVG tests |

## Acceptance mapping

- **AC01** — Chapter 3 closeout record is complete and task-triplet/topology repair checks passed; existing Chapter 3 regression suites protect status/Acceptance/subtask identity.
- **AC02** — `planning_acceptance_fixture.py` builds the Harbor Relay project with non-contiguous Taskmaster IDs 7 and 42 and generates real Chapter 5 readiness through the production reconciliation code.
- **AC03** — `test_ac03_same_generated_numeric_identity_can_have_different_semantics` proves semantic owner/layer comes from the Requirement, not the generated numeric position.
- **AC04** — existing source projection batching tests plus `test_ac04_batch_count_is_input_driven_and_oversize_blocks_are_not_truncated` prove complete accounting without a six-batch invariant or silent truncation.
- **AC05** — `test_ac05_multi_capability_and_multi_task_mapping_remain_legal` plus semantic conservation tests cover multi-Capability, one-Requirement-to-many-task and legitimate non-task sinks.
- **AC06** — Chapter 7 portability regression proves generic defaults do not inherit project task 41-46 and preserves explicit newrouge profile mappings.
- **AC07** — Chapter 7 profile validation rejects duplicate ownership and rendered view-ID collisions; the collector rejects unknown configured task IDs and reports completed tasks excluded by the configured range.
- **AC08** — `test_capability_regrouping_does_not_change_intent_identity` preserves mature Task ID and intent key while changing only derived Capability refs.
- **AC09** — MVG delta regression rejects ID rewrites, duplicate operations and unreviewed weakening; final manifest validation catches dangling refs.
- **AC10** — source-set add tests require explicit retirement and do not revive missing/retired sources.
- **AC11** — semantic topology and MVG runner tests keep Main/Workspace, manifest/revision and runtime/planning evidence identities separate.
- **AC12** — public CLI does not expose historical frozen replay as the normal route; workflow owning docs label the three replay scripts historical/repair-only.
- **AC13** — Chapter 5 reconciliation tests exercise explicit corrections, idempotent dependency application and readiness invalidation; unchanged semantic IDs are preserved by the Chapter 3 projection path.
- **AC14** — capability projection and topology tests cover existing formal Capability projection, multi-membership refresh and explicit legacy/unmapped behavior without letting frozen replay overwrite new formal results.

The final CI run on the PR head is the authoritative execution result for this map. Real model semantic acceptance is separately owned by REQ-CAPABILITY-MVG-SKILLS-001.
