---
GDD-ID: GDD-NEWROUGE-UI-WIRING-V1
Title: Newrouge Chapter 7 UI Wiring Board
Status: Draft
Owner: codex
Last Updated: 2026-05-09
Encoding: UTF-8
Applies-To:
  - .taskmaster/tasks/tasks.json
  - docs/gdd/ui-gdd-flow.md
ADR-Refs:
  - ADR-0010
  - ADR-0025
  - ADR-0032
  - ADR-0005
  - ADR-0007
  - ADR-0018
  - ADR-0024
  - ADR-0011
  - ADR-0019
  - ADR-0004
Test-Refs:
  - Tests.Godot/tests/Scenes/Map/test_map_tree_route.gd
  - Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs
  - Tests.Godot/tests/Tasks/test_task0033_acceptance.gd
  - Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd
  - Game.Core.Tests/Services/DeckServiceTests.cs
  - Game.Core.Tests/Tasks/Task0071WorkflowSelectionEvidenceTests.cs
  - Game.Core.Tests/Tasks/Task0072AcceptanceTests.cs
  - Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd
---

# Newrouge Chapter 7 UI Wiring Board

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
| Map Path, Continue, And Route Return | player-facing | T70, T86, T87, T97, T98, T103 | Show real route graph state, continue landing, locked-surface recovery, and owned path transitions without hidden state | Map / Continue / Route Return Surfaces |
| Combat Card Play And Targeting | player-facing | T72, T74, T83 | Show data-driven card text, legal targeting feedback, and CombatService-backed card-play resolution without scene-local branches | Combat Scene / Hand / Drag-To-Play Surfaces |
| Combat Runtime Bootstrap And Deck State | player-facing | T71, T80, T81, T82, T95, T96 | Show DeckService-backed piles, reshuffle timing, deck totals, warrior starting state, and Rage visibility from shared runtime ownership | Combat HUD / Deck State / Runtime Bootstrap Surfaces |
| Enemy Intent, Turn Resolution, And Definitions | player-facing | T73, T76, T89, T105, T108, T116 | Show data-backed enemy previews, multi-enemy routing, resolved enemy turns, and invalid-definition fallback as visible combat state | Enemy Intent Preview / Enemy Runtime Surfaces |
| Combat Rules, Triggers, And Feedback | player-facing | T75, T77, T78, T79, T90, T100, T101, T104 | Expose promoted rules, trigger hooks, fixed-damage ordering, and player-visible feedback without mutating deterministic combat ownership | Combat Feedback / Status / Resolution Surfaces |
| Reward Offer, Confirm, And Return Flow | player-facing | T84, T85, T114, T115 | Render stable offer locking, invalid-pool fallback, confirm gating, writeback, and route-owned return behavior | Reward Scene / Offer Choice / Return Path |
| Relics, Powers, Potions, And Shared Triggers | player-facing | T88, T99, T106, T110, T111, T112 | Show acquisition, equip state, participant visibility, and both combat-boundary and run-boundary trigger outcomes on governed surfaces | Relic Display / Participant HUD / Shared Trigger Feedback |
| Settlement Summary, Metadata, And Resume Evidence | player-facing | T91, T107, T109, T113 | Render settlement ownership, reward or relic metadata, and resume evidence from stored run data instead of partial placeholder summaries | Run Summary / Settlement / Resume Evidence Surfaces |
| Architecture, Security, And Review Governance | operator-facing or mixed | T92, T93, T94, T102 | Surface boundary protection, external-process guardrails, signal validation, and Chapter 6 sizing evidence as auditable governed outputs | Audit / Boundary / Security Evidence Surfaces |

## 4. Flow Recomposition

### Map Path, Continue, And Route Return

- T70 `Upgrade Map route graph visualization on top of existing route ownership`
- T86 `Generate route graph from existing ActConfig for the live Map path`
- T87 `Resume Continue into real Map or combat entry boundaries from autosave metadata`
- T97 `Bind generated ActConfig route data onto the live Map surface and route states`
- T98 `Restore locked Reward, Shop, and Event surfaces after Continue`
- T103 `Split Continue restore validation between primary boundaries and locked surfaces in the review pipeline`
### Combat Card Play And Targeting

- T72 `Bind CombatScene to existing data-driven card definitions and localized card text`
- T74 `Upgrade existing targeting flow with Slay-the-Spire-style card drag UX`
- T83 `Hand off CombatScene card play to the existing CombatService runtime`
### Combat Runtime Bootstrap And Deck State

