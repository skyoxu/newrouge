# ADR-0040: B 路线阶段、记录权威与迁移启用治理

- Status: Accepted
- Date: 2026-11-03
- Scope: newrouge B route / Story 1.2
- Review: 2026-11-03，用户收到本文完整 Proposed 正文后，明确委托代理按建议持续完成整个 Story 并自行作内部技术判断；代理独立对照原需求、PRD／SPEC、架构及三份继承 ADR 后采纳本治理定义。授权来源和审阅证据见文末；不授予迁移启用权限。

## 背景与当前效力

B 路线将新增需求从先定 Task 演进为先明确来源、Requirement、Capability／Flow 或合法非 Flow 验证去向，正式采纳后再据真实实施缺口生成或复用 Task。本文落实已确认的阶段和权威边界，不重新选择架构。

| 层次 | 当前事实 | 后续准入 |
| --- | --- | --- |
| 治理定义 | 本文治理定义已按用户全文展示后的明确委托，经独立来源审阅采纳为 Accepted | 记录实际授权和审阅依据；后续语义变更仍须受治理审阅，不从 Accepted 推导实现或启用完成 |
| 实现交付 | 当前公共入口仍执行既有 A；本 Story 只产出治理文本及导航 | 后续 Story 交付共享记录、采纳、三联、绑定、统一门禁、执行器及操作面并留证 |
| 迁移启用 | 本文不冻结 A、不切换默认 B、不退出 A，也不执行回退 | 各操作分别满足下文条件并经受审阅治理操作实施；Accepted 本身也不等于已启用 |

Story 1.2 仅完成治理文本及导航，仍须通过本轮 Build 评审与定向验证；入口继续使用现行命令。ADR 状态读取、链接检查、BMAD 安装或本轮文档产出都不是授权来源，也不是运行验收证明。

## 阶段责任与交接

目标职责顺序为 **3A → 3B → 3C → 4 → 5 → 6 → 适用 7 → Flow／累计里程碑收尾**。3A／3B／3C 是 Chapter 3 的职责划分，不预设三个新公共命令；本 Story 不增加命令或修改 dispatcher。

| 阶段 | 责任及向后交接条件 | 可合法尚不存在的对象 |
| --- | --- | --- |
| 3A 来源与独立审计 | 注册完整累计来源与可定位 Ledger；逐块投影或解释去向，形成 Requirement／验收意图；从完整原始输入独立审计遗漏及冲突，不以首轮 Task／Flow 投影裁剪审计范围 | Task、readiness、真实场景和实际接口 |
| 3B Task 无关正式采纳 | 审阅 Capability／Flow 语义或有依据的非 Flow 验证去向；明确起终点、必要分支、状态所有者、交接、验证目标及适用四部分，持久采纳并保持稳定身份 | Task ID、Task readiness、完整实现符号及真实场景；不得用 draft 开关或假对象代替正式采纳 |
| 3C 任务承接 | 先盘点已有实现、成熟 Task、共享能力和验证责任，只为真实缺口形成经审阅业务视图 delta，再由既有编译路径写三联；需求、Acceptance、责任、依赖及验证去向一致 | 待实施对象及最终运行证据 |
| 4 实施定义与绑定 | 按适用范围细化 Overlay／Core 契约、生产命令、只读状态、唯一状态所有者、C# 薄适配、对象／资源类型、生命周期、场景与绑定责任；待建对象明确 planned | 标为 planned 且责任和以后检查已明确的对象 |
| 5 同源核对与 readiness | 复用仍有效的来源审计，继续核对当前 Task／Acceptance／ADR／Overlay／Contract／依赖／绑定及适用义务；最终 manifest 或合法其他验证依据与当前 readiness 属于同一有效 InputSet | 当前 Task 的 done 状态与运行通过证据 |
| 6 单 Task 实施 | 只按当前有效绑定定义实施当前 Task，执行适用 TDD、自检、评审、Needs Fix、pre-commit 与恢复；进入时不要求本 Task 已 done，不能形成自身完成前置 | 目标 Flow 其他未完成 Task 的结果 |
| 适用 7 目标 UI 闭环 | 只收口目标 backlog slice，复用 6 已验证的 UI；真正缺口走受治理 Task／readiness／6 路径，不创建同义任务 | 无 UI 义务时本阶段可不适用，须有依据 |
| Flow／累计收尾 | Flow 满足全部当前必需义务、受影响回归和适用人工检查；累计里程碑另以同一整合快照满足累计范围 | 范围外未来义务可留待实施，但必须登记且不能宣称通过 |

