---
title: "Content Registry (SSoT)"
project: "newrouge"
date: "2026-01-23"
author: "skyo"
purpose: "Prevent ID/key drift and missing translations"
references:
  - _bmad-output/content-id-standard.md
  - project-context.md
---

# 内容登记表（SSoT）

目标：把“内容稳定 ID + 翻译 key + 升级路线/终极形态”登记成唯一真相源，避免后续进入 game-design 后出现：

- ID 冲突（重复/误拼/大小写混用）
- 翻译 key 漏配或漂移
- 升级路线与终极形态缺口导致实现/测试无法对齐

使用规则（硬口径）：

- 新增任何卡牌/遗物/事件/敌人/天赋前，必须先在本表登记。
- 发布后 ID 不得重命名；如必须调整，只能新增新 ID，并提供迁移/别名映射。

---

## Cards（按角色）

| content_id | hero | rarity | type | has_u1a | has_u1b | has_ultimate | translation_key_prefix | notes |
|---|---|---|---|---|---|---|---|---|
| card.warrior.cleave | warrior | common | attack | y | y | y | card.warrior.cleave | M1 starter |
| card.warrior.guard | warrior | common | skill | y | y | y | card.warrior.guard | M1 starter |
| card.warrior.rage_surge | warrior | common | skill | y | y | y | card.warrior.rage_surge | M1 starter |
| card.warrior.bloodrush | warrior | common | attack | y | y | y | card.warrior.bloodrush | M1 starter |
| card.warrior.taunt | warrior | common | skill | y | y | y | card.warrior.taunt | M1 starter |
| card.warrior.shield_wall | warrior | uncommon | skill | y | y | y | card.warrior.shield_wall | M1 starter |
| card.warrior.overpower | warrior | uncommon | attack | y | y | y | card.warrior.overpower | M1 starter |
| card.warrior.battlecry | warrior | common | skill | y | y | y | card.warrior.battlecry | M1 starter |
| card.warrior.crush | warrior | common | attack | y | y | y | card.warrior.crush | M1 starter |
| card.warrior.relentless | warrior | rare | power | y | y | y | card.warrior.relentless | M1 starter |
| card.assassin.quick_cut | assassin | common | attack | y | y | y | card.assassin.quick_cut | M1 starter |
| card.assassin.poison_dart | assassin | common | skill | y | y | y | card.assassin.poison_dart | M1 starter |
| card.assassin.crippling_strike | assassin | common | attack | y | y | y | card.assassin.crippling_strike | M1 starter |
| card.assassin.shadow_step | assassin | common | skill | y | y | y | card.assassin.shadow_step | M1 starter |
| card.assassin.bleed_edge | assassin | common | attack | y | y | y | card.assassin.bleed_edge | M1 starter |
| card.assassin.envenom | assassin | uncommon | power | y | y | y | card.assassin.envenom | M1 starter |
| card.assassin.silence | assassin | uncommon | skill | y | y | y | card.assassin.silence | M1 starter |
| card.assassin.mark_target | assassin | common | skill | y | y | y | card.assassin.mark_target | M1 starter |
| card.assassin.venom_burst | assassin | common | attack | y | y | y | card.assassin.venom_burst | M1 starter |
| card.assassin.dark_contract | assassin | rare | power | y | y | y | card.assassin.dark_contract | M1 starter |
| card.druid.stance_shift | druid | common | skill | y | y | y | card.druid.stance_shift | M1 starter |
| card.druid.thorn_ward | druid | common | skill | y | y | y | card.druid.thorn_ward | M1 starter |
| card.druid.root_bind | druid | common | skill | y | y | y | card.druid.root_bind | M1 starter |
| card.druid.feral_bite | druid | common | attack | y | y | y | card.druid.feral_bite | M1 starter |
| card.druid.barkskin | druid | common | power | y | y | y | card.druid.barkskin | M1 starter |
| card.druid.moonlit_growth | druid | uncommon | skill | y | y | y | card.druid.moonlit_growth | M1 starter |
| card.druid.sunflare | druid | uncommon | attack | y | y | y | card.druid.sunflare | M1 starter |
| card.druid.wild_call | druid | common | skill | y | y | y | card.druid.wild_call | M1 starter |
| card.druid.stoneform | druid | common | power | y | y | y | card.druid.stoneform | M1 starter |
| card.druid.surge_bloom | druid | rare | power | y | y | y | card.druid.surge_bloom | M1 starter |

---

## Curses（诅咒卡，独立池）

说明：
- 诅咒卡是独立卡类与独立池：`card.curse.<slug>`（见 `_bmad-output/content-id-standard.md`）
- 不可升级、无路线、无终极形态（单一形态）
- M1 必须具备移除途径（商店服务/事件/休整 入口）

| content_id | removable | translation_key_prefix | notes |
|---|---|---|---|
| card.curse.blood_debt | y | card.curse.blood_debt | M1 dark cost (HP loss) |
| card.curse.chains_of_regret | y | card.curse.chains_of_regret | M1 dark cost (gain curse) |

约束：

- `translation_key_prefix` 必须等于 `content_id`（避免 key 漂移）
- `has_u1a/has_u1b/has_ultimate` 用 `y/n` 标记，并作为内容验收清单的一部分

---

## Relics

| content_id | tier | translation_key_prefix | notes |
|---|---|---|---|
| relic.ashen_hourglass | common | relic.ashen_hourglass | M1 slice |
| relic.obsidian_mirror | uncommon | relic.obsidian_mirror | M1 slice |
| relic.blood_oath | rare | relic.blood_oath | M1 slice |
| relic.rusted_compass | common | relic.rusted_compass | M1 slice |
| relic.twilight_coin | uncommon | relic.twilight_coin | M1 slice |

---

## Events

| content_id | scope | unique_in_run | translation_key_prefix | notes |
|---|---|---|---|---|
| event.act1.example_event | act1 | y | event.act1.example_event | 示例：同局不重复 |

---

## Enemies

| content_id | scope | kind | notes |
|---|---|---|---|
| enemy.act1.example_enemy | act1 | normal | 示例 |

---

## Talents（共享天赋树）

| content_id | tier | translation_key_prefix | notes |
|---|---|---|---|
| talent.t1.example_talent | t1 | talent.t1.example_talent | 示例 |
