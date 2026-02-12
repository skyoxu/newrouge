=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_BEGIN ===
{
  "schema": "taskmaster-prd-part/v1",
  "generated_at_utc": "2026-01-29T12:44:47+00:00",
  "rel_path": ".taskmaster/docs/prd_parts/50-mechanics-edge-cases.md",
  "title": "docs/prd/MECHANICS-EDGE-CASES-SSOT-NEWROUGE-V1.md",
  "sha256": "68a0cb0ce4d8a3aa1183b985b039242533d9de010b194062a24f8306babcd1fd",
  "bytes": 12271
}
=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_END ===

---
SPEC-ID: MECHANICS-EDGE-CASES-SSOT-NEWROUGE-V1
Title: NewRouge v1 机制边界条件与反例 SSOT
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge v1 机制边界条件与反例 SSOT

用途：把最容易出现歧义/返工的“边界条件”集中写死，供策划/QA/研发统一对齐。本文不新增系统，只收敛口径与验收反例。

范围：v1（单人卡牌 roguelike；允许随机但必须可复现；允许退出重进但不刷结果；单槽 autosave；战斗中不存中间态）。

权威引用：
- v1 锁定表（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 存档/确定性：`docs/adr/ADR-0032-save-resume-determinism.md`
- 内容稳定 ID 与升级态字段：`_bmad-output/content-id-standard.md`
- 项目硬口径（Translations、日志、门禁）：`project-context.md`

---

## 1) 存档边界（必须一致）

1.1 节点前存档
- 进入“节点”之前保存入口前状态；进入节点后不再更新到下一节点完成。

1.2 战斗存档
- 进入战斗后保存“战斗初始状态”。
- 战斗过程中绝不保存任何中间态。

反例（出现任意一条即视为口径破坏）：
- 战斗中出现“继续本回合/继续到中途”的恢复语境
- 崩溃恢复回到“战斗中间态”

---

## 2) 退出重进与确定性（反刷随机）

2.1 定义
- “退出重进不刷结果”= 同一存档点 + 同一输入序列 → 同一结果（允许玩家做不同选择导致不同结果，但不允许通过重启重抽）。

2.2 三选一/多选一候选集锁定（Offer locking）
- 首次生成即落盘：`stable_ids[] + display_order[] + provenance`
- 退出重进候选集与顺序完全一致（含顺序）
- 允许重新选择，但不得重抽/重滚

2.3 UI 不推进 RNG
- 纯 UI 行为（切卡、查看详情、在事件内来回切换升级路线）不得推进 RNG。

反例：
- 退出重进后，同一节点的三选一候选集变了
- 仅通过“打开/关闭面板/切换标签页”改变了下一次掉落候选

---

## 3) 事件同局不重复（边界写死）

3.1 同局不重复的判定对象
- 按事件“定义 ID”（`event.<scope>.<slug>`）去重，不得用“事件类型”偷换边界。

反例：
- 同一 run 里出现两次相同 event_id（即使选项不同也不允许）

---

## 4) 卡牌升级系统（边界写死）

4.1 商店升级（禁止）
- 商店任何时候都不提供升级服务。

4.2 U1（二选一，不可逆）
- 升级时必须在 Route A/B 二选一，选择不可逆（离开升级入口后不可撤销）。

4.3 特殊事件：路线重选
- 事件内允许无限次切换路线；离开事件时以最终选择为准；该过程不得推进 RNG。

4.4 Ultimate（终极形态）
- 每张卡 1 个终极形态；可从未升级卡直接进阶；不可逆；不可再升级；不可换路线。

4.5 存档字段（最小口径）
- `upgrade_tier: 0|1|2`；`upgrade_route: null|a|b`（tier=2 时必须为 null）

反例：
- 出现“U1 可反悔/可撤销”的 UI/文案
- Ultimate 后还能再升或还能换路线
- 用新 card_id 表达升级（导致存档与翻译漂移）

---

## 4.6 手牌上限与首回合发牌（边界写死）

4.6.1 手牌上限
- 手牌上限永远是 10，且不被任何因素改变。

4.6.2 首回合 `innate`（第一回合在手牌）
- `innate` 卡牌实例在“每场战斗首回合”进入手牌（不推进 RNG）。
- `innate` 可使首回合手牌数量超过“每回合默认抽牌数=4”，但不得超过手牌上限 10。
- 若因 `innate` 导致手牌溢出：按 `instance_id` 升序保留前 10 张，其余不进入手牌。

反例：
- 仅因 UI 查看/悬停导致 `innate` 进入顺序漂移
- `innate` 溢出裁剪使用 RNG 或不稳定排序

