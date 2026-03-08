---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 测试策略（M1）
Status: Draft
ADR-Refs:
  - ADR-0025-godot-test-strategy
  - ADR-0005-quality-gates
  - ADR-0032-save-resume-determinism
  - ADR-0033-card-identity-and-forms
Arch-Refs:
  - CH03
  - CH06
  - CH07
Test-Refs:
  - Game.Core.Tests/Tasks/Task0003AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0004AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0011AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0050AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0057AcceptanceTests.cs
  - Tests.Godot/Smoke/ContinueGateTests.gd
---

# 08 测试策略（M1）

## 1. 测试分层
- Core（xUnit）：验证规则与契约，不依赖 Godot 引擎。
- Godot（GdUnit4/Runner）：验证场景、信号与 Continue 路径。
- CI Gate：验证回链、日志、编码、语义与取证完整性。

## 2. M1 必测能力

### 2.1 确定性与候选集锁定
- 同一存档点 + 同一输入序列，候选集与结果一致。
- 退出重进不得重抽三选一候选集。

### 2.2 存档边界
- 节点前存档可恢复。
- 进入战斗后回到战斗初始状态。
- 战斗中间态不得恢复。

### 2.3 卡牌身份与形态
- 升级不改变 `card_id`。
- U1 路线 A/B 约束可断言。
- Ultimate 覆盖 U1 能力且继承实例附着效果。

### 2.4 Continue Gate
- 坏档、迁移失败、校验失败时，Continue 必须被阻断并可提示。

## 3. 质量门禁对齐
- 覆盖率阈值：以仓库门禁口径为准。
- 语义门禁：任务 detail 与 acceptance 必须对齐。
- 文档门禁：关键路径文本必须 UTF-8、无 BOM、无语义乱码。

## 4. 证据落盘
- 单测：`logs/unit/<YYYY-MM-DD>/`
- 冒烟：`logs/e2e/<YYYY-MM-DD>/`
- CI：`logs/ci/<YYYY-MM-DD>/`

## 5. 失败处理
- 任何硬门失败不得标记任务为 done。
- 修复优先顺序：契约 -> 规则 -> 场景绑定 -> 文案/回链。


## 6. Task28 Test-Refs
- Task: `T28 / GM-0128`
- Test-Refs:
  - `Game.Core.Tests/Tasks/Task0028AcceptanceTests.cs`
  - `Game.Core.Tests/Services/ActConfigLoaderTests.cs`
  - `Game.Core.Tests/Services/ActConfigLoaderSchemaVersionTests.cs`
- Contract/Service under test:
  - `Game.Core/Contracts/Config/ActConfig.cs`
  - `Game.Core/Contracts/Config/ActConfigLoadResult.cs`
  - `Game.Core/Contracts/Interfaces/IActConfigProvider.cs`
  - `Game.Core/Contracts/Events/ActConfigLoadedEvent.cs`
  - `Game.Core/Services/ActConfigLoader.cs`
- Gate focus:
  - valid JSON maps `schema_version/act_id/node_graph/pools/encounters`
  - missing or unsupported `schema_version` must fail with assertable error code/message
  - read/deserialize failure must return deterministic failure result
