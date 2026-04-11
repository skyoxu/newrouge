extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const CHARACTER_SELECT_SCENE := preload("res://Game.Godot/Scenes/UI/CharacterSelect.tscn")
const SUMMARY_KEYS := [
    "ui.character.warrior.summary.rage_buff",
    "ui.character.warrior.summary.power_window",
    "ui.character.warrior.summary.cost_burst"
]

func test_language_applies_runtime() -> void:
    var packed = load("res://Game.Godot/Scenes/UI/SettingsPanel.tscn")
    if packed == null:
        push_warning("SKIP: SettingsPanel.tscn not found")
        return
    var panel = packed.instantiate()
    add_child(auto_free(panel))
    await get_tree().process_frame
    var lang_opt = panel.get_node("VBox/LangRow/LangOpt")
    if lang_opt.get_item_count() == 0:
        lang_opt.add_item("en"); lang_opt.add_item("zh")
    # select zh and emit selection
    var idx := -1
    for i in range(lang_opt.get_item_count()):
        if str(lang_opt.get_item_text(i)).to_lower() == "zh":
            idx = i
            break
    if idx == -1:
        push_warning("SKIP: zh option not found")
        return
    lang_opt.select(idx)
    lang_opt.emit_signal("item_selected", idx)
    await get_tree().process_frame
    assert_str(TranslationServer.get_locale()).contains("zh")


# ACC:T16.5
func test_character_select_summary_uses_translation_keys_and_updates_with_locale() -> void:
    var scene := CHARACTER_SELECT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    await get_tree().process_frame

    var keys := scene.call("GetWarriorSummaryKeysForTest")
    assert_int(int(keys.size())).is_equal(3)
    for i in range(0, 3):
        assert_str(str(keys[i])).is_equal(str(SUMMARY_KEYS[i]))

    var previous_locale := TranslationServer.get_locale()

    TranslationServer.set_locale("en")
    scene.call("RefreshLocaleForTest")
    await get_tree().process_frame
    var en_lines = scene.call("GetWarriorSummaryLinesForTest")

    TranslationServer.set_locale("zh-CN")
    scene.call("RefreshLocaleForTest")
    await get_tree().process_frame
    var zh_lines = scene.call("GetWarriorSummaryLinesForTest")

    TranslationServer.set_locale(previous_locale)
    scene.call("RefreshLocaleForTest")

    assert_int(int(en_lines.size())).is_equal(3)
    assert_int(int(zh_lines.size())).is_equal(3)
    for i in range(0, 3):
        var en_text := str(en_lines[i]).strip_edges()
        var zh_text := str(zh_lines[i]).strip_edges()
        assert_str(en_text).is_not_empty()
        assert_str(zh_text).is_not_empty()
        assert_str(en_text).is_not_equal(zh_text)

