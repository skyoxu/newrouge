# Epic 3 Context: Correct Requirement Route and Verification Accounting

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

允许规划消费者将同一 Requirement 关联到多条有意义的玩家动线，同时保留唯一权威验证处置和去重证据。路线成员关系须可独立查询，不得虚增完成计数或丢失旧覆盖数据。本 Epic 属于现有 133 个任务范围内的 MVG 工作流迁移。

## Stories

- Story 3.1: 持久化 Requirement 的多动线路线成员关系
- Story 3.2: 分离权威验证与共享证据
- Story 3.3: 在准入与最终审计中验证记账

## Requirements & Constraints

一个 Requirement 可参与多条不同 flow；每条关联须说明其在该路线中的可观察作用，重复标识符不能替代路线行为。路线数和证据引用数不得增加 Requirement 完成数。重复引用 Requirement、共享 Contract 和路线重叠本身不构成冲突。

每个有效 Requirement 必须恰有一条权威验证处置。未知 Requirement、无效 flow、重复关联键或验证键、缺失权威记录，以及越出冻结的当前 Capability/累计范围的引用，均属确定性错误。证据须能解析到准备好的来源；flow/test 引用须双向且范围一致。

报告采用以下语义：

| Disposition | 报告约束 |
| --- | --- |
| `flow` | 仅在所需权威证据存在时满足。 |
| `other_verification` | 仅在所需权威证据存在时满足。 |
| `deferred` | 已记账但未满足；保留授权依据。 |
| `source_gap` | 未满足且未完成；阻断规划完成。 |

分别呈现 `accounted` 与 `satisfied`。路线引用、拟议测试或规划准入均不能单独授予运行时验证状态；`runtime_verified` 仍由正式运行时验收产生。

迁移须保留旧权威处置、完成计数、有效映射及证据。替换现有 manifest 前须保留原快照或提供可逆迁移。不得为满足唯一性而丢弃路线关联，也不得静默弱化已接受的路线、测试、outcome 或 handoff；修改有效累计内容须有明确来源授权。

变更涉及 proposal/manifest、校验器、累计 delta/apply 与重放、汇总和兼容夹具。兼容重放须证明权威处置及完成计数守恒，并单独暴露路线成员关系。

## Technical Decisions

记账使用三个独立稳定键：

| 投影 | 稳定键 | 含义 |
| --- | --- | --- |
| `requirement_route_memberships` | `(requirement_id, flow_id)` | 每条路线一条关联，记录可观察作用。 |
| `requirement_verification` | `requirement_id` | Requirement 的唯一权威处置。 |
| 验证证据引用 | `(requirement_id, evidence_id)` | 去重证据，记录覆盖行为和路线。 |

共享证据须记录行为及路线范围。行为不同时，按需明确路线专属测试引用，不机械复制测试。共享证据 disposition 和 route-scope 的具体字段尚未确定，须在冻结 proposal schema 前落实，并保留上述键与计数规则。

迁移完成前，现有 `coverage_table` 仍采用每个 Requirement 一行的投影。保留其唯一 disposition 作为权威验证记录，将旧 flow owner 投影到路线关联或 owner metadata。多路线记账是迁移目标，不能视作已部署保证。

确定性记账校验在语义准入前、累计重放及最终全局审计时执行。机器检查通过后才进行含义与路线连续性的语义审查。机器失败须定位字段/对象并阻断语义准入。

输入绑定冻结的 Capability 快照、Chapter 5 readiness、准备证据及已接受前驱。证据缺失或不匹配时阻断。记账不得改写 GDD/Requirements、Taskmaster 状态、Contract、测试或运行时状态。Receipt 放在 `logs/**`；保持 Windows 和 Python 3.12 CI 兼容。

## UX & Interaction Patterns

保留 CLI 和 Knowledge 入口。汇总展示引用 flow、权威处置与证据，并呈现共享行为/路线；完成计数独立于关联数。进度和错误来自持久化 receipt，UI 状态不拥有记账或生命周期权威。本次不要求重做 Knowledge UI。

## Cross-Story Dependencies

路线成员关系建立关联模型；验证/证据分离建立权威计数；集成校验在准入、重放和最终审计中保护两个投影。三条 Story 须统一键和迁移语义。

Epic 1 提供冻结来源与确定性准入门。Epic 2 提供累计合并和幂等重放边界，须保留记账投影。Epic 4 在最终审计中消费相同不变量，来源缺口或未解决硬冲突须阻断规划完成。记账不得自行选择候选、推进 checkpoint、重开已接受历史或宣称运行时验收通过。
