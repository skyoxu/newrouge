---
GDD-ID: GDD-NEWROUGE-UI-FLOW-V1
Title: NewRouge v1 UI 接线型 GDD 动线
Status: Draft
Owner: skyo
Last Updated: 2026-04-20
Encoding: UTF-8
Applies-To:
  - docs/gdd/GDD-NEWROUGE-V1.md
  - docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
  - .taskmaster/tasks/tasks.json
  - .taskmaster/tasks/tasks_back.json
  - .taskmaster/tasks/tasks_gameplay.json
  - docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md
ADR-Refs:
  - ADR-0010
  - ADR-0011
  - ADR-0019
  - ADR-0025
  - ADR-0032
  - ADR-0033
Test-Refs:
  - Tests.Godot/tests/Integration/test_screen_navigation_flow.gd
  - Tests.Godot/tests/Integration/test_screen_navigator.gd
  - Tests.Godot/tests/Integration/test_map_navigation_state_transitions.gd
  - Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd
  - Tests.Godot/tests/Integration/test_reward_shop_event_resume_determinism.gd
  - Tests.Godot/tests/Tasks/test_task0014_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0015_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0016_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0017_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0018_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0019_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0020_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0021_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0022_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0023_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0026_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0033_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0034_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0039_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0041_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0042_acceptance.gd
  - Tests.Godot/tests/Tasks/test_task0045_acceptance.gd
  - Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs
  - Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs
  - Game.Core.Tests/Tasks/Task0017AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs
  - Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0021AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs
  - Game.Core.Tests/Tasks/Task0024AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0025AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0037AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0042AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0045AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0052AcceptanceTests.cs
---

# NewRouge v1 UI 接线型 GDD 动线

## 1. 范围与单一目标

本文档不是重写 PRD 或完整 GDD，而是补齐“已实现系统能力如何被玩家从 UI 触达”的接线设计。主目标是把任务三联、逐屏玩家规格、现有 GDD、Overlay 08 验收和当前测试证据串成一条可执行的 UI 集成路线。

当前口径：

- 用户已确认 `.taskmaster/tasks/tasks.json`、`.taskmaster/tasks/tasks_back.json`、`.taskmaster/tasks/tasks_gameplay.json` 对应任务视为完成。
- 任务文件内部分 `status` 仍可能滞后；本文档不修改任务状态，只基于已交付能力设计 UI 接线。
- 所有可见文本仍必须走 `Game.Godot/Translations/**`，脚本不得硬编码玩家可见文本。
- UI 只能调用受控命令入口，不得通过 hover、预览、刷新或打开面板推进 RNG 或改变确定性状态。
- `杀戮尖塔` 作为主要交互参考基准：用于约束信息密度、节点节奏、奖励/休整/地图的可读性与可玩闭环，不替代本仓 PRD、ADR、tasks 三联和 Overlay 的权威性。
- 已确定：`Reward` 与 `Rest` 采用独立资产场景，而不是嵌入式 surface。

## 1.1 主要参考基准：杀戮尖塔

本项目的 UI 接线和玩家动线以 `杀戮尖塔` 作为主要参考对象，但只参考“交互骨架”和“信息呈现原则”，不复制其内容资产、数值、具体文案或系统细节。

落到本仓时，参考原则如下：

- 主循环参考：主菜单进入 run，run 由地图节点推进，节点类型清楚区分，节点完成后回到地图。
- 信息层级参考：战斗 HUD 优先显示对当前决策最重要的信息，次要细节可折叠，不做过度面板化。
- 奖励参考：Reward 必须是独立、短流程、强确认的选择界面，强调“看一眼就能选”，而不是深层配置面板。
- 休整参考：Rest 必须是独立、低摩擦、强后果的 campfire 式决策点，强调恢复/升级/移除 Curse 的三岔选择。
- 地图参考：Map 必须先服务于路径决策和节点可达性，而不是装饰性视觉。
- 反馈参考：玩家每次点击后都能快速理解结果，不依赖阅读长日志才能继续。
- 边界差异：虽然参考 `杀戮尖塔`，但本仓仍必须遵守 ADR-0032、ADR-0033、现有任务验收和本仓翻译/日志/确定性规则。

### 1.2 与杀戮尖塔的具体对齐点

为避免“参考”停留在口号层，M1 UI 接线至少对齐以下几点：

- MainMenu：优先服务 New Run / Continue，不把设置、演示或调试入口放在主流程前面。
- Run Entry：真实入口必须尽快进入难度、角色和地图链路，而不是先进入 demo screen 或无关过渡 screen。
- Map：地图首先表达路径、节点类型和可达性；视觉层次服从路线选择，不反过来让路线信息埋没。
- Combat HUD：只保留当前决策真正需要的信息，避免把日志、说明、次要统计全部堆到主视野。
- Reward：奖励界面必须是独立短流程，默认支持“快速浏览后选择”，避免做成多层配置面板。
- Rest：休整界面必须是独立短流程，玩家进入后立即面对恢复/升级/移除 Curse 的核心决策。
- Event：事件页面必须先让玩家理解代价与收益，再做选择，不允许靠隐藏成本制造误解。
- Continue：继续游戏必须明确恢复边界和阻断原因，不允许玩家误以为能恢复战斗中间态。
- Feedback：点击后的反馈应在一个短周期内给出结果，不依赖展开工程化日志才能推进。

## 2. 玩家闭环主干

M1 的可玩闭环必须先保证玩家能无断点走完以下路径：

