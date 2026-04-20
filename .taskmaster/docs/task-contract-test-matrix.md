# 任务-契约-测试三向矩阵

## 摘要

- 扫描任务数：113
- 含 contractRefs 的任务数：80
- contractRefs 总数：221
- 唯一事件引用数：59
- 未解析事件数：0
- 已解析但无测试引用的事件数：0
- EventTypes 常量数：62
- 强类型事件契约数：61

## 任务明细

### NG-0002 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement core contracts for offer locking and deterministic outcomes
- 状态：pending
- layer：ci
- taskmaster_id：4
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.selected`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.skipped`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### NG-0003 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement core contracts for status and modifier system
- 状态：pending
- layer：ci
- taskmaster_id：5
- 事件：`core.status.applied`
  - 契约文件：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.status.stacked`
  - 契约文件：`Game.Core/Contracts/Events/StatusStackedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.expired`
  - 契约文件：`Game.Core/Contracts/Events/StatusExpiredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.dispelled`
  - 契约文件：`Game.Core/Contracts/Events/StatusDispelledEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### NG-0004 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement core contracts for combat loop and resolution pipeline
- 状态：pending
- layer：ci
- taskmaster_id：6
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.health.updated`
  - 契约文件：`Game.Core/Contracts/Events/HealthUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.score.updated`
  - 契约文件：`Game.Core/Contracts/Events/ScoreUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### NG-0005 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement save serialization and atomic write
- 状态：pending
- layer：core
- taskmaster_id：12
- 事件：`core.save.write.succeeded`
  - 契约文件：`Game.Core/Contracts/Events/SaveWriteSucceededEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`
- 事件：`core.save.write.failed`
  - 契约文件：`Game.Core/Contracts/Events/SaveWriteFailedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`
- 事件：`core.save.loaded`
  - 契约文件：`Game.Core/Contracts/Events/SaveLoadedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`

### NG-0007 (.taskmaster/tasks/tasks_back.json)

- 标题：Create main menu scene with new run and continue options
- 状态：done
- layer：adapter
- taskmaster_id：14
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.resumed`
  - 契约文件：`Game.Core/Contracts/Events/RunResumedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### NG-0008 (.taskmaster/tasks/tasks_back.json)

- 标题：Create modular Act structure for map system
- 状态：pending
- layer：adapter
- taskmaster_id：17
- 事件：`core.map.node.entered`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.node.locked`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.node.selected`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### NG-0009 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement reward scene with card three-choice-one and offer locking
- 状态：pending
- layer：adapter
- taskmaster_id：19
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.selected`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.skipped`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### NG-0010 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement card drop pools per Act and encounter type
- 状态：pending
- layer：core
- taskmaster_id：29
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### NG-0011 (.taskmaster/tasks/tasks_back.json)

- 标题：Define relic contracts and instance model
- 状态：pending
- layer：core
- taskmaster_id：30
- 事件：`core.relic.granted`
  - 契约文件：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`

### NG-0012 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement autosave triggers per determinism policy
- 状态：pending
- layer：core
- taskmaster_id：36
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.event.choice.committed`
  - 契约文件：`Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`

### NG-0013 (.taskmaster/tasks/tasks_back.json)

- 标题：Audit logging for determinism and security events
- 状态：pending
- layer：ci
- taskmaster_id：38
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### NG-0014 (.taskmaster/tasks/tasks_back.json)

- 标题：Run state machine with Command-only transitions
- 状态：pending
- layer：core
- taskmaster_id：43
- 事件：`core.run.state.transitioned`
  - 契约文件：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### NG-0015 (.taskmaster/tasks/tasks_back.json)

