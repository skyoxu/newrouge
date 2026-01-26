---
title: "Game Architecture"
project: "newrouge"
date: "2026-01-22"
author: "skyo"
version: "1.0"
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8, 9]
status: "complete"
engine: "Godot 4.5.1 .NET"
platform: "Windows (Steam)"

# Source Documents
gdd: "_bmad-output/gdd.md"
epics: null
brief: null
---

# Game Architecture

## Executive Summary

NewRouge 的架构以 “确定性 + 可取证” 为第一原则：单槽 autosave、战斗初始态恢复、三选一候选集锁定、RNG 流拆分与可回放。核心实现策略是 `Game.Core/**` 的 Command 驱动状态机与 `security-audit.jsonl` 审计闭环，保证“退出重进不刷结果”（ADR-0032）。

**Key Architectural Decisions:**
- Deterministic Command Loop（唯一决定性推进入口）
- JSON autosave（UTF-8，无 BOM，v1 不压缩）+ atomic write + migration gate
- Custom PRNG + RNG streams（run/combat/event/loot）+ persisted state

## Development Environment

### Prerequisites

- Windows 10/11
- .NET 8 SDK（`dotnet`）
- Godot 4.5.1 .NET（建议 console 版本）
- Python 3（Windows 启动器 `py -3`）

### Environment Variables

- 必需：`GODOT_BIN`（指向 Godot 4.5.1 console exe）
- 建议：`GODOT_PROJECT`（仓库根目录绝对路径，避免 CWD 漂移）
- CI/安全：`GD_SECURE_MODE=1`、`GD_OFFLINE_MODE=1`、`SECURITY_TEST_MODE=1`

### Setup Commands (Windows)

```powershell
dotnet restore .\\NewRouge.sln
py -3 scripts/python/quality_gates.py all --godot-bin \"%GODOT_BIN%\" --solution Game.sln --configuration Debug --build-solutions
```

> 注：`packages.lock.json` 由 `dotnet restore .\\NewRouge.sln` 生成并必须提交（可复现门禁；见 ADR-0031）。

## Document Status

本文档通过 BMGD Architecture Workflow 逐步生成，用于固化 NewRouge 的技术承重结构，避免多代理协作时口径漂移。

**Workflow Status:** complete（以 frontmatter 为准）。

---

本文档已完成；后续变更必须通过 ADR 与补丁更新，并保持 `stepsCompleted/status` 与正文一致。

## Executive Summary

NewRouge 采用 Godot 4.5.1 .NET（Windows-only）并以 `Game.Core/**` 为纯领域承重墙，核心目标是“确定性 + 可取证”：单槽 autosave、战斗初始态边界、三选一候选集锁定、RNG 流拆分与可回放。所有决定性状态推进只允许通过 Core Commands，跨切面统一双通道日志与 JSONL 审计。

## Project Context

### Game Overview

**NewRouge** 是一款 Windows（Steam）平台的单人卡牌构筑 roguelike：3 Act 分叉地图推进，节点包含战斗/精英/事件/商店/休整；通过奖励三选一构筑牌组与遗物引擎，目标单局约 60 分钟。三角色机制差异明确：战士（怒气作为状态 buff）、刺客（以叠加多种 debuff 为核心）、德鲁伊（姿态/状态持久 buff 与切换爆发）。

### Technical Scope

- Platform: Windows-only（Godot 4.5.1 .NET 锁死，.NET 8）
- Networking: None（单机）
- Determinism Contract: 强制“退出重进不刷结果”，并允许 Continue 仅回到规则定义的存档边界（详见 ADR-0032 + GDD Executive Summary）

### Core Systems (Architecture Load-Bearing)

