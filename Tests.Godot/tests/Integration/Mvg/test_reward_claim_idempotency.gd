extends "res://tests/Integration/Mvg/reward_fixture.gd"

# Exercise the actual settlement entry twice while another reward is unresolved.
func test_replaying_card_claim_does_not_apply_it_twice() -> void:
	var reward := _reward()
	var entries: Array = reward.call("GetVisibleRewardEntriesForTest")
	var cards: Array = reward.call("GetOfferedCardIdsForTest")
	var card_type := ""
	for entry in entries:
		if str(entry.get("reward_type", "")).ends_with("_card_choice"):
			card_type = str(entry["reward_type"])
	assert_str(card_type).is_not_empty()
	assert_int(cards.size()).is_greater(0)
	if card_type.is_empty() or cards.is_empty():
		return
	var request := {"action": "confirm", "selected_reward_type": card_type,
		"selected_card_id": str(cards[0]), "selected_index": 0}
	var before := _deck().size()
	var first: Dictionary = _main.call("ResolveRewardForTest", request)
	assert_bool(bool(first.get("ok", false))).is_true()
	assert_str(_scene_path()).is_equal(REWARD)
	assert_int(_deck().size()).is_equal(before + 1)
	var replay: Dictionary = _main.call("ResolveRewardForTest", request)
	assert_bool(bool(replay.get("ok", true))).is_false()
	assert_int(_deck().size()).is_equal(before + 1)
	assert_str(_scene_path()).is_equal(REWARD)

func test_replaying_gold_claim_preserves_exact_amount() -> void:
	var entries: Array = _reward().call("GetVisibleRewardEntriesForTest")
	var amount := -1
	for entry in entries:
		if str(entry.get("reward_type", "")) == "gold":
			amount = int((entry.get("config", {}) as Dictionary).get("amount", -1))
	assert_int(amount).is_greater(0)
	var before := int((_main.call("GetRunStateForTest") as Dictionary)["gold"])
	var request := {"action": "confirm", "selected_reward_type": "gold"}
	var first: Dictionary = _main.call("ResolveRewardForTest", request)
	assert_bool(bool(first.get("ok", false))).is_true()
	assert_str(_scene_path()).is_equal(REWARD)
	assert_int(int((_main.call("GetRunStateForTest") as Dictionary)["gold"])).is_equal(before + amount)
	var replay: Dictionary = _main.call("ResolveRewardForTest", request)
	assert_bool(bool(replay.get("ok", true))).is_false()
	assert_int(int((_main.call("GetRunStateForTest") as Dictionary)["gold"])).is_equal(before + amount)