- 标题：Deterministic resume integration tests (headless)
- 状态：pending
- layer：adapter
- taskmaster_id：44
- 事件：`core.run.resumed`
  - 契约文件：`Game.Core/Contracts/Events/RunResumedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### NG-0016 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement stability safeguards for combat loop
- 状态：pending
- layer：core
- taskmaster_id：49
- 事件：`core.combat.loop.hard_stopped`
  - 契约文件：`Game.Core/Contracts/Events/CombatLoopHardStoppedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`
- 事件：`core.combat.card.invalid_play_blocked`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### NG-0017 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement save migration validation and failure blocking
- 状态：pending
- layer：core
- taskmaster_id：50
- 事件：`core.save.migration.failed`
  - 契约文件：`Game.Core/Contracts/Events/SaveMigrationFailedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### NG-0018 (.taskmaster/tasks/tasks_back.json)

- 标题：Integrate combat turn flow and persistence
- 状态：pending
- layer：core
- taskmaster_id：51
- 事件：`core.combat.turn.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### NG-0019 (.taskmaster/tasks/tasks_back.json)

- 标题：Implement enemy intent selection logic
- 状态：pending
- layer：ci
- taskmaster_id：52
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### NG-0020 (.taskmaster/tasks/tasks_back.json)

- 标题：Headless smoke runner (Python) + strict mode
- 状态：done
- layer：ci
- taskmaster_id：53
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### NG-0023 (.taskmaster/tasks/tasks_back.json)

- 标题：Audit JSONL validation + gate integration
- 状态：done
- layer：ci
- taskmaster_id：56
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### NG-0043 (.taskmaster/tasks/tasks_back.json)

- 标题：Traceability gate for ADR/Chapter/Overlay links
- 状态：pending
- layer：ci
- taskmaster_id：57
- 事件：`core.traceability.checked`
  - 契约文件：`Game.Core/Contracts/Events/TraceabilityCheckedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### NG-0036 (.taskmaster/tasks/tasks_back.json)

- 标题：Signal contract validation and tests (security-sensitive)
- 状态：pending
- layer：ci
- taskmaster_id：None
- 事件：`core.guild.member.joined`
  - 契约文件：`Game.Core/Contracts/Guild/GuildMemberJoined.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0102 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Create core project structure and namespaces
- 状态：done
- layer：adapter
- taskmaster_id：2
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.state.transitioned`
  - 契约文件：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### GM-0103 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement core contracts for card identity and forms
- 状态：done
- layer：core
- taskmaster_id：3
- 事件：`core.card.upgraded`
  - 契约文件：`Game.Core/Contracts/Events/CardUpgradedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.card.ultimate.promoted`
  - 契约文件：`Game.Core/Contracts/Events/CardUltimatePromotedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0104 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement core contracts for offer locking and deterministic outcomes
- 状态：done
- layer：ci
- taskmaster_id：4
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.selected`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.skipped`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0105 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement core contracts for status and modifier system
- 状态：done
- layer：ci
- taskmaster_id：5
- 事件：`core.status.applied`
  - 契约文件：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.status.stacked`
  - 契约文件：`Game.Core/Contracts/Events/StatusStackedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.expired`
  - 契约文件：`Game.Core/Contracts/Events/StatusExpiredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.dispelled`
  - 契约文件：`Game.Core/Contracts/Events/StatusDispelledEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0106 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement core contracts for combat loop and resolution pipeline
- 状态：done
- layer：ci
- taskmaster_id：6
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.health.updated`
  - 契约文件：`Game.Core/Contracts/Events/HealthUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.score.updated`
  - 契约文件：`Game.Core/Contracts/Events/ScoreUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0107 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Set up event bus and contracts location
- 状态：done
- layer：core
- taskmaster_id：7
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.run.state.transitioned`
  - 契约文件：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### GM-0108 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement core logic for card identity and forms
- 状态：done
- layer：ci
- taskmaster_id：8
- 事件：`core.card.upgraded`
  - 契约文件：`Game.Core/Contracts/Events/CardUpgradedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.card.ultimate.promoted`
  - 契约文件：`Game.Core/Contracts/Events/CardUltimatePromotedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0109 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement deterministic RNG stream registry
- 状态：done
- layer：core
- taskmaster_id：9
- 事件：`core.rng.stream.advanced`
  - 契约文件：`Game.Core/Contracts/Events/RngStreamAdvancedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.rng.stream.restored`
  - 契约文件：`Game.Core/Contracts/Events/RngStreamRestoredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0110 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement status application, stacking, and decay
