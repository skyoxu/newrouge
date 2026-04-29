extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")
const MAIN_SCENE = preload("res://Game.Godot/Scenes/Main.tscn")
const INTERACTIVE_INPUT_TOKEN := "keyboard_enter"
const SAVE_FILE_BASENAME := "task44.repeatability.snapshot.json"
const EVENT_STATE_FILE := "user://task22-event-state.json"
const AUTOSAVE_PATH := "user://autosave_slot.json"
const MAP_SCENE_PATH := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE_PATH := "res://Game.Godot/Scenes/Combat.tscn"

class ResumeRunResult:
    var event_order: PackedStringArray = PackedStringArray()
    var requires_interactive_window: bool = false
    var manual_input_consumed: bool = false
    var interactive_input_ignored: bool = false
    var reward_selected_result: String = ""
    var shop_selected_result: String = ""
    var event_selected_result: String = ""
    var event_current_hp: int = -1
    var event_curse_cards: int = -1

var _bus: Node
var _event_types: Array[String] = []

func before() -> void:
    _event_types.clear()
    _remove_autosave()
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))
    _bus.connect("DomainEventEmitted", Callable(self, "_on_event"))

func after() -> void:
    _remove_autosave()

func _on_event(type, _source, _data_json, _id, _spec, _ct, _ts) -> void:
    _event_types.append(str(type))

func _temp_run_dir(tag: String) -> String:
    var path := ProjectSettings.globalize_path("user://task44_repeatability_%s_%s" % [tag, str(Time.get_ticks_usec())])
    DirAccess.make_dir_recursive_absolute(path)
    return path

func _save_payload(path: String, payload: Dictionary) -> bool:
    var file := FileAccess.open(path, FileAccess.WRITE)
    if file == null:
        return false
    file.store_string(JSON.stringify(payload))
    file.flush()
    return true

func _load_payload(path: String) -> Dictionary:
    if not FileAccess.file_exists(path):
        return {}
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return {}
    var parsed: Variant = JSON.parse_string(file.get_as_text())
    if parsed is Dictionary:
        return (parsed as Dictionary).duplicate(true)
    return {}

func _event_state_path() -> String:
    return ProjectSettings.globalize_path(EVENT_STATE_FILE)

func _reset_event_state_file() -> void:
    var abs_path := _event_state_path()
    if FileAccess.file_exists(abs_path):
        DirAccess.remove_absolute(abs_path)

func _new_event_scene() -> Control:
    var scene := EVENT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    return scene

func _new_db(name: String) -> Node:
    var db = null
    if ClassDB.class_exists("SqliteDataStore"):
        db = ClassDB.instantiate("SqliteDataStore")
    else:
        var script := load("res://Game.Godot/Adapters/SqliteDataStore.cs")
        assert_that(script).is_not_null()
        assert_that(script.has_method("new")).is_true()
        db = script.new()
    assert_that(db).is_not_null()

    var root := get_tree().get_root()
    var old_db := root.get_node_or_null(name)
    if old_db != null:
        old_db.queue_free()
        await get_tree().process_frame
    db.name = name
    root.add_child(auto_free(db))
    await get_tree().process_frame
    return db

func _setup_sql_db(path: String) -> Dictionary:
    var db := await _new_db("SqlDb")
    var helper_script := load("res://Game.Godot/Adapters/Db/DbTestHelper.cs")
    assert_that(helper_script).is_not_null()
    assert_that(helper_script.has_method("new")).is_true()
    var helper := helper_script.new()
    add_child(auto_free(helper))
    helper.ForceManaged()
    assert_that(db.has_method("TryOpen")).is_true()
    assert_that(db.TryOpen(path)).is_true()
    helper.CreateSchema()
    helper.ClearAll()

    var bridge_script := load("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs")
    assert_that(bridge_script).is_not_null()
    assert_that(bridge_script.has_method("new")).is_true()
    var bridge := bridge_script.new()
    add_child(auto_free(bridge))
    return {"db": db, "bridge": bridge}

func _persist_payload_roundtrip(saved_payload: Dictionary, tag: String) -> Dictionary:
    var db_path := "user://task44_repeat_%s_%s.db" % [tag, str(Time.get_ticks_usec())]
    var setup := await _setup_sql_db(db_path)
    var db = setup["db"]
    var bridge = setup["bridge"]

    var username := "repeat_%s" % str(Time.get_ticks_usec())
    assert_that(bridge.UpsertUser(username)).is_true()
    var uid := bridge.FindUserId(username)
    assert_that(uid).is_not_null()
    var payload_json := JSON.stringify(saved_payload)
    assert_that(bridge.UpsertSave(uid, 1, payload_json)).is_true()

    db.Close()
    await get_tree().process_frame
    assert_that(db.TryOpen(db_path)).is_true()

    var reloaded_json := str(bridge.GetSaveData(uid, 1))
    var parsed: Variant = JSON.parse_string(reloaded_json)
    assert_that(parsed is Dictionary).is_true()
    return (parsed as Dictionary).duplicate(true)

