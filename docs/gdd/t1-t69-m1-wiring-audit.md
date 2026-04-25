---
GDD-ID: GDD-NEWROUGE-T1-T69-M1-WIRING-AUDIT
Title: T1-T69 Minimal Feature Audit And M1 Wiring Snapshot
Status: Draft
Owner: codex
Last Updated: 2026-04-25
Encoding: UTF-8
Applies-To:
  - .taskmaster/tasks/tasks.json
  - .taskmaster/tasks/tasks_back.json
  - .taskmaster/tasks/tasks_gameplay.json
  - docs/gdd/ui-gdd-flow.md
  - docs/gdd/m1-playable-setup.md
  - Game.Godot/Scripts/Main.gd
  - Game.Godot/Scripts/UI/MainMenu.cs
  - Game.Godot/Scripts/UI/MapScene.cs
  - Game.Godot/Scripts/UI/CombatScene.cs
  - Game.Godot/Scripts/RewardScene.gd
  - Game.Godot/Scripts/UI/ShopScene.cs
  - Game.Godot/Scripts/UI/RestScene.gd
  - Game.Godot/Scripts/UI/EventScene.cs
  - Game.Godot/Scripts/UI/HUD.cs
ADR-Refs:
  - ADR-0011
  - ADR-0021
  - ADR-0024
  - ADR-0032
  - ADR-0033
Test-Refs:
  - Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd
  - Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd
  - Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd
  - Tests.Godot/tests/Integration/test_m1_feedback_fallbacks.gd
  - Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd
  - Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd
  - Tests.Godot/tests/Scenes/Rest/test_rest_scene_route_roundtrip.gd
  - Tests.Godot/tests/Scenes/Event/test_event_scene_result_feedback.gd
---

# T1-T69 最小功能审计与 M1 接线快照

## 1. 范围与判定规则

本文件只审计 `T1-T69`，并把三份任务文件统一看作同一批能力的三个视角：

- 主任务：`.taskmaster/tasks/tasks.json`
- Back 视图：`.taskmaster/tasks/tasks_back.json`
- Gameplay 视图：`.taskmaster/tasks/tasks_gameplay.json`

本文件中的“已接入 M1”只按当前玩家实际可走到的场景路由来判断，不按“底层已有契约/服务/测试”来判断。

判定标签统一如下：

- `已接入`：玩家可在当前 M1 路由中直接看到并操作。
- `部分接入`：玩家能进入该场景或看到该能力，但关键行为仍是占位、半接线或测试态。
- `底层支撑`：功能主要作为 M1 的基础设施、契约、数据、测试、门禁存在，不是单独玩家节点。
- `未接入 M1`：仓内已有实现或数据，但当前玩家路由还没有真正用到。

额外说明：

- `tasks.json` 中 `T59-T69` 当前仍为 `pending`，但代码中其中多项已经出现实际接线或部分接线。本文件按“运行时现状”记录，不按任务状态脑补。
- 当前 M1 路由以现有代码为准，不以理想设计为准。

## 2. 当前 M1 实际场景路由

按 `Game.Godot/Scripts/Main.gd`、`MainMenu.cs`、`MapScene.cs`、`CombatScene.cs`、`RewardScene.gd`、`ShopScene.cs`、`RestScene.gd`、`EventScene.cs` 的现状，当前玩家闭环可归纳为：

1. `MainMenu`
2. `DifficultySelect`
3. `CharacterSelect`
4. `Map`
5. `Combat / Event / Shop / Rest`
6. `Reward`（当前实际由 `Combat` 和 `Event` 都可进入）
7. `Map` 或 `Run Summary + MainMenu`

当前路由的关键现实约束：

- 地图路由是 `MapScene.cs` 中硬编码的 5 层节点树，不是由 `ActConfig` 真实驱动。
- `Combat` 胜利后可切到 `Reward`，Boss 奖励后直接显示 `Run Summary` 并回主菜单。
- `Event` 当前也会走到 `Reward`，这是当前代码事实，不代表最终设计一定如此。
- `Shop`、`Rest` 结束后回 `Map`。
- `Continue` 的阻断 UX 已有，但“成功 Continue 后恢复到真实运行节点”的完整玩家路径并未真正落地。

## 3. T1-T69 最小颗粒度功能审计

### 3.1 T1-T18

