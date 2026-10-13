# Epic 1 Context: Clean Capability Candidate Admission

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让工作流维护者针对一个冻结的 Capability，生成并准入三个完整且相互隔离的 MVG 增量候选。先证明输入完整可信，再执行确定性结构检查和独立语义硬检查，避免格式错误、来源漂移或失败上下文进入评选。完成本 Epic 不代表整个逐 Capability 选择与累计合并迁移已部署，也不代表游戏运行时通过验收。

## Stories

- Story 1.1: Freeze the Capability input envelope
- Story 1.2: Enforce isolated candidate admission
- Story 1.3: Repair hard issues and restart cleanly

## Requirements & Constraints

- 以显式选定的 Capability 版本为主输入，每次只处理当前 Capability 的增量。Capability 是规划边界，不强制一对一生成 flow；flow 可以表达跨模块的玩家操作动线。
- 准备阶段冻结 Capability 文件路径、内容 hash、source revision、顺序、Requirement 范围、Chapter 5 readiness 身份、完整证据清单以及已接受前置基线。来源漂移、缺少 ready 证据、必要证据缺失或顺序改变都在模型生成前阻断，并报告具体身份差异。
- 当前批准基线是 `docs/planning/semantic-topology/capabilities.v1.json`：11 项，source revision 为 `source-set:68d145756705834e7b664fcc`，SHA-256 为 `53B0EDBA89E636312447599147A3982D3A4644DAFD6DCBB3BF1E67FA8FE6B61E`。它与 133 个现有任务保持冻结；来源更新由 owning workflow 提供新基线，MVG 不自行生成替代来源。
- 核心输入与辅助证据必须完整传输。超出单次请求容量时，分片必须连续、有序、hash-bound 且能精确重组；缺失、重复、乱序、越界、hash 不一致或容量不足必须 fail closed。不得静默裁剪、用摘要替代源证据或复用另一 run 的 receipt。
- 每个候选只读取相同不可变准备输入与已接受前置基线，并拥有独立 lineage、workspace、调用身份和准备副本。候选之间不能读取 prompt、finding、proposal、workspace 或未准入产物。
- 语义准入前必须完成 schema、identity、ID 唯一性、selector、路径及引用域、Requirement 范围、flow/test 双向绑定、handoff 与累计 delta 的确定性检查。已有 C# selector 必须是对应测试源码中的类名；planned 对象必须有真实 owner、输入、断言和实施验收。仅真实跨系统边界需要 handoff，其 producer、consumer、Contract 和测试必须可追溯。
- 同一 Requirement 可以参与不同操作动线；重复路线引用本身不构成冲突或重复完成。同一关联重复、未知 Requirement、越界引用及权威记录丢失仍属于结构错误，不能以放松验证器解决。
- 稳定硬问题逐项局部修复，每问题最多三次；每次绑定当前 proposal hash 与目标对象及必要依赖范围。修复后重跑机器检查，只有目标问题减少且没有新增缺陷才原子接受，不改动无关有效映射或旧路线。
- 三次仍失败则退役当前 lineage，新 lineage 仅从不可变准备输入及已接受前置基线重新开始。不得传入失败 proposal、prompt、finding、transport 或 workspace，也不得因失败跳过 Capability。
- 保留每 lineage 64 次调用止损；run 绑定正整数 `mvg.run_invocation_limit`，首版默认 192，跨候选与 Capability 统计。执行、准备、传输、机器问题、语义硬问题和预算耗尽必须分类，不由模型修复数据源故障，也不自动扩大预算。
- 准入成功指标：进入独立语义审查的 proposal 没有格式、身份、selector、引用或 flow/test/handoff 结构问题；进入模型调用的来源没有截断或身份不匹配。规划工作流不得修改 GDD、Requirement 定义、Taskmaster 三联、游戏代码、Godot 资源或运行时验收状态。

## Technical Decisions

- 采用显式状态机与 append-only 证据 ledger。阶段消费不可变 hash-bound envelope，返回 typed result 与 receipt；coordinator 拥有状态推进，worker 不写选定累计基线或推进 Capability 顺序。
- 把强制 schema、prepared-domain preflight、生成后跨字段机器检查和独立语义硬检查分层。Prompt 不能代替 CLI/schema/local validator；机器拒绝不是语义 verdict，也不能进入比较器。
- 已接受 MVG 是只读 seed，不是第四个候选或失败补位。后续选择必须有三个 admitted candidates；不足时保留恢复证据并进入 `selection_blocked_insufficient_admitted_candidates`，不推进下一项。
- 所有准备、调用、问题、修复、准入与恢复事件记录 run/Capability/candidate/lineage 身份、阶段、attempt、错误类型、hash、时间及前置基线，证据放在 `logs/**`。恢复只能复用明确允许且 hash 一致的已接受产物；新页面 run 不复用旧模型证据。
- 使用环境默认模型，不显式指定其他模型。保持 Windows 环境、UTF-8 文档、现有 CLI/Knowledge 入口和 Python 3.12 CI 兼容性。
- Chapter 5 readiness 的具体 snapshot 路径、schema、hash 和 ready 字段尚未冻结；Story 1.1 实施设计须依据真实 owning 产物确定，不能虚构字段或弱化身份绑定。共享 evidence 字段及旧 coverage projection 迁移由后续记账 Epic 定义，当前不得声称目标 schema 已部署。

## UX & Interaction Patterns

复用现有 CLI 与 Knowledge 入口，通过持久化 receipt 展示阶段、进度、身份不一致和可恢复失败；UI 不拥有工作流状态。没有独立 UX 或 product brief 设计契约，不在本 Epic 重做页面。

## Cross-Story Dependencies

Story 1.1 提供后续隔离与准入所需的共同输入身份；Story 1.2 建立候选和机器 gate；Story 1.3 在这些边界上实施局部修复及干净 replacement。Epic 2 消费三个 admitted candidates 并实现选定 checkpoint 与累计推进，Epic 3 迁移路线成员关系及权威验证记账，Epic 4 接入全 run 预算、全局审计与完成边界。迁移期间现有全范围候选/可选 incumbent 行为仍是当前实现现实，不能把目标流程描述成已完成。