---

## 4.7 回合内止损与高难度刷牌刹车（边界写死）

4.7.1 稳定性止损：单回合出牌 100 张
- 单回合出牌达到 100 张时，强制中止玩家回合，并按正常 EndOfTurn 顺序结算。
- 该规则属于稳定性止损，不作为平衡手段。

4.7.2 高难度刷牌刹车：`OverplayTax`（难度 >= 10）
- 当本回合出牌数首次超过 N（N=12）时触发一次；**触发当下的那张牌（第 N+1 张）也受该规则影响**。
- 本回合内所有卡牌费用 +1，且最低费用=1；影响本回合后续抽到/生成到手的牌。
- 不可驱散；回合结束自然失效。

反例：
- `OverplayTax` 被驱散导致可刷无穷回合
- `OverplayTax` 不影响本回合后续生成牌（导致规则可被绕过）

---

## 4.8 结算顺序与触发器确定性（边界写死）

4.8.1 单次出牌（PlayCard）管线（最小口径）
- `Validate → ComputeCost → PayCost → BeforePlayTriggers → ResolveEffect → AfterPlayTriggers → MoveCard → DeathCheck`
- 目标不可选止损阀：在 `Validate` 阶段触发；失败则取消出牌并回手；不耗能量；不计出牌数；不进入弃牌/消耗堆。

4.8.2 计数与绕过（OverplayTax/止损）
- 出牌计数在 `PayCost` 成功后立刻 +1。
- 自动出牌/复制出牌等同样计入出牌数（避免绕过 `OverplayTax`）。

4.8.3 多目标与多段（稳定排序）
- AOE/多目标结算：按 `combatant_id` 升序逐个结算（不得用屏幕位置/随机）。
- 多段伤害：每段后立即 `DeathCheck`；若目标中途死亡，剩余段取消（不得转移到其他目标）。

4.8.4 触发器排序（同一时刻多触发）
- 总序：先玩家侧，再敌人侧。
- 玩家侧内部：遗物（`relic_id`）→ 状态（`status_id`）→ 卡牌实例触发（`instance_id`），各自按 `stable_id` 字典序。
- 敌人侧内部：按 `combatant_id` 升序；同一敌人内按 `stable_id` 字典序。

反例：
- 同一场战斗同一输入序列下，仅因“触发器顺序漂移”导致不同结果
- AOE 目标顺序不稳定导致“像刷随机”的争议

---

## 4.9 状态系统（Status）边界（边界写死）

4.9.1 状态分类（最小集合）
- Buff / Debuff / RuleModifier（规则类，不可驱散）。

4.9.2 最小字段（用于复盘与坏档阻断）
- `status_id`（建议：`status.<slug>`）
- `stacks`（可正可负）
- `duration_turns`（可空）
- `source_id`（稳定 id，例如 `relic.*` / `enemy.*` / `card.*`）
- `expires_timing`（建议：`owner_end_of_turn_cleanup`）

4.9.3 衰减/到期（统一口径）
- 有回合数的状态按“持有者回合结束 Cleanup”衰减/到期。
- 自然失效不等于驱散：回合结束自然失效属于生命周期，不视为驱散。

4.9.4 驱散边界（强冻结）
- 只允许驱散 `Debuff`。
- `RuleModifier` 永不可驱散（例如 `OverplayTax`）。
- `status.strength` 永不可驱散（即使为负）。

4.9.5 标杆状态（用于 v1 统一对齐）
- `status.weak`：输出乘区典型为 75%（伤害 -25%）；持续 N 回合；重复施加时 `duration_turns += N`（累加）；输出乘区下限=50%。
- `status.vulnerable`：受击乘区典型为 150%（受击增伤）；持续 N 回合；重复施加时 `duration_turns += N`（累加）；受击乘区上限=200%。
- `status.strength`：每点 Strength 使“造成的伤害”+3；允许为负；当 `stacks < 0` 时在持有者回合结束 Cleanup 使 `stacks += 1`（例如 -3 → -2）；获得 Strength 与当前值相加实现对冲（例如 -3 + 2 → -1）；不可驱散。
- `status.bloodbeat`（规则类）：每次出牌 `PayCost` 成功后触发，对玩家造成 1 点固定伤害（可被护甲格挡；不受 Strength/Weak/Vulnerable 等修饰）；战斗内常驻；不可叠加。

反例：
- 负 Strength 可被驱散导致“弱化类效果没有成本”
- `status.weak` 的持续计算在玩家/敌人回合结束混用，导致复盘不一致
- `status.bloodbeat` 可叠加或被驱散，导致强度与口径失控

---

