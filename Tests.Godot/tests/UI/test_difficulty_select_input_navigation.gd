extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const DIFFICULTY_SCENE := preload("res://Game.Godot/Scenes/UI/DifficultySelect.tscn")


func _new_scene() -> Control:
	var scene := DIFFICULTY_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


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


func test_navigation_supports_keyboard_mouse_and_gamepad_across_ten_options() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 1)
	await get_tree().process_frame

	_send_action(scene, "ui_right")
	_send_mouse_click(scene)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(3)

	for _i in range(0, 7):
		_send_joypad_button(scene, 14)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(10)


# ACC:T15.4
func test_confirm_keeps_ui_selection_and_applied_difficulty_in_sync() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 1)
	await get_tree().process_frame

	for _i in range(0, 4):
		_send_joypad_button(scene, 14)
	for _i in range(0, 3):
		_send_mouse_click(scene)
	_send_joypad_button(scene, 14)

	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(9)
	_send_joypad_button(scene, 0)

	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(9)
