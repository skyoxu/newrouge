# Epic 2 Context: Safe Increment Selection and Cumulative Checkpoints

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让工作流维护者为每个冻结 Capability 从三个已准入增量中选出一个，并将结果安全地合并为单一累计 MVG。选择、合并及恢复均绑定可验证身份，阻止缺失候选、旧基线漂移、部分写入和重复应用损坏已确认路线。本 Epic 描述目标行为；迁移尚未完成时，不把逐项选择与原子 checkpoint 宣称为当前能力。

## Stories

- Story 2.1: Select only a complete admitted candidate set
- Story 2.2: Commit a deterministic selected checkpoint
- Story 2.3: Make checkpoint replay and recovery idempotent

## Requirements & Constraints

- 每次只比较同一 Capability、同一冻结输入和同一累计基线下的三个 admitted increments。全部候选须先通过机器与独立语义准入；落选只能来自比较排名，不能在评选时追加语义硬拒绝。比较增量的来源忠实度、旅程连贯性、handoff、验证可行性和累计影响，不按候选编号或数组顺序决定胜负，也不混合候选。
- 已接受累计 MVG 只作为只读 seed，不能成为第四候选或缺失候选的 fallback。不足三个准入候选时进入 `selection_blocked_insufficient_admitted_candidates`，保存候选清单、原因及恢复证据，不推进累计基线或下一 Capability。
- 按冻结 Capability 文件顺序处理；当前项选择并合并完成后，下一项才消费已确认累计结果。冻结来源、Chapter 5 readiness、Requirement 范围、准备证据及基线身份变化均阻断旧结果应用，不能以新输入冒充原 run。
- 允许有来源依据地扩展跨 Capability 的玩家旅程；不机械地产生一 Capability 一 flow 或一 Task 一入口。未经显式权威变更，不删除或弱化已接受路线、handoff、测试、outcome 和有效映射。合并后的累计 manifest 必须通过完整确定性检查，失败保持此前基线。
- 同一 Requirement 的不同路线引用或共享 Contract 本身不构成冲突，不增加完成计数。保留唯一权威验证处置及可追溯证据；旧 coverage 数据在无损迁移前不得被覆盖。真正的历史重开由全局审计和显式证据计划处理，当前增量不能静默改写早期选择。
- 沿用 Windows、UTF-8 和现有工具链边界，所有过程证据放入 `logs/**`。不修改 Capability 分组、GDD、Requirement 定义、现有 133 个任务或游戏运行时；规划成功不代表 `runtime_verified`。

## Technical Decisions

- 单一 coordinator 拥有生命周期、累计基线和 checkpoint；阶段 worker 返回结果与 receipt，不自行推进已选序列。阶段消费不可变 hash-bound 输入，状态变化先记录事件再对外呈现；恢复验证事件和 receipt，不能仅凭文件存在推断成功。
- 选择记录绑定 Capability、候选集合及 lineage、proposal hash、基线 hash、比较输入输出和模型 receipt。累计证据保留各项准入 proof、选择、合并记录及下一项 seed，供恢复和最终审计回放，不以模型摘要替代源证据。
- checkpoint 事务 ID 为以下 tuple 的 canonical JSON SHA-256：`schema_version`、`run_id`、`capability_id`、`order_index`、`base_sha256`、`proposal_sha256`、`selection_receipt_sha256`。累计变化暴露前持久化完整 tuple，checkpoint payload 保持同一身份；选定 delta 与 checkpoint 原子提交。
- 基线 hash 不匹配时拒绝旧候选。相同事务身份和 canonical payload 的重放为 no-op；同身份不同 payload、缺失 receipt 或 predecessor hash 变化均 fail closed，保留冲突证据且不修改已接受 manifest。
- 保持 lineage 64 次调用止损与正整数 `mvg.run_invocation_limit`，首版默认 192；跨 Capability 拆分不得静默放大预算。完整预算预留、耗尽终态和全局审计由后续 Epic 接入。恢复仅复用身份完全匹配且允许复用的接受产物，新 run 不复用旧模型证据。
- 稳定 CLI/Knowledge 入口、工作流、Skill、validator 与验收说明必须随迁移保持一致；只改 prompt 或可选 helper 不构成迁移。readiness schema、共享 evidence 字段和受控 reopen 入口仍由各 owning 实施设计冻结，不虚构未批准字段。

## UX & Interaction Patterns

复用现有 CLI/Knowledge 操作，通过持久化 receipt 展示当前 Capability、阶段、失败原因和恢复身份。UI 是状态消费者，不拥有选择或 checkpoint；本 Epic 不新增独立页面设计。

## Cross-Story Dependencies

Epic 1 提供冻结输入、隔离候选及完整准入证据。Story 2.1 建立逐项完整候选评选；Story 2.2 在选定结果上实施原子 checkpoint；Story 2.3 验证其恢复与幂等重放。Epic 3 承担路线成员关系、唯一验证及共享证据的无损记账迁移；Epic 4 承担全 run 预算、全局冲突重开、最终审计和规划完成发布。目标迁移完成前，现有全候选 append 后整体选择及可选 incumbent 仍需明确标为旧行为，不能把后续保证提前记为已部署。