| System | Complexity | Source |
| --- | --- | --- |
| Save/Resume (single autosave slot) | High | GDD Executive Summary / ADR-0032 / project-context.md |
| Deterministic RNG (split streams + replayability) | High | GDD Executive Summary / project-context.md |
| Card/Combat Rules Engine (turn-based, deck piles, statuses) | High | PRD + GDD Executive Summary |
| Map/Node Progression (3 Acts branching, node types) | Medium | PRD |
| Content Pipeline (stable IDs, resources vs translations) | High | project-context.md / ADR-0010 |
| Testing & Quality Gates (xUnit, GdUnit4, coverage, logs) | Medium | ADR-0005 / ADR-0025 / project-context.md |
| Security Baseline (res://, user://, offline, allowlist) | Medium | ADR-0019 / project-context.md |
| Observability (structured logs, Sentry release health) | Medium | ADR-0003 / project-context.md |

### Technical Constraints (Non-Negotiables)

- Windows-only；Godot 4.5.1 .NET 锁死；不升级引擎版本。
- 文档中文，代码/脚本/测试英文；中文必须 UTF-8；禁止 Emoji。
- 新增三方库必须显式批准；优先复用现有脚本与依赖。
- 日志与取证统一落 `logs/**`，并遵循 `logs/ci/<YYYY-MM-DD>/**` 结构。
- v1 无必须支持的出网/云同步/多槽存档需求；但必须遵循默认拒绝出网与审计口径（GD_OFFLINE_MODE=1）。

### Complexity Drivers (What Will Cause Refactors If Wrong)

1) Save/Resume + Determinism：单槽 Continue、战斗初始态边界、候选集固定（ID+顺序+来源）、UI 不推进 RNG、原子写入与坏档/迁移门禁。
2) Content Scale & Consistency：首发 40 事件 + 90 基础卡 + 20 遗物，必须稳定 ID + 资源/文本分离，否则后续补丁必漂移且难以回归。
3) Cross-cutting Gates：可复现性、取证、覆盖率与 headless 测试策略需要先定骨架，否则实现会绕开门禁导致返工。

### Technical Risks (Early)

- 玩家误解“战斗中断回到战斗初始状态/三选一候选集固定”的规则，必须通过 UI/帮助页一致文案与审计证据闭环。
- 版本更新导致确定性回归：若候选集不落盘或 RNG 流混用，将出现“重启后结果变了”的高密度差评。

## Engine & Framework

### Selected Engine

**Godot 4.5.1 .NET**（version pinned）

**Version Verification:** Godot GitHub Releases `4.5.1-stable`（`/releases/latest` -> `4.5.1-stable`）
**Verification Date:** 2026-01-22

**Rationale（为何选它）**

- 与仓库模板与门禁脚本一致（Windows-only + C#/.NET 8 + Godot 4.5.1 锁死）。
- 本项目的承重复杂度来自“确定性存档契约/内容管线/门禁取证”，而不是换引擎；换引擎只会放大返工面。

### Project Initialization

- 使用当前仓库作为 starter（本仓库即模板），不引入额外第三方 starter/template。
- 版本锁定与可复现口径以 ADR-0031 与 `project-context.md` 为准（包含 `GODOT_BIN` 与 export templates 匹配要求）。

### Engine-Provided Architecture（由引擎直接提供的“默认决策”）

| Component | Solution | Notes |
| --- | --- | --- |
| Rendering | Godot renderer (Forward Plus) | 渲染路径由 `project.godot` 决定 |
| Scene System | SceneTree + Nodes | 场景装配与节点生命周期由引擎提供 |
| Signals | Built-in Signals | 场景内通信优先 Signals；跨场景事件走 EventBus（ADR-0004） |
| Input | InputMap | 输入绑定与分发由引擎提供 |
| Audio | Godot AudioServer | 音频播放与混音由引擎提供 |
| Physics | Godot Physics | 本作预计低依赖；如涉及碰撞按需启用 |
| Build/Export | Export presets + templates | Windows 导出产物命名与日志取证遵循项目口径 |

### Remaining Architectural Decisions（仍需显式拍板的架构决策）

