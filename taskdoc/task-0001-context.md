# Task 0001 上下文 (Serena MCP)

## 任务映射
- tasks.json: `master.tasks[id=1]`
- tasks_back.json: `NG-0001 (taskmaster_id=1)`
- tasks_gameplay.json: `GM-0101 (taskmaster_id=1)`
- downstream: `2`, `13`

## 1) find_symbol
- keywords: `CompositionRoot`, `EventBus`, `DataStore`, `Logger`, `SecurityAudit`, `FeatureFlags`
- hits: `Game.Godot/Autoloads/CompositionRoot.cs`, `Game.Core/Contracts/Interfaces/IEventBus.cs`, `Game.Godot/Adapters/EventBusAdapter.cs`

## 2) search_for_pattern
- interfaces: `IEventBus`, `IRunCommandHandler`, `ISaveService`, `IDataStore`, `ILogger`, `ISqlDatabase`

## 3) find_symbol 事件契约
- `RunStartedEvent` => `EventTypes.RunStarted`
- `RunResumedEvent` => `EventTypes.RunResumed`
- `RunStateTransitionedEvent` => `EventTypes.RunStateTransitioned`
- `CombatStartedEvent` => `EventTypes.CombatStarted`
- `AutosaveWrittenEvent` => `EventTypes.AutosaveWritten`
- event dictionary: `Game.Core/Contracts/EventTypes.cs`

## 4) find_referencing_symbols
- result: mostly empty/self references for infra symbols (`CompositionRoot`, `EventBusAdapter`).
- note: Task 0001 is environment baseline, low business call-chain density is expected.
