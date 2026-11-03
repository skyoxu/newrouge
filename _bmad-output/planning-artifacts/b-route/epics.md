---
status: final
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
currentStep: complete
requirementsExtracted: true
requirementsConfirmed: true
epicsApproved: true
currentEpic: 5
draftStories: 0
approvedStories: 49
partyDiscussion: completed
finalValidation: passed
completionConfirmed: true
validationReport: logs/ci/2026-11-03/b-route-epics/final-validation.md
created: 2026-11-03
updated: 2026-11-03
workflow: bmad-create-epics-and-stories
scope: newrouge-b-route
branch: fix/capability-synthesis-input-integrity
inputSnapshotCommit: aa821824d1d2700e79cc615de34698dda12363d3
codeBaselineCommit: cd925bdcae4b61992320773497f7edb729aac244
inputDocuments:
  - "_bmad-output/specs/spec-newrouge-b-route/SPEC.md"
  - "_bmad-output/specs/spec-newrouge-b-route/workflow-contract.md"
  - "_bmad-output/specs/spec-newrouge-b-route/verification-contract.md"
  - "_bmad-output/specs/spec-newrouge-b-route/migration-and-pilot.md"
  - "_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/addendum.md"
  - "_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/baseline-update.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/ARCHITECTURE-SPINE.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md"
  - "_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/prd.md"
  - "_bmad-output/planning-artifacts/sources/newrouge-b-route-original-requirements.md"
inheritedConstraints:
  - AGENTS.md
  - _bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/baseline-update.md
---

# newrouge B 路线 - Epic Breakdown

## Overview

本轮将已完成的B路线PRD、SPEC及全部七份伴随文档分解为Epic／Story。用户已确认需求清单、5个Epic及全部49个Story，并以C结束Party讨论、批准修订后的Epic5；正式正文已保存，最终文档校验通过、0项未关闭检查；用户已以最终C确认完成工作流，本文置为final；尚未实施。

- 输入范围：用户已确认采用 frontmatter 的十份文件；AGENTS、addendum 所列有效 ADR／Base／Overlay 作为继承约束。原附件中的指令性文字仅作需求来源，执行范围以本轮用户指令为准。
- 规划顺序：沿用已采纳五批交付及其依赖，先保护基线，再交付无 Task 正式采纳、三联与 Chapter4–7 承接、真实验证与操作面，最后以奖励双路径证明并切换新增默认入口；沿用用户批准的5个Epic，不预分配真实Task数量、时长或日程。
- 目标与边界：本次是路线改变；不设置提速或降成本目标。Taskmaster 保持唯一任务状态，Knowledge 保持派生，不新增规划数据库。保留 PRD／SPEC 的产品排除项。
- 委托边界：上一轮文档链的“停止／不生成 Story”描述该轮执行范围；用户本轮已另行授权 Epic／Story 分解。当前不据此修改真实 Task 三联、不实施代码、不执行游戏验收或发布。
- 既有项目：这是 brownfield 改造，复用现有工具链与项目结构，没有 starter template，不创建新应用。
- 引用编号：FR 沿用上游身份；NFR-E 与 AR 仅是本清单的追溯编号，不是新游戏 Requirement ID、Task ID 或完成状态。
- 来源定位：FR 原文来自 `prd.md` §4；质量约束来自其 §5–8 及 SPEC，AR-1–18 对应架构主干 AD-1–18，AR-19–28 提取 `planning-records.md`／基线的实施细则。正式实施仍须消费原始合同，本文不取代来源权威。
- Story进度：5个Epic共49个Story／256组验收场景已获用户批准并写入本文；四项Party修订均保留。第4步最终文档校验已通过，用户已以最终C完成文档工作流；批准记录、来源哈希和检查证据保存在 `logs/ci/2026-11-03/b-route-epics/`。

## Requirements Inventory

### Functional Requirements

**FR-1: 完整来源记账**

规划者可注册累计来源，先形成完整 Source Block Ledger、Requirement 和需求验收意图，再生成 Task。每个声明来源均可解析、可定位，每个来源块均有语义投影或明确去向；分批读取保留完整性证明。未进入当前 Flow 的需求须有累计去向，包括其他 Flow、共享约束、其他验证、待实施范围或有依据的延期及范围外决定。Task、Capability 或节点数量不能作为覆盖充分条件。承接 BR-01；验收 AC-BR-01、02。

**FR-2: 独立来源审计前移**

Task 无关的独立提取、遗漏与冲突核对在 Chapter 3A 完成或有效复用。审计从完整来源及 Ledger 确定范围，不受首轮 Requirement、Task 引用或已选 Flow 裁剪。Chapter 5 继续核对 Task、Acceptance、契约和绑定；相关来源、解析器或审计输入变化时，仅复用仍有效的审计，不能刷新旧 readiness 时间戳代替重查。承接 BR-02；验收 AC-BR-02、09。

**FR-3: 零 Task 的正式规划与合法非 Flow 去向**

目标范围没有 Task 或 Chapter 5 Task readiness 时，仍可正式规划、审阅和采纳。已有实现、Task 和共享能力可辅助复用判断，但不成为新规划的必需存在条件。不得依靠假 Task、假 readiness 或草案绕过开关获得正式通过。

全局约束、治理和工具链需求可采用已采纳的非 Flow 验证去向，明确来源理由及其他验证义务。标签或空字段不能构成豁免；规划可采纳与 Task 可实施是不同结论。承接 BR-03；验收 AC-BR-01、21。

**FR-4: Flow 语义及四部分职责**

每条目标 Flow 可解析并回链到稳定身份、来源和 Requirement，包含起点、进入条件、成功终点、必要失败／取消／返回分支、关键交接、状态所有者、可观察结果和验证目标。四部分职责可机器读取；合法重入、重试和玩法循环不被无环图假设拒绝，必要可达性及退出条件须检查，检查能力边界由设计明确。

共享规则、命令、状态和资源引用同一受治理定义。每条 Requirement 保留单一权威验证处置／覆盖 owner；多 Flow 路线成员关系、共享依赖与去重证据另行表达，不重复计完成。允许一条 Flow 跨多个 Capability，也允许 Task 与 Flow 多对多，不强制一节点一 Task、四部分各一 Task或每 Task 同时修改四部分。不适用职责有明确理由。四部分在拆 Task 前及实施前的最低内容见 `addendum.md`“四部分的阶段完整性”。承接 BR-04；验收 AC-BR-03、05。

**FR-5: 持久采纳与稳定身份**

正式采纳结果具有持久版本、来源绑定、内容身份和采纳依据，可跨会话恢复、审阅差异并驱动 Task。前置 Flow 与后续 Task／契约／manifest 绑定共享同一 Flow 身份；同一已采纳输入恢复时复用有效结果，不重新解释 GDD 或重新分配身份。显式重规划保留差异及身份对齐，不要求模型输出逐字一致。承接 BR-05；验收 AC-BR-04、06。

**FR-6: 从真实缺口生成或复用任务三联**

规划者先核对已有实现、完成 Task、共享能力与验证义务，再从目标 Flow 或合法非 Flow 去向的真实缺口产生任务。Task 可独立实施和局部验证，并回链 Requirement、Acceptance、依赖、实施责任及适用验证义务。

生成沿用业务视图、审阅、编译三联的受治理路径，不让 Agent 随意直写 `tasks.json`。成熟身份与状态受保护，不以固定任务数量或未经实测的单 Task 时长约束拆分。承接 BR-06；验收 AC-BR-01、05、14。

**FR-7: 分阶段细化四部分与绑定**

Chapter 3B 定义业务角色和逻辑交接，3C 绑定实施 Task，Chapter 4–5 细化契约、生产命令、只读状态、适配生命周期、场景资源及测试责任。前置规划不要求实际 Task ID、完整代码符号或场景已创建；实施前义务必须足够明确，planned 对象可未建但不被宣称已实现。

检查随阶段覆盖引用、状态所有者、命令与只读边界、四部分责任及交接。真实对象存在后再增加类型、编译、绑定和引擎检查。结构检查不能替代业务语义审阅或运行证明，不为过检创建假节点或假接口。承接 BR-07；验收 AC-BR-03、04、12。

**FR-8: 一致的 readiness 与验证适用性**

Chapter 5 核对当前 Task Acceptance、Requirement、适用规划或非 Flow 去向、ADR、Overlay、Contract、依赖及验证义务，处理遗漏、重复责任和无人承接的交接。所有实施输入必须属于同一组当前有效依据。

- 归属 Flow，或承担 MVG 交接、集成、回归义务的 Task，须有有效 manifest 绑定；缺失或过期则拒绝。
- 合法非 Flow 且确无 MVG 义务的 Task，凭有效的已采纳适用性依据、其他验证义务及共同就绪条件进入实施，不强造 Flow 或 manifest 归属。
- 适用性未知、依据缺失／损坏／过期／来源不明时拒绝，并报告具体缺口。非 Flow 任务实际影响既有 Flow 时仍须承接相应回归。

相关语义或绑定变化使受影响 readiness 失效，无关变化不迫使全仓重做。进入 Chapter 6 不要求待实施 Task 已完成；纯集成测试 owner 不因新条件产生等待自身完成的死锁，保留 producer／consumer／owner 的适用差异。承接 BR-08；验收 AC-BR-08、09、15、21及原始需求第10节 owner 例外。

**FR-9: 全入口消费与局部修复**

公共 CLI、直接实施、恢复及页面触发共享上述门禁。B 来源 Task 必须显式消费有效来源、实施依据、readiness 和适用义务；丢失绑定或来源标识不能落入无义务 legacy 路径。保留单 Task Chapter 6、TDD／检查、评审、Needs Fix、pre-commit、恢复和现行质量底线。

Agent 发现上游定义不足时返回定义所属阶段，不自行弱化 Acceptance、改变状态所有权或绕过绑定。纯实现缺陷不改变已采纳定义时复用有效规划，完成必要 Task 映射、readiness、自检和适用回归；若需新修复 Task，保留旧完成历史。触及玩法定义、契约、所有权、交接／绑定或验收义务的修复返回相应上游阶段。承接 BR-09；验收 AC-BR-08、10、19、23。

**FR-10: 提前声明 UI 义务并由 Chapter 7 收口**

Flow 规划提前承接 UI、输入、动画反馈、场景入口及返回条件；相关代码和场景可由 Chapter 6 Task 实施。Chapter 7 面向目标 backlog slice 确认闭环、发现遗漏并通过既有治理路径补缺，不等待全游戏 Task 完成，不重复创建已实现且已验证的同义任务。没有 UI 义务时不强制 Chapter 7。

真实引擎输入、场景方法调用及静态接线分别表达，不互相冒充。承接 BR-10；验收 AC-BR-12、13。

**FR-11: 两层验证与完成边界**

Task 局部自检验证规则、接口、绑定和受影响局部行为；Flow 集成在目标链路齐备后验证真实输入、跨层交接、状态变化及最终结果。可共享工具、构建和预热，不建设两套重复框架，也不按每个按钮、节点或代码编辑启动完整 MVG。

Flow 完成须满足全部当前必需义务。planned 条目、关系存在、结构通过、空报告、跳过或未运行都不是运行通过；局部绿色不自动推导 Flow 完成。视觉与手感等人工义务按范围保留；合法非 Flow 按其他已采纳义务验证，影响 Flow 时仍回归。承接 BR-11；验收 AC-BR-10、12、17、21。

**FR-12: 真实的影响范围与三类义务**

共享状态、命令、契约、适配、场景资源或测试基础设施变化时，登记全部直接及必要传递影响，包括尚未实现的 Flow。交付范围由有效来源及采纳计划确定；系统产生可审阅、可执行的回归集合，并分别列明：

1. 既有受影响可运行 Flow 的完整必需回归。因本次改动无法运行或失败时须修复后验证，不得改记 planned 或移出范围。
2. 本次交付范围内新增或尚未完成的义务。未完成保持 pending／blocked，并阻断本次范围完成。
3. 有依据不属于本次交付范围的未来 Flow 或义务。更新影响、定义／绑定和后续责任，不强制提前实现，不宣称已验证，不从累计验收消失。

同一 Flow 可以同时承载既有回归和新增义务。未知映射保守扩大到适用累计范围，仍按上述三类处理，不把全部 planned 当作可执行回归。不得通过重分类、实现状态过滤或旧 manifest 遗漏本次要求。无法确认本次全部必需义务满足时不得报告完成。

允许保守执行更大范围；若选择性执行，执行器须真正消费范围并报告声明范围、实际执行、待完成及覆盖，推荐排序不等于选择性回归。普通 Flow 收尾与累计里程碑收尾分开，critical、partial 或单 Flow 通过不等于 full-MVG。承接 BR-12；验收 AC-BR-11、17、22。

**FR-13: 分别证明规划稳定、应用幂等和证据复用**

同一已采纳输入恢复不重新拆分；同操作身份与相同内容重复应用不重复建任务、施加 delta 或覆盖文件；完整相关输入及验证规则未变时才复用有效证据。

应用具有持久记录和明确恢复点；中断后先核对已落地结果，同身份异内容、损坏证据或后续人工编辑产生可解释冲突，不盲目重放。复用身份覆盖适用来源、采纳规划、Task、契约、绑定、规则及相关依赖，影响结果的工具链和环境也纳入，不能只比较 HEAD、Task ID、文件名或单一正文哈希。单项 Capability 的恢复匹配键、当前依赖／delta 兼容性及运行证据身份分别核对，继承 ADR-0039 的完成项规则。

共享测试结果只在输入、快照、测试身份及验证语义均匹配时供多 Flow 引用；共享预热不共享可变测试状态。最终累计通过使用同一整合快照，不拼接不一致报告。承接 BR-13；验收 AC-BR-06、07、09、17。

**FR-14: 存量保护与有界兼容**

新增需求默认 B；旧成熟 Task 的 ID、状态、历史依据和成果保留。更新、拆分、合并、退役有可审阅差异与依据，候选默认值不能覆盖旧状态。旧 Flow 和测试留在累计 manifest；删除、退役或降低义务沿用现有防削弱要求。

旧 done 不证明新义务已通过，新增责任用变更任务或明确更新承接。存量 A 仅在明确适用范围内执行，B 不能通过丢来源标识变为 legacy。兼容需要退出条件，不永久维护两套相互矛盾的规划真相；已采纳的具体退出边界见第7节。承接 BR-14；验收 AC-BR-14、15、19、22。

**FR-15: Knowledge 与操作入口一致**

Knowledge 可定位来源、Requirement、Capability、Flow、四部分、Task、契约、场景和验证义务的关系、缺口及影响。展示区分计划、实现和运行证据，也区分工作区／分支预览、attempt、stable 与 main 发布身份；预览不得推进 current／last-known-good。

规划页面、CLI 支持先规划后任务，显示真实阶段、阻塞原因及恢复位置，不统一以 Task readiness 阻断前置规划。Chapter 6 不隐式全局刷新 Knowledge，Agent 消费明确绑定定义及原始证据，不依赖页面摘要或临时重扫推断依据。承接 BR-15；验收 AC-BR-08、16。

**FR-16: 有界完整输入与失败成本**

保留输入完整性、隔离分析、独立语义核对、候选采纳和失败预算保护，只调整其所属阶段。大 GDD、长报告和多 Flow 以有界批次处理，跨批共享义务和引用仍完整，禁止静默截断。下游失败时，复用输入未变、已完成并持久化且仍有效的上游成果。MVG 新执行只恢复已提交完成项，不恢复未完成模型候选／修复／检查／评选上下文；Capability 的显式证据恢复按其独立规则处理。

记录规划、任务生成、局部验证、Flow 验证和修复的耗时、模型调用及复用；无确定性进展停止无效重试并保留恢复原因。成本及复用记录用于诊断重复工作和失败开销，不将成本下降、固定 Task 时长或提速比例作为路线改造验收条件。承接 BR-16；验收 AC-BR-09、20。

**FR-17: 生产者与消费者完整迁移**

迁移覆盖来源与规划生产者、业务视图生成及三联编译、Chapter 4–7、manifest 校验与执行、Knowledge／规划页面、CLI、Skill、文档和测试，不能仅凭修改 `workflow.md` 判定迁移完成。新旧格式、合法缺失、损坏和未知版本具有可验证且不同的行为；迁移明确输入输出、身份保留及恢复方式。

AGENTS 路由、阶段文档、公共入口和示例指向同一实际流程。最终须对最小必要的规划依据、定义和迁移说明进行版本管理；过程日志遵守 `logs/**` 规则，不要求全部提交 Git。Chapter 顺序及新采纳记录治理须有显式 ADR 演进，不默改现有派生拓扑的权威边界。承接 BR-17；验收 AC-BR-16、19。

**FR-18: 奖励真实切片及两条迁移路径**

采用 `combat-reward-return` 为存量迁移与真实消费者试点，保留 Flow 身份及有效责任映射。最小业务改动是将奖励领取／跳过／返回链路收敛到生产命令、只读状态和必要 C# 场景适配；保留现有玩法、候选锁定、地图路由及原生场景布局、美术、动画可编辑区域。

两条路径分别证明：已有 Task／Flow 的增量承接不重建成熟身份；所选奖励适配变更能在尚无该变更实施 Task／readiness 时先完成正式 B 规划，再按实际缺口产生或复用任务，走通 Chapter 4–7 和适用 MVG。两条路径不要求制造第二个同义 Flow、同义 Task 或新奖励玩法。

试点从既有战斗结果进入路由所属独立 Reward 场景开始，到领取或跳过后按规定路由返回 Map 并完成受控状态写回结束。覆盖重复提交、重入／Continue 保持候选及顺序、不重复写回、必要绑定断开及输入漂移反例。玩家行为与自动验证调用同一真实生产业务路径；fixture 初始化与玩家动作证据分开，不能靠测试命名入口或可变内部状态冒充生产接口。

只迁移承担该链路职责的必要适配与绑定，不重构 Combat／Map 全部实现或全仓 GDScript；公开契约只在确有新增或改变公共边界时受治理地更新。试点须有 Windows／Godot／C# 原始证据；关系导入、图生成或 schema 通过不足以完成。承接 BR-18；验收 AC-BR-18，并结合 AC-BR-06–09、12–15、19、21–23。

### NonFunctional Requirements

**NFR-E-1: 平台与领域边界** 保持Windows-only、Godot.NET.Sdk4.5.1、C#／net8.0及现有SDK策略；Core与Game.Core/Contracts保持BCL-only，Godot薄适配不复制领域裁决，原生场景／人工区域可编辑。

来源：PRD§5；SPEC Constraints；AD-14/17。

**NFR-E-2: 权威与完整任务体系** 来源和有效ADR管语义，Taskmaster三联保留唯一任务状态，契约源码／manifest／运行报告各守权威，Knowledge只派生；不建立第二Task或MVG完成状态机。

来源：PRD§2/5/6；AD-1/7/16。

**NFR-E-3: 追溯与新鲜度** 正式义务可定位当前来源、采纳修订、Task定义／Acceptance、契约／绑定及验证规则；相关变更精确失效，无关HEAD／catalog／其他Task状态不使全仓重做。

来源：PRD FR-8/13、§5；AD-10。

**NFR-E-4: 恢复可靠性** 同ID同内容幂等、异内容冲突，中断先核对完整相关输入和目标；保后续编辑与历史proof，仅按工作流资格复用有效已提交成果，不盲重放或重置预算。

来源：PRD FR-13/16；AD-8/9；ADR-0039。

**NFR-E-5: 输入完整性与有界处理** 大输入分批但正文／对象／引用完整，保raw proof和全局守恒；机器校验先行、独立语义审阅，未知／歧义不静默裁剪，容量不足和无进展按既有预算停止。

来源：PRD FR-1/2/16；AD-15。

**NFR-E-6: 证据真实性** 结构、编译、静态接线、场景方法、真实引擎输入及人工义务分开；planned／空／跳过不算运行通过；最终累计验证同整合快照，引用共享结果需输入／测试身份／语义／环境匹配且状态隔离。

来源：PRD FR-7/10/11/12/13；AD-11/13。

**NFR-E-7: 存量和质量底线** 成熟ID／状态／历史／成果及累计Flow／test保留，更新／拆合／退役有差异和授权，候选默认值不能覆盖旧状态；沿用现有P1必修、NeedsFix、xUnit／GdUnit4、回归及分支保护。

来源：PRD FR-14、§5；AD-7/18。

**NFR-E-8: 文件与证据管理** 文档UTF-8、中文沟通，代码／脚本／测试／注释／打印遵守英文约定；最小治理定义与迁移说明版本化，原始journal／调用／运行证据按logs管理，不要求全提交。

来源：PRD§5、FR-17；AD-3/17。

**NFR-E-9: 有限工作范围与重复工作控制** 本期仅B工作流与奖励所选适配边界；纯实现修复复用有效规划，Chapter6不隐式全局Knowledge重建，不按按钮／节点／每次编辑全量MVG，不为回归强迫提前实现范围外Flow。

来源：PRD FR-9/11/12/15、§6；AD-13/16/18。

**NFR-E-10: 路线目标与过程观测** 目标是先规划后Task的路线成立，不设提速、成本下降、两小时、固定Task数／时长门槛；保各阶段实测耗时／调用／复用／重复与返工记录，unknown不冒充实测或费用。

来源：用户确认；PRD§7.3/8；AD-15。

**NFR-E-11: 统一失败与发布边界** 必需依据缺失、损坏、未知版本、输入漂移及未发布状态统一failclosed并给可恢复诊断；preview／attempt／workspace／stable／main身份分开，预览不推进canonical指针，部分规划不授予运行完成。

来源：PRD FR-8/9/15/17；AD-5/6/16。

### Additional Requirements

- **AR-1: 权威与依赖方向 [ADOPTED]** 来源与有效 ADR 管语义，采纳记录只保存从属来源的规划决定；Taskmaster 管唯一任务状态，Core 契约源码管程序契约，manifest 管累计义务，原始运行证据证明对应快照结果。派生拓扑不反写这些权威；游戏运行不依赖规划工具。新增治理及 Chapter 顺序通过显式 ADR 演进落实。（来源：ARCHITECTURE-SPINE.md AD-1。）

- **AR-2: 语义采纳与实施就绪分阶段 [ADOPTED]** 3A 独立来源审计、3B 无 Task 正式采纳、3C 任务承接和4–5实施绑定使用不同阶段检查。3B 不要求 Task ID、readiness、完整代码符号或已建场景；5才检查当前 Task 的具体义务。现有后置 planner gate 通过显式阶段适配演进，不能以 draft 开关、假 Task／witness 绕过。（来源：ARCHITECTURE-SPINE.md AD-2。）

- **AR-3: 共享版本化记录与单一编解码** `docs/planning/b-route/` 存最小采纳、绑定、策略及提交记录；语义计划与绑定各自有不可变修订。一个受治理 schema／codec 模块拥有 `planning-records.md` 的公共形状、版本、路径、hash 与错误合同，各消费者调用它；不复制私有解析器。未知、损坏或缺失的必需格式阻断，迁移不静默降级。（来源：ARCHITECTURE-SPINE.md AD-3。）

- **AR-4: 稳定身份与需求核算分离 [ADOPTED]** 复用既有 Requirement／Flow／Task 身份；新身份由采纳操作持久分配且查重，重试不再分配，改义保留 lineage 和差异。Flow 可跨 Capability，Task 与 Flow 多对多。继承现有 route-membership、unique-verification、shared-evidence 三组键及 `coverage_table` 兼容投影，不按路线数增加完成计数或复制规则正文。（来源：ARCHITECTURE-SPINE.md AD-4。）

- **AR-5: B 来源不可通过缺失信息退回 A** 切换策略及冻结 A 清单为必需版本化输入；只有 Task 定义／来源仍符合冻结边界且无当前 B 义务者可走 A。B origins 与 Task／计划引用双向一致，B 归属不可删回 A。策略、catalog、origins 或依据缺失／损坏／未知时拒绝，不从“没找到 trace”推断 legacy。（来源：ARCHITECTURE-SPINE.md AD-5。）

- **AR-6: 全入口共享 InputSet 门禁** Chapter5／6、direct CLI、resume／route 和页面调用同一 InputSet resolver／gate；核对来源、采纳、Task 定义、Acceptance、绑定、readiness 及适用义务。Flow／MVG 责任须有有效 manifest；合法无 MVG 非 Flow 须有已采纳适用性与其他验证。未知则拒绝。入口不要求当前 Task 已 done，producer／consumer／integration-only owner 按实际责任检查，不造 owner API。（来源：ARCHITECTURE-SPINE.md AD-6。）

- **AR-7: 三联写入与任务状态归属 [ADOPTED]** 先盘点已有实现、完成Task、共享能力、四部分及验证责任，再仅为真实缺口产生经审阅的业务视图 delta，由既有三联编译路径写任务；保留 ID、状态、历史及严格 join。定义 fingerprint 与可变状态分开；依赖／运行参与者状态由入口另做实时资格检查。编译提交须合并当前状态并对整文件前像作冲突检查，不恢复 journal 中的旧状态覆盖新进度。（来源：ARCHITECTURE-SPINE.md AD-7。）

