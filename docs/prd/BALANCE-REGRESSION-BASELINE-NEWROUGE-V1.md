---
SPEC-ID: BALANCE-REGRESSION-BASELINE-NEWROUGE-V1
Title: NewRouge v1 平衡与内容回归基线（最小必跑包）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge v1 平衡与内容回归基线（最小必跑包）

用途：当 v1 调整任何“数值/权重/投放/升级/事件/遗物/天赋”时，提供一套必须回归的最小基线，避免：
- 退出重进不刷结果被悄悄破坏（候选集漂移、UI 推进 RNG）
- 内容扩展引入系统级禁区（无限、锁死、常驻免疫）
- 事件投放与“同局不重复”规则失效

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

权威引用：
- v1 锁定表（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 存档/确定性：`docs/adr/ADR-0032-save-resume-determinism.md`
- 事件 ID 目录：`docs/prd/EVENT-ID-CATALOG-NEWROUGE-V1.md`
- 内容登记表：`_bmad-output/content-registry.md`
- 组合禁区：`docs/prd/CONTENT-POWER-BOUNDS-AND-COMBO-RULES-NEWROUGE-V1.md`
- 日志与取证口径：`project-context.md`

---

## 0) 什么时候必须跑（触发条件）

满足任一条件，就必须跑完本文“最小必跑包”：
- 新增/修改任意卡牌（含 U1/Ultimate）或其升级路线描述
- 新增/修改任意遗物/天赋（尤其是改变规则与权重的）
- 新增/修改任意事件（effects、奖励、投放权重、同局去重逻辑）
- 调整任意奖励三选一/多选一生成规则（候选集、顺序、权重）
- 调整存档边界或 Continue 行为（高风险）

---

## 1) 回归前置条件（统一口径）

每次回归记录必须写清：
- `date`
- `runner`
- `game_version`
- `seed`（若系统支持固定 seed，必须记录）
- `difficulty`（1..10）
- `hero`（warrior/assassin/druid）
- `run_length_minutes`（目标 ~60，若是快速回归可备注）
- `notes`

证据最小集（必须归档到 `logs/**`）：
- 关键截图或文本记录（事件/奖励三选一/升级选择/Continue 行为）
- 若涉及确定性：同一存档点重复两次的“候选集一致性”对比证据

---

## 2) 最小必跑包（v1）

> v1 是 3 Act + 60 分钟单局目标，但回归允许“短路跑法”。关键是覆盖风险点，不是通关。

### BR-001：三选一候选集锁定（退出重进不刷）

目标：
- 同一节点触发三选一奖励：退出到主菜单 → Continue → 候选集与顺序完全一致。

Pass：
- 候选集稳定（stable ids + 顺序）且可截图取证；重新选择不会导致“重抽”。

### BR-002：战斗中退出重进回到战斗初始状态

目标：
- 战斗中途退出：Continue 后回到战斗初始状态（不是中间态）。

Pass：
- 明确回到战斗初始；不出现中间态恢复。

### BR-003：休整免费升级（U1 二选一不可逆）

目标：
- 休整节点选择升级：可免费升级 1 张；选择 Route A/B 后不可逆。

Pass：
- 离开升级入口后不可改回；存档字段口径保持一致（tier/route）。

### BR-004：特殊事件内 U1 路线重选（无限切换但不推进 RNG）

目标：
- 在事件内对同一张已 U1 卡多次切换路线，离开事件后以最终路线为准。
- 过程中不改变其他随机结果（例如后续三选一候选集不因“切换次数”漂移）。

Pass：
- 最终路线正确落地；候选集不漂移。

### BR-005：Ultimate 机会（稀有、不可逆、不可换路线）

目标：
- 触发 Ultimate 机会后：可从 tier=0 直接变 tier=2；不可再升级；不可换路线。

Pass：
- tier/route 约束成立（tier=2 route=null）。

### BR-006：事件同局不重复

目标：
- 记录一次 run 的 event_id 序列，验证同局不重复按 event_id 生效。

Pass：
- event_id 无重复（允许跨局重复）。

---

## 3) 快速判定：哪些变化需要“扩展回归”

若本次改动涉及以下项，除最小必跑包外追加回归：
- 修改事件投放权重：追加跑“同 Act 连续 10 次事件抽取的分布记录”（验证无集中刷屏、且同局不重复不被破坏）
- 修改升级路线/文案：追加跑“升级选择界面可解释性检查”（不可逆提示、Translations key 覆盖）
- 修改遗物/天赋触发器：追加跑“触发链风险排查”（验证不触达组合禁区）

