---
GDD-ID: GDD-NEWROUGE-M1-PLAYABLE-SETUP
Title: NewRouge M1 Playable Setup And First-Run Requirements
Status: Draft
Owner: codex
Last Updated: 2026-04-23
Encoding: UTF-8
Applies-To:
  - docs/gdd/ui-gdd-flow.md
  - docs/gdd/GDD-NEWROUGE-V1.md
  - project.godot
  - Game.Core/Data/**
  - Game.Godot/Scenes/**
  - Game.Godot/Translations/**
ADR-Refs:
  - ADR-0010
  - ADR-0011
  - ADR-0023
  - ADR-0024
  - ADR-0025
  - ADR-0032
  - ADR-0033
Test-Refs:
  - Tests.Godot/tests/Scenes/Smoke/test_main_scene_smoke.gd
  - Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd
  - Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd
  - Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd
  - Tests.Godot/tests/Integration/test_m1_feedback_fallbacks.gd
  - Tests.Godot/tests/Integration/test_m1_ui_focus_accessibility.gd
  - Tests.Godot/tests/UI/test_run_summary_surface.gd
  - Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd
  - scripts/python/smoke_headless.py
---

# NewRouge M1 Playable Setup And First-Run Requirements

## 1. Goal

The next milestone is not more isolated UI wiring. The goal is a player-complete M1 loop: launch the game, start a new run, make a few meaningful Slay-the-Spire-like route decisions, resolve combat/event/shop/rest/reward screens, save or recover from invalid states, and reach an explicit run outcome or safe return point without developer intervention.

Reference model: Slay the Spire is used here as a structural reference, not a content clone. The M1 target should copy the clarity of its player loop: title menu, one character, one act map, node choice, turn-based combat, post-combat reward, campfire/rest, shop, event choices with costs, visible intent, and readable failure reasons.

## 2. Startup And Configuration Completeness

### 2.1 Required Configuration Files

| Area | Required Path | Current Status | M1 Requirement |
| --- | --- | --- | --- |
| Godot project settings | `project.godot` | Exists | Must keep `run/main_scene="res://Game.Godot/Scenes/Main.tscn"`, Windows-friendly 1280x720 default viewport, required autoloads, and C# project path. |
| Main bootstrap scene | `Game.Godot/Scenes/Main.tscn` | Exists | Must instantiate the real boot path, not a demo-only surface. It must include input bootstrap and route to player-facing main menu. |
| Main menu scene | `Game.Godot/Scenes/UI/MainMenu.tscn` | Exists | Must expose New Run, Continue, Settings, and Quit with visible disabled/blocked messaging for Continue. |
| Input defaults | `Game.Godot/Scripts/Bootstrap/InputMapper.cs` | Exists | Must define keyboard defaults for accept, cancel, directional navigation, and menu traversal. Add controller mappings before controller support is claimed. |
| Feature flags | `Game.Godot/Scripts/Config/FeatureFlags.cs` and `user://config/features.json` | Exists | Must default M1 playable path on. Experimental or debug-only flows must be opt-in and must not replace the New Run path. |
| Translations | `Game.Godot/Translations/en.csv`, `Game.Godot/Translations/zh-CN.csv` | Exists | Every visible M1 string must resolve through these files with no raw key echo; loading policy is defined in `docs/gdd/m1-translation-loading-strategy.zh-CN.md`. |
| Save and persistence path | `user://saves`, `user://config`, app userdata under Godot | Exists by adapter/service usage | Must keep saves and config inside `user://`; invalid absolute/traversal paths fail closed. |
| Export preset | `export_presets.cfg` | Exists | Must include a Windows runnable preset before external playtest delivery. |
| Audio assets | `Game.Godot/Assets/Audio/**` | Placeholder only | M1 may ship with placeholder silence, but missing configured audio must not crash. Add music/SFX manifest only when real assets exist. |
| Logs and smoke evidence | `logs/ci/<date>/smoke/**`, `logs/e2e/<date>/**` | Exists by scripts | Startup and first-run smoke outputs must land here, never under packed `res://`. |

### 2.2 Required Runtime Defaults

The playable default should be conservative:

- Default locale: English fallback, with zh-CN selectable and validated.
- Default window: 1280x720 viewport, stretch mode `viewport`.
- Default run profile: M1 Act 1, Warrior only, Difficulty 1 selected by default or explicitly prompted.
- Default save slot: one autosave slot, Continue gated by valid metadata.
- Default delivery posture: player-facing failures should show visible feedback first, logs second.
- Default debug posture: no debug-only route may be the only way to enter the M1 loop.

### 2.3 Config Acceptance

Before the game can be called "playable", these checks must pass:

- Opening `project.godot` starts `Game.Godot/Scenes/Main.tscn` without fatal autoload errors.
- MainMenu New Run reaches DifficultySelect, CharacterSelect, then Map.
- Continue either loads a valid autosave or shows a localized blocked reason.
- Settings language affects player-visible strings after restart or documented re-entry.
- Missing audio/config/save data degrades visibly and safely instead of crashing or silently doing nothing.

## 3. Minimum Content Data Set

### 3.1 Content Data Philosophy

Slay the Spire works because each floor asks for a clear tradeoff: fight for reward, visit a shop, rest or upgrade, take an event risk, or route toward danger. M1 should use a small content pool but must preserve that rhythm. Quantity is less important than having at least one meaningful decision on each screen.

### 3.2 Required Data Files And Locations

| Content Type | Required Path | Minimum M1 Set | Notes |
| --- | --- | --- | --- |
| Act config | `Game.Core/Data/act1-config.json` | 1 Act with 6-8 nodes and at least one branch | This file is recommended because `ActConfigLoader` already expects `schema_version`, `act_id`, `node_graph`, `pools`, and `encounters`. |
| Enemy definitions | `Game.Core/Data/act1-enemy-definitions.json` | Already has normal, elite, boss | Add at least 2 normal enemies before balance testing; current file can support smoke-level M1. |
| Card definitions | `Game.Core/Data/m1-card-definitions.json` | Warrior starting deck plus reward/shop pool | Should include stable IDs, translation keys, cost, type, target rule, base effect, and upgrade routes. |
| Starting deck | `Game.Core/Data/m1-warrior-starting-deck.json` | 10 cards | Required shape: card IDs and counts. Keep deterministic order or explicit shuffle seed behavior. |
| Card pools | `Game.Core/Data/m1-card-pools.json` | normal, elite, boss, shop, event reward pools | Existing `CardPoolCatalog` has generated IDs; a real JSON catalog should replace placeholder-only pools for player play. |
| Relics | `Game.Core/Data/m1-relic-definitions.json` | 5-8 playable relics for M1, even if 20 contract entries exist | StartingRelicService already has 20 identifiers; player-facing M1 needs only the subset with visible effects. |
| Curses | `Game.Core/Data/m1-curse-definitions.json` | At least 1 curse | Must support event cost and rest/shop removal. |
| Events | `Game.Core/Data/m1-event-definitions.json` | At least 2 events | One HP-loss event and one curse-cost event, each with preview and result text. |
| Shop inventory | `Game.Core/Data/m1-shop-pools.json` | At least 3 cards, 1 relic, 1 remove option, 1 transform/reforge option | Shop must never present card upgrade wording. |
| Rest options | `Game.Core/Data/m1-rest-options.json` | heal, upgrade, remove curse | Upgrade must be irreversible and visible. |
| Localization | `Game.Godot/Translations/en.csv`, `Game.Godot/Translations/zh-CN.csv` | All IDs above | No content item can ship without name, description, option, result, and blocked-state strings. |

### 3.3 Recommended Act 1 M1 Route

The first playable map should be intentionally small:

1. Floor 1: normal combat.
2. Floor 2: branch between event and normal combat.
3. Floor 3: reward or shop exposure after a completed node.
4. Floor 4: rest.
5. Floor 5: elite or normal combat.
6. Floor 6: boss or explicit M1 run-summary endpoint.

This provides the Slay-the-Spire-like rhythm without requiring full Act production.

### 3.4 Minimum Content Acceptance

The content set is playable only when:

- Every content stable ID referenced by map, reward, shop, event, rest, and combat can resolve to a definition.
- Every visible content definition has translation keys in both supported locales.
- At least one complete route can encounter Combat, Reward, Event, Shop, Rest, and a final outcome.
- RNG-affecting content generation uses named streams and does not advance from UI-only actions.
- Save/continue can restore at a node boundary without changing offered reward/shop/event choices.

## 4. Player Feedback And Failure Fallbacks

### 4.1 Feedback Files And Locations

| Feedback Area | Required Path | Requirement |
| --- | --- | --- |
| Translation strings | `Game.Godot/Translations/en.csv`, `Game.Godot/Translations/zh-CN.csv` | Own all player-facing copy for invalid actions, blocked routes, missing save, event result, reward lock, shop denial, rest confirmation, and run summary. |
| Main menu feedback | `Game.Godot/Scenes/UI/MainMenu.tscn`, `Game.Godot/Scripts/UI/MainMenu.cs` | Continue disabled or denied must explain why and tell the player what to do next. |
| Map feedback | `Game.Godot/Scenes/Map/Map.tscn`, `Game.Godot/Scripts/UI/MapScene.cs` | Locked node, invalid branch, completed node, and route return must be visible. |
| Combat feedback | `Game.Godot/Scenes/Combat.tscn`, `Game.Godot/Scripts/UI/CombatScene.cs` | Invalid target, insufficient energy, accepted command, enemy intent, and result summary must be visible without logs. |
| Reward feedback | `Game.Godot/Scenes/Reward.tscn`, `Game.Godot/Scripts/RewardScene.gd` | Offer lock, already-taken offer, skip, and confirm lock must be visible. |
| Shop feedback | `Game.Godot/Scenes/Shop.tscn`, `Game.Godot/Scripts/UI/ShopScene.cs` | Insufficient gold, duplicate purchase, invalid offer, remove/transform result, and leave route must be visible. |
| Rest feedback | `Game.Godot/Scenes/Rest.tscn`, `Game.Godot/Scripts/UI/RestScene.gd` | Heal amount, upgrade irreversibility, missing target, curse removal result, and return route must be visible. |
| Event feedback | `Game.Godot/Scenes/Event.tscn`, `Game.Godot/Scripts/UI/EventScene.cs` | Cost preview, invalid option, chosen option, result summary, HP/card/relic/gold changes, and route return must be visible. |
| Run summary | `Game.Core/Contracts/Save/RunSummaryMetadata.cs` plus the chosen Godot surface | Must show victory, defeat, abandoned, or M1 endpoint outcome with key run stats. |

### 4.2 Failure Fallback Rules

Use these rules consistently:

- Missing save: stay on MainMenu, show Continue blocked reason, keep New Run available.
- Save migration failure: block Continue, show recoverable/non-recoverable reason, do not mutate the save.
- Missing config/content: fail closed before entering a node that depends on the missing data; show the missing category, not an internal exception.
- Invalid map branch: keep player on Map, show blocked path reason, do not advance RNG or node state.
- Invalid combat action: keep combat state unchanged except visible feedback log.
- Reward/shop/event re-entry: preserve locked offers and previous committed choices.
- Audio missing: play no sound and optionally show no UI warning; never crash.
- Translation missing: fail visible-text smoke; in runtime, prefer readable fallback over raw key echo for playtest builds.

### 4.3 Feedback Acceptance

Player feedback is complete when the player can answer four questions on every M1 surface:

- What can I do now?
- Why is this action unavailable?
- What changed after my action?
- Where do I go next?

## 5. Playable Smoke / First-Run Smoke Timing

### 5.1 Can Smoke Start Before The Three Work Areas Are Finished?

Yes, but only as an incremental scaffold. A first-run smoke should be created early as a route skeleton, then become a hard gate after startup/config, minimum content data, and failure fallback copy are complete.

Do not wait until everything is finished to write the smoke. Waiting hides integration gaps. But do not treat an early route-only smoke as proof that M1 is playable.

### 5.2 Smoke Stages

| Stage | When To Add | What It Proves | Gate Strength |
| --- | --- | --- | --- |
| Stage A: boot smoke | Immediately | Godot starts `Main.tscn`, autoloads load, MainMenu appears | Hard once stable. |
| Stage B: route skeleton smoke | Before all content is final | New Run reaches DifficultySelect, CharacterSelect, Map, and one placeholder node | Soft until content exists. |
| Stage C: first-run smoke | After minimum content files exist | One deterministic M1 route visits Combat, Reward, Event/Shop/Rest, and returns to Map or summary | Hard for M1. |
| Stage D: recovery smoke | After failure fallback work | Continue blocked, invalid node/action, save restore, and locked offers behave visibly | Hard for playable claim. |

### 5.3 Recommended Test Locations

- Boot smoke: `Tests.Godot/tests/Scenes/Smoke/test_main_scene_smoke.gd`
- First-run smoke: `Tests.Godot/tests/Integration/test_m1_first_run_smoke.gd`
- Existing route evidence to extend: `Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd`
- Existing node route evidence to extend: `Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd`
- Existing visible text evidence: `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`
- Feedback and fallback evidence: `Tests.Godot/tests/Integration/test_m1_feedback_fallbacks.gd`
- Run summary evidence: `Tests.Godot/tests/UI/test_run_summary_surface.gd`
- Shop failure feedback and routing evidence: `Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd`
- MainMenu Continue blocked-message evidence: `Tests.Godot/tests/UI/test_main_menu_continue_blocked_message.gd`
- Existing focus evidence: `Tests.Godot/tests/Integration/test_m1_ui_focus_accessibility.gd`
- Python runner: `scripts/python/smoke_headless.py`

### 5.4 First-Run Smoke Acceptance

The final first-run smoke should:

- Start from `Game.Godot/Scenes/Main.tscn`.
- Use the real New Run path.
- Select Difficulty 1 and Warrior.
- Enter the Act 1 map.
- Resolve at least one Combat node.
- Take or skip a Reward.
- Visit at least one Event, Shop, or Rest node.
- Verify visible feedback after each action.
- Verify no raw translation keys are visible.
- Verify no fatal Godot errors are emitted.
- Write evidence under `logs/ci/<date>/smoke/**` or `logs/e2e/<date>/**`.

## 6. Immediate Work That Can Be Done Now

These tasks can start before balancing or art:

1. Add the recommended JSON content files under `Game.Core/Data/**` with schema-level validation and placeholder-balanced values.
2. Add translation keys for every M1 content item and fallback message in `Game.Godot/Translations/**`.
3. Add `Tests.Godot/tests/Integration/test_m1_first_run_smoke.gd` as a soft smoke that follows the intended path and marks missing content explicitly.
4. Promote the smoke to hard only after the minimum content set and failure fallback strings are present.
5. Add a setup validation script or gate that checks `project.godot`, content JSON presence, translation coverage, and smoke evidence paths before release/playtest.