- **AR-8: journal 恢复与一致提交可见性** 复用 journal，在项目操作锁下绑定 operation ID、请求内容、全部 authority 与目标 before／after 身份，写持久 pending；预检及逐目标写前复核，冲突不覆盖。全部目标与最小提交 receipt 完成验证后，最后原子发布单一 catalog；消费者复验 receipt、当前相关目标及 catalog 前后身份，不仅看 pending 是否存在。未知提交、中断或占用须消歧／阻断；完成操作同内容 no-op，同 ID 异内容冲突。具体协议见伴随文件。（来源：ARCHITECTURE-SPINE.md AD-8。）

- **AR-9: 继承完成项恢复与 worker 边界 [ADOPTED]** 保持 ADR-0039 的单项规范化内容匹配、历史冻结 proof、当前依赖／delta 校验与独立 adoption receipt；只复用已提交完成 checkpoint。独立 worker 无权推进 selected；协调器掌握复验、提交及持久预算；epoch／reopen 撤销继续生效。新 MVG 执行不恢复未完成候选／修复／检查／评选上下文。Capability 显式证据恢复及正式 apply journal 分别遵守其原合同。（来源：ARCHITECTURE-SPINE.md AD-9。）

- **AR-10: 相关输入与运行快照分别绑定** InputSet digest 覆盖当前相关来源、采纳修订、Task 定义／Acceptance、契约／绑定、适用义务、依赖闭包、检查规则及影响结果的工具／环境；不把整个 catalog hash、无关 Git 提交或可变 Task 状态等同语义改变。raw frozen proof 与声明的规范化视图分存并注明 codec。未知依赖保守扩大。最终运行结论沿现有 formal receipt／inventory／snapshot manifest，累计通过不得拼接不同整合快照。（来源：ARCHITECTURE-SPINE.md AD-10。）

- **AR-11: 影响与执行共用范围合同** 从受治理反向引用与累计 delta 计算必要传递影响，含 planned Flow；未知扩大后仍区分既有必需回归、本次交付新增和范围外未来义务。真实执行器消费同一范围合同，报告声明／实际／未执行／人工及覆盖，按有效身份去重共享测试。坏掉的既有 Flow 须修后回归；本次未完阻断，未来责任保留。Flow／partial／critical 不授权里程碑 full-MVG。（来源：ARCHITECTURE-SPINE.md AD-11。）

- **AR-12: 四部分定义与循环检查 [ADOPTED]** 3B 完整定义四部分逻辑责任、状态所有者及交接；Task 只承接适用部分，4–5细化生产命令、只读状态、类型／生命周期／资源绑定。确定性检查引用、边界唯一性、必要可达性、循环分量及声明退出；独立语义审阅覆盖条件与交接，不承诺证明任意程序终止。真实对象出现后补编译、类型、绑定及引擎检查；planned 不是实现证据。（来源：ARCHITECTURE-SPINE.md AD-12。）

- **AR-13: 修复与 UI 复用 [ADOPTED]** 纯实现缺陷复用当前有效采纳，仍完成必要映射、readiness、自检与受影响回归；改定义／契约／所有权／交接／义务则回 owning stage 做受治理 delta。Chapter7 只收口目标 slice，复用6已验证 UI；真实输入、场景方法、静态接线及人工义务分别取证，局部 PASS 不推导 Flow 完成。（来源：ARCHITECTURE-SPINE.md AD-13。）

- **AR-14: 奖励生产边界 [ADOPTED]** 保 `combat-reward-return` 身份、独立 route-owned Reward、Map 返回归属及候选／RNG／存档约束；只迁移所选生产命令、只读状态和必要 C# 薄适配／绑定。玩家与自动验证走同一业务入口，fixture 隔离；Core／Contracts BCL-only，原生场景与人工区域保留。公共契约真实变化才同步源码、Overlay 和 contractRefs。（来源：ARCHITECTURE-SPINE.md AD-14。）

- **AR-15: 完整来源与候选准入 [ADOPTED]** 3A 从完整累计来源与 Ledger 独立核对；后续仅按受治理闭包投影模型相关输入，保适用原文、全局记账及守恒 proof。复用现有无损传输、机器先行、独立语义 admission、隔离及稳定预算；未知／歧义保留，真正容量不足停止而不裁剪。执行故障、语义硬问题及预算终止分开。规划、Task生成、局部／Flow验证及返工均记录可追溯耗时、实际调用、复用和重复执行；观测不设提速门槛，不将预算预留当已观察费用。（来源：ARCHITECTURE-SPINE.md AD-15。）

- **AR-16: 派生展示与统一诊断 [ADOPTED]** Knowledge 读取提交身份，只读展示计划／实现／运行及分支／workspace／attempt／stable／main。committed prefix 可显示部分规划但不授权运行完成；preview 不写 current／last-known-good，6不隐式全局 refresh。所有入口使用共享 reason_code／stage／entity／expected／actual／resume_ref 诊断，不能以摘要替代原始绑定输入。（来源：ARCHITECTURE-SPINE.md AD-16。）

- **AR-17: 本地操作与环境边界** 新增能力运行于现有 Windows 工作站／CI 和既有 Python 编排，schema／文件门禁不依赖再次调用模型；无新数据库或分布式服务。最小治理记录入版本管理，原始 journal／调用与运行证据放 `logs/**`。受管写者共用项目锁；写入期间目标不支持并行人工编辑，发现后编辑或无法获得写入条件即冲突停止。Windows 占用／中断／重启故障注入通过前不切换默认 B；沿用现有平台、权限及 trusted-ref 发布规则。（来源：ARCHITECTURE-SPINE.md AD-17。）

- **AR-18: 有界迁移与退出 [ADOPTED]** 按已采纳五批交付，先固定／冻结A、建立正式无 Task 路径，再接入三联／4–7、真实执行与操作面，奖励双路径取证后切换新增默认 B。全部生产者／消费者／Skill／路由／示例及版本合同同步；活跃A完成或迁入且恢复测试通过后撤除其写入兼容，保历史读取。退役／减义务及回退都经差异审阅和防削弱检查；回退为有依据的补偿操作，保留后编辑与 B 来源。（来源：ARCHITECTURE-SPINE.md AD-18。）

- **AR-19: 共享记录与写者** 实现一处公共schema／codec及计划、绑定、策略、origins、commit、catalog六类版本化合同；plan与binding独立单调修订，同Flow／共享定义唯一owner；新记录从属来源，派生topology不升权。（来源：planning-records§记录与写入归属；AD-3/4。）

- **AR-20: 类型、路径和规范化** 公共引用仓库相对POSIX、明确schema／ID／修订和digest；拒绝根外路径／符号链接、重复JSON键、非法类型／未知schema／非有限数；canonical对象排版无关，数组序／类型／字符串值保留，raw proof另存。（来源：planning-records§引用、类型及内容身份。）

- **AR-21: Task状态与定义指纹分开** 初版可变allowlist仅Task／subtask.status，冻结verification_mode／codec／投影digest；提交保raw前后像，后续按相关Task定义＋实时资格检查，完成no-op不回写旧状态；未完成冲突先停止。（来源：planning-records§引用、类型及内容身份；AD-7/10。）

- **AR-22: 来源分类和零Task bootstrap** 策略／catalog／origins为必需治理输入，冻结A资格及完整反向Task索引，B不可删回A；3B可无Task映射及空Task bootstrap，不造Task或Chapter5 witness；合法非Flow需采纳理由与其他验证，真实MVG影响仍绑定。（来源：planning-records§记录与写入归属、Task来源分类和非Flow；AD-2/5/6。）

- **AR-23: 应用发布和租约** 复用journal和既有锁，执行prepare/reserve/apply/verify/publish/recover；同操作内容绑定、前后像及authority复核，receipt排除自身／catalog输出hash以免循环，catalog最后发布；scope租约按统一顺序，长模型／运行不持全局metadata锁。（来源：planning-records§共享apply与恢复协议；AD-8/17。）

- **AR-24: 已有pending、完成项与清理** 共享gate识别既有capability-apply.pending.json及原journal，未知scope保守阻断；无pending clone仍核提交链。继承ADR-0039原proof／新adoption、独立worker／父协调器复验、稳定预算、epoch／reopen撤销；本地clear不删除正式版本化采纳或累计基线。（来源：planning-records§共享apply与恢复协议；baseline-update；AD-9。）

- **AR-25: 真实验证范围接口** 按注册反向边和累计delta推导传递影响；VerificationScope绑定plan／manifest／基线／InputSet，执行器回执列声明／实际／未运行及原因／人工／覆盖，未知扩大仍三分类，复用测试需有效同快照身份，不把recommend排序当选择执行。（来源：planning-records§影响与执行范围接口；AD-11。）

- **AR-26: 诊断和观测生产责任** 共用reason_code／stage／entity_id／expected／actual／resume_ref，显式null不授权；阶段执行者写带run/operation、scope、stage、attempt的实测观测，同event去重，预算预留和暂停墙钟不作账单。（来源：planning-records§诊断与实施接入；AD-15/16。）

- **AR-27: 当前实现与改造缺口** 当前基线已有无损输入、分阶段synthesis、真实模型身份、逐Capability三候选／checkpoint／worker／完成项恢复／全局audit；继承不重造，正式无Task/readiness规划仍是待改造缺口。现有代码和旧窄架构的TARGET字样按当前源码/ADR事实解释。（来源：baseline-update；架构DesignParadigm与AD-2/9。）

- **AR-28: 消费者、ADR和切换前反例** 接入来源审计、planner、三联compiler、4/5、_mvg_obligations和6direct/route/resume、7、manifest/runner/milestone、Knowledge/页面/CLI/Skill/文档测试；schema共同产物前置，启用前覆盖缺origin/manifest、旧pending、journal损坏、崩溃点、后编辑、共享Task、状态并发、epoch/nonFlow/owner反例，Chapter/权威演进显式ADR。（来源：planning-records§诊断与实施接入；AD-17/18。）

### UX Design Requirements

未提供独立 UX DESIGN／EXPERIENCE 合同，因此本次不新增 UX-DR 条目。奖励生产场景的输入、领取／跳过／返回、只读状态、原生可编辑场景，以及规划页面的分支／workspace／attempt／stable／main 与失败诊断职责，已由 FR-10／15／18 和 AR-13／14／16／26 承接；不从模板推导视觉重设计、设计 token 或新组件范围。

### FR Coverage Map

主交付指定牵头Epic，共同承接列出阶段部分及最终业务证明；跨阶段FR须在所有适用部分满足后才算完整，不以主交付提前宣告全部通过。

| FR | 主交付 | 共同承接 | 可观察责任 |
| --- | --- | --- | --- |
| FR-1 | Epic 2 | 无 | 完整来源Ledger和累计去向 |
| FR-2 | Epic 2 | 无 | 独立来源审计前移 |
| FR-3 | Epic 2 | Epic 3 | 无Task正式采纳和合法非Flow |
| FR-4 | Epic 2 | Epic 3 | 逻辑Flow、四部分与唯一验证责任 |
| FR-5 | Epic 2 | Epic 5 | 持久采纳、稳定身份和显式差异 |
| FR-6 | Epic 3 | Epic 5 | 真实缺口盘点与三联生成／复用 |
| FR-7 | Epic 3 | Epic 2、Epic 5 | 3B逻辑定义至4–5绑定的阶段细化 |
| FR-8 | Epic 3 | Epic 4、Epic 5 | 共同InputSet、readiness和适用性 |
| FR-9 | Epic 3 | Epic 4、Epic 5 | 全入口门禁与局部修复路由 |
| FR-10 | Epic 3 | Epic 4、Epic 5 | UI义务提前承接与Chapter7复用 |
| FR-11 | Epic 4 | Epic 3、Epic 5 | 局部／Flow验证与真实完成边界 |
| FR-12 | Epic 4 | Epic 5 | 必要传递影响及三类义务的真实执行 |
| FR-13 | Epic 4 | Epic 2、Epic 3、Epic 5 | 规划稳定、应用幂等与证据复用分别证明 |
| FR-14 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 | 成熟成果保护、冻结A边界与条件退出 |
| FR-15 | Epic 4 | 无 | 派生Knowledge与操作入口身份一致 |
| FR-16 | Epic 2 | Epic 3、Epic 4、Epic 5 | 完整有界输入、预算止损与过程观测 |
| FR-17 | Epic 4 | Epic 1、Epic 2、Epic 3、Epic 5 | 全部生产者／消费者／文档和格式迁移 |
| FR-18 | Epic 5 | 无 | 奖励新规划／存量增量双路径与真实运行 |

NFR-E及AR为已确认清单的追溯编号，不另建任务／完成状态。以下列出各项牵头与共同承接，所有Epic同时遵守适用全局约束。

| 约束 | 主交付 | 共同承接 |
| --- | --- | --- |
| NFR-E-1 | Epic 5 | Epic 1、Epic 2、Epic 3、Epic 4 |
| NFR-E-2 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 |
| NFR-E-3 | Epic 3 | Epic 2、Epic 4 |
| NFR-E-4 | Epic 2 | Epic 3、Epic 4、Epic 5 |
| NFR-E-5 | Epic 2 | Epic 1、Epic 4 |
| NFR-E-6 | Epic 4 | Epic 2、Epic 3、Epic 5 |
| NFR-E-7 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 |
| NFR-E-8 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 |
| NFR-E-9 | Epic 3 | Epic 2、Epic 4、Epic 5 |
| NFR-E-10 | Epic 4 | Epic 2、Epic 3、Epic 5 |
| NFR-E-11 | Epic 3 | Epic 1、Epic 2、Epic 4、Epic 5 |
| AR-1 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 |
| AR-2 | Epic 2 | Epic 3 |
| AR-3 | Epic 1 | Epic 2、Epic 3、Epic 4 |
| AR-4 | Epic 2 | Epic 3、Epic 4、Epic 5 |
| AR-5 | Epic 3 | Epic 1、Epic 2、Epic 5 |
| AR-6 | Epic 3 | Epic 4 |
| AR-7 | Epic 3 | Epic 1、Epic 5 |
| AR-8 | Epic 2 | Epic 3、Epic 4 |
| AR-9 | Epic 2 | Epic 3、Epic 4 |
| AR-10 | Epic 3 | Epic 2、Epic 4 |
| AR-11 | Epic 4 | Epic 3、Epic 5 |
| AR-12 | Epic 2 | Epic 3、Epic 5 |
| AR-13 | Epic 3 | Epic 4、Epic 5 |
| AR-14 | Epic 5 | 无 |
| AR-15 | Epic 2 | Epic 3、Epic 4 |
| AR-16 | Epic 4 | Epic 2、Epic 3 |
| AR-17 | Epic 1 | Epic 2、Epic 3、Epic 4、Epic 5 |
| AR-18 | Epic 5 | Epic 1、Epic 2、Epic 3、Epic 4 |
| AR-19 | Epic 1 | Epic 2、Epic 3、Epic 4 |
| AR-20 | Epic 1 | Epic 2、Epic 3、Epic 4 |
| AR-21 | Epic 3 | Epic 2、Epic 4 |
| AR-22 | Epic 2 | Epic 1、Epic 3、Epic 5 |
| AR-23 | Epic 2 | Epic 3、Epic 4 |
| AR-24 | Epic 3 | Epic 2、Epic 4 |
| AR-25 | Epic 4 | Epic 3、Epic 5 |
| AR-26 | Epic 4 | Epic 1、Epic 2、Epic 3、Epic 5 |
| AR-27 | Epic 1 | Epic 2、Epic 3、Epic 4 |
| AR-28 | Epic 4 | Epic 1、Epic 2、Epic 3、Epic 5 |

## Epic List

用户已批准以下5个Epic。依赖顺序为Epic1→2→3→4→5；每个Epic可在其前置完成后独立验收，不等待后续Epic补齐自身功能。共享schema／codec是前置共同产物；公共journal／提交服务由正式采纳路径交付，三联与绑定复用。

### Epic 1: 可审阅迁移并保护既有成果

仓库维护者可盘点当前生产者、消费者、来源和成熟成果，生成可审阅差异与冻结A边界，识别会覆盖任务状态、改变身份或削弱累计义务的迁移。

**FRs covered（主覆盖）：** FR-14。

**共同承接：** FR-17。

**前置：** 无。

**交付范围：** 固定当前代码／来源基线、Task三联join与ID／状态／历史、现有Flow／test及运行证据身份；形成消费者矩阵、复用／缺口盘点和迁移预览。提供一处公共六类记录schema／codec、路径／类型／digest及诊断合同，用于该预览的合法性和保护检查，并定义后续公共写者接口。冻结A清单及策略有明确审阅来源，不从可选trace缺失推断legacy。Chapter顺序和治理权威变化登记显式ADR演进责任。

**独立验收结果：** 可以在现有仓库或零Task仓库完成预检和冻结边界审阅，定位重复ID、三联断链、成熟状态覆盖、累计义务退役缺依据及未知格式；预览不推进正式catalog或Knowledge发布指针。此Epic完成迁移前决策与保护能力，不以未来planner、实施门禁或奖励改造为通过前提。

**边界与交接：** 共享codec与版本合同是可交付预检的组成部分；不借此一次性创建未来plan／binding实例，不宣称全部实施入口已切换。正式记录bootstrap／发布由Epic2完成，入口强制分类由Epic3完成。

### Epic 2: 无实施Task也能正式规划、审阅和采纳

规划者可先把完整来源转换为Requirement、Capability／Flow或合法非Flow去向，在没有变更Task／readiness的情况下正式采纳并安全恢复同一计划。

**FRs covered（主覆盖）：** FR-1、FR-2、FR-3、FR-4、FR-5、FR-16。

**共同承接：** FR-7、FR-13、FR-14、FR-17。

**前置：** Epic 1。

**交付范围：** 完整累计Source Block Ledger与验收意图、独立来源审计；Task无关阶段适配、逻辑四部分、交接、分支／循环／退出、唯一验证owner与多Flow成员关系。复用现有无损传输、隔离候选、独立语义admission、父协调提交／稳定预算及ADR-0039完成项恢复。实现公共journal／锁／receipt／catalog最终发布、合法零Task bootstrap、不可变plan修订、持久身份与差异；诊断及实测阶段事件随生产者产出。

**独立验收结果：** 来源与所有来源块有可核对去向；无Task／readiness／代码符号／实际场景时可正式采纳Flow或有依据非Flow。重复请求不重新分配身份或重复采纳，同ID异内容、后编辑、损坏和发布中断产生明确恢复或阻断；只复用已完成且当前仍有效的成果，不恢复新MVG执行未完成模型中间态。可以只规划而不生成Task。

**边界与交接：** 使用Epic1唯一codec；本Epic实现一次共享提交服务，后续编译／绑定适配复用。合法规划采纳不依赖Epic3的Task readiness或Epic4页面展示／运行范围接口；采纳结果不代表已实施或运行通过。

### Epic 3: 按已采纳定义承接任务并一致实施与恢复

实施者可从真实缺口生成或复用完整Task三联，按当前绑定定义进入Chapter4–7，并在直接调用、恢复或路由入口得到一致决定。

**FRs covered（主覆盖）：** FR-6、FR-7、FR-8、FR-9、FR-10。

**共同承接：** FR-3、FR-4、FR-11、FR-13、FR-14、FR-16、FR-17。

**前置：** Epic 1、Epic 2。

**交付范围：** 复用盘点→业务视图delta→审阅→三联编译；保成熟身份、状态／历史，分离Task定义指纹与可变status。细化四部分的生产命令、只读状态、契约／资源／生命周期与测试责任；共享InputSet resolver和A／B／合法非Flow分类，接入Chapter5／6 direct／route／resume、页面实施触发及Chapter7。Task映射、origins及完整反向索引同提交；编译／绑定应用复用Epic2提交服务并校验旧pending。纯实现修复复用有效规划；定义变化返回owning stage。

**独立验收结果：** 真实缺口形成可实施／可局部验证的三联，进入6不要求本Task已done；合法非Flow及integration-only owner可按责任通过，缺manifest／B来源、未知或过期输入统一拒绝。相关定义变化使相关readiness失效，无关发布／其他Task状态推进不触发全仓失效；并发状态变化及后编辑不被旧journal覆盖。Chapter7复用已验证UI并只补真实缺口，无UI可不适用。

**边界与交接：** 运行仍可沿既有累计manifest执行，必要回归不延期；Epic4再提供统一影响范围请求、覆盖回执与完整操作面。Epic3的实施准入和局部检查不能以Epic4页面或选择性范围执行为前置，也不宣称单Task已完成整个Flow。

### Epic 4: 执行真实适用验证并展示可信进度

验证者能区分局部、Flow和累计里程碑结果，执行受影响义务并核对实际覆盖；操作者能从页面／CLI定位真实阶段、阻塞和恢复位置。

**FRs covered（主覆盖）：** FR-11、FR-12、FR-13、FR-15、FR-17。

**共同承接：** FR-8、FR-9、FR-10、FR-14、FR-16。

**前置：** Epic 1、Epic 2、Epic 3。

**交付范围：** 受治理反向引用与累计delta驱动必要传递影响，含planned Flow；VerificationScope连接真实runner／manifest／milestone handoff，明确既有必需、本次新增和范围外未来三类。绑定声明／实际执行／未运行原因／人工义务／覆盖及同整合快照；共享测试按有效身份去重并隔离可变状态。Knowledge、规划页面、CLI、Skill、AGENTS／阶段文档和示例完成迁移，preview／attempt／workspace／stable／main分开；汇集各阶段原有实测事件及统一诊断。跨入口和Windows恢复反例形成可复核结果。

**独立验收结果：** 影响范围真实到达执行器，允许有声明的更大保守执行；空、跳过、planned、本次未完和旧回归失败不被重分类成PASS。单Flow／partial不能冒充full-MVG，累计结果同整合快照。页面在无Task规划阶段可用且不篡改current／last-known-good；Chapter6不隐式全局刷新。所有生产者／消费者／文档一致并可追溯，过程观测不设速度或费用下降门槛。

**边界与交接：** 复用Epic2／3提交、分类和诊断服务，仅扩展验证范围与派生展示；不新增Task／MVG完成状态，不重造测试框架或分析平台。到本Epic已有可使用的通用B链路，不依赖未来奖励特定改造证明其每项功能。

### Epic 5: 用奖励双路径证明B路线并有条件切换入口

玩家经同一生产命令领取／跳过奖励并按既有路由返回Map；维护者以真实新规划及存量增量两条路径判断何时切换新增默认入口，并按条件退出A写入兼容。

**FRs covered（主覆盖）：** FR-18。

**共同承接：** FR-5、FR-6、FR-7、FR-8、FR-9、FR-10、FR-11、FR-12、FR-13、FR-14、FR-16、FR-17。

**前置：** Epic 1、Epic 2、Epic 3、Epic 4。

**交付范围：** 沿用combat-reward-return身份与成熟Task／累计Flow／test，完成所选生产命令、只读状态、必要C#薄适配及绑定；保独立route-owned Reward、Map返回所有权、候选及顺序、RNG／存档边界和原生场景人工区域。两条路径共用既有Flow，不造同义Task／Flow：变更范围无Task先正式采纳，以及成熟成果上的增量承接。取得Windows／Godot／C#真实输入、运行及适用人工证据后评估新增默认B切换；记录受治理补偿与A退出条件。

**独立验收结果：** 玩家与自动验证走同一生产业务入口，fixture与玩家动作证据分开；领取／跳过、重复提交、重入／Continue、断绑定及输入漂移反例成立。两条路径各有采纳→三联→4/5→6→适用7→全部必需Flow及受影响回归证据；不以本Flow结果冒充整个里程碑完成。默认B仅在消费者一致、恢复／失败反例及真实试点证据齐备后切换。只有活跃A全部完成或受治理迁入且恢复测试通过时才撤A新规划／写入兼容；未满足则保有界旧范围和明确未满足项，历史只读追溯保留。

**边界与交接：** 只改既定奖励边界，不扩为全游戏／Combat／Map重构或全仓C#迁移；不降低现有P1／回归要求，不以旧done覆盖新义务。此处是未来Epic的交付定义，本轮仅生成分解文档。

## Epic 1: 可审阅迁移并保护既有成果

仓库维护者可盘点当前生产者、消费者、来源和成熟成果，生成可审阅差异与冻结A输入，识别会覆盖状态、改变身份或削弱累计义务的迁移。主覆盖FR-14，共同承接FR-17；最终默认B切换／A退出和跨阶段FR完整性仍按已批准Epic覆盖图判断。

适用NFR-E-2／3／7／8／9／11与AR-1／3／5／17／19／20／27等已确认约束；无独立UX合同，本Epic不新增UI设计工作。schema／codec作为预检能力组成部分前置，正式发布服务和实施resolver分别由后续Epic承接。

