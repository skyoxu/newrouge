=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_BEGIN ===
{
  "schema": "taskmaster-prd-part/v1",
  "generated_at_utc": "2026-01-29T12:44:47+00:00",
  "rel_path": ".taskmaster/docs/prd_parts/40-ssot-locks.md",
  "title": "docs/prd/SSOT-LOCKS-NEWROUGE-V1.md",
  "sha256": "264c1ec35a81fd0addbf0f1fa6c22ac047a5251a06974292145a1e1533d54574",
  "bytes": 10960
}
=== TASKMASTER_PRD_PARTS_MANIFEST_JSON_END ===

---
SPEC-ID: SSOT-LOCKS-NEWROUGE-V1
Title: NewRouge v1 设计锁定表（SSoT）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge v1 设计锁定表（SSoT）

用途：把 NewRouge v1 中“不能漂移”的关键口径统一收口，作为跨 PRD/GDD/ADR/Context 的单一事实来源（SSoT），避免：

- 研发/策划/QA 各自记忆造成口径漂移
- UI/文案暗示不存在或被禁止的系统（例如“商店升级”“战斗中断点续打”“退出重进刷结果”）
- 内容扩展（卡牌/事件/遗物/天赋）悄悄破坏确定性、可解释性与可复现

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 若出现冲突：以本文档为最终口径，并必须回补到“来源”文档中（否则视为口径不一致缺陷）。

权威引用（来源入口）：
- PRD：`docs/prd/PRD-NEWROUGE-GAME-0001.md`
- GDD：`docs/gdd/GDD-NEWROUGE-V1.md`
- 项目硬口径：`project-context.md`
- 存档/确定性：`docs/adr/ADR-0032-save-resume-determinism.md`
- 内容稳定 ID：`_bmad-output/content-id-standard.md`
- 内容登记表：`_bmad-output/content-registry.md`

---

## 1) 适用范围

- 版本范围：v1（首发）
- 渠道与平台：Steam（Windows-only）
- 游戏类型：单人卡牌构筑 roguelike（结构标签：roguelike；主类型：card-game）
- 本锁定表仅覆盖“卡牌肉鸽主线”（`PRD-NEWROUGE-GAME-0001`），不覆盖任何历史示例 PRD。

---

## 2) 锁定项总表（v1）

> 结构：锁定项 → 口径（硬规则）→ 来源（权威入口）。  
> 备注：阈值/参数若属于 Base/ADR 的口径，不在此复制，只引用其来源。

### 2.1 平台与技术栈

1) 平台锁定（Windows-only）
- 锁定：只支持 Windows；不做 macOS/Linux/主机/移动端。
- 来源：`project-context.md`；ADR-0011

2) 引擎锁定（Godot 4.5.1 .NET）
- 锁定：Godot 4.5.1 .NET 锁死；v1 不升级 Godot。
- 来源：`project-context.md`；ADR-0031

3) 语言与运行时锁定
- 锁定：C# / .NET 8（`net8.0`）；Nullable 开启。
- 来源：`project-context.md`；ADR-0001

4) 依赖锁定与可复现
- 锁定：必须启用并提交 `packages.lock.json`（缺失视为阻塞前置条件）。
- 来源：`project-context.md`；ADR-0031

### 2.2 玩法结构与规模

5) 结构锁定（3 Act + 单局 60 分钟）
- 锁定：3 Act 分叉路线图；单局目标约 60 分钟。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`_bmad-output/gdd.md`

6) 角色锁定（3 角色）
- 锁定：3 角色：战士/刺客/德鲁伊。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`_bmad-output/gdd.md`

7) 角色机制口径锁定（高层）
- 锁定：战士“怒气”是状态类 buff（不是第二属性条）；刺客擅长给敌人叠加多种 debuff；德鲁伊通过“状态持久 buff + 切换状态定点爆发”形成差异。
- 来源：`_bmad-output/gdd.md`

8) 卡牌规模锁定
- 锁定：每角色 30 张基础卡（不含升级版本）。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`

9) 事件规模锁定
- 锁定：v1 事件总量 40；同一 run 内事件不重复。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`project-context.md`

10) 遗物规模锁定
- 锁定：v1 仅遗物系统；首发遗物数量 20。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`

