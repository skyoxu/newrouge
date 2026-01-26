---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
inputDocuments: []
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 0
workflowType: "gdd"
lastStep: 14
project_name: "newrouge"
user_name: "skyo"
date: "2026-01-23"
game_type: "card-game"
game_name: "NewRouge"
---

# NewRouge - Game Design Document

**Author:** skyo
**Game Type:** card-game
**Target Platform(s):** Windows (Steam)

---

## Executive Summary

### Core Concept

NewRouge 是一款“黑暗主题”的单人卡牌构筑 roguelike：玩家在 3 Act 分叉地图中推进，节点由战斗/精英/事件/商店/休整组成，通过奖励三选一逐步构筑牌组与遗物引擎，目标是在单局约 60 分钟内完成通关或在失败中积累长线进展。

首发包含 3 个机制差异明显的角色：战士（怒气作为状态型 buff 而非第二资源条）、刺客（擅长给敌人叠加多种 debuff 并围绕 debuff 做增幅/引爆）、德鲁伊（姿态/状态的持久 buff 与切换后的定点爆发）。元系统为“共享天赋树”，支持无条件重置，鼓励玩家反复试验流派；难度体系 10 档以数值曲线为主，不与天赋树强绑定。单局 60 分钟的黑暗卡牌肉鸽，用共享可重置天赋树鼓励流派实验，并用确定性反刷随机的存档契约保护玩家信任。

### Game Type

**Type:** Card Game (`card-game`)  
**Structure Tags:** Roguelike（run-based，3 Acts，branching map）

### Determinism & Save/Resume Contract（ADR-0032）

本项目将“退出重进不刷结果”作为硬约束，以保护玩家信任并支持 QA 复现（参考 ADR-0032）：

- 单槽自动存档：仅维护一个系统自动存档；主菜单提供唯一入口 Continue Game 读取该槽；新开一局允许覆盖旧存档但必须二次确认且不可撤销。
- 自动存档生命周期：Continue 仅在“进行中的 run 且校验通过”时可用；run 结束（死亡/通关）必须作废 autosave，Continue 不得回到已结束 run。
- 战斗保存边界：节点前存档；进入战斗仅保存“战斗初始状态”；战斗中绝不保存中间态；任何战斗中断后的继续游戏只能回到战斗初始状态。
- 严格确定性定义：不重抽不重滚；同 seed + 同输入序列 = 同一结果（玩家操作不同可导致不同结果）；对“三选一”场景，退出重进后候选集必须固定不变（允许重新选择，但候选项集合不变）。
- 确定性的边界（Scope）：仅“会影响局势的玩家输入”计入输入序列；纯 UI 行为不得推进 RNG 或改变候选集。
- 候选集锁定粒度（Lock granularity）：所有“三选一”必须持久化候选项的稳定 ID 列表与展示顺序；退出重进后保持完全一致，只允许重新选择。
- 存档一致性与坏档处置：自动存档写入必须原子化；Continue 读档必须做完整性校验；损坏/不兼容时必须阻止 Continue 并提示。
- RNG 流拆分：RNG 按系统拆分（run/combat/event/loot）；并在存档点持久化必要 RNG 状态，确保退出重进不改变候选集与战斗初始局面。
- 可审计性证据：每次存档写入/读档/迁移/阻断 Continue（含原因）都必须写入结构化审计记录，便于复现与客服排障（审计产物遵循 `logs/**` 口径）。

### Top Risks（摘要级）

- R1 退出重进规则被误解 | Mitigation: 主菜单/帮助/战斗开始三处统一解释 | Acceptance: 三处文案一致且可被引用
- R2 确定性被 UI/实现细节破坏 | Mitigation: UI 不推进 RNG + 候选集落盘（ID+顺序+来源） | Acceptance: 重载候选集与顺序完全一致
- R3 单槽覆盖误操作 | Mitigation: New Run 覆盖二次确认默认取消 | Acceptance: 无“一键误删”
- R4 坏档/迁移失败扩大损坏 | Mitigation: 原子写入 + 校验失败阻断 Continue + 幂等迁移失败不写回 | Acceptance: 不崩溃、不半加载、有 `logs/**` 证据