### Story 1.1: 生成可复查的当前基线与消费者盘点

As a 仓库维护者,
I want 固定当前仓库的真实输入、既有能力和消费入口,
So that 能区分需继承的现有成果与B路线缺口，审阅迁移范围。

Refs: FR-14；FR-17（盘点部分）；NFR-E-2；NFR-E-7；NFR-E-8；AR-17；AR-27；AC-BR-14；AC-BR-16（入口盘点部分）。

**前置：** 无；使用当前已存在的仓库读取能力。

**范围：** 只读盘点与可复查报告；复用已有来源／Task三联／manifest读取路径，报告可由独立盘点入口直接生成。不是3A完整来源块语义审计，也不调用模型生成新规划。

**Acceptance Criteria:**

**AC-1**

**Given** 当前仓库含当前分支、已提交基线及可能存在的工作区修改，
**When** 维护者运行基线盘点，
**Then** 报告分别记录实际HEAD、分支、声明代码基线、适用源文件路径及raw digest、工作区差异和采集身份，
**And** 原始a8a363aa…／历史8f93557…只作历史来源；不能把cd925bd…上的已有worker／checkpoint／恢复能力写成待重建或声称B已实现。

**AC-2**

**Given** AGENTS路由、有效ADR／Base／相关Overlay及本轮十份输入可读取，
**When** 生成来源及消费入口矩阵，
**Then** 矩阵覆盖来源／Ledger／审计、Capability／MVG planner、业务视图与三联compiler、4–7、manifest／runner／milestone handoff、Knowledge／页面／CLI／Skill／文档示例，
**And** 每行有实际文件或符号定位、当前读写责任、A／目标B差异及后续Epic承接；ADR状态以正文为准，两份ADR-0038使用完整文件名。

**AC-3**

**Given** 当前Task三联和累计manifest存在，
**When** 生成存量概览，
**Then** 报告通过原有join定位Task ID／状态／历史引用、Flow／test身份与原始文件证据，
**And** 不分配新ID、不重编号、不修改状态或原报告，不以固定旧Task数量限制后续真实缺口。

**AC-4**

**Given** 声明输入缺失、不可读、损坏或现有映射无法证明一致，
**When** 运行盘点，
**Then** 报告列出具体文件／实体、缺口及阻断或未知结论，
**And** 不以README摘要、缓存、文件名、空清单或模型自报替代缺失依据，不把失败报告当可采纳基线。

**AC-5**

**Given** 相同输入被重复盘点或采集期间相关文件改变，
**When** 比较采集前后身份并保存报告，
**Then** 相同内容保持可比较的内容身份，实测采集事件与时间另记；采集中发生漂移则报告不稳定并要求重采，
**And** 原始报告留logs，正式最小基线引用由后续1.5审阅保存；不调用付费模型、不写Task／规划发布指针。

### Story 1.2: 明确B阶段顺序、记录权威及迁移启用规则

As a 工作流维护者,
I want 把已确认的B路线写入可审阅的治理变更及入口路由,
So that 后续记录和阶段适配有明确授权边界，操作者不会把规划采纳、实施就绪和运行完成混用。

Refs: FR-14；FR-17（治理部分）；NFR-E-2；NFR-E-7；NFR-E-9；AR-1；AR-2；AR-5；AR-18；AC-BR-15；AC-BR-16。

**前置：** Story 1.1。

**范围：** 只落实已确认的顺序和权威决定，不重新选择架构、不改质量阈值。新增或supersede相关ADR并按现有治理完成审阅，编号在实施时按当时目录分配；不把未审阅Proposed记录视为Accepted。

**Acceptance Criteria:**

**AC-1**

**Given** 本轮PRD／SPEC／架构已确认且1.1盘点可定位受影响入口，
**When** 维护者提交阶段和治理ADR变更，
**Then** 明确3A来源审计、3B无Task正式采纳、3C任务承接、4–5绑定／readiness、6单Task、适用7及Flow／累计收尾的责任，
**And** 3B不需要Task／readiness／真实场景，进入6不要求本Task已done，单Task或Flow绿色不授予累计完成。

**AC-2**

**Given** 现有来源、Taskmaster、契约、manifest、运行报告及派生拓扑各有权威，
**When** 审阅新增最小规划记录的地位，
**Then** ADR保留来源语义、Taskmaster唯一任务状态、Core契约源码和累计manifest的各自责任，采纳决定从属来源，Knowledge保持派生，
**And** 不新增规划数据库、第二套Task／MVG生命周期或游戏运行依赖；两份ADR-0038和ADR-0039的继承关系明确。

**AC-3**

**Given** 启用B、冻结A、保留旧范围和最终退出兼容属于不同操作，
**When** 审阅策略及回退规则，
**Then** 新增默认B须等待后续消费者、恢复反例和奖励双路径真实证据；A仅在冻结且仍有效的边界实施／恢复，相关变化按受影响范围迁B，
**And** 退出A写入兼容须满足所有活跃A完成／迁入及恢复验证等条件，回退使用受审阅补偿且保后编辑／历史／B来源，不以删标识降回A。

**AC-4**

**Given** ADR审阅及状态尚未达到现有准入要求，
**When** 更新AGENTS和owning文档路由，
**Then** 新增说明可被准确找到并标明定义与待实现／待启用状态，实施顺序及后续承接清楚，
**And** 本Story只有治理文本按现有审阅准入后才算完成；未准入不启用新行为，不把提案、已安装BMAD或本轮文档当运行验收。

**AC-5**

**Given** 治理变更经过审阅，
**When** 核对范围和质量约束，
**Then** Windows／Godot4.5.1／C#、BCL-only Core／Contracts、现有测试／P1底线与分支保护保持有效，五批交付及奖励边界可回链，
**And** 目标明确为路线改变；不增加提速、降成本、固定Task数／时长等成功门槛。

### Story 1.3: 统一核验文件引用与规范化内容身份

As a 迁移审阅者,
I want 通过同一公共codec核对文件引用、raw与规范化内容身份，并得到可定位的诊断,
So that 不同入口不会对同一文件内容或错误作出矛盾判断。

Refs: FR-14；FR-17（公共合同部分）；NFR-E-3；NFR-E-8；NFR-E-11；AR-3；AR-17；AR-19；AR-20；AR-26（诊断公共形状）；AC-BR-19。

**前置：** Story 1.1、Story 1.2。

**范围：** 一处共享codec／引用和诊断定义，提供可单独调用的只读核验能力；此Story不产生完整记录合规、规划采纳、Task准入或提交成功结论。六类完整结构校验在1.4使用该codec；journal与InputSet resolver按已定Epic另行实现。

**Acceptance Criteria:**

**AC-1**

**Given** 被检查内容为JSON及有类型仓库引用，
**When** 调用公共解码和引用检查，
**Then** 重复键、非有限数、错误基础类型、未知schema标识、错误实体ID／修订类型被拒绝；不把bool当整数或字符串当已有Task ID类型，
**And** 引用包含POSIX仓库相对路径、明确schema／实体／修订及带算法标签digest；不默认补齐丢失的身份。

**AC-2**

**Given** 引用含绝对路径、仓库根逃逸、根外符号链接或未知实体，
**When** 解析路径和目标身份，
**Then** 按共享路径规则拒绝或报告无法证明，定位原引用和预期／实际值，
**And** 外部来源走既有source登记与冻结路径，不能把任意URL当本地文件；合法仓库内引用不被额外禁止。

**AC-3**

**Given** 两个JSON对象只改变键序或排版，另一些改变数组序、类型、值或字符串内容，
**When** 按沿用canonical_sha语义的带版本codec计算身份，
**Then** 仅对象键序／排版变化保持规范化digest；数组序、类型、Unicode原值和字符串空白变化保留语义差异，
**And** raw文件digest独立保存，冻结proof继续按原字节／原版本验证，不以新canonical结果改写历史proof。

**AC-4**

**Given** 任一核验成功、失败或适用项未知，
**When** 向调用者返回结果，
**Then** 使用唯一公共诊断形状reason_code／stage／entity_id／expected／actual／resume_ref，所有调用者引用同一枚举／类型，
**And** 不适用字段显式null，无法证明的内容不按null或空串获得授权；错误不只写页面文案。

**AC-5**

**Given** 现有Windows／Python工具链可运行读取及身份核验，
**When** 验证公共模块和只读核验入口，
**Then** 测试可区分损坏／未知格式与真实内容差异，并验证UTF-8、Windows路径及合法根内引用，
**And** 模块不引用Godot运行、模型调用或数据库，不写入正式规划／Task／发布指针；代码／测试／打印英文，文档中文。

### Story 1.4: 按唯一公共schema校验六类规划记录

As a 迁移审阅者,
I want 在提交或消费前核对策略、计划、绑定、origins、receipt和catalog的版本化结构及引用一致性,
So that 可以发现候选格式漂移与错误身份，而不等待所有生产者逐一落地。

Refs: FR-14；FR-17（格式部分）；NFR-E-2；NFR-E-8；NFR-E-11；AR-3；AR-4；AR-19；AR-20；AR-22（零Task形状）；AC-BR-04（planned形状部分）；AC-BR-19。

**前置：** Story 1.3。

**范围：** 实现既定六类schema及候选bundle只读结构／引用校验，不实例化所有未来业务对象，不生成真实计划／绑定／receipt或正式发布。结构合规与已提交、语义采纳、Task readiness、运行通过分开。

**Acceptance Criteria:**

**AC-1**

**Given** planning-records已规定六类记录形状和标识，
**When** 注册公共schema并调用1.3 codec校验单记录或候选bundle，
**Then** policy／plan／binding／origins／commit／catalog分别仅有一个schema定义，字段类型、枚举、必需项及扩展规则一致，
**And** 同v1不能加入不同消费者私有语义；未知版本／非法类型／缺必需项／无法解析引用各有明确失败，不静默降级。

**AC-2**

**Given** plan与binding修订、Flow共享引用和Task映射以候选bundle提供，
**When** 核验身份与结构关系，
**Then** plan_id为非空持久身份，plan与binding使用各自正整数修订及无前导零路径；binding分别引用精确plan修订，
**And** 重复／冲突Flow或共享定义owner、错误join类型、引用实体或修订不一致可定位；合法跨plan引用和多Flow共享不重复分配owner。

**AC-3**

**Given** 候选计划处于3B或仓库初次bootstrap无Task，
**When** 执行该阶段结构校验，
**Then** 无Task映射的3B计划、空origins／空冻结A集合在满足其他合同前提下是合法形状，不要求假Task或Chapter5 witness，
**And** Flow／非Flow去向及理由有对应结构；4／5 planned对象可不存在但责任／后续检查明确，stage不表示Task状态。

**AC-4**

**Given** 候选commit与catalog按公共形状互引，
**When** 核验digest引用和正式记录职责，
**Then** receipt目标digest排除自身及最终catalog输出，catalog引用receipt及其digest，二者无自引用hash循环，
**And** Task状态和runtime通过不写入新catalog／origins权威；未发布bundle只能得到候选结构结果，不能得到正式采纳或消费通过。

**AC-5**

**Given** 原始规划输入含损坏、未知schema、plan／binding修订混用或未解析的必需引用，
**When** 验证合法与反例样本，
**Then** 各反例被唯一校验器拒绝且所有调用方得到同类诊断，合法循环描述／非Flow结构／planned引用不被无环或已实现假设误拒，
**And** 本Story验证结构及已给定引用关系，不声称证明业务语义、任意循环终止、实际代码类型绑定或journal发布；这些仍由所属阶段验证。

### Story 1.5: 形成可审阅的成熟成果保护基准与冻结A输入

As a 仓库维护者,
I want 将现有任务、累计义务和A适用边界形成可追溯的保护输入,
So that 迁移能识别新增责任与存量成果，后续策略bootstrap不靠丢失trace猜测legacy。

Refs: FR-14；FR-17（基线输入部分）；NFR-E-2；NFR-E-3；NFR-E-7；NFR-E-8；AR-5；AR-17；AR-18；AR-21（保护投影定义部分）；AR-22；AC-BR-14；AC-BR-15；AC-BR-19。

**前置：** Story 1.1、Story 1.2、Story 1.3、Story 1.4。

**范围：** 生成并审阅最小存量保护／冻结A材料，原始采集证据放logs，正式最小定义及引用按仓库文档／来源治理版本化。该材料是Epic2策略bootstrap输入，不绕过其journal／receipt／catalog正式发布，也不提前授予各Task运行资格。

**Acceptance Criteria:**

**AC-1**

**Given** 1.1报告及其原文件身份仍可验证，
**When** 读取当前三联并生成保护基准，
**Then** 固定tasks.json.master.tasks[].id与两个业务视图taskmaster_id的严格join，保存成熟ID、当前状态／subtask状态、定义及历史／成果引用定位，
**And** 定义投影初版仅排除Task／subtask.status；Acceptance、依赖、来源、责任、semantic_review_tier及其他字段不被泛化成可变忽略项，原始bytes／digest另保。

**AC-2**

**Given** 当前累计manifest含旧Flow／test和有效回归／人工义务，
**When** 形成累计保护清单，
**Then** 保留稳定身份、适用映射及原始基线引用，明确新增义务不会由旧done自动满足，
**And** 退役、删Flow／test或减义务必须有来源支持和显式差异／审阅；不能以当前不可运行、planned重分类或测试失败作为消失依据。

**AC-3**

**Given** 存量A候选集合和来源范围有可审阅依据，
**When** 确定供策略使用的冻结A输入，
**Then** 逐项绑定Task ID、定义／来源scope、允许旧操作及审阅来源；无Task仓库可合法为空，
**And** 可选trace缺失不是A资格；已有B义务／相关定义变化须按B承接，来源不明或当前反向索引无法证明时保留阻断，不凭标签或done授权。

**AC-4**

**Given** 采集后Task状态合法推进、定义变更或文件被后编辑，
**When** 复核基准或生成本次审阅材料，
**Then** 保留当前权威状态／历史并显式显示基准差异；定义变化按投影识别，status变化不冒充语义变化，
**And** 保存本次使用的当前raw身份；已发生漂移的旧保护材料不能直接授权后续写入或覆盖新进度。

**AC-5**

**Given** 用户审阅保护和冻结A材料，
**When** 保存最小版本化依据，
**Then** 材料明确版本／来源、审阅结果、未解决项及Epic2 bootstrap接收条件，
**And** 未审阅材料不称正式冻结策略；不写新Task、origins／catalog，不切默认B、不删除旧兼容或历史成果。

### Story 1.6: 通过只读预检审阅迁移差异与阻断原因

As a 迁移操作者,
I want 用现有CLI体系预览候选迁移对定义、任务和累计义务的影响,
So that 在正式应用前看清真实缺口、需审阅变化和阻断位置，保护当前工作区。

Refs: FR-14；FR-17（预检与交接部分）；NFR-E-2；NFR-E-3；NFR-E-7；NFR-E-8；NFR-E-11；AR-3；AR-5；AR-17；AR-19；AR-20；AR-26；AR-28（预检部分）；AC-BR-14；AC-BR-15；AC-BR-16（预检入口部分）；AC-BR-19。

**前置：** Story 1.1、Story 1.2、Story 1.3、Story 1.4、Story 1.5。

**范围：** 在当前公共CLI／owning脚本提供只读预检及文档示例，参数命名由入口维护者细化；候选可来自明确审阅输入／fixtures，不依赖未来模型规划或三联写入。没有apply、恢复写入、模型调用、Task创建或发布副作用。

**Acceptance Criteria:**

**AC-1**

**Given** 当前有效盘点、保护基准和明确的候选变更均可读取，
**When** 从公共CLI运行迁移预检，
**Then** 按唯一schema／codec输出来源及对象差异、reuse／update／new／retire意图、当前Task与累计义务影响、需审阅项和阻断实体，
**And** 每项有原定位／内容身份／原因；不为凑四部分或固定Task数创建对象，不以缺少未来Task／场景误拒合法前置定义。

**AC-2**

**Given** 候选尝试用默认值覆盖成熟ID／状态、断开三联、删除B归属或无依据减累计义务，
**When** 运行预检，
**Then** 针对对应变化给出阻断诊断与受影响实体，旧done不被推导为新增义务通过，
**And** 合法更新／拆合／退役需完整来源和差异审阅才能继续；只有机器可核对的部分给确定结论，仍需语义审阅的内容不自报已批准。

**AC-3**

**Given** 治理记录未启用、已启用后缺失／损坏、格式未知或存在旧pending／未知scope，
**When** 执行只读状态检查，
**Then** 区分明确未启用、合法缺失和未知／损坏／待恢复；已启用后的策略／catalog／origins缺失不能推断legacy，
**And** 旧capability-apply.pending.json保留并定位原恢复入口，无法确定scope时保守阻断适用迁移；不删marker换绿，不假定后续journal已实现或调用其写者。

**AC-4**

**Given** 输入在运行中漂移、目标被编辑或操作者重复同一预检，
**When** 比较原始输入与本次观察身份，
**Then** 漂移使本次审阅结论失效并给重采位置；相同内容生成可比较差异，不自动再生成候选或付模型费用，
**And** 运行前后Task三联、原始来源、规划正式文件、manifest及发布指针保持不变；唯一输出是logs报告及明确请求的只读结果。

**AC-5**

**Given** 维护者在目标Windows环境运行已记录的Python工具链，
**When** 按owning文档示例执行成功及关键失败样本，
**Then** 合法预检、缺输入、未知版本、路径逃逸、状态覆盖、无依据退役、旧pending及零Task样本均有可复查结果，错误使用1.3公共形状并返回与现有CLI约定一致的失败状态，
**And** 预检说明、CLI help、Skill／AGENTS路由按当前实际能力一致，报告列未实现／未启用环节；代码／测试／打印英文，UTF-8文档中文。

**AC-6**

**Given** Story1.1–1.5及本Story前五组预检验收均已通过，
**When** 整理交给Epic2的输入，
**Then** 交接包含当前基线／消费者矩阵、审阅后的治理规则、唯一codec与六schema、保护与冻结A输入、只读预检报告及未决项，
**And** 只报告Epic1预检与保护能力完成；无journal正式采纳、Task实施门禁、游戏运行或默认B切换声明，不要求未来Epic先完成才算该预检可用。

## Epic 2: 无实施Task也能正式规划、审阅和采纳

规划者先把完整来源转换为Requirement、Capability／Flow或合法非Flow去向，在没有变更Task／readiness时正式采纳并安全恢复同一计划。主覆盖FR-1／2／3／4／5／16，共同承接FR-7／13／14／17；最终Task实施与运行证据仍按后续Epic承担。

主要约束为NFR-E-2／3／4／5／6／8／9／10／11及AR-2／3／4／8／9／12／15／17／22／23／24／26／27／28的对应阶段部分；无独立UX合同，不新增视觉设计。沿用ADR-0039及两份完整命名的ADR-0038各自边界，不重建当前已成熟的worker／checkpoint／admission／预算机制。

### Story 2.1: 在Task之前形成累计来源Ledger与需求验收意图

As a 需求规划者,
I want 注册完整累计来源并逐块记录Requirement投影、验收意图或明确去向,
So that 尚未拆Task的需求也能完整核对，不会因没有Flow引用而消失。

Refs: FR-1；FR-3（无Task输入部分）；FR-16；NFR-E-2；NFR-E-5；NFR-E-8；NFR-E-10；AR-1；AR-2；AR-15；AR-27；AC-BR-01（前置记账部分）；AC-BR-02；AC-BR-20。

**前置：** Story 1.1、Story 1.2、Story 1.3、Story 1.4、Story 1.5、Story 1.6。

**范围：** 复用来源注册／解析／无损传输，生成Task无关Ledger和Requirement／验收意图提议及记账报告；不生成正式Task或采纳计划。新提议身份与正式持久身份区分，旧身份保持回链，正式分配由采纳操作负责。

**Acceptance Criteria:**

**AC-1**

**Given** 累计来源已注册且目标变更尚无实施Task或readiness，
**When** 执行来源记账，
**Then** 从既有版本化chapter3-source-set及本次明确新增／退役声明构造完整累计输入，保存每个来源与块的定位、原文身份、Requirement／验收意图及投影或去向，
**And** 不要求假Task、全局Chapter5 witness或现有场景；历史Task只能作可选复用上下文。

**AC-2**

**Given** 来源含跨Flow共享约束、其他验证、有依据延期或范围外需求，
**When** 核对来源块和Requirement去向，
**Then** 每块有语义投影或明确且有来源理由的累计去向，尚未进入当前Flow／Task的内容保留，
**And** 未知、歧义和来源缺口明确列出；accounted不等于satisfied，Task／Capability／节点数不当覆盖证明。

**AC-3**

**Given** 大来源必须分块读取或现有解析器输出长对象，
**When** 构建并检查Ledger，
**Then** 保完整原文、顺序、块／文件hash及跨批引用、全局守恒证明，复用现有完整对象读取与传输校验，
**And** 缺页、截断、重复／遗漏块或无法重建引用阻断；不以摘要或可运行状态缩减声明来源。

**AC-4**

**Given** 登记来源被修改、损坏、不可读或声明退役缺依据，
**When** 复验来源身份和累计清单，
**Then** 定位受影响来源／块并报告需要补齐或重审的范围，
**And** 未经授权不能隐式移除来源；正式新规划未通过前不覆盖已有采纳、Task、累计manifest或原proof。

**AC-5**

**Given** 一次记账结束、失败或重复执行，
**When** 记录阶段事件，
**Then** 保run／scope／stage／attempt、实测活动耗时、实际模型dispatch数量或明确零调用、复用理由及终止原因，
**And** 未知值显式unknown，同event不重复计数，预算预留不当账单；不设速度或成本下降门槛。

### Story 2.2: 从完整来源独立审计遗漏与冲突

As a 需求审阅者,
I want 在拆任务前独立核对来源与Ledger中的遗漏、矛盾和交接,
So that 首轮投影漏掉的需求不会被后续规划范围掩盖。

Refs: FR-2；FR-16；NFR-E-3；NFR-E-5；NFR-E-8；AR-2；AR-15；AC-BR-02；AC-BR-09；AC-BR-20。

**前置：** Story 2.1。

**范围：** 适配现有独立审计流程至3A，在完整来源和Ledger范围提供可复验报告及来源审计复用判断；不替代后续Chapter5 Task／Acceptance／契约审阅。

**Acceptance Criteria:**

**AC-1**

**Given** 首轮Requirement或Flow投影故意漏掉一个未被Task引用的交接，
**When** 独立审计按完整登记来源和Ledger读取输入，
**Then** 报告仍发现并定位该原文交接，列出遗漏或冲突及受影响投影，
**And** 审计范围不由首轮引用集合反裁，不因没有Task／readiness或未选Flow跳过来源块。

**AC-2**

**Given** 独立审计发现矛盾、未知或欠定义，
**When** 完成审计并汇总准入结果，
**Then** 每条finding有原文／块定位、当前输入身份、严重性或已有治理分类及需返回的责任，
**And** 未解决的阻断项不能因已记账或模型自报接受而取得规划完成；延期／范围外决定需有效来源依据和显式审阅。

**AC-3**

**Given** 本次希望复用已完成且持久化的来源审计，
**When** 比较审计输入和规则身份，
**Then** 适用来源／Ledger、解析器和审计规则及影响结果的工具身份均匹配才复用，
**And** 相关变化只使受影响审计失效，无关HEAD或其他Task status变化不强迫重做；不通过刷新旧readiness时间戳代替审计。

**AC-4**

**Given** 审计proof损坏、引用原文不可解析或容量不足，
**When** 运行确定性校验和审阅，
**Then** 按公共诊断阻断，分清执行故障、语义问题及容量／预算终止，保留失败和恢复原因，
**And** 不静默裁剪、不自动放宽准入、不把缺失proof当作可复用；记录真实dispatch／耗时／复用事件。

**AC-5**

**Given** 来源审计有效并可回链，
**When** 交给后续语义规划和Chapter5，
**Then** 后续可定位报告与冻结输入并验证其新鲜度，3B不再为了拿审计结果先建Task，
**And** Chapter5仍需核对真实Task Acceptance、ADR／Overlay／契约／绑定，不以3A报告免掉实施审阅。

### Story 2.3: 准备Task无关且完整的规划输入

As a 玩法规划者,
I want 在没有Task／readiness时为Capability和MVG语义规划准备完整且有界的输入,
So that 正式前置规划使用可验证原文和相关闭包，不依赖后置Task门禁。

Refs: FR-3；FR-7（3B定义层部分）；FR-16；NFR-E-3；NFR-E-5；AR-2；AR-10（阶段输入部分）；AR-15；AR-27；AC-BR-01；AC-BR-09；AC-BR-19。

**前置：** Story 2.1、Story 2.2。

**范围：** 适配现有plan_capabilities／plan_mvg的prepare及相关输入投影，使用明确阶段合同；不靠allow_unready／draft跳过正式门禁，也不修改已有后置Task实施就绪合同。

