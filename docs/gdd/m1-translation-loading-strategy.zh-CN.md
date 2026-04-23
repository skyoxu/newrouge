---
GDD-ID: GDD-NEWROUGE-M1-TRANSLATION-LOADING-ZH-CN
Title: NewRouge M1 翻译注册与加载策略
Status: Draft
Owner: codex
Last Updated: 2026-04-23
Encoding: UTF-8
Applies-To:
  - project.godot
  - Game.Godot/Translations/en.csv
  - Game.Godot/Translations/zh-CN.csv
  - Game.Godot/Scripts/UI/**
  - Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd
ADR-Refs:
  - ADR-0010
  - ADR-0025
Test-Refs:
  - Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd
  - Tests.Godot/tests/UI/test_main_menu_translations.gd
  - Tests.Godot/tests/UI/test_settings_locale.gd
  - Tests.Godot/tests/UI/test_settings_locale_persist.gd
---

# NewRouge M1 翻译注册与加载策略

## 1. 结论

当前 M1 阶段采用“项目自定义 CSV + 运行时加载/兜底”的策略，不直接把 `Game.Godot/Translations/en.csv` 和 `Game.Godot/Translations/zh-CN.csv` 注册进 `project.godot`。

原因是当前 CSV 文件格式为：

```csv
key,value
ui.menu.new_run,New Run
```

这是项目内的 key-value 表格式，已经被 UI 脚本和测试读取，但它不是本项目当前已验证的 Godot 标准 translation resource 注册格式。为了避免 `project.godot` 出现“看起来注册了，但运行时并不可靠”的假配置，M1 阶段暂不直接注册这些 CSV。

## 2. 当前权威翻译资源

| Locale | 文件路径 | 用途 |
| --- | --- | --- |
| `en` | `Game.Godot/Translations/en.csv` | 默认兜底语言和英文 playtest 文本。 |
| `zh-CN` | `Game.Godot/Translations/zh-CN.csv` | 中文 UI、反馈、事件、商店、休息、战斗文本。 |

这两个文件是 M1 玩家可见文本的 SSoT。新增内容数据时，必须先补对应 translation key，再接入 UI。

## 3. 当前加载策略

M1 UI 的加载顺序为：

1. UI 节点先调用 `TranslationServer.Translate(key)`。
2. 如果 Godot translation server 返回空值或原始 key，脚本读取 `Game.Godot/Translations/<locale>.csv`。
3. 如果当前 locale 缺 key，回退到 `Game.Godot/Translations/en.csv`。
4. 如果英文也缺 key，UI 不应静默通过；visible-text smoke 或对应场景测试必须失败。

已采用该策略的典型脚本包括：

- `Game.Godot/Scripts/UI/MainMenu.cs`
- `Game.Godot/Scripts/UI/MapScene.cs`
- `Game.Godot/Scripts/UI/CombatScene.cs`
- `Game.Godot/Scripts/UI/ShopScene.cs`
- `Game.Godot/Scripts/UI/EventScene.cs`
- `Game.Godot/Scripts/UI/CharacterSelect.cs`
- `Game.Godot/Scripts/UI/DifficultySelect.cs`
- `Game.Godot/Scripts/RewardScene.gd`
- `Game.Godot/Scripts/UI/RestScene.gd`

## 4. Locale 设置与持久化

语言设置由以下路径负责：

- `Game.Godot/Scripts/UI/SettingsPanel.cs`
- `Game.Godot/Scripts/UI/SettingsLoader.cs`
- `user://settings.cfg`

运行规则：

- Settings 面板切换语言时调用 `TranslationServer.SetLocale(lang)`。
- Settings 保存时写入 `user://settings.cfg`。
- 启动时 `SettingsLoader` 读取已保存语言并重新调用 `TranslationServer.SetLocale(lang)`。
- M1 支持的主要 locale 是 `en` 和 `zh-CN`；其他语言如果出现在 UI 选项中，必须视为未完成语言，不得作为 M1 验收语言。

## 5. 何时改为 project.godot 注册

只有满足以下条件后，才把翻译资源注册到 `project.godot`：

- 已转换为 Godot 标准 `.translation`、`.po`，或经 Godot 4.5.1 验证可直接注册的标准 CSV translation resource。
- 本地 headless 能证明 `TranslationServer.Translate(key)` 在不读项目自定义 CSV 兜底时也能解析 `en` 和 `zh-CN`。
- `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd` 仍然通过。
- 导出后的 Windows build 能读取同一批翻译资源。

推荐后续路径：

- 源 CSV 继续保留在 `Game.Godot/Translations/*.csv`，作为人工编辑和脚本校验 SSoT。
- 增加生成脚本，把源 CSV 转换成 Godot 标准 translation resource。
- 将生成物放在 `Game.Godot/Translations/generated/**`。
- 只把生成物注册到 `project.godot`，不要直接注册未验证的源 CSV。

## 6. 验收要求

M1 翻译加载策略达标需要满足：

- `en.csv` 和 `zh-CN.csv` 均存在，且使用 UTF-8。
- M1 可见 UI 文本不得显示空字符串。
- M1 可见 UI 文本不得显示原始 key，例如 `ui.menu.new_run`。
- `SettingsPanel` 切换语言后，已支持刷新或重新进入的界面显示对应语言文本。
- `test_m1_visible_text_flow.gd` 覆盖 MainMenu、DifficultySelect、CharacterSelect、Map、Combat、Reward、Shop、Rest、Event。
- 新增 M1 内容数据时，必须同时补 `en` 和 `zh-CN` 文本。