### Failure Mode Checklist（Save/Resume & Determinism）

- Autosave 写入必须 atomic；失败必须保留上一份 autosave。
- Continue 必须做 integrity 校验；corrupted/incompatible 必须阻断 Continue 并给出明确提示。
- Migrations 必须 idempotent；失败不得写回；并产出 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。
- 只有 gameplay-affecting inputs 才推进 RNG；纯 UI inputs 不得推进。
- RNG streams 拆分（run/combat/event/loot），并在存档边界持久化必要状态。
- “三选一”必须持久化 stable IDs + display order + provenance；重载必须完全一致（含顺序）。

---

## Target Platform(s)

### Primary Platform

- Windows PC（Steam）
- 引擎：Godot 4.5.1 .NET（锁死版本，不升级）

### Platform Considerations

- 目标体验：单人、离线可玩（无必须在 v1 支持的出网/云同步需求）
- 存档：单槽 Continue + 确定性反刷随机（参考 ADR-0032）
- 显示：支持窗口/无边框/全屏；分辨率自适应（UI 需可缩放）

### Control Scheme

- 输入：鼠标/键盘优先（UI 点击/拖拽 + 快捷键）
- 必备快捷键：结束回合、确认/取消、打开牌堆/弃牌堆/角色信息、打开地图、打开设置
- 键位：支持重绑定（最小集：结束回合/确认/取消/地图/设置）

---

## Target Audience

### Demographics

- 核心受众：熟悉卡牌构筑/肉鸽的核心玩家
- 次级受众：愿意学习规则、偏好单人策略与反复试验流派的玩家

### Gaming Experience

- Core/Hardcore：偏策略型、愿意在失败中学习与优化路线/牌组/遗物组合

### Genre Familiarity

- 默认假设玩家知道“抽牌/弃牌/回合制/三选一奖励/事件节点/遗物被动”等概念
- 对新手：通过 UI 引导、术语统一与信息可视化降低理解成本（不靠长篇教程）

### Session Length

- 单局目标：约 60 分钟（允许波动）
- 适配“随时退出—继续”：但退出重进不改变候选与结果（信任优先）

### Player Motivations

- 构筑与流派实验（卡牌 × 遗物 × 天赋树）
- 路线决策与风险回报（分叉地图）
- “随机但不可刷”的公平感（确定性契约）

---

## Goals and Context

### Project Goals

- 交付一款可反复游玩的单人卡牌构筑 roguelike：3 Act 分叉地图、单局约 60 分钟、通关/失败闭环清晰。
- 用“退出重进不刷结果 + 单槽 Continue”的硬规则建立玩家信任，同时提升 QA 可复现性（ADR-0032）。
- 用“共享且可无条件重置的天赋树”鼓励跨角色、跨流派实验；10 档难度主要走数值曲线，不与天赋强绑定。
- 在 Windows（Steam）上提供稳定、信息清晰、可长期维护的技术与内容骨架（性能、日志、门禁与可观测性遵循既有 ADR/基线）。

### Background and Rationale

目标是复刻《杀戮尖塔》所验证的“卡牌构筑 + 路线选择 + run-based 失败学习”的核心快感，但在 v1 就明确两条差异化路线：

1) **扩展空间**：角色机制更分化（怒气 buff 战士 / debuff 刺客 / 姿态德鲁伊），并为后续角色、卡牌、事件、元系统扩展预留骨架。  
2) **信任口径**：把“退出重进不刷结果”写成可执行的存档/确定性契约（ADR-0032），避免未来在实现阶段被“方便调试/玩家想刷”带偏。

---

## Unique Selling Points (USPs)

- **确定性反刷随机**：同 seed + 同输入序列 = 同结果；退出重进不会改变“三选一”候选与战斗初始局面（以规则换信任）。
- **共享可重置天赋树**：所有角色共用一棵天赋树，允许无条件重置，鼓励反复试验不同流派与构筑路径。
- **以 debuff 为核心的刺客体系 + 姿态爆发德鲁伊 + 怒气 buff 战士**：三名角色的核心交互不同，避免“换皮同构”的体验。
- **黑暗主题 + 高对比信息呈现**：以氛围塑形，但把“可读性/可决策性”作为更高优先级。

