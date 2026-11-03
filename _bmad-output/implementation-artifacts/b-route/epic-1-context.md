# Epic 1 Context: 可审阅迁移并保护既有成果

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让仓库维护者获得可复查的当前基线、消费者矩阵、存量保护依据及只读迁移预检，识别身份、状态与累计义务风险，为后续正式采纳提供经审阅输入。本Epic交付预检与保护能力；正式采纳、实施门禁、奖励运行、默认B切换及A退役由后续Epic承接。

## Stories

- Story 1.1: 生成可复查的当前基线与消费者盘点
- Story 1.2: 明确B阶段顺序、记录权威及迁移启用规则
- Story 1.3: 统一核验文件引用与规范化内容身份
- Story 1.4: 按唯一公共schema校验六类规划记录
- Story 1.5: 形成可审阅的成熟成果保护基准与冻结A输入
- Story 1.6: 通过只读预检审阅迁移差异与阻断原因

## Requirements & Constraints

来源与有效ADR管语义，Taskmaster三联保持唯一任务状态权威，契约源码管程序合同，manifest管累计义务，原始报告证明对应快照结果。Knowledge只派生定位，预览不得推进current或last-known-good。盘点和结构校验分别陈述能力边界，不能授予语义采纳、Task readiness或运行通过。

保留成熟Task／Flow／test身份、当前状态、历史与成果；新增责任不能由旧done自动满足。更新、拆合、退役或降低累计义务须有来源、差异与审阅。缺失、损坏、未知及漂移明确阻断，不以摘要、缓存、空清单或模型自报替代依据。

覆盖来源／Ledger／审计、planner、业务视图／compiler、Chapter4–7、manifest／runner／handoff、Knowledge／页面／CLI／Skill／文档。ADR状态读正文，两份ADR-0038使用完整文件名。目标为路线改变，不设提速、降成本或固定Task数量门槛。

## Technical Decisions

采用既有Python编排的分阶段文件流水线，不新增数据库。Windows-only、Godot4.5.1、C#／net8.0与BCL-only Core／Contracts边界保持；原始证据放logs，最小正式依据经审阅版本化。当前声明代码基线与实际HEAD、分支、工作区差异分别记录；历史提交身份不充当当前身份。

公共codec统一路径、类型、digest及诊断，raw身份与规范化身份分存。对象键序与排版可规范化；数组顺序、类型、字符串及Unicode原值保留。policy／plan／binding／origins／commit／catalog各有唯一版本化schema；未知格式拒绝。诊断统一reason_code、stage、entity_id、expected、actual、resume_ref。

冻结A资格须有明确Task定义、来源scope及允许操作，不能凭缺trace推断legacy。采集漂移须重采，后编辑与pending须保留并定位恢复。正式发布与journal服务归后续Epic；本Epic不调用模型生成规划，不写Task或发布指针，不提前启用B。

## Cross-Story Dependencies

1.2依赖1.1；1.3依赖1.1／1.2；1.4依赖1.3；1.5依赖1.1–1.4；1.6依赖1.1–1.5。只读报告、治理审阅、公共codec／schema、保护与冻结A材料及预检结果共同交给Epic2；未决项保留，后续消费者复用同一合同。
