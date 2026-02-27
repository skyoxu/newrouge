---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 功能纵切（M1: Warrior 最小可玩闭环）
Status: Draft
ADR-Refs:
  - ADR-0032-save-resume-determinism
  - ADR-0033-card-identity-and-forms
  - ADR-0021-run-state-machine-and-core-bounded-context
  - ADR-0023-difficulty-system-and-balance-curve
  - ADR-0010-internationalization
  - ADR-0019-godot-security-baseline
Arch-Refs:
  - CH01
  - CH02
  - CH03
  - CH05
  - CH06
  - CH07
Test-Refs:
  - Game.Core.Tests/Determinism/OfferLockingTests.cs
  - Game.Core.Tests/Save/SaveResumeBoundaryTests.cs
  - Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs
  - Game.Core.Tests/Tasks/Task0011AcceptanceTests.cs
  - Tests.Godot/Smoke/ContinueGateTests.gd
---

# 08 功能纵切（M1: Warrior 最小可玩闭环）

## 1. 目标与范围
M1 的目标是交付一个可完整运行、可验证、可复现的最小闭环：
- 角色：仅 Warrior。
- 地图：Act 1 最小可推进路径，覆盖 Combat/Event/Shop/Rest 节点。
- 战斗：回合制基础循环可跑通。
- 奖励：战斗后三选一候选集可锁定且可复现。
- 存档：单槽 Continue 与战斗边界符合 ADR-0032。
- 升级：仅 Rest 与特殊事件允许升级；商店禁止升级。

非目标：
- 三角色完整上线。
- 三 Act 全量内容与完整平衡。
- 云同步、多槽存档、联网依赖。

## 2. 核心规则冻结（M1）

### 2.1 战斗资源与抽牌
- 每回合默认能量重置为 3（除非规则修正）。
- 每回合默认抽牌 4。
- 手牌上限 10，超出时按 `instance_id` 升序裁剪。

### 2.2 Warrior 怒气
- 怒气是状态 Buff，不是第二属性条。
- 怒气仅战斗内存在，回合结束不衰减，不清空，持续到战斗结束。

### 2.3 卡牌形态与升级
- 同一 `card_id` 固定四种形态：Base、U1A、U1B、Ultimate。
- U1 升级为 A/B 二选一，不可逆。
- 特殊事件允许对已 U1 卡免费换路线，离开事件时确认最终结果。
- Ultimate 可从 Base 或 U1 直接进阶；不可逆；不可再升级；不可再换路线。
- 终极卡默认带 Exhaust（可被后续规则修饰）。

### 2.4 升级入口
- Rest：升级是多选一项之一，选择后可免费升级 1 张卡。
- 特殊事件：可触发代价升级或换路线升级。
- Shop：任何时候不提供升级语境与升级服务。

### 2.5 退出重进与确定性
- 允许退出重进，但读取单槽 autosave。
- 进入战斗后只保存战斗初始状态，战斗中不保存中间态。
- 同一存档点 + 同一输入序列必须得到同一候选集与同一结果。
- 奖励/事件候选集首次展示即锁定，不得通过退出重进重抽。

## 3. 运行时主路径

### 3.1 Happy Path
1) MainMenu -> New Run 或 Continue。  
2) 选择难度（1-10）并固化到 run 元数据。  
3) 选择 Warrior 进入 Act 1 地图。  
4) 进入 Combat，执行 StartOfTurn -> Draw -> Main -> EndOfTurn 循环。  
5) 战斗结束进入 Reward 三选一，锁定候选集。  
6) 进入 Event/Shop/Rest 任一节点，推进 run 状态机。  
7) 可在节点边界退出并 Continue，状态与候选集保持一致。

### 3.2 失败路径
- Continue 读档失败、迁移失败或完整性校验失败：阻断 Continue 并提示。
- 非法路径写入、越权访问、违规外链：拒绝并写审计日志。
- 战斗中断恢复：只能回到战斗初始状态。

## 4. 任务映射（T1-T57）
- Core 合同与规则：T3-T12、T24-T33、T46-T50。
- Scene/UI 与流程：T14-T23、T34-T45、T51-T52。
- Gate/质量与可观测：T53-T57。

关键 gate 任务：
- T56: Audit JSONL validation + gate integration。
- T57: Traceability gate for ADR/Chapter/Overlay links。

## 5. 验收关注点
- 不允许“功能可用但不可复现”。
- 不允许“可继续游戏但边界不清晰”。
- 不允许“UI 显示口径与 ADR 口径不一致”。

详见：`ACCEPTANCE_CHECKLIST.md`。

## 6. 关键契约回链（M1）
- 运行状态机与命令入口：`Game.Core/Contracts/Run/RunState.cs`、`Game.Core/Contracts/Run/RunCommand.cs`、`Game.Core/Contracts/Interfaces/IRunCommandHandler.cs`。
- 奖励候选锁定与可重复：`Game.Core/Contracts/Offers/OfferLockSnapshot.cs`、`Game.Core/Contracts/Offers/OfferProvenance.cs`、`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`。
- 单槽 Continue 与边界保存：`Game.Core/Contracts/Save/AutosaveSnapshot.cs`、`Game.Core/Contracts/Save/ContinueMetadata.cs`、`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`、`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`。
- 卡牌四形态与不可逆升级：`Game.Core/Contracts/Cards/CardDefinition.cs`、`Game.Core/Contracts/Cards/CardInstance.cs`、`Game.Core/Contracts/Cards/CardForm.cs`、`Game.Core/Contracts/Cards/UpgradeRoute.cs`。
- 统一事件类型常量：`Game.Core/Contracts/EventTypes.cs`。