- `T01 / NG-0001 / GM-0101`: Windows + Godot + .NET 环境基线与证据落盘。M1 接线：`底层支撑`。证据：启动与质量门依赖该基线，但不是玩家场景功能。
- `T02 / - / GM-0102`: Core / Godot / Tests 根结构与命名空间边界。M1 接线：`底层支撑`。证据：仓结构与工程分层。
- `T03 / - / GM-0103`: 卡牌定义与实例身份契约。M1 接线：`底层支撑`。证据：卡牌、奖励、牌组服务都依赖它。
- `T04 / NG-0002 / GM-0104`: Offer lock 快照与来源追踪契约。M1 接线：`底层支撑`。证据：Reward / Shop / Event 的锁定语义来自该层。
- `T05 / NG-0003 / GM-0105`: Status / modifier 契约与不可驱散边界。M1 接线：`底层支撑`。证据：当前 M1 玩家界面未完整展示状态系统。
- `T06 / NG-0004 / GM-0106`: 战斗循环与出牌解析契约。M1 接线：`未接入 M1`。证据：当前 `CombatScene.cs` 仍使用本地简化逻辑，不是直接绑定该核心合同。
- `T07 / - / GM-0107`: 事件总线位置与发布订阅入口。M1 接线：`底层支撑`。证据：`Main.gd`、`MainMenu.cs`、`HUD.cs` 均依赖 EventBus。
- `T08 / - / GM-0108`: CardService 级别的卡牌形态、升级、终态转换逻辑。M1 接线：`未接入 M1`。证据：当前战斗与奖励并未把这些形态转换真正接到玩家流程。
- `T09 / - / GM-0109`: 命名 RNG stream 注册表。M1 接线：`底层支撑`。证据：确定性与 offer locking 的基础能力。
- `T10 / - / GM-0110`: 状态叠加、衰减、驱散服务。M1 接线：`未接入 M1`。证据：当前 M1 可玩路由未把完整状态演算展示到玩家回合中。
- `T11 / - / GM-0111`: 核心 CombatService 出牌管线。M1 接线：`未接入 M1`。证据：当前 `CombatScene.cs` 直接在场景内解析 `Strike/Defend`，没有真实绑定核心出牌管线。
- `T12 / NG-0005 / GM-0112`: 保存序列化与原子写。M1 接线：`底层支撑`。证据：Continue、autosave、run summary 元数据都依赖它。
- `T13 / NG-0006 / GM-0113`: Godot autoload 与 CompositionRoot。M1 接线：`底层支撑`。证据：`HUD.cs`、保存服务、EventBus 都通过 CompositionRoot / autoload 工作。
- `T14 / NG-0007 / GM-0114`: 主菜单 New Run / Continue / Settings / Quit。M1 接线：`已接入`。证据：`MainMenu.cs` 与 `Main.tscn`。
- `T15 / - / GM-0115`: 难度选择界面。M1 接线：`已接入`。证据：`DifficultySelect.cs`，由 `Main.gd` 路由进入。
- `T16 / - / GM-0116`: 战士角色选择界面。M1 接线：`已接入`。证据：`CharacterSelect.cs`，由 `Main.gd` 路由进入。
- `T17 / NG-0008 / GM-0117`: Act 结构与地图数据模型。M1 接线：`未接入 M1`。证据：当前 `MapScene.cs` 用硬编码 `_routeNodes`，不是由 `ActConfig` 真实生成。
- `T18 / - / GM-0118`: 战斗界面壳层、HUD 绑定、基础交互。M1 接线：`已接入`。证据：`CombatScene.cs` 与 `Combat.tscn`。

### 3.2 T19-T35

