---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08章契约规范（M1）
Status: Draft
ADR-Refs:
  - ADR-0004
  - ADR-0020
  - ADR-0021
  - ADR-0032
  - ADR-0033
  - ADR-0010
Arch-Refs:
  - CH01
  - CH05
  - CH06
  - CH07
Test-Refs:
  - Game.Core.Tests/Contracts/DomainEventContractTests.cs
  - Game.Core.Tests/Contracts/CardContractsTests.cs
  - Game.Core.Tests/Contracts/OfferContractsTests.cs
  - Game.Core.Tests/Contracts/RunAndSaveContractsTests.cs
  - Game.Core.Tests/Contracts/EventContractsM1Tests.cs
  - Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs
  - Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs
  - Game.Core.Tests/Contracts/InterfaceContractsTests.cs
  - logs/ci/2026-02-12/contracts-validate.json
---

# 08章契约规范（M1）

## 1. 契约落盘与约束
- SSoT 位置：`Game.Core/Contracts/**`。
- 契约必须纯 C#（仅 BCL），禁止 `Godot.*` 依赖。
- 事件类型命名遵循 ADR-0004：`core.<entity>.<action>`、`ui.menu.<action>`、`screen.<name>.<action>`。
- 事件名称常量统一存放在 `Game.Core/Contracts/EventTypes.cs`，业务代码禁止硬编码 `"core.*"`。

## 2. 契约定义

### 2.1 事件
- **RunStartedEvent** (`core.run.started`)
  - 触发时机：新 Run 创建并初始化后。
  - 字段：`RunId`, `DifficultyId`, `StartedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunStartedEvent.cs`

- **RewardOfferLockedEvent** (`core.reward.offer.locked`)
  - 触发时机：奖励候选首次展示并锁定时。
  - 字段：`RunId`, `OfferContextId`, `StableIds`, `DisplayOrder`, `LockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`

