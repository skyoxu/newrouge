extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const DIFFICULTY_SELECT_SCENE := "res://Game.Godot/Scenes/UI/DifficultySelect.tscn"
const CHARACTER_SELECT_SCENE := "res://Game.Godot/Scenes/UI/CharacterSelect.tscn"
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const START_SCREEN_SCENE := "res://Game.Godot/Scenes/Screens/StartScreen.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"
const MAIN_SCENE_PATH := "res://Game.Godot/Scenes/Main.tscn"

var _bus: Node
var _event_types: Array[String] = []


func before() -> void:
    _event_types.clear()
    _bus = EVENT_BUS_SCRIPT.new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))
    _bus.connect("DomainEventEmitted", Callable(self, "_on_event"))


func _on_event(type, _source, _data_json, _id, _spec, _ct, _ts) -> void:
    _event_types.append(str(type))


func _load_main() -> Control:
    var main := MAIN_SCENE.instantiate() as Control
    add_child(auto_free(main))
    await get_tree().process_frame
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav != null:
        nav.UseFadeTransition = false
        if nav.has_method("ClearRouteHistoryForTest"):
            nav.call("ClearRouteHistoryForTest")
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


func _press_new_run(main: Control) -> void:
    var menu := main.get_node("MainMenu") as Control
    menu.call("SetAutosaveAvailableForTest", false)
    var button := menu.get_node("VBox/BtnNewRun") as Button
    button.emit_signal("pressed")


func _difficulty_node(main: Control) -> Control:
    var root := main.get_node("ScreenRoot") as Node
    assert_int(root.get_child_count()).is_greater(0)
    var node := root.get_child(root.get_child_count() - 1) as Control
    assert_object(node).is_not_null()
    return node


func _character_node(main: Control) -> Control:
    var root := main.get_node("ScreenRoot") as Node
    assert_int(root.get_child_count()).is_greater(0)
    var node := root.get_child(root.get_child_count() - 1) as Control
    assert_object(node).is_not_null()
    return node


# acceptance: ACC:T59.1
func test_new_run_from_main_menu_opens_difficulty_first_and_skips_demo_screens() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame

    var history := _route_history(main)
    assert_int(history.size()).is_greater_equal(1)
    assert_str(history[0]).is_equal(DIFFICULTY_SELECT_SCENE)
    assert_bool(history.has(START_SCREEN_SCENE)).is_false()
    assert_bool(history.has(DEMO_SCENE)).is_false()


# acceptance: ACC:T59.3
func test_confirming_m1_character_routes_to_map_without_placeholder_or_demo_screens() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame
    var difficulty := _difficulty_node(main)
    difficulty.call("SelectDifficultyForTest", 3)
    difficulty.call("ConfirmSelectionForTest")
    await get_tree().process_frame
    var character := _character_node(main)
    character.call("SelectCharacterForTest", "warrior")
    character.call("ConfirmSelectedCharacterForTest")
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(MAP_SCENE)
    assert_bool(history.has(START_SCREEN_SCENE)).is_false()
    assert_bool(history.has(DEMO_SCENE)).is_false()


# acceptance: ACC:T59.3
func test_selecting_character_without_confirm_keeps_route_on_character_select() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame
    var difficulty := _difficulty_node(main)
    difficulty.call("SelectDifficultyForTest", 3)
    difficulty.call("ConfirmSelectionForTest")
    await get_tree().process_frame
    var character := _character_node(main)
    character.call("SelectCharacterForTest", "warrior")
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(CHARACTER_SELECT_SCENE)
    assert_bool(history.has(MAP_SCENE)).is_false()


# acceptance: ACC:T59.2
func test_confirming_difficulty_routes_next_to_character_select_and_not_map_or_demo_targets() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame
    var difficulty := _difficulty_node(main)
    difficulty.call("SelectDifficultyForTest", 5)
    difficulty.call("ConfirmSelectionForTest")
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(CHARACTER_SELECT_SCENE)
    assert_bool(history.has(MAP_SCENE)).is_false()
    assert_bool(history.has(START_SCREEN_SCENE)).is_false()
    assert_bool(history.has(DEMO_SCENE)).is_false()


