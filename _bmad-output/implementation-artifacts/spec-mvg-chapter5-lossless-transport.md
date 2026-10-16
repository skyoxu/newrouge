---
title: 'MVG Chapter 5 完整输入去重传输'
type: 'bugfix'
created: '2026-10-15'
status: 'in-progress'
baseline_commit: '8383b7a2091e23680d7b071bbc0e631aa886ff64'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 页面 MVG 生成在模型调用前被输入上限阻断。Chapter 5 核心约 1.86 MB，其中重复嵌入已准备 readiness 原文内的 fingerprint payload；辅助文件分片不能缩小核心。

**Approach:** 模型仅完整消费当前 Capability、受影响 flow/handoff 及权威引用的关联证据；全仓冻结来源与全部 readiness 仍由机器校验。模型投影中重复 payload 以路径、文件 hash、JSON Pointer 的可还原引用替代；所选 readiness 全文通过现有证据通道传输。核心自身超限时立即停止无效递归。

## Boundaries & Constraints

**Always:** 全局机器校验保留全部 Chapter 5 task、ready 状态、身份和原文；模型保留关联任务及全部关联证据。记录确定性的来源选择和排除原因，校验去重引用可精确还原。遵守 ADR-0005；冻结 envelope、freshness、候选隔离、预算和准入规则不变。

**Ask First:** 扩大模型预算、改变权威来源或启动新的付费全流程。

