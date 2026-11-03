# newrouge B 路线工程约束与验收补充

## 固定来源与技术基线

原始输入为《newrouge B 路线工作流改造原始需求》，2026-11-03 修订，BR-01–BR-18 与 AC-BR-01–AC-BR-23 保持原身份。用户随后明确：本次是路线改变，不以提速为目标；保留过程成本、调用和复用记录，但不以成本下降或 A/B 速度优势作为验收门槛。以下旧源码引用保留原始核对历史，其共同固定根为：

`https://github.com/skyoxu/newrouge/blob/a8a363aa5f4ad09d5032731b0e7dfc5a17b8c89b/`

当前工作基线为 `fix/capability-synthesis-input-integrity` 的 `cd925bdcae4b61992320773497f7edb729aac244`。新增既有能力及语义澄清见同目录 `baseline-update.md`；下表保留的旧提交接入线索不代表当前分支缺少 worker、checkpoint 或完成项恢复。

`AGENTS.md` 是仓库路由入口；具体规则以相应有效 ADR、Base／Overlay、权威契约和 owning workflow 文档为准。旧固定提交及原本地 `8f93557d7f5f07b7931e3f4966a2dce04e458344` 均是历史身份；当前分支事实与行号由 `baseline-update.md` 及对应新基线源码确定。

技术约束沿用 Windows-only、Godot.NET.Sdk 4.5.1、`net8.0` 和仓库 `global.json` 的 .NET SDK 8.0.401／latestPatch 策略。Python 工具沿用仓库 `py -3` 入口，实际验证记录解释器和相关工具环境；本次不增加新的 Python patch 硬门槛或引擎升级。

