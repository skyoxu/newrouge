---
Story-ID: PRD-NEWROUGE-GAME-0001
Title: NewRouge v1（暗黑卡牌肉鸽，3角色+共享天赋树）
Status: Draft
ADR-Refs:
  - ADR-0003-observability-release-health
  - ADR-0005-quality-gates
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0015-performance-budgets-and-gates
  - ADR-0019-godot-security-baseline
  - ADR-0025-godot-test-strategy
  - ADR-0032-save-resume-determinism
  - ADR-0033-card-identity-and-forms
Chapter-Refs:
  - docs/architecture/base/01-introduction-and-goals-v2.md
  - docs/architecture/base/02-security-baseline-godot-v2.md
  - docs/architecture/base/03-observability-sentry-logging-v2.md
  - docs/architecture/base/06-runtime-view-loops-state-machines-error-paths-v2.md
  - docs/architecture/base/07-dev-build-and-gates-v2.md
  - docs/architecture/base/09-performance-and-capacity-v2.md
Test-Refs:
  - Game.Core.Tests/Determinism/OfferLockingTests.cs
  - Game.Core.Tests/Save/SaveResumeBoundaryTests.cs
  - Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs
  - Tests.Godot/Smoke/ContinueGateTests.gd
  - Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0057AcceptanceTests.cs
---

# PRD-NEWROUGE-GAME-0001

## 0. 文档边界与 SSoT

本 PRD 只描述产品目标、玩法规则、验收边界与交付范围。  
实现真相与推进状态以任务系统为准：
- `.taskmaster/tasks/tasks.json`
- `.taskmaster/tasks/tasks_back.json`
- `.taskmaster/tasks/tasks_gameplay.json`

M1 Overlay 入口：
- `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md`
- `docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md`

## 1. 产品定位

NewRouge 是一款单人回合制卡牌构筑 roguelike：
- 单局结构：3 Act 分叉路线推进。
- 目标时长：约 60 分钟。
- 核心体验：构筑表达、代价抉择、可复现与可解释。

## 2. v1 目标与非目标

### 2.1 v1 目标
- 提供可完成的 3 Act 单局闭环。
- 提供 3 角色：战士、刺客、德鲁伊。
- 每角色 30 张基础卡（不含升级形态）。
- 事件总量 40（支持可重复池策略）。
- 遗物首发 20。
- 共享天赋树，支持无条件重置。
- 难度 10 档（以数值曲线为主，不与天赋树强绑定）。

### 2.2 v1 非目标
- 不做联网、云同步、多槽存档。
- 不做跨平台（Windows-only）。
- 不做战斗中间态恢复。

## 3. 角色机制（高层）

### 3.1 战士
- 怒气作为状态 Buff，不是第二属性条。
- 怒气在战斗内持续，回合结束不清空，不衰减，战斗结束清空。

### 3.2 刺客
- 强项是给敌方叠加多种 Debuff，并围绕 Debuff 联动收益构筑。

### 3.3 德鲁伊
- 通过状态切换与持久 Buff 形成定点爆发窗口。

## 4. 核心战斗规则（冻结）

- 每回合默认能量重置为 3。
- 每回合默认抽牌 4。
- 手牌上限永远 10，不被任何因素改变。
- 允许抽牌数超过 4，但不得超过手牌上限 10；超限时按 `instance_id` 升序裁剪。
- 出牌达到 N=12 后（难度 10+），本回合后续所有牌费用 +1（最低 1），不可驱散。
- 单回合出牌达到 100 张时，强制中止回合。

## 5. 升级与形态规则（ADR-0033）

### 5.1 升级入口
- 仅 Rest 与特殊事件可升级。
- Shop 任何时候不提供升级。
- 战斗后三选一可概率出现已升级形态卡牌。

### 5.2 U1 升级
- U1 必须 A/B 二选一，选择不可逆。

### 5.3 换路线事件
- 特殊事件允许对已 U1 卡免费换路线，事件内可反复切换。
- 离开事件时需确认，写入最终路线。

### 5.4 Ultimate
- 每张卡有 1 个 Ultimate。
- 可从 Base 或 U1 直接进阶。
- 进阶后不可逆，不可再升级，不可再换路线。
- Ultimate 默认带 Exhaust（可被修饰）。

### 5.5 身份与实例
- 升级与进阶不改变 `card_id`。
- 实例附着效果跟随实例继承，不因形态切换丢失。

## 6. 诅咒与黑暗代价

- M1 至少提供 2 个黑暗代价示例：HP Loss、获得 Curse。
- Curse 为独立卡类与独立命名空间，不可升级。
- M1 必须提供移除 Curse 路径（建议覆盖 Shop/Event/Rest）。

## 7. 存档、继续游戏与确定性（ADR-0032）

- 单槽 autosave，主菜单只有一个 Continue 入口。
- 节点前保存节点入口状态。
- 进入战斗保存战斗初始状态。
- 战斗中不保存中间态。
- 允许退出重进，但不得刷候选集与结果空间。
- 候选集首次展示即锁定：内容、顺序、稀有度标识必须可复现。

## 8. 事件与奖励池

- 事件可采用可重复池策略，但同一节点结果必须确定性。
- 每 Act 可配置不同卡池：普通怪、精英怪、Boss、商店、事件。
- 事件一旦选择，立即写入 run 状态。

## 9. UI 与文案硬规则

- 所有可见文本必须来自 `Game.Godot/Translations`。
- 禁止脚本硬编码可见文案。
- 商店语境禁止出现“升级”相关表达。

## 10. M1 可玩纵切

M1 范围：
- 角色：仅 Warrior。
- 地图：Act 1 最小闭环。
- 节点：Combat/Event/Shop/Rest 全覆盖。
- 验收：Continue Gate + 候选集锁定 + 升级规则闭环可验证。

## 11. 任务拆解策略（供 Taskmaster）

- Gate-0：先冻结 ADR-0032 与 ADR-0033 的实现边界。
- 复杂度目标：平均 <= 6，单任务 <= 8。
- 任务数量：建议 45-60，优先保证验收条目可落地可回链。

## 12. 验收标准（高层）

- 规则正确：核心战斗与升级规则按口径执行。
- 确定性正确：退出重进不刷结果。
- 回链正确：ADR/Chapter/Overlay/Test-Refs 完整可追溯。
- 取证正确：`logs/**` 产物可用于复盘。