- Save/Resume & Determinism：单槽 autosave、战斗初始态边界、候选集固定（ID+顺序+来源）、UI 不推进 RNG、原子写入、坏档/迁移门禁（ADR-0032）。
- RNG Architecture：run/combat/event/loot 流拆分与持久化策略（满足“退出重进不刷结果”）。
- Core Rules Engine：卡牌/状态/堆栈/结算顺序的领域模型与可测试边界（`Game.Core/**`）。
- Content Pipeline：稳定 ID、资源与文本分离、翻译键规范与构建期检查（ADR-0010 + project-context.md）。
- Quality Gates：xUnit/GdUnit4 分层测试策略、覆盖率门禁、headless 取证落 `logs/**`（ADR-0005/0025）。
- Security Defaults：GD_SECURE_MODE/GD_OFFLINE_MODE 默认拒绝出网与审计（ADR-0019）。

### Comparative Analysis (Weighted Matrix)

Given hard constraints (Windows-only, Godot 4.5.1 .NET pinned, existing repo template), switching engines (Unity/Unreal) is a net-negative for v1:

- Migration cost dominates all potential benefits.
- Determinism/save-resume complexity remains regardless of engine.
- Existing quality gates, logs, and project structure are already Godot-aligned.

Decision: Stay on Godot 4.5.1 .NET and treat “deterministic save/resume + content pipeline + gates” as the primary architecture work.

### Critical Perspective (Why This Could Fail)

Staying on Godot 4.5.1 .NET is the correct v1 choice under current constraints, but it carries predictable failure modes:

- Version pinning risk: security/export regressions may force an exception path.
  - Mitigation: define explicit “break-glass” criteria and ADR supersede workflow (ADR-0031).
- Determinism risk: hidden side effects (UI, callbacks, async ordering) can violate “no reroll/no reshuffle”.
  - Mitigation: enforce strict boundaries for gameplay-affecting inputs; persist offer IDs+order+provenance; audit all RNG advances.
- Concurrency risk: thread/async usage can introduce nondeterministic ordering.
  - Mitigation: deterministic state transitions run in `Game.Core/**` in a controlled loop; async work must not mutate decisive state.
- CI/export friction risk: environment drift breaks reproducibility.
  - Mitigation: gate on prereqs (Godot bin/templates/.NET SDK/lockfiles) and write evidence to `logs/**`.

## Architectural Decisions

### Decision Summary

| Category | Decision | Version | Rationale |
| --- | --- | --- | --- |
| State Management | State Machine + Command-driven core | N/A | 可测试、可复现；把“UI/回调/时序副作用”挡在 Core 之外 |
| Data Persistence | Local JSON autosave (UTF-8) + schema_version + atomic write | N/A | 易审计、易迁移、易取证；对单槽 Continue 语义最清晰 |
| RNG Architecture | Custom PRNG in `Game.Core/**` + split streams (run/combat/event/loot) + persisted state | N/A | 避免框架/实现差异带来的漂移；满足“退出重进不刷结果” |
| Offer Locking | “三选一”候选集落盘：stable IDs + display order + provenance | N/A | 版本更新与重载后结果不漂移；可做回归门禁 |

### State Management

**Approach:** State Machine + Command-driven core (Decision 1A)

- 核心状态只存在于 `Game.Core/**`：`RunState`、`CombatState`、`NodeState`（名称可调整，但边界必须明确）。
- Core 只接受显式 `Command` 推进（例：`StartRunCommand`、`EnterNodeCommand`、`PlayCardCommand`、`ChooseOfferCommand`、`EndTurnCommand`）。
- `Command` 是唯一可推进决定性状态的入口；只有 gameplay-affecting commands 才允许推进 RNG。
- 纯 UI 行为（查看牌堆/打开菜单/悬停提示等）不得推进 RNG、不得改变候选集。
- Godot 层（`Game.Godot/**`）只负责 UI/Signals/资源加载/装配；不得在场景回调里隐式变更决定性状态。

### Data Persistence

**Save System:** Local JSON autosave (Decision 2A)

