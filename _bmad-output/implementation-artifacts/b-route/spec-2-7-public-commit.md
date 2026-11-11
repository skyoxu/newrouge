# Story 2.7: shared public commit implementation

Status: in progress; implementation and scoped checks exist. Original verify
is running; publish/read and native Step 4/5 acceptance remain pending.
Frozen execution base: `22162e2a15e344ddcf0cbab0f8b1d0d5a1834b77` in R56.
Current documentation baseline: `d95547ad19d39bfda692047305fbe204f4d403b2` in R59.
Earlier R43 base: `9c690d94932a89c4fc4a8f60b5e5ee476adcc86d`.
The recovered R42 source snapshot is retained as provenance, without acceptance.
Refs: original epics.md Story2.7 AC1-6; architecture planning-records.md:46-63;
workflow-contract.md; verification-contract.md; ADR-0040.

## Current execution record

The original apply owner returned and its frozen targets reached their after
images, but its host post-control failed with OS exit 1. That failed result
and pending claim remain preserved. The subsequent read-only applied-state
recovery completed with OS exit 0; it did not replay apply or model requests.
The original verify process started on 2026-11-10 at 16:07:16 UTC under the
same operation. Its Task-root output is
`logs/ci/2026-11-09/story27-r56-zero03-verify-02`, with original held-process
supervision in `story27-r56-zero03-verify-normal-env-supervision-05` alongside
it. As of the 17:10 UTC observation, no final unit or supervisor receipt existed.
This is execution in progress, not verified publication or Story acceptance.

## Owned implementation

Use `_b_route_commit` through the existing adoption CLI's explicit apply/verify/
publish/read stages. The journal retains the exact Story2.6 operation and index;
a versioned auxiliary commit intent adds crash-visible lifecycle and an owned
pending marker. Six formal records keep their original schemas and registry.
The current native/adoption producer remains the admission owner; no model,
allocator, alternate mutex or Task completion state is introduced.

## AC map and authored checks

- AC1: initial fresh reserved context, whole future-bundle checks, exact target
  before/after classification at every write, after skip, unknown edit/source/
  sharing refusal retention. Tests: after/unknown, required source drift,
  re-signed dropped observation, resumed frozen allocation/review mismatch,
  actual Windows sharing refusal.
- AC2: actual after target and authority re-read; strict complete bundle checks;
  immutable minimal receipt binds original frozen operation. Existing eight
  projection tests cover identities, independent references and digest cycles.
- AC3: final complete catalog payload in durable intent, replace-last, one
  receipt for all frozen affected scopes, independent plan/binding references,
  unrelated preservation and safe rebase. Replan freezes prior current head
  scopes before host review. Tests cover durable ordering, unrelated publication
  between steps, retained catalog attempts and original revision preservation.
  Plan-only publication reads existing governance via the shared safe byte owner.
- AC4: the actual implemented bootstrap combination is a real admitted native
  plan plus policy and genuinely empty origins in one reviewed operation, with
  no Task/triplet/Chapter5 witness requirement. No fake Task/readiness/scene.
  Independent policy-only producer coverage is not claimed.
- AC5: explicit committed records context, receipt-sealed historical log proof,
  real related source and formal target verification, shared pending protection,
  catalog before/after reread, scoped semantic key and clone without logs.
  Candidate external validation stays strict. Tests include re-signed missing
  proof authority, source drift, catalog drift, unrelated scope identity and
  existing declared Task status projection versus Acceptance changes.
- AC6: complete no-op writes nothing; each fixed crash boundary retains active
  pending; published-but-uncleared marker blocks. Terminal history must connect
  its saved catalog after image to actual publication, including after a replan;
  a re-signed phase or disappeared marker alone cannot release the active claim.
  Windows tests use actual file
  sharing and fixed synthetic-owned process crash/restart. Fresh child apply
  uses only an explicit synthetic capture seam; commit/records/leases/IO remain
  real. No arbitrary system
  reboot, power-loss or database isolation claim.

## Validation ownership and sequence

The author may only parse/compare source AST, JSON and hashes. Root alone runs
tests, child fixtures, public stages, models and Git. The source author has not
executed any listed check. First run targeted new tests and affected 2.6 journal,
scope/review/CLI regressions, then required real Windows sharing/process checks.
Use the maintained deterministic selectors without deleting prior modules.

Formal Story2.6 prerequisites/acceptance are separate from this offline work.
After final integration/source freeze, Root must obtain then-current qualified
native/protection/review evidence and a legal fresh operation path, perform the
public commit/read scenario and formal Step4/Step5. Old subject/policy/proof
artifacts are retained with their original epoch and never relabeled. Default B,
Task readiness, runtime completion, automatic recovery/compensation and future
Task write producers remain outside this implementation's grants.

Details and evidence boundaries: docs/workflows/story-2-7-public-commit.md.