- T71 `Consolidate combat deck lifecycle wiring as the umbrella task for T80-T82`
- T80 `Wire CombatScene to existing DeckService runtime state instead of local pile counters`
- T81 `Expose draw-empty reshuffle cycle through existing DeckService-backed combat runtime`
- T82 `Add combat deck total display on top of DeckService-backed pile state`
- T95 `Seed CombatService runtime from the Warrior starting deck on combat entry`
- T96 `Promote Rage into the live CombatService-backed player runtime`
### Enemy Intent, Turn Resolution, And Definitions

- T73 `Upgrade existing combat targeting and victory routing to multi-enemy runtime state`
- T76 `Bind enemy intent generation and preview to data-driven AI on existing intent surfaces`
- T89 `Instantiate combat enemy runtime from existing enemy data definitions`
- T105 `Resolve enemy turn actions and no-repeat guardrails from the displayed intent path`
- T108 `Split enemy intent review between preview generation and enemy turn resolution`
- T116 `Bind combat enemy surfaces and invalid-definition fallback to data-backed runtime enemies`
### Combat Rules, Triggers, And Feedback

- T75 `Wire existing status contracts and rules into visible combat status effects`
- T77 `Integrate trigger registration and combat-time hooks into the shared combat runtime`
- T78 `Layer combat presentation feedback on top of deterministic state without mutating runtime logic`
- T79 `Unify combat defeat trigger by HP change event and single-resolution guard`
- T90 `Promote status trigger ordering and fixed damage rules into the live combat runtime`
- T100 `Promote AOE and multi-hit ordering rules into the live combat runtime`
- T101 `Align player-visible combat feedback with the promoted runtime rule results`
- T104 `Split combat rule promotion review between core resolution and surface feedback closure`
### Reward Offer, Confirm, And Return Flow

- T84 `Generate Reward offers from existing card drop pools on first entry`
- T85 `Complete Reward three-choice selection and confirm gating on the existing Reward scene`
- T114 `Stabilize Reward offer lock re-entry and invalid-pool fallback`
- T115 `Resolve Reward confirm writeback and skip through the route-owned return path`
### Relics, Powers, Potions, And Shared Triggers

- T88 `Integrate relic acquisition, equip state, and player-facing display on the shared run path`
- T99 `Drive relic runtime effects through the shared combat trigger path`
- T106 `Integrate powers and relics as visible and effectful combat participants`
- T110 `Drive relic runtime effects through shared run trigger boundaries`
- T111 `Integrate potions as visible and effectful combat participants`
- T112 `Drive relic runtime review between combat and run trigger closures`
### Settlement Summary, Metadata, And Resume Evidence

- T91 `Expand the run summary into a stored-data-backed settlement surface`
- T107 `Complete settlement metadata for rewards and relics`
- T109 `Split settlement review between owner surface, reward or relic metadata, and resume evidence`
- T113 `Surface settlement resume evidence from stored run data`
### Architecture, Security, And Review Governance

- T92 `Promote architecture boundary tests into the main task line for Core-versus-Godot protection`
- T93 `Add deny-by-default external process execution guard and audit coverage`
- T94 `Validate security-sensitive signal contracts before wider runtime expansion`
- T102 `Audit T70-T101 Chapter 6 sizing and split any task that still exceeds one deterministic closure`

## 5. UI Wiring Matrix

