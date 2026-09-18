extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

# This fixture prepares an already-completed encounter, then uses engine action
# events on focused controls. It does not claim mouse hit-testing or OS input.
const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP := "res://Game.Godot/Scenes/Map/Map.tscn"
const REWARD := "res://Game.Godot/Scenes/Reward.tscn"
const LIST := "RootMargin/VBox/RewardListScroll/RewardList"
const GRID := "CardChoiceOverlay/Shell/ChoiceVBox/ChoiceScroll/ChoiceGrid"

var _main: Control
var _bus: Node
var _previous_locale: String

func before_test() -> void:
	_previous_locale = TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	_bus = EVENT_BUS.new()
	_bus.name = "EventBus"
	get_tree().root.add_child(_bus)
	_main = MAIN_SCENE.instantiate() as Control
	add_child(_main)
	await get_tree().process_frame
	var nav := _main.get_node("ScreenNavigator")
	nav.UseFadeTransition = false
	nav.call("SwitchTo", MAP)
	await get_tree().process_frame
	_main.call("ResetMapRouteProgressForTest")
	var entered: Dictionary = _main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "")
	assert_bool(bool(entered.get("ok", false))).is_true()
	var completed: Dictionary = _main.call("CompleteMapNodeFlowForTest")
	assert_bool(bool(completed.get("ok", false))).is_true()
	assert_bool(await _wait_for(func() -> bool: return _scene_path() == REWARD)).is_true()

func after_test() -> void:
	var release := InputEventAction.new()
	release.action = "ui_accept"
	release.pressed = false
	get_viewport().push_input(release)
	Input.action_release("ui_accept")
	if is_instance_valid(_main):
		_main.queue_free()
	if is_instance_valid(_bus):
		_bus.queue_free()
	await get_tree().process_frame
	TranslationServer.set_locale(_previous_locale)

func _scene_path() -> String:
	return str(_main.get_node("ScreenNavigator").call("GetCurrentScenePathForTest"))

func _reward() -> Control:
	var root := _main.get_node("ScreenRoot")
	return root.get_child(root.get_child_count() - 1) as Control

func _deck() -> Array:
	return _main.call("GetRunDeckCardIdsForTest") as Array

func _wait_for(condition: Callable, timeout_ms: int = 3000) -> bool:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while not condition.call() and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	if not condition.call():
		print("MVG_WAIT_TIMEOUT scene=", _scene_path(), " state=", _main.call("GetRunStateForTest"))
		return false
	return true

func _activate(button: Button) -> bool:
	if not is_instance_valid(button) or not button.is_visible_in_tree() or button.disabled:
		return false
	button.grab_focus()
	await get_tree().process_frame
	if not button.has_focus():
		return false
	var press := InputEventAction.new()
	press.action = "ui_accept"
	press.pressed = true
	button.get_viewport().push_input(press)
	await get_tree().process_frame
	var release := InputEventAction.new()
	release.action = "ui_accept"
	release.pressed = false
	get_viewport().push_input(release)
	await get_tree().process_frame
	return true