- **AutosaveWrittenEvent** (`core.autosave.written`)
  - 触发时机：单槽 autosave 写入完成后。
  - 字段：`RunId`, `SavePointId`, `SavedAt`, `SchemaVersion`。
  - 契约位置：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`

- **RunContinueBlockedEvent** (`core.run.continue.blocked`)
  - 触发时机：Continue 被阻断（坏档/迁移失败/校验失败）。
  - 字段：`RunId`, `ReasonCode`, `Message`, `BlockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`

- **GuildMemberJoined** (`core.guild.member.joined`)
  - 触发时机：公会成员加入时。
  - 字段：`UserId`, `GuildId`, `JoinedAt`, `Role`。
  - 契约位置：`Game.Core/Contracts/Guild/GuildMemberJoined.cs`

### 2.1.2 M1主链事件扩展
- **RunStateTransitionedEvent** (`core.run.state.transitioned`)
  - 触发时机：Run 状态机通过 Command 发生转移后。
  - 字段：`RunId`, `FromState`, `ToState`, `Reason`, `TransitionedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`

- **CombatStartedEvent** (`core.combat.started`)
  - 触发时机：进入战斗结算循环起点时。
  - 字段：`RunId`, `CombatId`, `Turn`, `StartedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatStartedEvent.cs`

- **CombatCardPlayedEvent** (`core.combat.card.played`)
  - 触发时机：合法出牌并提交目标后。
  - 字段：`RunId`, `CombatId`, `ActorId`, `TargetId`, `CardInstanceId`, `EnergyCost`, `Sequence`, `PlayedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`

- **CombatStarted** (`core.combat.started`)
  - 触发时机：Task 7 验收中用于验证事件总线契约存在性的兼容 DTO。
  - 字段：`RunId`, `CombatId`, `Turn`, `StartedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatStarted.cs`

- **CardPlayed** (`core.combat.card.played`)
  - 触发时机：Task 7 验收中用于验证事件总线契约存在性的兼容 DTO。
  - 字段：`RunId`, `CombatId`, `CardInstanceId`, `PlayedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CardPlayed.cs`

- **CombatDamageResolvedEvent** (`core.combat.damage.resolved`)
  - 触发时机：伤害结算并完成护甲/状态修正后。
  - 字段：`RunId`, `CombatId`, `SourceId`, `TargetId`, `BaseDamage`, `FinalDamage`, `IsFixedDamage`, `TargetArmorAfter`, `ResolvedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`

- **CombatEndedEvent** (`core.combat.ended`)
  - 触发时机：战斗胜负已定并离开战斗场景时。
  - 字段：`RunId`, `CombatId`, `PlayerWon`, `Turns`, `EndedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatEndedEvent.cs`

- **RewardOfferPresentedEvent** (`core.reward.offer.presented`)
  - 触发时机：奖励三选一面板首次展示候选集时。
  - 字段：`RunId`, `OfferContextId`, `CandidateIds`, `DisplayOrder`, `PresentedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`

- **RewardOfferSelectedEvent** (`core.reward.offer.selected`)
  - 触发时机：玩家确认选择奖励项后。
  - 字段：`RunId`, `OfferContextId`, `SelectedId`, `SelectedIndex`, `SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`

- **RewardOfferSkippedEvent** (`core.reward.offer.skipped`)
  - 触发时机：奖励面板执行跳过后。
  - 字段：`RunId`, `OfferContextId`, `SkippedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`

- **EventEnteredEvent** (`core.event.entered`)
  - 触发时机：进入事件节点且选项集合被锁定时。
  - 字段：`RunId`, `EventId`, `NodeId`, `OptionIds`, `EnteredAt`。
  - 契约位置：`Game.Core/Contracts/Events/EventEnteredEvent.cs`

- **EventChoiceCommittedEvent** (`core.event.choice.committed`)
  - 触发时机：事件选项被确认并写入 run 状态后。
  - 字段：`RunId`, `EventId`, `OptionId`, `ChoiceResultId`, `CommittedAt`。
  - 契约位置：`Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`

- **RestOptionSelectedEvent** (`core.rest.option.selected`)
  - 触发时机：休整节点确认选项后。
  - 字段：`RunId`, `NodeId`, `OptionId`, `TargetCardInstanceId`, `SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RestOptionSelectedEvent.cs`

- **ShopItemPurchasedEvent** (`core.shop.item.purchased`)
  - 触发时机：商店锁定库存中的商品购买成功后。
  - 字段：`RunId`, `ShopId`, `ItemId`, `ItemType`, `Price`, `PurchasedAt`。
  - 契约位置：`Game.Core/Contracts/Events/ShopItemPurchasedEvent.cs`

### 2.1.3 M1二批主线事件（Deck/Status/Save/RNG）
- **DeckInitializedEvent** (`core.deck.initialized`)
  - 触发时机：战斗开始并初始化抽牌堆/弃牌堆/消耗堆时。
  - 字段：`RunId`, `CombatId`, `DrawPileCount`, `DiscardPileCount`, `ExhaustPileCount`, `InitializedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckInitializedEvent.cs`

- **DeckDrawnEvent** (`core.deck.drawn`)
  - 触发时机：抽牌阶段将卡牌加入手牌后。
  - 字段：`RunId`, `CombatId`, `ActorId`, `DrawnCardInstanceIds`, `DrawCount`, `DrawPileCountAfter`, `DrawnAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckDrawnEvent.cs`

- **DeckDiscardedEvent** (`core.deck.discarded`)
  - 触发时机：手牌进入弃牌堆后。
  - 字段：`RunId`, `CombatId`, `ActorId`, `CardInstanceIds`, `DiscardPileCountAfter`, `DiscardedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckDiscardedEvent.cs`

- **DeckRetainedEvent** (`core.deck.retained`)
  - 触发时机：回合结束后保留牌集合确定时。
  - 字段：`RunId`, `CombatId`, `ActorId`, `CardInstanceIds`, `RetainedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckRetainedEvent.cs`

- **DeckExhaustedEvent** (`core.deck.exhausted`)
  - 触发时机：卡牌进入消耗堆后。
  - 字段：`RunId`, `CombatId`, `ActorId`, `CardInstanceId`, `ExhaustPileCountAfter`, `ExhaustedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckExhaustedEvent.cs`

- **DeckShuffledEvent** (`core.deck.shuffled`)
  - 触发时机：弃牌堆回洗到抽牌堆后。
  - 字段：`RunId`, `CombatId`, `DrawPileCountBefore`, `DiscardPileCountBefore`, `DrawPileCountAfter`, `DiscardPileCountAfter`, `ShuffledAt`。
  - 契约位置：`Game.Core/Contracts/Events/DeckShuffledEvent.cs`

- **StatusAppliedEvent** (`core.status.applied`)
  - 触发时机：状态首次施加到目标后。
  - 字段：`RunId`, `CombatId`, `TargetId`, `StatusId`, `Stacks`, `DurationTurns`, `SourceId`, `AppliedAt`。
  - 契约位置：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`