1. MainMenu：玩家选择 New Run 或 Continue。
2. Difficulty Select：玩家选择 1 到 10 档难度，难度快照在 run start 后不可变。
3. Character Select：玩家选择 Warrior；Assassin 与 Druid 可展示但不可选或明确锁定。
4. Act Map：玩家在节点前选择路径；确认进入节点后不得回退改路。
5. Node Resolution：玩家进入 Combat、Event、Shop 或 Rest。
6. Reward / Upgrade：玩家在奖励、休整升级或事件升级中做显式选择。
7. Return Map：节点结算后回到地图，继续下一节点。
8. Run End / Continue：失败、胜利或退出后，Continue 入口必须可解释地恢复或阻断。

这条主干优先于任何视觉 polish。若主干不可达，后续所有功能即使领域层完成，也不能算作玩家可玩闭环。

## 3. 已完成能力清单

本清单按玩家体验能力归并 `tasks.json`、`tasks_back.json`、`tasks_gameplay.json`。三联视图以 `taskmaster_id` 回链主任务；即使任务文件内 `status` 尚未统一回填，本文按用户确认的“任务视为完成”处理，并只用于 UI 接线设计。

| Capability Group | Task IDs | Player-Facing Meaning | Primary UI Need |
| --- | --- | --- | --- |
| Project and runtime foundation | T01, T02, T13 | 玩家可启动 Godot 项目，场景由 CompositionRoot / Autoload 装配 | 启动失败要有可诊断日志；主场景进入 MainMenu |
| Contracts and event boundaries | T03, T04, T05, T06, T07 | 卡牌、状态、战斗、offer、事件具备稳定契约 | UI 只读契约快照，通过 command/service 提交动作 |
| Card identity and upgrades | T08, T21, T33 | 卡牌身份、形态、升级和牌堆操作稳定 | Card tooltip、Upgrade confirm、Deck piles panel |
| Determinism and save/continue | T09, T12, T36, T37, T38, T44, T50 | 退出重进不刷结果，坏档/迁移失败可阻断 | Continue metadata、blocked-state UI、resume diagnostics |
| Status, damage, and combat rules | T10, T11, T25, T47, T48, T49, T51 | 状态堆叠、伤害结算、回合推进和稳定保护可复现 | Combat HUD、intent preview、turn log、invalid action feedback |
| Combat resolution and enemy data feed | T35, T40 | Combat resolution and Act 1 enemy data are ready for UI consumption | Reward handoff routing, enemy roster feed, intent data source |
| Entry and run setup | T14, T15, T16, T24, T26, T27 | 新局、难度、角色、Warrior 起始牌组和难度规则可选 | MainMenu、Difficulty Select、Character Select、run-start summary |
| Map and node routing | T17, T28, T42, T43 | Act 配置、地图路径、节点进入和状态机转移明确 | Map route、node confirmation、invalid branch feedback |
| Reward and economy nodes | T19, T20, T29, T30, T31, T46 | 奖励、商店、卡池、遗物和 offer locking 可解释 | Reward surface、Shop scene、locked offer提示、relic/card tooltip |
| Rest and dark-cost events | T21, T22, T32 | 休整升级、Curse、事件代价与收益可执行 | Rest surface、Event scene、cost preview、irreversible confirmation |
| Localization and visible text | T23, T39 | M1 可见文本走 translations | 所有 UI label、button、tooltip、event text 使用 translation key |
| UI interaction details | T18, T34, T41, T45, T52 | 战斗 UI、拖拽、敌意图、难度 HUD、意图选择可见可操作 | Combat scene、HUD、card drag, target preview, enemy intent panel |
| Quality gates and traceability | T53, T54, T55, T56, T57, T58 | 自动化、审计、回链、语义范围能收口 | 非玩家界面；需要 evidence refs 和 PR/CI 门禁入口 |

## 4. 玩家体验动线重组

### 4.1 Run Entry Flow

玩家目标：从启动游戏到进入一局，不需要理解技术状态。

动线：

1. MainMenu 展示 New Run / Continue / Quit。
2. Continue 可用时展示 run metadata；不可用或坏档时展示原因。
3. New Run 在已有 autosave 时弹出覆盖确认。
4. Difficulty Select 选择 1 到 10 档难度。
5. Character Select 选择 Warrior。
6. 进入 Act Map，并展示初始资源摘要。

### 4.2 Map-To-Node Flow

玩家目标：在地图上理解路线选择，并进入一个明确节点。

动线：

1. Map 展示当前 Act、可达节点、不可达节点和节点类型。
2. 选择节点只改变 UI 选中态。
3. 确认节点写入节点前 autosave 并进入 Combat / Event / Shop / Rest。
4. 非法分支给出反馈并留在 Map。
5. 节点完成后返回 Map，下一个合法节点集刷新。

### 4.3 Combat-To-Reward Flow

玩家目标：完成战斗、理解回合结果、拿到奖励并返回地图。

动线：

1. Combat 展示手牌、能量、牌堆、敌人意图、状态和难度。
2. 玩家拖拽或选择卡牌，选择目标并确认出牌。
3. End Turn 推进敌方行动和下一回合。
4. 胜利后进入 Reward surface。
5. Reward 首次展示锁定三选一候选集。
6. 玩家选择一张或跳过，结算后返回 Map。

### 4.4 Event / Shop / Rest Flow

玩家目标：在非战斗节点做清楚、有代价提示、不可误解的选择。

动线：

1. Event 展示叙事、选项、代价与收益；确认后立即应用。
2. Shop 展示库存、价格、资源与离开入口；不出现任何升级语境。
3. Rest 展示恢复、升级、移除 Curse；升级进入不可逆确认。
4. 所有节点完成后都回到 Map 或进入 Reward，再回 Map。

### 4.5 Continue / Failure Flow

玩家目标：退出重进后知道自己能否继续，以及为什么不能继续。

