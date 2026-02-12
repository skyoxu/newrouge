=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_BEGIN ===
{
  "schema": "taskmaster-prd-part/v1",
  "generated_at_utc": "2026-01-29T12:44:47+00:00",
  "rel_path": ".taskmaster/docs/prd_parts/60-m1-acceptance-checklist.md",
  "title": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md",
  "sha256": "1968c33f103445802b5d03c6a22c3c0cd9aa74f6593a45294f720bf51e48051d",
  "bytes": 8300
}
=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_END ===

---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 功能纵切验收清单（M1：Warrior）
Status: Draft
ADR-Refs:
  - ADR-0005-quality-gates
  - ADR-0010-internationalization
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0019-godot-security-baseline
  - ADR-0020-contract-location-standardization
  - ADR-0025-godot-test-strategy
  - ADR-0033-card-identity-and-forms
Test-Refs:
  - Game.Core.Tests/Determinism/OfferLockingTests.cs # planned
  - Game.Core.Tests/Save/SaveResumeBoundaryTests.cs # planned
  - Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs # planned
  - Tests.Godot/Smoke/ContinueGateTests.gd # planned
---

# 08 功能纵切验收清单（M1：Warrior）

范围：只验收 M1 最小可玩闭环，不验收 v1 全量内容。

参考：
- 纵切说明：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md`
- PRD：`docs/prd/PRD-NEWROUGE-GAME-0001.md`
- GDD：`docs/gdd/GDD-NEWROUGE-V1.md`

证据归档（统一写入 `logs/**`）：
- 约定目录：`logs/ci/<YYYY-MM-DD>/`

---

## 一、文档完整性验收

- [ ] `_index.md` 存在且可导航：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md`
- [ ] 纵切文档存在：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md`
- [ ] 本清单具备 Front-Matter 且字段齐全：`PRD-ID/Title/Status/ADR-Refs/Test-Refs`
- [ ] PRD 的 “关联规格（v1）”包含本纵切入口（避免验收锚点漂移）

## 二、架构设计验收

### 2.1 M1 体验闭环（Warrior）

- [ ] MainMenu → New Run（覆盖确认默认取消）→ 选择难度 → 选择 Warrior → 进入地图
- [ ] Map（Act 1）至少可进入：战斗、事件、商店、休整
- [ ] 战斗后奖励：至少 1 次“卡牌三选一”
- [ ] 战斗基础规则（M1）：能量默认每回合重置为 3（除非卡牌/遗物影响）；每回合默认抽牌=4
- [ ] 战斗回合结构（M1，Design Gate 01）：`StartOfTurn → Draw → Main → EndOfTurn`
- [ ] EndOfTurn 顺序（M1，Design Gate 01）：`EndOfTurn.Triggers → Discard non-retained → Cleanup`（保留牌相关效果可在 Triggers 阶段生效）
- [ ] 能量上限（M1，Design Gate 01）：存在 `max_energy` 且硬上限=99（实现需避免溢出导致的恢复/复盘不一致）
- [ ] 休整升级：升级是多选一选项之一；选择升级则免费升级 1 张卡；U1 必须 Route A/B 二选一且不可逆
- [ ] 商店：任何时候不提供升级（UI/文案不得出现升级语境）
- [ ] 商店库存：进入商店时锁定库存与价格；退出重进不刷新（避免刷商店）
- [ ] 事件：至少 1 次体现“黑暗代价”（包含 HP loss 与 获得诅咒卡 两类示范），且结果可解释/可复盘

### 2.2 关键口径冻结点（高风险）

- [ ] 卡牌身份与形态：同一 `card_id` 四形态（Base/U1A/U1B/Ultimate），不因升级更换 ID（ADR-0033）
- [ ] U1 → Ultimate：允许进阶，进阶覆盖 U1 形态能力，但继承实例附着效果（ADR-0033）
- [ ] 奖励三选一出现 U1 卡时：RouteA/RouteB 由掉落 RNG 决定且 UI 明确标注（ADR-0033）
- [ ] 退出重进：三选一候选集与顺序不变；战斗中断回到战斗初始状态（与 ADR-0032 对齐）
- [ ] 跳过奖励：允许跳过，但跳过不刷新候选集、不重抽、不推进 RNG（确定性）
- [ ] 奖励界面出现即写 autosave：退出重进后仍能回到同一候选集与顺序
- [ ] 商店购买一致性：单一库存不可重复购买；退出重进恢复“进入商店时的库存 + 已购买记录”
- [ ] 事件写入：事件选项一旦选择，立刻写入 run 状态（退出重进不刷分支/结果）
- [ ] 目标不可选止损阀（M1，Design Gate 01）：当松开瞬间目标已死亡/不可选时，取消出牌并回手；不耗能量；不进入弃牌/消耗堆（避免误操作与确定性争议）
- [ ] 结算顺序确定性（Design Gate 03）：AOE 按 `combatant_id` 升序；多段伤害每段后 `DeathCheck` 且目标死亡后剩余段取消；同一时刻触发器使用稳定键（`stable_id`）排序（先玩家侧后敌人侧）
- [ ] 自动出牌/复制出牌计入出牌数（Design Gate 03）：避免绕过 `OverplayTax` 与稳定性止损
- [ ] 回合内稳定性止损（Design Gate 01/03）：单回合出牌达到 100 张时，当前牌结算完后强制结束玩家回合并进入 EndOfTurn（不得被阻止/延后）
- [ ] 若实现难度 >= 10（M1 允许有限档位）：`OverplayTax`（N=12）触发一次且**第 N+1 张牌也吃到加税**；本回合费用 +1 且最低=1；影响本回合后续抽到/生成牌；不可驱散；回合结束自然失效
- [ ] 状态系统口径（Design Gate 04）：`Debuff` 可驱散；`RuleModifier` 不可驱散；`status.strength` 不可驱散且允许负值；`status.weak` duration 累加；状态回合数按“持有者回合结束 Cleanup”衰减
- [ ] `status.bloodbeat`（Design Gate 04）：每次出牌 `PayCost` 成功后对玩家造成 1 点固定伤害（可被护甲格挡；不受 Strength/Weak 修饰）；战斗内常驻；不可叠加
- [ ] 伤害乘区口径（Design Gate 03/04）：`status.weak` 影响输出乘区（典型 75%，下限 50%）；`status.vulnerable` 影响受击乘区（典型 150%，上限 200%）；固定伤害不吃乘区但可被护甲/格挡吸收
- [ ] Offer locking 统一结构（Design Gate 05）：候选集快照包含 `stable_ids[] + display_order[] + provenance + rng_stream + locked_at_save_point`，且 `stable_ids[]` 为内容稳定 ID（非文案 key）
- [ ] Reward 写盘点（Design Gate 05）：生成并锁定 reward 后写 autosave，再展示界面；强退后 Continue 回到 Reward 界面（同候选集同顺序）
- [ ] Shop 写盘点（Design Gate 05）：进入商店即锁定库存+价格并写入 run 状态；购买后强退 Continue 回到商店且库存/价格/金币/已购标记一致
- [ ] Event 写盘点（Design Gate 05）：进入事件生成选项后即锁定并写入 run 状态；选择/跳过立刻写入；强退在结果展示中 Continue 进入“已选择后的结果展示/结算后状态”
- [ ] UI 不推进 RNG（Design Gate 05）：查看详情/翻页/排序/悬停/开关面板/事件内切换升级路线等不得推进 RNG（避免“打开面板影响掉落”）
- [ ] 敌方意图锁定（Design Gate 06）：敌方回合开始锁定 Intent；退出重进意图一致；查看意图/详情不推进 RNG
- [ ] 多敌人行动顺序（Design Gate 06）：按 `combatant_id` 升序（稳定键）
- [ ] Run schema 版本化（Design Gate 07）：run 存档包含 `schema_version`；版本不兼容/校验失败阻断 Continue 并提示；存档包含 `save_point_id`

### 2.3 本地化与可见文本

- [ ] 可见文本不硬编码：关键屏（MainMenu/Reward/Shop/Rest/Upgrade/Continue）文本来自 `Game.Godot/Translations`
- [ ] 卡牌显示约定（M1）：稀有度使用固定位置标记；卡牌名称颜色区分 Base/U1A/U1B/Ultimate（不依赖路线命名）
- [ ] 掉落池口径（Act 结构）：普通怪/精英怪/Boss/商店/事件 5 类卡池可区分（M1 可先落骨架）
- [ ] 诅咒卡口径：`card.curse.<slug>` 独立池、不可升级（单形态）；存在至少一种移除入口（M1 要求：商店/事件/休整均有入口）

## 三、代码实现验收

说明：本清单的“代码实现”项用于 Taskmaster 拆任务时作为 Done 标准；M1 前允许处于 planned 状态。

- [ ] `Game.Core/Contracts/**` 存在卡牌形态/升级路线相关契约（不依赖 Godot）
- [ ] `Game.Core/**` 存在候选集锁定的核心逻辑（可被 xUnit 验证）
- [ ] `Game.Godot/**` 关键屏具备最小可用 UI：MainMenu/Map/Reward/Shop/Rest/Upgrade
- [ ] Continue Gate：坏档/迁移失败会阻断 Continue 并提示（错误不静默）

## 四、测试框架验收

- [ ] xUnit：至少 1 个用例覆盖“候选集锁定不漂移”（Core）
- [ ] xUnit：至少 1 个用例覆盖“卡牌身份与形态（升级不换 card_id、继承附着效果）”（Core）
- [ ] Headless 冒烟：至少 1 个用例覆盖“Continue Gate 关键路径”（Godot）
- [ ] 证据归档：测试与冒烟产物写入 `logs/**`（路径口径以仓库规则为准）
