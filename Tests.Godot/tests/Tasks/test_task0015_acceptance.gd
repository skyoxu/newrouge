extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const DIFFICULTY_SCENE := preload("res://Game.Godot/Scenes/UI/DifficultySelect.tscn")


func _new_scene() -> Control:
	var scene := DIFFICULTY_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


func _contains_forbidden_talent_tree_phrase(text: String) -> bool:
	var lowered := text.to_lower()
	return lowered.find("talent tree") >= 0 \
		or lowered.find("requires talent") >= 0 \
		or lowered.find("locked by talent") >= 0


func _send_action(scene: Control, action_name: String) -> void:
	var action := InputEventAction.new()
	action.action = action_name
	action.pressed = true
	scene.call("_UnhandledInput", action)


func _send_mouse_click(scene: Control) -> void:
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	scene.call("_GuiInput", click)


func _send_joypad_button(scene: Control, button_index: int) -> void:
	var button := InputEventJoypadButton.new()
	button.button_index = button_index
	button.pressed = true
	scene.call("_UnhandledInput", button)


# ACC:T15.1
func test_scene_shows_operable_control_with_exactly_ten_options_and_live_selection_feedback() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 1)
	await get_tree().process_frame

	assert_bool(scene.visible).is_true()
	assert_int(int(scene.call("GetDifficultyOptionCountForTest"))).is_equal(10)

	scene.call("SelectDifficultyForTest", 3)
	await get_tree().process_frame

	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(3)
	assert_bool(bool(scene.call("IsSelectionIndicatorVisibleForTest"))).is_true()


# ACC:T15.1
func test_difficulty_select_scene_file_can_be_instantiated_with_required_nodes() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	assert_object(scene.get_node_or_null("VBox/DifficultyOptions")).is_not_null()
	assert_object(scene.get_node_or_null("VBox/LblDescription")).is_not_null()
	assert_int(int(scene.call("GetDifficultyOptionCountForTest"))).is_equal(10)


# ACC:T15.2
func test_all_ten_options_use_localized_descriptions_without_talent_tree_binding_language() -> void:
	var scene := _new_scene()
	var description_label := scene.get_node("VBox/LblDescription") as Label
	var previous_description := ""
	await get_tree().process_frame

	for level in range(1, 11):
		scene.call("SelectDifficultyForTest", level)
		await get_tree().process_frame
		assert_bool(bool(scene.call("HasDescriptionTranslationForTest", level))).is_true()
		var description := str(scene.call("GetDescriptionTextForTest", level))
		assert_str(description_label.text).is_equal(description)
		assert_bool(description.strip_edges().is_empty()).is_false()
		assert_bool(description.find(str(level)) >= 0).is_true()
		assert_bool(_contains_forbidden_talent_tree_phrase(description)).is_false()
		if level > 1:
			assert_str(description).is_not_equal(previous_description)
		previous_description = description


# ACC:T15.3
func test_confirmed_difficulty_persists_and_does_not_change_without_new_confirmation() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 4)
	await get_tree().process_frame

	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(4)

	scene.call("SelectDifficultyForTest", 8)
	await get_tree().process_frame
	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(4)

	scene.call("ConfirmSelectionForTest")
	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(8)

	var reopen := _new_scene()
	await get_tree().process_frame
	assert_int(int(reopen.call("GetSelectedDifficultyForTest"))).is_equal(8)


# ACC:T15.5
func test_control_shape_is_button_group_and_can_select_all_ten_levels() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	assert_str(str(scene.call("GetControlShapeForTest"))).is_equal("button_group")
	assert_int(int(scene.call("GetDifficultyOptionCountForTest"))).is_equal(10)

	scene.call("SelectDifficultyForTest", 10)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(10)
	scene.call("SelectDifficultyForTest", 1)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(1)


# ACC:T15.6
func test_navigation_flow_for_keyboard_mouse_and_gamepad_updates_and_confirms_selection() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 2)
	await get_tree().process_frame

	_send_action(scene, "ui_right")
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(3)
	for _i in range(0, 6):
		_send_mouse_click(scene)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(9)
	_send_joypad_button(scene, 13)
	_send_joypad_button(scene, 13)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(7)

	_send_joypad_button(scene, 0)
	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(7)


# ACC:T15.7
func test_reentering_scene_reads_last_confirmed_value_and_avoids_silent_reset() -> void:
	var first := _new_scene()
	first.call("ResetConfirmedDifficultyForTest", 6)
	await get_tree().process_frame

	assert_int(int(first.call("GetSelectedDifficultyForTest"))).is_equal(6)
	first.call("SelectDifficultyForTest", 10)
	await get_tree().process_frame

	var reopen_without_confirm := _new_scene()
	await get_tree().process_frame
	assert_int(int(reopen_without_confirm.call("GetSelectedDifficultyForTest"))).is_equal(6)

	first.call("ConfirmSelectionForTest")
	var reopen_after_confirm := _new_scene()
	await get_tree().process_frame
	assert_int(int(reopen_after_confirm.call("GetSelectedDifficultyForTest"))).is_equal(10)


# ACC:T15.8
func test_audit_can_locate_description_keys_and_text_for_all_levels() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	for level in range(1, 11):
		var key := str(scene.call("GetDescriptionKeyForTest", level))
		var text := str(scene.call("GetDescriptionTextForTest", level))
		assert_bool(key.begins_with("ui.difficulty.")).is_true()
		assert_bool(text.strip_edges().is_empty()).is_false()
		assert_bool(_contains_forbidden_talent_tree_phrase(text)).is_false()
