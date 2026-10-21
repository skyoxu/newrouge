# Task-view evidence implementation review

Base: `4c580b5880bfceb8fe6e1a39fd356c290d945fd0` on
`fix/capability-synthesis-input-integrity`.

Status: deterministic codec and opt-in runner integration verified; default
transport remains raw. Formal rollout is blocked on current-source references
and real-model/environment acceptance. No formal Capability was generated or
applied, and no Taskmaster/Requirement/Source Block authority was edited.

## Implementation

- Strict reversible field sharing for task views of the same master task.
  Unknown fields and all semantic values survive, including missing/null,
  empty values, types, array order, and differences between views.
- Self-contained packets with declared links, complete content, external
  citation pointers, and a fixed guide. Source Block bodies remain whole.
- Frozen prepare-time opt-in, shared Codex/OpenAI request admission, and paired
  task-view batching. Default/raw runs preserve their existing representation.
- Exact roundtrip, field-address expansion maps, prepared/original provenance,
  hashes, explicit excluded-ID receipts, and recursive blinding/projection
  checks before dispatch. Audit files never enter payload enumeration.
- Raw fallback only when full encoded requests fail to reduce both bytes and
  estimated tokens. Invalid evidence does not get a fallback.
- Full source/Requirement batch comparison now uses canonical JSON hashes,
  closing the Python boolean/number equality gap independently of trial mode.
- A reproducible repository audit and fixed raw/encoded model probe. The probe
  is separate from formal readiness and never automatically enables compression.

## Corpus evidence

The repository has 133 master tasks and 213 task-view rows: 89 back and 124
gameplay. Both the complete original triplet and its existing blinded projection
roundtrip exactly. Coverage is 100%; 201 view rows are retained and 12 rows
owned by cancelled tasks 117-122 are explicitly excluded, with no overlap.

| Representation | Original bytes | Encoded bytes | Reduction |
| --- | ---: | ---: | ---: |
| Complete original triplet | 1,138,899 | 817,304 | 28.24% |
| Existing blinded triplet | 1,130,255 | 811,820 | 28.17% |

These are **codec-only corpus measurements**, not full final-request savings.
Full request accounting includes the guide, relation index, source pointers,
shared context, and output schema. The small fixed comprehension fixture grows
from 2,477 to 3,681 bytes and from 629 to 990 conservative estimated tokens, so
normal selection correctly chooses raw. Its model probe deliberately tests both
forms regardless of the size decision. The larger integration fixture exercises
actual encoded selection, original output IDs, and repeated preflight stability.

`report.json` includes complete task-view keys, source file hashes, object/row
counts, removed blinding paths, exclusions, and target diagnostics. Large corpus
snapshots/maps are reproducible with the documented audit command and are not
committed. `model-probe-report.json`, `regression.log`, and `regression.xml` are
adjacent evidence files.

## Remaining gates

1. Task **89**, both `tasks_back.json#89` and `tasks_gameplay.json#89`, declares
   `logs/ci/<date>/single-task-light-lane-t88-t89/shards/shard-001-t88-89/summary.json`
   in `test_refs`. This is a missing exact target, not a resolvable citation.
   The trial blocks it before any model request. No date was inferred and no
   authority path was silently replaced. The current active-view catalog has
   one distinct unresolved target; ADR targets resolve.
2. The requested real-model probe is **blocked with 0 runner invocations**:
   this environment has no standalone Codex CLI. Unit mocks are not real-model
   evidence. The Windows environment must run the documented fixed probe and
   a controlled Capability acceptance run before default promotion.
3. The pushed checkout still lacks the actual local source manifest and
   Chapter 5 readiness evidence needed for a formal current-project run.
   No replacement manifest or fabricated ready state was generated.
4. The prior review's Codex no-tools/filesystem-isolation and exact model
   identity findings remain open; this transport change does not establish
   those contracts. See the earlier `capability-branch-review/review.md`.

## Verification

**225 passed, 1 skipped, 31 deselected; 19 subtests passed.** Tests cover strict
JSON counterexamples, deterministic nested-value variations, corrupt packets
and maps, provenance drift, missing targets, declared dependency cycles, direct
Source Blocks, nested historical answers, whole-request fallback, frozen mode,
source boolean/number corruption, both runners, CLI, Knowledge HTTP behavior,
incumbent review, staged synthesis, and Capability recovery.

The selection excludes `test_mvg_*`, whose pre-existing readiness-fixture issue
was documented in the prior branch review; production validators were not
relaxed. The skipped case depends on a local real-model failure artifact absent
from the pushed checkout. `git diff --check` passes. No engine or Windows model
acceptance is claimed by this Linux test run.

Usage and exact trial boundaries: `docs/workflows/capability-task-evidence.md`.
