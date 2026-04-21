extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")

func _new_scene() -> Control:
	var scene = EVENT_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


# acceptance: ACC:T22.4
# acceptance: ACC:T69.5
func test_event_scene_hp_loss_cost_applies_immediately() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 12, 0)
	var applied = bool(scene.call("ChooseOptionForTest", "lose_hp"))

	assert_bool(applied).is_true()
	assert_int(int(scene.call("GetCurrentHpForTest"))).is_equal(9)
	assert_str(str(scene.call("GetSelectedOptionIdForTest"))).is_equal("lose_hp")
	assert_str(str(scene.call("GetLoseHpPreviewTextForTest"))).contains("HP")
	assert_str(str(scene.call("GetLoseHpPreviewTextForTest"))).contains("-3")
	assert_str(str(scene.call("GetResultSummaryTextForTest"))).contains("Lost 3 HP")
	assert_str(str(scene.call("GetNumericChangesTextForTest"))).contains("HP -3")
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).contains("event.option").is_false()
	assert_str(str(scene.call("GetEventTitleForTest"))).is_not_empty()
	assert_str(str(scene.call("GetEventDescriptionForTest"))).is_not_empty()


# acceptance: ACC:T22.4
func test_event_scene_hp_loss_cost_must_not_leave_hp_unchanged_after_selection() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 10, 0)
	var hp_before = int(scene.call("GetCurrentHpForTest"))
	scene.call("ChooseOptionForTest", "lose_hp")

	assert_int(int(scene.call("GetCurrentHpForTest"))).is_not_equal(hp_before)