四部分指领域规则、C# 场景适配、绑定、场景。3B 说明逻辑责任，4–5 细化到可实施、可检查的定义；真实对象出现后补类型、编译、绑定及引擎检查。Flow 可跨多个 Capability，Task 与 Flow 可多对多；不强制一节点一 Task、四部分各一 Task或每 Task 改四层。不适用须说明理由，planned 不等于实现或运行通过。合法重入、重试和循环须明确必要可达性及退出边界，不承诺任意玩法必然终止。

合法非 Flow 仍经历来源记账、独立审计、采纳验证去向、真实 Task 及适用 4–6 检查。有已采纳理由、其他验证依据且确无 MVG 义务时不强造 Flow；实际影响既有 Flow 时仍绑定相应 manifest／回归。适用性未知、缺失、损坏或过期即阻断，Task 标签或 Agent 自报 N/A 不授权豁免。producer、consumer、integration-only owner 分别承接实际责任，治理／测试 owner 不必伪造运行时 API。

纯实现缺陷在不改采纳定义、契约、状态所有权、交接／绑定设计或验收义务时复用有效规划，仍做必要 Task 映射、readiness、自检和适用回归；触及这些定义则返回所属阶段形成受治理变更。Chapter 6 不凭 Knowledge 摘要重新解释需求，不隐式全局 refresh。

## 权威及最小规划记录的地位

| 对象 | 权威及限制 |
| --- | --- |
| 原始 GDD／PRD、批准变更、有效 ADR | 决定语义；Requirement 是保留来源回链的规范化投影，采纳记录不得凌驾来源 |
| 受治理采纳计划 | 保存从属特定来源／版本／审阅的规划决定和稳定身份；Capability 组织能力，不拥有 Task 状态或游戏完成状态 |
| Taskmaster 三联 | back／gameplay 是经审阅的业务视图，编译到 `.taskmaster/tasks/tasks.json`；后者是唯一任务状态权威；保留成熟 ID、状态、历史及严格 join，旧 done 不证明新增义务 |
| `Game.Core/Contracts/**` | 公共程序契约 SSoT，保持 BCL-only；测试、页面或规划摘要不替代源码契约 |
| 累计 MVG manifest | 管当前累计验证义务及 lineage；旧 Flow／test 仅能凭规格依据、显式 retire 和既有防削弱审阅移除或降义务，不是第二游戏状态机 |
| 原始运行报告与人工证据 | 只证明对应输入、manifest、测试、环境及整合快照下的实际结果；结构、静态接线、场景方法、真实引擎输入、人工视觉／手感分别取证 |
| Knowledge／topology／页面 | 可重建的关系、证据定位和派生展示；区分计划／实现／运行及 workspace preview／attempt／stable／main，预览不推进 current／last-known-good |

后续最小版本化记录位于 `docs/planning/b-route/`：`policy.v1.json` 保存受审阅切换边界与冻结 A 引用；`plans/` 保存不可变采纳修订；`bindings/` 保存各阶段 Task／四部分／验证绑定；`task-origins.v1.json` 保存 B 来源及完整适用 plan 集合；`commits/` 保存不可变最小提交 receipt；`catalog.v1.json` 最后发布一致提交的 scope／receipt。它们不存第二套 Task／MVG 完成状态，不新增规划数据库；游戏运行不依赖 Taskmaster、Knowledge 或 Chapter 记录。

上述六类记录、schema／codec、唯一写者、InputSet 及提交／锁协议沿用已确认的[共享记录与提交合同](../../_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md)，待后续交付，本 Story 不创建这些文件或私有替代格式。初始 3B 可无 Task 映射，不能以 Task／Chapter 5 witness 作为正式采纳 bootstrap 前置。

Requirement 的唯一权威验证处置／覆盖 owner、多 Flow 路线成员关系及共享证据去重分别保留现有 `requirement_verification`、`requirement_route_memberships`、`requirement_evidence` 键；`coverage_table` 继续是兼容投影，不因多路线重复计完成。

## 完整继承与 B 范围演进

两份 0038 必须按完整文件名引用；以下三份正文保持 Accepted，本文不整体 supersede 任一文件。