官方适用性依据：[Godot 4.5.1 发布](https://godotengine.org/article/maintenance-release-godot-4-5-1/)、[Godot 4.5 C# 文档](https://docs.godotengine.org/en/4.5/tutorials/scripting/c_sharp/c_sharp_basics.html)、[SDK 8.0.401 记录](https://github.com/dotnet/core/blob/main/release-notes/8.0/8.0.8/8.0.401.md)。这些是仓库固定版本的存在性和适用性依据，不表示它们是当前最新版本。

## 继承的 ADR 与架构边界

ADR 索引仅作导航，以固定文件正文状态为准。`ADR-0021-csharp-domain-layer-architecture.md`、`ADR-0031-build-reproducibility-and-version-pinning.md` 实际为 Accepted；`ADR-0037-mvg-integration-evidence.md` 仍为 Proposed，不能作为已冻结 ADR 引用。两份不同 Accepted 文件均使用编号0038，必须引用完整文件名，不自行重编号。

| 适用来源（相对固定根） | 约束 |
| --- | --- |
| `docs/adr/ADR-0007-ports-adapters.md`、`ADR-0021-csharp-domain-layer-architecture.md` | 纯 C# Core，薄 Scenes／Adapters，外部能力通过端口消费；不在 UI 分叉领域裁决 |
| `docs/adr/ADR-0020-contract-location-standardization.md` | 公共契约 SSoT 为 `Game.Core/Contracts/**`，保持 BCL-only，测试不是契约来源 |
| `docs/adr/ADR-0028-event-usage-tiering.md`、`ADR-0030-core-threading-model.md` | Glue 将 UI 意图转换为 Core 调用；玩法事件及线程边界沿用既有规则，上层不直接改 Core 状态 |
| `docs/adr/ADR-0026-event-publish-failure-strategy.md`、`ADR-0029-error-handling-policy.md` | 事件失败不冒充成功；业务拒绝、调用违例、状态损坏、IO 故障分别处理，避免半提交 |
| `docs/adr/ADR-0032-save-resume-determinism.md` | 单槽 autosave、既有战斗保存边界、候选及顺序锁定、UI 不推进 RNG、坏档与迁移失败阻断 Continue |
| `docs/adr/ADR-0025-godot-test-strategy.md`、`ADR-0005-quality-gates.md` | Core xUnit、Godot GdUnit4 与既有质量门禁；静态检查不替代玩家输入、运行和人工义务 |
| `docs/adr/ADR-0035-repository-knowledge-control-plane.md` | Knowledge 仅派生定位；trusted-ref 发布与 workspace preview 分开，恢复不隐式重建全局知识 |
| `docs/adr/ADR-0038-semantic-delivery-topology.md` | Source Block／Requirement／Capability／typed edges 从属原始来源；Capability 无任务状态；Taskmaster 保留状态权威 |
| `docs/adr/ADR-0038-mvg-candidate-admission.md` | 候选 ranking 前完成完整性、累计 delta 和独立语义 admission；证明、调用及替换预算持久化 |
| `docs/adr/ADR-0039-mvg-completed-capability-recovery.md`（当前工作基线） | 已提交完成项恢复、原proof与新adoption、独立worker／协调提交、持续预算、epoch与reopen撤销；不恢复新执行的未完成模型中间态 |
| `docs/architecture/base/04-system-context-c4-event-flows-v2.md`、`05-data-models-and-storage-ports-v2.md`、`06-runtime-view-loops-state-machines-error-paths-v2.md`、`07-dev-build-and-gates-v2.md`、`08-crosscutting-and-feature-slices.base.md` | 继承边界、状态、端口和门禁结构；具体业务纵切留在 M1 Overlay，Base 不复制新 PRD 细节 |

`ADR-0027-ownership-write-entry.md` 的具体领域示例是城池／地块所有权，不把其 OwnedIds 等字段移植到奖励。奖励受控写入口与唯一状态所有者以现有 Core／Adapter、奖励契约及本次四部分要求约束。

现存派生 topology 不应整体升级为新需求语义权威。持久采纳记录保存特定来源、版本及审查下被采纳的规划决定；来源继续约束需求，Taskmaster 继续约束任务状态，Knowledge／topology 继续可重建。Chapter 顺序与采纳治理改变应在实施时新增或明确演进相应 ADR 条款，不能静默覆盖旧 ADR。

## 现存生产者与消费者接入依据

| 固定路径／证据 | 已存在行为与改造边界 |
| --- | --- |
| `workflow.md` Chapter3–7；`scripts/python/plan_capabilities.py` 的 `_readiness_summary`、`prepare`、`generate` | 来源 Ledger、独立审计、任务三联及 Task-ready Capability 规划已有基础；需要正式解除前置规划对 Task／readiness 的依赖 |
| `scripts/python/plan_mvg.py` 的正式 gate、Task owner、planned／existing_verified 和 rebind | 已支持未来入口描述，但正式语义规划仍有 Task／readiness 前置；不能描述为完全不支持未来实现，也不能以 draft 开关代替零 Task 正式规划 |
| `scripts/python/normalize_task_intents.py` | 成熟 Task 的身份及分组保护保留；新 Task 可以由已采纳 Flow 实施缺口指导 |
| `scripts/python/_mvg_obligations.py`、`dev_cli.py` 及直接／恢复调用方 | 现有“无匹配 trace”可被视为 current 的路径必须区分 genuine legacy、有效非 Flow 和缺失 B 绑定；所有真实入口一致执行 |
| `_planning_apply_journal.py` 及 planning pending／scope 机制 | 已有 before／after 身份、journal、roll-forward 与后编辑冲突检测；新采纳记录／Task 多产物须纳入一致可见性和恢复设计，不声称逐文件替换等于跨文件原子事务 |
| `docs/planning/semantic-topology/README.md`、`chapter6_semantic_publication.py` | 派生关系和显式语义 publication 已有身份边界；前者不能替代受治理采纳依据或运行证据 |
| `docs/workflows/mvg-integration-acceptance.md`、`_mvg_manifest.py`、MVG runner | recommend 当前改变优先级但仍执行选定 manifest 全部 required_tests；选择性执行若落地须改真实消费者并记录实际覆盖 |
| `scripts/python/milestone_incremental_handoff.py` | 已区分 `required_regressions`、`planned_tests`、人工义务和 baseline delta；保留三类责任及累计防削弱 |
| `_mvg_evidence_transport.py`、候选 admission／完整性模块 | 保留 complete-text 分片、hash／context／batch 身份、完整 source accounting、exact citation、receipt／proof 与持久预算，不退化成模型自由读文后直写任务 |
| Knowledge／规划页面、公共 CLI、项目 Skill、AGENTS 路由、阶段文档和示例 | 一起迁移阶段、门禁、格式与恢复入口；页面展示不能越权更新发布指针 |

Task 是证据 owner 时不自动产生运行时 API 义务；治理／集成 owner 不必各造可执行业务入口，数据契约不应为过检改造成 API。实施就绪和运行完成检查保持不同阶段，避免集成 owner 等待自身 done。

具体 schema、目录、字段、身份／指纹和传递影响算法、多产物提交可见性、公共 CLI 参数由 SPEC／Architecture 细化。`os.replace` 之类单文件原语不提供多产物整体一致提交；Windows 文件占用、失败点和中断恢复需要实际验证。

## 四部分的阶段完整性

以下约束内容与行为，不预设 JSON 字段、类名、节点路径或生成方式。Flow 层面完整说明，单 Task 可只承担适用部分；不适用须说明理由。

| 部分 | 拆 Task 前的最低内容 | Chapter6 前的细化与消费边界 |
| --- | --- | --- |
| 领域规则 | 业务结果、前后条件、状态所有者、允许动作、关键不变量及失败行为 | 命令、只读状态、契约、状态迁移及边界足供实现／测试；受控入口写状态，UI 不直接写内部状态 |
| C# 场景适配 | 输入如何提交动作、需要读取的状态、展示与反馈责任 | 适配边界、生命周期、依赖及反馈义务明确；新增／调整适配遵守 C# 目标，不复制领域判断 |
| 绑定关系 | 逻辑控件、命令、视图状态和主要交接的对应关系 | 对象／资源引用、类型和生命周期明确，待建对象标 planned；缺失、错配及失效连接可被检查 |
| 场景实现 | 进入／退出场景、必要视图、视觉资源与布局职责 | 场景／资源范围和受管部分明确，保留人工制作区域及 Godot 原生布局、美术、动画编辑空间 |

“玩法规则与绑定定义”是实现依据，不是已实现证明。前置规划可使用逻辑标识和 planned 对象；真实对象存在后补类型、编译、绑定及引擎检查，不创建假节点、假接口或假 Task 过检。一条 Flow 可跨多个 Capability，多个 Flow 可共享能力；共享依赖引用不改变 Requirement 的唯一权威验证处置／覆盖 owner；允许多 Flow 路线参与和去重共享证据，不重复计完成。

## 奖励试点的继承边界

固定 `docs/testing/mvg/m1-full.json` 已有 `combat-reward-return` 及 Task refs `[61,83,84,85,114,115,128]`、Requirement／Capability、交接和测试映射。这些是复用盘点对象，不是要求重建、重新编号或强制新增同数量 Task。

固定 `RewardScene.gd` 使用字符串调用 `ResolveRewardForTest`、`SkipRemainingRewardsForTest` 并读取 `_reward_selection_state_by_context`；`Reward.tscn` 挂接该 GDScript。该依赖是已选生产适配改造对象，不证明整条 Flow 现状失败。

既有 `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/` 的 Feature Slice、Contracts、Testing 页面规定：Reward 是独立 route-owned 场景，Combat／Event 后可进入并返回 Map，不能变为 Combat HUD 子面板或 harness-only 行为。候选集与顺序保持稳定；Continue 恢复真实 route boundary。只读状态用于展示／诊断，不是任意改业务状态的测试后门。

既有锁定／展示／选择／跳过事件、OfferLockSnapshot、OfferProvenance 优先复用。Task59–69 等 UI／适配任务不是自动新增契约骨架的理由；只有确实新增或改变公共 DTO、事件、命令接口、所有权快照，才同步源码、Overlay、EventType 及 task contractRefs。保持原生场景布局、素材、动画与人工制作边界。

## 改造验收场景

以下是工作流改造验收，不替代游戏 Requirement、Task Acceptance 或 Flow 运行测试。全部为未来实施的验收义务。

| 原始身份 | 必须可观察的结果 |
| --- | --- |
| AC-BR-01 | 零 Task／readiness 时完成正式规划采纳，随后生成真实 Task；无假对象 |
| AC-BR-02 | 独立审计发现首轮投影遗漏的交接，不因未被 Task／Flow 引用而跳过来源块 |
| AC-BR-03 | Flow 起终点、分支、所有权及四部分可解析回链；合法循环和有理由的不适用不误拒 |
| AC-BR-04 | 前置 Flow 到 Task／契约／测试绑定身份不变；planned 合法但不展示为落地或运行通过 |
| AC-BR-05 | 共享 Task 可支撑两个 Flow，不固定四拆；共享引用不重复 Requirement 覆盖归属 |
| AC-BR-06 | 同输入恢复／应用保身份、复用结果，不重复建任务或施加 delta；重规划有差异 |
| AC-BR-07 | 多产物中断可辨识已写结果并恢复；后编辑或同操作异内容不被覆盖或伪报成功 |
| AC-BR-08 | B 无效来源／依据／readiness／义务在 CLI、直接、恢复和页面入口均拒绝；删 manifest 或无依据 N/A 不绕过 |
| AC-BR-09 | 无关变化复用证据；相关来源／契约／规则变化使受影响证据失效；损坏不视为未变化 |
| AC-BR-10 | Task 局部自检独立执行，小节点不触发全 MVG；Flow 收尾全必需义务满足 |
| AC-BR-11 | 全影响登记，既有回归、本次新增、未来范围义务分开；未知扩大仍三分类，不将范围外 planned 当可执行回归；声明与实际证据一致 |
| AC-BR-12 | 关键 UI 真实引擎输入被验证；断开必要绑定使检查失败；空报告、跳过和静态连接不冒运行通过 |
| AC-BR-13 | Chapter7 复用 Chapter6 已验证 UI，不创建同义任务；真缺口按受治理路径补齐 |
| AC-BR-14 | 旧 ID／状态、无关定义及累计测试保留；无依据移除 Flow／test 或降义务的 delta 被拒绝 |
| AC-BR-15 | 历史 done 不证明新义务已过；旧 A 适用范围与 B 必需绑定可区分 |
| AC-BR-16 | 页面、CLI、Skill、文档和实际入口一致；Knowledge 分证据等级、分支与预览，不污染发布视图 |
| AC-BR-17 | 同条件共享构建／预热与测试证据，测试可变状态隔离；不拼跨快照累计通过 |
| AC-BR-18 | 真实奖励变更走通 B 全链路，并验证旧 Flow 增量承接；有对应 Windows／Godot／C# 原始证据 |
| AC-BR-19 | 新旧格式、合法缺失、损坏和未知版本行为可验；兼容不绕过 B 必需义务 |
| AC-BR-20 | 对可比切片记录阶段耗时、调用、复用、重复测试及修复成本，能够判断返工变化 |
| AC-BR-21 | 有效合法非 Flow Task 无 MVG 义务时可入实施而不造 Flow；删适用性或其他验证依据各入口拒绝；真实 Flow 影响仍绑定回归 |
| AC-BR-22 | 共享改动影响旧 Flow A 和范围外未实现 B：A 坏了也须修后完整回归；B 留影响和后续责任不宣通过；B 入本范围则未完阻断；不重分类绕过 |
| AC-BR-23 | 纯实现缺陷复用有效规划，经必要 Task／readiness／自检／回归完成，不全重跑3A／3B；触定义或契约返所属阶段 |

额外反例：仅承担集成测试的 owner 不因完成条件新增自依赖；producer／consumer／owner 原有适用差异继续有测试覆盖。

验证按有意义的 Task 单元、变更批次、目标 Flow 收尾与累计里程碑分别触发。影响分析可持续更新，回归可在有意义批次集中执行，不要求每次保存立即运行。共享变化不能强迫本次范围外未实现 Flow 提前实现，也不能遗漏其后续累计义务。
