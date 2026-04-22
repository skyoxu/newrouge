---
GDD-ID: GDD-NEWROUGE-UI-WIRING-V1
Title: NewRouge Chapter 7 UI Wiring Board
Status: Draft
Owner: codex
Last Updated: 2026-04-22
Encoding: UTF-8
Applies-To:
  - .taskmaster/tasks/tasks.json
  - docs/gdd/ui-gdd-flow.md
ADR-Refs:
  - ADR-0031
  - ADR-0011
  - ADR-0024
  - ADR-0033
  - ADR-0020
  - ADR-0032
  - ADR-0021
  - ADR-0029
  - ADR-0004
  - ADR-0023
  - ADR-0007
  - ADR-0022
Test-Refs:
  - Game.Core.Tests/Tasks/Task1ToolchainVersionChecksTests.cs
  - Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs
  - Game.Core.Tests/Tasks/Task1DotnetRestoreLockfileTests.cs
  - Game.Core.Tests/Tasks/Task1WindowsPlatformGateTests.cs
  - Tests.Godot/tests/Tasks/test_task0002_acceptance.gd
  - Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs
  - Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs
  - Game.Core.Tests/Tasks/Task0003AcceptanceTests.cs
---

# NewRouge Chapter 7 UI Wiring Board

## 1. Design Goals

### 1.1 Experience Pillars
- Stable entry: startup, continue, and runtime entry must be explicit and recoverable.
- Readable loop: phase, pressure, resources, HP, prompts, and outcomes must be understandable from the UI alone.
- Explainable systems: config, governance, save, migration, and audit state must have visible ownership instead of hiding in logs.
- Deterministic recovery: failure, invalid action, persistence, and fallback states must be reproducible and visible.

### 1.2 Target Use
- Provide one governed planning surface for all currently completed task capabilities.
- Keep Chapter 7 focused on player-facing or operator-facing surface ownership before polish-only work.

## 2. Core Player Loop

1. Launch or continue from a stable entry surface.
2. Enter the runtime loop with readable phase, timing, pressure, and survival state.
3. Interact with combat, economy, progression, and meta systems through governed surfaces.
4. Resolve win, loss, save/load, config-governance, and migration outcomes with visible feedback.

## 3. Completed Capability Inventory

| Capability Slice | Audience | Task IDs | Player-Facing Meaning | Primary UI Need |
| --- | --- | --- | --- | --- |
| Entry And Bootstrap | player-facing | T01, T11, T21, T43, T45, T53 | Show canonical startup path, valid continue behavior, and explicit startup failure recovery | MainMenu / Boot Flow |
| Core Loop State And Outcome | player-facing | T03, T07, T08, T09, T10, T18, T19, T23, T24, T44 | Render readable phase, timer, HP, reward, prompt, and win/lose state from runtime events | HUD / Prompt / Outcome Surfaces |
| Combat Pressure And Interaction | player-facing | T04, T05, T06, T20, T22, T41, T42, T49, T51 | Render enemy pressure, targeting, combat outcomes, and camera interaction without hidden state | Combat HUD / Pressure / Camera Feedback |
| Economy Build And Progression | player-facing | T12, T13, T14, T15, T16, T17 | Render deterministic resource, build, queue, upgrade, and progression changes with clear invalid-state feedback | Resource / Build / Progression Panels |
| Meta Systems And Platform | player-facing or mixed | T25, T26, T27, T28, T29, T30, T46, T47, T48, T50, T52, T54, T55, T56, T57, T58 | Render persistence, localization, audio, performance, and platform status on governed player-visible surfaces | Settings / Save / Meta Surfaces |
| Config Governance And Audit | operator-facing or mixed | T02, T31, T32, T33, T34, T35, T36, T37, T38, T39, T40 | Render active config, schema status, fallback policy, migration status, and audit metadata without relying on logs-only evidence | Config Summary / Audit / Migration Surfaces |

## 4. Flow Recomposition

### Entry And Bootstrap