| 继承文件 | 保留及演进范围 |
| --- | --- |
| [docs/adr/ADR-0038-semantic-delivery-topology.md](ADR-0038-semantic-delivery-topology.md) | 保留原始来源语义、Taskmaster 状态、Capability 无 Task 完成语义、revision／hash、派生 Knowledge／Locator 及 Main／Workspace 边界。本文采纳后仅对其“without changing Chapter ordering”条款作 B 范围显式演进：前置 3A／3B 后由 3C 承接 Task；现行 A 的阶段与入口在迁移前继续有效 |
| [docs/adr/ADR-0038-mvg-candidate-admission.md](ADR-0038-mvg-candidate-admission.md) | 保留机器先行完整性、累计 delta、独立语义 admission、三个已准入候选后评选、有界修复／替换、不可变 prepared inputs、hash-bound proof、执行错误与语义问题区分及持久预算；不得以新采纳阶段绕过 |
| [docs/adr/ADR-0039-mvg-completed-capability-recovery.md](ADR-0039-mvg-completed-capability-recovery.md) | 保留完整单项 Capability 规范化内容哈希匹配、completed-only checkpoint、原冻结 proof 复验、当前依赖／累计 delta 兼容性及独立 adoption receipt；内容命中不等于证据有效 |

MVG 继续使用三个独立 OS worker；worker 不推进 selected，协调器拥有预算预留、父机器复验、评选和 `run.json` 的唯一原子提交点。新 MVG 执行不恢复未完成候选／修复／检查／评选中间态；稳定槽位预算不因重启或 lineage 重置，既有额度不增加。clear／epoch 在恢复、显示及发布路径继续核对，reopen 撤销受影响项及后继资格，保留历史。累计投影或 planning complete 不等于 runtime acceptance。

Capability 显式 `--resume-evidence`、MVG 完成项恢复和正式 apply journal 各按自身合同验证，不互相授予中间态复用许可。正式采纳通过自身 source／catalog／receipt 校验；本地 clear 不自动删除版本化正式采纳或累计 manifest，也不授权绕过已撤销 checkpoint 的当前恢复资格。

## 迁移操作与条件

五批按依赖和可观察交接推进，不预分配 Task ID／数量、时长或日程：先核对基线差异和存量保护／冻结输入；再交付无 Task 来源审计与正式采纳；再接三联和 4–7 绑定／readiness／恢复；再接真实执行范围、影响回归及全部操作面和反例；最后以奖励双路径真实证据支持新增需求默认 B。详见[迁移及试点合同](../../_bmad-output/specs/spec-newrouge-b-route/migration-and-pilot.md)。

| 操作 | 必须先成立的条件 | 操作边界 |
| --- | --- | --- |
| 固定／冻结 A 输入及允许范围 | 审阅当前与固定工作分支差异、来源／Task／规划／证据盘点，形成可复查成熟成果保护基准和可识别冻结清单；后续 Story 1.5 等证明有效性 | 清单和策略正式生效后，A 只在冻结且仍有效的定义／来源及原依据内实施／恢复；本 Story 不宣称冻结已完成 |
| 切新增需求默认 B | 后续共享记录、零 Task 正式采纳、三联／4–7、readiness、direct／CLI／resume／route／页面统一 gate、manifest 校验／真实执行器、Knowledge／Skill／路由／示例全部同步；Windows 占用／中断／重启、后编辑、漂移、缺来源／绑定、未知／损坏、非 Flow 及 owner 自依赖等反例通过；奖励双路径具有 Windows／Godot／C# 原始证据 | 经受审阅切换后新增需求走 B；存量相关需求或规划定义变化按受影响范围迁 B。默认 B 不要求全部 A 已退出，不以删 B 标识退回 legacy |
| 最终退出 A 写入兼容 | 所有活跃 A 已完成或受治理迁入 B；恢复／迁移反例及全部入口、文档一致性验证通过；退出资格有证据 | 才可受审阅撤除 A 新规划／写入兼容，保留历史只读追溯。策略撤权走治理操作，源码清理走正常开发／评审／测试，journal 不任意删除源码；5.10 条件未成则仍受阻且 Epic 5 不得 done |
| 补偿回退 | 审阅当前前像、原副作用、目标差异、适用范围、累计防削弱与恢复依据 | 使用新的补偿 operation；保留后编辑、历史、当前已完成 Task 状态和 B 来源。不直接还原旧 before 文件、不擦 journal／receipt、不删 origin／binding 或用旧格式绕过义务；5.11 可在其依赖满足后先于最终 A 退出收口 |

统一分类须先验证已提交 policy／catalog／origins 和完整反向关系；只有匹配冻结定义／来源且无当前 B 义务者才可按旧范围运行。B 来源、完整适用计划、readiness、manifest／其他验证任何必需依据缺失、损坏、未知或过期都拒绝；不能从“没有 trace”推断 genuine legacy。迁移启用前沿显式原入口执行当前 A，不把未交付 B gate 描述为现有行为。

