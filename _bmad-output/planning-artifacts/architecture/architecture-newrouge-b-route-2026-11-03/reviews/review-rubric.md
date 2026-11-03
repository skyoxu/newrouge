# 架构主干 Reviewer Gate：rubric walker

结论：通过；在本次 initiative 架构的静态语义审阅范围内，未发现阻断交接的规则缺失、不可执行决策或 SPEC 冲突。

严重度计数：Critical 0，High 0，Medium 0，Low 0。没有需 autofix、讨论、延期或忽略的实际 finding。

## 范围与证据边界

审阅对象为同目录上级的 `ARCHITECTURE-SPINE.md` 与 `planning-records.md`，按 `.agents/skills/bmad-architecture/references/reviewer-gate.md` 的 good-spine checklist 判断。驱动输入已完整阅读：`SPEC.md`、`workflow-contract.md`、`verification-contract.md`、`migration-and-pilot.md`，以及 SPEC 引用的 PRD `addendum.md`、`baseline-update.md`。同时阅读仓库 `AGENTS.md` 与 Accepted `ADR-0039-mvg-completed-capability-recovery.md`。

当前源码只做定向只读核对：`_planning_apply_journal.py` 的 before／after 冲突检查与完成恢复、`_mvg_obligations.py` 的无匹配 trace 返回 current、`_mvg_capability_checkpoint.py` 的 selected 提交点，以及 `_mvg_capability_recovery.py` 的磁盘已选完成项资格。版本核对使用 `global.json`、`NewRouge.csproj`、`Game.Core/Game.Core.csproj` 与现有 CI YAML。未执行 runtime tests、开发工作流、模型规划或 Windows／Godot 验收，也未修改架构或 memlog。本报告不证明目标设计已经实现。

按本轮授权，把确定性文件流水线、分阶段绑定、共享 journal／gate、派生 Knowledge、无数据库视为已决策条件；旧 2026-10-12 MVG 主干不作为此 initiative 的继承父主干。目标 JSON 字段是待实施的共享 schema 合同，不能因当前源码尚无对应字段就判为棕地事实错误。

## Good-spine checklist

| 检查项 | 判断与依据 |
| --- | --- |
| 固定下一层真正会分歧的边界 | 通过。来源与采纳权威、3B／3C／4–5阶段、唯一身份／owner、Task状态、B分类、所有入口、提交可见性、恢复、输入与运行身份、真实执行范围、UI／修复路由及生产适配均有约束。不是仅按功能目录分配模块。 |
| Rule 可执行且能防止所述分歧 | 通过。共享 schema／codec、InputSet resolver／gate、受管 apply 服务、catalog 发布点、scope租约、receipt复验和错误枚举均为具体检查／拒绝点；独立语义审阅和人工证据也明确保留，不以结构检查冒充语义或运行证明。 |
| Deferred 不释放共享分歧点 | 通过。调度与底层 Windows API 留给实施，但共享预算、写入权、统一模块和故障验证先决条件已定。DTO／节点名、参数与模块拆分由明确 owner 细化；公共身份、版本、写者、阶段、门禁、提交与恢复语义未延期。 |
| 技术版本与棕地一致 | 通过。Godot SDK 4.5.1、net8.0、.NET 8.0.401／latestPatch与仓库配置一致；Python 3.12与现有CI配置一致，没有增加Python patch门槛。官方存在性／适用性依据由已采纳addendum继承，本轮没有另作联网版本调查，也没有声称这些是最新版本。 |
| 棕地 ratification 而非重写 | 通过。保留既有 Taskmaster三联、journal、worker／协调器、selected、Requirement三组核算键和formal runtime证据。明确把无trace返回current限制在统一分类确认的legacy内，而非误称当前已具有B分类。新增catalog只管理正式采纳提交，不替代MVG run.json或任务状态。 |
| SPEC覆盖 | 通过。下表逐一核对11个CAP，并读取23个原始AC；无遗漏的跨入口、反例、试点或观测维度。 |
| 继承与权威不削弱 | 通过。AD-1、9、18保留来源／ADR、Contract源码、manifest、Task状态与历史证据的权限；明确ADR演进，不用新采纳记录静默覆盖旧ADR。ADR-0039的匹配键、历史proof、当前兼容性及独立adoption保持分离。 |
| initiative应拥有的环境／操作维度 | 通过。AD-17及结构图覆盖Windows工作站／现有CI、Python编排、模型runner、dotnet／Godot、版本化治理文件、logs与Knowledge。无新增服务／数据库；锁、占用、进程中断、重启、后编辑、失败恢复和默认切换前故障注入均有规定。精确镜像与运行patch作为证据记录，未越级建设部署平台。 |

## 逐项规则可执行性

