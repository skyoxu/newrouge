---
SPEC-ID: CONTENT-AUTHORING-ENTRY-NEWROUGE-V1
Title: NewRouge 内容作者单一入口（v1）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge 内容作者单一入口（v1）

用途：给“内容作者（卡牌/遗物/事件/天赋/敌人）”提供唯一入口。只要按本文顺序走，就能产出可登记、可翻译、可验收、可回归的内容增量，并且不破坏 NewRouge v1 的锁定口径（确定性、存档边界、升级系统等）。

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

权威引用（不重复发明规则）：
- v1 锁定表（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 内容稳定 ID 与翻译 key：`_bmad-output/content-id-standard.md`
- 内容登记表（SSoT）：`_bmad-output/content-registry.md`
- 存档/退出重进/三选一锁定：`docs/adr/ADR-0032-save-resume-determinism.md`
- 项目硬口径（Translations、日志、门禁）：`project-context.md`
- 组合禁区（防无限/锁死/常驻免疫）：`docs/prd/CONTENT-POWER-BOUNDS-AND-COMBO-RULES-NEWROUGE-V1.md`

---

## 0) 先读 3 份（不读就容易跑偏）

1) `docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`（尤其：存档/确定性、商店不升级、U1/Ultimate 规则）  
2) `_bmad-output/content-id-standard.md`（ID 语法与翻译 key 派生）  
3) `docs/prd/CONTENT-POWER-BOUNDS-AND-COMBO-RULES-NEWROUGE-V1.md`（组合禁区与自检清单）  

你必须记住的 3 条“不可违背”口径（内容侧最常见踩坑）：
- 退出重进不刷结果：三选一候选集必须锁定；UI 行为不得推进 RNG（见 ADR-0032）。
- 可见文本不硬编码：所有 UI 文案走 `Game.Godot/Translations`，且 key 由内容 ID 派生（见 `project-context.md`）。
- 商店永不升级：升级只发生在“休整节点”或“特定事件”；U1 二选一不可逆；Ultimate 稀有不可逆（见 SSoT）。

---

## 1) 你要做的事（按依赖顺序）

### 1.1 新增卡牌（Card）

依赖链（先登记后创作）：
1) 选择 `content_id`：`card.<hero>.<slug>`（见 `_bmad-output/content-id-standard.md`）
2) 在 `_bmad-output/content-registry.md` 的 Cards 表登记：
   - `content_id` / `hero` / `rarity` / `type`
   - `has_u1a/has_u1b/has_ultimate`（y/n）
   - `translation_key_prefix`（必须等于 `content_id`）
3) 规划翻译 key（不写实现，只写必须有的 key）：
   - base：`.name/.desc`
   - U1：`.u1a.name/.u1a.desc` 与 `.u1b.name/.u1b.desc`（若有）
   - Ultimate：`.ultimate.name/.ultimate.desc`（若有）

硬规则（v1）：
- 每角色 30 张基础卡（不含升级版本）；升级不产生新的 card_id（升级态在实例字段里表达）。
- 任意“触发器链/复制牌/无限资源”都必须先对照组合禁区（见 `CONTENT-POWER-BOUNDS...`）。

### 1.2 新增卡牌升级（U1/Ultimate 的内容补齐）

原则：升级是“同一张卡的变体表现”，不是新的内容 ID。

U1（常规升级）硬规则：
- 所有卡牌的 U1 必须 Route A/B 二选一，不可逆（从玩法与存档都不可逆）。

U1 路线重选事件（特殊事件）硬规则：
- 事件内允许无限次切换；离开事件以最终选择为准；该过程不得推进 RNG。

Ultimate（终极形态）硬规则：
- 稀有机会获得；可从未升级卡直接进阶；不可逆；不可再升级；不可换路线。

存档字段口径（内容侧必须理解）：
- `upgrade_tier: 0|1|2`；`upgrade_route: null|a|b`（tier=2 时 route 必须为 null）

### 1.3 新增遗物（Relic）

依赖链：
1) 选择 `content_id`：`relic.<slug>`
2) 在 `_bmad-output/content-registry.md` 的 Relics 表登记（key prefix 必须等于 id）
3) 规划翻译 key：`.name/.desc`

硬规则（v1）：
- v1 首发仅遗物系统；数量目标 20。
- 遗物不得引入组合禁区（无限资源、常驻免疫、控制链）。

### 1.4 新增事件（Event）

依赖链：
1) 选择 `event_id`：`event.<scope>.<slug>`（scope：common/act1/act2/act3）
2) 在 `_bmad-output/content-registry.md` 的 Events 表登记：
   - `content_id` / `scope` / `unique_in_run=y`
3) 在 `docs/prd/EVENT-ID-CATALOG-NEWROUGE-V1.md` 对齐是否属于“预留目录/已落地目录”
4) 规划翻译 key（必须可覆盖 UI）：
   - `.title/.desc`
   - `.opt.<n>.label`（选项名）
   - `.opt.<n>.result`（结果摘要）

硬规则（v1）：
- 同局不重复按 event_id 去重（不是“事件类型”去重）。
- 如事件含“三选一/多选一奖励”：必须满足候选集锁定（stable_ids + display_order + provenance）。

### 1.5 新增天赋（Talent，共享天赋树）

依赖链：
1) 选择 `content_id`：`talent.<tier>.<slug>`
2) 在 `_bmad-output/content-registry.md` 的 Talents 表登记（key prefix 必须等于 id）
3) 规划翻译 key：`.name/.desc`

硬规则（v1）：
- 所有角色共享同一棵天赋树，且可无条件重置。
- 天赋尽量改变“规则与权重”，避免纯数值堆叠成为唯一玩法。

---

## 2) 内容提交前自检（最小必过）

> 这份自检用于“提交内容前 3 分钟止损”，不替代正式验收清单。

1) 是否已登记稳定 ID（content-registry 里可查到）？  
2) 是否已规划翻译 key（由 ID 派生）？  
3) 是否可能破坏确定性（UI 推进 RNG、候选集不锁定、退出重进可刷）？  
4) 是否触达组合禁区（无限资源/递归触发/控制链/常驻免疫）？  
5) 是否踩到锁定项（商店升级、战斗中保存中间态、U1 可逆/Ultimate 可换路线）？  

