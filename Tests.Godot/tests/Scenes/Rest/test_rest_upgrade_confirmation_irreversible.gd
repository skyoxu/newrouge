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


func _enter_rest_scene(main: Control) -> Node:
	var enter_result := main.call("StartMapNodeRouteForTest", "rest-01", "rest", true, "") as Dictionary
	assert_bool(bool(enter_result.get("ok", false))).is_true()
	assert_str(str(enter_result.get("scene_path", ""))).is_equal(REST_SCENE)
	await get_tree().process_frame

	var root := main.get_node_or_null("ScreenRoot")
	assert_object(root).is_not_null()
	assert_int(root.get_child_count()).is_greater(0)
	return root.get_child(root.get_child_count() - 1)


func _current_scene_path(main: Control) -> String:
	var nav := main.get_node_or_null("ScreenNavigator")
	if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
		return ""
	return str(nav.call("GetCurrentScenePathForTest"))


func _route_history(main: Control) -> Array[String]:
	var nav := main.get_node_or_null("ScreenNavigator")
	if nav == null or not nav.has_method("GetRouteHistoryForTest"):
		return []
	var history_variant = nav.call("GetRouteHistoryForTest")
	var history: Array[String] = []
	for item in history_variant:
		history.append(str(item))
	return history


# acceptance: ACC:T21.5
# acceptance: ACC:T62.4
func test_confirmed_upgrade_cannot_be_undone_in_same_flow() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("SelectOptionForTest")).is_true()
	assert_bool(rest.has_method("ConfirmUpgradeForTest")).is_true()
	assert_bool(rest.has_method("RequestUndoAfterConfirmForTest")).is_true()
	assert_bool(rest.has_method("IsUpgradeConfirmedForTest")).is_true()
	assert_bool(rest.has_method("GetNextRouteForTest")).is_true()

	assert_bool(bool(rest.call("SelectOptionForTest", "upgrade"))).is_true()
	assert_bool(bool(rest.call("ConfirmUpgradeForTest"))).is_true()
	var undo_accepted := bool(rest.call("RequestUndoAfterConfirmForTest"))

	assert_bool(undo_accepted).is_false()
	assert_bool(bool(rest.call("IsUpgradeConfirmedForTest"))).is_true()
	assert_str(str(rest.call("GetNextRouteForTest"))).is_equal("map")

	var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_bool(bool(complete_result.get("ok", false))).is_true()
	assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
	assert_bool(_route_history(main).has(REST_SCENE)).is_true()
	assert_bool(_route_history(main).has(MAP_SCENE)).is_true()


# acceptance: ACC:T21.5
func test_confirmed_upgrade_refuses_restore_to_pre_upgrade_state() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("SelectOptionForTest")).is_true()
	assert_bool(rest.has_method("ConfirmUpgradeForTest")).is_true()
	assert_bool(rest.has_method("RequestRestorePreUpgradeSnapshotForTest")).is_true()
	assert_bool(rest.has_method("GetFeedbackForTest")).is_true()

	assert_bool(bool(rest.call("SelectOptionForTest", "upgrade"))).is_true()
	assert_bool(bool(rest.call("ConfirmUpgradeForTest"))).is_true()
	var restore_accepted := bool(rest.call("RequestRestorePreUpgradeSnapshotForTest"))

	assert_bool(restore_accepted).is_false()
	assert_str(str(rest.call("GetFeedbackForTest"))).is_equal("Upgrade confirmed.")


# acceptance: ACC:T62.4
func test_cancel_before_upgrade_confirmation_keeps_upgrade_target_unmodified_and_not_committed() -> void:
	var main := await _load_main_on_map()
	var rest := await _enter_rest_scene(main)

	assert_bool(rest.has_method("SelectOptionForTest")).is_true()
	assert_bool(rest.has_method("CancelUpgradeForTest")).is_true()
	assert_bool(rest.has_method("IsUpgradeConfirmPendingForTest")).is_true()
	assert_bool(rest.has_method("IsUpgradeConfirmedForTest")).is_true()
	assert_bool(rest.has_method("WasUpgradeTargetMutatedForTest")).is_true()
	assert_bool(rest.has_method("GetNextRouteForTest")).is_true()

	assert_bool(bool(rest.call("SelectOptionForTest", "upgrade"))).is_true()
	assert_bool(bool(rest.call("IsUpgradeConfirmPendingForTest"))).is_true()
	assert_bool(bool(rest.call("CancelUpgradeForTest"))).is_true()

	assert_bool(bool(rest.call("IsUpgradeConfirmPendingForTest"))).is_false()
	assert_bool(bool(rest.call("IsUpgradeConfirmedForTest"))).is_false()
	assert_bool(bool(rest.call("WasUpgradeTargetMutatedForTest"))).is_false()
	assert_str(str(rest.call("GetNextRouteForTest"))).is_equal("")
	assert_str(_current_scene_path(main)).is_equal(REST_SCENE)
