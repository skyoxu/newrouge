# Segmented Capability and MVG host entry v1

`scripts/python/plan_segmented.py` is the explicit opt-in host entry for
`newrouge.b-route-segmented-host.v1`. It supports `--planner capability` and
`--planner mvg` through the same four-phase engine. It does not change either
existing planner's default entry or old c4/m4 contracts.

## Source and plan authority

`_b_route_segmented_plan.build_plan(root, authority, partition_policy=...)` only
consumes the runtime's genuine opaque `PlanAuthority`. The issuer verifies actual
original 3A/current sources, raw bytes, membership, original rules, source policy,
campaign/profile/lineage occupancy, time facts and epoch. Dictionaries, copied
tokens, saved declarations and caller counters do not issue authority.

Plans contain only static `native_limit`, `campaign_limit`, `released` and
`worst_case_calls`. The real paid/unknown count is not copied into a plan as a
currentness assertion. The original owner derives it fresh before construction,
again at original birth CAS, and before every request. Profile limits remain
Capability 96 / MVG 192, campaign 290 and 64 per original candidate budget slot;
new business IDs or run IDs do not reset them. Original time and unknown
occupancy remain charged. No request count is a claim about physical provider
requests or service model identity.

The producer preserves the actual source owner's manifest, obligations, edges,
dimensions, fixed candidate identities/order and full original byte partitions.
Capability has two fixed candidates and MVG has three, matching the current
original profile. Each candidate gets complete generation, synthesis and
independent review, followed by equal-candidate joint panels and one final.
The production contract covers all 16 original business targets and exactly one
source-identity singleton per candidate; it does not use a preexisting candidate
as a substitute for paid generation.

`whole` is the conservative default: the complete domain forms one work unit.
Its minimal schedule is eight nodes for Capability and eleven for MVG. These are
planned logical calls, not approval to spend them or a promise of model quality.

`audited-components` is permitted only when the source owner actually consumed
an original independently audited semantic catalog. It groups connected source
obligations using the complete real dependency graph in both directions. It
does not split by token size or guess semantic independence. Generation and
synthesis slots stay within the original component; collection pieces are
assembled and checked by the existing complete business owner. Any actual
cross-component generated dependency requires the original full closure and
real paid independent/joint review, or blocks the plan. It is never hidden to
fit a request.

Final slot seeds are empty because the current source owner declares no separate
mandatory final output-slot field. This does not approve a summary-only final:
the engine must first prove complete paid original joint panels, independent
interaction-domain closure, exact original requests and no unresolved findings.
The manifest's actual mandatory final source segments and indivisible global
constraints remain unchanged. A future source contract requiring final direct
reading of an output slot needs its own explicit versioned owner field.

## Commands

Use the current implementation's source directory, with the original governed
artifact project supplied separately as `--root`:

```powershell
py -3 scripts/python/plan_segmented.py --root C:\path\project --planner capability --run-id fresh-cap --stage plan --planning-contract logs/ci/path/planning-contract.json
py -3 scripts/python/plan_segmented.py --root C:\path\project --planner mvg --run-id fresh-mvg --stage prepare --planning-contract logs/ci/path/planning-contract.json
py -3 scripts/python/plan_segmented.py --root C:\path\project --planner mvg --run-id fresh-mvg --stage execute
py -3 scripts/python/plan_segmented.py --root C:\path\project --planner mvg --run-id fresh-mvg --stage status
py -3 scripts/python/plan_segmented.py --root C:\path\project --planner mvg --run-id fresh-mvg --stage verify
```

These are command templates, not evidence they were executed.

- `plan` performs genuine source/funding capture and deterministic construction,
  then returns a JSON declaration without creating a native run or model call.
- `prepare` constructs from genuine current capture, then the original runtime
  independently recaptures and closes actual source/funding before zero-call
  birth. It cannot overwrite an existing namespace or retrospectively opt in an
  old run. An optional `--semantic-catalog` names an original audited file; its
  local raw reference alone is not approval. `--partition audited-components`
  affects construction only.
- `execute` reads only the immutable original `b/plan.json` from the canonical
  run home and calls the original shared new-protocol engine. It accepts no plan,
  partition, source, backend, effort, fee, claim or retry overrides.
- `status` verifies actual current authority and uses read-only original journal
  observation. A genuinely prepared zero-call run needs no auxiliary workflow
  initialization. Status creates no auxiliary file and repairs nothing.
- `verify` replays the persisted new candidate proof through its real owner. It
  does not grant old native admission, formal adoption or readiness.
- `resume-publication` is an explicit metadata-only operation for exactly one
  existing original pending transaction for that run. No pending transaction is
  not a reason to initialize or dispatch. A birth interrupted before its saved
  plan/run became readable requires its original birth recovery owner, not a
  different ID or an automatic prepare retry.

Errors return structured JSON with `status=blocked`, nonzero exit and
`automatic_retry=false`. There is no fallback backend or automatic request
retry. A blocked unknown result stays charged; neither `status`, `verify` nor
`resume-publication` authorizes another request.

## Input and evidence limits

The actual complete serialized input, including instruction, business schemas,
original/global bytes, declared prior evidence and official workspace wrapper,
must be at most **70,000 input tokens**. Output reserve is separate; input plus
reserve must remain at most the original **96,000** context tokens. Nodes reserve
26,000 output tokens, within the existing protocol maximum. The real renderer
measures the exact final wrapper before reservation and checks it again before
dispatch. Source-only estimates are not fit evidence; later generated values
may still make a request too large. An indivisible closure that cannot fit
blocks, without truncation or a fee/ID reset.

Three immutable request inputs are archived by the request owner outside the
model sandbox and bound into the permanent original reservation via
`input_archive_ref`. The journal's metadata-only paid-row view links an actual
native row, original journal, permanent claim, fixed workspace and auxiliary
progress without replaying a result or recursively invoking the core. The
runtime's separate paid gate still owns real birth/source/epoch/index and
archive qualification; a returned metadata dictionary is not a new permission.

This host entry produces new-protocol evidence only. It cannot claim old Story
2.5 acceptance, physical/provider model identity, actual provider reasoning
strength, merged main, default B activation, readiness or runtime acceptance.
The configuration remains official high, fresh ephemeral and no tools under the
original execution verifier.

## Validation status

New producer and CLI tests are offline drafts until Root runs the common source
barrier. Producer tests mock only the unavailable genuine PlanAuthority issuer
boundary and exercise real original byte/plan/slot validators. CLI tests use
explicit owner spies and never claim native or paid qualification. Journal's
already-passing baseline tests are only adapted for the new static plan shape,
archive field and metadata paid-row helper; actual results belong to Root's
execution logs, not this implementation document.


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
