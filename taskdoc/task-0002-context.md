# Task 0002 上下文 (Serena MCP)

## 任务映射
- tasks.json: `master.tasks[id=2]`
- tasks_gameplay.json: `GM-0102 (taskmaster_id=2)`
- depends_on: `1`

## 1) find_symbol
- keywords: `IDataStore`, `ILogger`, `IEventBus`, `GameStateManager`, `GameEngineCore`
- hits: `Game.Core/Ports/IDataStore.cs`, `Game.Core/Ports/ILogger.cs`, `Game.Core/Contracts/Interfaces/IEventBus.cs`, `Game.Core/State/GameStateManager.cs`, `Game.Core/Engine/GameEngineCore.cs`

## 2) search_for_pattern
- reusable interface surface confirmed in `Game.Core/Contracts/Interfaces` and `Game.Core/Ports`.

## 3) find_symbol 事件契约
- event records under `Game.Core/Contracts/Events` use `EventType = EventTypes.*`.
- naming aligned to ADR-0004 style (`core.*.*`).

## 4) find_referencing_symbols
- `GameStateManager` and `GameEngineCore` show mainly internal publish points.
- cross-file static references are weak; do not use reference count as sole refactor scope metric.
