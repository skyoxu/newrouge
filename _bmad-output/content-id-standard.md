---
title: "Content Stable ID Standard"
project: "newrouge"
date: "2026-01-23"
author: "skyo"
ssot:
  - project-context.md
---

# 内容稳定 ID 规范（v1）

目标：让卡牌/遗物/事件/敌人/天赋等内容在迭代中“可引用、可回归、可迁移”，避免因为重命名导致存档/翻译/事件池与测试全部崩坏。

这份规范是给设计与内容制作使用的；实现侧硬口径以 `project-context.md` 为准。

---

## 1) 语法（硬规则）

- 全小写 ASCII
- 用 `.` 分层（禁止用 `/`）
- slug 只允许 `[a-z0-9_]+`
- 禁止空格、中文、大小写混用、特殊符号（例如 `-`）
- 一旦发布不得重命名；如必须调整，只能“新增新 ID + 旧 ID 做别名/迁移映射”

---

## 2) 命名空间（v1 约定）

### 2.1 Hero（角色）

- `hero.warrior`
- `hero.assassin`
- `hero.druid`

### 2.2 Card（卡牌）

格式：`card.<hero>.<slug>`

示例：
- `card.warrior.strike`
- `card.assassin.poisoned_blade`
- `card.druid.stance_shift`

### 2.2.1 Curse Card（诅咒卡，v1）

格式：`card.curse.<slug>`

说明：
- 诅咒卡是独立卡类与独立池（不属于任一 hero 卡池）。
- 诅咒卡用于表达“黑暗代价”，通常由事件/代价注入牌组。
- 诅咒卡不可升级、无路线、无终极形态（单一形态）。

示例：
- `card.curse.blood_debt`
- `card.curse.chains_of_regret`

### 2.3 Relic（遗物）

格式：`relic.<slug>`

示例：
- `relic.blood_oath`
- `relic.shadow_lens`

### 2.4 Event（事件）

格式（推荐）：`event.<scope>.<slug>`

- scope：`common` / `act1` / `act2` / `act3`

示例：
- `event.common.strange_merchant`
- `event.act1.bandits`

### 2.5 Enemy（敌人）

格式：`enemy.<scope>.<slug>`

示例：
- `enemy.act1.cultist`
- `enemy.act3.final_boss`

### 2.6 Talent（天赋）

格式：`talent.<tier>.<slug>`

示例：
- `talent.t1.deck_thinning`
- `talent.t3.relic_synergy`

### 2.7 Status（状态，系统级稳定 ID）

格式：`status.<slug>`

说明：
- 状态属于“系统级稳定 ID”，用于结算顺序、触发器稳定排序（`stable_id`）、存档与复盘。
- 状态不是卡牌/遗物/事件等内容 ID，但同样必须稳定、全小写 ASCII、可长期引用。

示例：
- `status.strength`
- `status.weak`
- `status.bloodbeat`
- `status.vulnerable`

---

## 3) Translations key 派生规则（硬规则）

所有可见文本必须从 Translations 获取；key 必须由内容 ID 派生，避免“文本 key 漂移”：

- `card.<hero>.<slug>.name`
- `card.<hero>.<slug>.desc`
- `card.<hero>.<slug>.u1a.name`（常规升级 U1 Route A 显示名）
- `card.<hero>.<slug>.u1a.desc`（常规升级 U1 Route A 描述）
- `card.<hero>.<slug>.u1b.name`（常规升级 U1 Route B 显示名）
- `card.<hero>.<slug>.u1b.desc`（常规升级 U1 Route B 描述）
- `card.<hero>.<slug>.ultimate.name`（终极形态显示名）
- `card.<hero>.<slug>.ultimate.desc`（终极形态描述）
- 诅咒卡（单形态）：
  - `card.curse.<slug>.name`
  - `card.curse.<slug>.desc`
- `relic.<slug>.name`
- `relic.<slug>.desc`
- `event.<scope>.<slug>.title`
- `event.<scope>.<slug>.desc`
- `event.<scope>.<slug>.opt.<n>.label`
- `event.<scope>.<slug>.opt.<n>.result`

状态（system status）：
- `status.<slug>.name`
- `status.<slug>.desc`

---

## 4) 唯一性与冲突处理

- 新增内容前必须检查 ID 全局唯一（至少：卡牌/遗物/事件/敌人/天赋各自命名空间内唯一）
- 同名内容重做时禁止复用旧 ID（除非语义完全一致且不会破坏存档/回归）
- 删除内容必须保留“墓碑记录”（deprecate 列表），防止存档/引用悬空

---

## 5) 升级态表示（v1）

v1 有两类升级态，但升级态都不是新的“卡牌内容 ID”：

- **内容 ID 不变**：仍是 `card.<hero>.<slug>`
- **卡牌实例携带升级状态**：
  - `upgrade_tier = 0|1|2`（0=base，1=U1，2=ultimate）
  - `upgrade_route = null|a|b`（仅当 tier=1 有效；tier=2 必须为 null）
- **UI 文本按升级状态派生 key**：
  - U1：`card.<hero>.<slug>.u1a.*` / `card.<hero>.<slug>.u1b.*`
  - Ultimate：`card.<hero>.<slug>.ultimate.*`

这样做的目的：

- 存档更稳定：不因为“升级态改名/新增”破坏兼容
- 内容更可控：升级只改变同一张卡的表现与规则差异

---

## 6) 最小存档字段口径（升级系统）

为保证“退出重进不刷结果”和可复现，卡牌实例在存档中必须包含最小升级字段（与 UI 展示解耦）：

- `upgrade_tier: 0|1|2`（0=base，1=U1，2=ultimate）
- `upgrade_route: null|"a"|"b"`

硬规则：

- 当 `upgrade_tier=0` 时，`upgrade_route` 必须为 `null`
- 当 `upgrade_tier=1` 时，`upgrade_route` 必须为 `"a"` 或 `"b"`
- 当 `upgrade_tier=2` 时，`upgrade_route` 必须为 `null`（终极形态不可换路线）

说明：

- “特殊事件内无限次切换路线”属于纯玩家输入；离开事件时以最终选择写入上述字段即可。
- 终极形态可从未升级卡直接进阶：即 `upgrade_tier` 从 `0` 直接变为 `2`，且 `upgrade_route` 仍为 `null`。

### 6.1 诅咒卡（Curse）的升级字段约束

- 诅咒卡不可升级：
  - `upgrade_tier` 必须为 `0`
  - `upgrade_route` 必须为 `null`