**Never:** 截断关联来源、摘要代替原文、放宽输入上限、缩小全局机器校验范围、复用旧模型证据；修改任务三联、GDD、Capability 或游戏文件。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 预期 | 错误处理 |
| --- | --- | --- | --- |
| 重复 payload | envelope 与冻结 readiness 相等 | 引用可精确还原，原文完整传输 | 不重复内联 |
| 来源异常 | 缺失、hash 或 payload 不一致 | 模型调用前停止 | 明确来源错误 |
| 核心超限 | 不含辅助正文仍超限 | 不继续递归拆分 | 保留容量错误，调用数为零 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_capability_generation.py`：`complete_scope_context` 组装输入；`input_prompt` 负责分批；生成和独立准入共享此链路。
- `scripts/python/_mvg_input_envelope.py`：只读冻结与 freshness 权威，不重封旧输入。
- `scripts/python/_mvg_evidence_transport.py`：`plan_transport`、`plan_errors` 校验全部分片和身份。
- `scripts/python/tests/test_mvg_capability_append.py`、`test_mvg_evidence_transport.py`：现有完整传输与公共生成回归。
- 只读失败证据：`logs/ci/knowledge-planning/planning-5bd32a8d528846b99361e3bba9dd2a1f/job.json`；原隔离 run 保持不变。

## Tasks & Acceptance

**Execution:**

- [x] 上述测试文件：先证明大 fingerprint 重复及无效递归，再覆盖完整首、中、尾原文、引用还原和来源异常。
- [x] `_mvg_capability_generation.py`：加入可验证去重投影，保留全部原始证据及身份。
- [x] `_mvg_capability_generation.py` 与相关测试：根据当前 Requirement/受影响 flow/entrypoint/test 的真实任务归属，保留完整任务视图、Acceptance 引用、对应 Chapter 5 readiness/reconciliation 和权威来源；保留显式 evidence-ref，拒绝必要来源缺失。记录全局与模型范围，证明未削弱全局机器校验。
- [x] `_mvg_evidence_transport.py`：增加不可缩小核心的预检，仍逐批检查最终包装请求。
- [x] 原失败输入：新建 `logs/**` 定向验证目录，仅重放组装和容量预检，不执行模型或改旧 run。
- [x] `_mvg_capability_generation.py` 与测试：历史准入 transport context 没有 `evidence_selection` 时，从冻结 prepared 数据重建原提交 `8383b7a2091e23680d7b071bbc0e631aa886ff64` 的完整全仓输入投影，严格核对其旧字段、完整 Chapter 5 和原来源正文；不跳过验证、不重写历史 proof、不把新关联范围记录默认视为旧格式。新增记录删除 selection、历史正文/hash/任务/scope 漂移和跨 run 复用仍须阻断。旧读取只用于恢复，页面新生成仍走新关联范围和新证据。
- [x] `_mvg_evidence_transport.py` 与测试：二分装箱后尝试合并可容纳的相邻批次，完整保留 source/part 顺序、原文、空文件和所有 hash；只用最终包装请求的现有 probe 判断容量，不以估算代替最终准入。新增可复现的装箱浪费测试，证明批次减少且精确重组、拒绝异常不变。若跨源或单文件分片无法继续合并，停止搜索；不引入新压缩协议或无界容量搜索。
- [ ] `logs/**`：在新目录复验四项冻结输入的两阶段容量、批次和 64/192 调用限制；不消费旧模型结果。先跑新增定向测试及 transport/envelope 集合，公共模拟入口只选一项验证；不重复整套慢测试，不调用真实模型。预算仍不满足则如实交接，不扩大预算。

**Acceptance Criteria:**

- Given 原失败冻结输入，when 构建关联范围的生成与准入请求，then 核心和所有实际包装批次均遵守现有上限，所选来源正文可完整重组。
- Given 跨 Capability 关联或额外 Acceptance/authority 引用，when 选择证据，then 完整包含这些来源及对应 readiness；无关来源仍接受全局机器校验。
- Given 去重引用，when 本地还原，then 与原 fingerprint payload 完全相等，原 envelope hash 不变。
- Given 引用缺失或内容漂移，when 预检，then 调用数为零且不能进入语义准入。
- Given 原格式完整 transport proof，when 本地恢复，then 严格核验冻结全仓投影后接受且旧证据字节/hash 不变；Given 新格式删除选择审计或旧格式内容漂移，then 不能借历史兼容绕过准入。
- Given 二分产生可合并的相邻批次，when 装箱收束，then 调用批次减少、全部字符按原序重组、每个最终包装请求均通过现有容量 probe；不能合并或非容量错误时不得放宽校验。

## Spec Change Log

- 2026-10-16：真实输入证明每个 Capability 重复传输全仓 572 份文件必超现有调用预算；用户明确选择“按关联范围完整传输，保留全局机器校验”。据此调整模型输入范围，不改变全局权威、完整性、预算和隔离边界；保留已通过的去重及 fail-fast 修补。
- 2026-10-16：用户批准继续“处理恢复兼容，再优化分片，保持完整传输、不增加预算”。新增严格历史投影核验与相邻批次合并，不引入另一套压缩协议，不启动付费生成；现有 682 次测算保留为优化前证据，不承诺仅靠装箱即可满足预算。

## Design Notes

实际 127/127 fingerprint 均可从各自冻结 readiness 精确还原。去重后的 Chapter 5 投影约 202 KB；此数字不是新阈值，最终必须用真实包装器逐批测量。原文不删除、不改写，仅消除重复内联。

## Verification

- `logs/ci/2026-10-16/mvg-chapter5-lossless-transport/scoped-regression.xml`：15 项关联范围、完整传输与来源边界定向测试通过。完整三文件回归未完成，不声称全量通过。
- `git diff --check`：无空白错误；未改变受保护权威与游戏文件。
- `logs/ci/2026-10-16/mvg-chapter5-lossless-transport/scoped-frozen-replay/summary.json`：原冻结输入中目标 manifest 的四个 Capability，生成/准入两阶段核心与全部证据分片包装容量预检通过；所选正文和 fingerprint payload 精确还原，全部 127 项 readiness 仍接受全局校验，原 run/envelope 未变。没有生成真实候选或真实审查报告，不能据此声称最终 synthesis 或模型全流程通过。
- `recovery-packing-targeted.xml`：本轮 transport/envelope 和六项 scope/Chapter 5 定向测试共 66 项通过；`historical-recovery-green.xml` 独立历史 proof 恢复及漂移负例通过；`packing-green.xml` 两项最终包装装箱测试通过。后两份是重叠验证，不能累计成 69 个不同测试。本轮新增恢复/装箱测试没有保存修补前 RED，不声称完成完整 TDD。
- 三层独立审查已完成；blind 与 edge 无发现，verification 确认一处 extraction snapshot 测试旧断言。仅修正该断言以匹配批准的关联范围，同时核验全局 snapshot 描述符与文件 hash 不变，保留正文与 audit 篡改检查。完整 oversized 公共模拟未重跑。
- `recovery-packing-replay/summary.json`：容量复验进程退出时只完成 7/8 个阶段，无最终 `status`，不算完整通过。七阶段批次由对应旧结果 166 降至 147，均精确重组；最后 node review 未完成，不推测批次或最终 synthesis 容量。另行只读复核原 run inventory hash 与复验前相同。
- `recovery-packing-public.xml`：当前代码的 `test_real_cumulative_generation_admission_and_proof_verification` 通过，122.44 秒，全程假模型；`snapshot-scope-final.xml`：全局 extraction 绑定与局部排除检查通过，1.58 秒。不代表真实模型或完整页面流程通过。

## Remaining Blocker

优化前当前分片计划的完整乐观测算为每条 lineage 226 次、整轮 682 次，已超过 64/192。优化后已完成的七个阶段共 147 批，加入四项各两次 synthesis 和四次 selector 后，三个候选即使完全不计最后 node review，也需 `3 * (147 + 8) + 4 = 469` 次，仍超过 192；每条 lineage 也已经至少 155 次，超过跨 Capability 累计的 64 次限制。469 不是完整整轮估算，不与 682 当作完整前后值比较；最后阶段未完成，不能宣称优化后精确总数。此测算只针对当前分片计划，不是理论最优分片下界；真实增量与审查输出还可能增加请求大小或调用数。

本轮模型调用为零，不提高预算、不截断来源、不启动已知无法完成的全流程。代码审查已完成，但优化后容量复验不完整且预算阻断尚存，规格保留 `in-progress`，不标记工作流完成。未提交、未推送、未重启服务；其他传输协议或预算调整仍需用户决策。

## Suggested Review Order

**输入与恢复边界**

- 从关联范围构建入口核对完整正文与全局范围区分。
  [generation:255](../../scripts/python/_mvg_capability_generation.py#L255)
- 历史投影独立重建，恢复不修改旧证据。
  [generation:383](../../scripts/python/_mvg_capability_generation.py#L383)
- 重新核验来源，拒绝新记录降级和内容漂移。
  [generation:454](../../scripts/python/_mvg_capability_generation.py#L454)

**可还原传输与装箱**

- 用冻结 readiness 原文精确还原去重引用。
  [transport:33](../../scripts/python/_mvg_evidence_transport.py#L33)
- 核心先预检，相邻批次只按最终包装容量合并。
  [transport:203](../../scripts/python/_mvg_evidence_transport.py#L203)

**测试证据**

- 历史完整 proof 恢复及漂移拒绝。
  [append-tests:921](../../scripts/python/tests/test_mvg_capability_append.py#L921)
- 合并不改字符、顺序或 hash，非容量错误继续抛出。
  [transport-tests:114](../../scripts/python/tests/test_mvg_evidence_transport.py#L114)
