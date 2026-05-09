---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 测试策略（M1）
Status: Draft
ADR-Refs:
  - ADR-0025-godot-test-strategy
  - ADR-0005-quality-gates
  - ADR-0032-save-resume-determinism
  - ADR-0033-card-identity-and-forms
ADRs:
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
  - Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0050AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs
  - Tests.Godot/tests/Adapters/Security/test_continue_gate_recoverability.gd
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


## 7. Task14 Test-Refs
- Task: `T14 / GM-0114`
- Test-Refs:
  - `Tests.Godot/tests/Tasks/test_task0014_acceptance.gd`
  - `Tests.Godot/tests/UI/test_main_menu_scene.gd`
  - `Tests.Godot/tests/Integration/test_main_menu_new_run_overwrite_cancel.gd`
  - `Tests.Godot/tests/UI/test_main_menu_confirm_dialog_focus.gd`
  - `Tests.Godot/tests/UI/test_main_menu_translations.gd`
  - `Tests.Godot/tests/UI/test_main_menu_events.gd`
- Gate focus:
  - Main menu scene loads and remains visible
  - New Run/Continue/Quit flow checks are covered
  - Visible UI text is resolved from translations
  - Traceability includes ADR-0032 and ADR-0010

## 8. Task16 Test-Refs
- Task: `T16 / GM-0116`
- Test-Refs:
  - `Tests.Godot/tests/Tasks/test_task0016_acceptance.gd`
  - `Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_warrior_summary.gd`
  - `Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_locked_characters_unselectable.gd`
  - `Tests.Godot/tests/UI/test_settings_locale.gd`
  - `Game.Core.Tests/Tasks/Task16RunCharacterSelectedContractTests.cs`
- Gate focus:
  - only Warrior stays selectable; mage/rogue remain locked with `ui.character.not_open`
  - scene `res://Game.Godot/Scenes/UI/CharacterSelect.tscn` loads and supports Warrior selection flow
  - warrior summary stays at three visible localized lines (`rage_buff`, `power_window`, `cost_burst`)


## 9. Task59-69 UI Wiring Test-Refs
- T59 / GM-0159:
  - `Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd`
  - `Tests.Godot/tests/Tasks/test_task0014_acceptance.gd`
  - `Tests.Godot/tests/Tasks/test_task0015_acceptance.gd`
  - `Tests.Godot/tests/Tasks/test_task0016_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0059AcceptanceTests.cs`
- T60 / GM-0160:
  - `Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd`
  - `Tests.Godot/tests/Integration/test_map_navigation_state_transitions.gd`
  - `Tests.Godot/tests/Tasks/test_task0042_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0060AcceptanceTests.cs`
- T61 / GM-0161:
  - `Tests.Godot/tests/Scenes/Reward/test_reward_scene_three_cards_rendered.gd`
  - `Tests.Godot/tests/Scenes/Reward/test_reward_scene_route_roundtrip.gd`
  - `Tests.Godot/tests/Integration/test_reward_offer_lock_persist_reenter.gd`
  - `Game.Core.Tests/Tasks/Task0061AcceptanceTests.cs`
- T62 / GM-0162:
  - `Tests.Godot/tests/Scenes/Rest/test_rest_scene_route_roundtrip.gd`
  - `Tests.Godot/tests/Scenes/Rest/test_rest_upgrade_confirmation_irreversible.gd`
  - `Tests.Godot/tests/Tasks/test_task0021_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0062AcceptanceTests.cs`
- T63 / GM-0163:
  - `Tests.Godot/tests/UI/test_main_menu_continue_blocked_message.gd`
  - `Tests.Godot/tests/Tasks/test_task0014_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0037AcceptanceTests.cs`
  - `Game.Core.Tests/Tasks/Task0050AcceptanceTests.cs`
  - `Game.Core.Tests/Tasks/Task0063AcceptanceTests.cs`
- T64 / GM-0164:
  - `Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd`
  - `Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd`
  - `Tests.Godot/tests/Tasks/test_task0041_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0064AcceptanceTests.cs`
