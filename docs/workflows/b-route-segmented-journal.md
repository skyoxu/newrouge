# Segmented workflow journal owner

This is the opt-in segmented protocol's persistence owner. It does not activate
legacy Capability/MVG runs, grant an original checkpoint, or replace a model
receipt. The existing workflow remains the default.

## Authority and ordering

`_b_route_segmented_runtime` produces the actual new-run birth/current/funding
witness. `open_workflow` obtains it before creating locks or auxiliary files.
Old runs without a valid original birth are rejected before writes.

Writes use the original `_mvg_capability_recovery.operation_lock`, original
run `coordinator_lock`, then a short original registry `coordinator_lock`.
The operation/run locks cover the workflow session; the registry lock is released
before model work. A second cooperating session cannot create another active
request. Status/verification uses `read_only=True`, creates no lock or auxiliary
files, repairs nothing, and closes the observed metadata bytes after replay.

The fee authority is the original `run.json` `capability_selection.calls`,
`total_invocations` and `lineage_invocations`. Auxiliary records contain no
independent quota. Current funding retains the prior same-profile occupancy and
all campaign paid/unknown occupancy, including occupancy from archived registry
epochs. Plans contain static ceilings and node count, never a current paid-count
assertion; actual funding is read fresh from the original owner. Limits remain Capability 96, MVG 192, campaign 290 and
64 per attributable lineage. Shared non-selection work charges every involved
lineage once and the global ledger once; public selection is not candidate
regeneration. The full remaining plan must fit before another reservation.

## Publication and recovery

The original `_planning_apply_journal` owns multi-file roll-forward. Shared
journals live in the original registry store's `activity/segmented-journals`.
Each node has a permanent `q/n<ordinal>/claim.json` created exclusively. Its
identity binds the actual request, ordered node, actual parent result digests,
funding, epoch, original native after-image and original journal reference.
Reserve publishes the claim, original native debit, auxiliary state and original
registry `segmented_runs` head in one original journal transaction.

Completion requires the genuine core result and original artifact verification,
the genuine completed prefix, and independent thread/turn verification. It
publishes an exclusive `complete-claim.json`, result, original native outcome,
auxiliary state, settled active head and registry head through the same original
journal. The registry head pins the permanent claim's **raw** digest and native
after-image, never the mutable journal's whole digest. There is no self-reference
through the registry after-image.

At most one original pending publication is admitted across these workflows.
Explicit `session.resume()` rolls forward only that exact metadata transaction;
it never authorizes dispatch. A lost reservation return, partial claim, unknown
receipt or unknown model outcome cannot be retried, refunded, renamed or cleared
by this owner. A partial permanent claim which differs from both original
before/after images remains blocked. `fail` records a diagnostic conservatively
as unknown and keeps the original debit and active claim.

`inspect_native_history` is a pure original journal/claim/row linkage reader for
the runtime funding owner. It reports actual native rows separately from pending
encumbrance, and reports a pending native target only when its actual raw bytes
equal the original journal's exact before or after image. It does not issue
native qualification. The existing registry and its clear archives provide
cross-run high-water linkage; this does not claim to detect hostile deletion or
rollback of every original authority and all disk evidence together.

## Public session API

- `open_workflow(root, *, run_dir, plan, read_only=False)` returns a scoped session.
- `snapshot()` replays persisted actual result evidence once and returns ordered
  records plus in-process genuine `verified_result` tokens. A pending or unknown
  request returns a blocking diagnostic with `may_redispatch=False`.
- `workspace(node)` returns a fresh, absent final sandbox; the renderer alone
  creates its exact input files. `timeout(node)` asks the original runtime's
  current time-budget owner.
- `reserve(node, identity, *, rendered_request, completed_prefix)` requires both
  genuine factory tokens and exact rendered full-envelope validation before
  consuming the permanent claim and original debit.
- `complete(reservation, verified_result)` records actual verified completion.
- `fail(reservation, diagnostic)` preserves unknown occupancy without refund.
- `finalize(completion_token)` publishes exclusive auxiliary `q/completion.json`
  through the original journal, with all ordered paid result digests bound. It
  changes no fees, selected pointer or original formal registry entry.
- `resume()` is metadata-only, not request recovery or redispatch.

The runtime alone invokes `publish_born`/`resume_born` after actual qualification
under the original lock order. These JSON-only primitives publish a new initial
zero-call run and its birth metadata; they cannot restore a paid legacy run.

## Validation boundary

The focused journal tests use isolated synthetic TEMP roots and explicitly mock
only unavailable born/rendered/result qualification boundaries. They exercise
the original locks, registry head updater, journal publication, claims, native
ledger and interruption paths. These tests establish no paid execution, actual
model quality or native qualification. Root runs them after the common source
barrier; no actual dispatch was performed while implementing this owner.


## 2026-11-07 Root实际检查点

此前AST/未执行记述是历史时点。上一源码纪元的实际执行结果与失败边界见 `../../logs/ci/2026-11-07/segmented-wire-v1-checkpoint/report.md`；86/87受影响方法已有通过记录，1项输出容量错误仍保留，不能称完整通过或真实模型/原生资格。


## 新response wire实际离线结果

Root在完整723项源码/文档屏障下实际执行31项定向测试，全部通过、无跳过，前后hash一致：新wire/展开守卫8、原paid单节点协议/冷回放1、完整workflow13和candidate9。原64551B/29262输出失败保留在前一c55e3b07检查点，未事后改判。独立只读复核未发现可确认新增P1/P2，仅在其明确静态范围内。

证据见 `../../logs/ci/2026-11-07/segmented-response-wire-freeze/report.md`。未重跑不受影响的先前测试，不声称整套121同时全绿。项目原生模型/资格/OS子进程调用均0，本轮只有合成离线协议；真实模型质量、正式资格、默认B启用仍未取得。此段与换行规范化是测试后状态更新，测试当时文档原字节已归档，所有生产/测试代码字节未再改。


## R58 isolated integration status (planned)

Original R23 evidence above retains its original epoch. The R58 combination
with current R57 shared owners is not yet validated or formally enabled.
See `execution-plans/2026-11-10-r23-segmented-to-r58-opt-in-migration.md`.
No model/native/funding authority, default activation or old-proof requalification
is granted by this transplant. Existing ADR-0042 thresholds remain unchanged.


## Financial-prefix DATA validation

The auxiliary financial-prefix grammar is owned by
`scripts/python/_b_route_segmented_fiscal_prefix.py` and [ADR-0054](../adr/ADR-0054-segmented-financial-prefix-data.md).
It validates a supplied complete schedule claim and ordered native-bound prefix,
including retained STOP and unknown states. It does not publish a claim or grant
permission to append, dispatch, retry or release a hold. Live graph completeness,
the genuine allocation lease and native/source/result qualification remain the
original owners' responsibilities. The R59 migration checkpoint and focused
neutral tests are separate from old R23/R58 evidence and actual paid validation.
