extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"


func _load_main_on_map_for_t84() -> Control:
	var main := MAIN_SCENE.instantiate() as Control
	add_child(auto_free(main))
	await get_tree().process_frame
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


func _extract_offer_ids(snapshot: Dictionary) -> Array[String]:
	var ids: Array[String] = []
	var offers_variant = snapshot.get("offers", [])
	if typeof(offers_variant) != TYPE_ARRAY:
		return ids
	for item in offers_variant:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		var card := item as Dictionary
		var card_id := str(card.get("id", "")).strip_edges()
		if not card_id.is_empty():
			ids.append(card_id)
	return ids


# acceptance: ACC:T84.6
# acceptance: ACC:T128.3
func test_first_entry_reward_offer_must_use_shared_pool_on_existing_route() -> void:
	var main := await _load_main_on_map_for_t84()
	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(str(complete_result.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	assert_bool(main.has_method("GetRewardOfferSnapshotForScene")).is_true()
	var snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var source := str(snapshot.get("source", ""))
	var context_id := str(snapshot.get("context_id", ""))
	var encounter_type := str(snapshot.get("encounter_type", ""))
	var ids := _extract_offer_ids(snapshot)
	var offers_variant = snapshot.get("offers", [])

	assert_str(source).is_equal("shared-card-pool")
	assert_str(context_id).contains("combat-01")
	assert_str(encounter_type).is_equal("normal")
	assert_int(ids.size()).is_equal(3)
	for card_id in ids:
		assert_bool(card_id.begins_with("card.")).is_true()

	assert_int((offers_variant as Array).size()).is_equal(3)
	for offer_data in (offers_variant as Array):
		assert_bool(typeof(offer_data) == TYPE_DICTIONARY).is_true()
		var offer := offer_data as Dictionary
		assert_bool(str(offer.get("name_key", "")).begins_with("card.")).is_true()
		assert_bool(str(offer.get("description_key", "")).begins_with("card.")).is_true()
		assert_str(str(offer.get("description", ""))).contains(".description")


# acceptance: ACC:T84.2
# acceptance: ACC:T128.7
func test_first_entry_reward_offer_should_be_deterministic_across_independent_entries_for_same_context() -> void:
	var main_a := await _load_main_on_map_for_t84()
	var start_a := main_a.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(start_a.get("ok", false))).is_true()
	var done_a := main_a.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(done_a.get("ok", false))).is_true()
	await get_tree().process_frame
	var snapshot_a := main_a.call("GetRewardOfferSnapshotForScene") as Dictionary
	var ids_a := _extract_offer_ids(snapshot_a)
	assert_int(ids_a.size()).is_equal(3)

	var main_b := await _load_main_on_map_for_t84()
	var start_b := main_b.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(start_b.get("ok", false))).is_true()
	var done_b := main_b.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(done_b.get("ok", false))).is_true()
	await get_tree().process_frame
	var snapshot_b := main_b.call("GetRewardOfferSnapshotForScene") as Dictionary
	var ids_b := _extract_offer_ids(snapshot_b)
	assert_int(ids_b.size()).is_equal(3)

	assert_array(ids_b).is_equal(ids_a)


# acceptance: ACC:T84.1
func test_first_entry_reward_offer_for_opening_combat_is_two_attacks_and_one_defense() -> void:
	var main := await _load_main_on_map_for_t84()
	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(str(complete_result.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	var snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var offers_variant = snapshot.get("offers", [])
	assert_bool(typeof(offers_variant) == TYPE_ARRAY).is_true()
	var offers := offers_variant as Array
	assert_int(offers.size()).is_equal(3)

	var expected_ids := [
		"card.warrior.heavy_strike",
		"card.warrior.cleave",
		"card.warrior.defend"
	]
	var actual_ids: Array[String] = []
	for offer_variant in offers:
		assert_bool(typeof(offer_variant) == TYPE_DICTIONARY).is_true()
		var offer := offer_variant as Dictionary
		actual_ids.append(str(offer.get("id", "")).strip_edges())

	assert_array(actual_ids).is_equal(expected_ids)