- `T19 / NG-0009 / GM-0119`: 奖励场景、三选一、锁定语义。M1 接线：`部分接入`。证据：`RewardScene.gd` 已可进入、可 `Skip`，但三张奖励当前仍是 Label，非完整玩家可点选三选一。
- `T20 / - / GM-0120`: 商店场景、库存锁定、非升级语境。M1 接线：`已接入`。证据：`ShopScene.cs` 已有购买、移除诅咒、重铸、离店返回地图。
- `T21 / - / GM-0121`: 休息场景、治疗、升级、移除诅咒。M1 接线：`已接入`。证据：`RestScene.gd` 已有三类选项与返回地图。
- `T22 / - / GM-0122`: 事件场景、黑暗代价样例、结果说明。M1 接线：`已接入`。证据：`EventScene.cs` 已有 lose_hp / take_curse 选项、结果文案、继续返回。
- `T23 / - / GM-0123`: 翻译系统与 key 命名约定。M1 接线：`底层支撑`。证据：主菜单、难度、角色、地图、战斗、事件、商店、休息均走翻译键。
- `T24 / - / GM-0124`: 战士 10 张起始牌组。M1 接线：`未接入 M1`。证据：当前 `CombatScene.cs` 默认手牌与回合刷新仍是硬编码卡牌列表，不是完整起始牌组驱动。
- `T25 / - / GM-0125`: Warrior Rage 状态增益。M1 接线：`未接入 M1`。证据：当前战斗玩家流程未把 Rage 作为可见状态接到实际回合。
- `T26 / - / GM-0126`: 难度配置不可变契约。M1 接线：`底层支撑`。证据：难度 UI 与 HUD 摘要依赖难度锁定语义。
- `T27 / - / GM-0127`: 难度规则修饰器。M1 接线：`部分接入`。证据：难度已可选、已显示，但实际对战斗/掉落/经济的全量玩家效果未完全可见。
- `T28 / - / GM-0128`: ActConfig loader。M1 接线：`未接入 M1`。证据：`act1-config.json` 存在，但当前地图仍不是数据驱动。
- `T29 / NG-0010 / GM-0129`: Act / encounter 对应掉落池。M1 接线：`未接入 M1`。证据：Reward 场景当前不是从真实掉落池生成玩家可选卡。
- `T30 / NG-0011 / GM-0130`: Relic 契约与实例模型。M1 接线：`未接入 M1`。证据：遗物定义已存在，但当前 M1 玩家流程没有实际遗物获得/装备/生效界面。
- `T31 / - / GM-0131`: 20 个起始遗物定义与唯一性。M1 接线：`未接入 M1`。证据：数据与翻译存在，但没有进入当前玩家闭环。
- `T32 / - / GM-0132`: 诅咒卡与移除服务。M1 接线：`部分接入`。证据：事件可加诅咒，商店/休息可做“移除诅咒”动作，但当前更多是场景内状态，不是完整牌组服务闭环。
- `T33 / - / GM-0133`: DeckService 的抽牌/弃牌/消耗/保留。M1 接线：`未接入 M1`。证据：当前 `CombatScene.cs` 仍本地维护 draw/discard 数字，没有真实接到 `DeckService`。
- `T34 / - / GM-0134`: 卡牌目标与拖拽 UX。M1 接线：`部分接入`。证据：当前已有目标选择，但拖拽出牌并未形成玩家真实操作主路径。
- `T35 / - / GM-0135`: 战斗结束解析流水线。M1 接线：`部分接入`。证据：胜利后进入 Reward、Boss 后显示 Victory Summary，但完整“奖励选择 -> 牌组更新 -> 后续节点状态”闭环仍未完成。

### 3.3 T36-T52

- `T36 / NG-0012 / GM-0136`: 按确定性策略触发 autosave。M1 接线：`未接入 M1`。证据：相关服务存在，但当前玩家可见 Continue 成功恢复路径没有真正落地。
- `T37 / - / GM-0137`: 单槽 Continue 元数据与完整性校验。M1 接线：`部分接入`。证据：`MainMenu.cs` 已有 Continue 可用性与阻断原因；但继续成功后的真实还原路径未接好。
- `T38 / NG-0013 / GM-0138`: 确定性与安全审计日志。M1 接线：`底层支撑`。证据：日志与门禁使用，不是玩家面功能。
- `T39 / - / GM-0139`: M1 卡牌/遗物/事件翻译补齐。M1 接线：`部分接入`。证据：事件、商店、休息、部分主菜单文案已受益；遗物与更完整内容还未进入玩家路由。
- `T40 / - / GM-0140`: Act 1 敌人数据定义。M1 接线：`未接入 M1`。证据：数据文件存在，但 `CombatScene.cs` 当前仍以默认敌人状态为主。
- `T41 / - / GM-0141`: 敌方意图显示与预览 UI。M1 接线：`已接入`。证据：`CombatScene.cs` 中有 Enemy Intent panel、默认意图与图标回退。
- `T42 / - / GM-0142`: 地图节点可达性、回退与非法分支规则。M1 接线：`已接入`。证据：`MapScene.cs` 用 floor 可达性控制按钮禁用与反馈。
- `T43 / NG-0014 / GM-0143`: Command-only 运行状态机。M1 接线：`部分接入`。证据：入口路由与若干场景切换已由命令/事件驱动，但全量运行态仍非统一状态机持有。
- `T44 / NG-0015 / GM-0144`: headless 确定性恢复集成测试。M1 接线：`底层支撑`。证据：用于验证恢复，不是玩家直接功能。
- `T45 / - / GM-0145`: HUD 与 Run Summary 显示难度。M1 接线：`已接入`。证据：`HUD.cs` 与 `Main.gd`。
- `T46 / - / GM-0146`: 使用 RNG stream 生成锁定 offer。M1 接线：`部分接入`。证据：Shop / Reward / Event 存在锁定语义，但当前玩家奖励三选一并未完全走真实生成链路。
- `T47 / - / GM-0147`: 状态触发顺序与 fixed damage 规则。M1 接线：`未接入 M1`。证据：当前战斗采用简化 damage 逻辑，未显式展示完整状态顺序系统。
- `T48 / - / GM-0148`: 伤害计算与 AOE 顺序。M1 接线：`未接入 M1`。证据：当前战斗只做简单单体处理，没有完整 AOE 顺序玩家闭环。
- `T49 / NG-0016 / GM-0149`: 战斗循环稳定性保护。M1 接线：`底层支撑`。证据：约束与测试已存在，但玩家看到的是简化战斗表现。
- `T50 / NG-0017 / GM-0150`: 保存迁移验证与失败阻断。M1 接线：`部分接入`。证据：`MainMenu.cs` 已能把 schema/integrity 失败转成 Continue blocked reason。
- `T51 / NG-0018 / GM-0151`: 战斗回合流程与持久化整合。M1 接线：`部分接入`。证据：当前已有出牌、结束回合、敌人攻击、胜负路由；但持久化与完整牌堆循环没有真正落地。
- `T52 / NG-0019 / GM-0152`: 敌方意图选择逻辑。M1 接线：`部分接入`。证据：意图面板已显示，但当前默认样例色彩很强，未完全体现由真实敌人定义驱动的选择逻辑。

