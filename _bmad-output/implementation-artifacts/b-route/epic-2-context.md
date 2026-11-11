# Epic 2 Context: 无实施Task也能正式规划、审阅和采纳

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

在尚无实施 Task 或 readiness 时完成正式规划、审阅与采纳。将完整累计来源转换为 Requirement、验收意图、Capability／Flow 定义或有依据的非 Flow 验证去向；持久保存稳定身份，支持跨会话恢复已采纳计划，供后续 Task 编译承接。

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

- 每个登记的累计来源块须有语义投影或明确且有来源依据的去向。独立遗漏／冲突审计从完整来源与 Ledger 定界，不由首轮投影引用反裁。accounted 不等于 satisfied；未解决的来源缺口或阻断 finding 阻止规划完成。
- 正式采纳不要求 Task ID、Chapter 5 witness／readiness、代码符号或已有场景；已有实现仅辅助复用判断。假对象、draft／allow-unready 绕过及空字段不能授权采纳或非 Flow 豁免。
- Flow 保留稳定身份、来源／Requirement 回链、进入与成功条件、必要失败／取消／返回分支、交接、状态所有者及可观察验证目标。逻辑层须明确适用的领域规则、C# 适配、绑定及原生场景职责；planned 对象仍未实现。保留 UI 输入、反馈、进入／返回及适用人工义务。
- 允许跨 Capability Flow、共享 Requirement 及有依据的非 Flow 验证。保持唯一权威验证处置及定义 owner；路线成员关系与共享证据不得重复计完成。检查引用、边界归属、可达性、循环及声明退出，不假定图无环，也不声称证明任意程序终止。
- 保留完整适用原文／对象、有序批次、原始身份、跨批义务及全局守恒 proof。允许受治理依赖投影，禁止任意摘录、摘要替代和静默截断；容量不足时停止并给出恢复位置。
- 成功须有可复验的零 Task 采纳链、全局机器审计及独立语义 admission。保留成熟身份、状态、累计义务及后续编辑。记录实测耗时、dispatch、复用和终止；未知值显式 unknown。不设提速、降成本或 Task 数量目标。

## Technical Decisions

- 沿用 Windows 分阶段文件流水线与 Python 编排，不新增数据库或第二套生命周期。来源／ADR 管语义，Taskmaster 管 Task 状态，Knowledge／topology 保持派生。分别遵守 `ADR-0038-semantic-delivery-topology.md`、`ADR-0038-mvg-candidate-admission.md` 和 `ADR-0039-mvg-completed-capability-recovery.md` 的合同边界。
- 单一受治理 schema／codec 管理 `docs/planning/b-route/` 下六类记录：policy、不可变 plan、独立修订的 binding、Task origins、不可变 commit receipt 及 catalog。bootstrap 允许空 Task origins／冻结 A 集合。采纳持久保存新规划身份及已审阅差异／lineage，保留既有身份；Task 由后续 compiler 分配。
- 写前冻结 operation ID、规范化请求、scope、authority 及完整 before／after payload 身份。复用共享锁／journal：先短时 metadata 锁，再按稳定顺序取得 scope 租约；模型调用期间不持全局锁。同 ID 同内容复用分配，同 ID 异内容冲突。逐目标仅接受本操作 before 或 after 状态；未知编辑或 Windows 占用即停止。
- 应用、重读并验证全部目标，持久保存最小 receipt 后，才原子发布覆盖所有受影响 scope 的单一 catalog。receipt 目标 digest 不含自身或最终 catalog 输出；journal 保留最终 catalog payload。消费者核对提交链和实际文件后重读 catalog。相关 pending 阻断消费，包含 legacy pending／journal；缺少本地 logs 不豁免核验。恢复仅推进已核实的缺失步骤；补偿以当前状态为前像创建新受审阅 operation。
- 原始 proof 与规范化依赖身份分开。相关来源／审计／解析器／规则／codec／工具／环境变化使受影响结果失效；无关 HEAD、Task status 或 catalog 变化不单独失效。引用使用仓库相对 POSIX 路径、有类型 digest 和明确修订；必需记录缺失、损坏或未知均阻断。
- 复用隔离 worker、协调器独占 selection／checkpoint 提交、独立 admission 及持久预算。评选不等于正式 catalog 采纳。跨 run MVG 仅复用已提交完成项，核对单项规范化内容、原 proof、当前依赖／delta，并写新 adoption receipt。遵守 epoch／reopen 撤销；Capability 显式证据恢复与文件 journal 恢复各守原合同。
- 返回统一 `reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`；过程证据留在 `logs/**`，最小正式记录纳入版本管理。声明耐久性前验证 Windows 中断、重启、占用及发布失败。

## Cross-Story Dependencies

Epic 1 提供治理、共享记录／codec、基线保护及 scope 合同。内部顺序为记账 → 审计 → 冻结规划输入 → 候选／admission → 冻结采纳 → 发布 → 恢复／复用 → 公共入口集成；复用还要求有效准备输入与已完成评选。

Epic 3 消费已采纳身份、职责及提交／恢复服务，完成 Task 编译和绑定／readiness。Epic 4 承担完整 Knowledge／页面对齐及更广的验证消费者；Epic 5 承担奖励试点与默认 B 启用。Task 生成、Chapter 4–7 门禁和 runtime／full-MVG 证据仍由后续阶段负责。
