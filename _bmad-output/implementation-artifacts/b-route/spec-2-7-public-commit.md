# Story 2.7: shared public commit implementation

Status: in progress, R50 bootstrap-protection repair; Story 2.7 execution and formal acceptance pending.
Active base: `862f00f2f94a253f5c86e9f2e84de840aba4449c` in isolated R50.
R48 integration and its original execution epochs remain separate historical evidence.
Story 2.6 AC1-5 were qualified at R47 `4d0aa32195b10347d92370b82c673043e550224b`;
no adoption/runtime grant follows, and R50 execution is not inferred from it.
R43 offline35 remains evidence of its original source epoch, not R48 execution.
The recovered R42 source snapshot is retained as provenance, without acceptance.
Refs: original epics.md Story2.7 AC1-6; architecture planning-records.md:46-63;
workflow-contract.md; verification-contract.md; ADR-0040.

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

## R50 初始保护实现备注（不改变原 AC / 冻结意图）

为让 AC4 的真实 nativePlan + policy + 真空 origins 组合能够先取得合法 protection 输入，新增通用 inventory/protection v3 的 required / initially_absent / unknown 推导，依据实际空三件套、当前 anchors 和有界 governed Git/path/owner 原件。原 manifest validator、Task 事实、旧 v1/v2、当前必要引用与 ADR-0049 历史附件角色不变。这里只修复初始空根与成熟 manifest 约束之间的 collector/archive/live 通路，不生成假 Task/manifest/PASS，也不授予 default B/readiness/runtime。

Root 仍须对当前 R50 源码实际执行定向合成 Git/collector/archive/CLI 正反检查，再获得当期真实 native/protection/review、合法新 operation、public commit/read 及正式 Step4/5。作者只做文本/AST/JSON/hash，R48 及旧 native 证据不改名为 R50 当前通过。具体实现与限界见 ADR-0052 及两份 inventory/protection owner 文档；原上文 AC1–6 和正式执行顺序完整保留。