| Feature | UI Surface | Player Action | System Response | Test Refs |
| --- | --- | --- | --- | --- |
| Map Path, Continue, And Route Return (T70, T86, T87, T97, T98, T103) | Map / Continue / Route Return Surfaces | Resume a run, inspect route ownership, and return through locked reward or shop boundaries | Show real route graph state, continue landing, locked-surface recovery, and owned path transitions without hidden state | `Tests.Godot/tests/Scenes/Map/test_map_tree_route.gd`, `Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs`, `Game.Core.Tests/Services/MapActConfigurationTests.cs`, `Tests.Godot/tests/Integration/test_map_navigation_state_transitions.gd` |
| Combat Card Play And Targeting (T72, T74, T83) | Combat Scene / Hand / Drag-To-Play Surfaces | Inspect cards, drag or click to play them, and target legal enemies during combat | Show data-driven card text, legal targeting feedback, and CombatService-backed card-play resolution without scene-local branches | `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Game.Core.Tests/Tasks/Task0072AcceptanceTests.cs`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd` |
| Combat Runtime Bootstrap And Deck State (T71, T80, T81, T82, T95, T96) | Combat HUD / Deck State / Runtime Bootstrap Surfaces | Enter combat, inspect deck lifecycle state, and read warrior deck or Rage-backed runtime setup | Show DeckService-backed piles, reshuffle timing, deck totals, warrior starting state, and Rage visibility from shared runtime ownership | `Tests.Godot/tests/Tasks/test_task0033_acceptance.gd`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Game.Core.Tests/Services/DeckServiceTests.cs`, `Game.Core.Tests/Tasks/Task0071WorkflowSelectionEvidenceTests.cs` |
| Enemy Intent, Turn Resolution, And Definitions (T73, T76, T89, T105, T108, T116) | Enemy Intent Preview / Enemy Runtime Surfaces | Read enemy intents, verify no-repeat guardrails, and understand invalid-definition fallback during combat | Show data-backed enemy previews, multi-enemy routing, resolved enemy turns, and invalid-definition fallback as visible combat state | `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Tests.Godot/tests/Scenes/Battle/test_battle_card_targeting_drag_play_flow.gd`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`, `Game.Core.Tests/Tasks/Task0105WorkflowSelectionEvidenceTests.cs` |
| Combat Rules, Triggers, And Feedback (T75, T77, T78, T79, T90, T100, T101, T104) | Combat Feedback / Status / Resolution Surfaces | Read status effects, turn resolution, AOE or multi-hit ordering, and defeat or trigger outcomes during live combat | Expose promoted rules, trigger hooks, fixed-damage ordering, and player-visible feedback without mutating deterministic combat ownership | `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd`, `Game.Core.Tests/Tasks/Task0075WorkflowSelectionEvidenceTests.cs`, `Game.Core.Tests/Tasks/Task0077WorkflowSelectionEvidenceTests.cs` |
| Reward Offer, Confirm, And Return Flow (T84, T85, T114, T115) | Reward Scene / Offer Choice / Return Path | Inspect reward offers, select one of three choices, skip when allowed, and return to the owned route boundary | Render stable offer locking, invalid-pool fallback, confirm gating, writeback, and route-owned return behavior | `Game.Core.Tests/Services/CardPoolSelectionTests.cs`, `Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd`, `Game.Core.Tests/Tasks/Task0084AcceptanceTests.cs`, `Tests.Godot/tests/Integration/test_reward_first_entry_shared_pool_route.gd` |
| Relics, Powers, Potions, And Shared Triggers (T88, T99, T106, T110, T111, T112) | Relic Display / Participant HUD / Shared Trigger Feedback | Acquire relics, inspect equipped participants, and understand combat or run-trigger effects from powers, relics, and potions | Show acquisition, equip state, participant visibility, and both combat-boundary and run-boundary trigger outcomes on governed surfaces | `Game.Core.Tests/Tasks/Task0088AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0088WorkflowSelectionEvidenceTests.cs`, `Game.Core.Tests/Tasks/Task0099AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs` |
| Settlement Summary, Metadata, And Resume Evidence (T91, T107, T109, T113) | Run Summary / Settlement / Resume Evidence Surfaces | Inspect stored-data-backed summary output, verify reward and relic settlement metadata, and confirm resume evidence after a run | Render settlement ownership, reward or relic metadata, and resume evidence from stored run data instead of partial placeholder summaries | `Tests.Godot/tests/UI/test_run_summary_surface.gd`, `Game.Core.Tests/Tasks/Task0066AcceptanceTests.cs`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`, `Game.Core.Tests/Tasks/Task0091WorkflowSelectionEvidenceTests.cs` |
| Architecture, Security, And Review Governance (T92, T93, T94, T102) | Audit / Boundary / Security Evidence Surfaces | Inspect review governance, security-sensitive runtime guardrails, and architecture-boundary evidence for the current T70+ slice | Surface boundary protection, external-process guardrails, signal validation, and Chapter 6 sizing evidence as auditable governed outputs | `Game.Core.Tests/Tasks/Task0092AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0067AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0092WorkflowSelectionEvidenceTests.cs`, `Game.Core.Tests/Tasks/Task0093AcceptanceTests.cs` |

## 6. Screen And Surface Requirements

### Map Path, Continue, And Route Return
- Audience: player-facing.
- Empty state: Show no active route ownership until autosave or current run route data is available.
- Failure state: Show continue denial, locked-surface refusal, or invalid route recovery explicitly instead of silently falling back.
- Completion result: Player can resume into the correct map or combat boundary and read owned route transitions from visible map surfaces.

### Combat Card Play And Targeting
- Audience: player-facing.
- Empty state: Show no playable hand or targeting preview until combat runtime and hand state are available.
- Failure state: Show invalid target, missing definition, or rejected play feedback without mutating energy, HP, or pile state.
- Completion result: Player can read localized card content, target legal enemies, and resolve card plays through the shared combat runtime path.

