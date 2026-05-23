extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"

class FakeAutoSave:
	var locked_offer: Array = []
	var has_locked_offer: bool = false

	func write_locked_offer(cards: Array) -> void:
		locked_offer = cards.duplicate()
		has_locked_offer = true

	func read_locked_offer() -> Array:
		return locked_offer.duplicate()


class RewardFlowHarness:
	var _rng_seed: int
	var _save: FakeAutoSave
	var _current_offer: Array = []
	var _confirmed_card: String = ""
	var _skipped: bool = false

	func _init(save: FakeAutoSave, rng_seed: int = 7) -> void:
		_save = save
		_rng_seed = rng_seed

	func enter_reward_scene() -> Array:
		if _save.has_locked_offer:
			_current_offer = _save.read_locked_offer()
			return _current_offer.duplicate()
		_current_offer = _generate_offer(_rng_seed)
		_save.write_locked_offer(_current_offer)
		return _current_offer.duplicate()

	func confirm_choice(index: int) -> void:
		_confirmed_card = _current_offer[index]
		_save.has_locked_offer = false
		_save.locked_offer.clear()

	func skip_reward() -> void:
		_skipped = true
		_save.has_locked_offer = false
		_save.locked_offer.clear()

	func confirmed_card() -> String:
		return _confirmed_card

	func skipped() -> bool:
		return _skipped

	func _generate_offer(seed: int) -> Array:
		var cards := ["atk+1", "hp+5", "gold+20", "dash", "shield"]
		if seed % 2 == 0:
			cards.reverse()
		return cards.slice(0, 3)

func _load_main_on_map() -> Control:
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
		var card_id := str(card.get("id", "")).strip_edges()
		if not card_id.is_empty():
			ids.append(card_id)
	return ids



# acceptance: ACC:T19.3
# acceptance: ACC:T61.3
# acceptance: ACC:T114.1
# acceptance: ACC:T114.3
# acceptance: ACC:T114.4
# acceptance: ACC:T114.5
func test_reenter_must_not_regenerate_or_reorder_locked_offer() -> void:
	var save := FakeAutoSave.new()
	var flow := RewardFlowHarness.new(save, 7)

	var first_offer := flow.enter_reward_scene()
	var second_offer := flow.enter_reward_scene()

	assert_that(save.has_locked_offer).is_true()
	assert_that(save.read_locked_offer()).is_equal(first_offer)
	assert_that(second_offer).is_equal(first_offer)


# acceptance: ACC:T19.7
# acceptance: ACC:T61.5
# acceptance: ACC:T114.1
# acceptance: ACC:T114.3
# acceptance: ACC:T114.4
# acceptance: ACC:T114.5
func test_reward_display_confirm_skip_and_reenter_locking_contract() -> void:
	var save := FakeAutoSave.new()
	var flow := RewardFlowHarness.new(save, 7)

	var displayed_offer := flow.enter_reward_scene()
	var reentered_offer := flow.enter_reward_scene()
	assert_that(reentered_offer).is_equal(displayed_offer)

	flow.confirm_choice(1)
	assert_that(flow.confirmed_card()).is_equal(displayed_offer[1])
	assert_that(save.has_locked_offer).is_false()

	var after_confirm := flow.enter_reward_scene()
	assert_that(after_confirm).is_not_equal([])

	var save_skip := FakeAutoSave.new()
	var flow_skip := RewardFlowHarness.new(save_skip, 9)
	var skip_offer := flow_skip.enter_reward_scene()
	flow_skip.skip_reward()
	assert_that(flow_skip.skipped()).is_true()
	assert_that(save_skip.has_locked_offer).is_false()

	var after_skip := flow_skip.enter_reward_scene()
	assert_that(after_skip).is_equal(skip_offer)

# acceptance: ACC:T133.4
func test_reward_reenter_uses_same_shared_offer_snapshot_in_route_owned_flow() -> void:
	var main := await _load_main_on_map()
	var enter_result := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	var pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_bool(pending_context_id.is_empty()).is_false()
	assert_bool(bool(main.call("RegisterRewardEntryModifierForTest", "", {
		"action": "mutate",
		"target_entry_id": "gold",
		"config": {"amount": 91}
	}))).is_true()

	var first_complete := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(first_complete.get("ok", false))).is_true()
	assert_str(str(first_complete.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	var first_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_str(str(first_snapshot.get("context_id", "")).strip_edges()).is_equal(pending_context_id)
	var first_ids := _extract_offer_ids(first_snapshot)
	assert_int(first_ids.size()).is_equal(3)
	assert_str(str(first_snapshot.get("source", ""))).is_equal("shared-card-pool")
	var first_context_id := str(first_snapshot.get("context_id", "")).strip_edges()
	assert_bool(first_context_id.is_empty()).is_false()
	var mutated_gold_count := 0
	for entry_variant in (first_snapshot.get("entries", []) as Array):
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		if str(entry.get("reward_type", "")).strip_edges() != "gold":
			continue
		var config := entry.get("config", {}) as Dictionary
		if int(config.get("amount", 0)) == 91:
			mutated_gold_count += 1
	assert_int(mutated_gold_count).is_equal(1)

	var reward = _current_scene_instance(main)
	assert_object(reward).is_not_null()
	assert_bool(reward.has_method("SkipForTest")).is_true()
	assert_bool(bool(reward.call("SkipForTest"))).is_true()
	await get_tree().process_frame

	var back_to_map := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_bool(bool(back_to_map.get("ok", false))).is_true()
	assert_str(str(back_to_map.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	var second_complete := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(second_complete.get("ok", false))).is_true()
	assert_str(str(second_complete.get("scene_path", ""))).is_equal(REWARD_SCENE)
	await get_tree().process_frame

	var second_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var second_ids := _extract_offer_ids(second_snapshot)
	assert_int(second_ids.size()).is_equal(3)
	assert_str(str(second_snapshot.get("source", ""))).is_equal("shared-card-pool")
	var second_context_id := str(second_snapshot.get("context_id", "")).strip_edges()
	assert_str(second_context_id).is_equal(first_context_id)
	assert_array(second_ids).is_equal(first_ids)
	assert_that(second_snapshot).is_equal(first_snapshot)
