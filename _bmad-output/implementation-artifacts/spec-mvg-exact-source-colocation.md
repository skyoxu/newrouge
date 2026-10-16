---
title: 'MVG 相同原文分批归并'
type: 'optimization'
created: '2026-10-16'
status: 'done'
baseline_commit: 'da5bce2e9f73f968bd867c4bbb4cc7dddcfa2d92'
review_loop_iteration: 0
context:
  - AGENTS.md
  - .agents/skills/plan-mvg/SKILL.md
  - C:/Users/weiruan/.codex/skills/test-driven-development/SKILL.md
---

## Intent

继续用户授权的完整证据传输成本优化。上一轮 v2 已支持请求内无损共享，但按文件递归分批会把多个文件的相同大块原文放到不同请求。将完全相同的大块原文优先放在同一批，减少重复传输和核心权威的重复包装。所有来源与每个路径的独立报告继续完整存在；这不是复用模型判断。

## Boundaries

当前工作区已有上一轮未提交修改，全部保留，不 reset、不提交、不推送、不重启、不启动真实模型。不改游戏、任务三联、GDD、Capability、manifest、模型配置、64/192 限额、850000 byte/96000 token 容量或语义准入规则。不截断、摘要、过滤关联证据或减少完整核心，不跨候选/点击复用模型证据。代码/测试/注释英文，说明中文，UTF-8，所有日志在 logs/**，编辑使用 apply_patch。

只实现以下 v3 大块归并，不同时重构 codec 或 inline/synthesis 流程。当前 v1 codec、显式相对行号、片段地址、CLI 每 part 独立报告和独立 review 全文读取保持。历史 v1/v2 原始计划、prompt、hash 和校验行为不变；仍可明确创建 v1/v2 计划以验证历史恢复，但新默认为 v3。这是明确历史 proof 恢复，不是无用兼容层。

## Code Map / 已确认原因

- scripts/python/_mvg_evidence_transport.py：part 保留 path/source hash/start/end/text 及 canonical part hash；audit_prompt 的 v2 表示已支持精确子串共享；plan_transport 当前按完整文件二分并相邻合批；plan_errors 严格校验原文件和片段顺序。
- scripts/python/_mvg_lossless_context.py：_spans 识别 exact raw JSON 块及长行，完全不解析/归一化文本；原编码行为本次不变。
- scripts/python/tests/test_mvg_evidence_transport.py：来源全文、地址、篡改、旧计划测试入口。
- scripts/python/tests/test_mvg_capability_append.py:1019：Chapter5 全文测试直接按批次串接同文件原文，新 v3 可跨文件归组，测试需先验证 plan_errors，再按 start 重组。相关只读消费者已经检索，生产代码没有其它按文件批次顺序拼正文的消费方。必要时只适配此类测试的重组顺序，不改完整性断言。
- scripts/python/_mvg_capability_generation.py：preflight_runner_payload 测量实际最终包装，现有调用方无需修改。
- 机器原型 logs/ci/2026-10-16/mvg-source-sharing/prototype_packing.py：取 _spans 和完整文件边界、只选至少 4096 字符并重复出现的块，按原文起点且最长优先选择无重叠片段。保留所有间隙和空文件，以完全相同的 text 稳定归组。每个原路径/offset 都保留自身 part，不复制任何报告。完整核心和容量不变，第一项 9→7 批，第四项 42→27 批；不是最终预算承诺。实现前可读原型，但生产代码必须先 RED 测试。

## Tasks & Acceptance

- [x] 先写失败测试，记录 RED，覆盖大块重复的分批归并、完整还原、独立路径报告、无重复及空文件。
- [x] 新计划版本 newrouge.mvg-complete-evidence-transport.v3，默认启用确定性的精确大块归并；v1/v2 显式恢复保持原代码路径和提示词。仍绑定 newrouge.mvg-lossless-context.v1。
- [x] v3 按原型稳定归组，相同原文各路径 part 紧邻，gap 和尾部不丢失。4096 字符阈值是确定性传输策略，不是语义选择；阈值以下或非重复原文仍完整发送。不能用 hash 相同冒充字面相同。
- [x] v3 plan_errors 根据同一确定性原始片段顺序验证实际 parts；递归容量拆分只能在该原始片段内部连续前进，不能跨越边界，缺失/重复/错序/内容或偏移污染一律失败。不得只 sort 后拼接而忽略篡改次序。每条实际 part hash 和来源 hash 仍校验；完整来源字节身份不变。v1/v2 继续原有严格文件顺序验证。
- [x] 定向 GREEN：完整 transport 测试及必要公共生成/准入窄回归，日志保留。禁止跑已知约17分钟的六项公共回归合集；本次既无 wrapper/预算/inline 修改，无需重复它。
- [x] 更新 owning docs 三处（plan-mvg skill、mvg-integration-acceptance.md、workflow.md）中相关版本说明，明确所有源完整、每路径报告、相同块同批以及旧 proof 不改。不承诺满足预算。

Given 多路径包含相同 >=4096 字符块，when v3 完整包装分批，then 精确块稳定同组，所有原文件逐字符还原并对各 part 独立要求报告；任何未报告路径不能通过。

Given 内容相同但路径/offset 不同、空文件、缺失来源、中文/CRLF/尾部空白，when 分批并恢复，then 每个来源完整且没有身份混淆。Given 删除、复制、错序或重算 part hash 后改变边界，when plan_errors，then 明确失败。

Given 显式旧 v1/v2，when 生成/校验相同上下文，then 原提示词和 hash 不因 v3 默认改变，且 v2 中篡改为归组顺序仍失败。先捕获 v2 golden hash。

Given 无模型的冻结复算，when 计算实际批次，then 区分实际测量、未知 proposal/repair，以及真实模型尚未测试；不以吞来源或加预算宣称通过。

## Verification / handoff

实施代理只完成上述代码、测试、文档任务并记录 RED/GREEN；主代理接管四项八阶段冻结复算和独立审查，之后勾选以下最终任务，不要因它未勾选重跑真实模型：

- [x] 主代理：用现有 recalculate_budget.py 新 output-name 测全部四项八阶段。脚本逐源重组检查需先按 start 排序；另外始终要求生产 plan_errors 返回空，不弱化实际生产顺序检查。实现身份包含发生变化的生产模块；旧目录不覆盖。
- [x] 主代理：三层独立审查、修补确认问题、git diff --check 和受保护文件检查，输出成本对比及剩余预算缺口。

实施代理可以直接调用 tools，不再调用 bmad-build/其它可能要求委派的 skill，不创建自己的代理。不改本 spec 的既有边界或范围；不完成主代理任务。只报告实测，不用预期结果替代证据。

## Results

29 项 transport 加 4 项公共生成/准入、Chapter5、历史恢复与 synthesis 定向回归共 33 项通过。三层独立审查没有确认新缺陷；第三层因线程容量在前两层完成后单独执行。没有真实产品模型调用。`git diff --check` 通过，游戏、任务三联、GDD、Capability 和 manifest 无修改。

冻结同口径复算读取批次 184→124；单候选链含 synthesis 为 192→132，三链加评选为 580→400，估算输入 token 下降 29.28%。所有 context/core/inventory/source bytes 一致，历史 plan 文件未修改。仍超过 64/192，不是完整真实模型运行通过。结果与未知成本边界见 `logs/ci/2026-10-16/mvg-source-sharing/result.md`。本轮按范围不提交、不重启服务。

## Suggested Review Order

- 从新默认入口查看 v3 与历史分支。
  [_mvg_evidence_transport.py:261](../../scripts/python/_mvg_evidence_transport.py#L261)
- 查看完全相同原文的稳定归组。
  [_mvg_evidence_transport.py:142](../../scripts/python/_mvg_evidence_transport.py#L142)
- 检查原始片段顺序与边界守恒。
  [_mvg_evidence_transport.py:335](../../scripts/python/_mvg_evidence_transport.py#L335)
- 检查独立路径报告及篡改负例。
  [test_mvg_evidence_transport.py:118](../../scripts/python/tests/test_mvg_evidence_transport.py#L118)
- 核对历史提示词及计划 hash。
  [test_mvg_evidence_transport.py:254](../../scripts/python/tests/test_mvg_evidence_transport.py#L254)