- T01 `Set up project environment and dependencies`
- T11 `Implement combat resolution pipeline (core)`
- T21 `Implement rest scene with free upgrade option`
- T43 `Run state machine with Command-only transitions`
- T45 `Display difficulty in HUD and run summary`
- T53 `Headless smoke runner (Python) + strict mode`
### Core Loop State And Outcome

- T03 `Implement core contracts for card identity and forms`
- T07 `Set up event bus and contracts location`
- T08 `Implement core logic for card identity and forms`
- T09 `Implement deterministic RNG stream registry`
- T10 `Implement status application, stacking, and decay`
- T18 `Implement combat scene UI shell and bindings`
- T19 `Implement reward scene with card three-choice-one and offer locking`
- T23 `Set up translations system with key naming conventions`
- T24 `Implement Warrior starting deck with 10 cards`
- T44 `Deterministic resume integration tests (headless)`
### Combat Pressure And Interaction

- T04 `Implement core contracts for offer locking and deterministic outcomes`
- T05 `Implement core contracts for status and modifier system`
- T06 `Implement core contracts for combat loop and resolution pipeline`
- T20 `Implement shop scene with inventory locking and no upgrade context`
- T22 `Implement event scene with dark cost examples`
- T41 `Implement enemy intent display and preview UI`
- T42 `Map node entry gating and backtracking rules`
- T49 `Implement stability safeguards for combat loop`
- T51 `Integrate combat turn flow and persistence`
### Economy Build And Progression

- T12 `Implement save serialization and atomic write`
- T13 `Set up Godot autoloads and composition root`
- T14 `Create main menu scene with new run and continue options`
- T15 `Implement difficulty selection UI`
- T16 `Implement character selection UI for Warrior only`
- T17 `Create modular Act structure for map system`
### Meta Systems And Platform

- T25 `Implement rage as state buff for Warrior`
- T26 `Define difficulty configuration contract and immutability`
- T27 `Implement difficulty rule modifiers`
- T28 `Create ActConfig data model and loader`
- T29 `Implement card drop pools per Act and encounter type`
- T30 `Define relic contracts and instance model`
- T46 `Implement offer locking generation using RNG streams`
- T47 `Implement status trigger ordering and fixed damage rules`
- T48 `Implement damage calculation and AOE ordering`
- T50 `Implement save migration validation and failure blocking`
- T52 `Implement enemy intent selection logic`
- T54 `Integrate GdUnit4 suites into quality_gates.py`
- T55 `Coverage thresholds as configurable soft/hard gate`
- T56 `Audit JSONL validation + gate integration`
- T57 `Traceability gate for ADR/Chapter/Overlay links`
- T58 `Semantic scope governance for soft review stabilization`
### Config Governance And Audit

- T02 `Create core project structure and namespaces`
- T31 `Implement 20 starting relic definitions and uniqueness checks`
- T32 `Implement curse cards and removal services`
- T33 `Implement deck operations service (draw/discard/exhaust/retain)`
- T34 `Implement card targeting and drag UX`
- T35 `Implement end-of-combat resolution pipeline`
- T36 `Implement autosave triggers per determinism policy`
- T37 `Single-slot continue metadata and integrity checks`
- T38 `Audit logging for determinism and security events`
- T39 `Populate translations for M1 cards, relics, events`
- T40 `Define Act 1 enemy data and definitions`

## 5. UI Wiring Matrix

