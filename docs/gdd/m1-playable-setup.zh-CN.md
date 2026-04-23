---
GDD-ID: GDD-NEWROUGE-M1-PLAYABLE-SETUP-ZH-CN
Title: NewRouge M1 可玩化配置与首局流程要求
Status: Draft
Owner: codex
Last Updated: 2026-04-23
Encoding: UTF-8
Applies-To:
  - docs/gdd/ui-gdd-flow.md
  - docs/gdd/GDD-NEWROUGE-V1.md
  - project.godot
  - Game.Core/Data/**
  - Game.Godot/Scenes/**
  - Game.Godot/Translations/**
ADR-Refs:
  - ADR-0010
  - ADR-0011
  - ADR-0023
  - ADR-0024
  - ADR-0025
  - ADR-0032
  - ADR-0033
Test-Refs:
  - Tests.Godot/tests/Scenes/Smoke/test_main_scene_smoke.gd
  - Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd
  - Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd
  - Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd
  - Tests.Godot/tests/Integration/test_m1_feedback_fallbacks.gd
  - Tests.Godot/tests/Integration/test_m1_ui_focus_accessibility.gd
  - Tests.Godot/tests/UI/test_run_summary_surface.gd
  - Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd
  - scripts/python/smoke_headless.py
---

# NewRouge M1 可玩化配置与首局流程要求

## 1. 目标

下一阶段目标不是继续做孤立 UI 接线，而是让 M1/MVP 真的可以被玩家完整玩一遍。玩家应能从启动游戏开始，进入新 run，完成难度和角色选择，在地图上做节点选择，进入战斗、奖励、事件、商店、休息等关键节点，并在失败、无效操作、缺失存档或配置异常时获得可理解的反馈，而不是依赖开发者解释或查看日志。

《杀戮尖塔》在本文中作为结构参考，而不是内容复刻目标。M1 应参考它的清晰体验结构：标题菜单、单角色入口、单 Act 地图、节点选择、回合制战斗、战斗后奖励、篝火/休息、商店、带代价的事件选择、敌人意图展示、可读的失败原因。

## 2. 启动与配置完整性

### 2.1 必要配置文件

| 范围 | 文件路径 | 当前状态 | M1 要求 |
| --- | --- | --- | --- |
| Godot 项目配置 | `project.godot` | 已存在 | 必须保持 `run/main_scene="res://Game.Godot/Scenes/Main.tscn"`，默认窗口 1280x720，保留必要 autoload 和 C# 项目路径。 |
| 主启动场景 | `Game.Godot/Scenes/Main.tscn` | 已存在 | 必须进入真实启动流程，不能只指向 demo；应包含输入初始化并进入玩家可见主菜单。 |
| 主菜单场景 | `Game.Godot/Scenes/UI/MainMenu.tscn` | 已存在 | 必须提供 New Run、Continue、Settings、Quit；Continue 不可用时必须显示明确原因。 |
| 输入默认配置 | `Game.Godot/Scripts/Bootstrap/InputMapper.cs` | 已存在 | 必须提供确认、取消、上下左右和菜单导航键；未补控制器映射前不要宣称完整手柄支持。 |
| 功能开关 | `Game.Godot/Scripts/Config/FeatureFlags.cs` 与 `user://config/features.json` | 已存在 | M1 可玩路径应默认可用；实验或调试路径只能作为 opt-in，不能替代 New Run 主路径。 |
| 翻译资源 | `Game.Godot/Translations/en.csv`、`Game.Godot/Translations/zh-CN.csv` | 已存在 | M1 所有玩家可见文本都必须来自翻译表，不能显示空文本或原始 key；加载策略见 `docs/gdd/m1-translation-loading-strategy.zh-CN.md`。 |
| 存档与配置路径 | `user://saves`、`user://config`、Godot app userdata | 代码已有使用 | 存档和配置必须限制在 `user://` 下；绝对路径、越权路径、路径穿越必须 fail closed。 |
| 导出配置 | `export_presets.cfg` | 已存在 | 对外 playtest 前必须有 Windows 可运行导出 preset。 |
| 音频资产 | `Game.Godot/Assets/Audio/**` | 当前主要是占位 | M1 可以先用静音占位，但配置了音频而文件缺失时不得崩溃。真实音频存在后再补音乐/SFX manifest。 |
| 日志与 smoke 证据 | `logs/ci/<date>/smoke/**`、`logs/e2e/<date>/**` | 脚本已使用 | 启动和首局 smoke 的证据必须写到这些目录，不能写入打包的 `res://`。 |

### 2.2 必要运行默认值

- 默认语言：英文兜底，`zh-CN` 可选且经过验证。
- 默认窗口：1280x720，stretch mode 使用 `viewport`。
- 默认 run：M1 Act 1，只开放 Warrior，默认或显式选择 Difficulty 1。
- 默认存档：单 autosave 槽，Continue 由有效 metadata 控制。
- 默认反馈：玩家可见反馈优先，日志作为辅助证据。
- 默认调试策略：debug/demo 路径不能成为唯一进入 M1 loop 的方式。

### 2.3 配置验收

游戏可被称为“可玩”前，至少要满足：

- 打开 `project.godot` 后能启动 `Game.Godot/Scenes/Main.tscn`，且无 fatal autoload 错误。
- MainMenu 的 New Run 能进入 DifficultySelect、CharacterSelect，再进入 Map。
- Continue 要么加载有效 autosave，要么显示本地化的阻断原因。
- Settings 中语言选择能影响玩家可见文本，或者明确要求重启/重新进入场景后生效。
- 缺失音频、配置或存档时安全降级，并给出可见反馈，而不是崩溃或静默失败。

## 3. 最小内容数据集

### 3.1 内容数据原则

《杀戮尖塔》的首局体验成立，是因为每一层都让玩家做一个清晰选择：战斗拿奖励、进商店、休息或升级、承担事件风险、或者选择更危险但收益更高的路线。M1 不需要大量内容，但每个关键界面至少要有一个玩家能理解的选择。

### 3.2 必要数据文件与存放路径

| 内容类型 | 建议路径 | M1 最小集 | 说明 |
| --- | --- | --- | --- |
| Act 配置 | `Game.Core/Data/act1-config.json` | 1 个 Act，6-8 个节点，至少 1 个分支 | 推荐新增该文件，因为 `ActConfigLoader` 已要求 `schema_version`、`act_id`、`node_graph`、`pools`、`encounters`。 |
| 敌人定义 | `Game.Core/Data/act1-enemy-definitions.json` | 当前已有 normal、elite、boss | 当前文件可支撑 smoke 级 M1；进入平衡测试前建议至少补 2 个 normal 敌人。 |
| 卡牌定义 | `Game.Core/Data/m1-card-definitions.json` | Warrior 起始牌组 + 奖励/商店池 | 需要 stable id、翻译 key、费用、类型、目标规则、基础效果、升级路线。 |
| 起始牌组 | `Game.Core/Data/m1-warrior-starting-deck.json` | 10 张卡 | 需要 card id 与数量；顺序固定或明确由 seed 洗牌。 |
| 卡牌池 | `Game.Core/Data/m1-card-pools.json` | normal、elite、boss、shop、event reward 池 | 当前 `CardPoolCatalog` 有生成式占位 ID；真实游玩应由 JSON 内容池承接。 |
| 遗物 | `Game.Core/Data/m1-relic-definitions.json` | 5-8 个 M1 可玩遗物 | `StartingRelicService` 已有 20 个标识，但 M1 玩家体验只需要先落地可见效果的子集。 |
| 诅咒 | `Game.Core/Data/m1-curse-definitions.json` | 至少 1 张 curse | 用于事件代价、Rest/Shop 移除。 |
| 事件 | `Game.Core/Data/m1-event-definitions.json` | 至少 2 个事件 | 一个 HP loss 事件，一个 curse cost 事件；都要有预览和结果文本。 |
| 商店池 | `Game.Core/Data/m1-shop-pools.json` | 至少 3 张卡、1 个遗物、1 个移除选项、1 个 transform/reforge 选项 | 商店文本中禁止出现升级语境。 |
| 休息选项 | `Game.Core/Data/m1-rest-options.json` | heal、upgrade、remove curse | 升级必须显示不可逆。 |
| 本地化文本 | `Game.Godot/Translations/en.csv`、`Game.Godot/Translations/zh-CN.csv` | 覆盖上述所有内容 ID | 每个内容项都需要名称、描述、选项、结果、阻断状态文案。 |

### 3.3 推荐 M1 Act 1 路线

首个可玩地图应足够小，但要有完整节奏：

1. 第 1 层：普通战斗。
2. 第 2 层：事件或普通战斗分支。
3. 第 3 层：战斗后奖励或商店曝光。
4. 第 4 层：休息。
5. 第 5 层：精英或普通战斗。
6. 第 6 层：Boss 或明确的 M1 run summary 终点。

这能提供类似《杀戮尖塔》的体验节奏，同时避免在 M1 阶段要求完整 Act 产量。

### 3.4 内容验收

最小内容集可玩前必须满足：

- 地图、奖励、商店、事件、休息、战斗引用的 stable ID 都能解析到定义。
- 所有玩家可见内容定义在 `en` 和 `zh-CN` 中都有翻译。
- 至少一条完整路线能覆盖 Combat、Reward、Event、Shop、Rest 和最终结果。
- 影响 RNG 的内容生成必须使用命名 RNG stream，UI-only 操作不得推进 RNG。
- Save/Continue 能在节点边界恢复，且不会改变已锁定的 reward/shop/event 选择。

## 4. 玩家反馈与失败兜底

### 4.1 反馈文件与路径

| 反馈范围 | 路径 | 要求 |
| --- | --- | --- |
| 翻译文本 | `Game.Godot/Translations/en.csv`、`Game.Godot/Translations/zh-CN.csv` | 覆盖无效操作、路线阻断、缺失存档、事件结果、奖励锁定、商店拒绝、休息确认、run summary。 |
| 主菜单反馈 | `Game.Godot/Scenes/UI/MainMenu.tscn`、`Game.Godot/Scripts/UI/MainMenu.cs` | Continue 禁用或拒绝时说明原因，并告诉玩家下一步可做什么。 |
| 地图反馈 | `Game.Godot/Scenes/Map/Map.tscn`、`Game.Godot/Scripts/UI/MapScene.cs` | 锁定节点、非法分支、已完成节点、返回路线都必须可见。 |
| 战斗反馈 | `Game.Godot/Scenes/Combat.tscn`、`Game.Godot/Scripts/UI/CombatScene.cs` | 无效目标、能量不足、命令成功、敌人意图、结果摘要必须在 UI 可见。 |
| 奖励反馈 | `Game.Godot/Scenes/Reward.tscn`、`Game.Godot/Scripts/RewardScene.gd` | offer lock、重复选择、skip、确认锁定都必须可见。 |
| 商店反馈 | `Game.Godot/Scenes/Shop.tscn`、`Game.Godot/Scripts/UI/ShopScene.cs` | 金币不足、重复购买、非法 offer、移除/转换结果、离开路线都必须可见。 |
| 休息反馈 | `Game.Godot/Scenes/Rest.tscn`、`Game.Godot/Scripts/UI/RestScene.gd` | 回复量、升级不可逆、缺少目标、移除 curse 结果、返回路线都必须可见。 |
| 事件反馈 | `Game.Godot/Scenes/Event.tscn`、`Game.Godot/Scripts/UI/EventScene.cs` | 代价预览、非法选项、已选选项、结果摘要、HP/卡牌/遗物/金币变化和返回路线都必须可见。 |
| Run summary | `Game.Core/Contracts/Save/RunSummaryMetadata.cs` 与对应 Godot 展示面 | 必须显示 victory、defeat、abandoned 或 M1 endpoint 结果，以及关键 run 数据。 |

### 4.2 失败兜底规则

- 缺失存档：停留在 MainMenu，显示 Continue 阻断原因，New Run 保持可用。
- 存档迁移失败：阻止 Continue，显示可恢复/不可恢复原因，不修改原存档。
- 缺失配置或内容：进入依赖该数据的节点前 fail closed，并显示缺失类别，而不是内部异常。
- 非法地图分支：停留在 Map，显示路线阻断原因，不推进 RNG 或节点状态。
- 非法战斗操作：战斗状态不变，只追加可见反馈。
- Reward/Shop/Event 重进：保留已锁定 offer 和已提交选择。
- 音频缺失：静音或跳过播放即可，不得崩溃。
- 翻译缺失：visible-text smoke 必须失败；playtest runtime 中优先显示可读兜底，不显示原始 key。

### 4.3 反馈验收

每个 M1 界面都应让玩家回答四个问题：

- 我现在能做什么？
- 这个操作为什么不可用？
- 我操作之后发生了什么变化？
- 下一步应该去哪里？

## 5. Playable Smoke / First-Run Smoke 时机

### 5.1 能否先做 smoke？

可以先做，但只能作为增量脚手架。`first-run smoke` 应该尽早建立路线骨架，然后在启动配置、最小内容数据、失败兜底文案都完成后，再升级为 M1 playable 硬门。

不要等全部内容都完成才写 smoke，否则集成问题会被隐藏。但早期 route-only smoke 也不能证明 M1 已经可玩。

### 5.2 Smoke 阶段

| 阶段 | 何时添加 | 证明什么 | 门禁强度 |
| --- | --- | --- | --- |
| Stage A: boot smoke | 立刻 | Godot 能启动 `Main.tscn`，autoload 正常，MainMenu 出现 | 稳定后作为硬门。 |
| Stage B: route skeleton smoke | 内容未全部完成前 | New Run 到 DifficultySelect、CharacterSelect、Map，并进入一个占位节点 | 内容未完成前为软门。 |
| Stage C: first-run smoke | 最小内容文件存在后 | 一条确定性 M1 路线访问 Combat、Reward、Event/Shop/Rest，并返回 Map 或 summary | M1 硬门。 |
| Stage D: recovery smoke | 失败兜底完成后 | Continue 阻断、非法节点/操作、存档恢复、locked offer 可见且稳定 | playable claim 硬门。 |

### 5.3 推荐测试路径

- Boot smoke：`Tests.Godot/tests/Scenes/Smoke/test_main_scene_smoke.gd`
- First-run smoke：`Tests.Godot/tests/Integration/test_m1_first_run_smoke.gd`
- 可扩展的现有入口证据：`Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd`
- 可扩展的现有节点路由证据：`Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd`
- 可扩展的现有可见文本证据：`Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`
- 反馈与失败兜底证据：`Tests.Godot/tests/Integration/test_m1_feedback_fallbacks.gd`
- Run summary 证据：`Tests.Godot/tests/UI/test_run_summary_surface.gd`
- Shop 失败反馈与路线证据：`Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd`
- MainMenu Continue 阻断证据：`Tests.Godot/tests/UI/test_main_menu_continue_blocked_message.gd`
- 可扩展的现有焦点证据：`Tests.Godot/tests/Integration/test_m1_ui_focus_accessibility.gd`
- Python runner：`scripts/python/smoke_headless.py`

### 5.4 First-Run Smoke 验收

最终 first-run smoke 应做到：

- 从 `Game.Godot/Scenes/Main.tscn` 启动。
- 使用真实 New Run 路径。
- 选择 Difficulty 1 和 Warrior。
- 进入 Act 1 地图。
- 完成至少一个 Combat 节点。
- 选择或跳过 Reward。
- 至少访问 Event、Shop、Rest 中的一个节点。
- 每次关键操作后验证玩家可见反馈。
- 验证没有原始翻译 key 出现在界面上。
- 验证没有 Godot fatal error。
- 将证据写到 `logs/ci/<date>/smoke/**` 或 `logs/e2e/<date>/**`。

## 6. 当前可以先做的工作

这些工作不需要等最终平衡或美术完成：

1. 在 `Game.Core/Data/**` 下新增建议的 JSON 内容文件，并先用占位平衡值和 schema-level 校验。
2. 在 `Game.Godot/Translations/**` 中补齐所有 M1 内容项和失败兜底文案。
3. 新增 `Tests.Godot/tests/Integration/test_m1_first_run_smoke.gd`，先作为 soft smoke 跑通预期路线，并明确标记缺失内容。
4. 在最小内容集和失败兜底文本完成后，把 smoke 升为 hard gate。
5. 增加 setup validation 脚本或 gate，检查 `project.godot`、内容 JSON、翻译覆盖和 smoke 证据路径，再进入发布或外部 playtest。
