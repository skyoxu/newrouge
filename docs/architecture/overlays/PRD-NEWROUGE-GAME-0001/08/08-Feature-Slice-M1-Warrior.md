---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 功能纵切（M1：Warrior 最小可玩闭环）
Status: Draft
ADR-Refs:
  - ADR-0005-quality-gates
  - ADR-0010-internationalization
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0019-godot-security-baseline
  - ADR-0020-contract-location-standardization
  - ADR-0025-godot-test-strategy
  - ADR-0033-card-identity-and-forms
Related:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
  - docs/gdd/GDD-NEWROUGE-V1.md
  - docs/prd/SSOT-LOCKS-NEWROUGE-V1.md
  - docs/prd/CARD-ID-CATALOG-NEWROUGE-V1.md
  - docs/prd/RELIC-ID-CATALOG-NEWROUGE-V1.md
---

# M1：Warrior 最小可玩闭环（Feature Slice）

目标：在没有“内容量产”前，先把 v1 的高风险口径做成可验证闭环，作为后续 Taskmaster 拆任务的唯一验收锚点。

M1 的定义（只做这些）：
- 角色：Warrior
- 起始牌组：10 张（见 `docs/prd/CARD-ID-CATALOG-NEWROUGE-V1.md`）
- 地图：Act 1 的最小可推进路径（允许临时减少节点种类，但必须包含：战斗、事件、商店、休整）
- 奖励：战斗后“卡牌三选一”（至少 1 次）
- 休整：提供升级入口（U1 二选一，不可逆；商店无升级语境）
- 存档/继续：单槽 Continue 的 UI 与边界（战斗中断回到战斗初始状态；候选集锁定“不刷结果”）

非目标（M1 不做）：
- 3 Act 全通关
- 40 事件/20 遗物/30 卡牌/角色全套
- 难度 10 档完整曲线
- 共享天赋树完整内容（可留最小占位，但不得误导为“强绑定难度”）

---

## 1) 关键体验路径（Happy Path）

1) MainMenu
   - New Run（覆盖确认默认取消）
   - 选择难度（数值挑战为主，不强绑定天赋树）
   - 选择角色：Warrior
2) Map（Act 1）
   - 选择节点：战斗 → 奖励三选一
   - 选择节点：事件（至少一次体现“黑暗代价”）
   - 选择节点：事件（至少一次有选择与结果反馈）
   - 选择节点：商店（明确无升级语境）
   - 选择节点：休整（升级是多选一选项之一；选择后可升级 1 张卡）
3) 退出与继续（最少验证 2 条）
   - 三选一界面：退出重进候选集与顺序不变
   - 战斗中：退出重进回到战斗初始状态（不保存中间态）

---

## 2) 领域对象与数据口径（不写实现细节，只写不可变约束）

### 2.1 卡牌身份与形态（必须遵循 ADR-0033）

约束（SSoT）：
- `card_id` 不随升级变化；同一 `card_id` 有四形态：Base/U1A/U1B/Ultimate。
- 事件/遗物等“实例附着效果”在形态切换时继承保留。
- 奖励三选一出现 U1 卡时：RouteA/RouteB 由掉落 RNG 决定且 UI 标注。

最小代码契约片段（示意；Contracts 应落在 `Game.Core/Contracts/**`）：

```csharp
namespace Game.Core.Contracts.Cards;

public enum CardForm
{
    Base = 0,
    U1 = 1,
    Ultimate = 2,
}

public enum CardUpgradeRoute
{
    A = 1,
    B = 2,
}
```

### 2.2 奖励候选集锁定（对齐“退出重进不刷结果”）

M1 最小要求：
- “卡牌三选一”首次展示时锁定候选集（稳定标识 + 顺序 + 来源）。
- 退出重进后候选集与顺序一致（允许重新选择，但不得重抽）。
- “商店库存/价格”进入商店时锁定，退出重进不刷新（避免刷商店）。
- 若支持“跳过奖励”：跳过不刷新候选集、不重抽、不推进 RNG。
- 事件选项一旦选择，必须立刻写入 run 状态（防止退出重进刷分支/刷结果）。

---

## 3) UI/文案口径（只写可见事实）

- 所有可见文本必须来自 `Game.Godot/Translations`（禁止脚本硬编码可见文本）。
- 商店禁止出现升级相关语境（升级仅休整/特殊事件）。
- U1：二选一、不可逆。
- Ultimate：不可逆、不可再升级、不可换路线。
- 卡牌显示约定（M1）：
  - 稀有度（普通/优良/精良/史诗）使用固定位置标记表达。
  - 卡牌名称颜色区分形态：Base/Upgrade A/Upgrade B/Ultimate（不依赖路线命名）。

事件黑暗代价示范（M1）：
- 至少包含两类：HP loss、获得诅咒卡（用于验证“代价模块”可扩展）。

诅咒卡口径（M1）：
- 诅咒卡属于独立池：`card.curse.<slug>`，不可升级（单形态）。
- 必须具备移除入口：商店服务 / 事件 / 休整（多选一选项之一）。

---

## 4) 验收与测试对齐（只列路径，不做代码实现）

M1 planned Test-Refs（与 PRD 对齐）：
- `Game.Core.Tests/Determinism/OfferLockingTests.cs`
- `Game.Core.Tests/Save/SaveResumeBoundaryTests.cs`
- `Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs`
- `Tests.Godot/Smoke/ContinueGateTests.gd`

证据与取证（统一写入 `logs/**`）：
- `logs/ci/<YYYY-MM-DD>/e2e/`：headless 冒烟/截图（如有）
- `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`：关键动作审计（如涉及）
- `logs/ci/<YYYY-MM-DD>/playtest/`：试玩记录表与截图（M1 可先做短路版）