| Feature | UI Surface | Player Action | System Response | Test Refs |
| --- | --- | --- | --- | --- |
| Entry And Bootstrap (T01, T11, T21, T43, T45, T53) | MainMenu / Boot Flow | Launch, continue, retry bootstrap, or enter a run | Show canonical startup path, valid continue behavior, and explicit startup failure recovery | `Game.Core.Tests/Tasks/Task1ToolchainVersionChecksTests.cs`, `Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs`, `Game.Core.Tests/Tasks/Task1DotnetRestoreLockfileTests.cs`, `Game.Core.Tests/Tasks/Task1WindowsPlatformGateTests.cs` |
| Core Loop State And Outcome (T03, T07, T08, T09, T10, T18, T19, T23, T24, T44) | HUD / Prompt / Outcome Surfaces | Play a run, observe timing, rewards, prompts, and terminal transitions | Render readable phase, timer, HP, reward, prompt, and win/lose state from runtime events | `Game.Core.Tests/Tasks/Task0003AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Domain/GameEventContractsTests.cs`, `Tests.Godot/tests/Adapters/test_event_bus_adapter.gd` |
| Combat Pressure And Interaction (T04, T05, T06, T20, T22, T41, T42, T49, T51) | Combat HUD / Pressure / Camera Feedback | Fight, observe pressure, targeting, pathing, and camera responses | Render enemy pressure, targeting, combat outcomes, and camera interaction without hidden state | `Game.Core.Tests/Domain/OfferLockingContractTests.cs`, `Game.Core.Tests/Domain/RngStreamTypeTests.cs`, `Game.Core.Tests/Domain/OfferLockingDeterminismTests.cs`, `Game.Core.Tests/Tasks/Task0004AcceptanceTests.cs` |
| Economy Build And Progression (T12, T13, T14, T15, T16, T17) | Resource / Build / Progression Panels | Spend resources, place/build, train, upgrade, repair, or pick rewards | Render deterministic resource, build, queue, upgrade, and progression changes with clear invalid-state feedback | `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`, `Game.Core.Tests/Services/SaveServiceSerializationTests.cs`, `Game.Core.Tests/Services/SaveServiceVersionGuardTests.cs`, `Game.Core.Tests/Services/SaveServiceAtomicWriteTests.cs` |
| Meta Systems And Platform (T25, T26, T27, T28, T29, T30, T46, T47, T48, T50, T52, T54, T55, T56, T57, T58) | Settings / Save / Meta Surfaces | Save, load, localize, tune audio, or inspect platform/runtime status | Render persistence, localization, audio, performance, and platform status on governed player-visible surfaces | `Game.Core.Tests/Tasks/Task0025AcceptanceTests.cs`, `Tests.Godot/tests/Tasks/test_task0026_acceptance.gd`, `Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0027AcceptanceTests.cs` |
| Config Governance And Audit (T02, T31, T32, T33, T34, T35, T36, T37, T38, T39, T40) | Config Summary / Audit / Migration Surfaces | Inspect config state, validation, governance, migration, and report metadata | Render active config, schema status, fallback policy, migration status, and audit metadata without relying on logs-only evidence | `Tests.Godot/tests/Tasks/test_task0002_acceptance.gd`, `Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs`, `Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs`, `Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs` |

## 6. Screen And Surface Requirements

### Entry And Bootstrap
- Audience: player-facing.
- Empty state: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.
- Failure state: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.
- Completion result: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.

### Core Loop State And Outcome
- Audience: player-facing.
- Empty state: Negative tests must assert explicit failure when CardDefinition or CardInstance is struct, enum, or any non interface/class shape; missing negative gate fails acceptance.
- Failure state: Game.Core.Tests/Contracts must include reflection assertions that CardDefinition and CardInstance are IsInterface or IsClass (including record class); any other type shape fails acceptance.
- Completion result: In Game.Core/Contracts, CardDefinition and CardInstance must be interface or class (record class allowed); reflection tests assert IsInterface or IsClass and reject other shapes.

### Combat Pressure And Interaction
- Audience: player-facing.
- Empty state: ADR-0021 and ADR-0029 must be present in task=5 adr_refs of both tasks_back.json and tasks_gameplay.json; any missing or mismatch must fail.
- Failure state: In valid constructed samples, `OfferLockSnapshot.rng_stream` equals `OfferProvenance.rng_stream`; any mismatch fails contract validation.
- Completion result: `OfferLockSnapshot` includes `stable_ids`, `display_order`, `provenance`, `rng_stream`, and `locked_at_save_point` semantics (implemented as `IsLockedAtSavePoint`), and `Provenance` remains intact through value-object round-trip serialization/deserialization.

### Economy Build And Progression
- Audience: player-facing.
- Empty state: Startup smoke must run the Godot project and verify all required autoloads load without startup errors; if any autoload fails to load or any startup error/fatal appears, acceptance must fail and stop further wiring checks.
- Failure state: 保存仅允许写入 user:// 下合法相对路径；输入绝对路径、越权路径或 traversal-like 路径时必须 fail-fast 返回错误，且目标位置不得产生任何落盘文件。
- Completion result: xUnit must verify atomic commit behavior by writing to a temp file first and replacing the target as one commit outcome.

