# Epic 4 Context: Bounded Runs, Global Audit, and Authority-Safe Completion

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让操作者能在有明确费用边界的单一 MVG 工作流中恢复、终止、审核全局冲突，并仅在全部计划证据有效时宣布规划完成。普通跨 Capability 重叠无需重开历史，真正来源冲突必须显式记录影响与替代顺序。规划产物始终不能改写产品或运行时权威。

## Stories

- Story 4.1: run 预算与持久恢复状态
- Story 4.2: 全局冲突审计与显式 reopen 闭包
- Story 4.3: 权威安全的规划完成报告

## Requirements & Constraints

每条稳定硬问题最多修复三次，之后从不可变来源及已接受前驱创建干净上下文，不传失败 proposal、findings、prompt 或 workspace。单 candidate lineage 累计最多64次模型调用；run 限额为正整数 `mvg.run_invocation_limit`，缺省192，准备时保存值与来源。只有准备工作不扣模型调用预算；dispatch 前持久预留，dispatch 后超时、transport失败或坏输出仍扣账。恢复允许精确匹配的完成 receipt，缺响应不能免费重试或隐式扩额。

当前增量默认只修当前范围。重复 Requirement、共享 Contract、重叠操作动线本身不是硬冲突。只有来源证据支持的真实矛盾才能产生 reopen 计划，必须说明受影响 Capability/flow、证据、无效后继、替代顺序及替代选择。所有较晚累计后继默认失效，除非确定性 rebase 证明精确 base hash 与 accepted-predecessor 集合不变。

全部 Capability 必须完成三个候选的独立准入、比较选择及原子累计提交，之后执行最终全局确定性一致性审计。审计显示通过项、硬冲突、待实现义务、证据缺口和运行时状态，不能在评选后增加一次整批 LLM 语义否决。`source_gap` 与未解决真实冲突阻断 planning_complete；planned 测试义务不等同于失败，但不能被报告为已运行。

## Technical Decisions

coordinator 拥有生命周期、预算及 selected baseline，worker 仅返回带身份的结果。checkpoint 根据 run、Capability、顺序、base/proposal/receipt hash 确定身份，唯一提交点原子写入；恢复验证 canonical payload 和完整祖先链。相同事务重复恢复 no-op，不重复计费或合并，不匹配则阻断且保留诊断。reopen 不创建第二套任务或 MVG 生命周期，历史证据不可篡改，替代选择仍需三个完整准入候选。

准备来源包括精确 Capability 快照及顺序、Chapter 5 readiness、Requirement 范围、完整证据和已接受前驱。来源漂移要求新的准备，不用日志摘要替代缺失权威。新页面点击是新运行，不能复用旧候选证据。

Requirement 路线、唯一处置和证据分别以 pair、Requirement、evidence pair 记账；引用数不能增加完成数。最终审计与局部准入、恢复使用同一规则，不重复发明来源或完成模型。旧数据保留唯一处置、授权和证据，hash-bound历史只读投影。

GDD/Requirement、133项 Taskmaster任务、Contract、测试与运行时状态由各自工作流拥有。MVG只能写规划证据与manifest投影。运行时验证只能由正式MVG运行时验收给出；任意规划receipt、模型文字或页面状态均无该权限。违反写入边界先阻断并在logs记录，不事后用成功状态掩盖。

receipt记录run/Capability/candidate lineage/attempt身份、来源与内容hash、错误类别、时间和状态；全部日志与证据放logs。区分准备、transport、runner、机器问题、语义硬问题、预算耗尽和全局冲突，禁止混作同一种失败。Windows目标、UTF-8与Python 3.12 CI兼容保持现有约束。

## UX & Interaction Patterns

保留CLI和Knowledge入口，进度和恢复选项来自持久receipt。页面不拥有状态权威，不因缓存显示而允许恢复或扩大预算；错误明确说明阻断对象和阶段。当前Epic不要求重做UI。

## Cross-Story Dependencies

Epic 1提供输入与准入，Epic 2提供atomic selected checkpoints，Epic 3提供唯一记账；本Epic消费它们进行预算/重开/全局完成判断。预算先固定执行成本，全局冲突规则再约束历史影响，最终报告统一所有证据与权限边界。owning workflow、Skill与验收文档须同实施同步，并区分已部署与尚未迁移的目标能力。