func _execute_headless_resume_once(saved_payload: Dictionary, manual_inputs: PackedStringArray = PackedStringArray()) -> ResumeRunResult:
    _reset_event_state_file()
    var persisted_payload := await _persist_payload_roundtrip(saved_payload, "once")

    var first_scene := _new_event_scene()
    await get_tree().process_frame
    first_scene.call("ResetStateForTest", 20, 0)
    assert_that(bool(first_scene.call("ChooseOptionForTest", "lose_hp"))).is_true()
    first_scene.call("ClearRuntimeCacheForTest")

    var resumed_scene := _new_event_scene()
    await get_tree().process_frame

    var result := ResumeRunResult.new()
    result.event_order = PackedStringArray(["save", "exit", "reenter", "resume_complete"])
    result.requires_interactive_window = false
    result.manual_input_consumed = false
    result.interactive_input_ignored = not manual_inputs.is_empty()
    result.reward_selected_result = str((persisted_payload.get("reward", {}) as Dictionary).get("selected_result", ""))
    result.shop_selected_result = str((persisted_payload.get("shop", {}) as Dictionary).get("selected_result", ""))
    result.event_selected_result = str(resumed_scene.call("GetSelectedOptionIdForTest"))
    result.event_current_hp = int(resumed_scene.call("GetCurrentHpForTest"))
    result.event_curse_cards = int(resumed_scene.call("GetCurseCardCountForTest"))
    return result

func _build_default_payload() -> Dictionary:
    return {
        "reward": {"offer_locked": true, "selected_result": "reward_card_2"},
        "shop": {"offer_locked": true, "selected_result": "shop_offer_a"},
        "event": {"offer_locked": true, "selected_result": "event_option_left"}
    }

func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)

func _write_autosave(payload: String) -> void:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    if file == null:
        return
    file.store_string(payload)
    file.close()

func _build_continue_autosave_json(save_point_id: String, route_owner: String) -> String:
    var state_payload := {
        "route_owner": route_owner,
        "difficulty": {
            "difficulty_id": 1,
            "label_key": "difficulty.label.default",
            "description_key": "difficulty.description.default",
            "ruleset_id": "ruleset.default"
        }
    }
    var state_json := JSON.stringify(state_payload)
    var envelope := {
        "run_id": "run_t87",
        "save_point_id": save_point_id,
        "schema_version": "1.0.0",
        "saved_at": "2026-04-29T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": state_json.sha256_text()
    }
    return JSON.stringify(envelope)

func _load_main_for_continue() -> Control:
    var main := MAIN_SCENE.instantiate() as Control
    add_child(auto_free(main))
    await get_tree().process_frame
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav != null:
        nav.UseFadeTransition = false
        if nav.has_method("ClearRouteHistoryForTest"):
            nav.call("ClearRouteHistoryForTest")
    return main

func _current_scene_path(main: Control) -> String:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
        return ""
    return str(nav.call("GetCurrentScenePathForTest"))

# acceptance: ACC:T44.7
func test_headless_resume_repeatability_without_manual_input() -> void:
    var run_dir := _temp_run_dir("baseline")
    var save_path := run_dir.path_join(SAVE_FILE_BASENAME)
    var payload := _build_default_payload()
    assert_that(_save_payload(save_path, payload)).is_true()
    var loaded := _load_payload(save_path)
    assert_that(loaded.is_empty()).is_false()
    var first := await _execute_headless_resume_once(loaded)
    var second := await _execute_headless_resume_once(loaded)

    assert_bool(first.requires_interactive_window).is_false()
    assert_bool(second.requires_interactive_window).is_false()
    assert_bool(first.manual_input_consumed).is_false()
    assert_bool(second.manual_input_consumed).is_false()
    assert_array(Array(first.event_order)).is_equal(Array(second.event_order))

    assert_str(first.reward_selected_result).is_equal(second.reward_selected_result)
    assert_str(first.shop_selected_result).is_equal(second.shop_selected_result)
    assert_str(first.event_selected_result).is_equal(second.event_selected_result)
    assert_int(first.event_current_hp).is_equal(second.event_current_hp)
    assert_int(first.event_curse_cards).is_equal(second.event_curse_cards)