### Meta Systems And Platform
- Audience: player-facing or mixed.
- Empty state: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.
- Failure state: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.
- Completion result: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.

### Config Governance And Audit
- Audience: operator-facing or mixed.
- Empty state: Task 33 acceptance checklist must explicitly back-link ADR-0021 and ADR-0032 at item or footer level; missing either ADR link fails acceptance.
- Failure state: Game.Core/, Game.Core.Tests/, and Tests.Godot/ must each contain a .csproj with TargetFramework=net8.0 and Nullable=enable; Game.Godot/ is a script/resource directory and must not contain any standalone .csproj.
- Completion result: Repository root must contain Game.Core/, Game.Godot/, Game.Core.Tests/, and Tests.Godot/.

- Operator-facing read surfaces are allowed when player-facing interaction is not appropriate.

## 7. Screen-Level Contracts

### 7.1 MainMenu And Boot Flow
- Covered slice: Entry And Bootstrap.
- Must show: start, continue, retry bootstrap, and platform-start validation state.
- Must not hide: startup failure, continue-gate denial, or export/runtime startup issues behind logs only.
- Validation focus: boot path, continue gate, retry flow, and startup validation evidence.

### 7.2 Runtime HUD And Outcome Surfaces
- Covered slice: Core Loop State And Outcome.
- Must show: phase, timer, HP, prompts, reward entry, invalid-action prompts, speed state, and terminal outcomes.
- Must not hide: terminal or prompt state transitions that occur without visible HUD or outcome feedback.
- Validation focus: HUD state changes, prompts, reward visibility, and win/lose transitions.

### 7.3 Combat Pressure And Interaction Surfaces
- Covered slice: Combat Pressure And Interaction.
- Must show: pressure, spawn cadence, targeting, pathing fallback, combat resolution, and camera interaction state.
- Must not hide: combat pressure or targeting changes that only appear in logs or traces.
- Validation focus: combat feedback, pressure visibility, pathing fallback evidence, and camera interaction smoke checks.

### 7.4 Economy And Progression Panels
- Covered slice: Economy Build And Progression.
- Must show: resource totals, build placement state, queue state, upgrade/repair state, tech state, and progression results.
- Must not hide: invalid spend/build/progression transitions without governed feedback.
- Validation focus: resource determinism, build validation, queue behavior, and progression surface evidence.

### 7.5 Save, Settings, And Meta Surfaces
- Covered slice: Meta Systems And Platform.
- Must show: save/load status, cloud state, localization state, audio state, performance state, and platform/runtime status.
- Must not hide: persistence or settings failures that are only visible in lower-level logs.
- Validation focus: save/load flow, cloud sync, localization/audio controls, and platform status visibility.

### 7.6 Config Audit And Migration Surfaces
- Covered slice: Config Governance And Audit.
- Must show: active config, schema status, fallback status, migration state, config audit metadata, and report metadata.
- Must not hide: validation, fallback, or migration outcomes that do not surface on a governed read surface.
- Validation focus: config validation, governance, migration, and audit metadata evidence.

## 8. Screen State Matrix