- 存档位置与权限：仅 `user://`（遵循 ADR-0019 安全基线）。
- 存档粒度边界：节点前 + 进入战斗保存“战斗初始状态”；战斗中绝不保存中间态（ADR-0032）。
- 存档格式：JSON（UTF-8，无 BOM），v1 不压缩；包含：
  - `schema_version`（递增整型）
  - `run_id` / `seed`（及派生策略所需字段）
  - 当前 run 状态快照（节点/战斗边界的可复现最小集）
  - 任何已生成但需要稳定的“候选集”（见 Offer Locking）
- 写入要求：atomic write（写临时文件→校验→替换），失败保留上一份 autosave；Continue 读档必须做完整性校验，失败必须阻断并提示。
- 迁移门禁：迁移必须幂等；失败不得写回；必须产出 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。

### RNG Architecture

**Approach:** Custom PRNG + split streams + persisted state (Decision 3A)

- PRNG 必须在 `Game.Core/**`，不依赖 Godot；并显式拆分 RNG 流：`run` / `combat` / `event` / `loot`。
- 任一存档边界必须持久化必要 RNG 状态，确保重载不会改变：
  - 战斗初始局面（战斗中断回到初始态）
  - 三选一候选集与顺序
- 禁止用“隐式全局随机”驱动决定性结果（避免不同调用时序产生漂移）。

### Offer Locking (“三选一”)

**Approach:** Persist stable IDs + order + provenance (Decision 4 accepted)

- 所有“三选一”在首次生成时必须落盘：
  - `stable_ids[]`（稳定 ID）
  - `display_order[]`（展示顺序）
  - `provenance`（生成来源：node_id / event_id / reward_type 等）
- 退出重进允许重新选择，但候选集与顺序必须完全一致（含顺序）。

## Cross-cutting Concerns

本节规则适用于所有系统；任何实现必须遵守，避免多代理口径漂移。

### Error Handling

**Strategy:** Result objects in `Game.Core/**` + boundary try/catch in `Game.Godot/**`

- `Game.Core/**`：不允许未处理异常向外冒泡；用 `Result<T>` / `ErrorCode` 表达失败，并携带可审计上下文（不含敏感数据）。
- `Game.Godot/**`：只在边界层捕获异常（资源加载、存档读写、迁移、被拒绝的出网等）；失败时：
  - 记录审计（JSONL）
  - 阻断 Continue 并提示（符合 ADR-0032）
  - 不允许“半加载”或“吞错继续”