## 4.10 Offer/Shop/Event 确定性（边界写死）

4.10.1 Offer locking（候选集锁定）统一结构
- 统一结构：`stable_ids[] + display_order[] + provenance + rng_stream + locked_at_save_point`
- `stable_ids[]` 必须是内容稳定 ID（`card.*` / `relic.*` / `event.*`），不得使用文案 key 代替。
- `display_order[]` 必须锁定：退出重进候选集与顺序都必须一致。

`provenance` 最小字段：
- `source_type`、`source_id`、`act`、`floor`、`node_id`、`difficulty`、`rng_stream`、`stream_pos`

4.10.2 写盘点（避免“崩溃像刷结果”）
- Reward：奖励界面首次出现时锁定候选集与顺序，并写 autosave，然后再展示界面。
- Shop：进入商店即锁定“库存 + 价格”并写入 run 状态。
- Event：进入事件生成选项后即锁定并写入 run 状态；事件选项一旦选择（含跳过/离开），立刻写入 run 状态。

4.10.3 UI 不推进 RNG（强冻结）
- 查看详情/翻页/排序/悬停/打开关闭面板/事件内来回切换升级路线等均不得推进 RNG。

4.10.4 退出重进恢复点（写死）
- Reward：界面已出现并写 autosave，但未选择强退 → Continue 回到 Reward 界面（同候选集同顺序）。
- Shop：进入已锁库存/价格；购买后强退 → Continue 回到商店界面，库存/金币/已购标记一致。
- Event：进入已锁选项；选择立刻写入结果；若强退发生在结果展示中 → Continue 进入“已选择后的结果展示/结算后状态”。

4.10.5 错误处理（Continue Gate）
- 若锁定数据缺失/校验失败：必须阻断 Continue 并提示；必须提供明确下一步动作（例如返回主菜单、开始新局）。

反例：
- 退出重进后同一奖励候选集顺序变化
- 商店价格未锁导致退出重进可刷折扣/涨价
- UI 行为推进 RNG 导致“打开面板影响掉落”

---

## 4.11 敌方意图与 AI 确定性（边界写死）

4.11.1 Intent 锁定时机
- 敌方回合开始生成并锁定 Intent（对玩家可见），到敌方行动时保持不变。
- Intent 必须写入 run 状态（或至少写入 `combat` RNG stream 的 `stream_pos` 以保证退出重进一致）。

4.11.2 行动顺序与稳定键
- 多敌人行动顺序按 `combatant_id` 升序（稳定键）。

4.11.3 随机性边界
- 允许随机，但必须来自 `combat` RNG stream，且在锁定点固定；退出重进不得改变。
- UI 查看意图/悬停/详情等行为不得推进 RNG。

4.11.4 意图改写边界
- 默认 Intent 不因玩家当回合行为自动重算；仅当存在明确“改写意图”的效果时才改变，并必须写入状态以可复盘。

反例：
- 退出重进后敌方意图变化（像刷随机）
- 仅查看意图导致下一次掉落/敌方行为改变（UI 推进 RNG）

---

## 4.12 Run 存档版本化与 Continue Gate（边界写死）

4.12.1 `schema_version`
- run 存档必须包含 `schema_version`（int）；任意结构变更必须递增版本号。

4.12.2 v1 迁移策略（止损）
- 默认不自动迁移；版本不兼容或迁移失败必须阻断 Continue 并提示。

4.12.3 校验失败（坏档）
- 缺字段/字段非法/哈希不一致等校验失败必须阻断 Continue，并提供明确下一步动作（例如返回主菜单、开始新局覆盖确认）。

4.12.4 审计日志（JSONL）
- 最小字段：`ts, action, reason, target, caller, run_id, schema_version`；统一写入 `logs/**`。

4.12.5 保存点建模
- 存档必须记录 `save_point_id`（例如 `node_pre_enter`, `combat_start`, `reward_open`, `shop_enter`, `event_enter`, `event_choice_committed`），用于恢复定位与审计。

反例：
- 无 `schema_version` 导致无法判断兼容性
- 迁移失败仍继续运行导致更隐蔽数据损坏

---

## 5) 不允许的“玩法漏洞语境”（文案/UX）

以下语境一旦出现在 UI/文案/提示中，视为高风险缺陷（会诱导玩家试图刷结果）：
- “退出重进可以换结果”
- “战斗中途可继续”
- “商店可以升级”

---

## 6) 错误处理（Continue Gate）

6.1 坏档/迁移失败
- 必须阻断 Continue 并提示（不得“继续尝试加载”导致更大损坏）。

反例：
- 迁移失败仍进入游戏，然后出现更隐蔽的数据损坏