### Competitive Positioning

NewRouge 面向熟悉该品类的核心玩家：它不靠“更随机/更花哨”去卷，而是用“可预测的规则边界 + 更强的流派实验成本控制（可重置天赋）”来区分同类作品。

---

## Core Gameplay

### Game Pillars

1) **玩家信任（确定性契约）**：退出重进不刷结果；所有影响局势的随机必须可复现、可审计。  
2) **构筑深度（组合爆炸）**：卡牌 × 遗物 × 天赋树形成可解释的强协同，而不是黑箱叠数值。  
3) **清晰决策（信息可读）**：每一次选择能看见代价与收益；战斗与地图信息透明，避免“死因不明”。  
4) **黑暗氛围（风险回报）**：主题服务于压力与抉择，但不牺牲可读性与节奏。

### Core Gameplay Loop

Run Loop（宏观）：

选择角色与难度 → 进入 Act 1 → 在分叉地图选择节点（战斗/精英/事件/商店/休整） → 结算奖励（三选一为主）并调整牌组/遗物/状态 → 推进到 Boss → 进入下一 Act → Act 3 终局 Boss → 通关或死亡 → 结算元系统进展（天赋点等）→ 回到主菜单/开新一局

Combat Loop（微观）：

战斗开始（保存“战斗初始状态”）→ 抽牌 → 使用能量打出卡牌/触发遗物与状态 → 结束回合 → 敌方行动 → 回合循环直到胜负

### Win/Loss Conditions

#### Victory Conditions

- 击败 Act 3 的终局 Boss（通关一次 run）

#### Failure Conditions

- 角色生命值归零（run 失败）

#### Failure Recovery

- run 结束后必须作废 autosave，Continue 不得回到已结束 run（ADR-0032）。
- 失败被设计为学习与元系统积累：玩家可在天赋树上重新分配点数并立即开新局。

---

## Game Mechanics

### Primary Mechanics

- **地图推进**：在 3 Act 分叉节点路线图上选择路径，权衡风险（精英）与资源（商店/休整/事件）。
- **回合制卡牌战斗**：抽牌/弃牌/能量制；用卡牌与遗物构建引擎，围绕状态（buff/debuff）做增益与爆发。
- **构筑与管理**：战斗/事件/商店的奖励以“三选一”为主；玩家通过增加/移除/替换卡牌控制牌组质量与循环效率。
- **遗物系统**：被动规则改变与组合放大器（首发 20 个，强调可解释的协同）。
- **元系统（共享天赋树）**：所有角色共享一棵可无条件重置的天赋树，用于长期成长与流派实验的“试错成本管理”。

### Character Combat Identity（v1）

- 战士：怒气作为状态型 buff（可叠加/可消耗/可触发），围绕“越战越强”的节奏与爆发窗口。
- 刺客：擅长给敌人叠加多种 debuff，并通过“增幅/引爆/转移/延长”形成流派核心。
- 德鲁伊：姿态/状态的持久 buff，切换后获得定点爆发或功能转换（进攻/防守/资源）。

### Controls and Input

- 鼠标：点击/拖拽打出卡牌、选择奖励、选择地图节点、操作 UI。
- 键盘：结束回合、确认/取消、打开牌堆/弃牌堆/角色信息、打开地图、打开设置（支持重绑定）。
- 可见 UI 文本：必须通过 `Game.Godot/Translations/**`（脚本禁止硬编码可见文本）。

---

## Card Game Specific Design（Deckbuilder）

### Card Types and Effects

- 卡牌类型（建议最小集）：Attack / Skill / Power（以及保留扩展：Status / Curse）
- 稀有度：Common / Uncommon / Rare / Legendary（奖励三选一倾向按稀有度权重）
- 基础资源：能量（Energy），默认每回合上限为 3（可被卡牌/遗物/天赋修改）
- 典型效果类型：伤害、防御、抽牌、弃牌、检索、增益、减益、持续、爆发、资源转换、姿态切换、 debuff 增幅/引爆
- 关键词与状态：以“可读性优先”的少量关键词为目标；所有状态必须在 UI 有明确说明与可追踪来源

