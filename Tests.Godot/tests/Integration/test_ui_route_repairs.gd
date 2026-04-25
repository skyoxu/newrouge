extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"

var _bus: Node


func before() -> void:
	_bus = EVENT_BUS_SCRIPT.new()
	_bus.name = "EventBus"
	get_tree().get_root().add_child(auto_free(_bus))


func _load_main_on_map() -> Control:
	var main := MAIN_SCENE.instantiate() as Control
	add_child(auto_free(main))
	await get_tree().process_frame

	var nav := main.get_node_or_null("ScreenNavigator")
	assert_object(nav).is_not_null()
	nav.UseFadeTransition = false
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")
	nav.call("SwitchTo", MAP_SCENE)
	await get_tree().process_frame
	if main.has_method("ResetMapRouteProgressForTest"):
		main.call("ResetMapRouteProgressForTest")
	return main


func _current_scene_path(main: Control) -> String:
	var nav := main.get_node_or_null("ScreenNavigator")
	if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
		return ""
	return str(nav.call("GetCurrentScenePathForTest"))


func _current_scene_instance(main: Control):
	var root := main.get_node_or_null("ScreenRoot")
	if root == null or root.get_child_count() == 0:
		return null
	return root.get_child(root.get_child_count() - 1)


func _enter_scene(main: Control, node_id: String, node_type: String, expected_scene: String):
	var enter_result := main.call("StartMapNodeRouteForTest", node_id, node_type, true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(expected_scene)
	await get_tree().process_frame

	var scene = _current_scene_instance(main)
	assert_object(scene).is_not_null()
	return scene


# acceptance: ACC:UT:UIROUTE:EVENT-CONTINUE
func test_event_choice_exposes_continue_action_and_returns_to_map_via_reward_resolution() -> void:
	var main := await _load_main_on_map()
	var event_scene = await _enter_scene(main, "event-01", "event", EVENT_SCENE)

	assert_bool(event_scene.has_method("ChooseOptionForTest")).is_true()
	assert_bool(event_scene.has_method("ContinueAfterChoiceForTest")).is_true()
	assert_bool(event_scene.has_method("CanContinueForTest")).is_true()
	assert_bool(event_scene.has_method("ClearRuntimeCacheForTest")).is_true()
	assert_bool(event_scene.has_method("ResetStateForTest")).is_true()
	event_scene.call("ClearRuntimeCacheForTest")
	event_scene.call("ResetStateForTest", 20, 0)

	assert_bool(bool(event_scene.call("CanContinueForTest"))).is_false()
	assert_bool(bool(event_scene.call("ChooseOptionForTest", "lose_hp"))).is_true()
	assert_bool(bool(event_scene.call("CanContinueForTest"))).is_true()

	var continue_result := event_scene.call("ContinueAfterChoiceForTest") as Dictionary
	assert_bool(bool(continue_result.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)

	var reward_scene = _current_scene_instance(main)
	assert_object(reward_scene).is_not_null()
	assert_bool(reward_scene.has_method("SelectChoiceForTest")).is_true()
	assert_bool(reward_scene.has_method("ConfirmSelectedForTest")).is_true()
	assert_bool(bool(reward_scene.call("SelectChoiceForTest", 0))).is_true()
	assert_bool(bool(reward_scene.call("ConfirmSelectedForTest"))).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)


# acceptance: ACC:UT:UIROUTE:REST-CLICK
func test_rest_buttons_complete_route_without_manual_external_call() -> void:
	var main := await _load_main_on_map()
	var rest_scene = await _enter_scene(main, "rest-01", "rest", REST_SCENE)

	assert_bool(rest_scene.has_method("SelectOptionForTest")).is_true()
	assert_bool(bool(rest_scene.call("SelectOptionForTest", "heal"))).is_true()
	await get_tree().process_frame

	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(1)


# acceptance: ACC:UT:UIROUTE:HUD-GOLD
func test_hud_shows_gold_resource_and_updates_from_event_bus() -> void:
	var main := await _load_main_on_map()
	var hud := main.get_node("HUD")
	assert_object(hud).is_not_null()

	var gold_label := hud.get_node_or_null("TopBar/HBox/GoldLabel") as Label
	assert_object(gold_label).is_not_null()
	assert_str(gold_label.text).contains("Gold")

	var bus := get_node_or_null("/root/EventBus")
	assert_object(bus).is_not_null()
	bus.PublishSimple("core.gold.updated", "ut", '{"value":88}')
	for _i in range(30):
		await get_tree().process_frame

	assert_str(gold_label.text).contains("88")
