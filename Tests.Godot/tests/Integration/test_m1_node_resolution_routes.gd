extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"
const SHOP_SCENE := "res://Game.Godot/Scenes/Shop.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"

var _bus: Node


func before() -> void:
    _bus = EVENT_BUS_SCRIPT.new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))


func _load_main() -> Control:
    var main := MAIN_SCENE.instantiate() as Control
    add_child(auto_free(main))
    await get_tree().process_frame

    var nav := main.get_node_or_null("ScreenNavigator")
    if nav != null:
        nav.UseFadeTransition = false
        if nav.has_method("ClearRouteHistoryForTest"):
            nav.call("ClearRouteHistoryForTest")
        nav.call("SwitchTo", MAP_SCENE)
    await get_tree().process_frame

    main.call("ResetMapRouteProgressForTest")
    return main


func _route_history(main: Control) -> Array[String]:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetRouteHistoryForTest"):
        return []
    var route_variant = nav.call("GetRouteHistoryForTest")
    var history: Array[String] = []
    for item in route_variant:
        history.append(str(item))
    return history


func _current_scene_path(main: Control) -> String:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
        return ""
    return str(nav.call("GetCurrentScenePathForTest"))


func _start_route(main: Control, node_id: String, node_type: String, reachable: bool, reason: String = "") -> Dictionary:
    return main.call("StartMapNodeRouteForTest", node_id, node_type, reachable, reason) as Dictionary


func _complete_route(main: Control) -> Dictionary:
    return main.call("CompleteMapNodeFlowForTest") as Dictionary


# acceptance: ACC:T60.1
func test_selectable_map_node_becomes_actionable_route_entry() -> void:
    var main := await _load_main()

    var result := _start_route(main, "combat-01", "combat", true)

    assert_bool(bool(result.get("ok", false))).is_true()
    assert_str(str(result.get("scene_path", ""))).is_equal(COMBAT_SCENE)
    assert_str(_current_scene_path(main)).is_equal(COMBAT_SCENE)


# acceptance: ACC:T60.2
func test_reachable_node_enters_owned_flow_and_returns_to_map_after_completion() -> void:
    var main := await _load_main()

    var enter_result := _start_route(main, "shop-01", "shop", true)
    await get_tree().process_frame
    var complete_result := _complete_route(main)
    await get_tree().process_frame

    assert_bool(bool(enter_result.get("ok", false))).is_true()
    assert_str(str(enter_result.get("scene_path", ""))).is_equal(SHOP_SCENE)
    assert_bool(bool(complete_result.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(main.call("GetMapRouteCompletedNodeCountForTest")).is_equal(1)


# acceptance: ACC:T60.3
func test_unreachable_node_refuses_transition_and_keeps_progress_unchanged_with_feedback() -> void:
    var main := await _load_main()

    var before_count := int(main.call("GetMapRouteCompletedNodeCountForTest"))
    var result := _start_route(main, "event-locked", "event", false, "RouteBlocked")

    assert_bool(bool(result.get("ok", false))).is_false()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_str(str(main.call("GetMapRouteLastFeedbackForTest"))).is_equal("RouteBlocked")
    assert_int(main.call("GetMapRouteCompletedNodeCountForTest")).is_equal(before_count)


# acceptance: ACC:T60.3
func test_illegal_node_type_refuses_transition_with_explicit_reason_and_unchanged_progress() -> void:
    var main := await _load_main()

    var before_count := int(main.call("GetMapRouteCompletedNodeCountForTest"))
    var result := _start_route(main, "illegal-01", "unknown-type", true)

    assert_bool(bool(result.get("ok", false))).is_false()
    assert_str(str(result.get("reason", ""))).is_equal("unsupported-node-type")
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(main.call("GetMapRouteCompletedNodeCountForTest")).is_equal(before_count)


# acceptance: ACC:T60.4
func test_event_node_type_resolves_to_real_event_scene_not_placeholder() -> void:
    var main := await _load_main()

    var result := _start_route(main, "event-01", "event", true)

    assert_bool(bool(result.get("ok", false))).is_true()
    assert_str(str(result.get("scene_path", ""))).is_equal(EVENT_SCENE)
    assert_str(_current_scene_path(main)).is_equal(EVENT_SCENE)


# acceptance: ACC:T60.5
func test_map_route_transitions_keep_node_boundary_rules_for_completion_or_refusal() -> void:
    var main := await _load_main()

    var enter_result := _start_route(main, "rest-01", "rest", true)
    await get_tree().process_frame
    var complete_result := _complete_route(main)
    await get_tree().process_frame
    var blocked_result := _start_route(main, "rest-locked", "rest", false, "NodeLockedByRule")

    assert_bool(bool(enter_result.get("ok", false))).is_true()
    assert_str(str(enter_result.get("scene_path", ""))).is_equal(REST_SCENE)
    assert_bool(bool(complete_result.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_bool(bool(blocked_result.get("ok", false))).is_false()
    assert_str(str(main.call("GetMapRouteLastFeedbackForTest"))).is_equal("NodeLockedByRule")


# acceptance: ACC:T60.6
func test_map_route_smoke_reaches_combat_event_shop_and_rest_owned_flows() -> void:
    var main := await _load_main()
    var expected_routes: Array[Dictionary] = [
        {"id": "combat-01", "type": "combat", "scene": COMBAT_SCENE},
        {"id": "event-01", "type": "event", "scene": EVENT_SCENE},
        {"id": "shop-01", "type": "shop", "scene": SHOP_SCENE},
        {"id": "rest-01", "type": "rest", "scene": REST_SCENE}
    ]

    for expected in expected_routes:
        var result := _start_route(main, str(expected.get("id", "")), str(expected.get("type", "")), true)
        await get_tree().process_frame
        assert_bool(bool(result.get("ok", false))).is_true()
        assert_str(str(result.get("scene_path", ""))).is_equal(str(expected.get("scene", "")))
        _complete_route(main)
        await get_tree().process_frame


# acceptance: ACC:T60.7
func test_each_map_started_route_returns_to_map_or_refuses_with_explicit_reason() -> void:
    var main := await _load_main()

    var ok_result := _start_route(main, "combat-02", "combat", true)
    await get_tree().process_frame
    var completion_result := _complete_route(main)
    await get_tree().process_frame
    var count_after_ok := int(main.call("GetMapRouteCompletedNodeCountForTest"))
    var blocked_result := _start_route(main, "event-locked", "event", false, "RouteBlocked")

    assert_bool(bool(ok_result.get("ok", false))).is_true()
    assert_bool(bool(completion_result.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(count_after_ok).is_equal(1)

    assert_bool(bool(blocked_result.get("ok", false))).is_false()
    assert_str(str(main.call("GetMapRouteLastFeedbackForTest"))).is_equal("RouteBlocked")
    assert_int(main.call("GetMapRouteCompletedNodeCountForTest")).is_equal(count_after_ok)
    assert_bool(_route_history(main).has(EVENT_SCENE)).is_false()