### Combat Runtime Bootstrap And Deck State
- Audience: player-facing.
- Empty state: Show no deck lifecycle or player runtime bootstrap state until CombatService and DeckService ownership are ready.
- Failure state: Show missing deck state, invalid reshuffle, or bootstrap denial explicitly instead of using scene-local counters.
- Completion result: Player can read shared deck lifecycle state, warrior starting deck setup, and Rage-backed runtime state from governed combat surfaces.

### Enemy Intent, Turn Resolution, And Definitions
- Audience: player-facing.
- Empty state: Show no enemy intent or roster state until runtime enemies are instantiated.
- Failure state: Show invalid enemy-definition fallback, illegal target rejection, or no-repeat guard refusal explicitly.
- Completion result: Player can inspect multi-enemy state, enemy intent previews, resolved enemy turns, and invalid-definition fallback on governed surfaces.

### Combat Rules, Triggers, And Feedback
- Audience: player-facing.
- Empty state: Show no status, trigger, or resolution history until combat rules are active.
- Failure state: Show blocked trigger, invalid ordering, or single-resolution guard refusal instead of leaving stale combat feedback.
- Completion result: Player can read statuses, trigger ordering, defeat resolution, and multi-hit or AOE feedback from governed combat surfaces.

### Reward Offer, Confirm, And Return Flow
- Audience: player-facing.
- Empty state: Show no reward offers until the current reward boundary resolves a valid offer set.
- Failure state: Show invalid-pool fallback, re-entry lock refusal, or confirm or skip rejection explicitly instead of mutating route state silently.
- Completion result: Player can inspect a stable three-offer reward set, confirm or skip exactly once, and return through the owned route boundary.

### Relics, Powers, Potions, And Shared Triggers
- Audience: player-facing.
- Empty state: Show no relic, power, or potion participant state until shared run or combat ownership is available.
- Failure state: Show participant fallback, trigger refusal, or missing equip state explicitly instead of hiding it behind shared runtime logs.
- Completion result: Player can inspect equipped relics, visible powers and potions, and shared trigger outcomes across combat and run boundaries.

### Settlement Summary, Metadata, And Resume Evidence
- Audience: player-facing.
- Empty state: Show no settlement summary until stored run data is available for the selected run.
- Failure state: Show missing settlement metadata, missing reward or relic fields, or absent resume evidence explicitly instead of showing partial placeholder summaries.
- Completion result: Player can inspect stored settlement outcome, reward or relic metadata, and resume evidence from governed summary surfaces.

### Architecture, Security, And Review Governance
- Audience: operator-facing or mixed.
- Empty state: Show no audit evidence until the current T70+ governance artifacts are available.
- Failure state: Show missing architecture-boundary evidence, denied external-process guard coverage, or signal-validation gaps explicitly in audit outputs.
- Completion result: Operator can inspect architecture-boundary, security, and Chapter 6 sizing evidence for the current T70+ slice without creating a new gameplay UI task.

- Operator-facing read surfaces are allowed when player-facing interaction is not appropriate.

## 7. Screen-Level Contracts

### 7.1 Map Path And Continue Surfaces
- Covered slice: Map Path, Continue, And Route Return.
- Must show: reachable route graph, selected path, continue landing, locked-surface restore state, and refusal feedback.
- Must not hide: invalid route ownership, locked return-path refusal, or continue-boundary denial behind logs only.
- Validation focus: map graph visibility, continue landing, locked-surface recovery, and route-owned return behavior.

### 7.2 Combat Card Play Surfaces
- Covered slice: Combat Card Play And Targeting.
- Must show: localized card text, cost, target preview, legal target highlight, and card-play feedback.
- Must not hide: invalid target refusal, rejected play, or missing-definition fallback behind logs only.
- Validation focus: card text binding, drag or click play, legal targeting, and CombatService-backed play resolution.

### 7.3 Combat Runtime Bootstrap Surfaces
- Covered slice: Combat Runtime Bootstrap And Deck State.
- Must show: draw, discard, exhaust, reshuffle, deck total, starting deck ownership, and player runtime bootstrap state.
- Must not hide: scene-local pile ownership, missing reshuffle feedback, or bootstrap fallback behind logs only.
- Validation focus: DeckService-backed pile truth, reshuffle visibility, warrior deck bootstrap, and Rage runtime state.

