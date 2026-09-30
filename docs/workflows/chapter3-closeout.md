# Chapter 3 Temporary Reconciliation Closeout

`scripts/python/chapter3_closeout.py` completes an authorized temporary reconciliation in the same repair task. It does not generate tasks or planning content. Existing task data and active/retired source declarations remain unchanged.

## Entry contract

| Item | Contract |
| --- | --- |
| Begin | `py -3 scripts/python/chapter3_closeout.py begin --run-id <repair-run-id> --temporary` after mapping repair and reviewed diffs |
| Preview | `py -3 scripts/python/chapter3_closeout.py preview` reads the registered record |
| Apply/recover | `py -3 scripts/python/chapter3_closeout.py resume` continues only unfinished stages |
| Durable pointer | `docs/workflows/chapter3-closeout.json`, schema `chapter3.closeout.v1` |
| Durable record | `docs/workflows/closeouts/<run-id>.json`, same schema; historical execution evidence, not task-state authority |
| Phases | `prepared` → `repair-verified` → `unfrozen` → `recovery-verified` → `complete` |
| Input identity | SHA-256 of exact UTF-8 file bytes, prefixed `sha256:`; scope separately bound before removal |
| Repair checks | Existing triplet attestation; semantic topology validation with `--worktree --require-available` |
| Recovery checks | Real compiler/exporter and Chapter 7 creator on isolated repositories; no real test tasks |
| Logs | `logs/ci/chapter3-closeout/<run-id>/repair/` and `recovery/` |

The record binds task triplet, registered sources, topology, output configuration and Python validator/consumer code. Drift fails before removal or before completion. Run checks against current files: committed HEAD alone is insufficient for an uncommitted repair. Topology directory identity is a worktree snapshot, never Main publication.

## Consumers and failure handling

All scope consumers call `chapter3_task_scope.load_scope`, which validates the pointer/target and incomplete-closeout guard. Actual creation writers are `compile_task_triplet.py`, `build_taskmaster_tasks.py` and direct `create_chapter7_tasks_from_ui_candidates.py`; the Chapter 7 wrapper checks the same guard. Writers recheck before applying. Generic filesystem writes or external Taskmaster clients are outside these repository entrypoints.

Scope removal follows durable passing repair evidence. If removal or recovery stops, creation remains blocked even though the scope is absent. Recovery records passing evidence before clearing the guard by setting `complete`. Repeating completed closeout returns its historical evidence without changing tasks or rerunning analysis. Missing/corrupt target, identity mismatch or missing passing evidence fail closed. Retain the pointer and record in Git; deleting them is not a recovery command.

On changed inputs or a changed/reappeared scope, preserve later edits and inspect the conflict. Restore the exact recorded baseline only through a reviewed change, then resume. This entry does not automatically overwrite user edits or recreate a deleted scope. Failed closeout remains incomplete and guarded. Permanent scopes (`lifecycle: permanent`) are not released.

## Output and source boundaries

Chapter 7 document output uses `chapter7-profile.json.ui_document_path`, independent of frozen identity policy. NewRouge keeps `docs/planning/chapter7/ui-wiring-board.md`. The source declaration's retired paths remain read-only after unfreeze. Other projects without retired legacy output may retain their existing document path.

Closeout preserves `chapter3-source-set.json`, Knowledge GDD paths, all task identities/status/acceptance/subtasks and formal semantic relationships. It does not attest new task readiness, run the game or publish KCP. New GDDs enter the existing cumulative `add` declaration and reviewed task change route.

The three historical task-baseline replay scripts are not ordinary `add` dependencies. Their old business assumptions are evaluated separately by the portability repair; unfreeze does not depend on all later planning features being implemented.