| Screen Group | Entry State | Interaction State | Failure State | Recovery / Exit |
| --- | --- | --- | --- | --- |
| MainMenu And Boot Flow | show start, continue, and startup readiness before any run begins. | allow start, continue, retry bootstrap, and acknowledgement of startup state. | show startup failure, continue denial, or runtime-start validation failure explicitly. | retry bootstrap, acknowledge, or return to menu. |
| Runtime HUD And Outcome Surfaces | show no active run state until runtime data is available. | show phase, timer, HP, prompts, reward entry, invalid-action prompts, speed state, and terminal outcomes. | show prompt/terminal failure state instead of leaving the HUD stale or blank. | acknowledge outcome, continue the run, or return to menu. |
| Combat Pressure And Interaction Surfaces | show no active combat state until combat data and camera ownership are ready. | show pressure, targeting, pathing fallback, combat resolution, and camera interaction state. | show blocked targeting, missing path, or hidden pressure failure explicitly. | retry, acknowledge, or return to the governed combat-ready surface. |
| Economy And Progression Panels | show no owned economy state until resource/build/progression data is available. | show resource totals, build placement state, queue state, upgrade/repair state, tech state, and progression results. | show invalid spend/build/progression state without mutating deterministic ownership silently. | acknowledge invalid state, retry the action, or return to menu. |
| Save, Settings, And Meta Surfaces | show no persisted/platform state until save, cloud, or settings services are available. | show save/load status, cloud state, localization state, audio state, performance state, and platform/runtime status. | show persistence or settings failure instead of only writing low-level logs. | retry, acknowledge, or return to menu. |
| Config Audit And Migration Surfaces | show no active run state until config, validation, and migration data is available. | show active config, schema status, fallback status, migration state, config audit metadata, and report metadata. | show validation, fallback, or migration failure on the governed read surface. | retry, acknowledge, or return to menu after review. |

## 9. Scope And Non-Goals

- Chapter 7 covers UI or governed visible-surface ownership for every completed task in `.taskmaster/tasks/tasks.json`.
- It does not require final production polish, animation, skinning, or marketing-grade copy.

### 9.1 In Scope

- Surface ownership for startup, loop, combat, economy, meta, and governance capabilities.
- Empty state, failure state, and completion state for each major slice.
- Task alignment and validation references back to completed backlog items.

### 9.2 Non-Goals
- Final UX polish, visual theming, animation tuning, and cosmetic-only layout work.
- Replacing source-of-truth task status outside `.taskmaster/tasks/tasks.json`.

## 10. Unwired UI Feature List

- Entry And Bootstrap: define concrete scene ownership, empty/failure states, and validation evidence for T01, T11, T21, T43, T45, T53.
- Core Loop State And Outcome: define concrete scene ownership, empty/failure states, and validation evidence for T03, T07, T08, T09, T10, T18, T19, T23, T24, T44.
- Combat Pressure And Interaction: define concrete scene ownership, empty/failure states, and validation evidence for T04, T05, T06, T20, T22, T41, T42, T49, T51.
- Economy Build And Progression: define concrete scene ownership, empty/failure states, and validation evidence for T12, T13, T14, T15, T16, T17.
- Meta Systems And Platform: define concrete scene ownership, empty/failure states, and validation evidence for T25, T26, T27, T28, T29, T30, T46, T47, T48, T50, T52, T54, T55, T56, T57, T58.
- Config Governance And Audit: define concrete scene ownership, empty/failure states, and validation evidence for T02, T31, T32, T33, T34, T35, T36, T37, T38, T39, T40.

## 11. Next UI Wiring Task Candidates

### Candidate Slice MainMenu And Boot Flow

