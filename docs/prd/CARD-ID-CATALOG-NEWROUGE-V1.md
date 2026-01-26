---
SPEC-ID: CARD-ID-CATALOG-NEWROUGE-V1
Title: NewRouge v1 Card ID Catalog（卡牌内容身份证目录）
Status: Draft
Owner: skyo
Last Updated: 2026-01-25
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
SSoT:
  - _bmad-output/content-registry.md
  - _bmad-output/content-id-standard.md
ADR-Refs:
  - ADR-0033-card-identity-and-forms
---

# NewRouge v1 Card ID Catalog（卡牌内容身份证目录）

目的：把“卡牌稳定 ID（`card_id`）”作为内容生产与实现对齐的共同锚点，避免后续出现：
- `card_id` 重命名导致存档/翻译 key/回归基线崩坏
- 卡牌升级形态（U1A/U1B/Ultimate）被误实现为“换 ID”
- 角色/稀有度/投放池口径漂移，导致无法做确定性候选集锁定与验收

硬口径：
- 内容稳定 ID 语法与 Translations key 派生：`_bmad-output/content-id-standard.md`
- 内容登记表（唯一真相源）：`_bmad-output/content-registry.md`
- 同一 `card_id` 四形态（Base/U1A/U1B/Ultimate）：`docs/adr/ADR-0033-card-identity-and-forms.md`

使用规则：
- 本文件是“目录视图”，用于阅读与审核；SSoT 以 `content-registry.md` 为准。
- 新增/变更卡牌时：先改 `content-registry.md`，再同步本目录（避免“目录存在但登记表缺失”的口径漂移）。

---

## 1) 目录字段（v1 约定）

最小字段（必须可由登记表对齐）：
- `card_id`：`card.<hero>.<slug>`（全小写 ASCII，`.` 分层）
- `hero`：`warrior | assassin | druid`
- `rarity`：`common | uncommon | rare | legendary`（如需“精英卡”概念，优先用 `rare` 并用标签区分投放来源）
- `type`：`attack | skill | power`（仅用于设计对齐；具体实现可再细化）
- `starter_deck`：是否属于开局 10 张（用于“10 张起始牌组”口径）
- `has_u1a/has_u1b/has_ultimate`：v1 统一为 `y/y/y`
- `tags`：用于构筑与投放（示例：`rage`、`debuff`、`stance`、`finisher`、`engine`）

---

## 2) M1 最小纵切（首批预留 ID）

说明：
- 这是一批“纵切最小集”的预留稳定 ID，用于推进第一轮可玩闭环与后续任务拆解。
- 玩家可见名称与描述必须通过 Translations 提供；本文件不定义最终文案。

### 2.1 Warrior（起始牌组 10）

| card_id | rarity | type | starter_deck | tags | notes |
|---|---|---|---|---|---|
| card.warrior.cleave | common | attack | y | rage | 近战群体向；与怒气窗口联动 |
| card.warrior.guard | common | skill | y | rage | 防御向；与怒气维持/转化联动 |
| card.warrior.rage_surge | common | skill | y | rage,engine | 提供怒气来源或加速手段 |
| card.warrior.bloodrush | common | attack | y | rage | 以代价换取爆发（黑暗代价表达） |
| card.warrior.taunt | common | skill | y | control | 提供节奏控制或目标牵引 |
| card.warrior.shield_wall | uncommon | skill | y | engine | 偏引擎向防御能力 |
| card.warrior.overpower | uncommon | attack | y | finisher | 爆发终结向 |
| card.warrior.battlecry | common | skill | y | engine | 牌组/抽牌/临时增益入口 |
| card.warrior.crush | common | attack | y | rage | 单体重击向 |
| card.warrior.relentless | rare | power | y | engine | 起始牌组中唯一稀有位（用于定义流派方向） |

### 2.2 Assassin（起始牌组 10）

| card_id | rarity | type | starter_deck | tags | notes |
|---|---|---|---|---|---|
| card.assassin.quick_cut | common | attack | y | debuff | 基础伤害入口，带轻度 debuff |
| card.assassin.poison_dart | common | skill | y | debuff | 叠毒向 debuff 入口 |
| card.assassin.crippling_strike | common | attack | y | debuff,control | 减速/虚弱等控制类 debuff 入口 |
| card.assassin.shadow_step | common | skill | y | engine | 资源/节奏调整入口（不定义实现细节） |
| card.assassin.bleed_edge | common | attack | y | debuff | 流血向 debuff 入口 |
| card.assassin.envenom | uncommon | power | y | debuff,engine | debuff 引擎向增强 |
| card.assassin.silence | uncommon | skill | y | control | 抑制/封锁类 debuff（由敌方体系决定） |
| card.assassin.mark_target | common | skill | y | finisher | 终结增幅入口 |
| card.assassin.venom_burst | common | attack | y | finisher,debuff | 引爆/结算 debuff 的爆发入口 |
| card.assassin.dark_contract | rare | power | y | engine | 起始牌组稀有位：强力但带代价的引擎方向 |

### 2.3 Druid（起始牌组 10）

| card_id | rarity | type | starter_deck | tags | notes |
|---|---|---|---|---|---|
| card.druid.stance_shift | common | skill | y | stance | 姿态切换入口（定义“切换成本/收益”） |
| card.druid.thorn_ward | common | skill | y | stance | 防御/反伤向持久 buff 入口 |
| card.druid.root_bind | common | skill | y | control | 控制向（定点爆发铺垫） |
| card.druid.feral_bite | common | attack | y | finisher | 单体爆发入口（与姿态联动） |
| card.druid.barkskin | common | power | y | stance,engine | 持久 buff 的引擎位 |
| card.druid.moonlit_growth | uncommon | skill | y | engine | 资源/抽牌/成长向入口 |
| card.druid.sunflare | uncommon | attack | y | finisher | 爆发向入口 |
| card.druid.wild_call | common | skill | y | engine | 牌组/召唤/临时资源入口（不锁实现） |
| card.druid.stoneform | common | power | y | stance | 姿态相关的持久防御/代价表达 |
| card.druid.surge_bloom | rare | power | y | engine | 起始牌组稀有位：定义核心流派方向 |

---

## 3) 诅咒卡（Curse，独立池，v1）

口径（v1）：
- 诅咒卡是独立卡类与独立池：`card.curse.<slug>`
- 不可升级、无路线、无终极形态（单一形态）
- M1 必须具备移除途径：商店服务 / 事件 / 休整（多选一选项之一）

M1 预留稳定 ID（用于事件示范与验收）：

| card_id | removable | notes |
|---|---|---|
| card.curse.blood_debt | y | M1 dark cost example: HP loss |
| card.curse.chains_of_regret | y | M1 dark cost example: gain curse card |
