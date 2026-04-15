extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")

func _new_scene() -> Control:
	var scene = EVENT_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


# acceptance: ACC:T22.5
func test_join_curse_card_cost_adds_card_immediately_after_selection() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	var before_count = int(scene.call("GetCurseCardCountForTest"))

	var applied = bool(scene.call("ChooseOptionForTest", "take_curse"))
	var after_count = int(scene.call("GetCurseCardCountForTest"))

	assert_bool(applied).is_true()
	assert_int(after_count).is_equal(before_count + 1)
	assert_that(scene.call("GetDeckCardIdsForTest")).contains_exactly(["card.curse.basic"])
	assert_str(str(scene.call("GetSelectedOptionIdForTest"))).is_equal("take_curse")
	assert_str(str(scene.call("GetPersistedSelectedOptionIdForTest"))).is_equal("take_curse")
	var second_applied = bool(scene.call("ChooseOptionForTest", "take_curse"))
	assert_bool(second_applied).is_false()
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(1)
	assert_str(str(scene.call("GetPersistedSelectedOptionIdForTest"))).is_equal("take_curse")


# gate: T22:GATE:invalid-or-repeat-selection
func test_invalid_or_second_selection_must_not_increase_curse_cards() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)

	var invalid_applied = bool(scene.call("ChooseOptionForTest", "not_exists"))
	assert_bool(invalid_applied).is_false()
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(0)

	var first_applied = bool(scene.call("ChooseOptionForTest", "take_curse"))
	assert_bool(first_applied).is_true()
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(1)

	var second_applied = bool(scene.call("ChooseOptionForTest", "take_curse"))
	assert_bool(second_applied).is_false()
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(1)