- Matrix link: `## 5. UI Wiring Matrix row Entry And Bootstrap (T01, T11, T21, T43, T45, T53)`.
- Scope: T01, T11, T21, T43, T45, T53.
- UI entry: MainMenu / Boot Flow.
- Candidate type: task-shaped UI wiring spec.
- Screen group: MainMenu And Boot Flow.
- Player action: Launch, continue, retry bootstrap, or enter a run.
- System response: Show canonical startup path, valid continue behavior, and explicit startup failure recovery.
- Empty state: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.
- Failure state: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.
- Completion result: task-0001.json must include machine-readable fields for godot_version, dotnet_version, packages_lock_exists, and evidence_paths; missing any field fails acceptance.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `MainMenu`, `BootStatusPanel`, `ContinueGateDialog`.
- Test refs: `Game.Core.Tests/Tasks/Task1ToolchainVersionChecksTests.cs`, `Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs`, `Game.Core.Tests/Tasks/Task1DotnetRestoreLockfileTests.cs`, `Game.Core.Tests/Tasks/Task1WindowsPlatformGateTests.cs`.
### Candidate Slice Runtime HUD And Outcome Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Core Loop State And Outcome (T03, T07, T08, T09, T10, T18, T19, T23, T24, T44)`.
- Scope: T03, T07, T08, T09, T10, T18, T19, T23, T24, T44.
- UI entry: HUD / Prompt / Outcome Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Runtime HUD And Outcome Surfaces.
- Player action: Play a run, observe timing, rewards, prompts, and terminal transitions.
- System response: Render readable phase, timer, HP, reward, prompt, and win/lose state from runtime events.
- Empty state: Negative tests must assert explicit failure when CardDefinition or CardInstance is struct, enum, or any non interface/class shape; missing negative gate fails acceptance.
- Failure state: Game.Core.Tests/Contracts must include reflection assertions that CardDefinition and CardInstance are IsInterface or IsClass (including record class); any other type shape fails acceptance.
- Completion result: In Game.Core/Contracts, CardDefinition and CardInstance must be interface or class (record class allowed); reflection tests assert IsInterface or IsClass and reject other shapes.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `RuntimeHud`, `OutcomePanel`, `RuntimePromptPanel`.
- Test refs: `Game.Core.Tests/Tasks/Task0003AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0007AcceptanceTests.cs`, `Game.Core.Tests/Domain/GameEventContractsTests.cs`, `Tests.Godot/tests/Adapters/test_event_bus_adapter.gd`.
### Candidate Slice Combat Pressure And Interaction Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Combat Pressure And Interaction (T04, T05, T06, T20, T22, T41, T42, T49, T51)`.
- Scope: T04, T05, T06, T20, T22, T41, T42, T49, T51.
- UI entry: Combat HUD / Pressure / Camera Feedback.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Combat Pressure And Interaction Surfaces.
- Player action: Fight, observe pressure, targeting, pathing, and camera responses.
- System response: Render enemy pressure, targeting, combat outcomes, and camera interaction without hidden state.
- Empty state: ADR-0021 and ADR-0029 must be present in task=5 adr_refs of both tasks_back.json and tasks_gameplay.json; any missing or mismatch must fail.
- Failure state: In valid constructed samples, `OfferLockSnapshot.rng_stream` equals `OfferProvenance.rng_stream`; any mismatch fails contract validation.
- Completion result: `OfferLockSnapshot` includes `stable_ids`, `display_order`, `provenance`, `rng_stream`, and `locked_at_save_point` semantics (implemented as `IsLockedAtSavePoint`), and `Provenance` remains intact through value-object round-trip serialization/deserialization.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `CombatHud`, `PressurePanel`, `CameraControlOverlay`.
- Test refs: `Game.Core.Tests/Domain/OfferLockingContractTests.cs`, `Game.Core.Tests/Domain/RngStreamTypeTests.cs`, `Game.Core.Tests/Domain/OfferLockingDeterminismTests.cs`, `Game.Core.Tests/Tasks/Task0004AcceptanceTests.cs`.
### Candidate Slice Economy And Progression Panels

