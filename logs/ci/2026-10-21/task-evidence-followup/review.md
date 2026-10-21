# Task evidence follow-up review

Base: `a789c670f22c4ccb0b6341ee704f45ec129ddd6c` on
`fix/capability-synthesis-input-integrity`.

Deterministic input checks pass. Compression remains an opt-in trial, and no
formal Capability was generated or applied. This follow-up supersedes the
Task 89 missing-target finding in the preceding implementation review; it does
not close that review's model or environment gates.

## Repairs

1. Task 89's two views incorrectly listed a workflow summary log template in
   `test_refs`, although both already retained it in `evidence_refs`.
   `validate_task_test_refs.py` explicitly requires `.cs`/`.gd` test files under
   test roots. `Task0089WorkflowSelectionEvidenceTests.cs` explicitly checks
   the log template in `evidence_refs` and the real test file in `test_refs`.
   Removed only the duplicate template from the two `test_refs` arrays.
   Exact parsed comparisons prove every other value unchanged, including
   Acceptance, status, IDs, semantic refs, and the complete evidence refs.
   No date, replacement artifact, or inferred relationship was introduced.
   This is a separately reviewed metadata correction using existing task
   rules, not a compression-derived write to authority.
2. Recursive blinding previously attempted set membership on any field named
   `schema_version`. An otherwise valid unknown extension using an object or
   array raised `TypeError`. Only string schema identifiers are now matched;
   recursion still inspects nested objects and blocks historical Capability
   fields. The regression preserves null, object, array, and mixed-type values
   while also proving nested `capability_refs` remain blocked.

## Conservation and references

- All 133 master tasks and 213 view rows roundtrip exactly, before and after
  existing blinding. The existing partition retains 201 active view rows and
  explicitly excludes 12 cancelled rows with no overlap.
- The active-view catalog has **zero** unresolved declared targets, down from
  one distinct missing template. Task 89's existing validator reports zero
  errors after reproducing the original two errors.
- A separate canonical-authority check covers 127 Requirements, 139 complete
  Source Blocks, and 1,132 declared link records. All declared targets resolve;
  complete parsed JSON survives encoding and expansion. This check does not
  claim that the local source manifest or Chapter 5 readiness is current.
- The new multi-chunk regression deliberately uses different task orders in
  the two views and a task present in only one view. Every task's paired views
  stay in one batch; expansion maps reconstruct all rows in their original
  per-file order, with no duplicate or lost values.

| Codec-only corpus | Original bytes | Encoded bytes | Reduction |
| --- | ---: | ---: | ---: |
| Complete triplet | 1,138,729 | 817,219 | 28.23% |
| Existing blinded triplet | 1,130,085 | 811,735 | 28.17% |

These numbers are not final model-request savings. The fixed small probe still
selects raw: encoding grows the complete request from 2,477 to 3,681 bytes.

## Verification

**227 passed, 1 skipped, 31 deselected; 24 subtests passed.**
The selection covers the codec, input integrity, synthesis, Capability contracts,
incumbent review, CLI, shared transports, Knowledge HTTP behavior, and Capability
recovery. It uses the same scope as the preceding review: `test_mvg_*` remains
excluded for its documented pre-existing fixture issue, and the skipped case
depends on an unavailable local real-model artifact. No validation was relaxed.
No .NET, Godot, or Windows runtime acceptance is claimed.

Evidence files include `task89-before.json`, `task89-after.json`,
`task89-classification.json`, `report.json`, `declared-link-audit.json`,
`model-probe-report.json`, `regression.log`, and `regression.xml`.

Reproduce from the Windows repository root:

```powershell
py -3 scripts/python/validate_task_test_refs.py --task-id 89 --require-non-empty --out logs/ci/task89-test-refs.json
py -3 scripts/python/check_capability_task_evidence.py --out-dir logs/ci/task-evidence-audit
py -3 logs/ci/2026-10-21/task-evidence-followup/check_declared_links.py
```

## Remaining formal gates

The explicitly requested Codex probe remains **blocked before dispatch, with
0 runner invocations**, because this environment has no standalone Codex CLI.
The pushed checkout also lacks the real local source manifest and Chapter 5
readiness. The prior Codex filesystem/no-tools isolation and exact-model
identity findings remain open. Read-only execution and the label
`codex-cli-default` do not prove those contracts.

Updating task authority can invalidate prepared input identities and Chapter 5
fingerprints. Recheck affected Task 89 readiness through its existing Chapter 5
workflow and prepare a new run after restoring genuine local evidence; do not
reuse or relabel stale readiness. This patch does not rewrite readiness or
existing run journals. A verified runner and a real raw/encoded comprehension
check, followed by controlled Capability acceptance, remain prerequisites for
default promotion.
