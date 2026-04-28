extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")

const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"

var _bus: Node


func before() -> void:
    _bus = EVENT_BUS_SCRIPT.new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))


func _load_main_on_map() -> Control:
    var main := MAIN_SCENE.instantiate() as Control
    add_child(auto_free(main))
    await get_tree().process_frame

    var nav := main.get_node_or_null("ScreenNavigator")
    if nav != null:
        nav.UseFadeTransition = false
        if nav.has_method("ClearRouteHistoryForTest"):
            nav.call("ClearRouteHistoryForTest")
        nav.call("SwitchTo", MAP_SCENE)
    await get_tree().process_frame

    if main.has_method("ResetMapRouteProgressForTest"):
        main.call("ResetMapRouteProgressForTest")
    return main


func _route_history(main: Control) -> Array[String]:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetRouteHistoryForTest"):
        return []

    var route_variant = nav.call("GetRouteHistoryForTest")
    if route_variant == null:
        return []

    var history: Array[String] = []
    for item in route_variant:
        history.append(str(item))
    return history


func _current_scene_path(main: Control) -> String:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
        return ""
    return str(nav.call("GetCurrentScenePathForTest"))


func _current_scene_instance(main: Control):
    var root := main.get_node_or_null("ScreenRoot")
    if root == null:
        return null
    if root.get_child_count() == 0:
        return null
    return root.get_child(root.get_child_count() - 1)


func _start_and_complete_encounter(main: Control, node_id: String, node_type: String) -> void:
    var enter_result := main.call("StartMapNodeRouteForTest", node_id, node_type, true, "") as Dictionary
    assert_bool(bool(enter_result.get("ok", false))).is_true()
    assert_str(str(enter_result.get("scene_path", ""))).is_equal(node_type == "combat" ? COMBAT_SCENE : EVENT_SCENE)

    var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
    assert_bool(bool(complete_result.get("ok", false))).is_true()
    await get_tree().process_frame


func _resolve_reward_once(main: Control, action: String) -> Dictionary:
    if main.has_method("ResolveRewardForTest"):
        var result_variant = main.call("ResolveRewardForTest", action)
        if typeof(result_variant) == TYPE_DICTIONARY:
            return result_variant as Dictionary
        if typeof(result_variant) == TYPE_BOOL:
            return {"ok": bool(result_variant), "reason": "", "source": "main-bool"}
        return {"ok": false, "reason": "invalid-main-result", "source": "main"}

    var reward_scene = _current_scene_instance(main)
    if reward_scene == null:
        return {"ok": false, "reason": "reward-scene-missing", "source": "scene"}

    var normalized := action.strip_edges().to_lower()
    if normalized == "confirm":
        if reward_scene.has_method("SelectChoiceForTest"):
            reward_scene.call("SelectChoiceForTest", 0)
        elif reward_scene.has_method("SelectOptionForTest"):
            reward_scene.call("SelectOptionForTest", "reward_card_1")

        if reward_scene.has_method("ConfirmSelectedForTest"):
            return {"ok": bool(reward_scene.call("ConfirmSelectedForTest")), "reason": "", "source": "scene"}
        if reward_scene.has_method("ConfirmForTest"):
            return {"ok": bool(reward_scene.call("ConfirmForTest")), "reason": "", "source": "scene"}
        return {"ok": false, "reason": "confirm-hook-missing", "source": "scene"}

    if normalized == "skip":
        if reward_scene.has_method("SkipForTest"):
            return {"ok": bool(reward_scene.call("SkipForTest")), "reason": "", "source": "scene"}
        if reward_scene.has_method("SkipRewardForTest"):
            return {"ok": bool(reward_scene.call("SkipRewardForTest")), "reason": "", "source": "scene"}
        return {"ok": false, "reason": "skip-hook-missing", "source": "scene"}

    return {"ok": false, "reason": "unsupported-action", "source": "test"}


