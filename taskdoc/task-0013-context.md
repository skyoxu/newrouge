# Task 0013 上下文 (Serena MCP)

## 任务映射
- tasks.json: `master.tasks[id=13]`
- tasks_back.json: `NG-0006 (taskmaster_id=13)`
- tasks_gameplay.json: `GM-0113 (taskmaster_id=13)`
- depends_on: `1`, `2`

## 1) find_symbol
- keywords: `CompositionRoot`, `EventBusAdapter`, `DataStoreAdapter`, `LoggerAdapter`, `SecurityAudit`, `FeatureFlags`
- hits: `Game.Godot/Autoloads/CompositionRoot.cs`, `Game.Godot/Adapters/EventBusAdapter.cs`, `Game.Godot/Adapters/DataStoreAdapter.cs`, `Game.Godot/Adapters/LoggerAdapter.cs`, `Game.Godot/Scripts/Security/SecurityAudit.cs`, `Game.Godot/Scripts/Config/FeatureFlags.cs`

## 2) search_for_pattern
- injection alignment interfaces: `IEventBus`, `IDataStore`, `ILogger`, `IRunCommandHandler`, `ISaveService`

## 3) find_symbol 事件契约
- `core.run.started` -> `RunStartedEvent`
- `core.run.resumed` -> `RunResumedEvent`
- `core.run.state.transitioned` -> `RunStateTransitionedEvent`
- `core.combat.started` -> `CombatStartedEvent`
- `core.autosave.written` -> `AutosaveWrittenEvent`

## 4) find_referencing_symbols
- result for infra symbols is mostly empty/self references.
- interpretation: runtime wiring is mostly via Godot autoload lifecycle and composition root behavior.
