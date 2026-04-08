extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const AUTOSAVE_PATH := "user://autosave_slot.json"
const MAIN_MENU_SCENE := preload("res://Game.Godot/Scenes/UI/MainMenu.tscn")

func before() -> void:
    _remove_autosave()

func after() -> void:
    _remove_autosave()

func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)

func _write_autosave(payload: String) -> void:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    file.store_string(payload)
    file.close()

# acceptance: ACC:T14.6
func test_new_run_with_valid_autosave_focuses_real_cancel_button_in_confirmation_dialog() -> void:
    _write_autosave("{\"run_id\":\"run_a\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"2026-04-06T00:00:00Z\",\"state_json\":\"{}\",\"integrity_hash\":\"abc123\"}")
    var menu := MAIN_MENU_SCENE.instantiate() as Control
    add_child(auto_free(menu))
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