11) 难度锁定
- 锁定：10 档难度；以数值挑战为主；与天赋树不做强绑定。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`_bmad-output/gdd.md`

12) 天赋树锁定（共享 + 可重置）
- 锁定：所有角色共享同一棵天赋树；可无条件重置，鼓励试流派。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`_bmad-output/gdd.md`

补充锁定（战斗规则，v1）：
- 锁定：手牌上限永远是 10，且不被任何因素改变。
- 锁定：回合内稳定性止损——单回合出牌达到 100 张时，强制中止玩家回合，并按正常 EndOfTurn 结算（稳定性用途，不作为平衡手段）。
- 锁定：高难度刷牌刹车 `OverplayTax`（难度 >= 10）：当本回合出牌数首次超过 N（N=12）时触发一次；**触发当下的那张牌（第 N+1 张）也受该规则影响**；本回合内所有卡牌费用 +1，且最低费用=1；影响本回合后续抽到/生成到手的牌；不可驱散；回合结束自然失效。
- 锁定：结算顺序与触发器排序必须确定性：AOE 按 `combatant_id` 升序；多段伤害每段后 `DeathCheck`；同一时刻触发器按稳定键（`stable_id`）排序。
- 锁定：状态系统最小口径：`Debuff` 可驱散；`RuleModifier` 不可驱散；`status.strength` 不可驱散且允许负值；`status.weak` duration 累加；有回合数的状态按“持有者回合结束 Cleanup”衰减。
- 来源：`docs/gdd/GDD-NEWROUGE-V1.md`（Design Gate 01/02/03）

补充锁定（伤害乘区，v1）：
- 锁定：输出乘区（Attacker Multiplier）与受击乘区（Target Multiplier）分离，分别用于 `status.weak` 与 `status.vulnerable`。
- 锁定：`status.weak` 输出乘区典型为 75%，下限=50%；`status.vulnerable` 受击乘区典型为 150%，上限=200%，duration 累加（`duration_turns += N`）。
- 锁定：固定伤害（例如 `status.bloodbeat`）不受 Strength/Weak/Vulnerable 等乘区影响，但可被护甲/格挡吸收。
- 来源：`docs/gdd/GDD-NEWROUGE-V1.md`（Design Gate 03/04）

### 2.3 存档、退出重进与确定性（高风险冻结）

13) 允许退出重进，但不刷结果
- 锁定：允许退出重进；读取唯一 Continue（单槽 autosave）；退出重进不会改变事件候选集与结果空间（同一输入序列保持确定性）。
- 来源：ADR-0032；`project-context.md`

14) 存档粒度锁定
- 锁定：节点前存档；进入战斗后保存“战斗初始状态”；战斗中绝不保存中间态；战斗中退出重进回到战斗初始状态。
- 来源：ADR-0032；`project-context.md`

15) 三选一候选集锁定（Offer locking）
- 锁定：首次生成即落盘 `stable_ids[] + display_order[] + provenance`；退出重进后候选集与顺序不变；允许重新选择但禁止重抽/重滚。
- 来源：ADR-0032

15.1) Offer/Shop/Event 锁定结构与写盘点（v1）
- 锁定：Offer locking 统一结构补充字段：`rng_stream` 与 `locked_at_save_point`；`provenance` 最小字段必须包含 `source_type/source_id/act/floor/node_id/difficulty/rng_stream/stream_pos`。
- 锁定：Reward/Shop/Event 的写盘点必须提前锁定并落盘（Reward 界面出现前 autosave；Shop 进入即锁库存+价格；Event 进入即锁选项，选择/跳过立刻写入）。
- 锁定：UI 行为不得推进 RNG；按系统拆分 RNG streams（至少 run/combat/event/loot/shop/offer）。
- 来源：`docs/gdd/GDD-NEWROUGE-V1.md`（Design Gate 05）；ADR-0032

16) RNG 流拆分锁定
- 锁定：按系统拆分 RNG streams（run/combat/event/loot…）；UI 行为不得推进 RNG。
- 来源：ADR-0032；`project-context.md`

17) 坏档/迁移失败的阻断策略
- 锁定：迁移失败或校验失败必须阻断 Continue 并提示；不得“带病运行”。
- 来源：ADR-0032

