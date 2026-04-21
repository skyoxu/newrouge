extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const AUTOSAVE_PATH := "user://autosave_slot.json"

var _bus: Node
var _received := false
var _etype := ""
var _quit_callback_invoked := false

func before() -> void:
    _remove_autosave()
    # Install a temporary EventBus under /root to mimic Autoload
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))
    _bus.connect("DomainEventEmitted", Callable(self, "_on_evt"))

func after() -> void:
    _remove_autosave()

func _on_evt(type, _source, _data_json, _id, _spec, _ct, _ts) -> void:
    _received = true
    _etype = str(type)

func _on_quit_requested() -> void:
    _quit_callback_invoked = true

func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)

func _write_autosave(payload: String) -> void:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    file.store_string(payload)
    file.close()

func _sha256_hex(text: String) -> String:
    return text.sha256_text()

func _build_valid_autosave_json() -> String:
    var state_json := "{}"
    var integrity_hash := _sha256_hex(state_json)
    return "{\"run_id\":\"run_a\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"2026-04-06T00:00:00Z\",\"state_json\":\"%s\",\"integrity_hash\":\"%s\"}" % [state_json, integrity_hash]

# ACC:T14.5
func test_continue_is_disabled_without_autosave_and_stays_disabled_for_invalid_autosave() -> void:
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    assert_bool(continue_btn != null).is_true()
    assert_bool(continue_btn.disabled).is_true()

    _write_autosave("{")
    menu.call_deferred("queue_free")
    await get_tree().process_frame

    menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame
    continue_btn = menu.get_node("VBox/BtnContinue") as Button

    assert_bool(continue_btn.disabled).is_true()

# ACC:T14.5
func test_continue_is_enabled_with_valid_autosave_file() -> void:
    _write_autosave(_build_valid_autosave_json())
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    assert_bool(continue_btn.disabled).is_false()

# ACC:T14.5
func test_continue_stays_disabled_and_emits_blocked_for_parseable_but_corrupt_autosave() -> void:
    _received = false
    _etype = ""
    _write_autosave("{\"run_id\":\"run_a\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"not-a-date\",\"state_json\":\"{}\"}")
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    assert_bool(continue_btn.disabled).is_true()

    continue_btn.emit_signal("pressed")
    await get_tree().process_frame

    assert_bool(_received).is_true()
    assert_str(_etype).is_equal("core.run.continue.blocked")

# ACC:T14.12
func test_new_run_without_autosave_starts_without_overwrite_dialog() -> void:
    _received = false
    _etype = ""
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame
    menu.call("SetAutosaveAvailableForTest", false)

    var btn := menu.get_node("VBox/BtnNewRun")
    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    btn.emit_signal("pressed")
    await get_tree().process_frame

    assert_bool(dialog == null or not dialog.visible).is_true()
    assert_bool(_received).is_true()
    assert_str(_etype).is_equal("core.run.started")

# ACC:T14.13
func test_continue_with_valid_autosave_resumes_single_slot_and_hides_menu() -> void:
    _received = false
    _etype = ""
    _write_autosave(_build_valid_autosave_json())
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    continue_btn.emit_signal("pressed")
    await get_tree().process_frame

    assert_bool(_received).is_true()
    assert_str(_etype).is_equal("core.run.resumed")
    assert_bool(menu.visible).is_false()
    assert_object(menu.get_node_or_null("SlotSelectionDialog")).is_null()

# ACC:T14.8
func test_main_menu_emits_quit_and_requests_exit() -> void:
    _received = false
    _etype = ""
    _quit_callback_invoked = false
    var menu = preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame
    menu.call("SetQuitRequestCallbackForTest", Callable(self, "_on_quit_requested"))
    var btn = menu.get_node("VBox/BtnQuit")
    btn.emit_signal("pressed")
    await get_tree().process_frame
    assert_bool(_received).is_true()
    assert_str(_etype).is_equal("ui.menu.quit")
    assert_bool(menu.call("WasQuitRequestedForTest")).is_true()
    assert_bool(_quit_callback_invoked).is_true()
    assert_bool(menu.call("WasQuitIntentReachedForTest")).is_true()