**Example (C#):**
```csharp
public sealed record Error(string Code, string Message);

public sealed record Result<T>(bool Ok, T? Value, Error? Error)
{
    public static Result<T> Success(T value) => new(true, value, null);
    public static Result<T> Fail(string code, string message) => new(false, default, new Error(code, message));
}
```

### Logging & Audit

**Approach:** Dual-channel (human logs + machine audit JSONL)

- 开发日志（人读）：通过 `ILogger` 输出到控制台（INFO/WARN/ERROR/DEBUG），避免在高频热路径做重格式化。
- 审计日志（机器读）：统一写 `user://logs/security/security-audit.jsonl`（JSONL，一行一个 JSON），字段至少：
  `{ts, action, reason, target, caller}`，并建议增加 `area`（security/save/determinism）。
- Sentry：只上报 ERROR/异常与 release health（ADR-0003），不把 INFO 灌进去。

**Example (JSONL line):**
```json
{"ts":"2026-01-22T10:00:00Z","area":"save","action":"save.load.blocked","reason":"migration_failed","target":"autosave","caller":"MainMenu.Continue"}
```

### Configuration

**Approach:** Layered config + dev-only hot reload

- 硬口径/阈值：只在 ADR/Base/门禁脚本定义，代码引用名称，不复制数值。
- 平衡参数：`Game.Godot/Resources/**`（可被策划/开发调整）；允许 dev-only 热加载；release 强制关闭并审计。
- 玩家设置：`user://`（与存档分离）。
- 运行开关：环境变量只读（`GD_SECURE_MODE`、`GD_OFFLINE_MODE`、`ALLOWED_EXTERNAL_HOSTS`），并写审计。

### Event System

**Pattern:** Scene-local Signals + global EventBus (ADR-0004)

- 场景内：Signals
- 跨场景/跨系统：EventBus
- 事件命名：`newrouge.<entity>.<action>`
- 事件契约：`Game.Core/Contracts/**` 为 SSoT；事件类型必须常量化（禁魔法字符串）。
- 处理顺序：同步稳定顺序（可复现优先）。
- handler 异常：不得静默吞掉；至少 WARN 记录（含 event type/id），但不得让总线崩溃。

**Example (C# contract):**
```csharp
public sealed record RunStarted(string RunId, string Seed)
{
    public const string EventType = "newrouge.run.started";
}
```

### Debug Tools

**Gating:** dev-only，release 强制关闭

- Debug features 必须显式开关控制（DEBUG/CI/GD_SECURE_MODE 组合），并在 release 构建中剔除或禁用。
- Debug 命令不得改变决定性状态（或必须通过 Command 入口并被审计），避免破坏可复现性。

## Project Structure

### Organization Pattern

**Pattern:** Domain-Driven + Layered Boundaries

**Rationale:** 以 `Game.Core/**`（纯领域）为承重墙，`Game.Godot/**`（引擎适配）为外壳，测试分层映射，保证可测/可复现/可审计。

### Directory Structure

```
newrouge/
├── Game.Core/                     # Pure C# domain (NO Godot API)
│   ├── Contracts/                 # SSoT: events/DTO contracts (ADR-0004/0020)
│   ├── Domain/                    # Entities/value objects/domain rules
│   ├── Engine/                    # Core loop/state transitions (command-driven)
│   ├── Ports/                     # Interfaces for adapters (ADR-0007)
│   ├── Repositories/              # Persistence abstractions
│   ├── Services/                  # Domain services/use-cases
│   ├── State/                     # Run/Combat/Node state models
│   └── Utilities/                 # Pure helpers (deterministic-safe)
├── Game.Core.Tests/               # xUnit tests for Game.Core
│   ├── Domain/
│   ├── Engine/
│   ├── Repositories/
│   ├── Services/
│   ├── State/
│   └── Utilities/
├── Game.Godot/                    # Godot adapter layer + scenes/resources
│   ├── Adapters/                  # Port implementations + bridge nodes
│   ├── Autoloads/                 # CompositionRoot + global glue (minimal)
│   ├── Scenes/                    # .tscn scenes (UI/flows)
│   ├── Resources/                 # Data-driven configs/events (no visible text)
│   ├── Scripts/                   # Godot-facing scripts (glue, signals, UI)
│   ├── Translations/              # All visible UI text (no hardcoding)
│   ├── Assets/ Fonts/ Themes/     # Art/audio/UI styling assets
│   └── Examples/                  # Template examples (dev-only)
├── Tests.Godot/                   # Engine tests (GdUnit4 / headless)
│   ├── addons/
│   └── tests/
├── docs/                          # PRD/ADR/Architecture
├── scripts/                       # CI + python gates (SSoT for logs/ci)
├── logs/                          # All evidence/artifacts
└── _bmad-output/                  # BMAD artifacts (GDD/Architecture, etc.)
```

### System Location Mapping

| System | Location | Responsibility |
| --- | --- | --- |
| Command-driven state transitions | `Game.Core/Engine/**` + `Game.Core/State/**` | Deterministic progression; only Commands advance decisive state |
| Save/Resume (single autosave slot) | `Game.Core/State/**` + `Game.Core/Repositories/**` | JSON schema_version + atomic write + migration gate |
| PRNG + RNG stream splitting | `Game.Core/Utilities/**` (or `Game.Core/Engine/**`) | Custom PRNG; run/combat/event/loot streams; persisted state |
| Contracts (events/DTOs) | `Game.Core/Contracts/**` | EventType constants + DTO schema; no Godot dependency |
| Scene assembly + UI glue | `Game.Godot/Scenes/**` + `Game.Godot/Scripts/**` | Signals wiring, UI, input routing; no core rules |
| Adapters (ports) | `Game.Godot/Adapters/**` | Godot API wrapper; logging/event bridge; boundary try/catch |
| Localization | `Game.Godot/Translations/**` | All visible text; scripts must not hardcode visible strings |
| Data-driven content | `Game.Godot/Resources/**` | Events/cards/relic metadata; stable IDs; no visible text |
| Engine tests | `Tests.Godot/tests/**` | Headless smoke/security/perf suites |
| Unit tests | `Game.Core.Tests/**` | Every new Core type needs tests (except pure DTO by exception) |

### Naming Conventions

#### Files

- C# files: PascalCase (`CombatState.cs`, `RunStarted.cs`)
- Godot scenes: PascalCase (`MainMenu.tscn`, `CombatHud.tscn`)
- One scene one same-name script: `Foo.tscn` ↔ `Foo.cs`（同目录；仅对 `Game.Godot/Scenes/**` 下严格生效）
- Resource IDs / content IDs: dot notation (`card.warrior.strike`, `event.act1.bandits`)
- Event types: `newrouge.<entity>.<action>`（must be constants, no magic strings）

#### Code Elements

- Namespaces: `Game.Core.*` / `Game.Godot.*`（PascalCase）
- Public types: PascalCase
- Methods/locals: PascalCase for methods, camelCase for locals
- Constants: PascalCase for `public const`（与现有代码风格一致）

### Architectural Boundaries (Non-Negotiables)

- `Game.Core/**` 禁止引用 Godot API；只依赖 .NET 标准库。
- `Game.Godot/**` 只做适配与 UI/Scenes 胶水；决定性状态推进必须通过 Core Commands。
- 文本：可见 UI 文本必须来自 `Game.Godot/Translations/**`，脚本禁止硬编码可见文本。
- `Examples/**` 仅 dev-only；发布时剔除。
- Logs：所有取证写 `logs/**`；CI 取证写 `logs/ci/<YYYY-MM-DD>/**`。

## Implementation Patterns

本节定义“实现模板级”模式，目标是让多个 AI 代理写出可组合、可复现、可审计的代码。

### Novel Patterns

#### Novel Pattern A: Deterministic Command Loop（含 Offer Locking + RNG Streams）

**Purpose:** 将所有决定性状态推进收敛到 `Command`，确保同一存档点+同一输入序列=同一结果，并可做审计与回放。

**Core Components**

- `Game.Godot/Scenes/**` + `Game.Godot/Scripts/**`: UI/Signals，只负责把玩家意图变成 `Command`
- `Game.Core/Engine/**`: Command dispatcher / apply loop（唯一推进入口）
- `Game.Core/State/**`: `RunState` / `CombatState` / `NodeState`
- `Game.Core/Utilities/**`: Custom PRNG + stream split（run/combat/event/loot）
- Audit（JSONL）：对每次命令推进、RNG advance、offer 生成、save/load/migrate 写入 `security-audit.jsonl`

**Data Flow**

1) UI 触发（点击卡牌/选择奖励/结束回合）→ 构造 `Command`
2) Core `Apply(command)` → 校验 →（必要时）使用对应 RNG stream → 更新 State → 产出 Events/Effects
3) 若产生“三选一”：在 State 内落盘 `stable_ids[] + display_order[] + provenance`（Offer Locking）
4) 在 save boundary（节点前/入战斗）写 autosave（Atomic Autosave）