### 7.4 Enemy Intent And Resolution Surfaces
- Covered slice: Enemy Intent, Turn Resolution, And Definitions.
- Must show: enemy roster, current intent, selected target state, resolved enemy turn feedback, and invalid-definition fallback notice.
- Must not hide: enemy-definition rejection, illegal selection, or no-repeat guard outcome behind logs only.
- Validation focus: enemy preview visibility, multi-enemy routing, turn resolution, and invalid-definition fallback.

### 7.5 Combat Rules And Feedback Surfaces
- Covered slice: Combat Rules, Triggers, And Feedback.
- Must show: status stacks, trigger outcomes, fixed-damage ordering, defeat resolution, and player-visible combat feedback.
- Must not hide: trigger refusal, stale status state, or duplicate defeat resolution behind logs only.
- Validation focus: status visibility, trigger ordering, defeat guardrails, and promoted combat feedback.

### 7.6 Reward Offer And Confirm Surfaces
- Covered slice: Reward Offer, Confirm, And Return Flow.
- Must show: three-offer reward set, lock persistence, selected-card confirmation state, skip state, and route-owned return feedback.
- Must not hide: invalid-pool fallback, confirm denial, skip denial, or duplicate resolution behind logs only.
- Validation focus: offer generation, lock persistence, confirm gating, writeback, and route-owned return behavior.

### 7.7 Relic And Combat Participant Surfaces
- Covered slice: Relics, Powers, Potions, And Shared Triggers.
- Must show: relic acquisition, equipped participants, potion or power participant visibility, and trigger feedback across combat and run boundaries.
- Must not hide: missing equip state, trigger refusal, or participant fallback behind logs only.
- Validation focus: relic acquisition, participant visibility, combat-trigger feedback, and run-trigger feedback.

### 7.8 Settlement And Run Summary Surfaces
- Covered slice: Settlement Summary, Metadata, And Resume Evidence.
- Must show: stored run outcome, reward or relic metadata, and resume evidence linked to the same settlement owner surface.
- Must not hide: missing settlement metadata or missing resume evidence behind partial placeholder summaries.
- Validation focus: stored-data summary ownership, metadata visibility, and resume evidence visibility.

### 7.9 Governance And Audit Surfaces
- Covered slice: Architecture, Security, And Review Governance.
- Must show: architecture-boundary evidence, external-process guard evidence, signal-validation evidence, and Chapter 6 sizing audit context.
- Must not hide: missing audit evidence or governance gaps behind implementation-only notes.
- Validation focus: audit readability and governed evidence paths for architecture, security, and sizing.

## 8. Screen State Matrix

| Screen Group | Entry State | Interaction State | Failure State | Recovery / Exit |
| --- | --- | --- | --- | --- |
| Map Path And Continue Surfaces | show map or continue entry only when route ownership is known. | show reachable nodes, selected route, and restore or return choices. | show continue denial, missing autosave, or locked-surface refusal explicitly. | retry continue, return to map, or return to the owned route boundary. |
| Combat Card Play Surfaces | show hand and available play actions only when combat runtime is ready. | show card hover, drag preview, selected target, and resolved play feedback. | show rejected play or invalid target without consuming state. | cancel targeting, return card to hand, or continue combat. |
| Combat Runtime Bootstrap Surfaces | show no deck or bootstrap state until combat runtime is established. | show live draw, discard, exhaust, total-count, and player runtime status updates. | show bootstrap or pile-state mismatch explicitly. | retry combat entry or continue once shared runtime ownership is restored. |
| Enemy Intent And Resolution Surfaces | show no enemy preview until runtime enemies are ready. | show selected enemy, intent preview, and resolved enemy-turn outcomes. | show invalid-definition or illegal-target refusal explicitly. | clear selection, continue combat, or await valid runtime enemy state. |
| Combat Rules And Feedback Surfaces | show no rule-derived feedback until combat events begin. | show live status updates, trigger outcomes, and resolution history. | show duplicate resolution or invalid trigger ordering explicitly. | acknowledge feedback and continue combat under the shared runtime owner. |
| Reward Offer And Confirm Surfaces | show no reward selection until the offer set is resolved. | show selected reward, confirm or skip affordances, and return-path state. | show invalid pool or duplicate confirm or skip refusal explicitly. | confirm reward, skip reward, or return through the owned route boundary. |
| Relic And Combat Participant Surfaces | show no participant surfaces until shared run or combat ownership is established. | show equipped participants, trigger outcomes, and participant-affecting runtime changes. | show missing participant state or trigger refusal explicitly. | continue combat or run flow once participant ownership is restored. |
| Settlement And Run Summary Surfaces | show no settlement data until a stored run summary is selected. | show summary outcome, reward or relic metadata, and resume evidence together. | show missing stored-data fields explicitly. | close summary, return to run flow, or inspect another stored settlement. |
| Governance And Audit Surfaces | show no governance panel until audit artifacts are loaded. | show current audit evidence and governance findings as read-only outputs. | show missing audit artifacts or blocked evidence explicitly. | record findings or return to the current implementation lane. |

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

