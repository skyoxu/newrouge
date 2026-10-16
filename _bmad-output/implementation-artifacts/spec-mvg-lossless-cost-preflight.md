---
title: 'MVG 完整证据传输成本修复与预算复算'
type: 'bugfix'
created: '2026-10-16'
status: 'done'
baseline_commit: 'da5bce2e9f73f968bd867c4bbb4cc7dddcfa2d92'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="用户已授权修复并重新测算预算">

## Intent

**Problem:** 完整证据分批读取重复发送核心及 Chapter 5 全局数据，现有分片计划的正常路径超过 64/192 次限制；预检仅计算每项两次生成/审查，未能在付费前识别不可完成路径。

**Approach:** 为模型输入实现可本地精确还原的去重表示，完整保留所有关联证据、核心权威及引用位置；补充阶段可完成性检查。用同一批冻结证据、真实最终包装器做零模型复算，并查证历史版本输入范围差别。

## Boundaries & Constraints

**Always:** 遵守 ADR-0005；保留全局机器验证、全部关联正文、独立审查和三个候选的隔离。每次真实 dispatch 仍计账；三次硬问题修复规则不变。旧 proof 字节/hash 不修改，新编码必须有版本绑定及精确还原检查。默认预算和请求容量不变。

**Ask First:** 扩大预算、改变权威范围、启动付费模型。

**Never:** 截断/摘要替代来源，跳过必要来源或审查，跨 candidate/click 复用证据，重写旧 run，修改游戏、任务三联、GDD、Capability 或 manifest。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 预期 | 错误处理 |
| --- | --- | --- | --- |
| 重复内容 | 同源字段、任务视图或原文重复 | 唯一内容完整送达，可逐字符还原 | 校验引用闭合及 hash |
| 非重复与特殊字符 | 中文、CRLF、末尾空白、空文件、保留键 | 完整还原，引用行号仍指向原文 | 不允许静默归一化 |
| 输入污染 | 删除/修改共享内容或引用 | 在 dispatch 前拒绝 | 来源/编码错误 |
| 剩余预算不足 | 当前分片及必要后续调用超过剩余额度 | 第一项模型调用前拒绝 | 写成本证据，不伪装语义问题 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_evidence_transport.py`：完整源 part、包装 prompt、schema、plan_errors、审查 proof；历史 plan 恢复需保留原包装行为。
- `scripts/python/_mvg_capability_generation.py`：`model_context`、`complete_scope_context`、`input_prompt`、`synthesis_context`、`preflight_runner_payload`；现有 task-view 无损去重仅用于 synthesis。
- `scripts/python/_mvg_capability_selection.py`：共享 run/lineage reservation、当前前缀及剩余预算。
- `scripts/python/tests/test_mvg_evidence_transport.py`、`test_mvg_capability_append.py`：现有全文、引用、公共生成及恢复负例。
- 只读证据：`logs/ci/2026-10-16/mvg-page-real-main/budget-diagnosis.json`；`logs/ci/2026-10-16/mvg-chapter5-lossless-transport/recovery-packing-replay/` 的七个 plan 与冻结 analysis-input；原运行不得修改。

## Tasks & Acceptance

**Execution:**

- [x] 先增加失败测试，覆盖无损去重、原文/行号、篡改及预算不足零调用。
- [x] 改进模型输入表示和装箱，减少重复核心与 Chapter 5 原文；不强求靠压缩必然满足预算。
- [x] 接入可消费的阶段成本证据及剩余预算预检，计算读取、synthesis、必要下一阶段及 selector；动态 review 产生后再次预检，不伪称能预知未来所有输出。
- [x] 用冻结证据复算全部四项的 inspect/review；若真实包装预检耗时大，缓存精确 request 的纯本地预检结果，禁止近似冒充最终包装验证。
- [x] 运行相关定向回归和独立审查；将历史差别、已测调用数及未测边界写入 `logs/**` 报告。

**Acceptance Criteria:**

- Given 原证据，when 新编码还原，then 所有源字符、原始字段、顺序和引用位置完整，输入冻结身份不变。
- Given 新编码任意污染，when 本地校验，then 准入前失败；Given 历史 proof，then 原格式仍严格验证且不重写。
- Given 已知当前阶段无法在剩余预算内完成，when 启动，then 真实模型调用为零，记录机器成本错误。
- Given 冻结四项输入，when 零模型测算，then 明确区分已测分片、必要基础调用、动态审查/修复余量及真实付费全流程状态。

## Verification

- `py -3 -m pytest scripts/python/tests/test_mvg_evidence_transport.py scripts/python/tests/test_mvg_capability_append.py`，日志保存于 `logs/ci/2026-10-16/mvg-lossless-cost-preflight/`。
- `git diff --check`；独立验证受保护文件未变、服务无生成锁、无真实模型调用。

## Implementation Results

新传输使用 v2 计划及请求内无损共享表示，旧 v1 prompt 保持原行为。阶段门禁计算已知读取、synthesis、未来最低工作与评选；恢复时仅恢复当前候选/上下文已经验证的成本，不重新计费，也不复用其它上下文模型证据。评选额外验证每条候选链的后续最低余额。纯本地预检缓存绑定最终包装请求和容量上限。

最终冻结四项八阶段共 184 次读取、8 次 synthesis；单条候选链为 192 次，三链加四次评选为 580 次，仍超过 64/192。此估算不是未来任意输出的完整预测，也不是模型账单。没有通过提高预算、减少来源或真实付费重跑来宣布通过。历史来源范围、逐项数据和证据见 `logs/ci/2026-10-16/mvg-lossless-cost-preflight/result.md`。

三层独立审查发现的恢复成本、selector 未来候选链额度、动态 review 验证及旧测试解码问题已修补。核心定向回归 74 项通过，六项受影响公共入口与动态 review 回归通过；另有恢复/selector 窄测试三项通过及增加 predecessor 负例后两项通过。后两组与核心用例存在交集，不累加成总数。公共回归使用 fake runner，不能作为真实模型语义通过的证明。未运行整套全部测试。

## Suggested Review Order

- 从阶段门禁理解当前已知成本及未知成本的边界。
  [_mvg_capability_generation.py:822](../../scripts/python/_mvg_capability_generation.py#L822)
- 检查共享总账、候选链及评选的未来余额。
  [_mvg_capability_selection.py:357](../../scripts/python/_mvg_capability_selection.py#L357)
- 检查请求内共享、原文位置和严格还原。
  [_mvg_lossless_context.py:53](../../scripts/python/_mvg_lossless_context.py#L53)
- 检查版本化传输与历史包装边界。
  [_mvg_evidence_transport.py:202](../../scripts/python/_mvg_evidence_transport.py#L202)
- 检查恢复、动态审查和零额外调用的回归。
  [test_mvg_capability_append.py:328](../../scripts/python/tests/test_mvg_capability_append.py#L328)
- 检查字符保存、污染及引用定位。
  [test_mvg_evidence_transport.py:29](../../scripts/python/tests/test_mvg_evidence_transport.py#L29)