- 状态：done
- layer：core
- taskmaster_id：10
- 事件：`core.status.applied`
  - 契约文件：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.status.stacked`
  - 契约文件：`Game.Core/Contracts/Events/StatusStackedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.expired`
  - 契约文件：`Game.Core/Contracts/Events/StatusExpiredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.status.dispelled`
  - 契约文件：`Game.Core/Contracts/Events/StatusDispelledEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0111 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement combat resolution pipeline (core)
- 状态：done
- layer：ci
- taskmaster_id：11
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.health.updated`
  - 契约文件：`Game.Core/Contracts/Events/HealthUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0112 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement save serialization and atomic write
- 状态：done
- layer：core
- taskmaster_id：12
- 事件：`core.save.write.succeeded`
  - 契约文件：`Game.Core/Contracts/Events/SaveWriteSucceededEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`
- 事件：`core.save.write.failed`
  - 契约文件：`Game.Core/Contracts/Events/SaveWriteFailedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`
- 事件：`core.save.loaded`
  - 契约文件：`Game.Core/Contracts/Events/SaveLoadedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`

### GM-0114 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Create main menu scene with new run and continue options
- 状态：done
- layer：adapter
- taskmaster_id：14
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.resumed`
  - 契约文件：`Game.Core/Contracts/Events/RunResumedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### GM-0115 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement difficulty selection UI
- 状态：done
- layer：adapter
- taskmaster_id：15
- 事件：`core.run.difficulty.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs`

### GM-0116 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement character selection UI for Warrior only
- 状态：done
- layer：adapter
- taskmaster_id：16
- 事件：`core.run.character.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunCharacterSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task16RunCharacterSelectedContractTests.cs`

### GM-0117 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Create modular Act structure for map system
- 状态：done
- layer：adapter
- taskmaster_id：17
- 事件：`core.map.node.entered`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.node.locked`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.node.selected`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0118 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement combat scene UI shell and bindings
- 状态：done
- layer：adapter
- taskmaster_id：18
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.turn.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0119 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement reward scene with card three-choice-one and offer locking
- 状态：done
- layer：adapter
- taskmaster_id：19
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.selected`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.skipped`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0120 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement shop scene with inventory locking and no upgrade context
- 状态：done
- layer：adapter
- taskmaster_id：20
- 事件：`core.shop.inventory.locked`
  - 契约文件：`Game.Core/Contracts/Events/ShopInventoryLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.shop.item.purchased`
  - 契约文件：`Game.Core/Contracts/Events/ShopItemPurchasedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.shop.curse.removed`
  - 契约文件：`Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`

### GM-0121 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement rest scene with free upgrade option
- 状态：done
- layer：adapter
- taskmaster_id：21
- 事件：`core.rest.option.selected`
  - 契约文件：`Game.Core/Contracts/Events/RestOptionSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.card.upgraded`
  - 契约文件：`Game.Core/Contracts/Events/CardUpgradedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0122 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement event scene with dark cost examples
- 状态：done
- layer：adapter
- taskmaster_id：22
- 事件：`core.event.entered`
  - 契约文件：`Game.Core/Contracts/Events/EventEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- 事件：`core.event.choice.committed`
  - 契约文件：`Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.darkcost.applied`
  - 契约文件：`Game.Core/Contracts/Events/DarkCostAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`

