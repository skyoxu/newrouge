extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"


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


func _current_scene_instance(main: Control) -> Node:
	var root := main.get_node_or_null("ScreenRoot")
	if root == null or root.get_child_count() == 0:
		return null
	return root.get_child(root.get_child_count() - 1)


func _node_states(map_node) -> Dictionary:
	return map_node.call("GetRouteNodeStatesForTest") as Dictionary


# ACC:T97.1
func test_route_binding_uses_generated_route_graph_for_live_map_progression() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	var initial_states := _node_states(map)
	assert_str(str(initial_states.get("combat-01", ""))).is_equal("reachable")
	assert_str(str(initial_states.get("event-02", ""))).is_equal("locked")

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
	var progressed_states := _node_states(map)
	assert_str(str(progressed_states.get("combat-01", ""))).is_equal("completed")
	assert_str(str(progressed_states.get("event-02", ""))).is_equal("selected-path")
	assert_str(str(progressed_states.get("combat-02", ""))).is_equal("selected-path")


# ACC:T97.2
func test_route_binding_keeps_single_route_owned_map_surface_without_secondary_owner_path() -> void:
	var main := await _load_main_on_map()
	var map_before: Node = _current_scene_instance(main)
	var route_tree_before := map_before.get_node_or_null("RouteTree")
	assert_object(route_tree_before).is_not_null()

	var enter_result := map_before.call("InvokeRouteNodeForTest", "combat-01") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	await get_tree().process_frame

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	var reward_result := main.call("ResolveRewardForTest", "skip") as Dictionary
	assert_bool(bool(reward_result.get("ok", false))).is_true()
	await get_tree().process_frame

	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	var map_after: Node = _current_scene_instance(main)
	var route_tree_after := map_after.get_node_or_null("RouteTree")
	assert_object(route_tree_after).is_not_null()
	assert_bool(route_tree_after != route_tree_before).is_false()

	var detached_route_trees := main.find_children("RouteTree", "", true, false)
	assert_int(detached_route_trees.size()).is_equal(1)

	var reachable_after = map_after.call("GetReachableRouteNodeIdsForTest")
	assert_array(reachable_after).contains_exactly(["event-02", "combat-02"])
	assert_bool(map_after.has_method("InvokeRouteNodeForTest")).is_true()
	assert_bool(map_after.has_method("GetRouteNodeStatesForTest")).is_true()


func test_invalid_node_selection_keeps_map_route_progress_and_scene_unchanged() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)
	var before_count := int(main.call("GetMapRouteCompletedNodeCountForTest"))
	var before_start_invocations := int(main.call("GetMapRouteStartInvocationCountForTest"))

	var blocked_result := map.call("InvokeRouteNodeForTest", "rest-04") as Dictionary

	assert_bool(bool(blocked_result.get("ok", false))).is_false()
	assert_str(str(blocked_result.get("reason", ""))).is_equal("node-not-reachable")
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(before_count)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(before_start_invocations)