### 3.4 T53-T69

- `T53 / NG-0020 / GM-0153`: Python headless smoke runner。M1 接线：`底层支撑`。证据：用于启动/回归 smoke，不是玩家功能。
- `T54 / NG-0021 / GM-0154`: GdUnit4 集成进质量门。M1 接线：`底层支撑`。证据：测试门禁能力。
- `T55 / NG-0022 / GM-0155`: 覆盖率软硬门。M1 接线：`底层支撑`。证据：CI / 本地门禁能力。
- `T56 / NG-0023 / GM-0156`: JSONL 审计校验与门禁。M1 接线：`底层支撑`。证据：审计与质量门能力。
- `T57 / NG-0043 / GM-0157`: ADR / Chapter / Overlay 可追溯门。M1 接线：`底层支撑`。证据：治理门禁。
- `T58 / NG-0044 / GM-0158`: semantic scope 治理。M1 接线：`底层支撑`。证据：软审查与流程治理。
- `T59 / - / GM-0159`: MainMenu -> Difficulty -> Character -> Map 真实 M1 入口重接。M1 接线：`已接入`。证据：`Main.gd` 已这样路由，但任务状态仍是 pending。
- `T60 / - / GM-0160`: 地图到节点场景的路由归属。M1 接线：`已接入`。证据：`StartMapNodeRouteForTest` / `CompleteMapNodeFlowForTest` 已承担该职责。
- `T61 / - / GM-0161`: 独立 Reward 场景与路由整合。M1 接线：`部分接入`。证据：独立场景已可进出，但核心三选一仍未真正玩家可用。
- `T62 / - / GM-0162`: 独立 Rest 场景与路由整合。M1 接线：`已接入`。证据：休息场景与地图回路已存在。
- `T63 / - / GM-0163`: Continue blocked-state UX 与恢复文案。M1 接线：`部分接入`。证据：阻断态、文案、按钮已在主菜单可见；成功恢复 run 的玩家路径还不完整。
- `T64 / - / GM-0164`: 战斗 HUD 可解释性与命令反馈。M1 接线：`已接入`。证据：战斗有 command feedback、enemy intent、HP/energy/draw/discard 可见。
- `T65 / - / GM-0165`: 跨 UI 场景 M1 visible text flow 验证。M1 接线：`底层支撑`。证据：它本质是验证门；当前可见文本能力已部分落到各场景。
- `T66 / - / GM-0166`: Run summary surface ownership。M1 接线：`部分接入`。证据：`HUD.cs` 与 `Main.gd` 已可显示 Victory/Defeat Summary；但更完整结算面仍偏简化。
- `T67 / - / GM-0167`: 商店真实行为绑定与路由归属。M1 接线：`已接入`。证据：购买、移除诅咒、重铸、离店已接到独立 Shop 场景。
- `T68 / - / GM-0168`: M1 UI focus 与可访问性。M1 接线：`部分接入`。证据：部分焦点处理已做，如 Continue blocked / overwrite dialog；全局 UI pass 还不能算完成。
- `T69 / - / GM-0169`: 事件结果解释性与节点反馈路由。M1 接线：`已接入`。证据：事件结果摘要、数值反馈、继续按钮、回地图路由已存在。