### GM-0124 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement Warrior starting deck with 10 cards
- 状态：done
- layer：core
- taskmaster_id：24
- 事件：`core.deck.initialized`
  - 契约文件：`Game.Core/Contracts/Events/DeckInitializedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0125 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement rage as state buff for Warrior
- 状态：done
- layer：core
- taskmaster_id：25
- 事件：`core.status.applied`
  - 契约文件：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.status.stacked`
  - 契约文件：`Game.Core/Contracts/Events/StatusStackedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0126 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Define difficulty configuration contract and immutability
- 状态：done
- layer：adapter
- taskmaster_id：26
- 事件：`core.run.difficulty.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs`

### GM-0127 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement difficulty rule modifiers
- 状态：done
- layer：core
- taskmaster_id：27
- 事件：`core.difficulty.modifier.applied`
  - 契约文件：`Game.Core/Contracts/Events/DifficultyModifierAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0128 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Create ActConfig data model and loader
- 状态：done
- layer：core
- taskmaster_id：28
- 事件：`core.act.config.loaded`
  - 契约文件：`Game.Core/Contracts/Events/ActConfigLoadedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0129 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement card drop pools per Act and encounter type
- 状态：done
- layer：core
- taskmaster_id：29
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0130 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Define relic contracts and instance model
- 状态：done
- layer：core
- taskmaster_id：30
- 事件：`core.relic.granted`
  - 契约文件：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`

### GM-0131 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement 20 starting relic definitions and uniqueness checks
- 状态：done
- layer：core
- taskmaster_id：31
- 事件：`core.relic.granted`
  - 契约文件：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`

### GM-0132 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement curse cards and removal services
- 状态：done
- layer：core
- taskmaster_id：32
- 事件：`core.curse.added`
  - 契约文件：`Game.Core/Contracts/Events/CurseAddedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.curse.removed`
  - 契约文件：`Game.Core/Contracts/Events/CurseRemovedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.shop.curse.removed`
  - 契约文件：`Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`

### GM-0133 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement deck operations service (draw/discard/exhaust/retain)
- 状态：done
- layer：adapter
- taskmaster_id：33
- 事件：`core.deck.drawn`
  - 契约文件：`Game.Core/Contracts/Events/DeckDrawnEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.deck.discarded`
  - 契约文件：`Game.Core/Contracts/Events/DeckDiscardedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.deck.exhausted`
  - 契约文件：`Game.Core/Contracts/Events/DeckExhaustedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.deck.retained`
  - 契约文件：`Game.Core/Contracts/Events/DeckRetainedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.deck.shuffled`
  - 契约文件：`Game.Core/Contracts/Events/DeckShuffledEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`

### GM-0134 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement card targeting and drag UX
- 状态：done
- layer：adapter
- taskmaster_id：34
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.card.invalid_play_blocked`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0135 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement end-of-combat resolution pipeline
- 状态：done
- layer：core
- taskmaster_id：35
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0136 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement autosave triggers per determinism policy
- 状态：done
- layer：core
- taskmaster_id：36
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.event.choice.committed`
  - 契约文件：`Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`

### GM-0137 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Single-slot continue metadata and integrity checks
- 状态：done
- layer：core
- taskmaster_id：37
- 事件：`core.run.resumed`
  - 契约文件：`Game.Core/Contracts/Events/RunResumedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.save.loaded`
  - 契约文件：`Game.Core/Contracts/Events/SaveLoadedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`

### GM-0138 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Audit logging for determinism and security events
- 状态：done
- layer：ci
- taskmaster_id：38
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### GM-0139 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Populate translations for M1 cards, relics, events
- 状态：done
- layer：adapter
- taskmaster_id：39
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.event.entered`
  - 契约文件：`Game.Core/Contracts/Events/EventEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- 事件：`core.relic.granted`
  - 契约文件：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- 事件：`core.curse.added`
  - 契约文件：`Game.Core/Contracts/Events/CurseAddedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0140 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Define Act 1 enemy data and definitions