### 2.4 文案与本地化（禁止硬编码可见文本）

18) 可见文本不得硬编码
- 锁定：所有 UI 可见文案必须走 `Game.Godot/Translations`；脚本里禁止硬编码可见文本。
- 来源：`project-context.md`；ADR-0010；`_bmad-output/content-id-standard.md`

19) 翻译 key 派生锁定
- 锁定：翻译 key 必须由内容稳定 ID 派生；不得自造漂移 key。
- 来源：`_bmad-output/content-id-standard.md`

### 2.5 卡牌升级系统（v1 必做，且强冻结）

20) 商店永不提供升级
- 锁定：商店任何时候都不能升级；商店仅提供购买/移除/转换等非升级服务（具体服务可变，但“升级=禁止”不可变）。
- 来源：`docs/prd/PRD-NEWROUGE-GAME-0001.md`；`project-context.md`

21) 休整节点的免费升级
- 锁定：休整节点是多选一选项之一；若选择“升级”，则免费升级 1 张卡牌。
- 来源：`project-context.md`；`docs/prd/PRD-NEWROUGE-GAME-0001.md`

22) 常规升级 U1（二选一，不可逆）
- 锁定：所有卡牌的常规升级为 Route A/B 二选一；选择不可逆。
- 来源：`project-context.md`；`_bmad-output/content-id-standard.md`

23) 特殊事件：允许对已 U1 的卡免费换路线
- 锁定：特殊事件可对已升级（U1）的卡免费改路线；事件内可无限次切换；离开事件时以最终选择为准；该过程不得引入额外 RNG。
- 来源：`project-context.md`；ADR-0032（UI 不推进 RNG）

24) 终极形态 Ultimate（稀有机会，不可逆）
- 锁定：每张卡都有 1 个终极形态；仅史诗事件/关卡 Boss 等稀有机会获得；卡牌无需先 U1 即可直接进阶 Ultimate；不可逆；不可再升级；不可换路线。
- 来源：`project-context.md`；`_bmad-output/content-id-standard.md`

25) 升级状态的最小存档字段
- 锁定：卡牌实例必须以 `upgrade_tier: 0|1|2` + `upgrade_route: null|a|b` 表示升级态；tier=2 时 route 必须为 null。
- 来源：`_bmad-output/content-id-standard.md`

### 2.6 事件系统（同局去重 + 跨局抑制）

26) 同局不重复的边界
- 锁定：同一 run 内事件“定义 ID”不重复（按 `event.<scope>.<slug>` 判定），不得用“事件类型粗粒度”偷换去重边界。
- 来源：`project-context.md`

27) 跨局重复抑制策略（存在但参数不在此复制）
- 锁定：跨局允许重复，但必须有“重复抑制”策略（例如：权重衰减 + 硬冷却窗口）；具体参数只能放在 ADR/Base/门禁脚本中，不在本文复制。
- 来源：`project-context.md`；ADR-0015（门禁口径）

---

## 3) 变更治理（v1）

规则：
1) 若要改动任何锁定项，必须同时完成：
   - 更新本文档（本 SSOT）
   - 更新所有“来源”入口文档
   - 若改动涉及：安全/确定性/存档/门禁阈值/契约：必须新增或 Supersede 相应 ADR，并补齐 Test-Refs 与 `logs/**` 取证

2) 若仅新增内容（卡牌/遗物/事件/天赋）：
   - 不得破坏锁定项（尤其是：确定性、存档边界、商店不升级、可见文本不硬编码）
   - 必须先登记内容稳定 ID：`_bmad-output/content-registry.md`（硬门禁：未登记视为 Stop-Ship，拒绝合入/拒绝引用）
   - 登记时必须同时满足：
     - `translation_key_prefix` 必须等于 `content_id`（防 key 漂移）
     - 若新增 `event.*`：必须同步对齐 `docs/prd/EVENT-ID-CATALOG-NEWROUGE-V1.md`（避免 event_id 漂移/重复破坏“同局不重复”）
   - 内容制作与验收的唯一入口：
     - `docs/prd/CONTENT-AUTHORING-ENTRY-NEWROUGE-V1.md`
     - `docs/prd/CONTENT-REVIEW-CHECKLIST-NEWROUGE-V1.md`
