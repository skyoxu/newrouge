extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const CHARACTER_SELECT_SCENE := preload("res://Game.Godot/Scenes/UI/CharacterSelect.tscn")
const OVERLAY_TESTING_FILE := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Testing-M1.md"
const NOT_OPEN_LABEL_KEY := "ui.character.not_open"
const TASK16_EXPECTED_TEST_REFS := [
    "Tests.Godot/tests/Tasks/test_task0016_acceptance.gd",
    "Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_warrior_summary.gd",
    "Tests.Godot/tests/Scenes/CharacterSelect/test_character_select_locked_characters_unselectable.gd",
    "Tests.Godot/tests/UI/test_settings_locale.gd",
    "Game.Core.Tests/Tasks/Task16RunCharacterSelectedContractTests.cs"
]

func _new_scene() -> Control:
    var scene := CHARACTER_SELECT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    return scene


func _read_text(file_path: String) -> String:
    var global_path := ProjectSettings.globalize_path(file_path)
    if not FileAccess.file_exists(global_path):
        return ""
    var file := FileAccess.open(global_path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content


# ACC:T16.1
func test_only_warrior_can_be_selected_and_locked_interactions_keep_state_unchanged() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var warrior_button := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel/BtnWarrior") as Button
    var mage_button := scene.get_node_or_null("VBox/CharacterRow/MagePanel/BtnMage") as Button
    var rogue_button := scene.get_node_or_null("VBox/CharacterRow/RoguePanel/BtnRogue") as Button
    var mage_lock := scene.get_node_or_null("VBox/CharacterRow/MagePanel/LblMageLock") as Label
    var rogue_lock := scene.get_node_or_null("VBox/CharacterRow/RoguePanel/LblRogueLock") as Label

    assert_object(warrior_button).is_not_null()
    assert_object(mage_button).is_not_null()
    assert_object(rogue_button).is_not_null()
    assert_object(mage_lock).is_not_null()
    assert_object(rogue_lock).is_not_null()

    if warrior_button != null and mage_button != null and rogue_button != null and mage_lock != null and rogue_lock != null:
        assert_bool(warrior_button.disabled).is_false()
        assert_bool(mage_button.disabled).is_true()
        assert_bool(rogue_button.disabled).is_true()
        assert_bool(float(mage_button.modulate.a) < 1.0).is_true()
        assert_bool(float(rogue_button.modulate.a) < 1.0).is_true()
        assert_bool(mage_lock.visible).is_true()
        assert_bool(rogue_lock.visible).is_true()
        assert_str(mage_lock.text.to_lower()).contains("not open")
        assert_str(rogue_lock.text.to_lower()).contains("not open")

    assert_bool(bool(scene.call("IsCharacterInteractableForTest", "warrior"))).is_true()
    assert_bool(bool(scene.call("IsCharacterHiddenOrDimmedForTest", "mage"))).is_true()
    assert_bool(bool(scene.call("IsCharacterHiddenOrDimmedForTest", "rogue"))).is_true()
    assert_str(str(scene.call("GetLockLabelTextForTest", "mage")).to_lower()).contains("not open")
    assert_str(str(scene.call("GetLockLabelTextForTest", "rogue")).to_lower()).contains("not open")

    var selected_before := str(scene.call("GetSelectedCharacterForTest"))
    scene.call("SelectCharacterForTest", "mage")
    scene.call("KeyboardConfirmCharacterForTest", "rogue")

    assert_str(str(scene.call("GetSelectedCharacterForTest"))).is_equal(selected_before)


# ACC:T16.2
func test_character_select_scene_loads_on_windows_and_allows_warrior_selection_interaction() -> void:
    assert_bool(OS.has_feature("windows")).is_true()

    var scene := _new_scene()
    await get_tree().process_frame

    var warrior_button := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel/BtnWarrior") as Button
    assert_object(warrior_button).is_not_null()
    if warrior_button != null:
        assert_bool(warrior_button.visible).is_true()
        assert_bool(warrior_button.disabled).is_false()

    assert_bool(scene.visible).is_true()
    assert_bool(scene.has_method("SelectCharacterForTest")).is_true()
    assert_bool(scene.has_method("GetSelectedCharacterForTest")).is_true()

    if warrior_button != null and scene.has_method("GetSelectedCharacterForTest"):
        warrior_button.emit_signal("pressed")
        await get_tree().process_frame
        assert_str(str(scene.call("GetSelectedCharacterForTest"))).is_equal("warrior")


# ACC:T16.3
func test_overlay_test_refs_contains_task0016_acceptance_file_for_traceability() -> void:
    var overlay_text := _read_text(OVERLAY_TESTING_FILE)

    assert_bool(overlay_text.strip_edges().is_empty()).is_false()
    for test_ref in TASK16_EXPECTED_TEST_REFS:
        assert_bool(overlay_text.contains(test_ref)).is_true()


# ACC:T16.8
func test_warrior_panel_must_be_visible_and_interactable_after_scene_load() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var warrior_panel := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel") as Control
    var warrior_button := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel/BtnWarrior") as Button

    assert_object(warrior_panel).is_not_null()
    assert_object(warrior_button).is_not_null()
    if warrior_panel != null and warrior_button != null:
        assert_bool(warrior_panel.visible).is_true()
        assert_bool(warrior_button.visible).is_true()
        assert_bool(warrior_button.disabled).is_false()


# ACC:T16.7
func test_not_open_label_must_use_translation_key_and_follow_locale_changes() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var mage_lock := scene.get_node_or_null("VBox/CharacterRow/MagePanel/LblMageLock") as Label
    var rogue_lock := scene.get_node_or_null("VBox/CharacterRow/RoguePanel/LblRogueLock") as Label
    assert_object(mage_lock).is_not_null()
    assert_object(rogue_lock).is_not_null()

    assert_str(str(scene.call("GetLockLabelKeyForTest", "mage"))).is_equal(NOT_OPEN_LABEL_KEY)
    assert_str(str(scene.call("GetLockLabelKeyForTest", "rogue"))).is_equal(NOT_OPEN_LABEL_KEY)

    var previous_locale := TranslationServer.get_locale()
    TranslationServer.set_locale("zh-CN")
    scene.call("RefreshLocaleForTest")
    await get_tree().process_frame
    var mage_zh_text := ""
    var rogue_zh_text := ""
    if mage_lock != null and rogue_lock != null:
        mage_zh_text = mage_lock.text
        rogue_zh_text = rogue_lock.text

    TranslationServer.set_locale("en")
    scene.call("RefreshLocaleForTest")
    await get_tree().process_frame
    var mage_en_text := ""
    var rogue_en_text := ""
    if mage_lock != null and rogue_lock != null:
        mage_en_text = mage_lock.text
        rogue_en_text = rogue_lock.text

    TranslationServer.set_locale(previous_locale)
    scene.call("RefreshLocaleForTest")

    assert_str(mage_zh_text).is_not_equal(mage_en_text)
    assert_str(rogue_zh_text).is_not_equal(rogue_en_text)
