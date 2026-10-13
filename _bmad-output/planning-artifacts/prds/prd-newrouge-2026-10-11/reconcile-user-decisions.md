# Finalize 输入对账：用户已确认设计决策

对账对象：`prd.md`、`addendum.md`、`.memlog.md`

对账范围：本轮 Finalize 输入。用户确认的工作模式为 Fast path；产物是内部工作流 PRD；当前基线为 11 个 Capability；每个 Capability 生成 3 个独立 MVG 增量候选，候选通过准入后评选并累计合并；不同 MVG 表达不同操作动线；同一 Requirement 跨不同路线重复引用允许；跨 Capability 冲突默认修当前增量，只有真实硬冲突才显式重开受影响的早期 Capability；不扩充 GDD/133 tasks，不修改游戏代码。

## 已覆盖内容

| 用户决策 | 覆盖位置 | 对账结论 |
|---|---|---|
| Fast path | `.memlog.md` 的本轮决策记录；`prd.md` 已直接承载确认后的结果 | 结果内容已进入 PRD，但工作模式本身未写入 frontmatter 或独立元数据，见风险 1。 |
| 内部工作流 PRD | `prd.md` §0、§1（工作流维护者、Knowledge/CLI 用户）；§4、§5 的边界 | 已明确是 MVG 规划工作流优化，不是游戏功能需求扩展。 |
| 当前 11 Capability 基线 | `prd.md` §0、§5.1、§9 假设索引；`addendum.md` §1 | 已覆盖数量和用途；可冻结身份仍有缺口，见风险 2。 |
| 每个 Capability 3 个独立候选，准入后评选并累计合并 | `prd.md` FR-001、FR-002、FR-003；`addendum.md` §1、§3、§6 | 已明确隔离候选、机器/语义准入、选择、原子合并和顺序推进。 |
| 不同 MVG 是不同操作动线 | `prd.md` §1、术语 §2、FR-004/FR-005、SM-4；`addendum.md` §2 | 已明确 flow 是玩家操作路线，且 Capability 不强制一对一转换为 flow。 |
| 同一 Requirement 跨不同路线重复引用允许 | `prd.md` FR-004、FR-005、§4 非目标；`addendum.md` §2 | 已明确一对多/多对多路线关联、权威验证记账分离、重复关联本身仍拒绝。 |
| 跨 Capability 冲突默认修当前增量 | `prd.md` FR-009、§9 假设索引；`addendum.md` §2 | 已规定当前增量适配累计路线，不因一般重叠自动判冲突。 |
| 真实硬冲突才显式重开受影响早期 Capability | `prd.md` FR-009、FR-010、§8 Q5；`addendum.md` §2、§5、明确排除方案 | 已禁止静默重写，并要求冲突证据、受影响范围、失效下游增量和重选结果。 |
| 不扩充 GDD/133 tasks、不改游戏代码 | `prd.md` FR-012、§4 非目标、§5.2 不包含；`.memlog.md` assumption | 已明确不新增/扩充游戏任务、不改 GDD、运行时代码、资源和场景。 |

## 缺口与措辞风险

1. **Fast path 只在过程上下文中成立。** `prd.md` 没有 `working_mode: fast` 或等价声明，未来恢复/审阅者只能从外部对话或 memlog 推断。建议在不改变需求正文的前提下，给文档元数据或运行记录增加 Fast path 标记，并说明推断内容使用 `[ASSUMPTION]`。

2. **“11 个 Capability 基线”缺少不可漂移的身份。** 当前文字记录数量和日期，但未在 `prd.md`/`addendum.md` 固定 Capability 文件路径、版本或 hash；文件更新后仍可能被称为同一基线。建议在后续实现/架构输入中绑定 Capability 文件版本、hash 和读取快照，数量只作为辅助断言。

3. **候选、MVG 与 flow 的层级关系仍有解释空间。** 文档同时使用“3 个 MVG 增量候选”“累计 MVG”“多个 flow/路线”，但未明确一个候选可以包含多少 flow、评选对象是候选整体还是单个 flow 集合。建议增加一条验收口径：候选是当前 Capability scope 的增量提案，可包含新增或扩展的一个或多个 flow；评选选择整个增量，不能把不同候选的 flow 交叉拼接。

4. **“准入后评选”与候选预算/基线 incumbent 仍有开放决策。** `prd.md` §8 和 `addendum.md` §6 保留 incumbent 角色、64 invocation 预算和选择 rubric 的问题。建议在进入实现前将“只有完整准入候选可比较”作为固定门槛，并单独确定 run-level 与 lineage-level 预算语义，避免 3×11 候选被误读为自动扩大总预算。

5. **冲突处置的默认动作可更具象。** FR-009 表达了“当前增量适配累计路线”，但没有用统一状态名区分“局部修复完成”“报告待决”“显式重开”。建议后续 contract/日志为三类结果定义稳定枚举，并规定只有全局审计确认真实硬冲突时才生成早期 Capability reopen 计划。

## 建议

本次对账不修改 `prd.md` 或 `addendum.md`。后续 Finalize reviewer 可把上述风险作为审查输入；若需要解决，应在架构/contract 阶段补充基线身份、候选到 flow 的选择粒度、预算语义和冲突状态枚举，并通过对应 owning workflow 变更权威文件。
