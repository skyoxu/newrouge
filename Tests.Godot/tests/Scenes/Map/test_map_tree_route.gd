extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"

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


func test_map_exposes_five_floor_route_tree_and_only_first_floor_is_initially_available() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	assert_object(map).is_not_null()
	assert_bool(map.has_method("GetRouteTreeFloorCountForTest")).is_true()
	assert_bool(map.has_method("GetReachableRouteNodeIdsForTest")).is_true()
	assert_bool(map.has_method("InvokeRouteNodeForTest")).is_true()

	var legacy_action_row := map.get_node_or_null("ActionRow") as Control
	assert_object(legacy_action_row).is_not_null()
	assert_bool(legacy_action_row.visible).is_false()
	assert_int(int(map.call("GetRouteTreeFloorCountForTest"))).is_equal(5)
	var reachable = map.call("GetReachableRouteNodeIdsForTest")
	assert_array(reachable).contains_exactly(["combat-01"])


func test_tree_node_click_routes_current_floor_and_unlocks_next_floor_after_completion() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	var enter_result := map.call("InvokeRouteNodeForTest", "combat-01") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	await get_tree().process_frame

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	var reward_result := main.call("ResolveRewardForTest", "skip") as Dictionary
	assert_bool(bool(reward_result.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)

	map = _current_scene_instance(main)
	var reachable = map.call("GetReachableRouteNodeIdsForTest")
	assert_array(reachable).contains_exactly(["event-02", "combat-02"])

	var event_enter := map.call("InvokeRouteNodeForTest", "event-02") as Dictionary
	assert_bool(bool(event_enter.get("ok", false))).is_true()
	assert_str(str(event_enter.get("scene_path", ""))).is_equal(EVENT_SCENE)


func test_locked_future_floor_node_refuses_route_without_progress_mutation() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	var before_count := int(main.call("GetMapRouteCompletedNodeCountForTest"))
	var locked_result := map.call("InvokeRouteNodeForTest", "rest-04") as Dictionary

	assert_bool(bool(locked_result.get("ok", false))).is_false()
	assert_str(str(locked_result.get("reason", ""))).is_equal("node-not-reachable")
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(before_count)
