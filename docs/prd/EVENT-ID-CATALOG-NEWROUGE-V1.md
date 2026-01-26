---
SPEC-ID: EVENT-ID-CATALOG-NEWROUGE-V1
Title: NewRouge 事件 ID 目录与落地优先级（v1）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge 事件 ID 目录与落地优先级（v1）

用途：把 v1 “事件内容”按稳定 ID 做目录化对账，并给“先做可玩池，再扩到 40”的落地优先级建议，避免：

- 事件池引用了不存在的 EventDef
- event_id 重复/漂移导致“同局不重复”失效
- 翻译 key 漂移（导致 UI 文案缺失或错配）

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 事件稳定 ID 的最终登记位置是：`_bmad-output/content-registry.md`；本文档用于规划与对账。

权威引用：
- v1 锁定项（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 内容稳定 ID：`_bmad-output/content-id-standard.md`
- 内容登记表：`_bmad-output/content-registry.md`
- 确定性与三选一候选集锁定：`docs/adr/ADR-0032-save-resume-determinism.md`

---

## 1) 事件 ID 命名与稳定性（硬规则）

1) 事件 ID 格式（v1）
- `event.<scope>.<slug>`
- scope：`common` / `act1` / `act2` / `act3`
- slug：全小写 ASCII，`[a-z0-9_]+`，用 `_` 分词

2) ID 不得复用/重命名
- 发布后不得重命名；需要改语义时只能“新增新 ID + 旧 ID 墓碑/迁移映射”。

3) 同局不重复边界
- 同一 run 内事件按“定义 ID”去重（event_id 不重复）。

4) 翻译 key 派生
- `event.<scope>.<slug>.title`
- `event.<scope>.<slug>.desc`
- `event.<scope>.<slug>.opt.<n>.label`
- `event.<scope>.<slug>.opt.<n>.result`

---

## 2) v1 事件规划口径（规模与分布）

- 总量锁定：40 个事件（见 `docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`）。
- 分布建议（可调整，但总量与 scope 结构不变）：
  - `common`：8（跨 Act 通用题材，用于缓冲重复体感）
  - `act1`：10（教学与低压）
  - `act2`：11（强化 build 分岔与代价选择）
  - `act3`：11（高压与史诗机会：含 Ultimate 机会）

注：
- “特殊事件：U1 路线重选”与“Ultimate 机会”建议分别至少 1 个（可复用同一个事件，但不推荐把两者合并为同一入口）。
- 事件内 UI 行为不得推进 RNG；如事件包含三选一奖励，必须遵循 ADR-0032 的候选集锁定。

---

## 3) 落地优先级建议（从 10 → 20 → 40）

### 3.1 里程碑 A：10 个可用事件（最小可玩池）

目标：支撑 Act1/Act2 的最小多样性与教学，不引入高复杂度结算。

建议优先覆盖的“事件能力面”（不是题材）：
1) 资源交换：金币 ↔ 生命/卡牌污染/遗物（至少 2）
2) 卡组修剪：移除/转换/抽取（至少 1）
3) 风险换强：受诅咒/负面状态 ↔ 强奖励（至少 2）
4) build 分岔：提供明确的流派倾向奖励（至少 2）
5) 叙事缓冲：低强度事件（至少 1，且不得“无变化”伪事件）

### 3.2 里程碑 B：20 个可用事件（稳定量产池）

目标：覆盖全部 Act 的基础题材，并开始引入“策略代价”组合（但仍保持可解释）。

新增能力面建议：
- 敌方 debuff 教学强化（刺客向）
- 怒气 buff 代价/收益选择（战士向）
- 姿态切换的代价与爆发机会（德鲁伊向）
- 小型史诗机会（非 Ultimate）：高代价换强遗物/强牌

### 3.3 里程碑 C：40 个事件（v1 交付池）

目标：补齐 Act3 的史诗体验，并加入稀有机会（含 Ultimate）与更强的“黑暗代价”表达。

新增能力面建议：
- Ultimate 机会（史诗事件或 Boss 后置）
- U1 路线重选事件（仅改路线，不推进 RNG；离开事件时以最终选择为准）
- run 级规则改变（短期/永久）：必须能被存档与确定性复现，并且在 UI 有明确提示（可见文本走 Translations）

---

## 4) v1 事件 ID 预留目录（可直接用于登记表）

说明：
- 以下为“预留 ID”，用于避免后续作者各起各的名字导致冲突。
- 实际落地前，必须把选中的 event_id 逐条登记到 `_bmad-output/content-registry.md`（并补齐 translation_key_prefix）。

### 4.1 common（8）

- `event.common.wandering_scribe`
- `event.common.shattered_mirror`
- `event.common.blood_tithe`
- `event.common.whispering_fountain`
- `event.common.forgotten_cart`
- `event.common.black_market_note`
- `event.common.echoing_shrine`
- `event.common.lost_satchel`

### 4.2 act1（10）

- `event.act1.foggy_crossroads`
- `event.act1.abandoned_outpost`
- `event.act1.cracked_altar`
- `event.act1.sickly_garden`
- `event.act1.rusty_shrine`
- `event.act1.river_toll`
- `event.act1.torn_map`
- `event.act1.wounded_scout`
- `event.act1.stray_relic`
- `event.act1.cursed_lantern`

### 4.3 act2（11）

- `event.act2.silent_market`
- `event.act2.tainted_workbench`        # 卡组操作与风险交换
- `event.act2.shrine_of_exchange`       # 资源 ↔ 强度交换
- `event.act2.ritual_circle`
- `event.act2.broken_contract`
- `event.act2.fungal_chamber`
- `event.act2.shadow_patrol`
- `event.act2.trial_of_discipline`
- `event.act2.gilded_coffin`
- `event.act2.hollow_library`
- `event.act2.mercy_or_price`           # 明确的代价选项

### 4.4 act3（11）

- `event.act3.drowned_cathedral`
- `event.act3.obsidian_gate`
- `event.act3.forbidden_archive`
- `event.act3.angelic_bargain`          # 高代价高回报
- `event.act3.stolen_soul`
- `event.act3.black_sun_rite`
- `event.act3.throne_of_thorns`
- `event.act3.boss_trophy`
- `event.act3.ultimate_chance`          # 终极形态机会（稀有）
- `event.act3.reforge_choice`           # U1 路线重选（稀有，必须确定性）
- `event.act3.last_sanctuary`

---

## 5) 与确定性/存档的对齐规则（必须遵守）

1) 若事件提供“三选一/多选一奖励”：
- 必须落盘候选集锁定字段（stable_ids + display_order + provenance）
- 退出重进候选集与顺序不变

2) 若事件提供“U1 路线重选”：
- 事件内允许无限次切换，但不得推进 RNG
- 离开事件时以最终选择写入卡牌实例升级字段（见 `docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`）