## 4. 基于场景路由的功能接线矩阵

### 4.1 当前已形成的 M1 玩家闭环

| 场景路由段 | 已接入的最小功能 | 主要来源任务 |
| --- | --- | --- |
| MainMenu | `New Game`、`Continue` 阻断态、`Settings`、`Quit` | T14, T37, T50, T63 |
| DifficultySelect | 选择难度并进入下一步 | T15, T26, T27, T45, T59 |
| CharacterSelect | 选择 Warrior 并进入地图 | T16, T24, T59 |
| Map | 五层硬编码节点、可达性控制、反馈文案、节点场景路由 | T17, T42, T59, T60 |
| Combat | 手牌列表、能量、HP、Draw/Discard、敌方 HP、敌方意图、出牌、结束回合、胜负反馈 | T18, T41, T45, T51, T52, T64 |
| Reward | 可进入奖励场景、可 `Skip`、可确认后返回地图或结束 run | T19, T35, T46, T61 |
| Shop | 购买、移除诅咒、重铸、离店返回地图 | T20, T32, T67 |
| Rest | 治疗、升级确认、移除诅咒、返回地图 | T21, T32, T62 |
| Event | 选项预览、结果摘要、数值反馈、继续返回 | T22, T32, T69 |
| Run Summary | Victory / Defeat 摘要，返回主菜单 | T45, T50, T66 |

### 4.2 当前接线但仍明显是半成品的节点

- `Reward`：玩家实际只能可靠使用 `Skip`，三选一奖励还没有真正的可点击选择面。
- `Combat`：战斗场景可玩，但核心牌堆、起始牌组、完整出牌管线、状态/遗物/难度修饰并未真正并入。后续主承载任务现为 `T83/T95/T96/T89/T90/T100/T101/T105/T99/T110/T106/T111`。
- `Continue`：阻断 UX 已可见，但成功 Continue 后恢复到真实运行节点的玩家体验未完成。
- `Map`：已有五层路由，但不是由 `ActConfig` / 内容数据文件驱动。
- `Run Summary`：已有基础摘要，不等于完整的 run settlement surface。后续主承载任务现为 `T91/T107/T113`。

## 5. 当前未接入 M1 的功能拆分

为便于后续排期，本节把“未接入 M1”进一步拆成两类：

- `已有能力补接线`：仓内已有明显服务、场景、数据、测试或半成品行为，主要问题是没有真正并到当前玩家闭环。
- `缺真实实现`：仓内虽然有契约、数据占位、测试目标或部分样例，但离“玩家可实际使用”的真实实现还差一层或多层核心逻辑。

### 5.1 已有能力补接线

这些项更适合作为“补接线 / 补闭环”批次处理。

- `T19/T61`：Reward 独立场景已经接入路由，但三选一卡牌选择还没有真正成为玩家可点击、可确认、可写回状态的交互。
- `T20/T67`：Shop 已可买、可移除诅咒、可重铸，但还没有和真实内容池、真实运行状态形成更深闭环，当前仍偏 M1 占位实现。
- `T21/T62`：Rest 已可治疗、升级、移除诅咒并回地图，后续主要是把结果真正写回更完整的 run/deck 状态。
- `T22/T69`：Event 已有选项、结果摘要、数值反馈和返回地图；后续重点是和真实内容数据、真实牌组/资源状态对齐。
- `T24`：战士 10 张起始牌组能力已存在，但尚未成为当前 CombatScene 的真实发牌来源。
- `T27`：难度选择和 HUD 展示已经接上，后续主要是把难度规则影响继续并入真实战斗、经济、掉落行为。
- `T32`：诅咒相关能力已经在 Event、Shop、Rest 表面出现，后续主要是把它从场景局部状态并入真实牌组状态。
- `T33`：DeckService 已存在，但还没有接到当前抽牌堆、手牌、弃牌堆和回洗循环。
- `T34`：当前已有目标选择与按钮式出牌，后续若要达成设计目标，主要是把拖拽 UX 接到现有战斗流程，而不是从零开始。
- `T35`：当前已有“战斗胜利 -> Reward -> Map/Run Summary”骨架，缺的是更完整的战后状态写回。
- `T36`：autosave 触发服务已存在，但尚未形成当前玩家可见、可用的恢复闭环。
- `T37/T50/T63`：Continue 阻断态、完整性校验、迁移失败提示已经存在，缺的是 Continue 成功后的真实 run 恢复路径。
- `T39`：翻译文件和大部分基础文本已存在，后续更多是把新增真实内容全部挂入现有 i18n 管线。
- `T43`：入口与部分场景切换已经事件驱动，后续重点是把更多运行态统一收口到状态机，而不是各场景局部逻辑。
- `T45/T66`：HUD 和 Run Summary 已有基础显示，后续主要是补全更完整的结算信息与 surface ownership。
- `T46`：offer locking 语义已进入 Reward、Shop、Event 周边，后续主要是和真实生成链路对接。
- `T91/T107/T113`：结算面已具基础摘要，后续需按 owner surface、reward/relic metadata、resume evidence 三条窄化路线补完。
- `T51`：当前已有出牌、结束回合、敌方出手、胜负切换，后续主要是把这些动作并入真实 deck/save/combat core。
- `T52`：敌方意图面板已存在，后续主要是把意图选择从默认样例切到真实敌人定义驱动。
- `T59`：MainMenu -> Difficulty -> Character -> Map 已经接好，任务元数据未更新不影响运行态事实。
- `T60`：Map -> node scene 的路由归属已在 `Main.gd` 中形成。
- `T64`：战斗 HUD 可解释性基础已具备，后续是继续和真实战斗状态同步，而非重做界面。
- `T68`：部分焦点与可访问性已经存在，后续更多是系统化补完，而不是从零启动。

