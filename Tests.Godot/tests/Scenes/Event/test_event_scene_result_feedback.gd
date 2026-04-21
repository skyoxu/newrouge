extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")


func _new_scene() -> Control:
	var scene = EVENT_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


# acceptance: ACC:T69.1
func test_pre_confirm_displays_title_description_options_and_previews() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)

	assert_str(str(scene.call("GetEventTitleForTest"))).is_not_empty()
	assert_str(str(scene.call("GetEventDescriptionForTest"))).is_not_empty()
	assert_str(str(scene.call("GetLoseHpPreviewTextForTest"))).contains("HP")
	assert_str(str(scene.call("GetLoseHpPreviewTextForTest"))).contains("-3")
	assert_str(str(scene.call("GetTakeCursePreviewTextForTest"))).contains("Cards")
	assert_str(str(scene.call("GetTakeCursePreviewTextForTest"))).contains("+1")
	assert_bool(bool(scene.call("IsChosenOptionVisibleForTest"))).is_false()
	assert_bool(bool(scene.call("IsResultSummaryVisibleForTest"))).is_false()
	assert_bool(bool(scene.call("IsNumericChangesVisibleForTest"))).is_false()
	assert_bool(bool(scene.call("IsBlockedFeedbackVisibleForTest"))).is_false()


# acceptance: ACC:T69.2
func test_after_commit_displays_selected_option_summary_and_signed_numeric_changes() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)

	var applied := bool(scene.call("ChooseOptionForTest", "lose_hp"))
	assert_bool(applied).is_true()
	assert_bool(bool(scene.call("IsChosenOptionVisibleForTest"))).is_true()
	assert_bool(bool(scene.call("IsResultSummaryVisibleForTest"))).is_true()
	assert_bool(bool(scene.call("IsNumericChangesVisibleForTest"))).is_true()
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).contains("Chosen option:")
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).is_not_empty()
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).contains("event.option").is_false()
	assert_str(str(scene.call("GetResultSummaryTextForTest"))).contains("Lost 3 HP")
	assert_str(str(scene.call("GetNumericChangesTextForTest"))).contains("HP -3")
	assert_str(str(scene.call("GetNumericChangesTextForTest"))).contains("Curse cards +0")
	assert_bool(bool(scene.call("IsBlockedFeedbackVisibleForTest"))).is_false()


# acceptance: ACC:T69.6
func test_real_scene_feedback_nodes_are_visible_after_commit() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)

	var applied := bool(scene.call("ChooseOptionForTest", "take_curse"))
	assert_bool(applied).is_true()
	assert_that(scene.is_inside_tree()).is_true()
	assert_bool(bool(scene.call("IsChosenOptionVisibleForTest"))).is_true()
	assert_bool(bool(scene.call("IsResultSummaryVisibleForTest"))).is_true()
	assert_bool(bool(scene.call("IsNumericChangesVisibleForTest"))).is_true()
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).contains("Chosen option:")
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).is_not_empty()
	assert_str(str(scene.call("GetChosenOptionTextForTest"))).contains("event.option").is_false()
	assert_str(str(scene.call("GetResultSummaryTextForTest"))).contains("Took a curse card")
	assert_str(str(scene.call("GetNumericChangesTextForTest"))).contains("HP +0")
	assert_str(str(scene.call("GetNumericChangesTextForTest"))).contains("Curse cards +1")


# acceptance: ACC:T69.4
func test_invalid_or_unavailable_choice_keeps_state_and_shows_blocked_feedback() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 14, 0)
	var hp_before := int(scene.call("GetCurrentHpForTest"))
	var curses_before := int(scene.call("GetCurseCardCountForTest"))

	var invalid_applied := bool(scene.call("ChooseOptionForTest", "invalid-choice"))
	assert_bool(invalid_applied).is_false()
	assert_int(int(scene.call("GetCurrentHpForTest"))).is_equal(hp_before)
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(curses_before)
	assert_bool(bool(scene.call("IsBlockedFeedbackVisibleForTest"))).is_true()
	assert_str(str(scene.call("GetBlockedFeedbackTextForTest"))).is_not_equal("event.feedback.blocked.invalid_option")
	assert_str(str(scene.call("GetSelectedOptionIdForTest"))).is_equal("")


# acceptance: ACC:T69.5
func test_player_visible_event_copy_changes_with_locale_and_is_not_raw_key() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("SetLocaleForTest", "en")
	var en_title := str(scene.call("GetEventTitleForTest"))
	var en_preview := str(scene.call("GetLoseHpPreviewTextForTest"))

	scene.call("SetLocaleForTest", "zh-CN")
	var zh_title := str(scene.call("GetEventTitleForTest"))
	var zh_preview := str(scene.call("GetLoseHpPreviewTextForTest"))

	assert_str(en_title).is_not_equal("event.abyss_toll.title")
	assert_str(zh_title).is_not_equal("event.abyss_toll.title")
	assert_str(en_preview).is_not_equal("event.preview.hp_loss")
	assert_str(zh_preview).is_not_equal("event.preview.hp_loss")
	assert_str(en_title).is_not_equal(zh_title)
	assert_str(en_preview).is_not_equal(zh_preview)
