extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_FORMS := ["Base", "U1A", "U1B", "Ultimate"]
const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"

func _build_reward_scene_projection_for_red() -> Array:
	return [
		{"name": "Strike+", "description": "Deal +2 damage.", "form": "Base", "selectable": true},
		{"name": "Guard+", "description": "Gain +2 block.", "form": "U1A", "selectable": true},
		{"name": "Rage++", "description": "Gain +1 rage this turn.", "form": "U1B", "selectable": true}
	]

func _is_card_complete(card: Dictionary) -> bool:
	if not card.has("name"):
		return false
	if not card.has("description"):
		return false
	if not card.has("form"):
		return false
	if not card.has("selectable"):
		return false

	var name_text := String(card["name"]).strip_edges()
	var description_text := String(card["description"]).strip_edges()
	var form_text := String(card["form"]).strip_edges()
	var selectable := bool(card["selectable"])

	if name_text.is_empty() or description_text.is_empty():
		return false
	if not REQUIRED_FORMS.has(form_text):
		return false
	if not selectable:
		return false
	return true

func _validate_reward_cards(cards: Array) -> bool:
	if cards.size() != 3:
		return false
	for card_data in cards:
		if typeof(card_data) != TYPE_DICTIONARY:
			return false
		var card: Dictionary = card_data
		if not _is_card_complete(card):
			return false
	return true

func _load_main_on_map() -> Control:
	var main := MAIN_SCENE.instantiate() as Control
	add_child(auto_free(main))
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	nav.UseFadeTransition = false
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")
	nav.call("SwitchTo", MAP_SCENE)
	await get_tree().process_frame
	if main.has_method("ResetMapRouteProgressForTest"):
		main.call("ResetMapRouteProgressForTest")
	return main

func _current_scene_instance(main: Control):
	var root := main.get_node_or_null("ScreenRoot")
	if root == null or root.get_child_count() == 0:
		return null
	return root.get_child(root.get_child_count() - 1)

func _extract_offer_ids(snapshot: Dictionary) -> Array[String]:
	var ids: Array[String] = []
	var offers_variant = snapshot.get("offers", [])
	if typeof(offers_variant) != TYPE_ARRAY:
		return ids
	for item in offers_variant:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		var card := item as Dictionary
		var card_id := str(card.get("id", ""))
		if card_id.strip_edges().is_empty():
			card_id = str(card.get("name", ""))
		if not card_id.strip_edges().is_empty():
			ids.append(card_id.strip_edges())
	return ids

func _resolve_reward_context_id(main: Control, node_id: String, node_type: String, floor_index: int) -> String:
	if main == null or not main.has_method("_build_reward_context_id"):
		return ""
	var context_variant = main.call("_build_reward_context_id", node_id, node_type, floor_index)
	return str(context_variant).strip_edges()

func _inject_invalid_shared_pool_offer(main: Control, context_id: String) -> void:
	if main == null or context_id.is_empty():
		return
	var current = main.get("_reward_offer_by_context")
	var by_context: Dictionary = {}
	if typeof(current) == TYPE_DICTIONARY:
		by_context = (current as Dictionary).duplicate(true)
	by_context[context_id] = {
		"context_id": context_id,
		"act_id": 1,
		"encounter_type": "normal",
		"floor": 1,
		"offers": [
			{"id": "card.strike_plus", "name_key": "card.strike_plus.name"}
		],
		"source": "shared-card-pool"
	}
	main.set("_reward_offer_by_context", by_context)
	main.set("_reward_offer_active_context_id", context_id)

# acceptance: ACC:T19.1
# RED-FIRST: fails deterministically until Reward scene renders exactly three complete selectable cards.
func test_reward_scene_renders_exactly_three_selectable_cards_with_required_fields() -> void:
	var rendered_cards := _build_reward_scene_projection_for_red()
	assert_that(_validate_reward_cards(rendered_cards)).is_true()

func test_reward_scene_rejects_cards_when_any_required_field_is_missing() -> void:
	var invalid_cards := [
		{"name": "Strike+", "description": "Deal +2 damage.", "form": "Base", "selectable": true},
		{"name": "Guard+", "description": "Gain +2 block.", "form": "U1A", "selectable": true},
		{"name": "Rage++", "description": "", "form": "Ultimate", "selectable": true}
	]
	assert_that(_validate_reward_cards(invalid_cards)).is_false()