- `Game.Core/Contracts/Events/CombatStartedEvent.cs`
- `Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
- `Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
- `Game.Core/Contracts/Events/CombatEndedEvent.cs`
- `Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
- `Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
- `Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
- `Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
- `Game.Core/Contracts/Events/EventEnteredEvent.cs`
- `Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`
- `Game.Core/Contracts/Events/RestOptionSelectedEvent.cs`
- `Game.Core/Contracts/Events/ShopItemPurchasedEvent.cs`

- `Game.Core/Contracts/Events/DeckInitializedEvent.cs`
- `Game.Core/Contracts/Events/DeckDrawnEvent.cs`
- `Game.Core/Contracts/Events/DeckDiscardedEvent.cs`
- `Game.Core/Contracts/Events/DeckRetainedEvent.cs`
- `Game.Core/Contracts/Events/DeckExhaustedEvent.cs`
- `Game.Core/Contracts/Events/DeckShuffledEvent.cs`
- `Game.Core/Contracts/Events/StatusAppliedEvent.cs`
- `Game.Core/Contracts/Events/StatusStackedEvent.cs`
- `Game.Core/Contracts/Events/StatusExpiredEvent.cs`
- `Game.Core/Contracts/Events/StatusDispelledEvent.cs`
- `Game.Core/Contracts/Events/SaveWriteSucceededEvent.cs`
- `Game.Core/Contracts/Events/SaveWriteFailedEvent.cs`
- `Game.Core/Contracts/Events/SaveLoadedEvent.cs`
- `Game.Core/Contracts/Events/SaveMigrationFailedEvent.cs`
- `Game.Core/Contracts/Events/RngStreamAdvancedEvent.cs`
- `Game.Core/Contracts/Events/RngStreamRestoredEvent.cs`

- `Game.Core/Contracts/Events/ActConfigLoadedEvent.cs`
- `Game.Core/Contracts/Events/AuditLoggedEvent.cs`
- `Game.Core/Contracts/Events/CardUltimatePromotedEvent.cs`
- `Game.Core/Contracts/Events/CardUpgradedEvent.cs`
- `Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
- `Game.Core/Contracts/Events/CombatFixedDamageResolvedEvent.cs`
- `Game.Core/Contracts/Events/CombatLoopHardStoppedEvent.cs`
- `Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
- `Game.Core/Contracts/Events/CurseAddedEvent.cs`
- `Game.Core/Contracts/Events/CurseRemovedEvent.cs`
- `Game.Core/Contracts/Events/DarkCostAppliedEvent.cs`
- `Game.Core/Contracts/Events/DifficultyModifierAppliedEvent.cs`
- `Game.Core/Contracts/Events/HealthUpdatedEvent.cs`
- `Game.Core/Contracts/Events/IntentSelectedEvent.cs`
- `Game.Core/Contracts/Events/MapNodeEnteredEvent.cs`
- `Game.Core/Contracts/Events/MapNodeLockedEvent.cs`
- `Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`
- `Game.Core/Contracts/Events/MapPathBacktrackBlockedEvent.cs`
- `Game.Core/Contracts/Events/RelicGrantedEvent.cs`
- `Game.Core/Contracts/Events/RunCharacterSelectedEvent.cs`
- `Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
- `Game.Core/Contracts/Events/RunResumedEvent.cs`
- `Game.Core/Contracts/Events/ScoreUpdatedEvent.cs`
- `Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs`
- `Game.Core/Contracts/Events/ShopInventoryLockedEvent.cs`
- `Game.Core/Contracts/Events/TraceabilityCheckedEvent.cs`

## Task53 Acceptance Conclusion
- Scope: `scripts/python/smoke_headless.py` strict/non-strict behavior and CI traceability evidence.
- Acceptance evidence must include:
  - `logs/ci/<date>/task-0053.json`
  - `logs/ci/<date>/smoke/<timestamp>/headless.out.log`
  - `logs/ci/<date>/smoke/<timestamp>/headless.err.log`
  - `logs/ci/<date>/smoke/<timestamp>/summary.json`
- Test-Refs:
  - `Game.Core.Tests/Tasks/Task53HeadlessRunnerCliValidationTests.cs`
  - `Game.Core.Tests/Tasks/Task53HeadlessRunnerArtifactsSummaryTests.cs`
  - `Game.Core.Tests/Tasks/Task53HeadlessRunnerPermissiveModeTests.cs`
- Conclusion rule: Feature-slice evidence must stay aligned with `ACCEPTANCE_CHECKLIST.md`; any mismatch is a fail.

## Task54 Gate Notes
- Task: `T54 Integrate GdUnit4 suites into quality_gates.py`
- ADR-Refs: `ADR-0005`, `ADR-0011`, `ADR-0024`
- Chapter-Refs: `CH06`, `CH07`, `CH10`
- Test-Refs:
  - `logs/ci/<date>/task-0054.json`
  - `logs/ci/<date>/quality-gates/summary.json`
  - `logs/e2e/<date>/gdunit/junit.xml`
  - `Tests.Godot/tests/Integration/test_quality_gates_gdunit_suite_wiring.gd`
  - `Tests.Godot/tests/Integration/test_gdunit_junit_artifact_export.gd`
  - `Game.Core.Tests/Tasks/Task54GdUnitGatePolicyTests.cs`
  - `Game.Core.Tests/Tasks/Task54QualityGateSummaryTests.cs`
  - `Game.Core.Tests/Tasks/Task54GdUnitSuiteSelectionTests.cs`
  - `Game.Core.Tests/Tasks/Task54CiDecisionSyncTests.cs`
  - `Tests.Godot/tests/ci/test_gdunit_suite_wiring.gd`
  - `Game.Core.Tests/Tasks/Task32AcceptanceTests.cs`
- Runtime notes:
  - `adapters/security` failure blocks overall decision.
  - `integration/ui` failure is soft and does not block overall decision.
