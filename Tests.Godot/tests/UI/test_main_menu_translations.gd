extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_MENU_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_SCENE_FILE := "res://../Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_SCRIPT_FILE := "res://../Game.Godot/Scripts/UI/MainMenu.cs"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const KEY_PREFIXES := ["ui.", "menu.", "card.", "relic.", "event.", "etc."]

func _read_text(res_path: String) -> String:
    var absolute_path := ProjectSettings.globalize_path(res_path)
    if not FileAccess.file_exists(absolute_path):
        return ""
    var file := FileAccess.open(absolute_path, FileAccess.READ)
    if file == null:
        return ""
    return file.get_as_text()

func _looks_like_translation_key(value: String) -> bool:
    var text := value.strip_edges()
    for prefix in KEY_PREFIXES:
        if text.begins_with(prefix):
            return true
    return false

func _load_translation_values(csv_path: String) -> Dictionary:
    var values := {}
    var raw := _read_text(csv_path)
    for line in raw.split("\n", false):
        var trimmed := line.strip_edges()
        if trimmed == "" or trimmed.begins_with("key,value"):
            continue
        var comma := trimmed.find(",")
        if comma <= 0:
            continue
        var key := trimmed.substr(0, comma).strip_edges()
        var value := trimmed.substr(comma + 1).strip_edges()
        values[key] = value
    return values

func _contains_hardcoded_scene_ui_text(source_text: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('(text|title|dialog_text|ok_button_text|cancel_button_text)\\s*=\\s*"(?!ui\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(source_text) != null

func _contains_hardcoded_csharp_ui_text(source_text: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('(\\.Text|\\.Title|\\.DialogText|\\.OkButtonText|\\.CancelButtonText)\\s*=\\s*"(?!ui\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(source_text) != null

func test_main_menu_rejects_hardcoded_visible_ui_literals_in_scene_and_script_sources() -> void:
    var scene_source := _read_text(MAIN_MENU_SCENE_FILE)
    var script_source := _read_text(MAIN_MENU_SCRIPT_FILE)

    assert_bool(scene_source.length() > 0).is_true()
    assert_bool(script_source.length() > 0).is_true()

    assert_bool(_contains_hardcoded_scene_ui_text(scene_source)).is_false()
    assert_bool(_contains_hardcoded_csharp_ui_text(script_source)).is_false()

    var hardcoded_scene_snippet := "[node name=\"BtnNewRun\" type=\"Button\" parent=\"VBox\"]\ntext = \"New Run\"\n"
    assert_bool(_contains_hardcoded_scene_ui_text(hardcoded_scene_snippet)).is_true()

    var hardcoded_script_snippet := "button.Text = \"Continue\";\ndialog.Title = \"Overwrite run\";\n"
    assert_bool(_contains_hardcoded_csharp_ui_text(hardcoded_script_snippet)).is_true()

# acceptance: ACC:T14.7
# RED-FIRST: this should fail until MainMenu shows resolved localized values at runtime.
func test_main_menu_visible_text_is_not_raw_translation_key_for_buttons_and_dialogs() -> void:
    var expected := _load_translation_values(EN_TRANSLATIONS_FILE)
    var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var new_run_btn := menu.get_node("VBox/BtnNewRun") as Button
    var continue_btn := menu.get_node("VBox/BtnContinue") as Button
    var quit_btn := menu.get_node("VBox/BtnQuit") as Button
    var dialog := menu.get_node("OverwriteConfirmDialog") as ConfirmationDialog

    for key in ["ui.menu.new_run", "ui.menu.continue", "ui.menu.quit", "ui.menu.confirm_overwrite.title", "ui.menu.confirm_overwrite.body", "ui.menu.confirm", "ui.menu.cancel"]:
        assert_bool(expected.has(key)).is_true()
    assert_str(new_run_btn.text.strip_edges()).is_equal(str(expected["ui.menu.new_run"]))
    assert_str(continue_btn.text.strip_edges()).is_equal(str(expected["ui.menu.continue"]))
    assert_str(quit_btn.text.strip_edges()).is_equal(str(expected["ui.menu.quit"]))
    assert_str(dialog.title.strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.title"]))
    assert_str(dialog.dialog_text.strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.body"]))
    assert_str(dialog.ok_button_text.strip_edges()).is_equal(str(expected["ui.menu.confirm"]))
    assert_str(dialog.cancel_button_text.strip_edges()).is_equal(str(expected["ui.menu.cancel"]))
    assert_bool(_looks_like_translation_key(new_run_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(continue_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(quit_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(dialog.title)).is_false()