func _assert_reward_scene_interaction_surface(main: Control) -> void:
    var reward_scene = _current_scene_instance(main)
    assert_object(reward_scene).is_not_null()
    assert_bool(reward_scene.has_method("GetCardCountForTest")).is_true()
    assert_bool(reward_scene.has_method("GetFeedbackForTest")).is_true()
    assert_bool(reward_scene.has_method("SelectChoiceForTest")).is_true()
    assert_bool(reward_scene.has_method("ConfirmSelectedForTest")).is_true()
    assert_bool(reward_scene.has_method("SkipForTest")).is_true()
    assert_int(int(reward_scene.call("GetCardCountForTest"))).is_equal(3)

    var select_ok := bool(reward_scene.call("SelectChoiceForTest", 0))
    assert_bool(select_ok).is_true()
    var confirm_ok := bool(reward_scene.call("ConfirmSelectedForTest"))
    assert_bool(confirm_ok).is_true()
    assert_str(str(reward_scene.call("GetFeedbackForTest"))).is_equal("Reward confirmed.")


func _contains_non_gameplay_route_target(history: Array[String]) -> bool:
    for path in history:
        if path == DEMO_SCENE:
            return true
        if path.find("/Examples/") >= 0:
            return true
        if path.find("Tests.Godot") >= 0:
            return true
    return false


# acceptance: ACC:T61.1
# RED-FIRST: this fails until encounter completion routes into a real standalone Reward scene asset.
func test_combat_completion_routes_to_real_reward_scene_asset_not_placeholder_or_harness() -> void:
    var main := await _load_main_on_map()

    assert_bool(ResourceLoader.exists(REWARD_SCENE)).is_true()

    await _start_and_complete_encounter(main, "combat-01", "combat")
    var history := _route_history(main)

    assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
    assert_bool(history.has(REWARD_SCENE)).is_true()
    assert_bool(_contains_non_gameplay_route_target(history)).is_false()
    _assert_reward_scene_interaction_surface(main)