### 5.2 缺真实实现

这些项不能简单归类为“接一下就好”，仍然缺少真正能让玩家稳定使用的实现层。

- `T06/T11`：当前战斗场景并没有真正运行核心 CombatService / PlayCard 管线，仍缺真实运行时接入。
- `T17/T28`：当前地图不是由 `ActConfig` 真驱动，仍缺从数据到运行时地图生成的真实实现。
- `T25`：Rage buff 还没有成为玩家实际战斗循环中的真实状态与收益。
- `T29`：当前掉落池并未驱动 Reward 生成，仍缺真实奖励生成逻辑。
- `T30/T31`：遗物定义和翻译已存在，但遗物获得、装备、生效、展示仍缺玩家运行时实现；后续已拆到 `T88/T99/T110/T106` 分别承载 acquisition/display、combat effects、run-boundary effects、combat visible surfaces。
- `T40`：敌人数据文件存在，但敌人实例化、战斗属性与意图生成尚未真正绑定到这些数据。
- `T47/T48`：完整状态顺序、fixed damage、AOE 顺序目前仍停留在规则/测试层，未成为当前可玩战斗的一部分。

### 5.3 主要属于质量门与治理，不计入玩家 M1 接线

这些任务很重要，但它们不是“玩家还差一个按钮或场景就能玩到”的类型，因此单独列出，避免和玩法接线混淆：

- `T44`：主要是 headless 恢复确定性验证，不是玩家可见恢复功能本身。
- `T53-T58`：smoke、测试门、覆盖率门、审计门、追溯门、semantic governance 都属于流程和质量保证层。
- `T65`：主要是 M1 visible text flow 验证，不是新的玩家功能。
- `T102-T104/T108-T109/T112`：这些是针对 T70+ 的 Chapter 6 收敛治理任务，只进 `tasks.json` 与 `tasks_back.json`，不进入 `tasks_gameplay.json`。

## 6. 结论

按当前仓库现状，`T1-T69` 可以分成四层：

1. 已经形成玩家闭环的 UI 路由层：
   - 入口、地图、战斗、事件、商店、休息、基础奖励跳转、基础结算。
2. 已有能力但还需要补接线的玩家层：
   - Reward 三选一、DeckService 接战斗、起始牌组接战斗、Continue 成功恢复、完整 Run Summary、autosave 闭环、真实状态写回。
3. 仍缺真实实现的玩法层：
   - 核心 CombatService 运行时接入、ActConfig 真驱动地图、掉落池、遗物系统、敌人数据真驱动、完整状态与伤害规则。
4. 主要属于流程治理和质量门的层：
   - smoke、traceability、audit、coverage、semantic review、可见文本验证等。

如果后续目标是“把 M1 从可进入闭环提升为真正像样的可玩闭环”，优先级应先打在“已有能力补接线”，再进入“缺真实实现”：

## 7. T83-T91 缺口映射

基于当前缺口审计，`T83-T91` 已作为 `T70+` 的下一批任务落入三份任务文件，用于承载先前未覆盖的运行时闭环缺口。

### 7.1 新任务与缺口对应关系