### Deck Building

- 起始牌组：10 张（建议结构：7 张普通、2 张优良、1 张精英/高稀有；具体卡名按角色差异化）
- 牌池规模：每个角色首发 30 张基础卡牌（不含升级版本；升级为同一张卡的升级态）
- 复制规则：允许同名卡多张；不设硬上限，但通过商店移除/事件交换鼓励牌组“变薄”
- 流派目标：每个角色至少 3 条可自洽的基础流派（由卡牌 + 遗物 + 天赋支撑）

### Mana/Resource System

- 能量：每回合刷新；默认上限 3；允许通过构筑实现“短爆发（临时加能）/长续航（效率提升）”
- 资源设计原则：资源变化必须可预期、可追踪来源；纯 UI 行为不得推进 RNG（确定性边界）

### Turn Structure

- 玩家回合：回合开始触发 → 抽牌 → 主行动（打牌/触发）→ 结束回合 → 丢弃/保留结算（按规则）
- 敌方回合：按稳定顺序执行意图 → 结算状态衰减/持续效果
- 回合时长：不设硬计时；通过信息清晰与快捷键降低操作摩擦

### Card Collection and Progression

_本项目为单人 deckbuilder：不做“开包/收集/合成”式卡牌收集系统。卡牌主要在 run 内通过奖励/商店/事件获得。_

_v1 必须提供“卡牌升级系统”：仅在休整节点或特定事件中升级（商店任何时候都不提供升级服务）。升级分为：常规升级（U1 二选一路线）与终极形态（Ultimate，稀有来源）。_

_休整节点为“多选一”决策点：例如恢复体力 / 升级 / 其他；若选择升级，则免费升级 1 张卡牌。非休整事件提供升级时，必须伴随资源/代价且保持确定性。_

_常规升级（U1）：每次升级必须在 Route A / Route B 二选一，选择不可逆。特殊事件允许对已升级的卡牌免费更换升级路线：事件内可无限次切换，离开事件时以最终选择为准。_

_终极形态（Ultimate）：每张卡有一个终极形态，仅通过史诗事件/关卡 Boss 等稀有机会获得；可从未升级卡直接进阶；不可逆；不可再升级、不可再换路线。_

### Game Modes

- v1：单人 Run（主模式）
- v1 明确不做：PVP、联机合作、竞技天梯、多人 Draft

---

## Progression and Balance

### Player Progression

- **Run 内成长（核心）**：通过战斗/事件/商店获得卡牌与遗物，形成当局构筑引擎。
- **Meta 成长（元系统）**：共享天赋树（可无条件重置）；点数获取遵循“完成一局/推进更深/更高难度更高收益”的原则（具体数值在平衡阶段校准）。
- **技能成长**：玩家理解路线与构筑规律后提升胜率与难度通关能力。

### Difficulty Curve

- 10 档难度，默认以数值曲线为主（敌方属性/掉落权重/经济压力等），不与天赋树强绑定。
- 单局内部：Act 内“渐进 + Boss 峰值”的锯齿节奏（节点选择决定难度曲线形状）。

### Economy and Resources

- 资源类型（Run 内）：生命值、能量、金币（商店货币，战斗/事件获取；用于买卡/遗物/服务）
- 资源设计原则：金币与生命形成明确的风险回报；商店与事件提供“用资源换未来收益”的决策点。

---

## Level Design Framework

### Level Types

- 结构类型：程序化生成的分叉路线图（branching map），共 3 Act。
- 节点类型（最小集）：普通战斗、精英战斗、事件、商店、休整、Boss。
- 教学融入：通过早期节点组合、UI 提示与信息可视化渐进引导；避免单独“教程关”割裂体验。

### Level Progression

- Act 1 → Act 2 → Act 3 的线性推进；每个 Act 内通过分叉路径提供风险/收益分布不同的路线选择。
- 事件池：首发 40 个事件；单局内事件不重复，跨 run 可重复抽取（形成可重复池且避免单局刷同事件）。

---

## Art and Audio Direction

### Art Style