# acceptance: ACC:T61.2
# acceptance: ACC:T85.4
# RED-FIRST: this fails until Reward confirm resolves exactly once and returns to Map.
func test_confirm_from_reward_resolves_once_then_refuses_second_resolution_without_route_mutation() -> void:
    var main := await _load_main_on_map()

    await _start_and_complete_encounter(main, "combat-02", "combat")

    var first := _resolve_reward_once(main, "confirm")
    await get_tree().process_frame
    var history_after_first := _route_history(main)

    var second := _resolve_reward_once(main, "confirm")
    await get_tree().process_frame
    var history_after_second := _route_history(main)

    assert_bool(bool(first.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_bool(bool(second.get("ok", false))).is_false()
    assert_int(history_after_second.size()).is_equal(history_after_first.size())


# acceptance: ACC:T61.2
# acceptance: ACC:T85.4
func test_event_completion_then_skip_reward_resolves_once_and_second_skip_is_refused() -> void:
    var main := await _load_main_on_map()

    await _start_and_complete_encounter(main, "event-01", "event")

    var first := _resolve_reward_once(main, "skip")
    await get_tree().process_frame
    var history_after_first := _route_history(main)

    var second := _resolve_reward_once(main, "skip")
    await get_tree().process_frame
    var history_after_second := _route_history(main)

    assert_bool(bool(first.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_bool(bool(second.get("ok", false))).is_false()
    assert_int(history_after_second.size()).is_equal(history_after_first.size())


# acceptance: ACC:T61.4
# acceptance: ACC:T85.3
func test_reward_scene_exposes_three_cards_confirm_skip_and_visible_feedback() -> void:
    var main := await _load_main_on_map()
    await _start_and_complete_encounter(main, "combat-03", "combat")

    _assert_reward_scene_interaction_surface(main)

    var reward_scene = _current_scene_instance(main)
    var skip_ok := bool(reward_scene.call("SkipForTest"))
    assert_bool(skip_ok).is_true()
    assert_str(str(reward_scene.call("GetFeedbackForTest"))).is_equal("Reward skipped.")


# acceptance: ACC:T85.1
# acceptance: ACC:T85.2
# acceptance: ACC:T85.5
func test_reward_scene_confirm_gating_requires_selection_and_locks_after_resolution() -> void:
    var main := await _load_main_on_map()
    await _start_and_complete_encounter(main, "combat-04", "combat")

    var reward_scene = _current_scene_instance(main)
    assert_object(reward_scene).is_not_null()

    var confirm_without_selection := bool(reward_scene.call("ConfirmSelectedForTest"))
    assert_bool(confirm_without_selection).is_false()
    assert_int(int(reward_scene.call("GetSelectedIndexForTest"))).is_equal(-1)
    assert_bool(bool(reward_scene.call("IsLockedForTest"))).is_false()

    var select_first := bool(reward_scene.call("SelectChoiceForTest", 0))
    var selected_after_first := int(reward_scene.call("GetSelectedIndexForTest"))
    var select_second := bool(reward_scene.call("SelectChoiceForTest", 1))
    var selected_after_second := int(reward_scene.call("GetSelectedIndexForTest"))
    var can_confirm_old := bool(reward_scene.call("CanConfirmSelectedForTest", 0))
    var can_confirm_new := bool(reward_scene.call("CanConfirmSelectedForTest", 1))
    var confirm_selected := bool(reward_scene.call("ConfirmSelectedForTest"))
    var select_after_confirm := bool(reward_scene.call("SelectChoiceForTest", 1))
    var confirm_after_confirm := bool(reward_scene.call("ConfirmSelectedForTest"))

    assert_bool(select_first).is_true()
    assert_int(selected_after_first).is_equal(0)
    assert_bool(select_second).is_true()
    assert_int(selected_after_second).is_equal(1)
    assert_bool(can_confirm_old).is_false()
    assert_bool(can_confirm_new).is_true()
    assert_bool(confirm_selected).is_true()
    assert_bool(select_after_confirm).is_false()
    assert_bool(confirm_after_confirm).is_false()
    assert_bool(bool(reward_scene.call("IsLockedForTest"))).is_true()


# acceptance: ACC:T85.4
func test_reward_scene_skip_locks_reward_surface_and_blocks_late_confirm() -> void:
    var main := await _load_main_on_map()
    await _start_and_complete_encounter(main, "event-04", "event")

    var reward_scene = _current_scene_instance(main)
    assert_object(reward_scene).is_not_null()

    var selected := bool(reward_scene.call("SelectChoiceForTest", 0))
    var skipped := bool(reward_scene.call("SkipForTest"))
    var confirm_after_skip := bool(reward_scene.call("ConfirmSelectedForTest"))
    var select_after_skip := bool(reward_scene.call("SelectChoiceForTest", 1))

    assert_bool(selected).is_true()
    assert_bool(skipped).is_true()
    assert_bool(confirm_after_skip).is_false()
    assert_bool(select_after_skip).is_false()
    assert_bool(bool(reward_scene.call("IsLockedForTest"))).is_true()


# acceptance: ACC:T85.5
func test_reward_resolution_does_not_mutate_run_hp_or_gold_within_selection_phase_scope() -> void:
    var main := await _load_main_on_map()
    await _start_and_complete_encounter(main, "combat-05", "combat")

    assert_bool(main.has_method("GetRunStateForTest")).is_true()
    var before_state := main.call("GetRunStateForTest") as Dictionary
    var hp_before := int(before_state.get("hp", -1))
    var gold_before := int(before_state.get("gold", -1))
    var score_before := int(before_state.get("score", -1))

    var first := _resolve_reward_once(main, "confirm")
    await get_tree().process_frame

    assert_bool(bool(first.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)

    var after_state := main.call("GetRunStateForTest") as Dictionary
    assert_int(int(after_state.get("hp", -1))).is_equal(hp_before)
    assert_int(int(after_state.get("gold", -1))).is_equal(gold_before)
    assert_int(int(after_state.get("score", -1))).is_equal(score_before)


# acceptance: ACC:T61.5
# acceptance: ACC:T85.7
func test_reenter_reward_does_not_refresh_locked_offer_and_illegal_action_is_rejected() -> void:
    var main := await _load_main_on_map()

    await _start_and_complete_encounter(main, "event-02", "event")
    var illegal := _resolve_reward_once(main, "hack")
    assert_bool(bool(illegal.get("ok", false))).is_false()
    assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)

    var first_skip := _resolve_reward_once(main, "skip")
    await get_tree().process_frame
    assert_bool(bool(first_skip.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)

    await _start_and_complete_encounter(main, "event-03", "event")
    var reward_scene = _current_scene_instance(main)
    assert_int(int(reward_scene.call("GetCardCountForTest"))).is_equal(3)
