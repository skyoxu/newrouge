extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_MENU_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_SCENE_FILE := "res://../Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_SCRIPT_FILE := "res://../Game.Godot/Scripts/UI/MainMenu.cs"
const APPROVED_PREFIXES := ["ui.", "card.", "relic.", "event.", "etc."]

func _read_text(res_path: String) -> String:
    var absolute_path := ProjectSettings.globalize_path(res_path)
    if not FileAccess.file_exists(absolute_path):
        return ""
    var file := FileAccess.open(absolute_path, FileAccess.READ)
    if file == null:
        return ""
    return file.get_as_text()

func _has_approved_prefix(key: String) -> bool:
    for prefix in APPROVED_PREFIXES:
        if key.begins_with(prefix):
            return true
    return false

func _collect_publish_keys(script_source: String) -> Array[String]:
    var keys: Array[String] = []
    var regex := RegEx.new()
    var error := regex.compile('Publish\\("([^"]+)"')
    if error != OK:
        return keys
    for match in regex.search_all(script_source):
        keys.append(str(match.get_string(1)))
    return keys

func _contains_hardcoded_button_text(scene_source: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('text\\s*=\\s*"(?!ui\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(scene_source) != null

func _contains_hardcoded_csharp_ui_text(script_source: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('\\.Text\\s*=\\s*"(?!ui\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(script_source) != null

# acceptance: ACC:T23.5
# Task 23 UI text entry points:
# - MainMenu.tscn:VBox/BtnPlay.text
# - MainMenu.tscn:VBox/BtnSettings.text
# - MainMenu.tscn:VBox/BtnQuit.text
func test_main_menu_buttons_render_translation_keys_instead_of_raw_text() -> void:
    var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var node_paths := ["VBox/BtnPlay", "VBox/BtnSettings", "VBox/BtnQuit"]
    for node_path in node_paths:
        assert_bool(menu.has_node(node_path)).is_true()
        if not menu.has_node(node_path):
            continue
        var button := menu.get_node(node_path) as Button
        assert_str(button.text).starts_with("ui.")

# acceptance: ACC:T23.8
# RED-FIRST: this should fail while scene/script still contain hardcoded UI literals.
func test_main_menu_sources_refuse_unapproved_prefixes_and_hardcoded_ui_literals() -> void:
    var scene_source := _read_text(MAIN_MENU_SCENE_FILE)
    var script_source := _read_text(MAIN_MENU_SCRIPT_FILE)

    assert_bool(scene_source.length() > 0).is_true()
    assert_bool(script_source.length() > 0).is_true()

    var publish_keys := _collect_publish_keys(script_source)
    assert_bool(publish_keys.size() > 0).is_true()
    for key in publish_keys:
        assert_bool(_has_approved_prefix(key)).is_true()

    assert_bool(_contains_hardcoded_button_text(scene_source)).is_false()
    assert_bool(_contains_hardcoded_csharp_ui_text(script_source)).is_false()

func test_unapproved_prefix_and_hardcoded_snippet_are_rejected() -> void:
    assert_bool(_has_approved_prefix("legacy.menu.quit")).is_false()

    var scene_snippet := "[node name=\"BtnPlay\" type=\"Button\" parent=\"VBox\"]\ntext = \"Play\"\n"
    assert_bool(_contains_hardcoded_button_text(scene_snippet)).is_true()