- `T83`：承接 `T06/T11` 的基础战斗接线缺口，把 `CombatScene -> CombatService / PlayCard` 的基础运行时接到当前战斗场景。
- `T84`：承接 `T29/T46` 的 Reward 生成缺口，把掉落池与 offer locking 真接到 Reward。
- `T85`：承接 `T19/T61/T35` 的 Reward 半成品缺口，把三选一点击、确认、写回牌组、skip 闭环补齐。
- `T86`：承接 `T17/T28/T70` 的地图生成缺口，把 `ActConfig -> route graph generation` 接到当前 Map 路由路径。
- `T87`：承接 `T36/T37/T63` 的 Continue 半成品缺口，把 valid autosave 恢复到真实 `Map / Combat` primary boundary。
- `T88`：承接 `T30/T31` 的遗物运行时缺口，把 relic acquisition / equip / display 接入真实 run path。
- `T89`：承接 `T40/T73/T76` 的敌人运行时缺口，把 enemy definitions 真绑定到战斗实例与意图面。
- `T90`：承接 `T47/T75/T77` 的规则提升缺口，把 status ordering / fixed damage 提升到 live combat runtime。
- `T91`：承接 `T66` 及当前 Run Summary 半成品缺口，把基础 summary 扩成真正的 settlement surface。
- `T95`：承接 `T24/T33/T83` 的战士战斗入口缺口，把 Warrior 起始牌组真接到 CombatService 入口。
- `T96`：承接 `T25/T75/T95` 的 Rage 运行时缺口，把 Rage 从数据/规则层提升到 live combat runtime。
- `T97`：承接 `T60/T70/T86` 的地图绑定缺口，把 generated route 真投影到 Map surface 与 route states。
- `T98`：承接 `T84/T85/T87` 的恢复缺口，把 Reward / Shop / Event 锁定面恢复纳入 Continue。
- `T99`：承接 `T77/T88` 的遗物效果缺口，把 relic runtime effects 接入共享 trigger path。
- `T100`：承接 `T48/T89/T90` 的规则提升缺口，把 AOE / multi-hit ordering 提升到 live combat runtime。
- `T101`：承接 `T78/T90/T100` 的反馈对齐缺口，把 player-visible feedback 与 shared runtime 结果对齐。
- `T102-T104`：承接后续第六章执行治理缺口，防止 `T70+` 再次出现单任务承载多个 deterministic closure。

### 7.1A 复杂度拆分更新

为避免 `workflow.md` 第六章在单任务上承载多个独立 deterministic closure，原本偏重的 `T83/T86/T87/T88/T90` 已进一步拆分：

- `T83` 收窄为 `CombatScene -> CombatService / PlayCard` 基础接线；后续由 `T95` 承接 Warrior 起始牌组接入，`T96` 承接 Rage 运行时接入。
- `T86` 收窄为 `ActConfig -> route graph generation`；后续由 `T97` 承接 generated route -> Map surface binding。
- `T87` 收窄为 `Continue -> Map / Combat primary boundary restore`；后续由 `T98` 承接 `Reward / Shop / Event` 锁定面恢复。
- `T88` 收窄为 relic 获取、装备、展示；后续由 `T99` 承接 relic runtime effects。
- `T90` 收窄为 trigger ordering + fixed damage 提升；后续由 `T100` 承接 AOE / multi-hit ordering，`T101` 承接 player-visible feedback alignment。

这次拆分的原则不是增加任务数量本身，而是让每个任务更接近“一次 Chapter 6 只验证一个 owner boundary 或一组紧耦合 deterministic 规则”的粒度。

同时新增治理任务：

- `T102`：持续审计 `T70-T101` 是否仍存在超出单次 deterministic closure 的任务。
- `T103/T104`：分别约束 `Continue` 和 `combat rule promotion` 在 review / recovery 路径上保持窄化执行。

### 7.2 覆盖结论更新

按 `T83-T91` 的引入，前文列出的主要缺口现在已有明确后续承载任务：

- `Reward` 三选一可点击：由 `T84 + T114 + T85 + T115` 承载。
- `Combat` 真 runtime、牌堆、起始牌组、状态/规则接入：由 `T83 + T95 + T96 + T89 + T116 + T90 + T100 + T101` 承载。
- `Continue` 成功恢复真实运行节点：由 `T87 + T114 + T115 + T98` 承载。
- `Map` 从 `ActConfig` 真驱动：由 `T86 + T97` 承载。
- `Run Summary` 扩成真正结算面：由 `T91` 承载。
- `Relic` 获取/装备/展示/生效：由 `T88 + T99` 承载。