- 总体：黑暗主题的 2D 风格化表现（读数优先），强调高对比与明确的状态/意图可视化。
- 色彩：低饱和暗色为底，危险/关键提示使用高对比强调色（例如深红/冷青作为警示与增益区分）。
- UI：信息层级清晰；卡面与状态图标必须在 1080p 下可快速识别；避免“炫但看不懂”。

### Audio and Music

- 音乐：偏氛围与压迫感的配乐（章节/战斗/精英/Boss 有清晰层次），避免喧宾夺主影响思考。
- 音效：强调“反馈明确”（打出/触发/叠加/引爆/姿态切换）与“可读性”（关键行动有差异化提示）。
- 语音：v1 不做完整配音；允许少量非语言化点缀（喘息/低语/环境音）以强化黑暗主题。

---

## Technical Specifications

### Performance Requirements

- 帧率：目标 60 FPS（稳定性优先于视觉堆料）
- 分辨率：最低 1280x720（可玩）；基准 1920x1080；更高分辨率通过 UI 缩放支持
- 加载：冷启动与场景切换需可感知地“快”，并在可观测性里留证据（详细口径见既有基线/ADR）

### Platform-Specific Details

- 平台：Windows（Steam）
- 存档：单槽 autosave + Continue；本地存储；v1 不引入云同步与多槽存档（明确 out of scope）
- 文案：所有可见 UI 文本必须走 `Game.Godot/Translations/**`；脚本禁止硬编码可见文本
- 日志与取证：安全/网络/文件/权限审计与测试输出统一写入 `logs/**`（SSoT）

### Asset Requirements

- 2D 美术：角色/敌人立绘或头像、卡面图/框、状态图标、地图节点图标、背景、UI 皮肤
- 动效：卡牌打出/状态叠加/爆发与受击反馈的轻量特效（以可读性为第一约束）
- 音频：BGM（按 Act/战斗层次划分）+ SFX（核心反馈优先）

---

## Development Epics

### Epic Structure

### Epic Overview

| # | Epic Name | Scope | Dependencies | Est. Stories |
|---|-----------|-------|--------------|-------------|
| 1 | 可玩纵切（Act 1 骨架） | 地图节点推进 + 战斗基本循环 + 奖励三选一 + 单槽 Continue 规则落地（按 ADR-0032） | - | 12–18 |
| 2 | 战斗系统完整化 | 状态系统（buff/debuff）+ 敌人意图 + 基础 AI + 结算与信息呈现 | 1 | 15–25 |
| 3 | 角色机制（3 角色） | 战士怒气 buff、刺客 debuff 核心、德鲁伊姿态与爆发；起始牌组与基础流派 | 2 | 18–30 |
| 4 | 内容包 v1 | 卡牌（每角 30）、遗物（20）、事件（40）、精英/Boss 与掉落表 | 2,3 | 20–35 |
| 5 | 元系统与难度 | 共享天赋树（可重置）、天赋点获取与 UI、10 档难度数值曲线与门禁 | 1,2 | 12–20 |
| 6 | UI/UX 与本地化口径 | 菜单/继续游戏/覆盖确认、提示与帮助、可访问性、Translations 全链路 | 1 | 10–18 |
| 7 | 质量门禁与发布准备 | 性能/稳定性门禁、日志与取证工件、Windows 打包与发布前检查 | 1–6 | 10–18 |

### Recommended Sequence

优先按“可玩纵切 → 战斗闭环 → 角色差异 → 内容扩充 → 元系统与难度 → UI/UX → 门禁与发布”推进，确保每个阶段都有可玩的里程碑，避免长期停留在不可验证的抽象层。

### Vertical Slice

第一个可玩的里程碑：Act 1 的最小可通关纵切（单角色 + 10 起始牌组 + 若干敌人与事件 + 商店/休整最小实现 + 三选一奖励 + Continue 规则可验收）。

---

## Success Metrics

### Technical Metrics