**Acceptance Criteria:**

**AC-1**

**Given** 3A记账与独立审计有效，目标范围无Task／readiness，
**When** 选择正式3B阶段prepare，
**Then** 可生成有明确stage、来源／审计身份、规则／codec及适用上下文的冻结输入，
**And** 阶段合同不要求Task sinks、全局Chapter5 witness、实际代码符号或Godot节点，缺省不是绕过开关。

**AC-2**

**Given** 输入包含已有实现／共享能力及Task或没有这些对象，
**When** 构造供模型与确定性检查使用的上下文，
**Then** 已有对象用于复用判断且保身份，缺少Task不被当输入损坏；3B阶段声明的必需来源／审计／约束不可缺，
**And** 只在合法阶段合同内区分不适用项，不能把未知或损坏条目静默剔除；不把3B输入身份冒充最终实施InputSet。

**AC-3**

**Given** 源集合很大但只规划选定Capability或Flow，
**When** 按受治理闭包分批及分阶段synthesis，
**Then** 每次获得其适用完整原文／对象和全局记账／守恒proof，保跨批义务、完整前序草案及实际返回大小预检，
**And** 不能用先前临时摘要／任意搜索替代原输入，实际容量不足停止并给恢复位置。

**AC-4**

**Given** 相同输入重复prepare或相关规则／来源改变，
**When** 比较冻结输入身份，
**Then** 未变的已完成准备材料按原规则复用，相关变更生成新身份和明确失效范围，
**And** raw proof／历史batch身份继续按原版本核验，无关提交不独自触发全仓重做。

**AC-5**

**Given** 沿用当前Capability显式--resume-evidence或旧后置准备路径，
**When** 执行对应阶段的输入验证，
**Then** 原路径仍按其完整输入／receipt及真实模型身份合同运行，3B有自身明确正式语义，
**And** 不把MVG未完成中间态或旧Task-readiness缓存带入新的无Task准入，不创建第二套自由读取管线。

### Story 2.4: 描述可审阅的Flow及合法非Flow验证去向

As a 玩法规划者,
I want 在Task之前明确逻辑Flow、四部分职责、状态所有者及合法其他验证去向,
So that 后续任务从真实实施缺口承接同一行为链和责任。

Refs: FR-3；FR-4；FR-7（逻辑层）；NFR-E-2；NFR-E-6；AR-2；AR-4；AR-12；AR-22（非Flow去向部分）；AC-BR-03；AC-BR-04；AC-BR-05；AC-BR-21（采纳去向部分）。

**前置：** Story 2.3。

**范围：** 在现有planner的Task无关路径生成／读取逻辑候选并进行确定性结构检查；候选尚未正式采纳，独立语义admission及评选由2.5完成。

**Acceptance Criteria:**

**AC-1**

**Given** 有效准备输入含一个目标玩法链路，
**When** 生成或读取3B候选，
**Then** Flow包含来源／Requirement、逻辑身份、起点／进入条件、成功终点、必要失败／取消／返回、交接、状态所有者、可观察结果与验证目标，
**And** 领域规则、C#适配、绑定、原生场景的适用逻辑责任完整；不要求对象已创建，也不机械四拆或一节点一Task。

**AC-2**

**Given** Flow有重试、重入、合法循环或共享状态交接，
**When** 运行确定性图与责任检查，
**Then** 检查引用、边界唯一性、必要可达性、循环分量及声明退出条件，指出可判定范围，
**And** 合法循环不因无环图假设失败，不声称证明任意程序必终止；没有责任或退出解释不能以假节点／假接口过检。

**AC-3**

**Given** 一个Requirement进入多个Flow且Flow跨Capability，或共享命令／状态被多个计划引用，
**When** 核对候选关系，
**Then** 沿既有requirement_route_memberships、requirement_verification和requirement_evidence键，分离唯一权威验证处置、多个可观察路线角色及去重共享证据，
**And** 同Flow／共享定义有唯一owner，coverage_table保持兼容投影；不复制规则正文或按路线数重复计完成。

**AC-4**

**Given** 需求不适合Flow或有依据延期／来源缺口，
**When** 表达其累计去向，
**Then** 提供来源理由、适用性及其他验证义务或明确未解决项，不强造Flow，
**And** 标签／空字段不是N/A授权；合法非Flow采纳不自动授予Task实施豁免，真实MVG影响仍须后续绑定回归。

**AC-5**

**Given** 候选含planned对象、实现引用、UI或人工验证责任，
**When** 输出候选及检查结果，
**Then** 区分计划定义与实现／运行证明，提前保UI输入、反馈、场景入口／返回及适用人工义务，
**And** 真实对象出现后仍须类型、编译、绑定及引擎检查；候选结构通过不叫采纳、readiness或Flow完成。

### Story 2.5: 通过独立准入与有界评选选出可采纳候选

As a 规划审阅者,
I want 沿现有隔离候选生命周期先检查完整性和独立语义，再比较合格候选,
So that 硬问题候选不能进入采纳，失败不会无限重试或重置预算。

Refs: FR-4；FR-16；NFR-E-5；NFR-E-10；AR-9；AR-12；AR-15；AR-27；AC-BR-03；AC-BR-09；AC-BR-20。

**前置：** Story 2.3、Story 2.4。

**范围：** 适配已有Capability／MVG runner的阶段与输入，不重写其worker、admission、selected／checkpoint状态机。使用实际模型和receipt，遵守当前ADR-0038-mvg-candidate-admission及ADR-0039；默认预算不增加。

**Acceptance Criteria:**

**AC-1**

**Given** 候选来自2.3冻结输入，3B不依赖Task readiness，
**When** 执行确定性完整性／累计delta检查及独立语义admission，
**Then** 每个可参选候选都有绑定proposal、原输入、独立proof和真实执行receipt的合格证据，
**And** 先准入后比较，语义审阅覆盖分支条件、交接、四部分及来源；机器结构通过不能替代独立业务审阅。

**AC-2**

**Given** 现有MVG逐Capability路径需要三个合格候选及只读accepted seed，
**When** 运行候选、替换和评选，
**Then** 保独立OS子进程／工作区，worker只产候选，协调器预留预算、独立机器复验、评选并唯一提交selected／checkpoint，
**And** 没有三个合格候选不进入该路径的比较；不把旧incumbent当额外候选，不用worker自报成功推进正式状态。

**AC-3**

**Given** 存在稳定语义硬问题、调用失败或替换／调用止损，
**When** 执行修复及停止策略，
**Then** 原有稳定issue修复、稳定槽位64次及run默认192次上限、三轮替换等有效预算按当前ADR继承；子进程／lineage变更不重置预算，
**And** 执行故障／schema／身份问题与语义finding分开，预算耗尽不伪造issue耗尽；替换从冻结输入fresh lineage生成，不喂回退役候选／修复内容。

**AC-4**

**Given** 一个候选已评选但其hash、proof、模型身份或准备输入不一致，
**When** 最终复验所选候选，
**Then** 拒绝并保错误定位与原证据，不能用最后审阅静默换winner或回退到不合格候选，
**And** 相同失败不无进展重跑；保真实耗时／dispatch／复用／替换及终止事件，unknown不冒充成本。

**AC-5**

**Given** Task无关候选取得有效选择结果，
**When** 交给采纳操作准备，
**Then** 可定位所选内容、固定来源／审计、独立准入、相关规则和可比较差异，
**And** selected完成项只是既有规划执行的提交结果，尚不等于新B正式catalog采纳或任何Task／Flow运行通过。

### Story 2.6: 冻结采纳操作并持久分配稳定身份

As a 规划采纳者,
I want 把已审阅候选和身份对齐冻结为可恢复且不可偷换的采纳请求,
So that 重复提交不会重分配身份或改变已审阅内容。

Refs: FR-5；FR-13（规划／操作身份部分）；FR-14；NFR-E-3；NFR-E-4；NFR-E-8；AR-3；AR-4；AR-8；AR-17；AR-23；AC-BR-04；AC-BR-06；AC-BR-07。

**前置：** Story 2.5、Story 1.5、Story 1.6。

**范围：** 实现公共提交服务prepare／reserve部分，提供已冻结请求和可审阅操作状态；不写正式plan／policy／catalog目标，不把prepared当发布。复用既有共享操作锁／journal，不另设独立写锁体系。

**Acceptance Criteria:**

**AC-1**

**Given** 候选、审计、保护基准和采纳审阅有效，
**When** 生成采纳请求及差异预览，
**Then** 持久绑定operation ID与规范化请求内容、适用scope、来源authority、完整目标before／after身份及payload和proof引用，
**And** 现有Requirement／Flow／Task身份复用，新规划身份在本操作中分配、查重并持久保存；新plan与binding各自修订，不能从模型标题分配Task ID。

**AC-2**

**Given** 同操作请求重复prepare／reserve或同ID换了内容，
**When** 读取既有操作并核对身份，
**Then** 同ID同内容复用原分配与冻结结果；同ID异内容拒绝，不能悄然重分配或覆盖旧journal，
**And** 显式重规划生成可审阅差异、lineage和身份对齐，旧不可变修订及审计保留。

**AC-3**

**Given** 并行操作可能触及相同scope、共享Task或新身份，
**When** 在现有共享锁体系保留操作及scope，
**Then** 先短时项目metadata锁再按稳定scope顺序取得完整适用租约，校验已提交及pending分配避免碰撞，持久pending／journal在任何正式目标写前完整保存，
**And** 无可取得互斥条件、未知pending scope或Windows占用则停止；模型／长任务不持全局metadata锁，不创建假Task确定scope。

**AC-4**

**Given** 来源／目标被后编辑或冻结结果不满足累计防削弱／review，
**When** 完成reserve前和后续使用边界复验，
**Then** 不接受漂移、损坏、未知payload或缺审阅的操作；原proof、后编辑与失败记录保留，
**And** prepare／reserved只表示请求已冻结；只有后续服务可正式apply／publish，当前功能可独立输出可复查冻结请求。

**AC-5**

**Given** 操作者查看已冻结操作及待办，
**When** 输出公共诊断和恢复位置，
**Then** 说明操作ID／scope、准备／保留状态、expected／actual及resume_ref，引用唯一codec和六schema，
**And** 不把pending存在或创建journal当提交成功，不创建Task／规划数据库／新MVG状态；本Story不依赖未来恢复功能才能验证冻结请求。

### Story 2.7: 一致提交采纳目标并以catalog发布

As a 规划采纳者,
I want 通过公共提交服务应用已冻结请求，在全部目标验证后一次发布相关scope,
So that 正式消费者不会读到一半新一半旧的规划。

Refs: FR-5；FR-13（应用幂等部分）；FR-16；NFR-E-2；NFR-E-4；NFR-E-8；NFR-E-11；AR-3；AR-8；AR-17；AR-22（bootstrap部分）；AR-23；AC-BR-06；AC-BR-07；AC-BR-19。

**前置：** Story 2.6。

**范围：** 在现有journal上实现公共apply／verify／publish及正式读取核验，用于B采纳与策略bootstrap；三联／4–5绑定写入后续只接适配，不重造服务。自动recover由2.8扩展，本Story对中断必须已安全阻断。

**Acceptance Criteria:**

**AC-1**

**Given** 2.6持久请求、authority和全部before／after仍有效，
**When** 应用目标，
**Then** 逐目标写前重验，只接受本操作before或after，after跳过；任一未知编辑／占用／来源漂移冲突即停止，
**And** 不对Task或其他权威任意强制覆盖，不增加无用兼容写层；冻结请求未授权的文件不写。

**AC-2**

**Given** 已写目标均可重读验证，
**When** 执行verify并保存最小commit receipt，
**Then** 核对所有目标、适用引用、阶段输入、authority及累计义务，receipt不可变并纳入最小版本化记录，
**And** receipt不hash自身或最终catalog输出；完整payload、journal和过程证据留logs，审计事件不是提交点。

**AC-3**

**Given** 所有目标和receipt验证成功，
**When** 发布单一catalog，
**Then** 最后原子替换catalog，一次推进本操作全部scope并保留无关scope；journal先保存最终catalog完整after payload／digest，
**And** plan与binding修订独立，正式policy／origins引用一致；不得以单文件replace、写receipt或pending消失宣称整体完成。

**AC-4**

**Given** bootstrap仓库无Task或3B计划尚无Task映射，
**When** 提交策略／origins／采纳计划，
**Then** 允许合法空Task origins／冻结A集合，正式语义采纳不需要Taskmaster非空或Chapter5 witness，
**And** 不创建假Task／假readiness／实际场景对象，不在catalog写Task状态或runtime PASS；记录原本缺失与已启用后缺失的差别。

**AC-5**

**Given** 消费者读取已发布或中断状态，或没有本地logs的clone，
**When** 在适用保护下读取catalog及receipt／相关目标，随后重读catalog，
**Then** 只有正式链、相关实际文件和前后catalog身份一致且无待消歧相关pending时返回有效采纳；发布前崩溃或损坏状态明确阻断，
**And** 无关scope发布不单独改变当前语义，但相关依赖或适用集合变更会失效；不将catalog整体hash当所有Task的新鲜度键。

**AC-6**

**Given** 同请求已完整发布，或写入／发布过程中发生各崩溃点，
**When** 重试正式提交或读取，
**Then** 完整同内容提交为no-op且不重写已完成副作用；部分写入／已写未发布／发布后pending未清保留可恢复阻断，
**And** Windows目标上的占用／中断／重启及发布前后故障有证据；未验证的耐久性不能称数据库隔离或授权默认B切换。

### Story 2.8: 按journal恢复中断并保留后编辑

As a 规划操作者,
I want 识别采纳操作的实际落地状态并安全恢复或补偿,
So that 中断不会造成重复副作用、丢失人工修改或误报成功。

Refs: FR-5；FR-13；FR-14；FR-16；NFR-E-4；NFR-E-8；NFR-E-11；AR-8；AR-17；AR-23；AR-24（旧pending与恢复部分）；AC-BR-06；AC-BR-07；AC-BR-09；AC-BR-19。

**前置：** Story 2.7。

**范围：** 扩展同一公共提交服务recover／补偿入口，沿旧journal及pending原合同恢复；这不是恢复模型候选中间态。后续Task写入适配也必须使用同一协议。

**Acceptance Criteria:**

**AC-1**

**Given** 本地pending／journal可能处于未写、部分写、已写未发布或已发布未清理，
**When** 恢复核对操作内容、全部authority、目标bytes、receipt和catalog，
**Then** 按真实状态只推进合法缺失步骤或确认已发布no-op，已after目标不重施加，
**And** 不凭journal存在、pending消失或Agent摘要推断完成，不重新付模型费用以重建已有应用状态。

**AC-2**

**Given** 同ID异内容、未知后编辑、损坏journal／receipt或来源规则变化，
**When** 尝试恢复，
**Then** 停止并保原始证据，给出冲突／过期实体、expected／actual及需返回阶段，
**And** 不盲重放、不覆盖、不得擦除原journal／receipt换重试；相关失效与无关变化分开。

**AC-3**

**Given** 旧capability-apply.pending.json及其原journal仍存在，
**When** 新服务检查恢复资格，
**Then** 识别并路由到原apply恢复合同，相关pending消歧前阻断；未知scope保守阻断适用操作，
**And** 不只检查新B marker，不自动删旧marker，不把有效catalog作为pending豁免。

**AC-4**

**Given** 当前权威已被后续合法操作改变且需要回退原副作用，
**When** 按治理准备补偿，
**Then** 生成新的受审阅operation，使用当前前像核对原副作用、相关scope与当前身份，
**And** 保留后编辑、历史、当前Task完成状态及B来源，不直接还原旧before或借旧格式降回A。

**AC-5**

**Given** Windows占用、进程退出、重启、发布后清理失败或跨scope竞争在测试中注入，
**When** 运行恢复及公共读取入口，
**Then** 各故障均产生一致的可核对结果：恢复到完整提交或明确阻断，无混合状态被消费，
**And** 不相关scope可继续，长恢复不持全局锁等待；证据留logs，未覆盖的环境边界明确列出。

### Story 2.9: 复用已提交完成规划并遵守epoch与reopen撤销

As a 规划操作者,
I want 把当前仍有效的已完成规划成果用于新执行，同时保留原proof和预算历史,
So that 下游失败或无关提交不会迫使重做有效上游，也不会复活已撤销结果。

Refs: FR-5；FR-13（规划成果复用部分）；FR-16；NFR-E-3；NFR-E-4；NFR-E-5；AR-9；AR-10；AR-15；AR-24；AR-27；AC-BR-06；AC-BR-09；AC-BR-20。

**前置：** Story 2.3、Story 2.5、Story 2.7、Story 2.8。

**范围：** 适配现有ADR-0039完成项registry／checkpoint／adoption及B阶段输入关系，保原恢复键和实际预算；不新建恢复状态机，不把正式文件journal和候选模型恢复混为一体。

**Acceptance Criteria:**

**AC-1**

**Given** 历史单Capability完成项由原run.json提交，单项完整规范化内容与当前目标匹配，
**When** 尝试新执行adoption，
**Then** 以完整单项对象规范化内容hash匹配，验证原冻结proof，再检当前相关依赖和累计delta，写独立adoption receipt，
**And** Git／catalog元信息不是匹配键，不用相似度；内容命中不跳proof或当前兼容性，不伪造本run新的语义admission。

**AC-2**

**Given** 仅有prepared bundle、候选／修复／检查／评选中间态或不完整提交，
**When** 开始新的MVG执行，
**Then** 不作为可跨新执行复用完成项；从有效冻结输入按既有流程重新产生缺失成果，
**And** 已付调用、失败／预算历史保留，稳定槽位与run预算不因新进程／lineage重置；下游失败不使未变有效上游自动重跑。

**AC-3**

**Given** 原proof损坏、依赖／delta不兼容或只发生无关提交，
**When** 核对恢复资格，
**Then** 损坏／相关变化拒绝并定位，真正无关HEAD、其他Task status或catalog条目变化不单独使内容匹配失败，
**And** 历史proof的原版本／raw身份不重写；运行证据有效性仍须后续相应完整身份检查，不能用规划adoption证明游戏运行。

**AC-4**

**Given** 执行本地clear／epoch推进或显式reopen，
**When** 重新读取恢复、显示、提交和发布资格，
**Then** 沿原操作锁核对持久epoch，reopen撤销受影响项及后继，不恢复已撤销资格，
**And** 保原审计，local clear不自动删除Git中的正式采纳／累计基线；source-backed语义变化按治理更新相关采纳和绑定。

**AC-5**

**Given** 操作者指定Capability --resume-evidence或恢复应用journal，
**When** 选择恢复入口，
**Then** 分别按其完整准备输入／历史batch／receipt合同或2.8文件应用合同处理，诊断明确适用恢复类型，
**And** 不把这些许可泛化为新MVG执行未完成候选复用；记录实际复用来源／理由、调用数、耗时及未知值。

### Story 2.10: 从正式规划入口完成零Task采纳与跨会话复验

As a 需求规划者,
I want 通过现有公共规划入口完成完整无Task正式采纳，并在新会话定位同一计划和阻塞原因,
So that 可以先规划再交给任务承接，而不是通过draft绕过获取形式通过。

Refs: FR-1；FR-2；FR-3；FR-4；FR-5；FR-7（3B逻辑层）；FR-13（规划与采纳部分）；FR-14；FR-16；FR-17（规划生产者与入口部分）；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-5；NFR-E-6；NFR-E-8；NFR-E-9；NFR-E-10；NFR-E-11；AR-2；AR-3；AR-4；AR-8；AR-9；AR-12；AR-15；AR-22；AR-23；AR-26；AR-28（规划入口部分）；AC-BR-01（正式采纳部分）；AC-BR-02；AC-BR-03；AC-BR-04（身份交接部分）；AC-BR-05（逻辑关系部分）；AC-BR-06；AC-BR-07；AC-BR-09；AC-BR-19；AC-BR-20；AC-BR-21（正式非Flow采纳部分）。

**前置：** Story 2.1、Story 2.2、Story 2.3、Story 2.4、Story 2.5、Story 2.6、Story 2.7、Story 2.8、Story 2.9。

**范围：** 把本Epic已有能力接入现有CLI／owning脚本，完成真实正式入口、持久读取／恢复及文档交接；不强制3A／3B／3C各建新公共命令，不调用未来Task编译器或页面功能。此Story验收自身入口适配，前置算法／服务不延期。

**Acceptance Criteria:**

**AC-1**

**Given** 新仓库或目标变更没有实施Task／readiness、实际实现符号或场景，但有效来源齐备，
**When** 从正式规划入口完成3A→3B→采纳，
**Then** 得到可由公共读取器验证的policy／origins／plan／receipt／catalog链、来源／独立审计和逻辑四部分／Flow或合法非Flow去向，
**And** 无假Task／witness／节点，不依靠allow_unready或draft开关；有实现／旧Task时只辅助复用判断，零Task与存量上下文均可用。

**AC-2**

**Given** 某来源块无去向、审计／admission硬问题未解决或全局完成核对失败，
**When** 尝试宣告planning complete，
**Then** 可显示已合法提交的规划前缀及明确阻断，但最终planning complete须完整全局机器审计和适用语义准入通过，
**And** accounted与satisfied分开，未来实施planned可保责任但不冒充运行；来源缺口不能因已记账而让正式规划完成。

**AC-3**

**Given** 同有效采纳在新会话重复读取／恢复，或显式重规划，
**When** 通过公共入口复验，
**Then** 同输入复用有效计划、身份和已提交成果，重复应用无额外副作用；新规划有审阅差异与身份对齐，
**And** 相关变化精确失效，损坏／未知／后编辑／pending明确拒绝；返回原始依据及公共resume_ref，不用Knowledge摘要替代。

**AC-4**

**Given** 合法循环、跨Capability Flow、多Flow共享Requirement及合法非Flow样本，
**When** 执行正式入口与对应失败样本，
**Then** 合法对象能按各自理由采纳，重复owner、缺交接／其他验证、来源缺口、截断及伪N/A不能通过，
**And** 规划采纳与Task readiness／运行完成保持区分；不提前生成新Task或manifest实施绑定，不把后续Taskowner逼出业务API。

**AC-5**

**Given** CLI、Skill、AGENTS及阶段文档描述本次已交付能力，
**When** 核对help／示例／路由和阶段事件，
**Then** 说明先正式规划再交Task承接、实际阻塞及恢复入口，记录真实阶段耗时／dispatch／复用／返工及终止原因，
**And** 原有A范围入口在明确边界内保持可定位，新增默认B切换仍待Epic5；Knowledge完整页面对齐由Epic4承接，不以未做页面阻挡本CLI路径。

**AC-6**

**Given** 目标Windows环境执行本入口及本Epic全部前置验收，
**When** 核对交给Epic3的采纳合同，
**Then** 验证采纳身份、逻辑四部分、审阅proof、不可变plan与独立binding修订合同、冻结A输入及公共提交／恢复服务可追溯，
**And** 只报告无Task规划／采纳能力；真实Task生成、4–7门禁、奖励Windows／Godot／C#运行及累计full-MVG未被本Epic代验，当前本轮也仅编写Story。

## Epic 3: 按已采纳定义承接任务并一致实施与恢复

实施者从真实缺口生成或复用完整三联，按当前有效定义进入Chapter4–7，在CLI、直接、恢复、route及页面实施触发得到一致决定。主覆盖FR-6／7／8／9／10；共同承接FR-3／4／11／13／14／16／17及FR-15实施触发边界。

主要约束是NFR-E-1／2／3／4／6／7／8／9／10／11及AR-2–10／12／13／17／21–24／26／28的适用部分。无独立UX合同，只消费已采纳UI职责；不新建视觉设计范围或测试框架。公共codec／提交服务沿用Epic1／2，真实选择性执行和完整Knowledge展示仍属Epic4。

### Story 3.1: 从复用盘点形成真实缺口的任务变更预览

As a 实施规划者,
I want 从已采纳Flow或合法非Flow去向盘点既有实现与真实任务缺口,
So that 生成的任务承接实际责任，避免重建已完成成果或重复拆分。

Refs: FR-6；FR-14；FR-17（任务规划部分）；NFR-E-2；NFR-E-7；NFR-E-9；AR-4；AR-7；AR-27；AC-BR-01（Task承接部分）；AC-BR-05；AC-BR-14；AC-BR-15。

**前置：** Story 2.10。

**范围：** 复用现有任务意图规范化与业务视图生成路径，产出可审阅delta／复用报告；仅提议真实缺口，不写tasks.json、不把Story编号当Task ID。

**Acceptance Criteria:**

**AC-1**

**Given** 正式采纳和当前来源／审计仍有效，存在Flow或合法非Flow实施责任，
**When** 盘点实现、成熟Task、共享能力、四部分及验证义务，
**Then** 逐项区分已有可复用成果、真实定义／实现／验证缺口及新增责任，保来源／Requirement／Acceptance回链，
**And** 旧done只证明旧范围，不满足新义务；缺口不由Task数、Flow节点数或固定工时推断。

