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


func _edge_key(edge: Dictionary) -> String:
	return "%s->%s" % [str(edge.get("from", "")), str(edge.get("to", ""))]


func _walk_m1_route(main: Control, node_ids: Array) -> void:
	for node_id_variant in node_ids:
		var node_id := str(node_id_variant)
		var map = _current_scene_instance(main)
		var enter_result := map.call("InvokeRouteNodeForTest", node_id) as Dictionary
		assert_bool(bool(enter_result.get("ok", false))).is_true()
		var scene_path := str(enter_result.get("scene_path", ""))
		assert_bool(scene_path == COMBAT_SCENE or scene_path == EVENT_SCENE or scene_path == SHOP_SCENE or scene_path == REST_SCENE).is_true()
		await get_tree().process_frame
		var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
		assert_bool(bool(complete_result.get("ok", false))).is_true()
		if _current_scene_path(main) == REWARD_SCENE:
			var reward_result := main.call("ResolveRewardForTest", "skip") as Dictionary
			assert_bool(bool(reward_result.get("ok", false))).is_true()
		await get_tree().process_frame
		assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)


const SHOP_SCENE := "res://Game.Godot/Scenes/Shop.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"


# acceptance: ACC:T70.1
# acceptance: ACC:T70.2
# acceptance: ACC:T70.3
# ACC:T97.6
# ACC:T97.7
# ACC:T97.8
# ACC:T97.9
# ACC:T97.10
func test_map_exposes_five_floor_route_tree_and_only_first_floor_is_initially_available() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	assert_object(map).is_not_null()
	assert_bool(map.has_method("GetRouteTreeFloorCountForTest")).is_true()
	assert_bool(map.has_method("GetReachableRouteNodeIdsForTest")).is_true()
	assert_bool(map.has_method("InvokeRouteNodeForTest")).is_true()
	assert_bool(map.has_method("GetRouteEdgesForTest")).is_true()
	assert_bool(map.has_method("GetRouteNodeStatesForTest")).is_true()

	var legacy_action_row := map.get_node_or_null("ActionRow") as Control
	assert_object(legacy_action_row).is_not_null()
	assert_bool(legacy_action_row.visible).is_false()
	assert_int(int(map.call("GetRouteTreeFloorCountForTest"))).is_equal(5)
	var reachable = map.call("GetReachableRouteNodeIdsForTest")
	assert_array(reachable).contains_exactly(["combat-01"])

	var edges: Array = map.call("GetRouteEdgesForTest")
	assert_int(edges.size()).is_equal(7)
	var edge_lookup := {}
	var edge_nodes := {}
	for edge_variant in edges:
		var edge = edge_variant as Dictionary
		var key := _edge_key(edge)
		edge_lookup[key] = str(edge.get("state", ""))
		edge_nodes[str(edge.get("from", ""))] = true
		edge_nodes[str(edge.get("to", ""))] = true
	assert_dict(edge_lookup).contains_key("combat-01->event-02")
	assert_dict(edge_lookup).contains_key("combat-01->combat-02")
	assert_dict(edge_lookup).contains_key("event-02->shop-03")
	assert_dict(edge_lookup).contains_key("combat-02->combat-03")
	assert_dict(edge_lookup).contains_key("shop-03->rest-04")
	assert_dict(edge_lookup).contains_key("combat-03->rest-04")
	assert_dict(edge_lookup).contains_key("rest-04->boss-05")
	assert_str(str(edge_lookup["combat-01->event-02"])).is_equal("reachable")
	assert_str(str(edge_lookup["combat-01->combat-02"])).is_equal("reachable")
	assert_str(str(edge_lookup["rest-04->boss-05"])).is_equal("locked")
	assert_bool(edge_lookup.has("combat-01->shop-03")).is_false()
	assert_bool(edge_lookup.has("combat-01->rest-04")).is_false()
	assert_bool(edge_lookup.has("event-02->boss-05")).is_false()
	assert_bool(edge_lookup.has("combat-03->boss-05")).is_false()
	assert_int(edge_nodes.size()).is_equal(7)

	var node_states: Dictionary = map.call("GetRouteNodeStatesForTest")
	assert_str(str(node_states.get("combat-01", ""))).is_equal("reachable")
	assert_str(str(node_states.get("event-02", ""))).is_equal("locked")
	assert_str(str(node_states.get("rest-04", ""))).is_equal("locked")
	var combat_button := map.get_node_or_null("RouteTree/Floor1/combat_01") as Button
	var event_button := map.get_node_or_null("RouteTree/Floor2/event_02") as Button
	var edge_legend := map.get_node_or_null("edge_legend_label") as Label
	var edge_container := map.get_node_or_null("RouteEdgeContainer") as VBoxContainer
	var first_edge_label := map.get_node_or_null("RouteEdgeContainer/combat_01__event_02") as Label
	assert_object(combat_button).is_not_null()
	assert_object(event_button).is_not_null()
	assert_object(edge_legend).is_not_null()
	assert_object(edge_container).is_not_null()
	assert_object(first_edge_label).is_not_null()
	assert_int(edge_container.get_child_count()).is_greater_equal(7)
	assert_bool(first_edge_label.visible).is_true()
	assert_bool(combat_button.disabled).is_false()
	assert_bool(event_button.disabled).is_true()
	assert_str(combat_button.tooltip_text).contains("state:reachable")
	assert_str(event_button.tooltip_text).contains("state:locked")
	assert_str(first_edge_label.tooltip_text).contains("state:reachable")
	assert_bool(combat_button.modulate != event_button.modulate).is_true()
	assert_str(edge_legend.text).contains("combat-01->event-02(reachable)")
	assert_str(edge_legend.text).contains("rest-04->boss-05(locked)")


