extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

var _translation: Translation

func before_test() -> void:
	_translation = Translation.new()
	_translation.locale = "en"
	_translation.add_message("combat.turn.start", "Start Turn")
	_translation.add_message("combat.turn.end", "End Turn")
	_translation.add_message("combat.turn.title", "Turn Control")
	TranslationServer.add_translation(_translation)
	TranslationServer.set_locale("en")

func after_test() -> void:
	if _translation != null:
		TranslationServer.remove_translation(_translation)
		_translation = null

func _new_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene


# acceptance: ACC:T18.4
func test_turn_control_routes_command_and_does_not_advance_turn_without_takeover() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var turn_before := int(scene.call("GetTurnIndexForTest"))
	var mutation_before := int(scene.call("GetCoreStateMutationCountForTest"))
	var root := scene as Control
	var end_turn_button := root.get_node("HUD/TurnControls/EndTurnButton") as Button
	var signal_args: Array = []
	scene.connect("TurnActionRequested", Callable(self, "_on_turn_action_requested").bind(signal_args))

	end_turn_button.emit_signal("pressed")
	await get_tree().process_frame

	assert_that(scene.call("GetDispatchedCommandsForTest")).is_equal(["end_turn"])
	assert_that(signal_args).is_equal(["end_turn"])
	assert_that(int(scene.call("GetTurnIndexForTest"))).is_equal(turn_before)
	assert_that(int(scene.call("GetCoreStateMutationCountForTest"))).is_equal(mutation_before)


func test_invalid_turn_action_is_refused_and_state_remains_unchanged() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var turn_before := int(scene.call("GetTurnIndexForTest"))
	var mutation_before := int(scene.call("GetCoreStateMutationCountForTest"))

	var accepted := bool(scene.call("RequestTurnActionForTest", "invalid_action"))

	assert_that(accepted).is_false()
	assert_that(scene.call("GetDispatchedCommandsForTest")).is_equal([])
	assert_that(int(scene.call("GetTurnIndexForTest"))).is_equal(turn_before)
	assert_that(int(scene.call("GetCoreStateMutationCountForTest"))).is_equal(mutation_before)


func test_start_turn_button_dispatches_start_turn_command() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var root := scene as Control
	var start_turn_button := root.get_node("HUD/TurnControls/StartTurnButton") as Button
	var signal_args: Array = []
	scene.connect("TurnActionRequested", Callable(self, "_on_turn_action_requested").bind(signal_args))

	start_turn_button.emit_signal("pressed")
	await get_tree().process_frame

	assert_that(scene.call("GetDispatchedCommandsForTest")).is_equal(["start_turn"])
	assert_that(signal_args).is_equal(["start_turn"])


# acceptance: ACC:T18.5
func test_turn_control_labels_resolve_localization_keys_in_headless_smoke() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	var end_turn_text := str(scene.call("ResolveLocalizedTextForTest", "combat.turn.end"))
	var title_text := str(scene.call("ResolveLocalizedTextForTest", "combat.turn.title"))
	var root := scene as Control
	var end_turn_button := root.get_node("HUD/TurnControls/EndTurnButton") as Button
	var start_turn_button := root.get_node("HUD/TurnControls/StartTurnButton") as Button
	var turn_title_label := root.get_node("HUD/TurnTitleLabel") as Label

	assert_that(root.visible).is_true()
	assert_that(end_turn_button.visible).is_true()
	assert_that(start_turn_button.text).is_equal("Start Turn")
	assert_that(end_turn_button.text).is_equal("End Turn")
	assert_that(turn_title_label.text).is_equal("Turn Control")
	assert_that(end_turn_text).is_equal("End Turn")
	assert_that(title_text).is_equal("Turn Control")


func _on_turn_action_requested(action_name: String, sink: Array) -> void:
	sink.append(action_name)
