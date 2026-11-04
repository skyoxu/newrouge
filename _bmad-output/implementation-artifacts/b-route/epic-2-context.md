# Epic 2 Context: 无实施Task也能正式规划、审阅和采纳

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

在实施 Task 创建前完成正式来源审计、语义规划与持久采纳。规划者可将完整累计来源转换为 Requirement、Capability／Flow 定义或有依据的非 Flow 验证去向，并在没有 Task readiness、实现符号或既有场景的情况下，跨会话恢复同一组已采纳身份。这为后续任务生成提供可信交接，同时区分规划采纳、实施就绪和运行通过。

## Stories

- Story 2.1: 在Task之前形成累计来源Ledger与需求验收意图
- Story 2.2: 从完整来源独立审计遗漏与冲突
- Story 2.3: 准备Task无关且完整的规划输入
- Story 2.4: 描述可审阅的Flow及合法非Flow验证去向
- Story 2.5: 通过独立准入与有界评选选出可采纳候选
- Story 2.6: 冻结采纳操作并持久分配稳定身份
- Story 2.7: 一致提交采纳目标并以catalog发布
- Story 2.8: 按journal恢复中断并保留后编辑
- Story 2.9: 复用已提交完成规划并遵守epoch与reopen撤销
- Story 2.10: 从正式规划入口完成零Task采纳与跨会话复验

## Requirements & Constraints

- 注册完整累计来源，显式声明新增和退役。每个来源块须保留原始身份、定位、Requirement／验收意图投影或有依据的去向。保留共享约束、延期范围与未解决缺口；已记账不等于已满足。独立遗漏／冲突审计覆盖完整来源和 Ledger，不限于首轮 Requirement 或 Flow 引用。
- 大输入分批处理时保留原文、对象顺序、跨批引用和全局守恒证明。后续范围投影遵循受治理的依赖闭包。未知、损坏、截断或超容量输入明确阻断，不得静默丢弃。
- 正式 3B 规划要求有效 3A 证据，不要求 Task ID、Chapter 5 witness、readiness 或虚构对象。既有实现与 Task 仅作可选复用上下文。非 Flow 采纳须有来源支持的适用性依据和其他验证义务；标签、空字段不构成豁免。
- Flow 声明进入条件、成功结果、必要失败／取消／返回分支、交接、状态所有者、可观察结果和验证目标。在逻辑层描述适用的领域规则、C# 场景适配、绑定及场景实现。检查引用、所有权、可达性、循环分量和声明出口；允许合法循环，不声称证明任意程序终止。
- 保留成熟身份、历史和累计义务。显式重规划保留经审阅差异与 lineage。规划完成须通过全局记账核对和适用的独立语义准入；仅有已提交前缀或 planned 实现不足以完成。
- 确定性校验先于独立语义准入和评选。复用既有隔离 worker、仅协调器可提交的选择／checkpoint 及持久预算；worker 自报不能推进采纳，进程／lineage 变化不能重置预算。无进展时停止重试。记录真实阶段耗时、dispatch、复用和终止情况，未知值显式标明；不设速度、成本或 Task 数目标。

## Technical Decisions

- 沿用现有 Windows／Python 文件流水线，不新增数据库或 Task／MVG 状态机。来源与有效 ADR 管语义，Taskmaster 独占 Task 状态权威，Knowledge 保持派生。最小治理记录版本化；journal、payload 和原始 proof 放在 `logs/**`。
- 消费 Epic 1 的唯一共享 codec 和六类记录合同。策略、不可变 plan 修订、独立修订的 binding、origins、提交 receipt 和 catalog 存于 `docs/planning/b-route/`。复用既有 Requirement／Flow／Task ID；采纳操作持久保存新规划身份及查重结果。每个 Flow／共享定义只有一个 owner。路线成员关系、Requirement 唯一验证归属和去重证据分别表达，保留兼容的 `coverage_table` 投影。
- 基于既有锁和 journal 实现一套共享 `prepare/reserve/apply/verify/publish/recover` 服务。写入前冻结操作内容、权威依据、scope 及目标 before／after payload。同 ID 同内容复用分配结果，异内容冲突。先取得短时 metadata 保护，再按固定顺序取得 scope 租约；模型调用或长任务期间不持有全局 metadata 锁。
- 每个目标写前复验，只接受冻结的 before 或本操作 after，已应用目标跳过。核验全部目标与权威依据、持久保存不可变 receipt 后，最后原子发布 catalog，一次推进全部受影响 scope。receipt 不包含自身及最终 catalog 输出 digest；journal 保留最终 catalog payload。单文件替换或 pending 消失不能证明整体发布完成。
- 读取者在适用保护下校验 catalog、receipt 和相关实际文件，再重读 catalog。相关 pending 操作消歧前阻断，包括旧 Capability pending／journal；未知 scope 保守阻断。没有本地 logs 的 clone 仍须校验已发布链。零 Task bootstrap 允许空 origins／冻结 A 集合。
- 恢复核对实际文件和发布状态，保留后编辑与原始 proof，只推进合法缺失步骤。损坏、漂移或未知编辑产生诊断并停止。回退使用针对当前状态的新受审阅补偿操作。
- 仅复用已提交的 MVG 完成项：匹配单 Capability 完整规范化内容，验证原冻结 proof 和当前依赖／delta，并生成独立 adoption receipt。保留 epoch／reopen 撤销效力。新 MVG 执行不得恢复未完成候选／修复／审阅上下文；显式 Capability 证据恢复与文件 journal 恢复各守独立合同。相关变化使受影响证据失效，无关 HEAD／catalog／Task 状态变化本身不使其失效。

## UX & Interaction Patterns

通过既有 CLI／归属入口提供正式规划，展示真实阶段、阻塞实体、expected／actual 身份和 `resume_ref`。共用 `reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref` 诊断。如实展示部分已提交规划。提前声明 UI 输入、反馈、场景进入／返回及人工义务；本 Epic 不新增视觉设计，不依赖后续 Knowledge 页面。

## Cross-Story Dependencies

Epic 1 提供基线保护、迁移预检及共享身份／schema 合同。本 Epic 内，Ledger 先于审计和冻结输入，逻辑候选先于准入／评选，操作保留先于发布、恢复和完成成果复用；Story 2.10 将这些能力接入零 Task 公共路径。Epic 3 消费已采纳身份／proof 及共享提交服务，承接 Task 编译和实施绑定；Epic 4 承担完整页面／验证集成，Epic 5 承担默认 B 启用和奖励运行证明。这些后续 Epic 均非正式零 Task 采纳的前置条件。
