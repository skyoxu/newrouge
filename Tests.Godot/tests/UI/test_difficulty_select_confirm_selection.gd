extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const DIFFICULTY_SCENE := preload("res://Game.Godot/Scenes/UI/DifficultySelect.tscn")

var _bus: Node
var _event_received := false
var _event_type := ""


func before() -> void:
	_event_received = false
	_event_type = ""
	_bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
	_bus.name = "EventBus"
	get_tree().get_root().add_child(auto_free(_bus))
	_bus.connect("DomainEventEmitted", Callable(self, "_on_event"))


func _on_event(type, _source, _data_json, _id, _spec, _ct, _ts) -> void:
	_event_received = true
	_event_type = str(type)


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


# ACC:T15.4
func test_confirm_keeps_ui_selection_and_applies_same_difficulty_after_mixed_navigation() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 1)
	await get_tree().process_frame

	for _i in range(0, 3):
		_send_joypad_button(scene, 14)
	for _i in range(0, 4):
		_send_mouse_click(scene)
	_send_joypad_button(scene, 13)
	_send_joypad_button(scene, 13)
	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(6)

	_send_joypad_button(scene, 0)
	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(6)
	assert_bool(_event_received).is_true()
	assert_str(_event_type).is_equal("core.run.difficulty.selected")


func test_navigation_does_not_apply_difficulty_before_confirm() -> void:
	var scene := _new_scene()
	scene.call("ResetConfirmedDifficultyForTest", 2)
	await get_tree().process_frame

	_send_joypad_button(scene, 14)
	_send_joypad_button(scene, 14)
	for _i in range(0, 5):
		_send_mouse_click(scene)
	_send_joypad_button(scene, 13)

	assert_int(int(scene.call("GetSelectedDifficultyForTest"))).is_equal(8)
	assert_int(int(scene.call("GetConfirmedDifficultyForTest"))).is_equal(2)