动线：

1. MainMenu 读取单槽 metadata。
2. metadata 有效时 Continue 进入上次允许恢复的边界。
3. metadata 无效、坏档、迁移失败或完整性失败时，Continue 不进入游戏内。
4. UI 展示阻断原因，并保留 New Run / Quit 等可恢复动作。

## 5. UI 接线矩阵

| Capability | Task IDs | UI Surface | Player Action | System Response | State/RNG Boundary | Evidence/Test Refs | Wiring Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Start / Continue | T14, T36, T37 | `Game.Godot/Scenes/UI/MainMenu.tscn` | 点击 New Run、Continue、Quit | New Run 进入新局流程；Continue 读取单槽 metadata；坏档展示阻断原因 | Continue 不得创建新 RNG；New Run 覆盖旧档必须二次确认 | `Tests.Godot/tests/Tasks/test_task0014_acceptance.gd`, `Tests.Godot/tests/Integration/test_main_menu_new_run_overwrite_cancel.gd`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0037AcceptanceTests.cs` | P0：Continue 阻断原因若只在日志中，不在 UI 中，玩家无法恢复 |
| Difficulty Selection | T15, T26, T45 | `Game.Godot/Scenes/UI/DifficultySelect.tscn`, HUD, run summary | 选择难度并确认 | 创建 run-start 难度快照；HUD 与结算展示同一难度 | run start 后难度不可变；返回选择界面不得覆盖 autosave | `Tests.Godot/tests/Tasks/test_task0015_acceptance.gd`, `Tests.Godot/tests/UI/test_difficulty_select_confirm_selection.gd`, `Tests.Godot/tests/Tasks/test_task0026_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0045_acceptance.gd`, `Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0045AcceptanceTests.cs` | P1：难度可选但 HUD/summary 不一致会破坏复盘 |
| Character Selection | T16, T24, T25 | `Game.Godot/Scenes/UI/CharacterSelect.tscn` | 选择 Warrior 并确认 | 绑定 Warrior 起始牌组与 rage 状态口径；其他角色锁定 | 角色确认后写入 run metadata；预览不推进 RNG | `Tests.Godot/tests/Tasks/test_task0016_acceptance.gd`, `Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_warrior_summary.gd`, `Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_locked_characters_unselectable.gd`, `Game.Core.Tests/Tasks/Task0024AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0025AcceptanceTests.cs` | P1：角色说明若把 rage 描述成第二资源条，会违背 GDD |
| Act Map Navigation | T17, T42 | `Game.Godot/Scenes/Map/Map.tscn` | 选择可达节点并确认进入 | 进入目标节点；非法分支拒绝并保留当前位置 | 节点前是 autosave 边界；确认进入后不得回退改路 | `Tests.Godot/tests/Tasks/test_task0017_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0042_acceptance.gd`, `Tests.Godot/tests/Scenes/Map/test_map_node_pre_enter_state.gd`, `Tests.Godot/tests/Scenes/Map/test_map_branch_selection_paths.gd`, `Game.Core.Tests/Tasks/Task0017AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0042AcceptanceTests.cs` | P0：地图能显示但节点确认未接场景跳转，会断主循环 |
| Combat Shell | T18, T33, T34, T41, T51, T52 | `Game.Godot/Scenes/Combat.tscn`, `Game.Godot/Scenes/UI/HUD.tscn` | 出牌、选目标、结束回合、查看敌意图 | 战斗服务推进回合；HUD 更新能量、手牌、牌堆、意图和状态 | 进入战斗只保存初始状态；战斗中不保存中间态；UI hover 不推进 RNG | `Tests.Godot/tests/Tasks/test_task0018_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0033_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0034_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0041_acceptance.gd`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0052AcceptanceTests.cs` | P0：战斗 UI 若绕过 Core 服务直接改状态，会破坏可复现性 |
| Reward Three-Choice | T19, T36, T46 | Dedicated Reward scene asset | 选择一张、跳过、确认 | 展示三选一候选集；确认一次后锁定结果；跳过保留 offer 证据 | offer 首次展示即锁定 stable ids/order/provenance；重进不刷新 | `Tests.Godot/tests/Tasks/test_task0019_acceptance.gd`, `Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd`, `Tests.Godot/tests/Scenes/Reward/test_reward_scene_skip_preserves_offer.gd`, `Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd`, `Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs` | P0：当前尚未看到真实独立 Reward 场景资产落地 |
| Shop Node | T20 | `Game.Godot/Scenes/Shop.tscn` | 购买、移除、转换、离开 | 库存锁定；重复购买拒绝；商店无升级语境 | re-enter 不刷新库存；购买是显式命令 | `Tests.Godot/tests/Tasks/test_task0020_acceptance.gd`, `Tests.Godot/tests/Integration/test_reward_shop_event_resume_determinism.gd`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs` | P1：服务可用但文案出现“升级/强化”会违背升级口径 |
| Rest Node | T21 | Dedicated Rest scene asset | 选择恢复、升级或移除 Curse | 恢复或免费升级一张；升级确认不可逆 | 升级是显式输入，不推进额外 RNG | `Tests.Godot/tests/Tasks/test_task0021_acceptance.gd`, `Tests.Godot/tests/Scenes/Rest/test_rest_upgrade_no_cost_no_resource_deduction.gd`, `Tests.Godot/tests/Scenes/Rest/test_rest_upgrade_confirmation_irreversible.gd`, `Game.Core.Tests/Tasks/Task0021AcceptanceTests.cs` | P0：当前尚未看到真实独立 Rest 场景资产落地 |
| Event Node | T22, T36 | `Game.Godot/Scenes/Event.tscn` | 阅读事件，选择 HP Loss 或 Curse 等代价选项 | 立即应用代价与收益；结算后返回地图或进入奖励 | 同局事件不重复；事件选择提交触发 autosave；重进不刷结果 | `Tests.Godot/tests/Tasks/test_task0022_acceptance.gd`, `Tests.Godot/tests/Scenes/Event/test_event_scene_hp_loss_cost_applies_immediately.gd`, `Tests.Godot/tests/Scenes/Event/test_event_scene_curse_card_cost_applies_immediately.gd`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs` | P1：事件结果若缺少代价预告，玩家不能理解黑暗代价 |
| Translation Coverage | T23, T39 | All player-facing screens | 切换或加载 locale | UI 文本从 translation keys 渲染；缺 key 不回显给玩家 | 文本加载不改变 run state；key 是稳定内容 ID | `Tests.Godot/tests/Tasks/test_task0023_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0039_acceptance.gd`, `Tests.Godot/tests/UI/test_main_menu_translations.gd`, `Tests.Godot/tests/UI/test_reward_ui_translations.gd`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs` | P0：硬编码玩家可见文本会绕过 i18n gate |
| Quality / Traceability Gates | T53, T54, T55, T56, T57, T58 | CI / local gates, no direct player screen | 研发运行门禁 | Headless、GdUnit、Coverage、Audit JSONL、Traceability、Semantic scope 汇总 | 证据落 `logs/**`；失败不得伪绿 | `Game.Core.Tests/Tasks/Task53HeadlessRunnerCliValidationTests.cs`, `Game.Core.Tests/Tasks/Task54QualityGateSummaryTests.cs`, `Game.Core.Tests/Tasks/Task55CoverageScriptEntrypointBindingTests.cs`, `Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs`, `Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs`, `Game.Core.Tests/Tasks/Task58SemanticScopeGovernanceTests.cs` | P1：门禁存在但 UI backlog 不回链，会导致后续修复不可追踪 |

## 6. 屏幕契约

### 6.1 MainMenu

必须可见：

- New Run、Continue、Quit。
- Continue 可用时展示至少一条可解释 metadata：难度、节点位置或 run 状态。
- Continue 阻断时展示原因，不允许只有日志证据。

必须接线：

- New Run：无 autosave 时进入 Difficulty Select；有 autosave 时先二次确认覆盖。
- Continue：读取单槽 metadata 与完整性检查结果；失败留在菜单。
- Quit：只退出，不改变 autosave。

### 6.2 Difficulty Select

必须可见：

- 1 到 10 档难度。
- “数值挑战为主，不与天赋树强绑定”的短说明。

必须接线：

- Confirm：写入 run-start 难度快照，再进入 Character Select。
- Back：返回 MainMenu，不覆盖 autosave。
- HUD / run summary 必须显示同一难度快照。

### 6.3 Character Select

必须可见：

- Warrior 可选。
- Assassin、Druid 若未接入，必须锁定并给出非承诺式提示。
- Warrior 说明必须写清 rage 是状态 buff，不是第二资源条。

必须接线：

- Confirm Warrior：创建 Warrior starting deck 并绑定角色 metadata。
- Preview：只读展示，不推进 RNG。

### 6.4 Act Map

必须可见：

- 当前 Act、可达节点、不可达节点、节点类型图标。
- HP、金币、关键状态摘要。

必须接线：

- Select node：只改变 UI 选中态。
- Confirm node：保存节点前状态并进入目标节点。
- Invalid branch：拒绝并展示反馈，不改变 run state。

### 6.5 Combat

必须可见：

- 能量、手牌、抽牌堆/弃牌堆/消耗堆摘要。
- 敌人意图、状态层数、当前回合。
- 当前难度快照。

必须接线：

- Play card：通过 Core combat command 结算。
- Target / drag：只在确认出牌时提交。
- End turn：推进回合阶段。
- Exit / Continue：战斗中不保存中间态，重进回到战斗初始状态。

### 6.6 Reward

必须可见：

- 三个候选项、来源、候选集锁定提示。
- Confirm 与 Skip 的明确区别。

必须接线：

- First show：锁定 offer stable ids、order、provenance。
- Confirm：只允许一次成功提交。
- Skip：不改变 offer 集合，不隐式刷新。

场景状态备注：当前场景列表未看到真实独立 `Reward.tscn` 落地，但已定方案为独立资产场景。目标形态应接近 `杀戮尖塔` 的奖励流转节奏，即战斗/事件结束后进入一个短流程、强选择、强确认的独立界面，再返回地图。

### 6.7 Shop

必须可见：

- 库存、价格、玩家资源、离开入口。
- 不出现升级、强化、升星等升级语境。

必须接线：

- Purchase：提交购买命令并锁定结果。
- Remove / transform：只走明确服务入口。
- Re-enter：库存不刷新。

### 6.8 Rest

必须可见：

- 恢复、升级、移除 Curse 等可选动作。
- 升级说明：免费升级 1 张卡，U1 Route A/B 二选一，选择不可逆。

必须接线：

- Heal：提交恢复命令。
- Upgrade：进入升级选择，确认后不可逆。
- Remove Curse：只移除合法 Curse。

场景状态备注：当前场景列表未看到真实独立 `Rest.tscn` 落地，但已定方案为独立资产场景。目标形态应接近 `杀戮尖塔` 的 campfire 决策点，即玩家进入独立界面后，在恢复/升级/移除 Curse 之间做一次清楚且有后果的选择，再返回地图。

### 6.9 Event

必须可见：

- 事件标题、描述、选项、代价与收益提示。
- HP Loss、Curse 等黑暗代价必须在确认前可理解。

必须接线：

- Commit choice：立即应用代价与收益，并写 autosave。
- Cancel / Back：只在未提交前允许。
- Reward-producing event：复用 Reward 的 offer locking 口径。

### 6.10 HUD / Run Summary

必须可见：

- 当前难度、HP、金币、角色、当前节点或 Act。
- Combat 中的敌意图与牌堆摘要。

必须接线：

- HUD 只读展示状态快照，不直接拥有领域状态。
- Run summary 展示同一 run metadata，不重新计算或修改结果。

## 7. 玩家日志、提示与可解释性契约

本章补齐“玩家看到什么反馈才算可解释”。原则来自 `docs/prd/PLAYER-FEEDBACK-EXPLAINABILITY-NEWROUGE-V1.md`，并只保留 UI 接线必须落实的最小字段。

### 7.1 总原则

- 默认展示结果摘要，细节可以折叠，但不能完全隐藏。
- 玩家可见文本必须走 translations，不允许硬编码可见英文或中文。
- 展示行为不能推进 RNG；只有确认、提交、结束回合、购买、升级、选择事件选项等显式动作才允许改变状态。
- 可解释反馈必须优先覆盖：事件、奖励、升级、Continue 阻断、战斗关键结算。

### 7.2 Combat 最小日志字段

Combat 至少应有一处玩家可见的结果反馈区，可以是战斗日志面板、浮层摘要或回合结果区。最低字段：

- 出牌对象：哪张卡被打出。
- 目标对象：命中了谁或为何无效。
- 结果摘要：造成伤害、获得格挡、附加状态、抽牌、弃牌、消耗等。
- 关键数字：伤害值、格挡值、状态层数/持续回合数、能量变化。
- 拒绝原因：若命令非法，必须明确是无目标、能量不足、目标无效还是时机不合法。

建议短句格式：

- `Strike hit Slime for 6 damage`
- `Defend granted 5 block`
- `Poison applied: 2T`
- `Action rejected: invalid target`

### 7.3 Event 最小显示字段

Event 进入时必须显示：

- 标题与描述。
- 每个选项的标签。
- 每个选项的代价/风险提示短句。

Event 提交后必须显示：

- 玩家选择了哪个选项。
- 发生了什么效果。
- 关键数字变化：HP、金币、状态、获得/失去的卡牌或遗物数量。

建议短句格式：

- `Cost: HP -5`
- `Reward: gain 1 card`
- `Status: Poison 2T`

### 7.4 Reward 最小显示字段

Reward 面板必须显示：

- 奖励来源：来自哪场战斗、哪个节点或哪个事件。
- 每个候选项的显示名与一行摘要。
- `候选集已锁定` 或语义等价提示，明确退出重进不会刷新。

可折叠信息：

- provenance 摘要。
- stable ids / order 的工程细节，但不要求默认展示给玩家。

禁止语境：

- 任何暗示“退出重进可以换奖励”或“再次打开可能不同”的文字。

### 7.5 Rest / Upgrade 最小显示字段

Rest 必须显示：

- 当前可选动作：恢复、升级、移除 Curse。
- 若存在升级：`免费升级 1 张卡牌`。
- U1 A/B 路线差异摘要。
- `选择后不可逆` 的明确提示。

特殊事件内路线重选必须显示：

- 事件内可以切换。
- 离开事件时以最终选择为准。
- 不改变其他随机结果。

Ultimate 机会必须显示：

- 来源可识别。
- `不可逆`、`不可再升级`、`不可换路线`。

### 7.6 Continue / Save Boundary 最小显示字段

Continue 可用时至少显示：

- 当前难度。
- 当前进度位置：Act、节点类型或战斗边界。
- 最近一次允许恢复的边界类型：节点前、战斗初始、奖励首显后等。

Continue 被阻断时必须显示：

- 阻断原因。
- 玩家下一步可做的动作：返回主菜单、New Run、查看日志或保留原地。

必须避免误导：

- 不得暗示可以恢复到战斗中间态。
- 不得暗示坏档仍可安全继续。

### 7.7 Map / Shop / HUD 最小提示字段

Map 必须显示：

- 当前可达与不可达节点差异。
- 非法路径选择被拒绝时的短提示。

Shop 必须显示：

- 价格、购买结果、资源不足或重复购买失败原因。
- 不允许出现升级语境。

HUD 必须显示：

- 当前难度。
- HP、金币、能量。
- 牌堆摘要与敌意图。
- 若存在无效动作，给出短反馈，不允许静默失败。

### 7.8 最小禁用语境

UI 和内容文案中禁止出现下列表述或同义误导：

- `退出重进可以换结果`
- `战斗中断点续打`
- `商店升级`
- 任何暗示 preview、hover、打开面板会改变结果的文案

### 7.9 Explainability 验收目标

任一关键流程被玩家执行后，都必须回答以下问题：

1. 我刚刚做了什么选择。
2. 系统刚刚发生了什么。
3. 为什么这个结果是这样。
4. 如果失败或被阻断，我下一步还能做什么。

## 8. 动线级 UI 状态与反馈契约

| Flow | UI Entry | State Display | Operation Feedback | Empty State | Failure State | Completion Result |
| --- | --- | --- | --- | --- | --- | --- |
| Run Entry | MainMenu New Run / Continue | Continue metadata, version, save status | Button focus, overwrite confirmation, blocked reason banner | No autosave: Continue disabled or explained | Bad save, migration failure, integrity failure: stay on MainMenu with reason | Difficulty Select or restored boundary |
| Difficulty / Character | Difficulty Select, Character Select | selected difficulty, Warrior summary, locked heroes | confirm highlight, back navigation, invalid locked hero feedback | no character unlocks beyond Warrior: locked cards visible | missing difficulty snapshot or invalid hero: block confirm | Act Map with run metadata |
| Map-To-Node | Act Map node selection | Act, route, reachable nodes, resources | selected node highlight, confirm prompt, invalid branch feedback | no reachable node: run-end or error recovery prompt | invalid branch/backtrack rejection: stay on Map | target node scene or surface |
| Combat-To-Reward | Combat scene | HP, block/status, energy, hand, piles, enemy intent, difficulty | card play result, invalid target, end-turn transition, damage/status log | no playable card: end-turn affordance remains | illegal command rejected with UI feedback, no state mutation | Reward surface or run failure summary |
| Reward | Reward surface | source, three options, locked-offer hint | confirm once, skip confirmation, selected card feedback | no eligible rewards: explicit skip / continue | duplicate confirm or invalid offer rejected | Map return with deck/run state updated |
| Event | Event scene | title, description, choices, cost/reward preview | choice confirmation, immediate cost application feedback | no available option: leave option or fallback event | insufficient resource / invalid choice rejected | Reward or Map return |
| Shop | Shop scene | inventory, prices, player gold, owned/removed state | purchase success/failure, duplicate purchase rejection | empty inventory: leave remains available | no gold / invalid offer rejected | Map return with inventory locked |
| Rest | Rest surface | HP, deck, Curse count, upgrade candidates | irreversible upgrade confirmation, heal/remove result | no upgrade candidates: upgrade disabled with reason | invalid card/Curse selection rejected | Map return with chosen rest result |
| Continue / Failure | MainMenu or Run Summary | last run metadata, failure/win reason, recoverability | continue allowed/blocked, new run overwrite prompt | no save: New Run remains primary | blocked continue with explicit reason | restored boundary or new run entry |

## 9. 未接 UI 功能清单

| Priority | Capability | Current Evidence | Missing UI Concern | Proposed Resolution |
| --- | --- | --- | --- | --- |
| P0 | Run Entry real route ownership | `MainMenu.cs` emits `ui.menu.start`; `Main.gd` currently routes to `Scenes/Screens/StartScreen.tscn` or demo screen, not M1 run-entry chain | Real navigation does not yet match target flow `MainMenu -> DifficultySelect -> CharacterSelect -> Map` | Rewire main start route so M1 flow is first-class, not demo-only |
| P0 | Reward navigation and surface ownership | Reward tests exist under `Tests.Godot/tests/Scenes/Reward/**`; no standalone `Reward.tscn` observed in current scene list | Decision already made, but asset not implemented: Reward must become a navigable standalone scene asset | Implement `Reward.tscn` and wire `Combat/Event -> Reward -> Map` |
| P0 | Rest navigation and surface ownership | Rest tests exist under `Tests.Godot/tests/Scenes/Rest/**`; no standalone `Rest.tscn` observed in current scene list | Decision already made, but asset not implemented: Rest must become a navigable standalone scene asset | Implement `Rest.tscn` and wire `Map -> Rest -> Map` |
| P0 | Main loop navigation smoke | Screen navigation tests exist, but this document has not yet tied them to a full M1 playable slice | MainMenu-to-Reward-to-Map may still have hidden route gaps | Create one vertical smoke path: New Run -> Difficulty -> Warrior -> Map -> Combat/Event -> Reward -> Map |
| P0 | Continue blocked-state UX | Save and continue tests exist | UI may expose failure only through logs rather than player-facing feedback | Add blocked-state UX contract and test bad save / migration failure / integrity failure messages |
| P0 | Combat command boundary | Combat service and scene binding tests exist | Scene scripts could accidentally mutate state outside Core command/service | Add UI-level smoke proving hover/preview/invalid target does not mutate deterministic state |
| P1 | Run summary ownership | Difficulty HUD tests exist | Run Summary target surface is not defined | Decide whether summary is independent screen, HUD overlay, or MainMenu metadata panel |
| P1 | Logs and explainability | Audit JSONL and deterministic tests exist | Player-facing turn/result log rules are not detailed | Define combat/event result log minimum: damage, status, cost, reward source, blocked reason |
| P1 | Resource/status presentation | Combat, HUD, status tests exist | HP, gold, energy, status, Curse and deck pile display rules are distributed | Consolidate into HUD/panel contract and add one visible-state smoke |
| P1 | Translation coverage across M1 flow | T23/T39 tests exist | Flow-level text coverage may miss dynamic panels | Add M1 flow i18n smoke for MainMenu, Difficulty, Character, Map, Combat, Reward, Shop, Rest, Event |
| P1 | Shop real behavior binding | `Shop.tscn` exists, but no real Shop scene script found in current asset scan | UI surface appears mostly static; purchase/remove/reforge behavior may live only in tests or lower layers | Add real Shop UI binding script and explicit route ownership |
| P1 | Map real interaction binding | `Map.tscn` currently shows only grouped icon nodes; no real map scene script found in current asset scan | Node selection, confirmation, reachability and return path may not yet be implemented in real scene | Add real Map UI binding script and route entry/exit commands |
| P2 | Accessibility and focus | Existing UI a11y tests exist | P0 flow does not define focus order per screen | Batch later with keyboard/controller navigation and focus cycle checks |

## 10. 下一批 UI 接线任务候选

| Candidate | Priority | Vertical Slice | Scope | Acceptance |
| --- | --- | --- | --- | --- |
| UI-T01 Run Entry Vertical Slice | P0 | MainMenu -> Difficulty -> Character -> Map | Wire route ownership and visible metadata from New Run to first Map entry | Automated smoke reaches Map; manual script confirms New Run overwrite behavior and Warrior-only selection |
| UI-T02 Node Resolution Route Slice | P0 | Map -> Combat/Event/Shop/Rest -> Map | Ensure every node type has one explicit entry and return route | Automated smoke enters each node type and returns or blocks with reason |
| UI-T03 Reward Standalone Scene | P0 | Combat/Event -> Reward -> Map | Implement standalone Reward scene asset and wire offer locking UX | Reward first show locks candidates; confirm/skip returns Map; re-enter does not refresh offer |
| UI-T04 Rest Standalone Scene | P0 | Map -> Rest -> Upgrade/Heal/Remove -> Map | Implement standalone Rest scene asset and wire irreversible upgrade confirmation | Upgrade is free once, confirmation irreversible, no RNG advancement |
| UI-T05 Continue Blocked-State UX | P0 | MainMenu -> Continue | Surface bad save, migration, integrity and missing-save states | UI shows reason and stays recoverable; no crash; New Run remains available |
| UI-T06 Combat HUD And Command Boundary | P1 | Combat turn loop | Consolidate HP, energy, piles, status, enemy intent, difficulty and action feedback | Invalid target/preview does not mutate state; valid command updates HUD and log |
| UI-T07 M1 Visible Text Flow | P1 | All M1 screens | Confirm translation keys cover all player-visible labels and dynamic results | `en` and `zh-CN` render non-empty, non-key-echo visible text |
| UI-T08 Run Summary Decision | P1 | Run end / Continue metadata | Define final summary surface and data source | Summary shows difficulty, outcome, node progress and reason without recomputing run state |

## 11. 当前实现状态审计

本章只记录“当前仓库真实场景/脚本是否已经满足契约”，不把测试 double 或 harness 误判为真实 UI 接线完成。

| Surface / Flow | Real Asset Status | Current Evidence | Contract Status | Gap Summary |
| --- | --- | --- | --- | --- |
| MainMenu | Real scene + real script | `Game.Godot/Scenes/UI/MainMenu.tscn`, `Game.Godot/Scripts/UI/MainMenu.cs` | 部分满足 | New Run / Continue / overwrite confirm / i18n 已有；但 Continue blocked-state 仍未见明确玩家原因文案，且 New Run 后未进入 M1 正式链路 |
| Difficulty Select | Real scene + real script | `DifficultySelect.tscn`, `DifficultySelect.cs` | 部分满足 | 难度 1..10、输入导航、确认事件已实现；但未见真实 route 继续到 Character Select |
| Character Select | Real scene + real script | `CharacterSelect.tscn`, `CharacterSelect.cs` | 部分满足 | Warrior-only 可选、锁定角色和摘要已实现；但未见确认后创建 run 并进入 Map 的真实路由 |
| HUD / Run Summary | Real scene + real script | `HUD.tscn`, `HUD.cs` | 部分满足 | 难度 HUD 和 run summary 面板存在；但日志/资源/状态统一呈现仍不完整 |
| Combat | Real scene + real script | `Combat.tscn`, `CombatScene.cs` | 部分满足 | 手牌、能量、牌堆、敌意图、回合按钮、快照应用已存在；但玩家可见结果日志和完整 M1 路由仍不足 |
| Event | Real scene + real script | `Event.tscn`, `EventScene.cs` | 部分满足 | 事件标题、描述、双选项、代价提交和持久化已存在；但更通用的结果面板与返回路由仍需确认 |
| Shop | Real scene only | `Shop.tscn` present; no real Shop UI script found in current scan | 未满足 | 当前更像静态布局，未见真实购买/移除/重铸绑定脚本 |
| Map | Real scene only | `Map.tscn` contains grouped icon nodes only; no real Map UI script found in current scan | 未满足 | 当前未见真实节点选择、确认、回退、可达性脚本 |
| Reward | No real scene asset found | Reward behavior appears in tests/harnesses only | 未满足 | 已确定为独立场景，但真实 `Reward.tscn` 尚未落地 |
| Rest | No real scene asset found | Rest behavior appears in tests/harnesses only | 未满足 | 已确定为独立场景，但真实 `Rest.tscn` 尚未落地 |
| Run Entry Route | Partially real, but demo-oriented | `Main.gd` handles `ui.menu.start` by switching to `Scenes/Screens/StartScreen.tscn` or demo screen | 未满足 | 当前真实入口没有接上目标 M1 链路 `MainMenu -> Difficulty -> Character -> Map` |

结论：

- 已经存在一批真实 UI 资产，但它们尚未形成 M1 的完整可玩链路。
- `Reward` / `Rest` 当前更像“测试驱动下的行为定义”，还不是“仓库里已明确接线的真实玩家界面”；本轮已决定两者都应落为独立场景资产。
- `Map` / `Shop` 已有视觉壳，但真实交互绑定不足，不能直接视作闭环已完成。

## 12. 动线验收矩阵

| Flow | Automated Validation | Manual Validation | Evidence / Output |
| --- | --- | --- | --- |
| Run Entry | `Tests.Godot/tests/Integration/test_screen_navigation_flow.gd`, `Tests.Godot/tests/Tasks/test_task0014_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0015_acceptance.gd`, `Tests.Godot/tests/Tasks/test_task0016_acceptance.gd` | Start game, select New Run, choose difficulty, choose Warrior, verify Map appears | GdUnit JUnit / summary under `logs/ci/<date>/**` |
| Map-To-Node | `Tests.Godot/tests/Integration/test_map_navigation_state_transitions.gd`, `Tests.Godot/tests/Scenes/Map/test_map_branch_selection_paths.gd`, `Tests.Godot/tests/Tasks/test_task0042_acceptance.gd` | Select legal and illegal nodes; confirm illegal branch does not move player | GdUnit scene evidence and route screenshots if captured |
| Combat-To-Reward | `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Tests.Godot/tests/Tasks/test_task0034_acceptance.gd`, `Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd` | Play one valid card, end turn, win or force reward, confirm Reward surface appears | Combat/Reward GdUnit results plus deterministic offer evidence |
| Combat resolution / enemy data feed | `Game.Core.Tests/Tasks/Task0035AcceptanceTests.cs`, `Game.Core.Tests/Services/CombatServiceTests.cs`, `Game.Core.Tests/Tasks/Task0040AcceptanceTests.cs` | Verify victory reaches Reward only after ordered settlement markers, defeat reaches GameOver then MainMenu, and Act 1 enemy definitions remain deterministic inputs for intent/feed surfaces | xUnit acceptance logs and ordered settlement evidence |
| Reward Determinism | `Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd`, `Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs` | Exit and re-enter reward; verify same three options and order | Offer stable ids/order/provenance evidence |
| Event / Shop / Rest | `Tests.Godot/tests/Scenes/Event/test_event_scene_hp_loss_cost_applies_immediately.gd`, `Tests.Godot/tests/Tasks/test_task0020_acceptance.gd`, `Tests.Godot/tests/Scenes/Rest/test_rest_upgrade_confirmation_irreversible.gd` | Enter each node, choose one valid action, verify feedback and return route | GdUnit scene results and optional audit JSONL |
| Continue / Failure | `Game.Core.Tests/Tasks/Task0037AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0050AcceptanceTests.cs` plus future UI blocked-state smoke | Corrupt or invalidate save; click Continue; verify visible blocked reason | Save/continue test logs and UI smoke output |
| Translation / Explainability | `Tests.Godot/tests/Tasks/test_task0039_acceptance.gd`, `Tests.Godot/tests/UI/test_reward_ui_translations.gd`, future M1 flow i18n smoke | Switch locale or load both locales; inspect dynamic text surfaces | Translation validation summary |
| Gates / Traceability | `Game.Core.Tests/Tasks/Task53HeadlessRunnerCliValidationTests.cs`, `Game.Core.Tests/Tasks/Task54QualityGateSummaryTests.cs`, `Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs`, `Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs`, `Game.Core.Tests/Tasks/Task58SemanticScopeGovernanceTests.cs` | Confirm PR links task, ADR, overlay, tests and logs | `logs/ci/<date>/**`, PR body refs |

## 13. 正式 GDD / UX 沉淀规则

本文档是接线工作台，不直接替代正式 GDD 或逐屏 UX 规格。动线升级为正式文档前必须满足：

- 至少一个自动化验证覆盖该动线的主路径。
- 至少一个手工脚本确认玩家可理解反馈、失败态和完成结果。
- 所有玩家可见文本通过 translation key。
- 关键状态边界已验证：展示不推进 RNG，确认才提交 command。
- 证据路径写入 `logs/**` 或对应 PR 说明。

满足后，将稳定内容回写到：

- `docs/gdd/GDD-NEWROUGE-V1.md`：只沉淀玩法循环和体验规则。
- `docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`：沉淀逐屏 UI 字段、失败态、空状态和操作反馈。
- `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md`：沉淀验收与 Test-Refs。

## 14. 即时 UI 集成 Backlog

### P0：主循环可达性

- 确认 `MainMenu -> DifficultySelect -> CharacterSelect -> Map -> Node -> Reward/ReturnMap` 是否存在真实导航链路。
- 实现独立 `Reward.tscn` 与 `Rest.tscn`，并接入真实导航链路。
- 确认 Combat UI 所有状态变更都通过 Core command/service，不允许场景脚本直接改领域状态。
- 确认 Continue 阻断原因在 UI 中可见，不只写入日志。

### P1：可解释与一致性

- HUD、Difficulty Select、Run Summary 使用同一难度快照。
- Reward、Event、Shop、Rest 明确展示确定性与不可逆边界。
- Warrior、rage、enemy intent、deck piles 的 UI 文案与 GDD 术语一致。
- 所有玩家可见文本都有 translation key 覆盖。

### P2：体验 polish

- 添加节点切换、奖励出现、牌堆查看等视觉反馈。
- 优化锁定提示与不可逆提示的文案强度。
- 补充焦点流、键盘/手柄导航和可访问性检查点。

## 15. 验证计划

最小验证应按层执行：

- 文档一致性：确认本文 `Test-Refs` 路径存在，且与任务三联和 Overlay 08 不冲突。
- GdUnit 场景链路：优先跑 screen navigation、map navigation、combat UI、reward/shop/event resume determinism。
- xUnit 领域边界：优先跑 save/continue、difficulty immutability、offer locking、combat turn flow、enemy intent。
- 门禁聚合：在 UI 接线实现后，用 Task53/Task54/Task56/Task57/Task58 对证据路径、GdUnit、Audit JSONL、Traceability 和 semantic scope 做收口。

建议的后续验收切片：

1. P0 navigation smoke：MainMenu 到 Reward 再回 Map。
2. P0 continue smoke：节点前、战斗初始、奖励首显三类恢复。
3. P1 explainability smoke：难度、敌意图、offer locking、不可逆升级提示。
4. P1 i18n smoke：M1 visible text 在 `en` 与 `zh-CN` 下不回显 key、不为空。

## 16. 未决问题

- 任务三联 `status` 与用户确认的完成状态存在漂移，是否需要另开治理任务统一回填。
- Meta Progression 在 M1 UI 闭环中是否暂缓；逐屏规格已有要求，但当前任务主干未把它列为 P0。
- Run Summary 的最终落点是独立屏幕、HUD overlay，还是 MainMenu Continue metadata 的一部分。