- **StatusStackedEvent** (`core.status.stacked`)
  - 触发时机：同名状态层数发生变化后。
  - 字段：`RunId`, `CombatId`, `TargetId`, `StatusId`, `PreviousStacks`, `CurrentStacks`, `StackedAt`。
  - 契约位置：`Game.Core/Contracts/Events/StatusStackedEvent.cs`

- **StatusExpiredEvent** (`core.status.expired`)
  - 触发时机：状态自然到期被移除后。
  - 字段：`RunId`, `CombatId`, `TargetId`, `StatusId`, `ExpiredAt`。
  - 契约位置：`Game.Core/Contracts/Events/StatusExpiredEvent.cs`

- **StatusDispelledEvent** (`core.status.dispelled`)
  - 触发时机：状态被驱散后。
  - 字段：`RunId`, `CombatId`, `TargetId`, `StatusId`, `Reason`, `DispelledAt`。
  - 契约位置：`Game.Core/Contracts/Events/StatusDispelledEvent.cs`

- **SaveWriteSucceededEvent** (`core.save.write.succeeded`)
  - 触发时机：autosave 写入成功后。
  - 字段：`RunId`, `SavePointId`, `SchemaVersion`, `IntegrityHash`, `WrittenAt`。
  - 契约位置：`Game.Core/Contracts/Events/SaveWriteSucceededEvent.cs`

- **SaveWriteFailedEvent** (`core.save.write.failed`)
  - 触发时机：autosave 写入失败后。
  - 字段：`RunId`, `SavePointId`, `ReasonCode`, `Message`, `FailedAt`。
  - `ReasonCode` 最小覆盖：`temp_write_failed`、`atomic_replace_failed`、`save_failed`。
  - `Message` 用于向调用方暴露失败摘要；更细的结构化 evidence（如 `action`, `target`, `caller`, `temp_path`）由运行时异常与审计链承接。
  - 契约位置：`Game.Core/Contracts/Events/SaveWriteFailedEvent.cs`

- **SaveLoadedEvent** (`core.save.loaded`)
  - 触发时机：Continue 读取存档成功后。
  - 字段：`RunId`, `SavePointId`, `SchemaVersion`, `LoadedAt`。
  - 契约位置：`Game.Core/Contracts/Events/SaveLoadedEvent.cs`

- **SaveMigrationFailedEvent** (`core.save.migration.failed`)
  - 触发时机：存档版本迁移失败后。
  - 字段：`RunId`, `FromSchema`, `ToSchema`, `ReasonCode`, `FailedAt`。
  - 契约位置：`Game.Core/Contracts/Events/SaveMigrationFailedEvent.cs`

- **RngStreamAdvancedEvent** (`core.rng.stream.advanced`)
  - 触发时机：指定 RNG 流消费随机数后。
  - 字段：`RunId`, `StreamName`, `PositionBefore`, `PositionAfter`, `AdvancedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RngStreamAdvancedEvent.cs`

