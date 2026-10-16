---
id: SPEC-mvg-capability-increment-planning-and-admission-optimization
companions:
  - capability-baseline.md
  - workflow-state-machine.md
  - requirement-accounting.md
  - recovery-and-worker-boundaries.md
  - ../../planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md
sources:
  - ../../planning-artifacts/prds/prd-newrouge-2026-10-11/prd.md
  - ../../planning-artifacts/prds/prd-newrouge-2026-10-11/addendum.md
---

> **Canonical contract.** This SPEC and its companions define the contract for incremental MVG planning and admission in `newrouge`. The adopted architecture companion supplies the implementation invariants and current-versus-target boundary; this SPEC remains the semantic Capability contract.

# MVG Capability 增量规划与准入契约

## Why

当前实现已有逐 Capability 评选和原子 checkpoint，但候选生命周期仍由同一协调进程调用，页面主要展示整轮发布结果。工作流维护者需要隔离候选工作、减少无关上下文，并在长流程中复用已完成项、立即看到累计成果。仅修复规划工作流，不扩充 GDD 或 133 个现有任务。

## Capabilities

- **CAP-1**
  - **intent:** 按冻结 Capability 顺序逐项生成三个相互隔离的 MVG 增量候选，并在当前项选出一个合格增量后再推进。
  - **success:** 每个 Capability 的三个候选由独立子进程完成生成和准入；主流程机器复验后只对三个合格候选排名；下一项不接收历史模型对话或失败上下文。

- **CAP-2**
  - **intent:** 将选定增量安全地合并到累计 MVG，并保留基线、选择、合并和恢复的可审计身份。
  - **success:** 每次合并绑定输入/基线 hash 和 receipt，可重放且失败不部分写入；基线漂移会阻止旧候选应用。

- **CAP-3**
  - **intent:** 允许同一 Requirement 出现在不同操作路线，同时独立记录唯一的权威验证处置和证据。
  - **success:** 不同 `(requirement_id, flow_id)` 关联可共存；验证 disposition 唯一；共享证据不增加完成计数且可追溯。

- **CAP-4**
  - **intent:** 在语义准入前确认模型输入和 proposal 的结构、引用、身份及证据完整性。
  - **success:** 截断、缺失、乱序、未知 ID、非法 selector、无效 handoff 或不一致 flow/test 关系在语义调用前被确定性阻断。

- **CAP-5**
  - **intent:** 对硬问题执行有边界的局部修复和干净上下文恢复，并区分内容问题、执行问题和预算终止。
  - **success:** 每个稳定硬问题最多修复三次；失败后新 lineage 不读取失败上下文；稳定候选槽位或 run 预算耗尽明确终止，不能通过替换 lineage 补额度，Capability 不被跳过。

- **CAP-6**
  - **intent:** 在全部 Capability 增量完成后审计跨路线一致性，并区分规划完成与运行时验收。
  - **success:** 全局报告分类记录通过项、真实硬冲突、待实现义务、证据缺口和未执行 runtime acceptance；无完整 proof 时不得标记规划完成。

- **CAP-7**
  - **intent:** 按单项 Capability 内容复用已经完成的 MVG，避免因无关 Git 提交重复生成。
  - **success:** 内容哈希相同且累计重放兼容的完成项零模型调用复用；内容变化或未完成项从头生成；不采用相似度匹配。

- **CAP-8**
  - **intent:** 每完成一个 Capability，立即看到当前累计 MVG 及进度。
  - **success:** 原子提交后的结果立即进入 Cumulative MVG scope；后续失败或服务重启仍可查看，且区分新生成、复用、部分规划和运行验收。

- **CAP-9**
  - **intent:** 用户可以清理当前本地生成 MVG，使下一次工作流全部重新开始。
  - **success:** 清理后显示零完成项，旧日志和指针不能恢复结果；生成与清理互斥，保留审计、Capability、任务和正式运行证据。

## Constraints

- Capability 主输入只能来自每轮显式选定并冻结的 `capabilities.v1.json`。历史 11 项快照见 `capability-baseline.md`，不是其他版本或项目的数量限制。
- 当前 accepted MVG 是只读累计底座，不是第四个候选；少于三个 admitted candidates 时阻断当前 Capability，不使用不合格候选或 incumbent 补位。
- 每个 run 内的稳定 candidate 槽位/chain 最多 64 次调用，跨 Capability、替换 lineage 和进程持续累计；每次 run 绑定正整数 `mvg.run_invocation_limit`，默认 192，统计生成、证据检查、修复、语义和评选调用。
- 输入必须完整传输并由 hash、路径、行号和 receipt 绑定；不能用摘要或截断替代来源。
- 机器结构门必须先于独立语义准入；被机器拒绝的 proposal 不得进入比较。
- 跨 Capability 默认只修当前增量；只有证据支持的真实硬冲突才允许显式重开早期选择，且必须保留影响范围和下游重建记录。
- 不修改游戏代码、GDD、Requirement 定义、Taskmaster 三联、Godot 资源或运行时验收状态；Chapter 5 readiness 必须与 Capability 基线版本/hash 绑定。
- 所有工作流证据和审计记录写入 `logs/**`，并遵循现有 MVG owning workflow、Skill 和 acceptance 文档。
- 恢复唯一匹配键为单项 Capability 的规范化内容哈希；JSON 对象键序和缩进不影响哈希，数组顺序、字段值和类型改变影响哈希。Git commit、catalog hash 和生成时间不参与该键。
- 仅恢复原子提交的完成项；候选、修复、检查和评选中间状态仅供审计。复用需要完整性和累计兼容性机器验证，不改写历史 proof，也不额外调用模型。
- 关联完整来源和已选结构化边界可跨阶段传递，无关原文与过程聊天不可重复注入。具体边界与验收矩阵见 `recovery-and-worker-boundaries.md`。

## Non-goals

- 不新增或扩充 GDD、Requirement 或现有 133 个任务。
- 不把 Capability 强制一对一转换为 flow，也不把 Task 强制转换为 runtime entrypoint。
- 不用 prompt 替代 schema、确定性 validator、证据传输或准入门。
- 不允许比较器替代硬性准入，也不允许静默重写已选早期 Capability。
- 不修改运行时玩法或实现 runtime acceptance；Knowledge UI 仅增加本次规划进度和清理能力。

## Success signal

定向测试证明：完成 A 后中断 B；无关 Git 提交后新 run 复用 A、全新执行 B；修改 A 内容后重新生成 A；清理后不再恢复任何当前生成结果。页面在每项提交后可见进度，独立 worker 输出经主机器复验，最终规划完成仍需全局机器审计。

## Assumptions

- 现有 133 个游戏任务保持不变；每轮 Capability 文件和顺序在 prepare 冻结，来源变化开启新 run。
- 三个候选、每问题三次修复、每稳定候选槽位 64 次 stop-loss 和 run 默认总预算 192 次是当前初始参数。
- 当前仓库的 Capability 顺序是权威输入顺序，不表达产品优先级。

## Existing implementation contracts

- Chapter 5 使用 `_mvg_input_envelope.py` 的冻结 envelope 和现有完整 readiness 检查，不另造 readiness 状态。
- 共享映射使用现有 `requirement_route_memberships`、`requirement_verification` 和 `requirement_evidence`；沿用 `requirement-accounting.md` 的键。
- 显式重开沿用 `plan-mvg` 的 `audit`、`reopen-plan`、`reopen` 及 hash-bound plan，新增恢复资格撤销，不另造任务生命周期。