- Map Path, Continue, And Route Return: define concrete scene ownership, empty/failure states, and validation evidence for T70, T86, T87, T97, T98, T103.
- Combat Card Play And Targeting: define concrete scene ownership, empty/failure states, and validation evidence for T72, T74, T83.
- Combat Runtime Bootstrap And Deck State: define concrete scene ownership, empty/failure states, and validation evidence for T71, T80, T81, T82, T95, T96.
- Enemy Intent, Turn Resolution, And Definitions: define concrete scene ownership, empty/failure states, and validation evidence for T73, T76, T89, T105, T108, T116.
- Combat Rules, Triggers, And Feedback: define concrete scene ownership, empty/failure states, and validation evidence for T75, T77, T78, T79, T90, T100, T101, T104.
- Reward Offer, Confirm, And Return Flow: define concrete scene ownership, empty/failure states, and validation evidence for T84, T85, T114, T115.
- Relics, Powers, Potions, And Shared Triggers: define concrete scene ownership, empty/failure states, and validation evidence for T88, T99, T106, T110, T111, T112.
- Settlement Summary, Metadata, And Resume Evidence: define concrete scene ownership, empty/failure states, and validation evidence for T91, T107, T109, T113.
- Architecture, Security, And Review Governance: define concrete scene ownership, empty/failure states, and validation evidence for T92, T93, T94, T102.

## 11. Next UI Wiring Task Candidates