**AC-2**

**Given** 一个Task可承接多个Flow，或多个Task共同完成一个Flow，
**When** 生成业务视图delta预览，
**Then** 保Task与Flow多对多及Requirement唯一验证处置、多个路线成员与共享证据关系，
**And** 不机械四拆、不一节点一Task、不为集成owner制造业务API。

**AC-3**

**Given** 已有成熟ID／状态／历史或提出update／reuse／split／merge／retire，
**When** 审阅变更计划，
**Then** 默认保现有身份／状态／历史及无关定义，更新和退役有明确范围、来源差异与理由，
**And** 候选默认值不能覆盖旧ID或状态，不将本次改坏的旧Flow／test移出累计基线。

**AC-4**

**Given** 新任务需要实施责任、依赖及局部验证，
**When** 输出业务视图提议，
**Then** 每个真实缺口可独立实施与局部验证，并引用当前plan修订、Requirement、Acceptance、适用四部分和验证去向，
**And** Task永久ID仍由现有任务分配／编译路径拥有；输出不是ready或运行通过。

**AC-5**

**Given** 输入漂移、映射不完整、来源不明或delta有语义硬问题，
**When** 完成预览检查，
**Then** 定位对应plan／Requirement／Task并阻断或返回owning stage，保可审阅证据及实际阶段事件，
**And** 不自由直写tasks.json，不为让提议通过弱化Acceptance或复制同义Task。

### Story 3.2: 受治理编译三联与3C绑定并保留当前任务状态

As a 任务维护者,
I want 将已审阅delta经现有三联编译路径一致提交，并同步B来源和计划映射,
So that 正式Task及其实施依据可追溯，重试或并发状态推进不丢历史。

Refs: FR-6；FR-7（3C部分）；FR-13（任务应用部分）；FR-14；FR-17；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-7；AR-3；AR-4；AR-7；AR-8；AR-21；AR-22；AR-23；AC-BR-04；AC-BR-05；AC-BR-06；AC-BR-07；AC-BR-14；AC-BR-15。

**前置：** Story 3.1、Story 2.6、Story 2.7、Story 2.8。

**范围：** 给既有normalize_task_intents／compile_task_triplet及受管写者接共享提交适配，发布3C binding／origins／反向索引，不重造任务状态机或journal；只校验3C必需项，不等待4–5对象或readiness，也不授予Chapter5 readiness。

**Acceptance Criteria:**

**AC-1**

**Given** 3.1提议和审阅均有效，
**When** 经既有业务视图编译三联，
**Then** 保持tasks.json.master.tasks[].id与back／gameplay的taskmaster_id严格join，真实新ID只由原分配路径产生，semantic_review_tier进入真实视图，
**And** Task定义／Acceptance／依赖／责任映射可回链；禁止Agent绕过编译直接改tasks.json取得正式结果。

**AC-2**

**Given** 任务已关联一个或多个B plan，或新增关联共享Task，
**When** 提交3C binding及origins，
**Then** 精确绑定plan修订、独立binding修订、全部Task适用plan集合与完整反向索引，同Flow身份不变，
**And** 所有映射同操作一致发布，覆盖当前和新增scope租约；不删旧B归属降回A，也不在origins／catalog复制Task状态。

**AC-3**

**Given** 审阅后的编译请求遇到当前Task／subtask status合法推进，
**When** 在共享锁内重读并派生提交，
**Then** 合并当前状态、保成熟ID／历史与无关定义，原始before／after bytes及verification_mode／codec／投影digest写入提交证明，
**And** 定义投影初版仅排除Task／subtask.status，Acceptance／依赖／来源等不排除；journal冻结后再有并发变化则冲突停止或重派生审阅，不吞掉新进度。

**AC-4**

**Given** 编译／binding在多产物中断后恢复或完整操作重复apply，
**When** 调用已有共享服务，
**Then** 未完成操作按全部原始前像／后像和authority严格恢复；完整同内容操作验证当前相关定义及资格后no-op，
**And** no-op不重写旧after恢复历史status，其他Task合法变化不使本Task定义全盘失效；同ID异内容／后编辑明确冲突。

**AC-5**

**Given** 三联、binding、origins、最小receipt及catalog不能全部验证，
**When** 发布或读取正式结果，
**Then** 相关scope不放行，未知／损坏／旧pending按公共合同阻断，完整验证后catalog最后发布，
**And** 无依据退役／累计义务削弱被拒绝；不以某个文件已写或pending消失证明3C完成。

**AC-6**

**Given** 三联编译和绑定提交成功，
**When** 更新对应入口说明并记录事件，
**Then** 当前Task仍按Taskmaster状态管理，实施门禁继续要求4–5；原有历史与累计manifest保留，
**And** 原始日志留logs，最小治理定义版本化，调用／耗时／复用／终止事件可追溯，不承诺提速。

### Story 3.3: 统一判定Task来源及完整适用计划集合

As a 实施入口维护者,
I want 在判断legacy或B之前验证策略、catalog、origins及反向引用,
So that B缺失标识不会误走无义务旧路线，共享Task不会漏掉其他计划责任。

Refs: FR-8；FR-9；FR-14；FR-17；NFR-E-2；NFR-E-3；NFR-E-11；AR-5；AR-6；AR-22；AR-24；AC-BR-08；AC-BR-15；AC-BR-19；AC-BR-21。

**前置：** Story 3.2。

**范围：** 公共resolver的来源分类与计划集合部分，可独立检查和诊断；不自行复制完整InputSet规则，不以分类结果直接授予实施权限。

**Acceptance Criteria:**

**AC-1**

**Given** 当前迁移政策已启用，
**When** 查询任一Task的来源分类，
**Then** 先验证policy／catalog／origins已提交身份和完整映射，再识别冻结范围内A、B或无法证明，
**And** 缺任一必需治理记录、未知格式、损坏／未发布／相关pending均阻断；不是先看trace为空就返回current。

**AC-2**

**Given** Task候选为A，
**When** 核对其冻结边界，
**Then** 须同时匹配冻结ID、定义／来源scope及允许旧操作，且完整反向索引证明没有当前B义务，
**And** 新增或相关定义变化走B；done、旧readiness或缺trace均不能单独授权A。

**AC-3**

**Given** Task被多个plan引用或刚加入新plan，
**When** 汇总当前适用集合，
**Then** Task origins与plan／binding反向引用集合完全一致，每项引用及修订可验证，
**And** 缺行／重复矛盾／删B归属／篡改策略不能落为无义务，新的适用集合改变该Task输入身份。

**AC-4**

**Given** 本地无pending的clone或存在旧capability-apply.pending.json，
**When** 验证提交链和当前相关文件，
**Then** clone仍验证版本化receipt／catalog与相关实际文件；旧pending按原journal消歧，未知scope保守阻断，
**And** 不能因logs缺失把未发布混合状态当合法，也不能删除marker获取分类通过。

**AC-5**

**Given** 操作仍处明确未启用的旧范围或需要查看分类结果，
**When** 通过只读调用输出决定，
**Then** 未启用仅沿显式原入口与旧边界，已启用分类按同一公共规则执行，报告reason_code／stage／entity／expected／actual／resume_ref，
**And** 合法非Flow仍只是可进一步核对的B去向，实际验证适用性由有效定义／影响确定，不由自由标签授权。

### Story 3.4: 在Chapter4细化生产契约与四部分实施定义

As a 功能实施规划者,
I want 把已采纳逻辑职责细化为足以实施和测试的命令、只读状态、适配与资源绑定,
So that Agent能依据明确边界实施，同时保留planned对象和原生场景制作空间。

Refs: FR-7；FR-10（实施定义部分）；FR-14；FR-17（Chapter4部分）；NFR-E-1；NFR-E-2；NFR-E-6；NFR-E-7；AR-2；AR-3；AR-6；AR-12；AR-13；AC-BR-03；AC-BR-04；AC-BR-12（绑定定义部分）。

**前置：** Story 3.2、Story 3.3。

**范围：** 沿既有Chapter4 Overlay／Contract治理与共享binding提交路径细化定义，不在本Story实现真实游戏功能，不为过检生成空接口或新公共DTO。

**Acceptance Criteria:**

**AC-1**

**Given** 3B逻辑定义和3C Task承接有效，
**When** 执行受影响范围Chapter4细化，
**Then** 明确生产命令、只读状态、唯一状态所有者、前后条件／不变量、适配依赖／生命周期、逻辑控件至对象／资源、场景入口／返回和测试责任，
**And** Flow层面四部分完整，单Task只承接适用部分；不机械四拆，不把治理／集成owner变成业务API。

**AC-2**

**Given** 现有Core／Contracts／Overlay可复用或确有公共边界变更，
**When** 细化契约与引用，
**Then** 优先引用Game.Core/Contracts唯一BCL-only契约和既有Overlay，真实公共变更才同步源码、Overlay、EventType及Task contractRefs，
**And** 适配不复制领域裁决，UI不直接写内部状态；成熟Overlay稀疏更新按现有合并规则保护人工内容。

**AC-3**

**Given** 待建对象还没有实际符号、节点或资源，
**When** 生成stage4 binding，
**Then** 允许明确planned引用，但适用责任、预期类型／生命周期、交接及以后检查可解析，
**And** 不能因为未实现缺少类型检查而说运行通过，也不强造假节点／readiness；真实对象存在后必须完成类型、编译、绑定与引擎检查。

**AC-4**

**Given** 既有定义／真实对象发生错配或上游定义不足，
**When** 检查并发布binding，
**Then** 错误定位到plan／Task／契约／资源，必要时返回定义所属阶段；只有定义与引用一致才提交新binding修订，
**And** 新binding不改旧plan修订／Flow身份，不弱化Acceptance换绿，不重复复制共享规则。

**AC-5**

**Given** 目标slice有UI或明确无UI，
**When** 登记实施义务和场景边界，
**Then** 保真实输入、场景方法、静态接线及人工义务各自责任，保原生布局／美术／动画人工区域，
**And** 未声明UI不能被默认免掉；无UI有依据则不强造Chapter7；更新owning入口说明及可追溯阶段事件。

### Story 3.5: 构造共同InputSet并精确判断新鲜度

As a 实施与恢复入口维护者,
I want 通过一个公共resolver取得当前Task全部相关实施依据及内容身份,
So that 所有入口对过期、相关变化和合法状态推进作出一致判断。

Refs: FR-7；FR-8；FR-9；FR-13；FR-16；NFR-E-3；NFR-E-4；NFR-E-11；AR-3；AR-6；AR-10；AR-21；AR-24；AC-BR-08；AC-BR-09；AC-BR-19。

**前置：** Story 3.3、Story 3.4。

**范围：** 公共InputSet resolver及内容／资格检查接口，使用现有契约、manifest及可显式提供的有效绑定；不依赖尚未开发的选择性runner或页面。公共算法仅此一处。

**Acceptance Criteria:**

**AC-1**

**Given** Task来源和完整plan集合经3.3证明且已有适用定义，
**When** 解析当前实施输入，
**Then** 包含相关source／Ledger／Requirement、plan／binding精确修订、Task定义与Acceptance、ADR／Overlay／Contract、manifest或其他验证、依赖闭包、规则／codec及影响结果的工具／环境，
**And** 每条保定位／raw身份及规范化策略，input_set_digest来自这些规范化条目；必需项未知／损坏不能静默排除。

**AC-2**

**Given** Task status或其他Task／无关catalog／HEAD变化，但当前定义和相关依赖未变，
**When** 比较当前输入身份，
**Then** status不当语义变化，其他无关变化不强迫本Task或全仓重做；入口仍实时核对当前依赖和任务资格，
**And** 不以整个catalog hash、整份tasks文件或单一Git HEAD作为所有Task新鲜度键。

**AC-3**

**Given** Acceptance、依赖、责任、契约／绑定、来源／规则或适用plan集合相关变化，
**When** 复验输入和旧readiness／缓存，
**Then** 相关变化改变身份并使受影响结果失效，明确需要返回的阶段；未知依赖扩大适用闭包，不能证明则阻断，
**And** 初版Task投影仅忽略Task／subtask.status，不能扩大mutable吞掉其他定义字段；raw提交proof按原模式保留。

**AC-4**

**Given** 读取时catalog或相关target漂移，或相关pending未消歧，
**When** 在适用读／执行保护内验证并重读，
**Then** 相关链一致且无未决占用才给有效InputSet，否则重试或公共阻断；旧pending仍被识别，
**And** 固定一致snapshot后保scope保护，在副作用／恢复边界重验；不持全局metadata锁等待长调用。

**AC-5**

**Given** 独立调用者需要检查已准备的实施输入或失败原因，
**When** 调用公共接口，
**Then** 得到相同结构、digest和公共诊断，Task当前未done不单独导致输入不合法，
**And** 合法来源／结构结果不等于readiness或运行通过；冻结Taskmaster状态不复制到新catalog／plan权威。

### Story 3.6: 绑定真实MVG义务或合法其他验证依据

As a 验证责任维护者,
I want 把Task实际责任与当前manifest或已采纳的其他验证依据绑定,
So that Flow责任不遗漏，合法非Flow也能在有证据的条件下实施。

Refs: FR-7；FR-8；FR-10；FR-11（适用性部分）；FR-12（保守绑定部分）；FR-14；NFR-E-2；NFR-E-6；NFR-E-9；AR-4；AR-6；AR-10；AR-11（绑定边界）；AR-12；AR-22；AC-BR-05；AC-BR-08；AC-BR-15；AC-BR-21；AC-BR-22（义务保留部分）。

**前置：** Story 3.4、Story 3.5。

**范围：** 适配现有manifest校验／rebind及非Flow验证去向，准备stage5义务绑定。可采用现有完整累计执行范围，不等待Epic4选择性执行；未知影响保守扩大且仍区分未来／本次责任。

**Acceptance Criteria:**

**AC-1**

**Given** Task属于Flow或承担MVG交接／集成／回归义务，
**When** 生成或复核实施绑定，
**Then** 须引用当前有效正式manifest、相关Flow／test／Requirement身份和具体责任，绑定当前plan／Task定义和累计基线，
**And** 缺manifest、旧manifest遗漏新责任或错修订不能通过，不因Task是工具／治理类型免掉真实影响。

**AC-2**

**Given** Task为已采纳合法非Flow且当前可证明没有MVG义务，
**When** 登记其验证适用性，
**Then** 来源理由、采纳决定、其他验证义务及共同InputSet有效时可不造Flow／manifest归属，
**And** 标签、空字段、Agent自报N/A或删适用性／其他验证依据不构成豁免。

**AC-3**

**Given** 非Flow变更实际影响已有Flow或反向关系未知，
**When** 分析适用义务并绑定，
**Then** 已知影响承接回归，未知保守扩大到可证明的适用累计范围，同时保既有必需、本次新增、范围外未来责任，
**And** 不能按目前能运行的对象缩小本次义务，不能为回归强迫范围外未来Flow提前实现；无法证明适用性则阻断。

**AC-4**

**Given** producer、consumer或integration-only owner承接不同责任，
**When** 校验角色与依赖，
**Then** 按其真实生产、消费或测试角色检查，不要求每个owner具业务API，也不新增等待当前Task自身done的前置，
**And** 不抹去真实依赖／业务前置，Task未实现与所需定义不明是不同问题。

**AC-5**

**Given** 同一Flow／测试或Requirement被多条路线共享，
**When** 维护累计绑定及stage5候选，
**Then** 沿唯一验证处置与多路线／共享证据键，不重复完成计数；新义务不会由旧done自动覆盖，
**And** 退休／减义务仍需来源与显式审阅；binding独立修订经共享提交服务发布，单纯绑定不算运行证据。

### Story 3.7: 在Chapter5核对同源定义并形成有效readiness

As a 任务实施者,
I want 在实施前确认Acceptance、来源、契约、绑定与验证义务属于同一组当前依据,
So that Agent得到可实施的定义和明确缺口，不靠自报或陈旧时间戳放行。

Refs: FR-7；FR-8；FR-9；FR-14；FR-17（Chapter5部分）；NFR-E-3；NFR-E-6；NFR-E-7；NFR-E-11；AR-2；AR-6；AR-10；AR-12；AR-13；AC-BR-08；AC-BR-09；AC-BR-15；AC-BR-21。

**前置：** Story 3.5、Story 3.6。

**范围：** 适配现有Chapter5 semantic reconciliation／guarded检查与readiness产物，用共同resolver和已采纳来源审计；不是重新定义来源语义，也不是运行验收。

**Acceptance Criteria:**

**AC-1**

**Given** 当前来源审计可复验，3C／4定义及适用义务已绑定，
**When** 执行Chapter5，
**Then** 核对Task Acceptance、Requirement、计划／非Flow去向、ADR／Overlay／Contract、依赖与验证义务，定位遗漏、重复责任和无人承接交接，
**And** 继续独立Task／契约语义核对，不以3A审计省略本阶段；有效原审计不因无关变化全量重做。

**AC-2**

**Given** 共同InputSet及阶段定义一致，
**When** 生成readiness及绑定，
**Then** readiness明确冻结输入身份、适用scope和依据，并通过同一提交／格式路径供入口复验，
**And** 不是只刷新旧ready时间戳，stage5不改旧plan修订或引入新任务完成状态。

**AC-3**

**Given** Task未done、存在合法planned对象或仅承担集成测试，
**When** 执行阶段就绪检查，
**Then** 未done本身不拒绝，planned可未实现但定义足够明确；按producer／consumer／owner实际责任检查，
**And** 不新增owner自身done死锁，不为planned造假场景／接口，不把就绪标为已实现或运行通过。

**AC-4**

**Given** manifest／其他验证、契约／绑定、source／rule或Task定义缺失／损坏／过期，
**When** 尝试取得或复用readiness，
**Then** 公共诊断阻断并定位owning stage；相关输入变化只失效受影响就绪，
**And** 无依据N/A和缺B来源不能落legacy，旧done不能绕过新义务。

**AC-5**

**Given** Chapter5通过或产生Needs Fix，
**When** 保存检查／修复交接及说明，
**Then** 沿现有P1必修、审阅与质量底线处理，必修项未修不放行；允许延期项仅按既有政策记录，
**And** 不改质量阈值、关闭测试或弱化Acceptance换绿；记录实际耗时／调用／复用和返回阶段。

### Story 3.8: 让直接Chapter6与公共CLI消费统一实施门禁

As a 任务实施者,
I want 从直接脚本或公共CLI开始当前单Task时都取得相同实施决定,
So that 不能通过更换入口跳过有效定义、readiness和真实义务。

Refs: FR-8；FR-9；FR-11（局部自检部分）；FR-13；FR-14；FR-16；FR-17（Chapter6 direct部分）；NFR-E-10；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-7；NFR-E-9；NFR-E-11；AR-5；AR-6；AR-8；AR-10；AR-13；AR-17；AR-21；AR-24；AC-BR-08；AC-BR-09；AC-BR-10；AC-BR-15；AC-BR-19；AC-BR-21。

**前置：** Story 3.7、Story 2.8。

**范围：** 在dev_cli、run_single_task_chapter6_lane、_mvg_obligations及直接调用的真实副作用边界接同一gate；保既有单任务TDD／质量流程，不新增执行框架。恢复／route入口由3.9接入。

**Acceptance Criteria:**

**AC-1**

**Given** 有效B Task拥有同源定义／readiness及适用验证依据，
**When** 从公共CLI或直接Chapter6入口执行，
**Then** 两入口调用同一来源分类／InputSet／readiness／义务门禁，接受合法Flow或无MVG非Flow，进入当前单Task流程，
**And** 当前Task不先要求done，旧A只在其冻结边界使用原有效依据；_mvg_obligations不能先无trace返回current再补检查。

**AC-2**

**Given** 缺B来源、plan／binding／manifest或其他验证、损坏／过期／未知依据，
**When** 尝试直接或间接实施，
**Then** 在模型调用、文件应用及其他实施副作用前阻断，返回同一reason_code及定位，
**And** 删标识／manifest、自由N/A、改Task类型或调用内部脚本不获得旁路。

**AC-3**

**Given** 运行需要固定相关定义且可能有并行绑定／状态变化，
**When** 持适用scope租约开始并在副作用边界复验，
**Then** 统一锁顺序、相关scope互斥和短metadata锁约束生效，状态写者遵守共享保护并保当前Taskmaster权威，
**And** 不在长模型／执行期间持全局锁，不相关scope可推进，相关InputSet漂移或保护不可得则安全停止。

**AC-4**

**Given** Task经过实现、局部测试、评审与修复，
**When** 执行既有Chapter6流程，
**Then** 保TDD、自检、Needs Fix、pre-commit和P1底线，局部验证覆盖当前适用领域／适配／绑定责任及必要已有回归，
**And** 不因每按钮／节点／保存运行全MVG，不把局部PASS、planned、空报告或跳过升级为Flow／累计完成。

**AC-5**

**Given** 上游定义缺口或质量／运行失败已触发既有止损信号，
**When** 处理失败，
**Then** 保真实错误和恢复点，遵守rerun_guard等现有止损；定义问题返回owning stage，状态／budget历史不重置，
**And** Chapter6不隐式全局Knowledge refresh，不临时重扫或用页面摘要重解释需求；记录真实执行／复用／返工事件。

### Story 3.9: 在恢复与route入口重验当前输入和任务资格

As a 恢复任务的实施者,
I want 在resume或route执行前检查当前有效依据和持久run状态,
So that 旧缓存、状态变化或入口切换不会恢复一个已无资格的执行。

Refs: FR-8；FR-9；FR-13；FR-14；FR-16；FR-17（resume／route部分）；NFR-E-3；NFR-E-4；NFR-E-7；NFR-E-9；NFR-E-11；AR-5；AR-6；AR-8；AR-9；AR-10；AR-13；AR-21；AR-24；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-09；AC-BR-15；AC-BR-19；AC-BR-21。

**前置：** Story 3.8。

**范围：** 给resume_task、chapter6_route、_chapter6_recovery_common及实际恢复副作用接统一gate；沿既有推荐／执行边界，不把recommendation-only变成执行。

**Acceptance Criteria:**

**AC-1**

**Given** 已有Task run及恢复sidecars，当前定义仍有效，
**When** 调用resume／route推荐或明确执行，
**Then** 先复验共同InputSet、readiness、适用义务与当前Task／依赖资格，再按既有协议决定恢复位置，
**And** recommendation-only仅给建议，不生成实施副作用；不能因缓存显示ready绕过当前依据。

**AC-2**

**Given** 来源／规则／契约／绑定或Task适用plan集合相关变化，或存在pending／损坏，
**When** 尝试恢复，
**Then** 按同一公共原因拒绝并定位owning stage／原journal，未知scope保守阻断，
**And** 旧A资格／旧done不遮蔽新增B责任，Capability模型证据恢复和文件应用恢复仍按各自合同。

**AC-3**

**Given** 仅当前或其他Task status合法推进，或无关scope／HEAD改变，
**When** 复验已完成操作和当前恢复资格，
**Then** 相关定义未变可保已提交成果，不重写旧after状态；任务与依赖实际资格重新判断，
**And** 不能仅用Task ID／HEAD／整份tasks文件hash认定复用，也不把当前任务未done当通用拒绝条件。

**AC-4**

**Given** 正在执行的scope遇到绑定替换、共享Task新plan加入或后编辑，
**When** 恢复至副作用边界，
**Then** 固定本run InputSet并取得当前及相关scope保护，冲突或漂移停止而非使用一半新旧依据，
**And** journal前像／当前状态校验保后编辑和新进度，scope保护遵循公共锁顺序且不长期占全局metadata锁。

**AC-5**

**Given** run已出现确定性失败／重复重试预算或epoch／reopen撤销，
**When** 决定下一动作，
**Then** 沿原持久预算、stop-loss及合法完成项规则处理，失败／调用历史保留，
**And** 不通过新run lineage、换入口、重建Knowledge或删除marker清除无进展信号；公共诊断与CLI help／Skill说明一致。

### Story 3.10: 按缺陷类型复用规划或返回定义所属阶段

As a 修复任务的实施者,
I want 明确区分纯实现缺陷与定义／契约变化，并按已有责任修复,
So that 能保留有效规划和旧完成历史，同时避免临时修改验收获取通过。

Refs: FR-8；FR-9；FR-13；FR-14；FR-16；NFR-E-3；NFR-E-7；NFR-E-9；AR-6；AR-10；AR-13；AC-BR-09；AC-BR-10；AC-BR-14；AC-BR-23。

**前置：** Story 3.1、Story 3.2、Story 3.7、Story 3.8、Story 3.9。

**范围：** 在现有Chapter6失败／修复交接中提供可复查缺口与路由依据，实际Task更新走既有治理三联；不自动执行上游重规划或增开同义修复任务。

**Acceptance Criteria:**

**AC-1**

