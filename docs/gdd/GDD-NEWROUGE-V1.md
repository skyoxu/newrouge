---
GDD-ID: GDD-NEWROUGE-V1
Title: NewRouge v1 Game Design Document（工作版）
Status: Draft
Owner: skyo
Last Updated: 2026-02-12
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
ADR-Refs:
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0019-godot-security-baseline
  - ADR-0025-godot-test-strategy
  - ADR-0032-save-resume-determinism
  - ADR-0033-card-identity-and-forms
Test-Refs:
  - Game.Core.Tests/Determinism/OfferLockingTests.cs
  - Game.Core.Tests/Save/SaveResumeBoundaryTests.cs
  - Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs
  - Tests.Godot/Smoke/ContinueGateTests.gd
---

# NewRouge v1 GDD（工作版）

## 1. 设计目标

### 1.1 体验支柱
- 构筑表达：同角色至少 3 条可行构筑方向。
- 代价抉择：强收益必须绑定可解释代价。
- 可读可解释：玩家能理解状态、代价、结果来源。
- 可复现：退出重进不刷结果，失败可复盘。

### 1.2 目标人群
- 喜欢单人卡牌 roguelike。
- 愿意做长线构筑尝试与复盘。

## 2. 核心循环

1) MainMenu：New Run / Continue。
2) 选择难度与角色。
3) 进入分叉地图并选择节点。
4) 在 Combat/Event/Shop/Rest 中推进 run。
5) 战斗后奖励三选一，强化牌组。
6) 到达 Boss 或失败后结算并进入下一局。

## 3. 角色设计

### 3.1 战士（M1 主角色）
- 怒气是状态 Buff，不是第二资源条。
- 怒气可累积并参与爆发决策。

### 3.2 刺客
- 擅长给敌方叠加 Debuff 并转化收益。

### 3.3 德鲁伊
- 依赖状态切换与持久 Buff 管理爆发窗口。

## 4. 战斗系统规格

### 4.1 回合基础
- 默认每回合能量 3。
- 默认每回合抽牌 4。
- 手牌上限 10（固定）。

### 4.2 回合阶段
- StartOfTurn -> Draw -> Main -> EndOfTurn。
- EndOfTurn 执行触发器后，弃掉非保留牌，再清理状态。

### 4.3 出牌与稳定性
- 难度 10+：每回合出牌达到 12 后，后续卡牌费用 +1（最低 1）。
- 单回合出牌达到 100 强制结束回合，防止无限循环失控。

## 5. 升级与形态

### 5.1 规则总览
- 升级只发生在 Rest 与特殊事件。
- Shop 永不提供升级。
- U1 升级必须 A/B 二选一，不可逆。
- 特殊事件可对已 U1 卡免费换路线，离开事件确认最终路线。
- Ultimate 不可逆，不可再升级，不可再换路线。

补充硬口径：
- 商店语境中禁止出现“升级/进阶/升星/强化”等升级文案。
- 难度系统以数值挑战为主，且不与天赋树强绑定。

### 5.2 身份规则
- 升级不改变 `card_id`。
- 形态为 Base/U1A/U1B/Ultimate。
- 实例附着效果在形态切换时继承。

## 6. 黑暗代价

- M1 至少展示两类代价：HP Loss、Curse。
- Curse 是独立卡池，且必须可移除。

## 7. 存档与 Continue

- 单槽 autosave。
- 节点前保存节点入口状态。
- 进入战斗保存战斗初始状态。
- 战斗中不保存中间态。
- Continue 失败必须阻断并提示原因。

## 8. M1 最小可玩纵切

### 8.1 范围
- Warrior + Act 1 最小路径。
- 节点类型覆盖：Combat/Event/Shop/Rest。
- 必须至少完整跑通一次奖励三选一。

### 8.2 非范围
- 三角色完整平衡。
- 三 Act 全量内容。
- 云同步、多槽存档。

## 9. 节点与界面要求

### 9.1 MainMenu
- New Run、Continue、Quit。
- Continue 仅在存在有效 autosave 时可用。

### 9.2 Difficulty Select
- 提供 1-10 档难度入口。
- 文案强调“数值挑战为主”，不暗示天赋树强绑定。

### 9.3 Character Select
- M1 只开放 Warrior。

### 9.4 Shop
- 可购买/移除/转换。
- 不允许出现升级语境。

### 9.5 Rest
- 至少包含：恢复、升级、移除 Curse（三选一结构可扩展）。

## 10. 文案与可访问性

- 所有可见文本必须来自 `Game.Godot/Translations`。
- 禁止脚本硬编码可见文本。
- 形态标识除颜色外应有辅助标识（如 A/B、图标）。

## 11. 测试与验收

### 11.1 必测项
- 候选集锁定与确定性。
- Continue 阻断路径。
- 卡牌身份与形态规则。
- 存档边界规则。

### 11.2 证据
- 单测：`logs/unit/<YYYY-MM-DD>/`
- 冒烟：`logs/e2e/<YYYY-MM-DD>/`
- CI：`logs/ci/<YYYY-MM-DD>/`

## 12. 任务对齐

- 任务推进以 `.taskmaster/tasks/*.json` 为准。
- 关键 gate：T56（Audit JSONL）、T57（Traceability）。
- Overlay 验收以 `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md` 为准。
