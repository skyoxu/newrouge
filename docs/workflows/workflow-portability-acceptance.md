# Workflow Portability Acceptance

Status: implemented and acceptance-mapped on PR #251.

This file owns the evidence map for `REQ-WORKFLOW-PORTABILITY-001`. It does not redefine Chapter 3 closeout or the Capability/MVG planning lifecycle.

## H01-H12 disposition

| ID | Disposition | Current evidence |
| --- | --- | --- |
| H01 | Historical replay only | `build_gdd_from_task_baseline.py` remains an explicit historical task-derived baseline tool. Normal new-GDD routing does not call it; `workflow.md` labels the replay tools non-default. |
| H02 | Historical replay only | The fixed six-batch assertion remains confined to `review_frozen_task_projection.py`; dynamic production batching is input/budget driven. |
| H03 | Historical replay only | Numeric governance classification remains confined to historical replay; ordinary semantic projection uses reviewed Requirement `kind` and source evidence. |
| H04 | Historical replay only | Frozen-candidate reconciliation remains a repair tool. Normal Requirement/Task projection supports optional Capability, multi-membership and non-task sinks. |
| H05 | Closed temporary lifecycle | The T1-T133 temporary scope was removed by the durable Chapter 3 closeout. Incomplete closeout state continues to guard all real creation routes. |
| H06 | Fixed | Chapter 7 built-in defaults are structural only. Project business sections replace instead of deep-inheriting example IDs; explicit inheritance is opt-in and effective sources are recorded. |
| H07 | Preserved project configuration | The reviewed newrouge `chapter7-profile.json` remains project data. Generic defaults do not broaden it. Duplicate bucket assignments and view-ID template collisions fail validation. |
| H08 | Preserved source governance | Closeout retained active/retired source declarations. New sources require explicit registration; historical retirement is not reversed by unfreeze. |
| H09 | Fixed | Task intent identity is based on stable semantic/source partition and prior Requirement ownership. Capability regrouping updates refs without changing mature intent ID/key. |
| H10 | Fixed | README and the critical MVG manifest no longer claim done Tasks 59/60 are pending blockers. `m1-full.coverage.blocking_task_ids` is the current planning authority; runtime verification remains separate. |
| H11 | Fixed | MVG delta update rejects ID rewrite, duplicate/conflicting operations, broken final references and deterministic weakening without a resolvable reviewed authority. |
| H12 | Preserved | Project Health topology/scenes keep Main vs Workspace identity, exact revision/manifest binding and runtime/static separation. No name-based Capability/MVG inference was added. |

## Consumer matrix

| Consumer | Input contract | Legacy behavior | Current migration / verification |
| --- | --- | --- | --- |
| Source ledger / semantic projection | source manifest, Source Blocks, reviewed semantic Requirements | Historical task-derived GDD may still be replayed explicitly | Normal source registration is cumulative; projection batching accounts for every primary block and fails rather than truncating an oversized block. |
| Task normalizer / candidate / triplet | reviewed Requirements, optional Capability refs, previous intents | Capability formerly influenced grouping identity | Capability is advisory/derived for identity; previous Requirement ownership preserves mature intent IDs. Triplet remains Taskmaster-owned. |
| Chapter 5 reconciliation / readiness | full declared sources, task slice, authority refs, input fingerprint | No migration shortcut | Existing fingerprint invalidation and semantic correction tests remain authoritative. Capability-only rebind is handled only by the later planning stage. |
| Topology validator / refresh / promotion | source/Requirement/Capability/Task topology + revision identity | Legacy checkout can remain explicitly unmapped | Workspace never becomes Main authority; source/revision drift makes topology stale rather than rewriting identity. |
| KCP / Project Health UI | published topology, selected revision, exact MVG manifest/run summary | Historical nodes may remain read-only | Main/Workspace and planned/runtime states remain separate; cumulative flows are not inferred from Capability names. |
| Chapter 7 profile / task creation | effective project profile + Taskmaster triplet | Built-in newrouge business buckets were implicit | Generic defaults contain no business task IDs. Project mappings are explicit; duplicate ownership/template collision fail closed. |
| MVG updater / runner | explicit manifest/delta + exact content hash | Reward pilot remains a named example only | Cumulative baseline uses guarded add/update/retain/retire; old runtime evidence is bound to the exact manifest/revision. |
| Historical capability-review / frozen replay | explicit historical artifact/repair commands | Project-specific IDs, six batches and old capability review shape | Kept outside normal add/planning routes. New formal Capability planning has a separate contract and cannot be overwritten by replay. |

## AC01-AC14 evidence map

| AC | Result | Evidence |
| --- | --- | --- |
| AC01 newrouge baseline migration | PASS | Chapter 3 closeout record is complete; triplet/topology checks pass; CI runs the repository regression suite. |
| AC02 second same-stack project fixture | PASS | `test_second_project_fixture_supports_sparse_ids_different_semantics_and_no_capability` uses sparse IDs 2/107, a different game domain and no Capability. |
| AC03 same number, different semantics | PASS | The same fixture assigns the same external fixture number to functional and non-functional requirements; classification follows reviewed semantic kind, not number. |
| AC04 non-six batches / large source | PASS | `test_dynamic_batching_is_not_six_and_oversize_block_is_not_truncated` produces five dynamic batches and verifies full oversized source text. Existing Chapter 3 projection tests also verify every block is accounted for and oversized blocks are never silently truncated. |
| AC05 many-to-many / no Capability | PASS | The second-project fixture proves no-Capability task projection; existing semantic-conservation tests cover multi-Capability/multi-source relations and legal non-task sinks. |
| AC06 Chapter 7 profile isolation | PASS | `test_chapter7_profile_does_not_inherit_business_task_ids` and empty-profile replacement coverage. |
| AC07 scope / ID conflicts | PASS | Duplicate bucket assignment and rendered view-ID collisions fail in the new portability fixture; existing Chapter 7 tests cover scoped candidate generation. |
| AC08 Capability after Task creation | PASS | `test_capability_regrouping_does_not_change_intent_identity` preserves mature ID/key while updating refs. |
| AC09 MVG delta counterexamples | PASS | Portability and MVG acceptance tests reject ID rewrite, duplicate operations, unknown references and unreviewed weakening, then validate the full resulting manifest. |
| AC10 source governance | PASS | Chapter 3 source-set cumulative/retirement tests plus the real closeout preserve active/retired sources; historical task-derived GDD is explicitly non-default. |
| AC11 evidence refresh separation | PASS | Semantic-topology and MVG acceptance tests bind workspace/main, revision and exact manifest hashes; stale evidence becomes stale rather than current. |
| AC12 normal route vs historical tools | PASS | `workflow.md` and stable entrypoints mark the three frozen replay scripts historical; normal Chapter 3 add and Chapter 7 use generic routes. |
| AC13 Requirement correction loop | PASS | Chapter 5 reconciliation tests detect semantic/authority drift; Chapter 3 semantic-conservation tests preserve unchanged IDs through add/reprojection and require reviewed semantic coverage before promotion. |
| AC14 old/new artifact migration | PASS | Topology validator supports explicit legacy-unmapped/read-only states; current semantic topology handles optional/multi Capability relations and is validated/refreshed without invoking frozen replay. |

## Required gates

The portability stage is accepted only when the current PR HEAD passes:
- Python regression suite / Windows Quality Gate
- Windows Smoke dry run
- MVG Integration

The later Capability/MVG Skill requirement has its own production-model acceptance and is not satisfied by this matrix.