**Given** 缺陷未改玩法定义、契约、状态所有权、交接／绑定设计或验收义务，
**When** 判定修复范围，
**Then** 引用当前有效采纳与原Task／Flow身份，经必要Task映射、readiness、局部自检及适用回归进入修复，
**And** 不默认全重跑3A／3B，不省掉当前就绪或回归，纯实现变化与定义缺口有可审阅依据。

**AC-2**

**Given** 修复涉及定义、契约、所有权、交接／绑定设计或验证义务，
**When** 形成缺口交接，
**Then** 返回拥有该定义的3A／3B／4／5等阶段，以受治理差异承接后续变化，
**And** 不能弱化Acceptance、自由N/A、改状态或删除测试把定义变更伪装为局部修复。

**AC-3**

**Given** 真实修复缺口需要新Task或更新既有Task，
**When** 提出业务视图delta并经治理处理，
**Then** 只承接真实新增责任，保旧ID／done／历史及累计基线；Task与Flow关系正确，
**And** 不创建同义重复任务，不用旧done覆盖新义务，新增来源／定义变化使受影响绑定和readiness按规则重验。

**AC-4**

**Given** 同一缺陷复现、无关输入变化或已完成上游仍有效，
**When** 继续现有run恢复或路由，
**Then** 复用当前有效成果并保稳定预算／错误记录，定位实际重复与返回阶段，
**And** 不通过重复候选生成或全局Knowledge刷新掩盖失败；当前修复结论不冒充Flow／累计完成。

**AC-5**

**Given** 修复完成或仍被阻断，
**When** 报告适用自检／回归及未完责任，
**Then** 区分局部PASS、真实运行及人工义务，未执行或范围内未完仍保pending／blocked，
**And** 现有Needs Fix、P1及测试规则继续生效，记录实测耗时／调用／复用／返工。

### Story 3.11: 按目标slice收口Chapter7并复用已验证UI

As a UI闭环维护者,
I want 消费Flow提前声明的UI责任和Chapter6有效证据，仅补目标slice真实缺口,
So that 无需等待全游戏或重复创建已实现同义任务即可判断目标UI闭环。

Refs: FR-7；FR-8；FR-9；FR-10；FR-11（UI证据部分）；FR-13；FR-14；FR-17（Chapter7部分）；NFR-E-1；NFR-E-2；NFR-E-6；NFR-E-7；NFR-E-9；AR-6；AR-10；AR-12；AR-13；AC-BR-04；AC-BR-10；AC-BR-12；AC-BR-13；AC-BR-21。

**前置：** Story 3.4、Story 3.6、Story 3.7、Story 3.8、Story 3.9、Story 3.10。

**范围：** 适配现有Chapter7 backlog／wiring／artifact manifest／任务补缺与状态patch路径；保原profile及目标slice责任，不新建UI框架或重做视觉设计。

**Acceptance Criteria:**

**AC-1**

**Given** 目标Flow／backlog slice声明UI义务且相关定义有效，
**When** 执行Chapter7闭环核对，
**Then** 消费场景入口／返回、真实输入、反馈、绑定与适用人工义务，只针对该目标slice，
**And** 无需等全游戏Task完成；无UI有有效依据则不适用，不以未声明字段自动跳过实际UI。

**AC-2**

**Given** Chapter6已有与当前InputSet／测试身份相符的UI证据，
**When** 匹配已完成责任，
**Then** 复用仍有效的实现和验证义务，保原Task／Flow身份及证据定位，
**And** 不重复生成同义Task／义务；过期、不同条件、仅静态接线或方法调用证据不能充当真实引擎输入。

**AC-3**

**Given** 关键绑定断开、对象类型／生命周期不符或证据空／跳过／未执行，
**When** 运行适用核对与测试，
**Then** 对应检查失败或保持pending并定位，不把planned／连线存在当运行通过，
**And** 人工视觉／手感义务独立保留，局部UI完成不能自动宣告Flow全必需义务已完成。

**AC-4**

**Given** 发现真实UI实施或定义缺口，
**When** 通过既有治理路径补缺，
**Then** 定义变化返回owning stage，任务变化由业务视图审阅／编译承接，状态patch尊重Taskmaster及共享保护，
**And** 保成熟状态／历史和原生场景人工区域，不能静默直写新义务或清旧done。

**AC-5**

**Given** Chapter7生成目标slice结果，
**When** 保存对应证据和交接，
**Then** 报告已验证、待执行、人工及阻断项，所有引用可回到当前绑定／原始证据，
**And** 保后续Flow／累计收尾责任，沿CLI／Skill／profile文档真实入口；不隐式全局Knowledge刷新。

### Story 3.12: 让页面实施触发与全入口决定保持一致

As a 从页面发起实施或恢复的操作者,
I want 页面操作复用同一实施／恢复服务，并核对本批全部真实入口,
So that 页面、CLI、直接及恢复调用不能互相绕过，也能准确得到阻塞和恢复位置。

Refs: FR-6；FR-7；FR-8；FR-9；FR-10；FR-13；FR-14；FR-15（实施触发边界）；FR-16；FR-17（本批入口对齐）；NFR-E-10；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-7；NFR-E-9；NFR-E-11；AR-5；AR-6；AR-7；AR-8；AR-10；AR-13；AR-17；AR-21；AR-24；AR-26；AR-28（实施入口部分）；AC-BR-05；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-09；AC-BR-13；AC-BR-14；AC-BR-15；AC-BR-16（实施触发部分）；AC-BR-19；AC-BR-21；AC-BR-23。

**前置：** Story 3.3、Story 3.5、Story 3.6、Story 3.7、Story 3.8、Story 3.9、Story 3.10、Story 3.11。

**范围：** 只接现有页面触发／Knowledge路由调用的真实执行边界并完成本批入口一致性验收，不开发Epic4完整进度展示或选择性runner。使用既有全部适用累计执行能力，不以未来Epic功能作为准入前置。

**Acceptance Criteria:**

**AC-1**

**Given** 页面请求实施、恢复或路由一个B Task，
**When** 执行请求对应服务，
**Then** 页面调用与CLI／direct／resume／route相同gate和当前InputSet，实施前资格及scope保护相同，
**And** 不能用页面摘要、前端缓存或旧ready授权；preview触发不得推进current／last-known-good或main发布身份。

**AC-2**

**Given** 相同合法Flow、合法非Flow、纯集成owner或冻结A输入用于各真实入口，
**When** 对比决定及实际副作用边界，
**Then** 各入口按相同适用差异放行或阻断，不造manifest／业务API／自身done前置，
**And** Task局部实施不等于Flow完成；触发时始终核对真实Task与依赖状态，不提前启用新增默认B。

**AC-3**

**Given** 分别删origin／manifest／非Flow理由、损坏journal或切断binding，或增加共享Task新plan，
**When** 运行CLI／direct／resume／route／页面一致性反例，
**Then** 每一实际入口均在副作用前按同一公共原因拒绝或使当前旧readiness失效，无法证明scope时保守阻断，
**And** 不只测dispatcher而漏底层直接调用，不把unknown视为legacy，现有旧pending亦被覆盖。

**AC-4**

**Given** 已完成apply后status推进，或未完成apply时发生状态并发／后编辑，
**When** 在Windows运行状态与恢复反例，
**Then** 完整操作no-op不回写旧状态；未完成操作严查raw前像并冲突停止，当前相关定义的投影校验与无关变化复用成立，
**And** 跨scope共享Task改变适用集合须取得全部相关保护；已发布但相关pending未消歧仍阻断，不用删marker取得通过。

**AC-5**

**Given** 页面实施服务及本Story前四组核对已完成，前述Story各自验收有效，
**When** 整理Epic3对Epic4的交接，
**Then** 本批真实消费者、CLI／Skill／AGENTS／owning文档说明一致，交付三联／绑定、共同InputSet／readiness／门禁、修复与UI责任及可追溯实测事件，
**And** 仍列未实现的真实范围接口／完整Knowledge展示／奖励试点，不以关系图或样本通过宣告全迁移或累计full-MVG；当前本轮仅编写Story未执行这些未来测试。

## Epic 4: 执行真实适用验证并展示可信进度

验证者区分局部、Flow和累计里程碑结果，执行受影响义务并核对实际覆盖；操作者从Knowledge、页面／CLI定位真实阶段、阻塞和恢复位置。主覆盖FR-11／12／13／15／17，共同承接FR-8／9／10／14／16。

重点约束是NFR-E-2／3／4／6／7／8／9／10／11及AR-10／11／16／17／24／25／26／28等适用部分；沿既有Windows／Godot／C#、测试与trusted-ref规则，不增规划数据库或第二套完成状态。没有独立UX合同，页面沿既有结构完成已采纳职责，不扩视觉重设计。

### Story 4.1: 从受治理反向关系计算完整传递影响

As a 变更规划者,
I want 从共享变更定位所有必要受影响Flow、Task和验证责任，包括尚未实现的Flow,
So that 不会因页面图不全或当前代码可运行而遗漏后续责任。

Refs: FR-12；FR-13（相关输入部分）；FR-14；FR-17（影响消费者部分）；NFR-E-2；NFR-E-3；NFR-E-9；AR-4；AR-10；AR-11；AR-25；AC-BR-09；AC-BR-11；AC-BR-22。

**前置：** Story 3.12。

**范围：** 在既有plan／binding／manifest和依赖结构上注册反向边及闭包查询，输出可审阅影响证明；不新建规划数据库，不把派生图设为来源权威，不执行测试或提前创建未来Task。

**Acceptance Criteria:**

**AC-1**

**Given** 共享规则、状态、命令、契约、适配、场景资源或测试基础设施发生明确变更，
**When** 按已提交四部分定义、绑定、契约、测试责任和累计manifest构建反向引用并查询，
**Then** 报告所有直接及必要传递影响，含当前Task、已有与planned Flow及其他验证去向，给出根、路径和来源身份，
**And** 不是仅按Task标签、页面可见关系或已实现对象过滤；Flow跨Capability和共享Task仍完整。

**AC-2**

**Given** 反向图含共享对象、合法循环、多Flow引用或唯一owner定义，
**When** 计算必要闭包，
**Then** 以稳定实体身份去重并在循环中终止查询，保可解释路径和唯一语义owner引用，
**And** 不把遍历环当玩法非法，不按路线数重复计Requirement覆盖或复制共享规则。

**AC-3**

**Given** 有必需边缺失、未知映射或不可验证引用，
**When** 决定保守影响范围，
**Then** 扩大到可证明适用的累计manifest／来源范围并保未知及扩大原因，仍列planned与当前责任，
**And** 没有可证明边界时不能缩到空集，也不能把全部未来planned变成应立即执行的回归。

**AC-4**

**Given** 相关source／plan／binding／契约／规则改变或只发生无关发布，
**When** 复验影响证明及缓存，
**Then** 相关变化重算适用部分，无关HEAD／catalog条目不单独使全仓闭包失效，未知相关性保守扩大，
**And** 不复用损坏proof，不以原始文件名或单一内容hash替代完整相关身份。

**AC-5**

**Given** 操作者查看或交接影响报告，
**When** 通过只读接口取得结果，
**Then** 可定位每个影响的义务、来源、当前修订与未知项，报告只证明影响核算，
**And** 影响登记不等于已实现／已运行，不更新Task状态、正式发布指针或无依据退休旧Flow／test；事件留logs。

### Story 4.2: 形成可执行的三类义务VerificationScope

As a 验证责任维护者,
I want 将影响报告与当前交付边界转换为有身份、可审阅且可执行的验证范围,
So that 旧回归、本次新增和范围外未来责任不会混淆或被失败重分类。

Refs: FR-11；FR-12；FR-13；FR-14；NFR-E-2；NFR-E-3；NFR-E-6；NFR-E-9；AR-10；AR-11；AR-25；AC-BR-10；AC-BR-11；AC-BR-14；AC-BR-17；AC-BR-21；AC-BR-22。

**前置：** Story 4.1、Story 3.6、Story 3.7。

**范围：** 以既有公共codec／schema注册 newrouge.b-route-verification-scope.v1，冻结范围合同及交付分类证据；不重造manifest权威或为未实现对象创建假可执行测试。

**Acceptance Criteria:**

**AC-1**

**Given** 4.1影响、当前已采纳交付范围、有效manifest与共同InputSet可核对，
**When** 生成VerificationScope，
**Then** 绑定schema_version、scope_id、input_set_digest、精确plan／manifest／累计基线、变更根、传递影响及证明、声明测试和人工责任，
**And** 用稳定Flow／test／Requirement身份引用，当前责任不能由旧manifest或当前可运行状态裁剪。

**AC-2**

**Given** 范围中存在旧回归、本次新增或未完、以及有依据的未来义务，
**When** 逐义务分类，
**Then** 旧受影响回归完整保留，本次未完保持pending／blocked并阻断本次完成，范围外未来登记定义／绑定更新及后续责任，
**And** 同一Flow可同时承载旧与新增义务，不能把整个失败Flow转planned或future获取绿色。

**AC-3**

**Given** 共享改动使旧Flow A失败并影响范围外未实现B，
**When** 核对范围及后续变更，
**Then** A须修后完整回归，B保影响和责任不宣通过；B进入本次范围时其未完义务阻断，
**And** 合法范围调整需来源与受治理delta／防削弱审阅，不以失败、启动不了或测试缺失作为移除理由。

**AC-4**

**Given** 映射未知、合法非Flow影响Flow或其他验证仍适用，
**When** 制定执行集合，
**Then** 未知保守扩大但仍保三类责任，真实MVG影响绑定回归，合法无MVG非Flow按已采纳其他验证处理，
**And** 可执行测试、待实施义务和人工检查分别列明，未实现测试不捏造PASS或脚本入口。

**AC-5**

**Given** 重复生成同输入范围或范围依据发生漂移，
**When** 验证合同及审阅结果，
**Then** 同有效内容保持可比较身份，相关变化产生新范围并使受影响旧结论失效，未知／损坏版本拒绝，
**And** 范围仅授权声明的验证责任，不授予Task／Flow／里程碑完成，不更新Task状态。

### Story 4.3: 让真实执行器消费范围并报告实际覆盖

As a 验证执行者,
I want 把VerificationScope传给实际测试执行器并取得可核对的执行回执,
So that 推荐排序、空报告或仅声明范围不会冒充已完成回归。

Refs: FR-11；FR-12；FR-13（运行身份部分）；FR-17（runner部分）；NFR-E-1；NFR-E-6；NFR-E-7；NFR-E-9；AR-6；AR-10；AR-11；AR-17；AR-25；AC-BR-10；AC-BR-11；AC-BR-12；AC-BR-17；AC-BR-22。

**前置：** Story 4.2。

**范围：** 改造既有manifest校验／MVG runner及相关入口的请求与回执，复用xUnit／GdUnit4和既有正式runtime receipt／inventory／snapshot。允许执行声明范围或明确更大保守集合，不承诺提速。

**Acceptance Criteria:**

**AC-1**

**Given** 有效VerificationScope及目标工具链已就绪，
**When** 通过实际runner启动验证，
**Then** 执行器真实消费scope_id／digest、当前formal manifest、声明测试与环境，并固定整合snapshot及适用保护，
**And** 不是只改recommend排序；如仍运行更大累计集合，明确记录实际超集而不称选择性执行。

**AC-2**

**Given** 部分测试实际运行、失败、未运行或需人工，
**When** 生成正式执行回执，
**Then** 列requested_tests、executed_tests、not_run及原因、manual_obligations、结果证据和覆盖，绑定同scope／InputSet／manifest／整合snapshot，
**And** 漏项、空报告、跳过、planned或本次未完不能PASS；旧回归失败／无法启动不能转future。

**AC-3**

**Given** 真实对象已存在或需验证UI关键输入，
**When** 执行适用的类型／编译／绑定／引擎检查，
**Then** 领域xUnit、Godot GdUnit4、静态接线、场景方法、真实引擎输入及人工义务各报对应证据等级，
**And** 断开必要绑定使相应检查失败，fixture初始化与玩家动作证据区分；不以测试命名入口或假runner冒游戏生产路径。

**AC-4**

**Given** 输入／绑定／环境在运行或恢复边界漂移，或确定性失败／stop-loss已知，
**When** 检查执行资格和后续动作，
**Then** 相关变化／占用阻断当前结论并保已观察结果，沿既有停止信号避免无进展执行，
**And** scope租约与短metadata锁遵循共享服务，不长期占全局锁，不跳回归／关测试换绿。

**AC-5**

**Given** 同一输入分别以小范围、明确超集或坏范围运行，
**When** 核对真实进程调用、解析结果和覆盖回执，
**Then** 执行范围与实际证据可重建，未知schema／错manifest／缺必需测试被拒绝或标阻断，
**And** 协议fixtures仅证明适配／解析，不能当实际Godot玩法通过；Windows／工具实际版本和未验证限制随证据记录。

### Story 4.4: 在身份匹配时复用构建与共享测试证据

As a 验证执行者,
I want 在保持测试状态隔离的条件下复用有效构建、预热和共享测试结果,
So that 多个Flow可以引用同一有效证明，重试不重复做无关工作且不污染状态。

Refs: FR-11；FR-13；FR-16；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-9；NFR-E-10；AR-4；AR-9；AR-10；AR-11；AR-25；AR-26；AC-BR-06；AC-BR-09；AC-BR-17；AC-BR-20。

**前置：** Story 4.3、Story 2.9、Story 3.5。

**范围：** 在现有构建／runner／证据读取路径加入身份核验和共享引用，不新建Task／MVG完成缓存或第二证明格式；构建复用与测试结果复用分别判断。

**Acceptance Criteria:**

**AC-1**

**Given** 多个Flow需要相同构建或预热，
**When** 验证可复用工件身份，
**Then** 仅在影响其结果的源内容／工具链／环境及现有工件规则匹配时复用，并记录原始来源和理由，
**And** 复用构建不自动等于测试通过，实际未命中的成本／耗时保留，不能用预算预留宣称节约费用。

**AC-2**

**Given** 同一测试被多个当前Flow要求，
**When** 按现有测试身份、完整相关输入、验证语义、环境及同一整合snapshot核对结果，
**Then** 仅有效同条件结果可去重引用，沿Requirement唯一验证处置／多路线角色保覆盖行为，
**And** 不按Flow数量重复计完成，不把不同输入或仅名称相同的测试合并。

**AC-3**

**Given** 测试顺序变化、重入、共享fixture或并行状态可能互相影响，
**When** 执行测试并管理可变状态，
**Then** 各测试有隔离／重置边界，重复或换序不能继承前一测试的业务可变状态，
**And** 可共享只读构建／预热，不共享未经隔离的游戏状态；人工义务不能由机器共享结果代替。

**AC-4**

**Given** 相关来源／契约／规则／snapshot变化、proof损坏，或仅无关语义变化，
**When** 重新判断复用资格，
**Then** 相关或损坏结果拒绝，真正无关变化不单独导致语义重做；仍严格沿既有formal runtime receipt／inventory／snapshot及dirty-worktree检查，
**And** 不为复用绕过现有运行证据身份，不拼不同整合快照；Capability完成项adoption与运行证据复用继续各按独立规则。

**AC-5**

**Given** 本次命中复用、真正重跑或不能证明资格，
**When** 保存回执和事件，
**Then** 列复用证据ID／来源／匹配理由、实际执行和未知／失效原因，同event去重，
**And** 不刷新旧PASS时间戳充新运行，不设置提速或成本下降指标，结果供现有收尾路径使用。

### Story 4.5: 分别核对Task、Flow和累计里程碑完成

As a 验收维护者,
I want 按当前全部适用义务与正式证据核对不同范围的完成声明,
So that 局部绿色、部分运行或跨快照报告不能冒充整个里程碑通过。

Refs: FR-11；FR-12；FR-13；FR-14；FR-17（milestone handoff部分）；NFR-E-2；NFR-E-6；NFR-E-7；NFR-E-9；AR-6；AR-10；AR-11；AR-13；AR-25；AC-BR-10；AC-BR-11；AC-BR-12；AC-BR-13；AC-BR-14；AC-BR-17；AC-BR-21；AC-BR-22。

**前置：** Story 4.2、Story 4.3、Story 4.4、Story 3.11。

**范围：** 适配既有Flow／milestone_incremental_handoff及正式验收读取规则，增加三类义务和范围核对；原始报告仍为运行证明，不在新catalog保存通过状态或创建另一生命周期。

**Acceptance Criteria:**

**AC-1**

**Given** 单Task局部自检成功、但Flow其他必需实现或验证未齐，
**When** 请求收尾，
**Then** 局部结果仅满足其对应责任，Flow保持pending／blocked并列缺项，
**And** 不因旧done、结构关系、planned或已有可运行代码忽略本次新增义务。

**AC-2**

**Given** 目标Flow实施、适用Chapter7和验证已齐，
**When** 核对目标Flow完成，
**Then** 所有当前必需义务、受影响旧回归及适用人工检查均有当前身份的有效证据才通过，
**And** 真实输入、方法调用、静态连线及人工等级不混用；集成owner不因检查新增自身done前置。

**AC-3**

**Given** 单Flow、critical或partial结果被用于里程碑收尾，
**When** 运行累计核对，
**Then** 只有当前累计必测与组合测试及人工义务在同一整合snapshot满足才可称累计full-MVG，
**And** 部分结果显示真实范围，不拼接不同snapshot的绿色报告；缺任一当前必需项不授权累计通过。

**AC-4**

**Given** 旧Flow A因共享改动失败，范围外未实现B受影响或后来进入本次范围，
**When** 合并milestone handoff与范围结果，
**Then** A修后完整回归；B在范围外保定义／绑定更新及后续责任而不要求提前实施，B进入本次则未完阻断，
**And** 不按当前是否能运行重分类换绿，旧Flow／test退役或减义务继续走显式防削弱。

**AC-5**

**Given** manifest／scope／InputSet／receipt损坏、过期或报告为空／未执行，
**When** 生成完成结论，
**Then** 拒绝无法证明的范围并定位reason_code／实体／恢复依据；合法非Flow按其已采纳其他验证判断，
**And** 原Task状态仍由Taskmaster管理，来源和运行报告保持各自权威，更新owning收尾说明与事件。

### Story 4.6: 派生展示规划、实施与运行身份

As a 查阅项目状态的维护者,
I want 从Knowledge定位当前来源、关系、缺口和原始证据，并看清所在分支及证据等级,
So that 计划、部分进度或旧工作区不会被误读成正式运行和main发布事实。

Refs: FR-13（展示有效性部分）；FR-15；FR-17（Knowledge部分）；NFR-E-2；NFR-E-3；NFR-E-6；NFR-E-8；NFR-E-9；NFR-E-11；AR-1；AR-4；AR-10；AR-16；AR-24；AR-28；AC-BR-04；AC-BR-09；AC-BR-16；AC-BR-17；AC-BR-19。

**前置：** Story 4.1、Story 4.5、Story 3.5、Story 2.9。

**范围：** 适配既有Knowledge／semantic-topology派生读取和受控刷新／发布边界；不把logs纳入普通全局语义检索，不建立新权威或隐式刷新副作用。

**Acceptance Criteria:**

**AC-1**

**Given** 正式提交身份、Task状态与运行报告可验证，
**When** 构建或读取派生关系，
**Then** 可定位来源／Requirement／Capability／Flow／四部分／Task／契约／场景／义务及影响，分开计划、实现、运行与证据等级，
**And** 从原始权威和提交链读取，关系存在不等于实现，运行结论回链原始报告；派生图不反写来源或Task状态。

**AC-2**

**Given** 当前对象来自工作分支／workspace preview、attempt、stable或main，
**When** 展示其来源和身份，
**Then** 每项绑定对应snapshot／分支／提交或工作区身份，已提交规划前缀明确标部分规划，
**And** preview不得推进current／last-known-good；dirty workspace或非trusted-ref不发布为main事实，保ADR-0035既有trusted-ref规则。

**AC-3**

**Given** 没有Task的正式采纳或合法非Flow定义存在，
**When** 派生展示，
**Then** 来源／采纳／逻辑四部分和验证去向可被定位，缺实施Task显示真实阶段，
**And** 不统一以Task readiness阻断前置规划，不创建假Task或把planned对象描绘成真实资源。

**AC-4**

**Given** proof过期、pending未消歧、epoch／reopen撤销本地资格或source相关变化，
**When** 复验展示条目，
**Then** 显示失效／阻断及原始定位，撤销项不复活，损坏／未知不作为合法缺失或PASS，
**And** local clear本身不删除正式Git采纳／累计基线；正式采纳按自身source／catalog链验证，旧审计保留。

**AC-5**

**Given** 普通Chapter6／Review／Recovery消费Knowledge或显式注册closure producer刷新，
**When** 执行对应读取／刷新路径，
**Then** 普通消费者不隐式全局重建／发布，注册Chapter3／5 producer按原hook区分Workspace Last Attempt与Latest Successful，canonical仍需trusted-ref，
**And** 日志证据以显式引用定位，不扩普通全局检索到logs／备份／历史；静态导航与原来源回退保持可用。