- 状态：done
- layer：core
- taskmaster_id：40
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0141 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement enemy intent display and preview UI
- 状态：done
- layer：adapter
- taskmaster_id：41
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.turn.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0142 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Map node entry gating and backtracking rules
- 状态：done
- layer：adapter
- taskmaster_id：42
- 事件：`core.map.node.locked`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.node.selected`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.map.path.backtrack.blocked`
  - 契约文件：`Game.Core/Contracts/Events/MapPathBacktrackBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0143 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Run state machine with Command-only transitions
- 状态：done
- layer：core
- taskmaster_id：43
- 事件：`core.run.state.transitioned`
  - 契约文件：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### GM-0144 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Deterministic resume integration tests (headless)
- 状态：done
- layer：adapter
- taskmaster_id：44
- 事件：`core.run.resumed`
  - 契约文件：`Game.Core/Contracts/Events/RunResumedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`

### GM-0145 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Display difficulty in HUD and run summary
- 状态：done
- layer：adapter
- taskmaster_id：45
- 事件：`core.run.difficulty.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.score.updated`
  - 契约文件：`Game.Core/Contracts/Events/ScoreUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0146 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement offer locking generation using RNG streams
- 状态：done
- layer：core
- taskmaster_id：46
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0147 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement status trigger ordering and fixed damage rules
- 状态：done
- layer：core
- taskmaster_id：47
- 事件：`core.status.applied`
  - 契约文件：`Game.Core/Contracts/Events/StatusAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.status.expired`
  - 契约文件：`Game.Core/Contracts/Events/StatusExpiredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.combat.fixed_damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatFixedDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`

### GM-0148 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement damage calculation and AOE ordering
- 状态：done
- layer：core
- taskmaster_id：48
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0149 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement stability safeguards for combat loop
- 状态：done
- layer：core
- taskmaster_id：49
- 事件：`core.combat.loop.hard_stopped`
  - 契约文件：`Game.Core/Contracts/Events/CombatLoopHardStoppedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`
- 事件：`core.combat.card.invalid_play_blocked`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0150 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement save migration validation and failure blocking
- 状态：done
- layer：core
- taskmaster_id：50
- 事件：`core.save.migration.failed`
  - 契约文件：`Game.Core/Contracts/Events/SaveMigrationFailedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DeckStatusSaveEventContractsTests.cs`, `Game.Core.Tests/Contracts/DomainEventContractTests.cs`
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`

### GM-0151 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Integrate combat turn flow and persistence
- 状态：done
- layer：core
- taskmaster_id：51
- 事件：`core.combat.turn.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.autosave.written`
  - 契约文件：`Game.Core/Contracts/Events/AutosaveWrittenEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0152 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement enemy intent selection logic
- 状态：done
- layer：ci
- taskmaster_id：52
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0153 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Headless smoke runner (Python) + strict mode
- 状态：done
- layer：ci
- taskmaster_id：53
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.combat.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs`
- 事件：`core.combat.ended`
  - 契约文件：`Game.Core/Contracts/Events/CombatEndedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`

### GM-0156 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Audit JSONL validation + gate integration
- 状态：done
- layer：ci
- taskmaster_id：56
- 事件：`core.audit.logged`
  - 契约文件：`Game.Core/Contracts/Events/AuditLoggedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0157 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Traceability gate for ADR/Chapter/Overlay links
- 状态：done
- layer：ci
- taskmaster_id：57
- 事件：`core.traceability.checked`
  - 契约文件：`Game.Core/Contracts/Events/TraceabilityCheckedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0159 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Rewire M1 run entry from main menu to difficulty, character, and map
- 状态：pending
- layer：adapter
- taskmaster_id：59
- 事件：`core.run.started`
  - 契约文件：`Game.Core/Contracts/Events/RunStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.difficulty.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs`
- 事件：`core.run.character.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunCharacterSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task16RunCharacterSelectedContractTests.cs`
- 事件：`core.run.state.transitioned`
  - 契约文件：`Game.Core/Contracts/Events/RunStateTransitionedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.map.node.entered`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0161 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement standalone Reward scene and route integration
- 状态：pending
- layer：adapter
- taskmaster_id：61
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.reward.offer.presented`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.selected`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.reward.offer.skipped`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferSkippedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`

### GM-0162 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement standalone Rest scene and route integration
- 状态：pending
- layer：adapter
- taskmaster_id：62
- 事件：`core.rest.option.selected`
  - 契约文件：`Game.Core/Contracts/Events/RestOptionSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.card.upgraded`
  - 契约文件：`Game.Core/Contracts/Events/CardUpgradedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.curse.removed`
  - 契约文件：`Game.Core/Contracts/Events/CurseRemovedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`

### GM-0164 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement combat HUD explainability and command feedback
- 状态：pending
- layer：adapter
- taskmaster_id：64
- 事件：`core.combat.turn.started`
  - 契约文件：`Game.Core/Contracts/Events/CombatTurnStartedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.intent.selected`
  - 契约文件：`Game.Core/Contracts/Events/IntentSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.combat.card.played`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardPlayedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`