**Hard Rules**

- `Command` 是唯一可推进决定性状态的入口；纯 UI 行为不得推进 RNG 或改变候选集。
- RNG 必须拆分 streams：`run` / `combat` / `event` / `loot`；并在存档边界持久化必要 RNG 状态。
- Offer Locking：首次生成即落盘 stable IDs + 顺序 + 来源；重载必须完全一致（含顺序）。

**Example (C# skeleton)**
```csharp
public interface ICommand
{
    string Kind { get; }
}

public sealed record ApplyResult(
    object NewState,
    IReadOnlyList<Game.Core.Contracts.DomainEvent> Events);

public interface IGameEngine
{
    Result<ApplyResult> Apply(object state, ICommand command);
}
```

#### Novel Pattern B: Atomic Autosave + Migration Gate

**Purpose:** 单槽 autosave 可中断继续且不可刷结果；迁移失败必须阻断 Continue 并提示；全流程可审计。

**Core Components**

- `Game.Core/Repositories/**`: `ISaveRepository`（user:// storage 由 Godot adapter 实现）
- `Game.Core/State/**`: Save snapshot schema（`schema_version` + minimal deterministic state）
- Migration runner（幂等）：失败不写回
- Atomic writer：temp → validate → replace（失败保留上一份）

**Hard Rules**

- autosave write 必须原子化；失败必须保留上一份 autosave。
- Continue load 必须做完整性校验；损坏/不兼容/迁移失败：阻断 Continue 并提示。
- 迁移必须幂等；失败不得写回；产出 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。
- v1 存档 JSON UTF-8，无 BOM，不压缩（可审计优先）。

**Example (C# pseudo)**
```csharp
public static Result<Unit> AtomicWrite(string finalPath, string jsonUtf8)
{
    var tmpPath = finalPath + ".tmp";
    File.WriteAllText(tmpPath, jsonUtf8, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    // validate read-back / checksum here
    File.Move(tmpPath, finalPath, overwrite: true);
    return Result<Unit>.Success(Unit.Value);
}
```

### Standard Patterns (Consistency)

#### Communication

- Scene-local: Godot Signals
- Cross-system: EventBus with `DomainEvent` envelope (type/source/dataJson/id/specVersion/...)
- Dispatch: synchronous stable order (determinism-first)
- Handler exceptions: MUST log WARN with event type/id; MUST NOT crash the bus

#### Entity Creation

- Core domain objects: Factory pattern（集中校验与默认值）
- Godot nodes/scenes: PackedScene instantiation；对象池仅按需（避免 v1 过度复杂）

#### Data Access

- `Game.Core/**` only via Ports (`Game.Core/Ports/**`)
- `Game.Godot/Adapters/**` implements ports and touches Godot APIs
- No direct file/network access in Core

#### State Transitions

- Only Commands mutate decisive state
- Reducer/Apply style: pure(ish) state transition + explicit effects
- Audit every decisive transition

### Consistency Rules (Enforcement)

| Pattern | Convention | Enforcement |
| --- | --- | --- |
| Command-driven | decisive state only via Commands | xUnit tests for each new Core type (DTO exception by review) |
| Offer Locking | persist IDs+order+provenance | regression test: reload returns identical offers |
| Audit | JSONL `security-audit.jsonl` | CI artifacts under `logs/ci/<YYYY-MM-DD>/**` |
| Localization | no hardcoded visible text | build-time/static scan + code review gate |

## Architecture Validation

### Validation Summary

| Check | Result | Notes |
| --- | --- | --- |
| Decision Compatibility | PASS | Godot 4.5.1 .NET pinned; Command/Save/RNG decisions coherent |
| GDD Coverage | PASS (current scope) | GDD currently provides Step-02 core constraints; later GDD steps still pending |
| Pattern Completeness | PASS | Deterministic Command Loop + Atomic Autosave/Migration Gate + standard patterns |
| Epic Mapping | N/A | No epics/brief/narrative provided |
| Document Completeness | PASS | No placeholders; structure/tables/examples present |

### Issues Resolved

- Fixed stale progress text in document body (use frontmatter as SSoT).
- Aligned EventBus handler dispatch with determinism-first rules (stable order + WARN logging).
- Aligned security audit JSONL fields and output file to repo audit SSoT (`security-audit.jsonl`).

### Follow-ups (Non-blocking)

- ADR-0032 remains `Proposed`; Acceptance Criteria + DoD now defined to upgrade it to `Accepted` after minimal implementation + tests + logs evidence.

### Validation Date

2026-01-22