# acceptance: ACC:T59.2
func test_selecting_difficulty_without_confirm_keeps_route_on_difficulty_select() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame
    var difficulty := _difficulty_node(main)
    difficulty.call("SelectDifficultyForTest", 5)
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(DIFFICULTY_SELECT_SCENE)
    assert_bool(history.has(CHARACTER_SELECT_SCENE)).is_false()
    assert_bool(history.has(MAP_SCENE)).is_false()


# acceptance: ACC:T59.5
func test_m1_run_entry_smoke_flow_main_menu_to_difficulty_to_character_to_map() -> void:
    var main := await _load_main()

    _press_new_run(main)
    await get_tree().process_frame
    var difficulty := _difficulty_node(main)
    difficulty.call("SelectDifficultyForTest", 2)
    difficulty.call("ConfirmSelectionForTest")
    await get_tree().process_frame
    var character := _character_node(main)
    character.call("SelectCharacterForTest", "warrior")
    character.call("ConfirmSelectedCharacterForTest")
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(MAP_SCENE)
    assert_array(history).is_equal([DIFFICULTY_SELECT_SCENE, CHARACTER_SELECT_SCENE, MAP_SCENE])
    assert_bool(_event_types.has("core.run.started")).is_true()


# acceptance: ACC:T59.4
func test_without_autosave_continue_stays_disabled_and_new_run_does_not_open_overwrite_dialog() -> void:
    var main := await _load_main()
    var menu := main.get_node("MainMenu") as Control
    menu.call("SetAutosaveAvailableForTest", false)
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    assert_bool(continue_btn.disabled).is_true()

    var new_run_btn := menu.get_node("VBox/BtnNewRun") as Button
    new_run_btn.emit_signal("pressed")
    await get_tree().process_frame

    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    assert_bool(dialog == null or not dialog.visible).is_true()


# acceptance: ACC:T59.4
func test_with_autosave_cancel_keeps_current_scene_on_main() -> void:
    var main := await _load_main()
    var menu := main.get_node("MainMenu") as Control
    menu.call("SetAutosaveAvailableForTest", true)
    await get_tree().process_frame

    var new_run_btn := menu.get_node("VBox/BtnNewRun") as Button
    new_run_btn.emit_signal("pressed")
    await get_tree().process_frame

    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    assert_object(dialog).is_not_null()
    if dialog != null:
        dialog.emit_signal("canceled")
    await get_tree().process_frame

    assert_bool(menu.visible).is_true()
    assert_str(_current_scene_path(main)).is_equal("")
    assert_array(_route_history(main)).is_empty()


# acceptance: ACC:T59.4
func test_with_autosave_confirm_routes_to_difficulty_select_not_demo_targets() -> void:
    var main := await _load_main()
    var menu := main.get_node("MainMenu") as Control
    menu.call("SetAutosaveAvailableForTest", true)
    await get_tree().process_frame

    var new_run_btn := menu.get_node("VBox/BtnNewRun") as Button
    new_run_btn.emit_signal("pressed")
    await get_tree().process_frame

    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    assert_object(dialog).is_not_null()
    if dialog != null:
        dialog.emit_signal("confirmed")
    await get_tree().process_frame

    var current := _current_scene_path(main)
    var history := _route_history(main)
    assert_str(current).is_equal(DIFFICULTY_SELECT_SCENE)
    assert_int(history.size()).is_greater_equal(1)
    assert_str(history[0]).is_equal(DIFFICULTY_SELECT_SCENE)
    assert_bool(history.has(START_SCREEN_SCENE)).is_false()
    assert_bool(history.has(DEMO_SCENE)).is_false()
    assert_bool(history.has(MAIN_SCENE_PATH)).is_false()