- **RngStreamRestoredEvent** (`core.rng.stream.restored`)
  - 触发时机：从快照恢复 RNG 流状态后。
  - 字段：`RunId`, `StreamName`, `PositionAfter`, `SnapshotHash`, `RestoredAt`。
  - 契约位置：`Game.Core/Contracts/Events/RngStreamRestoredEvent.cs`

### 2.1.4 M1三批主线事件（Run/Map/Card/Shop/Gate）

- **ActConfigLoadedEvent** (`core.act.config.loaded`)
  - 触发时机：act configuration loaded and frozen for current run。
  - 字段：`RunId, ActId, ConfigVersion, LoadedAt`。
  - 契约位置：`Game.Core/Contracts/Events/ActConfigLoadedEvent.cs`

- **AuditLoggedEvent** (`core.audit.logged`)
  - 触发时机：audit log entry persisted。
  - 字段：`RunId, Action, Reason, Target, Caller, LoggedAt`。
  - 契约位置：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`

- **CardUltimatePromotedEvent** (`core.card.ultimate.promoted`)
  - 触发时机：card promoted into ultimate form。
  - 字段：`RunId, CardInstanceId, CardId, FromForm, ToForm, PromotedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CardUltimatePromotedEvent.cs`

- **CardUpgradedEvent** (`core.card.upgraded`)
  - 触发时机：card upgraded into branch form。
  - 字段：`RunId, CardInstanceId, CardId, FromForm, ToForm, Route, UpgradedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CardUpgradedEvent.cs`

- **CombatCardInvalidPlayBlockedEvent** (`core.combat.card.invalid_play_blocked`)
  - 触发时机：invalid card play blocked by rules。
  - 字段：`RunId, CombatId, ActorId, CardInstanceId, ReasonCode, BlockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`

- **CombatFixedDamageResolvedEvent** (`core.combat.fixed_damage.resolved`)
  - 触发时机：fixed damage resolved。
  - 字段：`RunId, CombatId, SourceId, TargetId, Amount, TargetArmorAfter, ResolvedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatFixedDamageResolvedEvent.cs`

- **CombatLoopHardStoppedEvent** (`core.combat.loop.hard_stopped`)
  - 触发时机：combat hard-stop threshold reached。
  - 字段：`RunId, CombatId, PlayedCardsCount, Threshold, ReasonCode, StoppedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatLoopHardStoppedEvent.cs`

- **CombatTurnStartedEvent** (`core.combat.turn.started`)
  - 触发时机：combat turn opened before main phase。
  - 字段：`RunId, CombatId, Turn, ActorId, Energy, DrawCount, StartedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`

- **CurseAddedEvent** (`core.curse.added`)
  - 触发时机：curse card added to run deck。
  - 字段：`RunId, CardId, SourceType, SourceId, AddedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CurseAddedEvent.cs`

- **CurseRemovedEvent** (`core.curse.removed`)
  - 触发时机：curse card removed from run deck。
  - 字段：`RunId, CardId, SourceType, SourceId, RemovedAt`。
  - 契约位置：`Game.Core/Contracts/Events/CurseRemovedEvent.cs`

- **DarkCostAppliedEvent** (`core.darkcost.applied`)
  - 触发时机：dark cost applied to run state。
  - 字段：`RunId, SourceId, CostType, Amount, AppliedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DarkCostAppliedEvent.cs`

- **DifficultyModifierAppliedEvent** (`core.difficulty.modifier.applied`)
  - 触发时机：difficulty modifier applied。
  - 字段：`RunId, DifficultyId, ModifierId, Value, AppliedAt`。
  - 契约位置：`Game.Core/Contracts/Events/DifficultyModifierAppliedEvent.cs`

- **HealthUpdatedEvent** (`core.health.updated`)
  - 触发时机：health value updated。
  - 字段：`RunId, TargetId, PreviousHealth, CurrentHealth, Delta, UpdatedAt`。
  - 契约位置：`Game.Core/Contracts/Events/HealthUpdatedEvent.cs`

- **IntentSelectedEvent** (`core.intent.selected`)
  - 触发时机：enemy intent selected for turn。
  - 字段：`RunId, CombatId, ActorId, IntentId, SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`

- **MapNodeEnteredEvent** (`core.map.node.entered`)
  - 触发时机：map node entered。
  - 字段：`RunId, ActId, NodeId, NodeType, EnteredAt`。
  - 契约位置：`Game.Core/Contracts/Events/MapNodeEnteredEvent.cs`

- **MapNodeLockedEvent** (`core.map.node.locked`)
  - 触发时机：map node locked by route constraint。
  - 字段：`RunId, ActId, NodeId, ReasonCode, LockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/MapNodeLockedEvent.cs`

- **MapNodeSelectedEvent** (`core.map.node.selected`)
  - 触发时机：map node selected and committed。
  - 字段：`RunId, ActId, NodeId, SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`

- **MapPathBacktrackBlockedEvent** (`core.map.path.backtrack.blocked`)
  - 触发时机：path backtrack blocked。
  - 字段：`RunId, FromNodeId, ToNodeId, ReasonCode, BlockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/MapPathBacktrackBlockedEvent.cs`

- **RelicGrantedEvent** (`core.relic.granted`)
  - 触发时机：relic granted to inventory。
  - 字段：`RunId, RelicId, SourceType, SourceId, GrantedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`

- **RunCharacterSelectedEvent** (`core.run.character.selected`)
  - 触发时机：run character selected。
  - 字段：`RunId, CharacterId, SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunCharacterSelectedEvent.cs`

- **RunDifficultySelectedEvent** (`core.run.difficulty.selected`)
  - 触发时机：run difficulty selected and frozen。
  - 字段：`RunId, DifficultyId, SelectedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`

- **RunResumedEvent** (`core.run.resumed`)
  - 触发时机：continue resumed run from autosave。
  - 字段：`RunId, SavePointId, ResumedAt`。
  - 契约位置：`Game.Core/Contracts/Events/RunResumedEvent.cs`

- **ScoreUpdatedEvent** (`core.score.updated`)
  - 触发时机：score value updated。
  - 字段：`RunId, PreviousScore, CurrentScore, Delta, UpdatedAt`。
  - 契约位置：`Game.Core/Contracts/Events/ScoreUpdatedEvent.cs`

- **ShopCurseRemovedEvent** (`core.shop.curse.removed`)
  - 触发时机：shop curse removal purchased。
  - 字段：`RunId, ShopId, CardId, Price, RemovedAt`。
  - 契约位置：`Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs`

- **ShopInventoryLockedEvent** (`core.shop.inventory.locked`)
  - 触发时机：shop inventory first shown and locked。
  - 字段：`RunId, ShopId, StableIds, DisplayOrder, LockedAt`。
  - 契约位置：`Game.Core/Contracts/Events/ShopInventoryLockedEvent.cs`

- **TraceabilityCheckedEvent** (`core.traceability.checked`)
  - 触发时机：traceability gate completed。
  - 字段：`RunId, Scope, Status, CheckedAt`。
  - 契约位置：`Game.Core/Contracts/Events/TraceabilityCheckedEvent.cs`

### 2.2 DTO 与枚举
- Combat UI HUD snapshot
  - `Game.Core/Contracts/Combat/CombatHudSnapshot.cs`
  - Purpose: adapter-facing immutable read model for hand cards, energy, and pile counters.
- 卡牌与形态
  - `Game.Core/Contracts/Cards/CardDefinition.cs`
  - `Game.Core/Contracts/Cards/CardForm.cs`
  - `Game.Core/Contracts/Cards/CardInstance.cs`
  - `Game.Core/Contracts/Cards/CardInstanceModifier.cs`
  - `Game.Core/Contracts/Cards/UpgradeRoute.cs`
- 奖励候选
  - `Game.Core/Contracts/Offers/OfferItem.cs`
  - `Game.Core/Contracts/Offers/OfferLockSnapshot.cs`
  - `Game.Core/Contracts/Offers/OfferProvenance.cs`
  - `Game.Core/Contracts/Offers/OfferSourceType.cs`
- 状态系统
  - `Game.Core/Contracts/Status/Status.cs`
  - `Game.Core/Contracts/Status/StatusInstance.cs`
  - `Game.Core/Contracts/Status/StatusOperations.cs`
  - `Game.Core/Contracts/Status/StatusType.cs`
  - `Game.Core/Contracts/Status/ExpiresTiming.cs`
- Run 与存档
  - `Game.Core/Contracts/Run/RunState.cs`
  - `Game.Core/Contracts/Run/RunCommand.cs`
  - `Game.Core/Contracts/Run/RunTransition.cs`
  - `Game.Core/Contracts/Save/AutosaveSnapshot.cs`
  - `Game.Core/Contracts/Save/ContinueMetadata.cs`
  - `Game.Core/Contracts/Save/ContinueGateDecision.cs`
  - `Game.Core/Contracts/Save/ContinueLoadValidationResult.cs`
  - `Game.Core/Contracts/Save/SaveMigrationResult.cs`
- 配置与内容
  - `Game.Core/Contracts/Config/DifficultyConfig.cs`
  - `Game.Core/Contracts/Config/ActConfig.cs`
  - `Game.Core/Contracts/Config/ActConfigLoadResult.cs`
  - `Game.Core/Contracts/Content/RelicDefinition.cs`
  - `Game.Core/Contracts/Content/RelicInstance.cs`
  - `Game.Core/Contracts/Content/CurseDefinition.cs`
- 通用事件信封与事件常量
  - `Game.Core/Contracts/DomainEvent.cs`
  - `Game.Core/Contracts/EventTypes.cs`
  - `Game.Core/Contracts/RngStreamType.cs`

### 2.3 接口契约
- `Game.Core/Contracts/Interfaces/IRngStreamRegistry.cs`
- `Game.Core/Contracts/Interfaces/IOfferService.cs`
- `Game.Core/Contracts/Interfaces/IStatusService.cs`
- `Game.Core/Contracts/Interfaces/ISaveService.cs`
- `Game.Core/Contracts/Interfaces/ISaveMigrationService.cs`
- `Game.Core/Contracts/Interfaces/IRunCommandHandler.cs`
- `Game.Core/Contracts/Interfaces/IDifficultyProvider.cs`
- `Game.Core/Contracts/Interfaces/IActConfigProvider.cs`
- `Game.Core/Contracts/Interfaces/IRelicService.cs`
- `Game.Core/Contracts/Interfaces/ICurseService.cs`
- `Game.Core/Contracts/Interfaces/IEventBus.cs`
  - 用途：跨层发布/订阅领域事件，作为 Core 与 Adapter 的统一事件总线抽象。
  - 方法：`PublishAsync(DomainEvent evt)`、`Subscribe(Func<DomainEvent, Task> handler)`。

## 3. 回顾式审查结果（6 点）
- 命名：事件常量统一归口 `EventTypes`，符合 ADR-0004 规范。
- 文档注释：新增事件契约均包含 XML `summary/remarks`。
- EventType 常量：新增事件全部定义 `EventType`，且值与文档一致。
- 纯 C#：新增契约不依赖 Godot API。
- 类型明确：字段使用 `string`、`DateTimeOffset`、`int`、`IReadOnlyList<T>` 等明确类型。
- Overlay 回链：本页记录了新增事件/DTO/接口及契约路径。

## 4. Task 6 Contract Backlink
- **CombatLoop** (`core.combat.loop`)
  - 触发时机：战斗阶段机进行合法/非法迁移校验时
  - 字段：`CurrentPhase`, `LastGuardFailureReason`
  - 契约位置：`Game.Core/Contracts/Combat/CombatLoop.cs`
- **CombatLoopPhase** (`core.combat.loop.phase`)
  - 用途：定义战斗阶段枚举（StartOfTurn, Draw, Main, EndOfTurn）
  - 契约位置：`Game.Core/Contracts/Combat/CombatLoop.cs`

