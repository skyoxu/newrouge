---
id: SPEC-mvg-capability-increment-planning-and-admission-optimization
companions:
  - capability-baseline.md
  - workflow-state-machine.md
  - requirement-accounting.md
  - ../../planning-artifacts/architecture/architecture-newrouge-2026-10-12/ARCHITECTURE-SPINE.md
sources:
  - ../../planning-artifacts/prds/prd-newrouge-2026-10-11/prd.md
  - ../../planning-artifacts/prds/prd-newrouge-2026-10-11/addendum.md
---

> **Canonical contract.** This SPEC and its companions define the contract for incremental MVG planning and admission in `newrouge`. The adopted architecture companion supplies the implementation invariants and current-versus-target boundary; this SPEC remains the semantic Capability contract.

# MVG Capability 增量规划与准入契约

## Why

当前 MVG 规划把每个候选一路处理完全部 Capability 后才统一评选，且 Requirement 路线引用与唯一验证记账混在一起，导致候选失败难以局部恢复、累计结果难以安全推进。工作流维护者需要按冻结的 Capability 顺序生成可比较的增量，在格式和证据完整后才进入语义准入，并保留可重放的累计基线，同时不扩充 GDD 或 133 个现有任务。

## Capabilities

- **CAP-1**
  - **intent:** 按冻结 Capability 顺序逐项生成三个相互隔离的 MVG 增量候选，并在当前项选出一个合格增量后再推进。
  - **success:** 每个 Capability 都有三个独立 lineage；只有通过准入的候选可比较；选择和合并完成后才创建下一 Capability 的输入。

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
  - **success:** 每个稳定硬问题最多修复三次；失败后新 lineage 不读取失败上下文；lineage 或 run 预算耗尽产生明确可恢复终态，Capability 不被跳过。

- **CAP-6**
  - **intent:** 在全部 Capability 增量完成后审计跨路线一致性，并区分规划完成与运行时验收。
  - **success:** 全局报告分类记录通过项、真实硬冲突、待实现义务、证据缺口和未执行 runtime acceptance；无完整 proof 时不得标记规划完成。

## Constraints

- Capability 主输入只能来自冻结的 `capabilities.v1.json`；当前基线为 11 个 ID、指定顺序、`source_revision: source-set:68d145756705834e7b664fcc` 和 SHA-256 `53B0EDBA89E636312447599147A3982D3A4644DAFD6DCBB3BF1E67FA8FE6B61E`。详见 `capability-baseline.md`。
- 当前 accepted MVG 是只读累计底座，不是第四个候选；少于三个 admitted candidates 时阻断当前 Capability，不使用不合格候选或 incumbent 补位。
- 每个 candidate lineage 最多 64 次调用；每次 run 必须绑定正整数 `mvg.run_invocation_limit`，首版默认 192，统计所有候选和 Capability 的生成、证据检查、修复和语义调用。
- 输入必须完整传输并由 hash、路径、行号和 receipt 绑定；不能用摘要或截断替代来源。
- 机器结构门必须先于独立语义准入；被机器拒绝的 proposal 不得进入比较。
- 跨 Capability 默认只修当前增量；只有证据支持的真实硬冲突才允许显式重开早期选择，且必须保留影响范围和下游重建记录。
- 不修改游戏代码、GDD、Requirement 定义、Taskmaster 三联、Godot 资源或运行时验收状态；Chapter 5 readiness 必须与 Capability 基线版本/hash 绑定。
- 所有工作流证据和审计记录写入 `logs/**`，并遵循现有 MVG owning workflow、Skill 和 acceptance 文档。

## Non-goals

- 不新增或扩充 GDD、Requirement 或现有 133 个任务。
- 不把 Capability 强制一对一转换为 flow，也不把 Task 强制转换为 runtime entrypoint。
- 不用 prompt 替代 schema、确定性 validator、证据传输或准入门。
- 不允许比较器替代硬性准入，也不允许静默重写已选早期 Capability。
- 不在本契约中实现 Knowledge UI、运行时玩法或 runtime acceptance。

## Success signal

在一次新的 MVG run 中，维护者可以从冻结 Capability 输入开始，依次得到三个隔离候选、三个合格候选中的一个选择和一个可重放累计 checkpoint；最终全局审计能明确说明规划是否完成、哪些问题需要显式重开，以及哪些 runtime acceptance 尚未执行。

## Assumptions

- 当前 11 个 Capability 和 133 个任务在本契约实施期间保持不变；来源变化由 owning workflow 生成新的规划基线。
- 三个候选、每问题三次修复、64 次 lineage stop-loss 和 192 次首版 run 总预算是当前批准的初始参数。
- 当前仓库的 Capability 顺序是权威输入顺序，不表达产品优先级。

## Open Questions

- Chapter 5 readiness 的具体 artifact 路径、hash 和 ready 字段如何纳入实现契约？
- 共享 evidence 的 disposition 与 route-scope 字段采用什么稳定 schema？
- 显式重开早期 Capability 的受控 CLI/UI 入口和操作者确认方式是什么？
