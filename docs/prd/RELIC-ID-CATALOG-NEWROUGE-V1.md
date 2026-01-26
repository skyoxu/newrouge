---
SPEC-ID: RELIC-ID-CATALOG-NEWROUGE-V1
Title: NewRouge v1 Relic ID Catalog（遗物内容身份证目录）
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

# NewRouge v1 Relic ID Catalog（遗物内容身份证目录）

目的：把遗物稳定 ID（`relic_id`）作为“投放、平衡、文案、存档与客服排障”的共同锚点。

硬口径：
- 内容稳定 ID 语法与 Translations key 派生：`_bmad-output/content-id-standard.md`
- 内容登记表（唯一真相源）：`_bmad-output/content-registry.md`

使用规则：
- 本文件是“目录视图”，用于阅读与审核；SSoT 以 `content-registry.md` 为准。
- 新增/变更遗物时：先改 `content-registry.md`，再同步本目录。

---

## 1) 目录字段（v1 约定）

- `relic_id`：`relic.<slug>`（全小写 ASCII）
- `tier`：`common | uncommon | rare | legendary`
- `tags`：用于构筑与投放（示例：`economy`、`engine`、`risk`、`healing`、`combat`）
- `synergy`：倾向联动（示例：`rage`、`debuff`、`stance`、`general`）
- `notes`：仅写设计意图，不写最终数值

---

## 2) M1 最小纵切（首批预留 ID）

| relic_id | tier | tags | synergy | notes |
|---|---|---|---|---|
| relic.ashen_hourglass | common | economy | general | 资源/节奏相关的小引擎位 |
| relic.obsidian_mirror | uncommon | engine | general | 提供构筑方向的规则型遗物（非纯数值） |
| relic.blood_oath | rare | risk,engine | rage | 强力但带代价，适配黑暗主题 |
| relic.rusted_compass | common | economy | general | 地图/节点选择相关的小增益位 |
| relic.twilight_coin | uncommon | economy | general | 与商店/消费决策联动（不触碰“商店升级”禁区） |

