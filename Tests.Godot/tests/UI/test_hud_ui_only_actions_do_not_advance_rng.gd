extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const STREAM_NAMES := [
	"run",
	"combat",
	"event",
	"loot",
	"shop",
	"offer",
]
const MAIN_MENU_SCENE_PATH := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const RNG_PROBE_SCRIPT_PATH := "res://Game.Godot/Scripts/UI/Task9RngStateProbe.cs"
const EVENT_BUS_SCRIPT_PATH := "res://Game.Godot/Adapters/EventBusAdapter.cs"


func _instantiate_main_menu() -> Control:
	var menu_scene := load(MAIN_MENU_SCENE_PATH) as PackedScene
	assert_that(menu_scene).is_not_null()
	var menu := menu_scene.instantiate() as Control
	assert_that(menu).is_not_null()
	add_child(menu)
	return menu


func _simulate_ui_only_action(menu: Control) -> void:
	var settings_button := menu.get_node("VBox/BtnSettings") as Button
	assert_that(settings_button).is_not_null()
	settings_button.emit_signal("pressed")


func _simulate_gameplay_action(menu: Control) -> void:
	var play_button := menu.get_node("VBox/BtnPlay") as Button
	assert_that(play_button).is_not_null()
	play_button.emit_signal("pressed")


func _ensure_event_bus() -> Node:
	var root := get_tree().root
	var existing := root.get_node_or_null("EventBus")
	if existing != null:
		return existing
	var event_bus_script := load(EVENT_BUS_SCRIPT_PATH) as Script
	assert_that(event_bus_script).is_not_null()
	var event_bus := event_bus_script.new() as Node
	assert_that(event_bus).is_not_null()
	event_bus.name = "EventBus"
	root.add_child(event_bus)
	return event_bus


func _new_probe() -> Node:
	_ensure_event_bus()
	var probe_script := load(RNG_PROBE_SCRIPT_PATH) as Script
	assert_that(probe_script).is_not_null()
	var probe := probe_script.new() as Node
	assert_that(probe).is_not_null()
	add_child(probe)
	probe.call("ResetWithSeed", 20260404)
	return probe


# acceptance: ACC:T9.4
func test_ui_only_actions_do_not_advance_any_named_rng_stream() -> void:
	var probe := _new_probe()
	var event_bus := _ensure_event_bus()
	var positions_before := probe.call("CapturePositions") as Dictionary
	var snapshots_before := probe.call("CaptureSnapshots") as Dictionary
	var menu := _instantiate_main_menu()
	await get_tree().process_frame

	_simulate_ui_only_action(menu)
	menu.queue_free()

	var positions_after := probe.call("CapturePositions") as Dictionary
	var snapshots_after := probe.call("CaptureSnapshots") as Dictionary
	probe.queue_free()
	event_bus.queue_free()
	assert_that(positions_after).is_equal(positions_before)
	assert_that(snapshots_after).is_equal(snapshots_before)


func test_gameplay_roll_advances_combat_stream_as_control_case() -> void:
	var probe := _new_probe()
	var expected_before := probe.call("CapturePositions") as Dictionary
	probe.call("TriggerGameplayRoll")

	var positions_after := probe.call("CapturePositions") as Dictionary
	probe.queue_free()
	assert_int(int(positions_after["combat"])).is_equal(int(expected_before["combat"]) + 1)
	for stream_name in STREAM_NAMES:
		if stream_name == "combat":
			continue
		assert_int(int(positions_after[stream_name])).is_equal(int(expected_before[stream_name]))
