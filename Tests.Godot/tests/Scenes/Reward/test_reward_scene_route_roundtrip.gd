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
	TranslationServer.set_locale("en")

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

func _run_deck_ids(main: Control) -> Array[String]:
	assert_bool(main.has_method("GetRunDeckCardIdsForTest")).is_true()
	var variant = main.call("GetRunDeckCardIdsForTest")
	var ids: Array[String] = []
	if typeof(variant) != TYPE_ARRAY:
		return ids
	for item in variant:
		ids.append(str(item))
	return ids

func _run_state(main: Control) -> Dictionary:
	assert_bool(main.has_method("GetRunStateForTest")).is_true()
	var variant = main.call("GetRunStateForTest")
	return variant as Dictionary if typeof(variant) == TYPE_DICTIONARY else {}

func _current_scene_instance(main: Control):
	var root := main.get_node_or_null("ScreenRoot")
	if root == null or root.get_child_count() == 0:
		return null
	return root.get_child(root.get_child_count() - 1)

func _start_and_complete_encounter(main: Control, node_id: String, node_type: String) -> void:
	var enter_result := main.call("StartMapNodeRouteForTest", node_id, node_type, true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	var expected_scene := COMBAT_SCENE if node_type == "combat" else EVENT_SCENE
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(expected_scene)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	await get_tree().process_frame

func _resolve_reward_once(main: Control, action: String) -> Dictionary:
	var reward_scene = _current_scene_instance(main)
	if reward_scene == null:
		if main.has_method("ResolveRewardForTest"):
			var result_variant = main.call("ResolveRewardForTest", action)
			if typeof(result_variant) == TYPE_DICTIONARY:
				return result_variant as Dictionary
			if typeof(result_variant) == TYPE_BOOL:
				return {"ok": bool(result_variant), "reason": "", "source": "main-bool"}
			return {"ok": false, "reason": "invalid-main-result", "source": "main"}
		return {"ok": false, "reason": "reward-scene-missing", "source": "scene"}

	var normalized := action.strip_edges().to_lower()
	if normalized == "confirm":
		var selected_card_id := ""
		var selected_index := -1
		if reward_scene.has_method("GetSelectedIndexForTest"):
			selected_index = int(reward_scene.call("GetSelectedIndexForTest"))
		if reward_scene.has_method("GetOfferedCardIdsForTest"):
			var offered_ids = reward_scene.call("GetOfferedCardIdsForTest") as Array[String]
			if selected_index >= 0 and selected_index < offered_ids.size():
				selected_card_id = offered_ids[selected_index]
			elif offered_ids.size() > 0:
				selected_card_id = offered_ids[0]
		if selected_index < 0 and reward_scene.has_method("SelectChoiceForTest"):
			reward_scene.call("SelectChoiceForTest", 0)
			selected_index = 0
		if reward_scene.has_method("ConfirmSelectedForTest"):
			return {
				"ok": bool(reward_scene.call("ConfirmSelectedForTest")),
				"reason": "",
				"source": "scene",
				"selected_card_id": selected_card_id,
				"scene_path": _current_scene_path(main)
			}
		return {"ok": false, "reason": "confirm-hook-missing", "source": "scene"}

	if normalized == "skip":
		if reward_scene.has_method("SkipForTest"):
			return {"ok": bool(reward_scene.call("SkipForTest")), "reason": "", "source": "scene", "scene_path": _current_scene_path(main)}
		return {"ok": false, "reason": "skip-hook-missing", "source": "scene"}

	return {"ok": false, "reason": "unsupported-action", "source": "test"}

func _assert_reward_scene_surface(main: Control) -> void:
	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	assert_object(reward_scene.get_node_or_null("VBox/CardList")).is_not_null()
	assert_object(reward_scene.get_node_or_null("VBox/Actions")).is_not_null()
	assert_object(reward_scene.get_node_or_null("VBox/Actions/ConfirmButton")).is_not_null()
	assert_object(reward_scene.get_node_or_null("VBox/Actions/SkipButton")).is_not_null()
	assert_object(reward_scene.get_node_or_null("VBox/Feedback")).is_not_null()
	assert_object(reward_scene.get_node_or_null("RootMargin/VBox/RewardListScroll/RewardList")).is_not_null()

func _contains_non_gameplay_route_target(history: Array[String]) -> bool:
	for path in history:
		if path == DEMO_SCENE:
			return true
		if path.find("/Examples/") >= 0:
			return true
		if path.find("Tests.Godot") >= 0:
			return true
	return false

func _reward_entry_titles(reward_scene: Control) -> Array[String]:
	var titles: Array[String] = []
	var reward_list = reward_scene.get_node_or_null("RootMargin/VBox/RewardListScroll/RewardList")
	if reward_list == null:
		return titles
	for row in reward_list.get_children():
		if row is HBoxContainer and row.get_child_count() >= 2:
			var name_button := row.get_child(1)
			if name_button is Button:
				titles.append(str((name_button as Button).text).strip_edges())
	return titles

func _press_reward_row(reward_scene: Control, row_index: int) -> bool:
	var reward_list = reward_scene.get_node_or_null("RootMargin/VBox/RewardListScroll/RewardList")
	if reward_list == null:
		return false
	if row_index < 0 or row_index >= reward_list.get_child_count():
		return false
	var row = reward_list.get_child(row_index)
	if row.get_child_count() < 2:
		return false
	var name_button := row.get_child(1)
	if name_button is Button:
		(name_button as Button).emit_signal("pressed")
		return true
	return false

func _press_reward_row_with_title_fragment(reward_scene: Control, title_fragment: String) -> bool:
	var reward_list = reward_scene.get_node_or_null("RootMargin/VBox/RewardListScroll/RewardList")
	if reward_list == null:
		return false
	var needle := title_fragment.strip_edges().to_lower()
	for row in reward_list.get_children():
		if not (row is HBoxContainer) or row.get_child_count() < 2:
			continue
		var name_button := row.get_child(1)
		if not (name_button is Button):
			continue
		var text := str((name_button as Button).text).strip_edges().to_lower()
		if text.find(needle) < 0:
			continue
		(name_button as Button).emit_signal("pressed")
		return true
	return false

func _count_reward_rows(reward_scene: Control) -> int:
	var reward_list = reward_scene.get_node_or_null("RootMargin/VBox/RewardListScroll/RewardList")
	return 0 if reward_list == null else reward_list.get_child_count()

func _claim_first_card_choice_via_overlay(reward_scene: Control) -> bool:
	if not _press_reward_row_with_title_fragment(reward_scene, "card"):
		return false
	var overlay = reward_scene.get_node_or_null("CardChoiceOverlay")
	if overlay == null or not overlay.visible:
		return false
	var grid = reward_scene.get_node_or_null("CardChoiceOverlay/Shell/ChoiceVBox/ChoiceScroll/ChoiceGrid")
	if grid == null or grid.get_child_count() <= 0:
		return false
	var first_card = grid.get_child(0)
	if first_card is Button:
		(first_card as Button).emit_signal("pressed")
		return true
	return false

# acceptance: ACC:T61.1
# acceptance: ACC:T128.2
func test_combat_completion_routes_to_real_reward_scene_asset_not_placeholder_or_harness() -> void:
	var main := await _load_main_on_map()
	assert_bool(ResourceLoader.exists(REWARD_SCENE)).is_true()

	await _start_and_complete_encounter(main, "combat-01", "combat")
	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	_assert_reward_scene_surface(main)

	var history := _route_history(main)
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	assert_bool(history.has(REWARD_SCENE)).is_true()
	assert_bool(_contains_non_gameplay_route_target(history)).is_false()
	assert_int(int(reward_scene.call("GetCardCountForTest"))).is_equal(3)
	assert_int(_count_reward_rows(reward_scene)).is_equal(2)

# acceptance: ACC:T115.1
# acceptance: ACC:T128.5
func test_single_card_choice_reward_confirm_adds_one_card_and_returns_to_map() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-01", "combat")

	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	var offered_ids := reward_scene.call("GetOfferedCardIdsForTest") as Array[String]
	assert_int(offered_ids.size()).is_equal(3)
	var deck_before := _run_deck_ids(main)

	assert_bool(bool(reward_scene.call("SelectChoiceForTest", 1))).is_true()
	var confirm_result := _resolve_reward_once(main, "confirm")
	await get_tree().process_frame
	var deck_after := _run_deck_ids(main)

	assert_bool(bool(confirm_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(deck_after.size()).is_equal(deck_before.size() + 1)
	assert_str(deck_after[deck_after.size() - 1]).is_equal(offered_ids[1])

# acceptance: ACC:T115.1
func test_confirm_after_reselection_writes_final_selected_card_id_only_once() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-01", "combat")

	var reward_scene = _current_scene_instance(main)
	var offered_ids := reward_scene.call("GetOfferedCardIdsForTest") as Array[String]
	var deck_before := _run_deck_ids(main)

	assert_bool(bool(reward_scene.call("SelectChoiceForTest", 0))).is_true()
	assert_bool(bool(reward_scene.call("SelectChoiceForTest", 1))).is_true()
	assert_bool(bool(reward_scene.call("CanConfirmSelectedForTest", 0))).is_false()
	assert_bool(bool(reward_scene.call("CanConfirmSelectedForTest", 1))).is_true()

	var confirm_result := _resolve_reward_once(main, "confirm")
	await get_tree().process_frame
	var deck_after := _run_deck_ids(main)

	assert_bool(bool(confirm_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(deck_after.size()).is_equal(deck_before.size() + 1)
	assert_str(deck_after[deck_after.size() - 1]).is_equal(offered_ids[1])

# acceptance: ACC:T115.2
# acceptance: ACC:T128.6
func test_event_reward_skip_resolves_card_choice_without_deck_mutation_and_returns_to_map() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "event-02", "event")

	var deck_before := _run_deck_ids(main)
	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	assert_int(_count_reward_rows(reward_scene)).is_equal(3)

	var first := _resolve_reward_once(main, "skip")
	await get_tree().process_frame
	var deck_after := _run_deck_ids(main)

	assert_bool(bool(first.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	assert_array(deck_after).is_equal(deck_before)

# acceptance: ACC:T115.3
func test_multi_entry_reward_stays_on_reward_until_all_entries_are_resolved() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-02", "combat")

	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	var titles_before := _reward_entry_titles(reward_scene)
	assert_int(titles_before.size()).is_equal(4)

	var state_before := _run_state(main)
	var deck_before := _run_deck_ids(main)
	var claimed_card_ok := _claim_first_card_choice_via_overlay(reward_scene)
	assert_bool(claimed_card_ok).is_true()
	await get_tree().process_frame

	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	var state_after_card := _run_state(main)
	var reward_after_card = _current_scene_instance(main)
	assert_object(reward_after_card).is_not_null()
	assert_int(_count_reward_rows(reward_after_card)).is_equal(3)
	assert_int(_run_deck_ids(main).size()).is_equal(deck_before.size() + 1)
	assert_int(int(state_after_card.get("gold", -1))).is_equal(int(state_before.get("gold", -1)))

	assert_bool(_press_reward_row_with_title_fragment(reward_after_card, "gold")).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	var state_after_gold := _run_state(main)
	assert_int(int(state_after_gold.get("gold", -1))).is_greater(int(state_after_card.get("gold", -1)))

	var reward_after_gold = _current_scene_instance(main)
	assert_bool(_press_reward_row_with_title_fragment(reward_after_gold, "iron tonic")).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	var state_after_consumable := _run_state(main)
	var consumables_after = state_after_consumable.get("consumable_ids", [])
	assert_bool(typeof(consumables_after) == TYPE_ARRAY).is_true()
	assert_int((consumables_after as Array).size()).is_equal(1)

	var reward_after_consumable = _current_scene_instance(main)
	assert_bool(_press_reward_row_with_title_fragment(reward_after_consumable, "rare")).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	assert_int(_count_reward_rows(_current_scene_instance(main))).is_equal(1)

# acceptance: ACC:T85.1
# acceptance: ACC:T85.2
func test_reward_scene_confirm_gating_requires_selection_before_resolution() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-01", "combat")

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

	assert_bool(select_first).is_true()
	assert_int(selected_after_first).is_equal(0)
	assert_bool(select_second).is_true()
	assert_int(selected_after_second).is_equal(1)
	assert_bool(can_confirm_old).is_false()
	assert_bool(can_confirm_new).is_true()

# acceptance: ACC:T85.4
func test_reward_scene_skip_resolves_only_current_legacy_card_choice_and_keeps_route_open_when_entries_remain() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-01", "combat")

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
	assert_bool(bool(reward_scene.call("IsLockedForTest"))).is_false()
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	assert_int(_count_reward_rows(_current_scene_instance(main))).is_equal(1)

# acceptance: ACC:T85.5
func test_reward_resolution_does_not_mutate_run_hp_or_score_during_card_choice_claim() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-01", "combat")

	var before_state := _run_state(main)
	var hp_before := int(before_state.get("hp", -1))
	var gold_before := int(before_state.get("gold", -1))
	var score_before := int(before_state.get("score", -1))

	var first := _resolve_reward_once(main, "confirm")
	await get_tree().process_frame
	assert_bool(bool(first.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)

	var after_state := _run_state(main)
	assert_int(int(after_state.get("hp", -1))).is_equal(hp_before)
	assert_int(int(after_state.get("gold", -1))).is_equal(gold_before)
	assert_int(int(after_state.get("score", -1))).is_equal(score_before)

# acceptance: ACC:T128.7
# acceptance: ACC:T128.4
func test_illegal_action_is_rejected_without_route_or_deck_mutation() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "event-02", "event")

	var deck_before := _run_deck_ids(main)
	var history_before := _route_history(main)
	var illegal := _resolve_reward_once(main, "hack")
	var deck_after := _run_deck_ids(main)
	var history_after := _route_history(main)

	assert_bool(bool(illegal.get("ok", false))).is_false()
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	assert_array(deck_after).is_equal(deck_before)
	assert_array(history_after).is_equal(history_before)

func test_skip_all_button_skips_remaining_rewards_and_returns_to_map() -> void:
	var main := await _load_main_on_map()
	await _start_and_complete_encounter(main, "combat-02", "combat")

	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	var skip_all_button = reward_scene.get_node_or_null("RootMargin/VBox/RewardActions/SkipAllButton")
	assert_object(skip_all_button).is_not_null()
	assert_bool(skip_all_button is Button).is_true()

	(skip_all_button as Button).emit_signal("pressed")
	await get_tree().process_frame

	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