### 7.3 任务视图定位说明

`T83-T91` 同时写入了主任务文件、`tasks_back.json`、`tasks_gameplay.json`。

- 在 `tasks.json` 中，它们是后续可执行的主任务。
- 在 `tasks_gameplay.json` 中，只有直接面向玩家可玩闭环的 gameplay 任务进入该视图；`T102-T104` 作为治理任务只进入 `tasks.json` 与 `tasks_back.json`。
- 在 `tasks_back.json` 中出现同号映射，不代表它们是“纯治理任务”，而是为了保持 backlog/architecture 视图对同一批任务的质量门、依赖和证据追踪。

因此，`T70+` 这批新增任务不是“部分 gameplay、部分治理”二选一，而是：

- 主体目标是 gameplay / UI wiring / runtime closure。
- 同时保留 backlog 视图映射，用于 acceptance、overlay、contract、chapter 追踪。


### 7.4 主线治理补充

最近两轮沟通后，`NG-0034`、`NG-0035`、`NG-0036` 已不再只停留在 `tasks_back.json` 的 backlog 状态，而是提升为 `tasks.json` 中的主线治理任务：

- `NG-0034 -> T92`：把 Core 不能依赖 Godot 的架构边界测试提升为主线守卫，避免后续角色、卡牌、怪物 runtime 扩展破坏分层。
- `NG-0035 -> T93`：把外部进程执行守卫提升为主线安全边界任务，确保未来工具链或运行时扩展不会绕过 deny-by-default 审计边界。
- `NG-0036 -> T94`：把安全敏感 signal contract 校验提升为主线守卫，避免在继续扩 runtime 与集成面时发生信号签名漂移。

这些任务不是 gameplay 任务，但已经被视为当前主线的一部分，因为它们直接保护 `T83+` 之后的角色扩展、卡牌机制扩展、怪物机制扩展不发生架构和安全边界退化。

1. 奖励三选一真正可选并写回运行状态。
2. 牌堆、起始牌组、弃牌回洗接入真实 DeckService。
3. Continue 成功恢复 run 的真实玩家路径。
4. 战后、事件、休息、商店的结果统一写回真实 run 状态。
5. 之后再推进地图与节点内容改为数据驱动，并补遗物、掉落池、核心战斗管线的真实实现。

## 7. T70+ 复杂度收敛快照

为避免 `workflow.md` 第六章在后续任务上反复出现超长 deterministic closure，本轮继续对 `T70+` 中仍偏重的任务做了第二次窄化：

- `T99 -> T99 + T110`：把遗物运行时效果拆成 combat trigger path 与 run trigger boundaries 两条闭环。
- `T106 -> T106 + T111`：把 powers/relics 与 potions 的 combat participant 接线拆开，避免一个任务同时覆盖三类系统。
- `T107 -> T107 + T113`：把 settlement metadata 拆成 reward/relic metadata 与 resume evidence 两条闭环。
- `T109`：同步升级为 settlement 三路 review lane。
- `T112`：新增 relic runtime review lane，避免 `T99 + T110` 在 Chapter 6 重新并回一个超大复审面。

当前 `T70+` 中更适合优先执行的窄路径，已集中到：

- `T83/T95/T96`：CombatService + Warrior runtime 主线。
- `T89/T90/T100/T101/T105`：敌人与战斗规则主线。
- `T99/T110/T106/T111`：非卡牌战斗参与者与遗物运行时主线。
- `T91/T107/T113`：Settlement 主线。
- `T102/T103/T104/T108/T109/T112`：Chapter 6 review / recovery 治理主线。

## 8. T84/T85/T89 第三轮复杂度收敛

本轮继续把仍偏重的 Reward 与 enemy runtime 任务拆成更适合 Chapter 6 的粒度：

- `T84 -> T84 + T114`：把 Reward first-entry offer generation 与 re-entry lock stability / invalid-pool fallback 拆开。
- `T85 -> T85 + T115`：把 Reward selection / confirm gating 与 confirm writeback / skip resolution 拆开。
- `T89 -> T89 + T116`：把 data-backed enemy runtime instantiation 与 enemy surface binding / invalid-definition fallback 拆开。

调整后的建议执行主线：

- Reward 主线：`T84 -> T114 -> T85 -> T115`
- Enemy 主线：`T89 -> T116 -> T90 -> T100 -> T101`
- Continue / settlement 相关依赖已同步窄化：
  - `T98` 现在依赖 `T114 + T115`
  - `T107` 现在依赖 `T115`
