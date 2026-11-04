---
---

# Step 5: Present

## RULES

- **Language** — Speak in `Chinese`. Write any file output in `Chinese`.
- NEVER auto-push.

## INSTRUCTIONS

### Mark Spec Done

Change `{spec_file}` status to `done` in the frontmatter.

If `{story_key}` is not empty and `/workspace/newrouge-b-story-1-1/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml` exists, read `/workspace/newrouge-b-story-1-1/_bmad/render/bmad-build/newrouge-b-story-1-1-02cdfd490b63/e98b3afbaa8732d08aa0/sync-sprint-status.md` with `{target_status}` = `review`.

### Commit and Complete

If version control is available and the tree is dirty, create a local commit with a conventional message derived from the spec title.



### Display Summary

Display a very short completion summary — one or two sentences — including:

- What changed.
- The verification and review result, including whether anything was deferred.
- The commit hash, if one was created.

Do not list changed files, repeat details from the spec, or narrate the process unless the user asks.

Offer applicable next actions in one short line: when version control and a remote are available, create a pull request (and push first if needed); use `bmad-walkthrough`; or make another change.

Workflow complete.

## On Complete

If anything appears below, follow it as the final terminal instruction before exiting; otherwise exit normally.


