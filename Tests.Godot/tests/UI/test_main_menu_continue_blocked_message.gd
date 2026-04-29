extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

# RED-FIRST: this suite defines the blocked-state UX contract for Continue failures.
# acceptance anchor: ACC:T87.5

const AUTOSAVE_PATH := "user://autosave_slot.json"
const MAIN_MENU_SCENE := preload("res://Game.Godot/Scenes/UI/MainMenu.tscn")
const BLOCKED_DIALOG_PATH := "ContinueBlockedDialog"
const BLOCKED_MESSAGE_PATH := "ContinueBlockedDialog/MarginContainer/VBox/MessageLabel"
const BLOCKED_NEW_RUN_PATH := "ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnNewRun"
const BLOCKED_CANCEL_PATH := "ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnCancel"
const BLOCKED_RETURN_PATH := "ContinueBlockedDialog/MarginContainer/VBox/ButtonRow/BtnReturnToMenu"

var _bus: Node
var _events: Array[String] = []
var _previous_locale := ""

func before() -> void:
    _previous_locale = TranslationServer.get_locale()
    TranslationServer.set_locale("en")
    _remove_autosave()
    _events.clear()
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))
    _bus.connect("DomainEventEmitted", Callable(self, "_on_event"))

func after() -> void:
    _remove_autosave()
    if _previous_locale != "":
        TranslationServer.set_locale(_previous_locale)

func _on_event(type, _source, _data_json, _id, _spec, _ct, _ts) -> void:
    _events.append(str(type))

func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)

func _write_autosave(payload: String) -> void:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    file.store_string(payload)
    file.close()

func _build_invalid_integrity_autosave_json() -> String:
    return "{\"run_id\":\"run_t63\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"2026-04-21T00:00:00Z\",\"state_json\":\"{}\",\"integrity_hash\":\"broken\"}"

func _build_migration_failure_autosave_json() -> String:
    return "{\"run_id\":\"run_t63\",\"save_point_id\":\"menu\",\"schema_version\":\"999.0.0\",\"saved_at\":\"2026-04-21T00:00:00Z\",\"state_json\":\"{}\",\"integrity_hash\":\"abc123\"}"

func _build_locked_surface_autosave_json() -> String:
    var state_payload := {
        "route_owner": "map",
        "difficulty": {
            "difficulty_id": 1,
            "label_key": "difficulty.label.default",
            "description_key": "difficulty.description.default",
            "ruleset_id": "ruleset.default"
        }
    }
    var state_json := JSON.stringify(state_payload)
    var envelope := {
        "run_id": "run_t87_locked_surface",
        "save_point_id": "reward_pick",
        "schema_version": "1.0.0",
        "saved_at": "2026-04-29T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": state_json.sha256_text()
    }
    return JSON.stringify(envelope)

func _prepare_continue_blocked_case(mode: String) -> void:
    _remove_autosave()
    if mode == "missing":
        return
    if mode == "invalid_integrity":
        _write_autosave(_build_invalid_integrity_autosave_json())
        return
    if mode == "migration_failure":
        _write_autosave(_build_migration_failure_autosave_json())
        return
    if mode == "locked_surface":
        _write_autosave(_build_locked_surface_autosave_json())
        return

func _instantiate_menu() -> Control:
    var menu := MAIN_MENU_SCENE.instantiate() as Control
    add_child(auto_free(menu))
    return menu

func _blocked_message_text(menu: Control) -> String:
    var message_node := menu.get_node_or_null(BLOCKED_MESSAGE_PATH)
    if message_node == null:
        return ""
    return str(message_node.get("text")).strip_edges()

func _assert_blocked_feedback(menu: Control, expected_reason_fragment: String) -> void:
    var dialog := menu.get_node_or_null(BLOCKED_DIALOG_PATH) as Control
    var message_node := menu.get_node_or_null(BLOCKED_MESSAGE_PATH)

    assert_bool(dialog != null).is_true()
    assert_bool(message_node != null).is_true()
    if dialog == null or message_node == null:
        return

    assert_bool(dialog.visible).is_true()
    var message_text := str(message_node.get("text")).to_lower()
    assert_bool(message_text.length() > 0).is_true()
    assert_bool(message_text.find(expected_reason_fragment.to_lower()) >= 0).is_true()

func _assert_no_resume_or_start_events() -> void:
    assert_bool(_events.has("core.run.resumed")).is_false()
    assert_bool(_events.has("core.run.started")).is_false()

# ACC:T63.1
func test_continue_blocked_message_names_reason_for_missing_invalid_and_migration_failures() -> void:
    var cases := [
        {"mode": "missing", "expected_reason": "no save"},
        {"mode": "invalid_integrity", "expected_reason": "integrity"},
        {"mode": "migration_failure", "expected_reason": "migration"}
    ]

    for case_data in cases:
        _events.clear()
        _prepare_continue_blocked_case(str(case_data["mode"]))

        var menu := _instantiate_menu()
        await get_tree().process_frame

        var continue_btn := menu.get_node("VBox/BtnContinue") as Button
        continue_btn.emit_signal("pressed")
        await get_tree().process_frame
        await get_tree().process_frame

        assert_bool(menu.visible).is_true()
        assert_bool(_events.has("core.run.resumed")).is_false()
        _assert_blocked_feedback(menu, str(case_data["expected_reason"]))

        menu.queue_free()
        await get_tree().process_frame

