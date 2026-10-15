---
title: 'Story 4.1：持久化 dispatch 预算与恢复终态'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: 'c7357af69e3f29979fcf59898b442e9205978ef6'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** run limit 当前只在执行时取默认值，缺少冻结来源；预留后仍做准备工作，执行异常和预算终止也可能被包装为普通候选失败。

**Approach:** prepare 绑定正整数预算及来源，在实际模型 dispatch 边界恰好一次持久预留；区分 lineage 退役与 run 耗尽，恢复不退款、不隐式加额。

## Boundaries & Constraints

**Always:** 默认 run limit 为 192；lineage 64 次及每硬问题三次修复不变。超时、坏输出和 transport 失败只要已 dispatch 就扣账，准备失败不扣。进度从持久 receipts 派生。

**Ask First:** 无；预算默认及终态来自已批准 AD-7/NFR-003。

**Never:** 不跑付费模型、Godot、远程 Git；不改任务/Capability/GDD/正式 manifest 或游戏文件；不自动增加预算、不重用失败上下文；不改旧 run 的已绑定 hash。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| LIMIT | 默认或显式正整数 | prepare 持久化值、来源及身份绑定 | 0/负数/bool/float 拒绝 |
| PREPARATION | 复制、schema、prompt、freshness/preflight 失败 | 无 dispatch、零新增费用单位 | 保留准备诊断 |
| DISPATCH | 超时、坏 JSON、transport 或返回前中断 | 每次实际 dispatch 恰好一个持久单位 | 无输出不退款 |
| EXHAUSTION | lineage 64 或 run 达限 | 分别 retired / run_blocked_budget_exhausted | 保存前缀，恢复不再调用 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- `prepare/_prepare_impl/main` 新 limit 参数和来源冻结；`invoke_for` 的 lineage reserve 当前在沙箱准备前，旧 admission 的 before_invoke 还会重复预留。
- `scripts/python/_mvg_capability_selection.py` -- `reserve` 当前 run/candidate 账本，`verified_prefix` 恢复预留窗口，selector preflight 后仍有 factory 准备；terminal catch 不得吞专门 budget 状态。
- `scripts/python/_mvg_capability_generation.py`, `_mvg_capability_append.py` -- evidence/generate/semantic 的 call 及 before_call；使用单一 dispatch 预留权威和一致 attempt ID，worker 计数是投影而非第二次收费。
- `scripts/python/_mvg_input_envelope.py` -- index/state/envelope 固定预算，不让直接修改 run.json 扩额。
- `scripts/python/_project_health_planning.py` -- recovery_available/终态投影，识别预算终止，不自动复用成新预算。
- `scripts/python/tests/test_mvg_capability_append.py` -- public run budget、reserved interruption、preflight、三次修复和 context restart；fake runner。
- `scripts/python/tests/test_mvg_planning_contract.py`, `test_mvg_checkpoint_replay.py` -- durable/concurrent 预留及 replay 费用守恒。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted 门禁依据。

## Tasks & Acceptance

**Execution:**
- [x] `plan_mvg.py`, `_mvg_input_envelope.py` -- 冻结默认/显式预算及来源。
- [x] coordinator/worker/runner -- 将预留统一到实际 dispatch 边界。
- [x] 终止/恢复消费者 -- 独立预算错误、无免费重试或加额。
- [x] 离线矩阵及 owning docs -- 证明零准备费用、一次 dispatch 一次扣账。

**Acceptance Criteria:**
- Given a new run, when preparation completes, then its positive run invocation limit and source are durable and cannot drift on resume.
- Given a dispatch reservation, when execution fails or is interrupted, then it remains charged exactly once and exhaustion preserves recovery evidence with distinct terminal state.

## Design Notes

默认策略 coordinator 总账为权威，scope worker 与 lineage 文件仅作可核对投影；可用 reservation ID 消除崩溃窗口歧义，禁止靠多个独立计数器“差不多一致”。未收到响应视为已预留的未知执行，不能免费再调用。新请求需新 attempt，完整 hash-bound receipt 可本地恢复。旧策略最低限度去除重复扣账，不保留无效新兼容层。

