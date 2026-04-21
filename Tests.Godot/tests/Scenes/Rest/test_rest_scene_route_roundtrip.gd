extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"

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


func _route_history(main: Control) -> Array[String]:
	var nav := main.get_node_or_null("ScreenNavigator")
	if nav == null or not nav.has_method("GetRouteHistoryForTest"):
		return []
	var route_variant = nav.call("GetRouteHistoryForTest")
	var history: Array[String] = []
	for item in route_variant:
		history.append(str(item))
	return history


func _enter_rest_scene(main: Control) -> Node:
	var enter_result := main.call("StartMapNodeRouteForTest", "rest-01", "rest", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(REST_SCENE)
	await get_tree().process_frame

	var root := main.get_node_or_null("ScreenRoot")
	assert_object(root).is_not_null()
	assert_int(root.get_child_count()).is_greater(0)
	return root.get_child(root.get_child_count() - 1)


# acceptance: ACC:T62.1
func test_rest_route_uses_real_standalone_scene_and_not_placeholder() -> void:
	assert_bool(ResourceLoader.exists(REST_SCENE)).is_true()

	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_object(rest).is_not_null()
	assert_str(_current_scene_path(main)).is_equal(REST_SCENE)
	assert_bool(_route_history(main).has(REST_SCENE)).is_true()


# acceptance: ACC:T62.2
func test_rest_scene_exposes_heal_upgrade_and_curse_removal_choices() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("GetAvailableOptionsForTest")).is_true()
	var options_variant = rest.call("GetAvailableOptionsForTest")
	var options: Array[String] = []
	for item in options_variant:
		options.append(str(item))

	assert_bool(options.has("heal")).is_true()
	assert_bool(options.has("upgrade")).is_true()
	assert_bool(options.has("remove_curse")).is_true()
	assert_int(options.size()).is_equal(3)


# acceptance: ACC:T62.3
func test_heal_from_rest_returns_to_map_with_valid_post_rest_route() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("SelectOptionForTest")).is_true()
	assert_bool(rest.has_method("GetNextRouteForTest")).is_true()
	assert_bool(bool(rest.call("SelectOptionForTest", "heal"))).is_true()
	assert_str(str(rest.call("GetNextRouteForTest"))).is_equal("map")

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(1)

	var history := _route_history(main)
	assert_bool(history.has(REST_SCENE)).is_true()
	assert_bool(history.has(MAP_SCENE)).is_true()


# acceptance: ACC:T62.5
func test_remove_curse_from_rest_applies_result_and_returns_to_map() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("SelectOptionForTest")).is_true()
	assert_bool(rest.has_method("WasCurseRemovedForTest")).is_true()
	assert_bool(rest.has_method("GetNextRouteForTest")).is_true()

	assert_bool(bool(rest.call("WasCurseRemovedForTest"))).is_false()
	assert_bool(bool(rest.call("SelectOptionForTest", "remove_curse"))).is_true()
	assert_bool(bool(rest.call("WasCurseRemovedForTest"))).is_true()
	assert_str(str(rest.call("GetNextRouteForTest"))).is_equal("map")

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(1)