- Matrix link: `## 5. UI Wiring Matrix row Economy Build And Progression (T12, T13, T14, T15, T16, T17)`.
- Scope: T12, T13, T14, T15, T16, T17.
- UI entry: Resource / Build / Progression Panels.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Economy And Progression Panels.
- Player action: Spend resources, place/build, train, upgrade, repair, or pick rewards.
- System response: Render deterministic resource, build, queue, upgrade, and progression changes with clear invalid-state feedback.
- Empty state: Startup smoke must run the Godot project and verify all required autoloads load without startup errors; if any autoload fails to load or any startup error/fatal appears, acceptance must fail and stop further wiring checks.
- Failure state: 保存仅允许写入 user:// 下合法相对路径；输入绝对路径、越权路径或 traversal-like 路径时必须 fail-fast 返回错误，且目标位置不得产生任何落盘文件。
- Completion result: xUnit must verify atomic commit behavior by writing to a temp file first and replacing the target as one commit outcome.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `ResourcePanel`, `BuildPanel`, `ProgressionPanel`.
- Test refs: `Game.Core.Tests/Tasks/Task0012AcceptanceTests.cs`, `Game.Core.Tests/Services/SaveServiceSerializationTests.cs`, `Game.Core.Tests/Services/SaveServiceVersionGuardTests.cs`, `Game.Core.Tests/Services/SaveServiceAtomicWriteTests.cs`.
### Candidate Slice Save, Settings, And Meta Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Meta Systems And Platform (T25, T26, T27, T28, T29, T30, T46, T47, T48, T50, T52, T54, T55, T56, T57, T58)`.
- Scope: T25, T26, T27, T28, T29, T30, T46, T47, T48, T50, T52, T54, T55, T56, T57, T58.
- UI entry: Settings / Save / Meta Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Save, Settings, And Meta Surfaces.
- Player action: Save, load, localize, tune audio, or inspect platform/runtime status.
- System response: Render persistence, localization, audio, performance, and platform status on governed player-visible surfaces.
- Empty state: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.
- Failure state: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.
- Completion result: Task 25 acceptance must explicitly include ADR-0033 and ADR-0021 traceability; missing either ADR id fails acceptance.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `SettingsMenu`, `SavePanel`, `RunSummaryPanel`.
- Test refs: `Game.Core.Tests/Tasks/Task0025AcceptanceTests.cs`, `Tests.Godot/tests/Tasks/test_task0026_acceptance.gd`, `Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0027AcceptanceTests.cs`.
### Candidate Slice Config Audit And Migration Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Config Governance And Audit (T02, T31, T32, T33, T34, T35, T36, T37, T38, T39, T40)`.
- Scope: T02, T31, T32, T33, T34, T35, T36, T37, T38, T39, T40.
- UI entry: Config Summary / Audit / Migration Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Config Audit And Migration Surfaces.
- Player action: Inspect config state, validation, governance, migration, and report metadata.
- System response: Render active config, schema status, fallback policy, migration status, and audit metadata without relying on logs-only evidence.
- Empty state: Task 33 acceptance checklist must explicitly back-link ADR-0021 and ADR-0032 at item or footer level; missing either ADR link fails acceptance.
- Failure state: Game.Core/, Game.Core.Tests/, and Tests.Godot/ must each contain a .csproj with TargetFramework=net8.0 and Nullable=enable; Game.Godot/ is a script/resource directory and must not contain any standalone .csproj.
- Completion result: Repository root must contain Game.Core/, Game.Godot/, Game.Core.Tests/, and Tests.Godot/.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `ConfigAuditPanel`, `MigrationStatusDialog`, `ReportMetadataPanel`.
- Test refs: `Tests.Godot/tests/Tasks/test_task0002_acceptance.gd`, `Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs`, `Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs`, `Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs`.

## 12. Copy And Accessibility

- Visible text should remain explicit and actionable.
- Failure messages must tell the player or operator what happened and what to do next.
- Do not rely on color only to convey terminal, invalid, or route-selection state.

## 13. Test And Acceptance

- Chapter 7 validation must keep `## 5. UI Wiring Matrix`, `## 10. Unwired UI Feature List`, and `## 11. Next UI Wiring Task Candidates` intact.
- Evidence should resolve back to xUnit, GdUnit, smoke, or CI outputs already referenced by task views.
- Any new UI slice should add or name a concrete validation path before implementation.

### MainMenu And Boot Flow
- Overlay acceptance notes: 地图：Act 1 最小可推进路径，覆盖 Combat/Event/Shop/Rest 节点。

### Runtime HUD And Outcome Surfaces
- Overlay acceptance notes: 每回合默认能量重置为 3（除非规则修正）。

### Combat Pressure And Interaction Surfaces
- Overlay acceptance notes: 每回合默认抽牌 4。

### Economy And Progression Panels
- Overlay acceptance notes: Core 合同与规则：T3-T12、T24-T33、T46-T50。

### Save, Settings, And Meta Surfaces
- Overlay acceptance notes: Task: T28 / GM-0128 Create ActConfig data model and loader

### Config Audit And Migration Surfaces
- Overlay acceptance notes: 存档：单槽 Continue 与战斗边界符合 ADR-0032。


## 14. Task Alignment

- Completed task count currently expected by Chapter 7: 58.
- Chapter 7 uses `.taskmaster/tasks/tasks.json` as the completion-state SSoT.
- View files remain enrichment sources for test refs, acceptance, labels, and contract context.
