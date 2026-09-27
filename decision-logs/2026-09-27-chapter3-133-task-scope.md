# Chapter 3 task-scope correction

- Status: Needs Fix
- Decision: The current milestone has exactly Taskmaster IDs T1-T133. The 501 tasks created by the experimental Chapter 3 branch are not accepted into this branch.
- Authority: `.taskmaster/tasks/tasks.json` owns task identity and status. The task views provide acceptance and discipline-specific details, not a competing completion state.
- GDD: `docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md` is the sole current Chapter 3 GDD input and Project Health GDD path. The three retired GDD files remain as historical references and are excluded from the Knowledge source catalog.
- Resolution: The current GDD has 139 reviewed Source Blocks in six batches. Its 127 active requirements map to existing T1-T133 IDs; T117-T122 remain superseded history. Workspace topology is fresh and has no orphan requirements. The frozen-task guard prevents an accidental 134th task during reconciliation.
- Resolution: On this frozen-scope repository, Chapter 7 now defaults to `docs/planning/chapter7/ui-wiring-board.md` for new writes. The retired `docs/gdd/ui-gdd-flow.md` reference is read-only; explicit write attempts are rejected. Historical links remain reference evidence only.
- Resolution: The 16 implemented pending tasks (T54, T57, T59, T60, T64, T71-T76, T92, T105, T131-T133) are synchronized to `done` in the master and both task views. The six cancelled tasks remain cancelled; no pending tasks remain.
- Resolution: Removed 16 legacy `tasks_back.json` rows without `taskmaster_id` and removed their 19 dependency references. They were outside the frozen T1-T133 authority set and are recorded in `logs/ci/task-generation/unmapped-view-prune.v1.json`.
- Open issue: The stable topology is currently a Workspace artifact on an uncommitted branch. Committed-ref validation and canonical Knowledge publication must wait until the reviewed branch is merged into `main`.

See `execution-plans/2026-09-27-chapter3-133-task-reconciliation.md` for the bounded completion path and evidence locations.
