# SPEC 输入对账

结论：**Pass（输入对账）**。原两个 P2 输入承接缺口已定点复核关闭，当前无未解决 finding。未发现 P0／P1 的产品行为冲突、授权扩大或已采纳排除项回退；本结论不代表实现或运行验收通过。

## 核对范围与限度

- 目标：`ARCHITECTURE-SPINE.md` 与 `planning-records.md`，2026-11-03 当前工作树。
- 输入：`spec-newrouge-b-route/SPEC.md` 及全部五份 companions：`workflow-contract.md`、`verification-contract.md`、`migration-and-pilot.md`、PRD `addendum.md`、`baseline-update.md`。补核对应 PRD 的 FR-1–18／原始 BR 映射及 AC-BR-01–23。
- 身份：产品基线 `cd925bdcae4b61992320773497f7edb729aac244`；文档输入 `e9cd3d9cb4f054f04348013c1cba926675fcca49`；分支 `fix/capability-synthesis-input-integrity`。这是文档输入对账，不是源码实现检查或运行验收；未运行测试、生成任务或执行工作流。
- 已采纳技术选择：版本化分阶段文件流水线、journal、统一消费者 gate、派生 Knowledge、无新数据库。新 schema、catalog、租约和补偿操作属于技术细化，本身不改变批准的产品行为。

修复复核仅重新检查下述两项：AD-7 的盘点／真实缺口约束，以及 AD-15／伴随合同的跨阶段观测；未扩大检查维度或重复完整审查。

## 已关闭缺口

### R-SPEC-01 · P2 · Resolved · 3C 真实缺口前置盘点

- **输入依据：** SPEC CAP-4 intent；`workflow-contract.md` 阶段交接表 3C；PRD FR-6 明确先核对已有实现、完成 Task、共享能力与验证义务，再从真实缺口生成或复用三联。
- **原缺口：** 只保护旧身份／状态及三联写入路径，未明确生成前盘点既有成果和真实缺口。
- **关闭证据：** `ARCHITECTURE-SPINE.md:71` 的 AD-7 现明确“先盘点已有实现、完成Task、共享能力、四部分及验证责任，再仅为真实缺口产生经审阅的业务视图 delta”。盘点已成为任务生成规则的前置，且 delta 继续沿既有三联编译路径；不要求新增独立盘点系统或固定字段。
- **复核结果：** 满足 CAP-4／FR-6 的核心约束，关闭；无剩余精度问题。

### R-SPEC-02 · P2 · Resolved · 跨阶段可关联过程观测

- **输入依据：** SPEC CAP-10 success；`verification-contract.md:53`；PRD FR-16、7.3；`addendum.md:106` 的 AC-BR-20。必须记录阶段耗时、模型调用、复用、重复测试及返工，能够定位重复工作和无进展重试；没有提速或降成本门槛。
- **原缺口：** 只有日志位置、费用／预算和错误诊断，没有落实跨阶段生产责任及可关联观测内容。
- **关闭证据：** `ARCHITECTURE-SPINE.md:119` 的 AD-15 现覆盖规划、Task 生成、局部／Flow 验证和返工的可追溯耗时、实际调用、复用与重复执行；`planning-records.md:77` 指定各阶段执行者写既有 logs，以 operation／run、scope、stage、attempt 关联 active 耗时、实际 dispatch、复用来源／原因、重复测试／预热、返工返回和终止原因，事件去重，未观察值明确 unknown。原始日志继续受 `logs/**` 规则约束，不把预留、暂停墙钟或估算当实测费用。
- **复核结果：** 满足 CAP-10／AC-BR-20 的可追溯观测责任，且不引入提速／降成本验收门槛；关闭，无剩余精度问题。

## 能力及原始验收覆盖