### Story 4.7: 在规划页面按真实阶段操作并定位阻塞与恢复

As a 使用规划页面的规划者,
I want 先规划后任务，并在页面看清当前阶段、已提交前缀、错误和合法恢复入口,
So that 页面操作与CLI实际流程一致，不需要伪造readiness才能开始规划。

Refs: FR-3（页面入口部分）；FR-8；FR-9；FR-15；FR-17（页面／CLI部分）；NFR-E-2；NFR-E-6；NFR-E-9；NFR-E-11；AR-2；AR-6；AR-16；AR-26；AR-28；AC-BR-01（页面阶段部分）；AC-BR-04；AC-BR-08；AC-BR-16；AC-BR-19；AC-BR-21。

**前置：** Story 4.6、Story 2.10、Story 3.12。

**范围：** 修改现有规划页面及其调用适配，消费已实现CLI／服务和4.6派生模型；保现有视觉结构，不新增独立UX设计、控制面或第二套任务／运行状态。

**Acceptance Criteria:**

**AC-1**

**Given** 目标尚无Task／readiness且来源输入适用，
**When** 从页面选择来源审计或正式语义规划，
**Then** 调用对应Task无关正式入口，不因后置readiness缺失禁用前置阶段，阶段名／输入／输出与CLI一致，
**And** 不走隐藏draft／allow_unready旁路；页面上Task生成／实施动作只有相应阶段条件满足才可执行。

**AC-2**

**Given** 有已提交前缀、当前候选进行中或预算／执行失败，
**When** 展示本次进度，
**Then** 消费现有协调器／checkpoint／epoch和catalog的真实结果，显示当前阶段、已完成范围、阻塞原因及恢复位置，
**And** worker／候选中间态不当已采纳，部分规划不当planning complete或runtime PASS，不读取旧撤销结果填绿；显式新请求按原合同创建新run，resume选定现有run且不重置其预算。

**AC-3**

**Given** 操作者查看一次失败或可恢复操作，
**When** 展示诊断并调用已有恢复入口，
**Then** reason_code／stage／entity／expected／actual／resume_ref来自同一公共服务，原始依据可定位，推荐与执行区别明确，
**And** 不能用摘要生成新的权限或恢复指令；Task实施触发仍走3.12统一gate，旧A与合法非Flow按实际适用差异处理。

**AC-4**

**Given** 页面处workspace／attempt预览或选择查看stable／main，
**When** 读取或发起受允许操作，
**Then** 身份明确且与4.6一致，预览不能写canonical发布指针，恢复／实施不隐式全局Knowledge refresh，
**And** 不由页面自由切换Task来源或删除B标识，不引入多租户／认证／平台迁移工程。

**AC-5**

**Given** 浏览器页面、公共CLI和直接服务面对相同成功／失败输入，
**When** 核对真实请求与结果，
**Then** 无Task规划、缺B依据、未知版本、合法非Flow、pending／budget等决定与实际入口一致，页面显示准确可恢复状态，
**And** 界面说明不承诺未实现功能；自动化页面／接口测试只证明交互合同，不冒充Godot玩法或真实奖励试点证据。

### Story 4.8: 汇集可追溯过程观测与统一诊断

As a 诊断工作流问题的维护者,
I want 按阶段／Flow追踪实际调用、耗时、复用、重复执行和返工原因,
So that 能发现遗漏、失效范围错误和无进展重试，而不以速度或成本下降替代路线验收。

Refs: FR-13；FR-15；FR-16；FR-17（观测接口部分）；NFR-E-2；NFR-E-8；NFR-E-9；NFR-E-10；NFR-E-11；AR-9；AR-15；AR-16；AR-26；AC-BR-06；AC-BR-09；AC-BR-16；AC-BR-20；AC-BR-23。

**前置：** Story 4.3、Story 4.4、Story 4.5、Story 4.7、Story 2.10、Story 3.12。

**范围：** 汇集既有logs／stage事件和公共错误合同，补齐缺失生产责任与只读查询；不新增分析平台、付费账单推断或Task／MVG完成状态。

**Acceptance Criteria:**

**AC-1**

**Given** 规划、Task生成、局部验证、Flow验证或返工已有阶段事件，
**When** 按operation／run、scope／Flow、stage、attempt与event身份汇集，
**Then** 可回到每次执行者及原始证据，显示已观察活动耗时、实际dispatch、构建预热／重复测试、复用来源／理由、返回阶段及终止原因，
**And** 同event只计一次，重复尝试仍各保原事件；不能把协调器reservation、worker投影和同一dispatch当多笔调用。

**AC-2**

**Given** 暂停墙钟、模型估算、预算预留或无法观察的数值存在，
**When** 展示耗时或费用相关信息，
**Then** 可观察值与unknown分开，暂停墙钟不称活动耗时，预留与实测费用／账单分开，
**And** 不伪造缺基线对比、不承诺提速／降成本、两小时、固定Task数或工时门槛。

**AC-3**

**Given** 不同入口遇到缺治理、未知版本、引用损坏、漂移、pending、冲突、预算或语义问题，
**When** 输出或汇总错误，
**Then** 复用唯一reason_code枚举和公共六字段，保责任stage、实体、expected／actual及恢复定位，不适用显式null，
**And** 错误类别不被页面文案重新解释；执行故障不转换为语义finding或反过来掩盖budget。

**AC-4**

**Given** 同源采纳复用、应用no-op或测试共享引用，
**When** 核对三类复用的观测，
**Then** 分别标明规划稳定／采纳、应用幂等及运行证据复用身份和决定，不以一种通过证明另两种，
**And** 观测只从原日志／receipt派生，不刷新旧PASS时间或重建全局Knowledge作为修复。

**AC-5**

**Given** 本次没有可比A/B基线或发现无进展／重复执行，
**When** 查询过程报告，
**Then** 保留数据缺口、已有stop-loss及可定位返工原因，允许按同口径历史数据参考，
**And** 任何过程指标不抵消来源遗漏、成熟身份变化、少验义务、失败重分类或提前实现范围外Flow等退化。

### Story 4.9: 对齐全部生产者消费者与治理文档

As a 工作流维护者,
I want 按消费者矩阵核对实际入口、公共格式、Skill与文档是否都消费B合同,
So that 迁移不会停留在workflow.md说明或少数dispatcher适配。

Refs: FR-8；FR-9；FR-11；FR-12；FR-13；FR-14；FR-15；FR-16；FR-17；NFR-E-2；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-11；AR-1；AR-3；AR-5；AR-6；AR-16；AR-18（切换前覆盖部分）；AR-19；AR-26；AR-28；AC-BR-08；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-19；AC-BR-21。

**前置：** Story 4.5、Story 4.6、Story 4.7、Story 4.8、Story 3.12。

**范围：** 以Epic1盘点矩阵核对并补齐真实遗漏适配及owning文档／测试，不把已批准Story文本当实施证据；默认入口切换及A最终退出仍归Epic5。

**Acceptance Criteria:**

**AC-1**

**Given** 前期消费者矩阵和本批实现可定位，
**When** 逐项核对来源／Ledger／审计、planner、业务视图／三联、4–7、_mvg_obligations、CLI／direct／route／resume／页面、manifest／runner／milestone、Knowledge，
**Then** 每项列实际读写路径、公共schema／resolver／提交调用、有效输入与成功／失败证据及剩余项，
**And** 不能只依据修改workflow.md、测试dispatcher或一份总摘要宣告覆盖；共享Task和底层直接入口不能漏。

**AC-2**

**Given** 新增格式、旧格式、合法缺失、损坏或未知版本输入用于各消费者，
**When** 核对实际处理，
**Then** 各入口依同一版本合同区分并拒绝不明依据，B不能删origin／trace／manifest降回legacy，合法非Flow仍需理由与其他验证，
**And** 旧A仅在明确冻结边界运行，格式迁移有输入／输出、身份保留和恢复说明，未满足项明确阻断切换。

**AC-3**

**Given** AGENTS、workflow、public entrypoints、项目Skill及示例描述实际流程，
**When** 更新并校验链接／参数／阶段，
**Then** 指向已实现同一入口，保3A／3B／3C与4–7边界、模型恢复／journal恢复、Task／Flow／累计完成及发布身份区别，
**And** Chapter顺序／治理通过有效ADR演进，Proposed不能当Accepted；两份ADR-0038使用完整文件名，不改现有质量／分支保护。

**AC-4**

**Given** 最小采纳、绑定、策略、receipt及迁移说明需要跨session／clone消费，
**When** 审阅版本管理与证据布局，
**Then** 最小治理依据入版本管理，原始journal／调用／运行证据留logs，clone仍通过receipt／catalog／当前文件验证一致性，
**And** 不强制全部logs提交，不把logs／备份／历史纳入普通全局语义来源，不复制公共codec／私有解析器。

**AC-5**

**Given** 所有本批消费者结果汇总，
**When** 形成切换前覆盖报告，
**Then** 明确已通过、阻断及不适用依据并可重建单项证据，本批通用B功能可用且不依赖奖励特定改造，
**And** 报告不自动切新增默认B／撤A兼容，真正奖励试点与切换授权条件仍留Epic5；只读报告不写第二状态机。

### Story 4.10: 在Windows故障与共享变更下核对端到端结论

As a 准备交付B路线的维护者,
I want 用受控失败及共享影响场景核对真实消费者、恢复和完成声明,
So that 能在奖励试点前发现混合提交、旁路和错误通过，而不靠扩大完成声明掩盖。

Refs: FR-8；FR-9；FR-11；FR-12；FR-13；FR-14；FR-15；FR-16；FR-17；NFR-E-1；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-10；NFR-E-11；AR-5；AR-6；AR-8；AR-9；AR-10；AR-11；AR-13；AR-16；AR-17；AR-21；AR-24；AR-25；AR-26；AR-28；AC-BR-05；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-09；AC-BR-10；AC-BR-11；AC-BR-12；AC-BR-13；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-17；AC-BR-19；AC-BR-20；AC-BR-21；AC-BR-22；AC-BR-23。

**前置：** Story 4.1、Story 4.2、Story 4.3、Story 4.4、Story 4.5、Story 4.6、Story 4.7、Story 4.8、Story 4.9。

**范围：** 复用Epic2／3故障工具和既有框架验证跨消费者合同并修复发现的本范围缺陷，记录真实Windows能力边界；不把协议fixtures称作奖励玩法验收，不执行Epic5入口切换。

**Acceptance Criteria:**

**AC-1**

**Given** 真实Windows环境可控制文件占用、进程退出／重启、发布前后故障和状态并发，
**When** 注入prepare／reserve／apply／verify／publish／recover关键失败点并调用真实读／执行入口，
**Then** 结果为完整且可验证提交或明确阻断，部分写／已发布待清pending／损坏journal均不被混合消费，
**And** 后编辑及当前Task状态保留，同ID异内容拒绝；仅模拟OS异常不能宣称验证Windows占用／持久化，未测边界明确列出。

**AC-2**

**Given** 共享Task跨scope加入新plan，来源／规则漂移或旧pending scope未知，
**When** 经CLI／direct／resume／route／页面与正式读取路径核对，
**Then** 当前和新增scope保护及适用集合完整，相关readiness／证据失效，旧pending原合同恢复；不相关scope可继续，
**And** 不靠删除marker／origin／manifest或增加伪N/A绕过，集成owner与合法非Flow的正反例均符合真实责任。

**AC-3**

**Given** 共享变更影响旧Flow A与范围外未实现B，随后B改入本次范围，
**When** 串联影响、scope、实际runner与收尾，
**Then** A失败／无法启动须修后完整回归；B先保未来责任不宣通过，入本次后未完明确阻断，声明范围与实际覆盖一致，
**And** 旧失败不能重分类或用旧manifest消除，本次没有被迫提前实现最初范围外Flow。

**AC-4**

**Given** 同测试被多Flow引用或两个结果来自不同snapshot，另有空／跳过／方法调用报告，
**When** 核对共享结果及Flow／milestone结论，
**Then** 同条件证据可共享且状态隔离；不同snapshot不能拼累计通过，空／跳过／方法调用不冒充实际引擎输入或人工检查，
**And** partial／critical／单Flow结果标真实范围，协议fake runner只记工作流适配证据，真实Godot义务仍须原始引擎证据。

**AC-5**

**Given** 页面、Knowledge及运行观测面对失败、epoch／reopen或恢复，
**When** 核对显示、诊断和发布指针，
**Then** 展示与正式链一致，撤销恢复资格不复活，preview／attempt不污染stable／main或canonical指针，原始日志可追溯，
**And** Chapter6／Review／Recovery无隐式全局refresh，预算／费用／耗时未知和实测分开，不用指标改善抵消失败。

**AC-6**

**Given** 前九个Story及本Story前五组验收已完成，
**When** 交接Epic5试点所需能力和剩余条件，
**Then** 提供可复查消费者覆盖、范围执行／证据、Windows故障结果、迁移说明与明确未满足项，通用B链路各功能可独立验收，
**And** 奖励生产适配、双路径真实Windows／Godot／C#证据、默认B切换与A退出仍待Epic5；当前本轮只起草Story未运行这些未来验收。

## Epic 5: 用奖励双路径证明B路线并有条件切换入口

玩家经同一生产命令领取／跳过奖励并按既有路由返回Map；维护者以无Task新规划及存量增量承接判断新增默认B切换，并按独立条件退出A写入兼容。主覆盖FR-18，其他FR／NFR／AR仍沿已确认库存及覆盖图承接。

沿用combat-reward-return、route-owned Reward、Map返回归属、候选顺序／RNG／存档及原生人工区域，不扩视觉重设计／玩法或全仓迁移。各Story只依赖此前能力，数量不预分配真实Task数或固定时长。

### Story 5.1: 固定奖励真实变更与存量复用边界

As a 奖励试点维护者,
I want 明确现有combat-reward-return的真实生产适配缺口及可复用成果,
So that 试点有业务意义，同时不扩大玩法范围或重建成熟任务。

Refs: FR-6；FR-14；FR-18；NFR-E-1；NFR-E-2；NFR-E-7；NFR-E-9；AR-4；AR-7；AR-14；AR-18；AC-BR-05；AC-BR-14；AC-BR-15；AC-BR-18。

**前置：** Story 4.10。

**范围：** 读取当前实际代码、M1 Overlay、契约、累计manifest与任务，形成可审阅真实Requirement变更及复用盘点；只记录，不预创该变更实施Task或修改现有玩法。

**Acceptance Criteria:**

**AC-1**

**Given** 当前仓库与既有combat-reward-return可定位，
**When** 盘点Reward生产命令／只读状态／C#适配与绑定，
**Then** 保存实际分支／输入身份、现有Requirement／Flow／Task／测试映射与真正需改变的责任，
**And** 固定Task refs [61,83,84,85,114,115,128]仅作盘点对象，不是新Task清单或必须重跑／重建数量。

**AC-2**

**Given** 现有RewardScene.gd与Main中有ForTest字符串调用和内部状态读取，
**When** 确定所选替换边界，
**Then** 明确生产链将改用受治理生产命令、只读状态和必要C#场景适配，保现有领域owner和路由责任，
**And** 不单凭命名或现有接口依赖断言整个Flow已失败，不预先冻结未来API名／类名／节点路径。

**AC-3**

**Given** 真实业务链从战斗结果进入独立Reward再领取／跳过返回Map，
**When** 确认试点成功与失败范围，
**Then** 保combat-reward-return身份、route-owned Reward、Map返回归属、候选及顺序锁定、RNG／存档与人工场景区域，
**And** 不扩为Combat／Map全重构、全仓GDScript迁移、数值／玩法／美术重设计或第二个同义Flow。

**AC-4**

**Given** 所选新增／变更Requirement尚无专门实施Task／readiness，
**When** 保存规划前时点的可验证输入，
**Then** 明确真实变化范围及Task尚未生成的证明，旧Task／实现只辅助复用，
**And** 不删除成熟Task制造零Task外观，不先建假Task／witness再宣称先规划。

**AC-5**

**Given** 已有契约／Offer对象／奖励事件可复用，
**When** 形成公共边界变更提议，
**Then** 优先现有M1 Overlay及Core契约，只有确实新增或改变公共边界才列需更新项，
**And** 不因C#适配就机械新增DTO／事件／接口；最小定义版本化，原始盘点／审阅证据留logs。

### Story 5.2: 在无变更Task时正式采纳奖励规划

As a 奖励变更规划者,
I want 先于该变更实施Task正式采纳来源、逻辑Flow和四部分责任,
So that 以真实业务变化证明B路线前置规划成立。

Refs: FR-1；FR-2；FR-3；FR-4；FR-5；FR-7（前置逻辑层）；FR-13；FR-16；FR-18；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-5；NFR-E-6；NFR-E-10；AR-2；AR-4；AR-8；AR-9；AR-12；AR-14；AR-15；AR-22；AR-23；AC-BR-01；AC-BR-02；AC-BR-03；AC-BR-04；AC-BR-06；AC-BR-09；AC-BR-18；AC-BR-20。

**前置：** Story 5.1、Story 2.10、Story 4.7。

**范围：** 使用已实现B正式入口处理5.1真实来源变化，留下尚无该变更Task／readiness的正式采纳证据；尚不生成任务或实现游戏功能。 补充必需输入独立性与阶段合同正反例，不要求全仓无Task。

**Acceptance Criteria:**

**AC-1**

**Given** 5.1变更范围尚无实施Task／readiness且当前累计来源有效，
**When** 执行3A完整记账和独立来源审计，
**Then** 真实奖励变化、既有约束及必要交接均有可定位Requirement／验收意图或累计去向，遗漏和冲突按原合同处理，
**And** 完整范围不受首轮Task／Flow引用裁剪，不把已记账缺口当满足。

**AC-2**

**Given** 来源审计有效而实际新适配／绑定尚未建立，
**When** 执行3B正式语义规划与独立admission，
**Then** 在同一combat-reward-return下明确领域命令／只读状态责任、C#适配、逻辑绑定、场景、成功／失败／取消／返回与验证目标，
**And** 合法循环、planned对象及Task尚不存在均按阶段合同处理；不靠draft／allow_unready或假接口过检。

**AC-3**

**Given** 规划和采纳审阅通过，
**When** 经共享服务发布采纳，
**Then** plan／policy／receipt／catalog可复验，保存采纳时未有变更Task的输入身份及时间顺序，Flow旧身份不变，
**And** 所需Task映射仅留给后续真实缺口承接，不造第二同义Flow，也不把采纳说成readiness或运行PASS。

**AC-4**

**Given** 同有效输入跨会话恢复或采纳请求重复，
**When** 执行公共复验／no-op，
**Then** 复用有效计划、身份和完成成果，不重新分配或重复施加；显式重规划有差异和身份对齐，
**And** 相关来源／规则变化及损坏／后编辑按公共规则阻断，预算与原proof不改写。

**AC-5**

**Given** 规划者从CLI或页面查看本次结果，
**When** 核对阶段、诊断与观测，
**Then** 两入口显示一致的已采纳范围／后续责任及恢复点，原始来源／审计／admission／操作证据可定位，
**And** 记录真实耗时／dispatch／复用与未知项，不用提速或成本下降证明成功；preview不推进canonical发布指针。

**AC-6**

**Given** 本次奖励适配变更范围无实施Task／Task readiness，其他3B必需依据有效，旧Task如有仅作可选复用上下文，
**When** 记录本次实际3B必需输入闭包，并在隔离样本核对相应阶段门禁的正反例，
**Then** 缺少可选Task／Task readiness上下文不成为拒绝正式前置阶段的理由，而缺来源、独立审计或该阶段必需治理依据仍阻断；本次真实采纳及独立admission proof绑定当次实际冻结输入，
**And** 零Task仅指本次变更范围，不清空真实Taskmaster或删除policy／catalog／origins制造通过；合同样本不替代真实采纳，也不挪用另一输入的历史proof。不要求模型两次输出相同或额外重跑完整付费模型链。

### Story 5.3: 以存量增量路径承接真实任务和实施绑定

As a 奖励功能实施者,
I want 在已采纳奖励计划下复用旧成果，只为真实新缺口生成或更新三联并完成4–5绑定,
So that 新规划和存量增量都能接入既有实施链，而不重复建设任务或重置历史。

Refs: FR-5；FR-6；FR-7；FR-8；FR-9；FR-10；FR-13；FR-14；FR-18；NFR-E-1；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-7；NFR-E-9；AR-4；AR-6；AR-7；AR-8；AR-10；AR-12；AR-14；AR-21；AR-22；AC-BR-01（采纳后任务部分）；AC-BR-04；AC-BR-05；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-14；AC-BR-15；AC-BR-18。

**前置：** Story 5.2、Story 3.12。

**范围：** 将同一真实变更从5.2采纳转为3C三联及Chapter4／5实施定义，分别保无Task前置与成熟Flow增量承接证明；不是重复执行同一delta或建立两套相互竞争的任务。

**Acceptance Criteria:**

**AC-1**

**Given** 5.2正式采纳与5.1成熟成果盘点仍有效，
**When** 审阅奖励真实缺口并编译业务视图，
**Then** 仅为必要命令／状态／适配／绑定／验证责任生成或复用真实Task，保旧ID／状态／历史与累计测试，
**And** 不固定Task数量，不机械四拆，不重建旧done或让旧done自动证明新增义务。

**AC-2**

**Given** 同一Flow含旧任务和新责任，Task可跨Flow共享，
**When** 发布三联、3C binding、origins及反向索引，
**Then** 保combat-reward-return与Requirement验证owner／路线成员键，完整适用plan集合一致，
**And** 两条路径分别可追溯：采纳前无变更Task、采纳后在成熟成果上增量承接；不靠同义Task／Flow或重复apply造证明。

**AC-3**

**Given** 进入Chapter4／5前需确定真实生产边界，
**When** 按现有Core契约和M1 Overlay细化，
**Then** 明确受控生产命令、只读状态、唯一状态owner、C#薄适配生命周期、原生资源绑定、真实输入及人工／测试责任，
**And** 仅确有公共变更才同步源码Contract、Overlay、EventType及contractRefs；Core／Contracts BCL-only，不冻结无依据新DTO。

**AC-4**

**Given** 必要对象仍planned、当前Task未done或仅有集成owner，
**When** 执行Chapter5及统一门禁，
**Then** 定义足够可实施／可测并有当前manifest或有效其他验证及共同readiness，按producer／consumer／owner责任判断，
**And** 不要求当前Task先done、不造业务API／实际节点，planned不当实现；相关未知／缺失／过期绑定阻断。

**AC-5**

**Given** 重复编译／中断恢复、当前状态推进或后编辑，
**When** 经公共服务复验，
**Then** 完整操作no-op不回写旧状态，未完成操作严查原始前像，变更映射、状态和累计义务保留，
**And** 所有生成／绑定均经审阅三联与共享提交，不直写tasks.json；输入／状态并发与失败证据留logs。

### Story 5.4: 实现奖励受控生产命令与只读状态边界

As a 奖励玩法调用者,
I want 通过真实生产命令领取／跳过并读取受限只读状态,
So that 玩家与自动验证走同一业务路径，不依赖可变内部状态或测试后门。

Refs: FR-7；FR-9；FR-11；FR-13；FR-18；NFR-E-1；NFR-E-2；NFR-E-6；NFR-E-7；NFR-E-9；AR-1；AR-12；AR-14；AC-BR-04；AC-BR-10；AC-BR-12；AC-BR-18。

**前置：** Story 5.3。

**范围：** 在已确定owner和现有规则上实现必要生产命令／只读边界，优先复用Core服务／契约；不做全Main／Combat／Map迁移。当前验收为命令与适用局部测试，不等待后续场景适配或宣告Flow完成。

**Acceptance Criteria:**

**AC-1**

**Given** 5.3实施定义和readiness有效，
**When** 经当前Task Chapter6实现所选生产命令，
**Then** 领取／跳过／返回责任沿唯一受控写入口和原状态owner，规则裁决不复制到UI或薄适配，
**And** 既有合法结果／拒绝／错误语义保留，调用边界不新增并行状态真相；代码不含Godot引用的Core／Contracts保持BCL-only。

**AC-2**

**Given** 展示或自动验证需要奖励候选／选择状态，
**When** 读取生产只读状态，
**Then** 提供已审阅范围内的受限状态／结果，不可借返回引用或任意字典写入改领域状态，
**And** fixture初始化和玩家动作接口分离，生产调用不以ForTest名／内部可变字段作为受认可后门；方法名由既有契约治理确定。

**AC-3**

**Given** 同一选择重复提交、非法选择、无有效奖励context或已完成责任被重试，
**When** 调用真实生产入口，
**Then** 按既有幂等／拒绝规则处理，不重复发奖励或写回，不以失败半提交冒成功，
**And** 候选集合及顺序、不变量、路由归属和纯UI不推进RNG的约束继续成立；不新增奖励机制。

**AC-4**

