# Chapter 3 task-scope correction

- Status: Resolved for committed baseline; canonical publication pending main merge
- Title: chapter3-133-task-scope
- Date: 2026-09-27
- Supersedes: none
- Superseded by: none
- Branch: chapter3-repair-133-20260927
- Git Head: 895a927bee8eb149d3354299890a08c405018b6b
- Why now: The repository is repairing Chapter 3 data structures under a strict 133-task freeze.
- Context: An experimental generation branch created additional tasks; this branch preserves the original T1-T133 authority set and reconciles its triplet and topology artifacts.
- Decision: The current milestone has exactly Taskmaster IDs T1-T133. The 501 tasks created by the experimental Chapter 3 branch are not accepted into this branch.
- Authority: `.taskmaster/tasks/tasks.json` owns task identity and status. The task views provide acceptance and discipline-specific details, not a competing completion state.
- GDD: `docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md` is the sole current Chapter 3 GDD input and Project Health GDD path. The three retired GDD files remain as historical references and are excluded from the Knowledge source catalog.
- Resolution: The current GDD has 139 reviewed Source Blocks in six batches. Its 127 active requirements map to existing T1-T133 IDs; T117-T122 remain superseded history. Workspace topology is fresh and has no orphan requirements. The frozen-task guard prevents an accidental 134th task during reconciliation.
- Resolution: On this frozen-scope repository, Chapter 7 now defaults to `docs/planning/chapter7/ui-wiring-board.md` for new writes. The retired `docs/gdd/ui-gdd-flow.md` reference is read-only; explicit write attempts are rejected. Historical links remain reference evidence only.
- Resolution: The 16 implemented pending tasks (T54, T57, T59, T60, T64, T71-T76, T92, T105, T131-T133) are synchronized to `done` in the master and both task views. The six cancelled tasks remain cancelled; no pending tasks remain.
- Resolution: Removed 16 legacy `tasks_back.json` rows without `taskmaster_id` and removed their 19 dependency references. They were outside the frozen T1-T133 authority set and are recorded in `logs/ci/task-generation/unmapped-view-prune.v1.json`.
- Resolution: Commit `7120a264` and its follow-up status/guard fixes were validated on the committed branch. Workspace topology is fresh and closure evidence is passed. Only canonical Knowledge validation/publication remains gated on merging the reviewed commit into `main`; this is a publication prerequisite, not an unverified patch state.

- Consequences: Chapter 3 and Chapter 7 reject unapproved task expansion until the freeze configuration and source baseline are explicitly changed.
- Recovery impact: Resume from the execution plan and rerun the documented hard-gate command; do not regenerate the task triplet.
- Validation: Chapter 3, semantic conservation, topology, Chapter 7, and task contract checks passed before CI run 36319054383; governance failures are tracked separately.
- Related ADRs: none
- Related execution plans: `execution-plans/2026-09-27-chapter3-133-task-reconciliation.md`
- Related task id(s): T1-T133 (frozen baseline)
- Related run id: `36319054383`
- Related latest.json: n/a (CI run-level repair)
- Related pipeline artifacts: n/a (CI run-level artifact URL is recorded by the related run id)

See `execution-plans/2026-09-27-chapter3-133-task-reconciliation.md` for the bounded completion path and evidence locations.
