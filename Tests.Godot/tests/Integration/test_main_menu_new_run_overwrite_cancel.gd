extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const AUTOSAVE_PATH := "user://autosave_slot.json"
const MAIN_MENU_SCENE := preload("res://Game.Godot/Scenes/UI/MainMenu.tscn")

var _bus: Node
var _events: Array[String] = []

func before() -> void:
    _remove_autosave()
    _events.clear()
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))
    _bus.connect("DomainEventEmitted", Callable(self, "_on_event"))

func after() -> void:
    _remove_autosave()

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

func _sha256_hex(text: String) -> String:
    return text.sha256_text()

func _build_valid_autosave_json() -> String:
    var state_json := "{}"
    var integrity_hash := _sha256_hex(state_json)
    return "{\"run_id\":\"run_a\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"2026-04-06T00:00:00Z\",\"state_json\":\"%s\",\"integrity_hash\":\"%s\"}" % [state_json, integrity_hash]

func _read_autosave() -> String:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content

func _instantiate_menu() -> Control:
    var menu := MAIN_MENU_SCENE.instantiate() as Control
    add_child(auto_free(menu))
    return menu

# acceptance: ACC:T14.6
func test_new_run_with_existing_autosave_opens_real_overwrite_dialog_with_cancel_default_focus() -> void:
    _write_autosave(_build_valid_autosave_json())
    var menu := _instantiate_menu()
    await get_tree().process_frame

    var button := menu.get_node("VBox/BtnNewRun") as Button
    button.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var dialog := menu.get_node("OverwriteConfirmDialog") as ConfirmationDialog
    var cancel_button := dialog.get_cancel_button()

    assert_bool(dialog.visible).is_true()
    assert_bool(cancel_button != null).is_true()
    assert_bool(cancel_button.has_focus()).is_true()
    assert_str(str(menu.call("GetLastDialogFocusPreferenceForTest"))).is_equal("cancel")

# acceptance: ACC:T14.6
func test_cancel_on_real_overwrite_confirmation_keeps_autosave_unchanged_and_does_not_start_run() -> void:
    _write_autosave(_build_valid_autosave_json())
    var before_cancel := _read_autosave()
    var menu := _instantiate_menu()
    await get_tree().process_frame

    var button := menu.get_node("VBox/BtnNewRun") as Button
    button.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var dialog := menu.get_node("OverwriteConfirmDialog") as ConfirmationDialog
    dialog.emit_signal("canceled")
    await get_tree().process_frame

    var after_cancel := _read_autosave()
    assert_str(after_cancel).is_equal(before_cancel)
    assert_bool(_events.has("core.run.started")).is_false()
    assert_bool(menu.visible).is_true()

# acceptance: ACC:T14.14
func test_confirm_on_real_overwrite_confirmation_starts_new_run_from_single_slot_flow() -> void:
    _write_autosave(_build_valid_autosave_json())
    var menu := _instantiate_menu()
    await get_tree().process_frame

    var button := menu.get_node("VBox/BtnNewRun") as Button
    button.emit_signal("pressed")
    await get_tree().process_frame
    await get_tree().process_frame

    var dialog := menu.get_node("OverwriteConfirmDialog") as ConfirmationDialog
    dialog.emit_signal("confirmed")
    await get_tree().process_frame

    assert_bool(_events.has("core.run.started")).is_true()
    assert_bool(menu.visible).is_false()
    assert_object(menu.get_node_or_null("SlotSelectionDialog")).is_null()