**Given** 原有OfferLockSnapshot／OfferProvenance及奖励事件可复用，
**When** 实现接口及必要测试，
**Then** 引用现有契约并验证对应状态变化和失败行为，确有公共变更才按5.3同步权威文件，
**And** 不为适配拆分机械新建DTO／事件，不删除稳定测试引用；xUnit和适用适配测试遵守P1／Needs Fix。

**AC-5**

**Given** 命令层局部测试与评审通过或发现定义不足，
**When** 完成当前Task交接，
**Then** 保存实际生产入口、局部测试／编译及未实现绑定责任的证据，定义缺口返回owning stage，
**And** 局部PASS不称真实引擎输入或Flow通过，不隐式重规划／全局Knowledge refresh，阶段观测可追溯。

### Story 5.5: 将原生Reward场景接入必要C#薄适配

As a 领取奖励的玩家,
I want 在既有独立Reward场景通过实际控件领取或跳过，并沿正确路由返回Map,
So that 生产UI使用同一受控命令和只读状态，场景仍可原生编辑。

Refs: FR-7；FR-9；FR-10；FR-11；FR-14；FR-18；NFR-E-1；NFR-E-2；NFR-E-6；NFR-E-7；NFR-E-9；AR-12；AR-13；AR-14；AC-BR-03；AC-BR-04；AC-BR-10；AC-BR-12；AC-BR-13；AC-BR-18。

**前置：** Story 5.4。

**范围：** 仅迁移所选Reward输入／展示／绑定职责到必要C#薄适配，接现有原生Reward.tscn；不重做美术布局，不将Reward塞入Combat HUD或仅harness。

**Acceptance Criteria:**

**AC-1**

**Given** 既有战斗结果按真实路由进入Reward，
**When** 初始化C#薄适配并接控件／资源，
**Then** Reward保持独立route-owned场景，实际领取／跳过控件调用5.4同一生产命令并按真实结果展示／返回Map，
**And** 适配只转换输入、读取状态和反馈，不复制领域裁决，不直接写内部状态或经旧ForTest字符串调用冒生产边界。

**AC-2**

**Given** 场景包含原生布局、素材、动画和人工制作区域，
**When** 更新脚本／信号／对象绑定，
**Then** 保可编辑原生场景与非目标人工区域，只改必要适配和绑定，并明确生命周期／类型／资源责任，
**And** 不扩为全场景重做、全仓GDScript迁移或Combat／Map重构；只清理已确认无人消费的过期适配，不盲删仍有责任的旧调用。

**AC-3**

**Given** 绑定缺失／类型错配／生命周期结束或命令被业务拒绝，
**When** 执行适用检查和真实控件动作，
**Then** 缺连接导致对应检查／行为明确失败或阻断，合法拒绝显示真实结果而不假成功，
**And** 不靠造假节点或测试方法调用代替真实输入；静态接线、编译、场景方法、真实引擎输入分别保存等级。

**AC-4**

**Given** 玩家完成领取或跳过，并重复操作控件，
**When** 调用原生UI业务链，
**Then** 遵守原命令结果、返回归属与本地重复提交保护，必要反馈与待处理状态明确，
**And** 不重新抽候选、推进UI专用RNG或重复写回；持久Continue跨重启责任由5.6集成，不影响当前会话控件可独立验收。

**AC-5**

**Given** 适配及绑定验收完成，
**When** 经Chapter6与目标UI交接保存证据，
**Then** 当前Task映射／契约／场景资源和实际测试可回链，Chapter7只需收口真实剩余义务，
**And** 不重复建同义Task或说全Flow／累计通过，不降低质量底线；保未来真实整合取证责任。

### Story 5.6: 使奖励重入与Continue沿既有存档边界恢复

As a 中断后继续游戏的玩家,
I want 在奖励场景重入或Continue后看到相同候选与顺序，并保持合法路由和一次性结果,
So that 新适配不会引入重抽、重复发奖或错误存档边界。

Refs: FR-7；FR-9；FR-11；FR-13；FR-14；FR-18；NFR-E-1；NFR-E-2；NFR-E-6；NFR-E-7；NFR-E-9；AR-12；AR-13；AR-14；AC-BR-06；AC-BR-09；AC-BR-12；AC-BR-14；AC-BR-18。

**前置：** Story 5.4、Story 5.5。

**范围：** 将新命令／只读状态和C#适配生命周期接既有奖励／存档／路由恢复，按ADR-0032回归；复用已正确实现的存档逻辑，不增战斗中间存档或改全游戏保存架构。

**Acceptance Criteria:**

**AC-1**

**Given** 奖励候选首次生成后已有稳定ID／展示顺序／provenance及原存档边界，
**When** 退出重进或从真实Continue入口恢复，
**Then** 重建适配引用并读取同一受控状态，候选集合与顺序不变，允许原规则内重新选择但不重抽／重滚，
**And** UI展示／焦点／动画等纯UI行为不推进RNG，原run／combat／event／loot边界不改变。

**AC-2**

**Given** 领取／跳过过程中发生重复请求、重入或完成后Continue，
**When** 沿同一生产命令处理，
**Then** 不重复发奖或重复写回，实际结果及route boundary一致，可按既有拒绝／幂等语义解释，
**And** 不依靠可变内部字典恢复第二套状态，C#适配销毁／重建不获得新的奖励context权限。

**AC-3**

**Given** 战斗中断、奖励返回Map或保存失败，
**When** 消费原存档／路由合同，
**Then** 战斗仍只恢复战斗初始状态，Reward保持route-owned、返回Map归属正确，原保存失败保上一有效autosave，
**And** 不新增战斗中间态保存，不因本试点改变Combat／Map所有权或玩法规则。

**AC-4**

**Given** 存档损坏／不兼容或迁移失败，
**When** 通过真实Continue入口恢复，
**Then** 沿原完整性／迁移门禁阻断并提供错误及原始证据，不失败写回或伪成功，
**And** 不为拿绿关闭既有安全／迁移测试；正常与反例原始证据区分真实引擎动作和fixture设置。

**AC-5**

**Given** 上述恢复行为及已有稳定测试仍适用，
**When** 执行目标局部／集成回归并交接，
**Then** 复用现有Offer／save测试引用，新增仅针对真实缺口；当前输入／测试身份／环境及快照可回链，
**And** 不将不同快照局部报告拼成最终累计通过，未验人工／Flow责任仍列明，观测不设提速目标。

### Story 5.7: 以Windows真实输入完成奖励双路径取证

As a 奖励试点验收者,
I want 核对无Task前置采纳与成熟Flow增量承接的完整证据，并验证真实奖励链路,
So that 路线成立有实际Windows／Godot／C#证明，而非图或schema通过。

Refs: FR-1；FR-2；FR-3；FR-4；FR-5；FR-6；FR-7；FR-8；FR-9；FR-10；FR-11；FR-12；FR-13；FR-14；FR-15；FR-16；FR-17；FR-18；NFR-E-1；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-10；NFR-E-11；AR-4；AR-6；AR-8；AR-9；AR-10；AR-11；AR-12；AR-13；AR-14；AR-15；AR-16；AR-17；AR-18；AR-25；AR-26；AR-28；AC-BR-01；AC-BR-02；AC-BR-03；AC-BR-04；AC-BR-05；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-09；AC-BR-10；AC-BR-11；AC-BR-12；AC-BR-13；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-17；AC-BR-18；AC-BR-19；AC-BR-20；AC-BR-21；AC-BR-22；AC-BR-23。

**前置：** Story 5.1、Story 5.2、Story 5.3、Story 5.4、Story 5.5、Story 5.6、Story 4.10。

**范围：** 按现有Chapter6／目标7／正式MVG与范围执行进行真实试点验收，原始23项工作流AC按适用范围逐项定位；不为两路径制造新玩法／同义Flow／重复Task，不自动切换默认入口。 证据对照区分准备、输入方式、业务结果和环境，保已采纳的真实运行及人工义务，不新增统一OS输入自动化。

**Acceptance Criteria:**

**AC-1**

**Given** 目标Windows环境具当前Godot.NET.Sdk4.5.1／C#及仓库SDK策略，
**When** 执行真实奖励输入链，
**Then** 从战斗结果经route-owned Reward领取或跳过到Map，玩家和自动验证共用生产命令，C#适配／绑定实际参与，
**And** 记录实际OS／SDK／引擎版本、代码／资源与整合snapshot、输入动作、正式receipt／inventory及原始结果；静态／method／fixture不能冒真实输入。

**AC-2**

**Given** 5.2规划前时点和5.3存量增量承接均有真实证据，
**When** 核对两条路径链路，
**Then** 分别证明变更Task／readiness不存在时完成正式采纳，以及成熟Flow／Task／累计义务上的增量承接，再沿三联→4／5→单Task6→适用7→Flow义务串联，
**And** 保同一Flow和成熟ID／状态／历史，不靠重复apply或复制同义Task证明两条路径；旧done不覆盖新增责任。

**AC-3**

**Given** 目标UI和Flow收尾需要运行／人工检查，
**When** 复用有效Chapter6证据并执行目标Chapter7及全部必需义务，
**Then** 领取／跳过、重复提交、候选顺序、重入／Continue、必要断绑定与失败反馈均有对应当前证据，视觉／手感人工义务独立保留，
**And** 空、跳过、planned／仅schema或关系图不算运行通过，局部通过不推Flow完成；人工未完成保持阻断。

**AC-4**

**Given** 奖励共享变更影响其他旧Flow与范围外未来义务，
**When** 使用当前VerificationScope和实际执行回执，
**Then** 既有必需回归完整执行且失败须修，本次新增未完阻断，未来责任保留不宣通过；声明／实际／未运行及人工覆盖一致，
**And** 相同有效同snapshot证据可共享并隔离状态；单奖励Flow不得称整个里程碑full-MVG，累计声明另需全部累计同snapshot。

**AC-5**

**Given** 原始AC-BR-01–23含通用反例或对奖励路径不直接适用的治理项，
**When** 对照前四Epic证据与本试点实测，
**Then** 逐项列来源、适用范围、实际正反例或有效已完成证据、限制和未满足项，缺源／漂移／旧pending／后编辑／未知版本等按真实入口结果核对，
**And** 不以一句N/A、历史302项脚本测试或假runner总体通过替代当前必需证明，不偷换阶段完成与游戏运行。

**AC-6**

**Given** 试点结果汇总，
**When** 形成切换前审阅包，
**Then** 保双路径身份、阶段耗时／实际调用／复用／重复与返工、质量／回归结果、剩余责任及可恢复定位，
**And** 不设提速／成本下降门槛，不推canonical／main发布或自动切B；未通过则阻断默认切换并按owning stage修复。

**AC-7**

**Given** 两条规划／任务路径、前期有效机制proof和本次奖励运行／人工证据均可定位，
**When** 按当前义务制作准备方式、实际输入方式、生产命令／观察结果、运行环境、相关输入／snapshot及原始报告的证据对照，
**Then** 分别标明规划稳定、文件应用幂等和奖励业务幂等的证明，并区分fixture准备、结构／编译／静态接线、场景方法、真实引擎action、确有覆盖的鼠标／OS输入及人工检查；Windows环境本身不证明OS输入，
**And** fixture可准备合法Reward起点，但不能代替当前manifest／Flow必需交接；适用视觉／手感等人工义务保留，未完阻断。未覆盖的输入方式如实标明，不新增统一OS鼠标自动化或完整Combat自动化；通用机制证据仅按其有效性复用，不能冒充本次运行或拼接跨整合snapshot通过。

### Story 5.8: 在证据齐备后切换新增需求默认入口为B

As a 路线迁移维护者,
I want 依据真实试点和消费者一致性审阅，有条件切换新增需求默认入口,
So that 新增工作遵循先规划后Task，存量A仍有明确边界而非永久双真相。

Refs: FR-8；FR-9；FR-13；FR-14；FR-15；FR-16；FR-17；FR-18；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-7；NFR-E-8；NFR-E-10；NFR-E-11；AR-5；AR-6；AR-8；AR-16；AR-17；AR-18；AR-22；AR-23；AR-26；AR-28；AC-BR-07；AC-BR-08；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-18；AC-BR-19；AC-BR-20；AC-BR-21。

**前置：** Story 5.7、Story 4.9、Story 4.10。

**范围：** 通过受审阅策略operation执行仓库工作流默认路由切换，不等于推送Git、main发布或游戏发行。A最终写入兼容退出与新增默认B是不同条件，分别记录。 实际应用前须完成绑定本次候选的受控补偿演练并再次复验当前依据；事后收口不能补发事前应用资格。

**Acceptance Criteria:**

**AC-1**

**Given** 双路径奖励实测、Windows故障恢复、全部消费者及格式／文档一致性和有效治理审阅已齐，
**When** 复验默认B切换条件，
**Then** 只有全部当前必需条件满足才形成可应用策略请求，逐项绑定实际证据及当前输入／before身份，
**And** 仅文档／图／schema、部分试点或未验证Windows语义不能满足；任何未决必修／来源缺口均阻断。

**AC-2**

**Given** 当前A冻结输入需在实际切换时复验，
**When** 形成策略及来源边界，
**Then** 冻结可识别A ID、定义／来源scope与允许旧操作，完整origins／反向映射保B责任，相关变化按B承接，
**And** 合法status推进保留；不能用早期盘点直接覆盖当前状态，B对象不能删标识降A。

**AC-3**

**Given** 本次候选策略内容、目标scope与合同版本已冻结，已有通用恢复证据可复验，
**When** 在隔离工作区对本次候选执行受控切换／补偿演练，并核对正式应用资格，
**Then** 演练证据绑定规范化候选内容、scope及合同版本，验证补偿保留后编辑、当前Task状态与B来源；只复用经有效性核对的通用恢复证据，
**And** 演练失败或相关候选／合同变化不得实际切换；真实应用前须再次核对当前authority、目标前像和适用保护。演练receipt不是正式commit，不推进真实仓库catalog或发布指针，不要求全量重跑模型链。

**AC-4**

**Given** 策略请求经审阅且保护／当前authority有效，
**When** 使用公共journal／receipt／catalog提交，
**Then** 新增需求的CLI／页面／Skill及实际生产者默认走B，旧A仅在冻结有效边界实施／恢复，所有入口共用分类／门禁，
**And** 策略、origins及相关映射一致发布，scope占用／后编辑／中断冲突安全处理；重复同内容no-op。

**AC-5**

**Given** 切换后新增需求或B对象丢source／binding／manifest，或非Flow确无MVG责任，
**When** 经各真实入口执行，
**Then** 新增需求不回先定Task路线，缺B依据统一拒绝；合法非Flow按有效采纳／其他验证及实际影响处理，
**And** 标签、空字段或旧readiness不旁路；当前Task及integration owner不被加自身done条件。

**AC-6**

**Given** 切换策略已生效或恢复过程中读取状态，
**When** 核对操作面、文档和正式提交链，
**Then** 展示已切换范围与仍活跃A责任，CLI help／Skill／AGENTS／例子与实际一致，预览不推进canonical发布指针，
**And** 新默认B不宣称A已退役或整个游戏已验收；最小策略／迁移说明版本化，原始操作与运行证据留logs。

**AC-7**

**Given** 切换请求不满足条件、同ID异内容或有未知后编辑，
**When** 尝试应用或恢复，
**Then** 明确阻断并保原结果／证据，给reason_code及补齐／恢复定位，
**And** 不通过删除日志／pending、修改旧Task完成状态或弱化义务求切换，不执行未授权外部发布。

### Story 5.9: 核对A退出资格并交付统一门禁能力

As a 兼容范围维护者,
I want 依据当前权威核对A退出资格并准确区分允许、阻断及未知,
So that 可以验证退出门禁能力，同时把实际退役明确留给独立交付。

Refs: FR-13；FR-14；FR-17；NFR-E-2；NFR-E-4；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-11；AR-5；AR-7；AR-8；AR-17；AR-18；AR-22；AR-23；AR-28；AC-BR-07；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-19。

**前置：** Story 5.8、Story 4.9。

**范围：** 实现并验证只读退出资格核对及供受管退出操作调用的统一门禁，不在本Story实际撤权或删除源码。门禁正反例可独立验收；实际退役由Story5.10承接，条件未成熟时5.10保持blocked。

**Acceptance Criteria:**

**AC-1**

**Given** 当前冻结A边界、真实Task／来源及受治理迁入证据可读取，
**When** 核对退出资格，
**Then** 从当前Taskmaster与已提交依据列出全部活跃A，核对完成／迁入、必要恢复／迁移反例、相关未决操作及入口／文档一致性，
**And** Task done不证明新增B义务；未知／损坏不是零活跃，不靠修改status、删除trace／任务或来源标识清空名单。

**AC-2**

**Given** 仍有活跃A未完成／未迁入，或依据未知／损坏、相关pending未消歧，
**When** 运行退出门禁，
**Then** 返回阻断并定位每项未满足条件、责任和后续治理入口，原A仅沿冻结有效边界继续，
**And** 门禁本身可被验证，但实际撤权不得执行；不强迫范围外未来Flow提前实现，不把默认B成功当A已退出。

**AC-3**

**Given** 全部当前退出条件真实满足且可验证，
**When** 运行统一资格检查，
**Then** 返回绑定当前输入／政策与依据身份的允许结果，供受管写者在实际应用边界再次核对，
**And** 资格结果不是撤权receipt或代码清理证明，不直接修改policy／catalog／origins、Task状态或旧源码。

**AC-4**

**Given** 先前允许结果之后出现来源／定义／迁入／pending等相关漂移，
**When** 重新消费资格结果，
**Then** 门禁识别过期并要求重验，相关scope无法保护或条件不能证明时阻断，
**And** 不使用旧缓存、历史列表或刷新时间戳授权实际退出；诊断沿公共reason_code及原始定位。

**AC-5**

**Given** 退出资格在允许、阻断和未知样本验证通过，
**When** 验收本Story并交接，
**Then** 可以仅报告退出门禁能力通过，并把当前实际资格及剩余A责任交给5.10，
**And** fixture允许／阻断不等于真实仓库已撤权／退役，不把5.10未完或blocked从Epic完成声明中移除。

### Story 5.10: 在条件成熟后实际撤权并清理A写入兼容

As a 兼容范围维护者,
I want 在真实退出条件满足后撤除旧A写权限和无用写入代码，同时保留历史读取,
So that A的实际退役有独立完成证据，门禁通过不能替代退役行动。

Refs: FR-13；FR-14；FR-17；NFR-E-2；NFR-E-4；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-11；AR-5；AR-7；AR-8；AR-17；AR-18；AR-22；AR-23；AR-28；AC-BR-07；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-19。

**前置：** Story 5.8、Story 5.9、Story 4.9。

**范围：** 执行有真实前置条件的实际退役。策略／路由撤权使用受审阅治理operation；旧代码／适配清理按正常开发、评审、测试及版本交付完成，journal不承担任意源码删除。条件未满足时本Story保持blocked；既有新增默认B切换不以本Story已完成为前置。

**Acceptance Criteria:**

**AC-1**

**Given** 5.9门禁可用且本次真实活跃A均完成或经治理迁入，相关恢复／迁移反例及入口一致性满足，
**When** 在实际撤权前复验当前依据与保护条件，
**Then** 冻结本次审阅、政策／authority、目标前像及完整适用scope，证明没有未消歧的相关旧写入／恢复责任，
**And** 不以fixture、历史盘点或旧允许缓存代替当前资格；未知或保护不可取得即停止。

**AC-2**

**Given** 活跃A未完成／未迁入或真实退出依据不明，
**When** 尝试推进本Story，
**Then** 保持blocked并列出未满足条件及对应责任，保冻结有效A的有界实施／恢复，
**And** 不改Task status凑退出，不提前实现范围外Flow，不撤掉仍有合法消费者的兼容；新增默认B可按其自身有效条件维持。

**AC-3**

**Given** 实际资格与审阅请求有效，
**When** 通过公共提交服务撤除A新规划／写权限，
**Then** 政策／路由变更经journal、最小receipt和catalog一致发布，各真实写入口以撤权原因拒绝A写操作，
**And** 策略操作不删除源码，B来源、成熟ID／状态／历史和累计基线保留；不存在删除标识或换入口旁路。

**AC-4**

**Given** A写权限已实际撤除且旧写入入口／适配已无合法消费者，
**When** 通过正常开发流程清理旧代码并更新CLI／Skill／路由／示例，
**Then** 清理变更经代码审阅及相应测试／版本交付，历史只读解释与原始证据仍可定位，真实旧写路径不再可用，
**And** 不把journal扩为源码删除器，不删除正式采纳／Task历史／累计测试或仍必要的历史读者；不保无用写入兼容层。

**AC-5**

**Given** 撤权应用中断、发生后编辑或完成操作重复，
**When** 恢复治理操作并核对清理版本，
**Then** 治理提交按当前前后像与receipt恢复或no-op，未知冲突停止；代码清理状态由其真实版本／测试证明，
**And** 不还原旧before覆盖后编辑或当前Task进度，不将策略补偿等同旧代码自动恢复。

**AC-6**

**Given** 需要对外报告本Story或A退出完成，
**When** 核对实际撤权、代码清理和历史读取证据，
**Then** 只有三者均真实完成且当前依据有效才可报告5.10完成及A已退出；撤权后清理未完明确保本Story未完成，
**And** 5.9功能验收不能抵扣本Story，部分结果或待办不从总交付消失；原始操作／版本／测试证据可追溯，当前本轮不执行这些未来动作。

### Story 5.11: 以补偿回退反例收口迁移与完成声明

As a 路线迁移审阅者,
I want 在切换和回退时保留后编辑、当前状态与B来源，并准确交接未完成责任,
So that 路线变更可解释、可恢复，完成声明不会掩盖仍活跃A或未验义务。

Refs: FR-8；FR-9；FR-11；FR-12；FR-13；FR-14；FR-15；FR-16；FR-17；FR-18；NFR-E-2；NFR-E-3；NFR-E-4；NFR-E-6；NFR-E-7；NFR-E-8；NFR-E-9；NFR-E-10；NFR-E-11；AR-5；AR-6；AR-8；AR-9；AR-10；AR-11；AR-13；AR-14；AR-16；AR-17；AR-18；AR-21；AR-23；AR-24；AR-25；AR-26；AR-28；AC-BR-06；AC-BR-07；AC-BR-08；AC-BR-09；AC-BR-11；AC-BR-14；AC-BR-15；AC-BR-16；AC-BR-17；AC-BR-18；AC-BR-19；AC-BR-20；AC-BR-21；AC-BR-22；AC-BR-23。

**前置：** Story 5.7、Story 5.8、Story 5.9。

**范围：** 使用已实现5.9门禁及真实切换／补偿结果核对交接，不等待5.10实际退役完成。若A退役条件尚未成熟，必须如实保留5.10 blocked及有界A责任，不得据本Story收口宣布Epic整体全部完成；不直接还原历史文件或外部发布。

**Acceptance Criteria:**

**AC-1**

**Given** 切换／绑定操作需回退，当前已存在后续编辑／Task进度／B对象，
**When** 准备受审阅补偿operation，
**Then** 以当前前像、原副作用和适用scope审阅补偿，保历史、最新状态及B来源，
**And** 不能把旧before覆盖新内容，不能用旧默认开关把已归B对象降回A；当前B依据不足须阻断而非偷偷走legacy。

**AC-2**

**Given** 补偿遇到占用、中断、损坏证据或同ID异内容，
**When** 经公共服务应用／恢复，
**Then** 与原提交同样严格核对journal／receipt／catalog及当前authority，完整匹配no-op、冲突保全部证据，
**And** 不擦除原审计或重置候选预算／epoch／reopen资格，不伪造当前模型admission或运行通过。

**AC-3**

**Given** 补偿后重新读取Task／Flow／milestone或页面状态，
**When** 复验受影响定义与证据，
**Then** 相关变化精确使绑定／readiness／运行证据按各自合同失效，未受影响有效结果可复用；页面身份与原始链一致，
**And** 只在当前义务与同snapshot实际证据满足时报告对应范围通过，不拼跨快照、不把partial／单Flow叫累计full。

**AC-4**

**Given** 5.9门禁已实现且当前可允许或阻断，5.10可能完成或仍blocked，
**When** 核对迁移交接，
**Then** 分别引用默认B是否实际切换、A是否实际撤权、代码是否清理、历史读取是否有效、奖励Flow及累计未完责任，
**And** 5.9完成不等于5.10实际退役；5.10未满足时保blocked，本Story对账完成不授予Epic整体完成或隐藏未完退出责任。

**AC-5**

**Given** 所有适用交付条件和未满足项已核对，
**When** 形成最终迁移审阅与操作说明，
**Then** 最小定义／策略／迁移说明版本化，实际Windows／Godot／C#与原始AC-BR证据可追溯，耗时／调用／复用／返工及未知如实保留，
**And** 不承诺提速、不降低质量、不额外创建Task状态／数据库；本轮当前交付只是Epic／Story文档，未执行实施、真实切换、游戏验收或远端发布。