| 输入 | 架构承接 | 判断 |
| --- | --- | --- |
| CAP-1／FR-1–2／BR-01–02；AC-01、02、09 | AD-2、10、15；InputSet source／Ledger／Requirement 及原文／raw proof | 完整累计来源及 Ledger 定界的独立 3A 审计成立，后续投影不反裁来源；无 Task 正式路径成立 |
| CAP-2／FR-3–4、7／BR-03–04、07；AC-01、03、05、21 | AD-2、4、6、12；计划／绑定分修订；非 Flow 分类 | 四部分及真实对象后补检查、合法循环、Flow 跨 Capability、Task 多对多、唯一验证 owner 和合法非 Flow 均保留 |
| CAP-3／FR-5／BR-05；AC-04、06 | AD-3、4、8、9；plan lineage、不可变修订、操作身份 | 持久采纳、同输入恢复及显式重规划差异承接；3B 不要求 Task／readiness |
| CAP-4／FR-6／BR-06；AC-01、05、14 | AD-4、7、8、18；三联治理及状态保护 | 身份／历史／写入路径成立；真实缺口前置盘点已按 R-SPEC-01 复核关闭 |
| CAP-5／FR-7–9／BR-07–09；AC-08、09、15、19、21、23及 owner 反例 | AD-5–10、12、13；分类、InputSet、统一 resolver／gate | B 丢标识不降 legacy；所有真实入口一致；合法非 Flow 有其他验证；owner 不伪造 API／自身 done 前置；纯实现修复保 readiness／回归 |
| CAP-6／FR-10–11／BR-10–11；AC-10、12、13、17、21 | AD-6、11–13；VerificationScope 及运行 receipt | 局部／Flow 两层验证、目标 UI slice 复用、真实输入与静态／场景方法／人工证据分级成立 |
| CAP-7／FR-12／BR-12；AC-11、17、22 | AD-4、10、11；反向闭包、VerificationScope、实际执行覆盖 | 旧必需回归／本次新增／范围外未来三分类、未知扩大仍分类、旧失败修后回归及 partial 不冒 full 成立 |
| CAP-8／FR-13／BR-13；AC-06、07、09、17 | AD-8–10、13；journal、receipt、最终 catalog、scope 保护 | 规划稳定／应用幂等／证据有效分离；后编辑冲突、相关失效和无关复用成立；累计运行必须同整合快照 |
| CAP-9／FR-14–15、17／BR-14–15、17；AC-14–16、19 | AD-3、5–7、16、18；policy／origins／catalog 及全消费者接入 | 五批和 A 有界退出、版本／损坏／合法缺失分类、派生展示和 preview 发布身份成立 |
| CAP-10／FR-16／BR-16；AC-09、20 | AD-9、15–17；继承传输／admission／预算 | 完整输入、独立候选 admission、预算、已提交完成项恢复与停止边界保留；跨阶段观测已按 R-SPEC-02 复核关闭 |
| CAP-11／FR-18／BR-18；AC-18及其余适用反例 | AD-14、18；奖励双路径、既有生产／测试框架 | `combat-reward-return`、独立 Reward／Map 路由、命令／只读状态／必要 C# 适配、候选／RNG／存档、旧身份及累计测试均保留；Windows／Godot／C# 运行证据属于未来实施门槛 |

上表 AC 缩写均指 `AC-BR-*`；01–23 全部已定位，不将架构条文视为这些场景已经运行通过。完整来源独立审计、四部分、合法非 Flow、owner 自依赖、纯实现修复、三类共享影响和同快照运行均未发现相反规则。

## 约束与排除项

权威方向（来源／ADR、采纳、Taskmaster、Core 契约、manifest、原始运行证据、派生 Knowledge）由 AD-1／3／7／16 保留；Windows／Godot 4.5.1／net8.0、Core／Contracts BCL-only、薄适配、原生场景和既有 ADR 由 AD-1／14／17、Stack 承接。ADR-0039 的匹配键、当前依赖／delta、历史 proof／新 adoption、worker／协调提交、持久预算及 epoch／reopen 撤销没有混同；完整 3A 审计与后续受治理投影保持边界。

未发现重编号历史、第二套 Task／MVG 生命周期、通用 DSL／解释器、全量生成、全仓 C# 迁移、玩法／数值／美术重制、额外引擎／平台、多租户／认证／沙箱／ji-mu-yun、质量或分支保护降级等扩围。没有 Task 数／交付时长／速度／成本下降承诺；当前交付止于架构和必要 SPEC 回补，不含实施任务生成、代码修改、运行验收、发布或 Story Breakdown。