- T65 / GM-0165:
  - `Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd`
  - `Tests.Godot/tests/Tasks/test_task0023_acceptance.gd`
  - `Tests.Godot/tests/Tasks/test_task0039_acceptance.gd`
  - `Tests.Godot/tests/UI/test_reward_ui_translations.gd`
  - `Game.Core.Tests/Tasks/Task0065AcceptanceTests.cs`
- T66 / GM-0166:
  - `Tests.Godot/tests/UI/test_run_summary_surface.gd`
  - `Tests.Godot/tests/UI/test_hud_scene.gd`
  - `Tests.Godot/tests/Tasks/test_task0045_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0066AcceptanceTests.cs`
- T67 / GM-0167:
  - `Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd`
  - `Tests.Godot/tests/Tasks/test_task0020_acceptance.gd`
  - `Tests.Godot/tests/Integration/test_reward_shop_event_resume_determinism.gd`
  - `Game.Core.Tests/Tasks/Task0067AcceptanceTests.cs`
- T68 / GM-0168:
  - `Tests.Godot/tests/UI/A11y/test_button_invokable.gd`
  - `Tests.Godot/tests/UI/A11y/test_focus_cycle.gd`
  - `Tests.Godot/tests/UI/A11y/test_visible_labels.gd`
  - `Tests.Godot/tests/Integration/test_m1_ui_focus_accessibility.gd`
  - `Game.Core.Tests/Tasks/Task0068AcceptanceTests.cs`
- T69 / GM-0169:
  - `Tests.Godot/tests/Scenes/Event/test_event_scene_result_feedback.gd`
  - `Tests.Godot/tests/Scenes/Event/test_event_scene_hp_loss_cost_applies_immediately.gd`
  - `Tests.Godot/tests/Scenes/Event/test_event_scene_curse_card_cost_applies_immediately.gd`
  - `Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd`
  - `Game.Core.Tests/Tasks/Task0069AcceptanceTests.cs`

## 10. Task70-116 Runtime Closure Test Baseline
T70-T116 stay inside the same M1 verification envelope, but they expand it from basic UI wiring into runtime-closure and replay-closure validation.

### 10.1 Runtime Promotion Focus
The following areas now require explicit verification before the corresponding task can be marked done:
- Combat runtime handoff from scene-local placeholders to shared Core services.
- Reward generation, confirm, skip, and re-entry lock stability.
- Map route generation from `ActConfig` instead of scene-local fixed buttons.
- Continue restore into real route boundaries and locked-surface replay.
- Settlement persistence and replay evidence from stored run data.
- Enemy runtime instantiation and invalid-definition fallback.
- Relic, powers, and later potions entering the same deterministic trigger path.

### 10.2 Minimum Test Shape
For T70-T116, acceptance should normally include a mix of:
- Core tests that prove rule promotion or contract-boundary behavior without Godot.
- Godot scene or integration tests that prove the player-facing surface now consumes the shared runtime path.
- Resume/re-entry tests when the task changes Reward, Shop, Event, Continue, or settlement ownership.
- Contract-ref and traceability checks when task metadata or public contract baselines are updated.

### 10.3 Review-Governance Tasks
T102, T103, T104, T108, T109, and T112 are Chapter 6 split/governance tasks. They do not add new player features by themselves, but their acceptance must still verify:
- narrowed review scope still covers the intended runtime boundary
- no previous acceptance ref was silently dropped
- `summary.json`, repair guidance, and task refs still point to the same M1 slice evidence

### 10.4 Contract Drift Guard
If a T70-T116 task updates `contractRefs`, test evidence must show one of these is true:
- the refs now point to existing `EventTypes` constants and corresponding contract files, or
- the same change added the missing contract baseline under `Game.Core/Contracts`

Task metadata must not be accepted when it references placeholder event names that have no corresponding contract baseline.

### 10.5 Phase 0-2 Decision For Test And Contract Baseline
The current Phase 0-2 review result for `T70-T116` is:
- overlay documents must be kept in sync because these tasks expanded the runtime-closure scope of M1
- tests may point at existing contract baselines or future contract promotion requirements, but they must not assume placeholder task metadata is already canonical contract truth
- new `Game.Core/Contracts` files are only required when implementation in the selected task actually promotes a new public contract
- potion-related tests must continue to treat potion contracts as future work until `T77` or `T111` implementation lands with real contract files and `EventTypes` constants