- 事件：`core.combat.card.invalid_play_blocked`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.combat.damage.resolved`
  - 契约文件：`Game.Core/Contracts/Events/CombatDamageResolvedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0006CombatContractsTraceabilityTests.cs`, `Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs`
- 事件：`core.health.updated`
  - 契约文件：`Game.Core/Contracts/Events/HealthUpdatedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

### GM-0165 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement M1 visible text flow validation across UI scenes
- 状态：pending
- layer：adapter
- taskmaster_id：65
- 事件：`core.run.continue.blocked`
  - 契约文件：`Game.Core/Contracts/Events/RunContinueBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0014ContractRefsTests.cs`
- 事件：`core.run.difficulty.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunDifficultySelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0015ContractRefsTests.cs`
- 事件：`core.run.character.selected`
  - 契约文件：`Game.Core/Contracts/Events/RunCharacterSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task16RunCharacterSelectedContractTests.cs`
- 事件：`core.map.node.selected`
  - 契约文件：`Game.Core/Contracts/Events/MapNodeSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.combat.card.invalid_play_blocked`
  - 契约文件：`Game.Core/Contracts/Events/CombatCardInvalidPlayBlockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`
- 事件：`core.reward.offer.locked`
  - 契约文件：`Game.Core/Contracts/Events/RewardOfferLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.shop.inventory.locked`
  - 契约文件：`Game.Core/Contracts/Events/ShopInventoryLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.rest.option.selected`
  - 契约文件：`Game.Core/Contracts/Events/RestOptionSelectedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`
- 事件：`core.event.entered`
  - 契约文件：`Game.Core/Contracts/Events/EventEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`

### GM-0167 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement real Shop UI behavior binding and route ownership
- 状态：pending
- layer：adapter
- taskmaster_id：67
- 事件：`core.shop.inventory.locked`
  - 契约文件：`Game.Core/Contracts/Events/ShopInventoryLockedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.shop.item.purchased`
  - 契约文件：`Game.Core/Contracts/Events/ShopItemPurchasedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- 事件：`core.shop.curse.removed`
  - 契约文件：`Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`

### GM-0169 (.taskmaster/tasks/tasks_gameplay.json)

- 标题：Implement Event result explainability and node feedback routing
- 状态：pending
- layer：adapter
- taskmaster_id：69
- 事件：`core.event.entered`
  - 契约文件：`Game.Core/Contracts/Events/EventEnteredEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- 事件：`core.event.choice.committed`
  - 契约文件：`Game.Core/Contracts/Events/EventChoiceCommittedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsM1Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`, `Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs`
- 事件：`core.darkcost.applied`
  - 契约文件：`Game.Core/Contracts/Events/DarkCostAppliedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs`
- 事件：`core.relic.granted`
  - 契约文件：`Game.Core/Contracts/Events/RelicGrantedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`, `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- 事件：`core.curse.added`
  - 契约文件：`Game.Core/Contracts/Events/CurseAddedEvent.cs`
  - 关联测试：`Game.Core.Tests/Contracts/DomainEventContractTests.cs`, `Game.Core.Tests/Contracts/EventContractsBatch3Tests.cs`