# acceptance: ACC:T70.4
# acceptance: ACC:T70.5
# acceptance: ACC:T70.6
# ACC:T97.1
# ACC:T97.2
# ACC:T97.3
# ACC:T97.4
# ACC:T97.5
func test_tree_node_click_routes_current_floor_and_unlocks_next_floor_after_completion() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	var enter_result := map.call("InvokeRouteNodeForTest", "combat-01") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(1)
	assert_str(str(main.call("GetMapRouteLastStartDestinationForTest"))).is_equal(COMBAT_SCENE)
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

	var node_states: Dictionary = map.call("GetRouteNodeStatesForTest")
	assert_str(str(node_states.get("combat-01", ""))).is_equal("completed")
	assert_str(str(node_states.get("event-02", ""))).is_equal("selected-path")
	assert_str(str(node_states.get("combat-02", ""))).is_equal("selected-path")
	assert_str(str(node_states.get("rest-04", ""))).is_equal("locked")
	var event_button := map.get_node_or_null("RouteTree/Floor2/event_02") as Button
	var rest_button := map.get_node_or_null("RouteTree/Floor4/rest_04") as Button
	var edge_legend := map.get_node_or_null("edge_legend_label") as Label
	var selected_edge_label := map.get_node_or_null("RouteEdgeContainer/event_02__shop_03") as Label
	var locked_edge_label := map.get_node_or_null("RouteEdgeContainer/shop_03__rest_04") as Label
	assert_object(event_button).is_not_null()
	assert_object(rest_button).is_not_null()
	assert_object(edge_legend).is_not_null()
	assert_object(selected_edge_label).is_not_null()
	assert_object(locked_edge_label).is_not_null()
	assert_bool(event_button.disabled).is_false()
	assert_bool(rest_button.disabled).is_true()
	assert_str(event_button.tooltip_text).contains("state:selected-path")
	assert_str(rest_button.tooltip_text).contains("state:locked")
	assert_str(selected_edge_label.tooltip_text).contains("state:selected-path")
	assert_str(locked_edge_label.tooltip_text).contains("state:locked")
	assert_bool(selected_edge_label.modulate != locked_edge_label.modulate).is_true()
	assert_bool(event_button.modulate != rest_button.modulate).is_true()

	var edges: Array = map.call("GetRouteEdgesForTest")
	var edge_lookup := {}
	for edge_variant in edges:
		var edge = edge_variant as Dictionary
		edge_lookup[_edge_key(edge)] = str(edge.get("state", ""))
	assert_str(str(edge_lookup.get("combat-01->event-02", ""))).is_equal("completed")
	assert_str(str(edge_lookup.get("combat-01->combat-02", ""))).is_equal("completed")
	assert_str(str(edge_lookup.get("event-02->shop-03", ""))).is_equal("selected-path")
	assert_str(str(edge_lookup.get("combat-02->combat-03", ""))).is_equal("selected-path")
	assert_str(str(edge_lookup.get("shop-03->rest-04", ""))).is_equal("locked")
	assert_str(edge_legend.text).contains("combat-01->event-02(completed)")
	assert_str(edge_legend.text).contains("event-02->shop-03(selected-path)")
	assert_str(edge_legend.text).contains("shop-03->rest-04(locked)")

	var event_enter := map.call("InvokeRouteNodeForTest", "event-02") as Dictionary
	assert_bool(bool(event_enter.get("ok", false))).is_true()
	assert_str(str(event_enter.get("scene_path", ""))).is_equal(EVENT_SCENE)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(2)
	assert_str(str(main.call("GetMapRouteLastStartDestinationForTest"))).is_equal(EVENT_SCENE)