| 决策 | 可观察的 enforcement／拒绝边界 |
| --- | --- |
| AD-1 | 记录只保存从属规划决定；Task状态／程序契约／累计义务／运行证明各有唯一权威，治理变化走ADR。 |
| AD-2 | 3B允许零Task且不调用5的Task readiness前置；实施阶段才校验具体义务，禁止draft／假witness。 |
| AD-3 | 一个共享schema／codec定义公共版本、引用、digest与错误；未知、损坏及必需缺失统一拒绝。 |
| AD-4 | 持久身份分配与重试绑定；Flow和共享命令／状态唯一owner；复用既有route、verification及evidence键。 |
| AD-5 | 冻结A清单、policy、catalog、origins与双向索引先校验，不能从缺trace推断legacy或删除B来源回退。 |
| AD-6 | 所有入口共用InputSet gate；非Flow须正式适用性与其他验证；当前Task不要求先done，integration owner不造API。 |
| AD-7 | 先盘点、审阅业务视图delta再三联编译；定义投影只排除版本化status白名单，写入冲突不覆盖成熟进度。 |
| AD-8 | prepare→reserve→apply→verify→publish→recover协议；单一catalog最后发布，消费者核对实际文件、receipt及前后catalog，旧pending也阻断。 |
| AD-9 | 仅selected已提交完成checkpoint可复用；历史proof、当前依赖／delta与新adoption分离；worker不能推进selected，epoch／reopen撤销保留。 |
| AD-10 | 精确相关InputSet与运行snapshot分开；raw／规范化身份并存；可变status及无关catalog不作为全仓语义失效键。 |
| AD-11 | 同一VerificationScope由影响计算与真实执行器消费；三类义务、requested／executed／not_run／manual覆盖和full口径明确。 |
| AD-12 | 逻辑四部分、owner、引用、可达性、SCC与退出检查；语义审阅另行承担，真实对象出现后才补类型／引擎证明。 |
| AD-13 | 纯实现缺陷复用采纳仍过readiness和回归；定义／契约变化回owning stage；Chapter7只补目标slice真缺口。 |
| AD-14 | 稳定奖励Flow、route-owned Reward、受控生产命令与只读状态，fixture隔离、薄C#适配及BCL-only边界固定。 |
| AD-15 | 3A完整累计来源审计；后续投影保原文、全局记账及proof；admission、预算与已观察成本分类明确。 |
| AD-16 | Knowledge提交身份／证据等级／branch视图分开；preview不推进发布指针；所有入口共用结构化诊断。 |
| AD-17 | 受管写者共用项目锁；短metadata锁与scope租约顺序、非阻塞冲突、Windows故障注入及默认切换门槛明确。 |
| AD-18 | 五批交付、A冻结／迁入／退出、全消费者适配、补偿式rollback与累计防削弱明确。 |

## CAP覆盖与关键反例

| CAP | 关键覆盖证据 |
| --- | --- |
| 1 | AD-2、15：完整来源／Ledger独立审计不能被首轮Flow或Task投影反裁。 |
| 2 | AD-2、4、12：正式零Task采纳、合法循环、四部分／交接、跨Capability及唯一owner。 |
| 3 | AD-3、4、8、9：不可变plan修订、lineage、持久分配、正式提交和有效完成项恢复。 |
| 4 | AD-7、8：复用盘点、真实缺口、受审阅delta、三联严格join及旧ID／状态／历史保留。 |
| 5 | AD-5–10、12、13：所有入口同一有效InputSet；非Flow合法通过、损坏／删依据拒绝、当前任务与owner无done自依赖。 |
| 6 | AD-6、11–13：局部／Flow职责与证据等级分开，Chapter7复用、planned不冒运行证明、人工义务保留。 |
| 7 | AD-10、11和VerificationScope：传递影响、未知扩大仍三分类、真实执行覆盖、共享测试身份去重及累计同snapshot。 |
| 8 | AD-8–10、13：operation内容绑定、同内容no-op、后编辑冲突、发布前后恢复与合法status推进；不恢复未完成模型中间态。 |
| 9 | AD-3、5–7、16、18：冻结A、B不可丢标回退、未知与合法缺失区分、Knowledge及全部入口同步、明确退出兼容。 |
| 10 | AD-9、15–17及伴随观测合同：完整传输／准入、持久预算、失败分类、耗时／调用／复用／返工追溯，无速度门槛。 |
| 11 | AD-14、18及驱动SPEC试点合同：同一奖励Flow双路径、候选／RNG／存档约束、生产接口／只读状态、C#薄适配与未来Windows／Godot原始证据。 |

共同基础设施的实现顺序已约束：初始schema／codec／读写服务是后续消费者的共同前置，不允许独立feature各建解析器；3Bbootstrap允许空Task origins与空冻结A集合，不把共享治理记录初始化变为Task前置死锁。scope租约覆盖共享Task当前及新增scope；metadata锁不跨模型调用持有。consumer既检查新B pending也检查既有capability pending，clone不能以缺本地logs绕过提交身份验证。

本次没有需要强行列出的风险finding。Windows原语、故障注入、运行证据与schema实现属于已明确约束的后续实施责任；架构通过不等同这些验证已经通过。