- 性能：主战斗场景 60 FPS 稳定；关键交互无明显卡顿（以 P95/P99 帧耗时评估）
- 稳定性：崩溃率与严重错误率在可观测性系统里可追踪；关键错误必须可定位（日志/审计齐全）
- 确定性：退出重进后“三选一”候选集与顺序一致；战斗恢复回到战斗初始状态；determinism mismatch = 0
- 存档：原子写入；坏档/迁移失败阻断 Continue 且有明确提示与 `logs/**` 证据

#### Key Technical KPIs

| Metric | Target | Measurement Method |
|-------|--------|--------------------|
| FPS stability | 60 FPS target, no sustained drops | 本地性能烟测 + `logs/perf/**` 摘要 |
| Determinism mismatches | 0 | 回放/重载一致性测试 + `logs/ci/**` 取证 |
| Autosave integrity failures | 0 | 读档校验 + 故障注入测试日志 |
| Crash-free sessions (24h) | ≥ 99.5%（口径见基线） | Release Health Gate（Sentry） |

### Gameplay Metrics

- 单局时长：目标中位数接近 60 分钟（允许随构筑与难度波动）
- 失败学习：玩家在失败后能通过天赋树/构筑理解获得“可见的下一次尝试方向”
- 流派可行性：每个角色至少 3 条基础流派在难度 1–3 可稳定通关（后续按难度递减）
- 选择质量：地图分叉与事件/商店形成“可讨论的抉择”，而不是“唯一最优路线”

#### Key Gameplay KPIs

| Metric | Target | Measurement Method |
|-------|--------|--------------------|
| Median run duration | ~60 min | playtest 记录 + 运行时统计 |
| First-time win rate (D1) | 低于 50%（学习驱动） | playtest 与 QA 统计（校准阈值） |
| Build diversity | 每角 ≥2 条可行流派 | 构筑标签统计 + 通关样本复盘 |
| Difficulty adoption | 10 档有梯度分布 | 难度选择分布 + 流失点分析 |

---

## Out of Scope

- 多槽存档、云同步/跨设备同步、账号体系与任何必须出网的功能（v1 明确不做）
- 任何“退出重进刷结果/重抽候选”的机制（与 ADR-0032 冲突，明确禁止）
- 联机/多人、PVP、天梯、赛事、工坊/Mod 官方支持、关卡编辑器
- 多平台（macOS/Linux/Steam Deck/主机/移动端/网页）移植
- 复杂升级树（多层、多分支、可反复重置的升级系统；v1 不做，仅包含 U1 二选一 + Ultimate 终极形态）
- 大规模叙事演出与全配音（v1 不做）

### Deferred to Post-Launch

- 额外角色、更多 Act、更多遗物/事件/卡牌扩充
- Daily Run / 挑战模式 / 周期性活动（如需要可作为后续版本内容）
- 多语言（除简体中文外）

---

## Assumptions and Dependencies

### Key Assumptions

- v1 的核心优先级：确定性契约 > 可读性与决策质量 > 构筑深度 > 视觉复杂度。
- 没有必须在 v1 支持的出网/云同步/多槽存档需求（当前优先级一致）。
- 10 档难度以数值曲线为主；共享天赋树用于鼓励试验，不与难度强绑定。
- 角色与内容规模以“可验收与可扩展的骨架”优先：先保证 3 角色各自至少 3 条基础流派可玩。

### External Dependencies

- 引擎与运行时：Godot 4.5.1 .NET、.NET 8
- 发行平台：Steam（Windows）
- 可观测性与门禁：遵循既有 ADR/基线（含日志与 release-health gate）

### Risk Factors

- 确定性/存档边界被弱化会直接破坏玩家信任与 QA 可复现性（高风险，已用 ADR-0032 冻结）。
- 内容规模（卡牌/事件/遗物）与平衡工作量容易被低估（需要严格的内容管线与数据化复盘）。
- 黑暗主题与可读性冲突：若 UI 牺牲信息呈现，会显著损害策略体验（必须坚持读数优先）。

---

## Document Information

**Document:** NewRouge - Game Design Document  
**Version:** 1.0  
**Created:** 2026-01-23  
**Author:** skyo  
**Status:** Complete

### Change Log

| Version | Date | Changes |
|--------|------|---------|
| 1.0 | 2026-01-23 | Initial GDD complete (Steps 1–14) |