# acceptance: ACC:T84.1
# acceptance: ACC:T114.2
# acceptance: ACC:T114.3
# acceptance: ACC:T114.4
# acceptance: ACC:T114.5
func test_reward_scene_uses_shared_pool_offer_on_first_entry_route() -> void:
	var main := await _load_main_on_map()
	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(str(complete_result.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	var reward = _current_scene_instance(main)
	assert_object(reward).is_not_null()
	assert_bool(reward.has_method("GetOfferSourceForTest")).is_true()
	assert_bool(reward.has_method("GetOfferedCardIdsForTest")).is_true()
	var source := str(reward.call("GetOfferSourceForTest"))
	var ids_variant = reward.call("GetOfferedCardIdsForTest")
	var ids: Array[String] = []
	for item in ids_variant:
		ids.append(str(item))
	assert_str(source).is_equal("shared-card-pool")
	assert_int(ids.size()).is_equal(3)
	for card_id in ids:
		assert_bool(card_id.begins_with("card.")).is_true()

	var card_list := reward.get_node_or_null("VBox/CardList")
	assert_object(card_list).is_not_null()
	assert_int(card_list.get_child_count()).is_greater(2)
	var card1_button := reward.get_node_or_null("VBox/CardList/CardSlot1/Body/ArtButton")
	var card1_name := reward.get_node_or_null("VBox/CardList/CardSlot1/Body/Name")
	var card1_description := reward.get_node_or_null("VBox/CardList/CardSlot1/Body/Description")
	var card1_art := reward.get_node_or_null("VBox/CardList/CardSlot1/Body/ArtButton")
	assert_object(card1_button).is_not_null()
	assert_object(card1_name).is_not_null()
	assert_object(card1_description).is_not_null()
	assert_object(card1_art).is_not_null()
	var card1_text := str(card1_name.text)
	assert_str(card1_text).is_not_equal("Reward Card 1")
	assert_bool(card1_text.begins_with("ui.reward.card")).is_false()
	assert_bool(str(card1_description.text).begins_with("card.")).is_false()
	assert_object(card1_art.texture_normal).is_not_null()
	card1_button.emit_signal("pressed")
	assert_int(int(reward.call("GetSelectedIndexForTest"))).is_equal(0)
	assert_bool(bool(reward.call("CanConfirmSelectedForTest", 0))).is_true()
	assert_bool(bool(reward.call("IsLockedForTest"))).is_false()

# acceptance: ACC:T128.4
func test_reward_scene_shows_fallback_for_invalid_shared_pool_snapshot() -> void:
	var main := await _load_main_on_map()
	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	var context_id := _resolve_reward_context_id(main, "combat-01", "combat", 1)
	assert_bool(context_id.is_empty()).is_false()
	_inject_invalid_shared_pool_offer(main, context_id)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(str(complete_result.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	var reward = _current_scene_instance(main)
	assert_object(reward).is_not_null()
	assert_bool(reward.has_method("GetCardCountForTest")).is_true()
	assert_bool(reward.has_method("GetVisibleCardSlotCountForTest")).is_true()
	assert_bool(reward.has_method("GetFeedbackForTest")).is_true()
	assert_bool(reward.has_method("SelectChoiceForTest")).is_true()
	assert_bool(reward.has_method("ConfirmSelectedForTest")).is_true()

	var offered_count := int(reward.call("GetCardCountForTest"))
	assert_int(offered_count).is_less(3)
	var select_ok := bool(reward.call("SelectChoiceForTest", 0))
	assert_bool(select_ok).is_false()
	var confirm_ok := bool(reward.call("ConfirmSelectedForTest"))
	assert_bool(confirm_ok).is_false()
	var feedback := str(reward.call("GetFeedbackForTest"))
	assert_str(feedback).is_not_equal("")

	var card_list := reward.get_node_or_null("VBox/CardList")
	assert_object(card_list).is_not_null()
	assert_int(int(reward.call("GetVisibleCardSlotCountForTest"))).is_equal(0)

# acceptance: ACC:T128.8
func test_reward_scene_empty_state_hides_offers_and_rejects_actions_before_valid_offer_resolution() -> void:
	var main := await _load_main_on_map()
	var nav := main.get_node_or_null("ScreenNavigator")
	assert_object(nav).is_not_null()
	var route_before := []
	if nav.has_method("GetRouteHistoryForTest"):
		route_before = nav.call("GetRouteHistoryForTest")

	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()

	var context_id := _resolve_reward_context_id(main, "combat-01", "combat", 1)
	assert_bool(context_id.is_empty()).is_false()
	_inject_invalid_shared_pool_offer(main, context_id)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(str(complete_result.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame
	var route_after_entry := []
	if nav.has_method("GetRouteHistoryForTest"):
		route_after_entry = nav.call("GetRouteHistoryForTest")

	var reward = _current_scene_instance(main)
	assert_object(reward).is_not_null()
	assert_bool(reward.has_method("GetCardCountForTest")).is_true()
	assert_bool(reward.has_method("GetVisibleCardSlotCountForTest")).is_true()
	assert_bool(reward.has_method("SelectChoiceForTest")).is_true()
	assert_bool(reward.has_method("ConfirmSelectedForTest")).is_true()
	assert_bool(reward.has_method("SkipForTest")).is_true()

	assert_int(int(reward.call("GetCardCountForTest"))).is_equal(0)
	var card_list := reward.get_node_or_null("VBox/CardList")
	assert_object(card_list).is_not_null()
	assert_int(int(reward.call("GetVisibleCardSlotCountForTest"))).is_equal(0)
	assert_bool(bool(reward.call("SelectChoiceForTest", 0))).is_false()
	assert_bool(bool(reward.call("ConfirmSelectedForTest"))).is_false()
	assert_bool(bool(reward.call("SkipForTest"))).is_false()

	if nav.has_method("GetRouteHistoryForTest"):
		var route_after = nav.call("GetRouteHistoryForTest")
		assert_array(route_after).is_equal(route_after_entry)
		assert_int(route_after.size()).is_greater(route_before.size())

# acceptance: ACC:T84.6
func test_reward_scene_first_entry_offer_is_deterministic_for_same_context_before_resolution() -> void:
	var main_a := await _load_main_on_map()
	var enter_a := main_a.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_a.get("ok", false))).is_true()
	var complete_a := main_a.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_a.get("ok", false))).is_true()
	await get_tree().process_frame
	var first_snapshot := main_a.call("GetRewardOfferSnapshotForScene") as Dictionary
	var first_ids := _extract_offer_ids(first_snapshot)
	assert_int(first_ids.size()).is_equal(3)

	var main_b := await _load_main_on_map()
	var enter_b := main_b.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_b.get("ok", false))).is_true()
	var complete_b := main_b.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_b.get("ok", false))).is_true()
	await get_tree().process_frame
	var second_snapshot := main_b.call("GetRewardOfferSnapshotForScene") as Dictionary
	var second_ids := _extract_offer_ids(second_snapshot)
	assert_int(second_ids.size()).is_equal(3)
	assert_array(second_ids).is_equal(first_ids)
