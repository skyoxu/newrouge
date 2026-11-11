# Independent Epic 2 CLI repair while private transfer is pending

Starting checkpoint: 6edb6b2f76dc96a8a8da4c4861cab10ae43c469c. Branch: build/cloud-epic2-recovery-20261111.

## Changes and evidence

A public context response still claimed Story 2.9's ABI was absent although the migrated completed-reuse implementation is installed. The diagnostic now points to the native planner coordinator while keeping operation context observation-only. Its existing nine focused checks passed.

Actual CLI smoke inspection found a missing public resume_ref for read when its receipt does not exist. Story 2.10 AC3 explicitly requires original reasons and a public resume_ref. A new actual empty-target regression failed first (RED). The minimal CLI repair enriches only a receipt read's missing diagnostic reference with its known repository-relative receipt path; original reason/stage and an already provided resume_ref remain unchanged. Four affected boundary checks then passed, covering the new case, pending owner diagnostics, changed/wrong receipt and normal protected reading. No new permission, schema, record or retry was introduced.

Four fresh Python subprocess checks passed: direct and dev-cli read, each with and without --context, from an unrelated cwd on a newly created empty target. All reject with file_not_found, the same operation identity, false qualification flags and the exact receipt resume_ref. No target file was created. These are actual missing-input observations, not a synthetic successful original operation.

One existing published-clone test passed with explicitly synthetic upstream admission and real local storage/reader behavior. It confirms a published reader can consume complete receipt-sealed formal references without local historical logs, while missing sealing authority remains rejected. The initial selector used nonexistent CommitTests and raised a loader error without running the intended method; the corrected PublicCommitTests selection passed separately. Both result files remain.

| Attempt | Result | Scope |
| --- | --- | --- |
| story210-context-routing-01 | 9 passed | Existing context routing/claim/diagnostic checks; owner seams synthetic |
| story210-missing-receipt-red-02 | 1 failed, retained | Actual empty-target missing resume_ref before repair |
| story210-receipt-boundary-green-03 | 4 passed | Exact changed boundary and adjacent controls |
| public-read-fresh-process.json | 4 passed | Actual fresh direct/dev-cli processes, no target writes |
| story210-published-clone-04 | Loader error, retained | Wrong class selector; intended method did not execute |
| story210-published-clone-selector-05 | 1 passed | Corrected selector, receipt-sealed clone control |

The earlier mixed-stage smoke command stopped on its first direct-read null resume_ref. Its original tool output remains; no completed six-case result is claimed. The RED artifact independently reproduces the exact defect.

## Material boundary

No private package has been received or read in this step. The existing _PublishedBundle/read_committed contract permits absent historical logs only when actual unchanged formal targets and receipt authority seal the full references. Therefore a genuine published-read qualification needs the original target formal chain/current non-log dependencies, not an automatic transfer of every historical proof or the fiscal ledger. Original compensation preparation/recovery and paid segmented qualification retain their own exact private requirements. No new original operation was started or reconstructed.

The local-only transfer checklist remains untracked. Source fixes, existing failure records and prior passing scopes are preserved. The Library read-only workflow is ready for the resolved package; no files were uploaded or shared.

Story 2.8 actual recovery/capacity, Story 2.9 formal closure, Story 2.10 full Windows acceptance and paid segmentation remain pending their actual inputs. No model turn, budget release, network-403 retry/bypass, remote write, main merge, Fast setting change or Aliyun execution occurred. No full suite was repeated.