干净 Capability context restart 清空失败上下文，仍消耗同一候选累计 lineage 预算，不重置64。新协议恢复先验完整链与预算绑定，旧产物只读保持历史身份。证据记录 run/candidate/Capability/phase、reservation、时间、错误类和计数，不输出密钥。不得把执行预算错误当语义 finding。

日志放 `logs/ci/2026-10-15/story-4-1/`，实现代理不提交。

已核实的 dispatch 边界：`generate_append` 当前在 `call(...)` 后仍验证 envelope；`invoke_for` 在 lineage reserve 后仍创建目录、复制输入、写 schema/prompt；selector 在 coordinator reserve 后仍调用会做上述准备的 factory。应把实际 dispatch callback 传到完成准备后的唯一 runner 调用点，coordinator、worker 和 lineage 使用同一 reservation 身份。保留可离线注入的 runner，不让 fake runner 绕过预算门。selector 不属于 candidate lineage，但计入 run 总额。准备未完成时不得发表 running attempt，dispatch 预留必须先持久化。

公共参数实际还经过 `dev_cli.py` 的 parser 与 `dev_cli_builders.build_plan_mvg_cmd`，默认值及显式值都须到达 prepare，来源与值一起进入 index/envelope/state；不能只改底层 parser。当前 `test_public_run_budget_boundary_preserves_prefix_and_stays_terminal` 通过直接修改 run.json 降额，冻结模式部署后须改为在 prepare 时传值，并单独断言改 run.json 被拒绝；旧的 insufficent-candidates 预期应更新为专门 budget 终态，不更改其保留前缀与零恢复调用断言。lineage 历史文件视为可验证投影，恢复预留崩溃窗口不得改已准入 payload 的内容/hash。

## Verification

- 独立预算矩阵与 public fake runner：默认/非法值、pre-dispatch失败、timeout/malformed/transport、预留中断、并发、两类耗尽及无调用恢复。
- 受影响 repair/restart、checkpoint replay、Knowledge recovery 定向回归。
- 改动模块 `py_compile`；`git diff --check`。

审查后的定向结果：请求身份与旧账兼容10项、selector恢复7项、dispatch身份6项全部通过。主代理另独立复验selector原子中断与预算终态2项通过；证据位于`logs/ci/2026-10-15/story-4-1/`。较早195项契约回归已通过，未重复宣称为最后修补后的全套结果。无收费模型或引擎执行。

## Suggested Review Order

**预算与唯一记账**

- 从prepare冻结预算及来源开始。
  [plan_mvg.py:4369](../../scripts/python/plan_mvg.py#L4369)
- coordinator原子预留，并同时发布selector尝试。
  [_mvg_capability_selection.py:359](../../scripts/python/_mvg_capability_selection.py#L359)
- 耗尽恢复保留专属终态，不隐式扩额。
  [_mvg_capability_selection.py:392](../../scripts/python/_mvg_capability_selection.py#L392)

**实际调用与恢复身份**

- 完成沙箱准备及预检后才能扣账。
  [plan_mvg.py:4757](../../scripts/python/plan_mvg.py#L4757)
- 输入、输出和回执绑定同一次调用。
  [_mvg_capability_generation.py:371](../../scripts/python/_mvg_capability_generation.py#L371)
- 页面显式恢复保留耗尽运行。
  [_project_health_planning.py:265](../../scripts/python/_project_health_planning.py#L265)

**定向验证**

- 公共selector中断与耗尽覆盖真实协调路径。
  [test_mvg_capability_append.py:584](../../scripts/python/tests/test_mvg_capability_append.py#L584)
- 身份变异、旧记录和输出证明逐项验证。
  [test_mvg_dispatch_identity.py:15](../../scripts/python/tests/test_mvg_dispatch_identity.py#L15)
