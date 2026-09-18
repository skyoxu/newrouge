extends "res://tests/Integration/Mvg/reward_fixture.gd"

# acceptance: ACC:T115.1
# acceptance: ACC:T128.5
func test_engine_action_claims_one_card_then_remaining_reward_returns_to_map() -> void:
	var reward := _reward()
	var rows := reward.get_node(LIST)
	var entries: Array = reward.call("GetVisibleRewardEntriesForTest")
	var card_index := -1
	for index in range(entries.size()):
		if str(entries[index].get("reward_type", "")).ends_with("_card_choice"):
			card_index = index
	assert_int(card_index).is_greater_equal(0)
	if card_index < 0:
		return
	var open_button := rows.get_child(card_index).get_child(1) as Button
	if OS.get_environment("MVG_INPUT_CHALLENGE") == "disconnect-reward-input":
		for connection in open_button.pressed.get_connections():
			open_button.pressed.disconnect(connection["callable"])
	var before := _deck().duplicate()
	assert_bool(await _activate(open_button)).is_true()
	var opened := await _wait_for(func() -> bool: return reward.get_node("CardChoiceOverlay").visible)
	assert_bool(opened).override_failure_message("MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES").is_true()
	if not opened:
		return
	var grid := reward.get_node(GRID)
	assert_int(grid.get_child_count()).is_greater(0)
	if grid.get_child_count() == 0:
		return
	var offered: Array = reward.call("GetOfferedCardIdsForTest")
	assert_bool(await _activate(grid.get_child(0) as Button)).is_true()
	assert_bool(await _wait_for(func() -> bool: return _deck().size() == before.size() + 1)).is_true()
	assert_str(str(_deck().back())).is_equal(str(offered[0]))
	assert_str(_scene_path()).is_equal(REWARD)
	assert_bool(reward.get_node("CardChoiceOverlay").visible).is_false()
	var unresolved: Array = reward.call("GetVisibleRewardEntriesForTest")
	for entry in unresolved:
		assert_bool(str(entry.get("reward_type", "")).ends_with("_card_choice")).is_false()
	var remaining := reward.get_node(LIST)
	assert_int(remaining.get_child_count()).is_equal(1)
	var expected_gold := int((unresolved[0].get("config", {}) as Dictionary).get("amount", -1))
	assert_int(expected_gold).is_greater(0)
	var gold_before := int((_main.call("GetRunStateForTest") as Dictionary).get("gold", -1))
	assert_bool(await _activate(remaining.get_child(0).get_child(1) as Button)).is_true()
	assert_bool(await _wait_for(func() -> bool: return _scene_path() == MAP)).is_true()
	assert_int(_deck().size()).is_equal(before.size() + 1)
	assert_int(int((_main.call("GetRunStateForTest") as Dictionary).get("gold", -1))).is_equal(gold_before + expected_gold)