# ACC:T63.2
# acceptance anchor: ACC:T87.2
func test_continue_blocked_state_exposes_recovery_actions_without_dismissing_feedback() -> void:
    _prepare_continue_blocked_case("locked_surface")

    var menu := _instantiate_menu()
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var dialog := menu.get_node_or_null(BLOCKED_DIALOG_PATH) as Control
    var new_run_btn := menu.get_node_or_null(BLOCKED_NEW_RUN_PATH) as Button
    var cancel_btn := menu.get_node_or_null(BLOCKED_CANCEL_PATH) as Button
    var return_btn := menu.get_node_or_null(BLOCKED_RETURN_PATH) as Button

    assert_bool(dialog != null).is_true()
    assert_bool(new_run_btn != null).is_true()
    assert_bool(cancel_btn != null).is_true()
    assert_bool(return_btn != null).is_true()
    if dialog == null or new_run_btn == null or cancel_btn == null or return_btn == null:
        return

    assert_bool(dialog.visible).is_true()
    assert_bool(new_run_btn.visible).is_true()
    assert_bool(cancel_btn.visible).is_true()
    assert_bool(return_btn.visible).is_true()
    assert_bool(_blocked_message_text(menu).length() > 0).is_true()
    assert_bool(_blocked_message_text(menu).to_lower().find("locked") >= 0).is_true()

    _events.clear()
    cancel_btn.emit_signal("pressed")
    await get_tree().process_frame

    assert_bool(menu.visible).is_true()
    assert_bool(dialog.visible).is_false()
    assert_bool(_blocked_message_text(menu).to_lower().find("locked") >= 0).is_true()
    _assert_no_resume_or_start_events()

    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    assert_bool(dialog.visible).is_true()
    _events.clear()
    return_btn.emit_signal("pressed")
    await get_tree().process_frame

    assert_bool(menu.visible).is_true()
    assert_bool(dialog.visible).is_false()
    assert_bool(_blocked_message_text(menu).to_lower().find("locked") >= 0).is_true()
    _assert_no_resume_or_start_events()

# ACC:T63.3
func test_migration_failure_message_states_supported_recovery_boundary() -> void:
    _prepare_continue_blocked_case("migration_failure")

    var menu := _instantiate_menu()
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var message_text := _blocked_message_text(menu).to_lower()
    _assert_blocked_feedback(menu, "migration")
    assert_bool(message_text.find("start a new run") >= 0).is_true()
    assert_bool(message_text.find("return to the menu") >= 0).is_true()
    assert_bool(message_text.find("mid-combat resume is not supported") >= 0).is_true()
    assert_bool(_events.has("core.run.resumed")).is_false()
    assert_bool(menu.visible).is_true()

# ACC:T63.5
# acceptance anchor: ACC:T87.4
func test_continue_refuses_resume_until_player_selects_recovery_action() -> void:
    _prepare_continue_blocked_case("locked_surface")

    var menu := _instantiate_menu()
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    assert_bool(_events.has("core.run.resumed")).is_false()
    assert_bool(menu.visible).is_true()
    _assert_blocked_feedback(menu, "locked")

    var new_run_btn := menu.get_node_or_null(BLOCKED_NEW_RUN_PATH) as Button
    assert_bool(new_run_btn != null).is_true()
    if new_run_btn == null:
        return

    new_run_btn.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    assert_bool(_events.has("core.run.started")).is_true()
    assert_bool(menu.visible).is_false()

# ACC:T63.6
func test_windows_smoke_surfaces_missing_and_invalid_save_blocked_attempts_to_player() -> void:
    var surfaced_attempts := 0
    var cases := [
        {"mode": "missing", "expected_reason": "no save"},
        {"mode": "invalid_integrity", "expected_reason": "integrity"}
    ]

    for case_data in cases:
        _events.clear()
        _prepare_continue_blocked_case(str(case_data["mode"]))

        var menu := _instantiate_menu()
        await get_tree().process_frame

        var continue_btn := menu.get_node("VBox/BtnContinue") as Button
        continue_btn.emit_signal("pressed")
        await get_tree().process_frame
        await get_tree().process_frame

        var dialog := menu.get_node_or_null(BLOCKED_DIALOG_PATH) as Control
        var message_text := _blocked_message_text(menu).to_lower()
        if dialog != null and dialog.visible and message_text.find(str(case_data["expected_reason"]).to_lower()) >= 0:
            surfaced_attempts += 1

        assert_bool(menu.visible).is_true()
        assert_bool(message_text.length() > 0).is_true()
        assert_bool(message_text.find(str(case_data["expected_reason"]).to_lower()) >= 0).is_true()

        menu.queue_free()
        await get_tree().process_frame

    assert_bool(surfaced_attempts == 2).is_true()