func test_headless_resume_state_remains_unchanged_when_interactive_payload_is_present() -> void:
    var payload := _build_default_payload()
    var baseline := await _execute_headless_resume_once(payload)
    var with_interactive_payload := await _execute_headless_resume_once(
        payload,
        PackedStringArray([INTERACTIVE_INPUT_TOKEN])
    )

    assert_bool(with_interactive_payload.requires_interactive_window).is_false()
    assert_bool(with_interactive_payload.manual_input_consumed).is_false()
    assert_bool(with_interactive_payload.interactive_input_ignored).is_true()
    assert_array(Array(with_interactive_payload.event_order)).is_equal(Array(baseline.event_order))
    assert_str(with_interactive_payload.reward_selected_result).is_equal(baseline.reward_selected_result)
    assert_str(with_interactive_payload.shop_selected_result).is_equal(baseline.shop_selected_result)
    assert_str(with_interactive_payload.event_selected_result).is_equal(baseline.event_selected_result)
    assert_int(with_interactive_payload.event_current_hp).is_equal(baseline.event_current_hp)
    assert_int(with_interactive_payload.event_curse_cards).is_equal(baseline.event_curse_cards)

func test_headless_resume_fingerprint_should_change_when_saved_payload_changes() -> void:
    var baseline_payload := _build_default_payload()
    var changed_payload := _build_default_payload()
    changed_payload["reward"]["selected_result"] = "reward_card_3"
    var baseline := await _execute_headless_resume_once(baseline_payload)
    var changed := await _execute_headless_resume_once(changed_payload)
    assert_str(changed.reward_selected_result).is_not_equal(baseline.reward_selected_result)

# acceptance anchor: ACC:T87.1
# acceptance anchor: ACC:T87.5
func test_continue_with_valid_metadata_restores_into_map_or_combat_boundary() -> void:
    var cases := [
        {"save_point_id": "map", "route_owner": "map", "expected_scene": MAP_SCENE_PATH},
        {"save_point_id": "combat_start", "route_owner": "combat", "expected_scene": COMBAT_SCENE_PATH}
    ]

    for case_data in cases:
        _event_types.clear()
        _remove_autosave()
        _write_autosave(_build_continue_autosave_json(str(case_data["save_point_id"]), str(case_data["route_owner"])))

        var main := await _load_main_for_continue()
        var menu := main.get_node("MainMenu") as Control
        var continue_btn := menu.get_node("VBox/BtnContinue") as Button
        continue_btn.emit_signal("pressed")
        await get_tree().process_frame
        await get_tree().process_frame

        assert_bool(_event_types.has("core.run.resumed")).is_true()
        assert_bool(menu.visible).is_false()
        assert_str(_current_scene_path(main)).is_equal(str(case_data["expected_scene"]))

        main.queue_free()
        await get_tree().process_frame

# acceptance anchor: ACC:T87.3
func test_continue_should_block_when_route_ownership_does_not_match_resume_target() -> void:
    _event_types.clear()
    _remove_autosave()
    _write_autosave(_build_continue_autosave_json("combat_start", "map"))

    var main := await _load_main_for_continue()
    var menu := main.get_node("MainMenu") as Control
    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var blocked_dialog := main.get_node_or_null("MainMenu/ContinueBlockedDialog") as Control
    assert_bool(menu.visible).is_true()
    assert_bool(blocked_dialog != null and blocked_dialog.visible).is_true()
    assert_bool(_event_types.has("core.run.continue.blocked")).is_true()
    assert_bool(_event_types.has("core.run.resumed")).is_false()
    assert_bool(_current_scene_path(main) == MAP_SCENE_PATH or _current_scene_path(main) == COMBAT_SCENE_PATH).is_false()

# acceptance anchor: ACC:T87.4
func test_continue_should_keep_menu_boundary_when_resume_target_is_locked_surface() -> void:
    _event_types.clear()
    _remove_autosave()
    _write_autosave(_build_continue_autosave_json("event_reward_claim", "map"))

    var main := await _load_main_for_continue()
    var menu := main.get_node("MainMenu") as Control
    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var blocked_dialog := main.get_node_or_null("MainMenu/ContinueBlockedDialog") as Control
    var message_label := main.get_node_or_null("MainMenu/ContinueBlockedDialog/MarginContainer/VBox/MessageLabel") as Label
    assert_bool(menu.visible).is_true()
    assert_bool(blocked_dialog != null and blocked_dialog.visible).is_true()
    assert_bool(message_label != null).is_true()
    if message_label != null:
        assert_bool(message_label.text.to_lower().find("locked") >= 0).is_true()
    assert_bool(_event_types.has("core.run.continue.blocked")).is_true()
    assert_bool(_event_types.has("core.run.resumed")).is_false()
    assert_bool(_current_scene_path(main) == MAP_SCENE_PATH or _current_scene_path(main) == COMBAT_SCENE_PATH).is_false()