### Candidate Slice Map Path And Continue Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Map Path, Continue, And Route Return (T70, T86, T87, T97, T98, T103)`.
- Scope: T70, T86, T87, T97, T98, T103.
- UI entry: Map / Continue / Route Return Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Map Path And Continue Surfaces.
- Player action: Resume a run, inspect route ownership, and return through locked reward or shop boundaries.
- System response: Show real route graph state, continue landing, locked-surface recovery, and owned path transitions without hidden state.
- Empty state: Show no active route ownership until autosave or current run route data is available.
- Failure state: Show continue denial, locked-surface refusal, or invalid route recovery explicitly instead of silently falling back.
- Completion result: Player can resume into the correct map or combat boundary and read owned route transitions from visible map surfaces.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `MapScreen`, `ContinueGateDialog`, `RouteReturnPanel`.
- Test refs: `Tests.Godot/tests/Scenes/Map/test_map_tree_route.gd`, `Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs`, `Game.Core.Tests/Services/MapActConfigurationTests.cs`, `Tests.Godot/tests/Integration/test_map_navigation_state_transitions.gd`.
### Candidate Slice Combat Card Play Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Combat Card Play And Targeting (T72, T74, T83)`.
- Scope: T72, T74, T83.
- UI entry: Combat Scene / Hand / Drag-To-Play Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Combat Card Play Surfaces.
- Player action: Inspect cards, drag or click to play them, and target legal enemies during combat.
- System response: Show data-driven card text, legal targeting feedback, and CombatService-backed card-play resolution without scene-local branches.
- Empty state: Show no playable hand or targeting preview until combat runtime and hand state are available.
- Failure state: Show invalid target, missing definition, or rejected play feedback without mutating energy, HP, or pile state.
- Completion result: Player can read localized card content, target legal enemies, and resolve card plays through the shared combat runtime path.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `CombatHud`, `HandPanel`, `TargetPreviewOverlay`.
- Test refs: `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Game.Core.Tests/Tasks/Task0072AcceptanceTests.cs`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`.
### Candidate Slice Combat Runtime Bootstrap Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Combat Runtime Bootstrap And Deck State (T71, T80, T81, T82, T95, T96)`.
- Scope: T71, T80, T81, T82, T95, T96.
- UI entry: Combat HUD / Deck State / Runtime Bootstrap Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Combat Runtime Bootstrap Surfaces.
- Player action: Enter combat, inspect deck lifecycle state, and read warrior deck or Rage-backed runtime setup.
- System response: Show DeckService-backed piles, reshuffle timing, deck totals, warrior starting state, and Rage visibility from shared runtime ownership.
- Empty state: Show no deck lifecycle or player runtime bootstrap state until CombatService and DeckService ownership are ready.
- Failure state: Show missing deck state, invalid reshuffle, or bootstrap denial explicitly instead of using scene-local counters.
- Completion result: Player can read shared deck lifecycle state, warrior starting deck setup, and Rage-backed runtime state from governed combat surfaces.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `DeckStatePanel`, `CombatBootstrapPanel`, `PlayerRuntimeStatusPanel`.
- Test refs: `Tests.Godot/tests/Tasks/test_task0033_acceptance.gd`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Game.Core.Tests/Services/DeckServiceTests.cs`, `Game.Core.Tests/Tasks/Task0071WorkflowSelectionEvidenceTests.cs`.
### Candidate Slice Enemy Intent And Resolution Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Enemy Intent, Turn Resolution, And Definitions (T73, T76, T89, T105, T108, T116)`.
- Scope: T73, T76, T89, T105, T108, T116.
- UI entry: Enemy Intent Preview / Enemy Runtime Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Enemy Intent And Resolution Surfaces.
- Player action: Read enemy intents, verify no-repeat guardrails, and understand invalid-definition fallback during combat.
- System response: Show data-backed enemy previews, multi-enemy routing, resolved enemy turns, and invalid-definition fallback as visible combat state.
- Empty state: Show no enemy intent or roster state until runtime enemies are instantiated.
- Failure state: Show invalid enemy-definition fallback, illegal target rejection, or no-repeat guard refusal explicitly.
- Completion result: Player can inspect multi-enemy state, enemy intent previews, resolved enemy turns, and invalid-definition fallback on governed surfaces.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `EnemyIntentPanel`, `EnemyRosterPanel`, `EnemyFallbackNotice`.
- Test refs: `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Tests.Godot/tests/Scenes/Battle/test_battle_card_targeting_drag_play_flow.gd`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`, `Game.Core.Tests/Tasks/Task0105WorkflowSelectionEvidenceTests.cs`.
### Candidate Slice Combat Rules And Feedback Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Combat Rules, Triggers, And Feedback (T75, T77, T78, T79, T90, T100, T101, T104)`.
- Scope: T75, T77, T78, T79, T90, T100, T101, T104.
- UI entry: Combat Feedback / Status / Resolution Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Combat Rules And Feedback Surfaces.
- Player action: Read status effects, turn resolution, AOE or multi-hit ordering, and defeat or trigger outcomes during live combat.
- System response: Expose promoted rules, trigger hooks, fixed-damage ordering, and player-visible feedback without mutating deterministic combat ownership.
- Empty state: Show no status, trigger, or resolution history until combat rules are active.
- Failure state: Show blocked trigger, invalid ordering, or single-resolution guard refusal instead of leaving stale combat feedback.
- Completion result: Player can read statuses, trigger ordering, defeat resolution, and multi-hit or AOE feedback from governed combat surfaces.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `StatusEffectPanel`, `CombatFeedbackPanel`, `ResolutionLogPanel`.
- Test refs: `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`, `Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd`, `Game.Core.Tests/Tasks/Task0075WorkflowSelectionEvidenceTests.cs`, `Game.Core.Tests/Tasks/Task0077WorkflowSelectionEvidenceTests.cs`.
### Candidate Slice Reward Offer And Confirm Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Reward Offer, Confirm, And Return Flow (T84, T85, T114, T115)`.
- Scope: T84, T85, T114, T115.
- UI entry: Reward Scene / Offer Choice / Return Path.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Reward Offer And Confirm Surfaces.
- Player action: Inspect reward offers, select one of three choices, skip when allowed, and return to the owned route boundary.
- System response: Render stable offer locking, invalid-pool fallback, confirm gating, writeback, and route-owned return behavior.
- Empty state: Show no reward offers until the current reward boundary resolves a valid offer set.
- Failure state: Show invalid-pool fallback, re-entry lock refusal, or confirm or skip rejection explicitly instead of mutating route state silently.
- Completion result: Player can inspect a stable three-offer reward set, confirm or skip exactly once, and return through the owned route boundary.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `RewardScene`, `RewardChoicePanel`, `RewardReturnPanel`.
- Test refs: `Game.Core.Tests/Services/CardPoolSelectionTests.cs`, `Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd`, `Game.Core.Tests/Tasks/Task0084AcceptanceTests.cs`, `Tests.Godot/tests/Integration/test_reward_first_entry_shared_pool_route.gd`.
### Candidate Slice Relic And Combat Participant Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Relics, Powers, Potions, And Shared Triggers (T88, T99, T106, T110, T111, T112)`.
- Scope: T88, T99, T106, T110, T111, T112.
- UI entry: Relic Display / Participant HUD / Shared Trigger Feedback.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Relic And Combat Participant Surfaces.
- Player action: Acquire relics, inspect equipped participants, and understand combat or run-trigger effects from powers, relics, and potions.
- System response: Show acquisition, equip state, participant visibility, and both combat-boundary and run-boundary trigger outcomes on governed surfaces.
- Empty state: Show no relic, power, or potion participant state until shared run or combat ownership is available.
- Failure state: Show participant fallback, trigger refusal, or missing equip state explicitly instead of hiding it behind shared runtime logs.
- Completion result: Player can inspect equipped relics, visible powers and potions, and shared trigger outcomes across combat and run boundaries.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `RelicTray`, `ParticipantStatusPanel`, `TriggerFeedbackPanel`.
- Test refs: `Game.Core.Tests/Tasks/Task0088AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0088WorkflowSelectionEvidenceTests.cs`, `Game.Core.Tests/Tasks/Task0099AcceptanceTests.cs`, `Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs`.
### Candidate Slice Settlement And Run Summary Surfaces