# acceptance: ACC:T70.1
# acceptance: ACC:T70.4
# acceptance: ACC:T70.7
func test_route_transitions_cover_all_m1_node_types_without_parallel_execution_path() -> void:
	var main := await _load_main_on_map()
	await _walk_m1_route(main, ["combat-01", "event-02", "shop-03", "rest-04"])

	var map = _current_scene_instance(main)
	var boss_enter := map.call("InvokeRouteNodeForTest", "boss-05") as Dictionary
	assert_bool(bool(boss_enter.get("ok", false))).is_true()
	assert_str(str(boss_enter.get("scene_path", ""))).is_equal(COMBAT_SCENE)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(5)
	assert_str(str(main.call("GetMapRouteLastStartDestinationForTest"))).is_equal(COMBAT_SCENE)

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(REWARD_SCENE)
	var reward_result := main.call("ResolveRewardForTest", "skip") as Dictionary
	assert_bool(bool(reward_result.get("ok", false))).is_true()
	assert_str(str(reward_result.get("outcome", ""))).is_equal("victory")
	assert_bool(bool(reward_result.get("menu_visible", false))).is_true()


# acceptance: ACC:T70.7
# acceptance: ACC:T86.4
func test_locked_future_floor_node_refuses_route_without_progress_mutation() -> void:
	var main := await _load_main_on_map()
	var map = _current_scene_instance(main)

	var before_count := int(main.call("GetMapRouteCompletedNodeCountForTest"))
	var before_start_invocations := int(main.call("GetMapRouteStartInvocationCountForTest"))
	var locked_result := map.call("InvokeRouteNodeForTest", "rest-04") as Dictionary

	assert_bool(bool(locked_result.get("ok", false))).is_false()
	assert_str(str(locked_result.get("reason", ""))).is_equal("node-not-reachable")
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(before_count)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(before_start_invocations)
	var feedback_text := str(map.call("GetFeedbackForTest"))
	assert_str(feedback_text).contains("rest-04")

	var disconnected_result := map.call("InvokeRouteNodeForTest", "boss-05") as Dictionary
	assert_bool(bool(disconnected_result.get("ok", false))).is_false()
	assert_str(str(disconnected_result.get("reason", ""))).is_equal("node-not-reachable")
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(before_count)
	assert_int(int(main.call("GetMapRouteStartInvocationCountForTest"))).is_equal(before_start_invocations)
	var disconnected_feedback := str(map.call("GetFeedbackForTest"))
	assert_str(disconnected_feedback).contains("boss-05")