多产物提交复用共享项目锁和 journal，绑定 operation 内容、authority 和 before／after，冲突时保留证据并停止；全部目标及 receipt 验证后才最后发布 catalog。单文件 replace、receipt 存在或 pending 消失不证明整体一致提交；B catalog 发布不替代 MVG 协调器的 selected 提交点。已发布同内容恢复为 no-op，同 ID 异内容冲突；未完成操作严格核对前像，不用旧状态覆盖后续 Task 进度。

Story 1.1 的盘点可以定位消费者；T108 历史报告缺失仍如实保留，不能补造、借旧 done 或以不可采纳 capture 认证正式保护基准。Story 1.5 须继续处理该历史证据限制。后续实施、恢复和启用均不能以本 Story 的治理文本替代证明。

## 验证、试点及不变约束

Task 自检、Flow 完成和累计里程碑分别判断。共享变化登记全部传递影响，区分既有必需回归、本次新增／未完义务、范围外未来责任；本次改坏旧 Flow 必须修复后回归，不能改列 future；本次未完阻断完成，范围外未来义务登记但不宣通过。累计通过绑定同一整合快照，不拼接不同快照结果。仅改变 recommend 排序不称选择性执行。

奖励双路径复用同一 `combat-reward-return`：一条在变更范围尚无 Task／readiness 时先正式采纳再承接真实缺口，另一条证明旧 Flow／Task 与累计测试的增量保护。只收敛所选生产命令、只读状态及必要 C# 薄适配／绑定；保留独立 route-owned Reward、返回 Map、候选与顺序锁定、既有存档／Continue／RNG 和原生布局／美术／动画人工区域。玩家与自动验证共用生产入口，fixture 隔离；不扩为全游戏迁移或新奖励玩法。

Windows-only、Godot 4.5.1、C#／net8.0、仓库 SDK 策略、BCL-only Core／Contracts、xUnit／GdUnit4、现有测试门禁、P1 必修底线、安全规则及分支保护保持有效。本 Story 不改程序、三联、Task 身份／状态／历史、质量阈值、默认路由或发布指针，不执行 Chapter 6、游戏测试、Windows CI、commit／push／PR／merge。仅 Story／Build spec／ADR 审阅及原始证据跟踪的已批准纳管限于 1.2 纯治理文本，不继承 1.1 例外，也不豁免后续真实实施。

本轮目标是路线改变。阶段耗时、调用、复用、重复测试及返工留可追溯观测，不增加提速、降成本、固定 Task 数量／时长等成功门槛。

## 来源与审阅依据

- [Story 1.2 与 AC-1–5](../../_bmad-output/planning-artifacts/b-route/epics.md)；[已批准 Build spec](../../_bmad-output/implementation-artifacts/b-route/spec-1-2-b-route-governance-and-stage-authority.md)；[Sprint 范围](../../_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md)。
- [SPEC](../../_bmad-output/specs/spec-newrouge-b-route/SPEC.md) 及其全部七份 companion：[阶段与权威合同](../../_bmad-output/specs/spec-newrouge-b-route/workflow-contract.md)、[验证与恢复合同](../../_bmad-output/specs/spec-newrouge-b-route/verification-contract.md)、[迁移与试点](../../_bmad-output/specs/spec-newrouge-b-route/migration-and-pilot.md)、[PRD addendum](../../_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/addendum.md)、[基线对照](../../_bmad-output/planning-artifacts/prds/prd-newrouge-b-route-2026-11-03/baseline-update.md)、[架构主干](../../_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/ARCHITECTURE-SPINE.md)、[共享记录与提交合同](../../_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md)。
- 2026-11-03，用户在完整 Proposed 正文展示后明确要求：“你可以按照给予的建议持续帮我完成整个story，现在是最高思考模型和深度，不必再问我，你可以自己和会话模型对话并帮我选择”。本次 Accepted 由代理按此明确委托作技术采纳，非先前 Build spec 批准的自动推论，也非虚构一次额外的人类投票。独立来源核对未确认实质冲突；原生 Build 三层评审及定向验证结果另留原始证据。授权原文、候选全文前像和审阅依据保存于 `logs/ci/2026-11-03/b-route-story-1-2-build/adoption-and-final-review-20261103T161146Z/`。机器检查通过不替代授权，Accepted 不代表 B 实现或启用。