- Matrix link: `## 5. UI Wiring Matrix row Settlement Summary, Metadata, And Resume Evidence (T91, T107, T109, T113)`.
- Scope: T91, T107, T109, T113.
- UI entry: Run Summary / Settlement / Resume Evidence Surfaces.
- Candidate type: task-shaped UI wiring spec.
- Screen group: Settlement And Run Summary Surfaces.
- Player action: Inspect stored-data-backed summary output, verify reward and relic settlement metadata, and confirm resume evidence after a run.
- System response: Render settlement ownership, reward or relic metadata, and resume evidence from stored run data instead of partial placeholder summaries.
- Empty state: Show no settlement summary until stored run data is available for the selected run.
- Failure state: Show missing settlement metadata, missing reward or relic fields, or absent resume evidence explicitly instead of showing partial placeholder summaries.
- Completion result: Player can inspect stored settlement outcome, reward or relic metadata, and resume evidence from governed summary surfaces.
- Requirement IDs: `Add requirement mapping before implementation.`
- Validation artifact targets: `Add artifact target before implementation.`
- Suggested standalone surfaces: `RunSummaryPanel`, `SettlementMetadataPanel`, `ResumeEvidencePanel`.
- Test refs: `Tests.Godot/tests/UI/test_run_summary_surface.gd`, `Game.Core.Tests/Tasks/Task0066AcceptanceTests.cs`, `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`, `Game.Core.Tests/Tasks/Task0091WorkflowSelectionEvidenceTests.cs`.

## 12. Copy And Accessibility

- Visible text should remain explicit and actionable.
- Failure messages must tell the player or operator what happened and what to do next.
- Do not rely on color only to convey terminal, invalid, or route-selection state.

## 13. Test And Acceptance

- Chapter 7 validation must keep `## 5. UI Wiring Matrix`, `## 10. Unwired UI Feature List`, and `## 11. Next UI Wiring Task Candidates` intact.
- Evidence should resolve back to xUnit, GdUnit, smoke, or CI outputs already referenced by task views.
- Any new UI slice should add or name a concrete validation path before implementation.

### Map Path And Continue Surfaces
- Overlay acceptance notes: After checking workflow.md Phase 0-2 against the current triplet and Overlay 08 baseline, T70-T116 do require overlay maintenance, but they do not automatically require new contract files.

### Combat Card Play Surfaces
- Overlay acceptance notes: Data-driven card, enemy, and route binding: T72, T73, T76, T89, T116.

### Combat Runtime Bootstrap Surfaces
- Overlay acceptance notes: Deck/runtime handoff and HUD truth source: T71, T80, T81, T82, T95.

### Enemy Intent And Resolution Surfaces
- Overlay acceptance notes: Data-driven card, enemy, and route binding: T72, T73, T76, T89, T116.

### Combat Rules And Feedback Surfaces
- Overlay acceptance notes: Surface feedback on top of deterministic runtime results: T74, T75, T78, T101.

### Reward Offer And Confirm Surfaces
- Overlay acceptance notes: Reward and post-combat closure: T84, T85, T114, T115.

### Relic And Combat Participant Surfaces
- Overlay acceptance notes: Relic acquisition and run-surface visibility: T88, T110.

### Settlement And Run Summary Surfaces
- Overlay acceptance notes: Settlement ownership and replay evidence: T91, T107, T113.


## 14. Task Alignment

- Completed task count currently expected by Chapter 7: 47.
- Chapter 7 uses `.taskmaster/tasks/tasks.json` as the completion-state SSoT.
- View files remain enrichment sources for test refs, acceptance, labels, and contract context.
