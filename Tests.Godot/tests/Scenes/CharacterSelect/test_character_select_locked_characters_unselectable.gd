extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const CHARACTER_SELECT_SCENE := preload("res://Game.Godot/Scenes/UI/CharacterSelect.tscn")

func _new_scene() -> Control:
    var scene := CHARACTER_SELECT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    return scene


# acceptance: ACC:T16.6
func test_locked_character_click_does_not_change_selected_state() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var mage_button := scene.get_node_or_null("VBox/CharacterRow/MagePanel/BtnMage") as Button
    var mage_lock := scene.get_node_or_null("VBox/CharacterRow/MagePanel/LblMageLock") as Label
    var warrior_state := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel/LblWarriorState") as Label
    assert_object(mage_button).is_not_null()
    assert_object(mage_lock).is_not_null()
    assert_object(warrior_state).is_not_null()
    if mage_button != null and mage_lock != null and warrior_state != null:
        assert_bool(mage_button.disabled).is_true()
        assert_bool(mage_lock.visible).is_true()
        assert_str(warrior_state.text.to_lower()).contains("selected")

    scene.call("SelectCharacterForTest", "mage")

    if mage_button != null and mage_lock != null and warrior_state != null:
        assert_bool(mage_button.disabled).is_true()
        assert_bool(mage_lock.visible).is_true()
        assert_str(mage_lock.text.to_lower()).contains("not open")
        assert_str(warrior_state.text.to_lower()).contains("selected")

    assert_str(str(scene.call("GetSelectedCharacterForTest"))).is_equal("warrior")


func test_locked_character_keyboard_confirm_does_not_change_selected_state() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var rogue_button := scene.get_node_or_null("VBox/CharacterRow/RoguePanel/BtnRogue") as Button
    var rogue_lock := scene.get_node_or_null("VBox/CharacterRow/RoguePanel/LblRogueLock") as Label
    var warrior_state := scene.get_node_or_null("VBox/CharacterRow/WarriorPanel/LblWarriorState") as Label
    assert_object(rogue_button).is_not_null()
    assert_object(rogue_lock).is_not_null()
    assert_object(warrior_state).is_not_null()
    if rogue_button != null and rogue_lock != null and warrior_state != null:
        assert_bool(rogue_button.disabled).is_true()
        assert_bool(rogue_lock.visible).is_true()
        assert_str(warrior_state.text.to_lower()).contains("selected")

    scene.call("KeyboardConfirmCharacterForTest", "rogue")

    if rogue_button != null and rogue_lock != null and warrior_state != null:
        assert_bool(rogue_button.disabled).is_true()
        assert_bool(rogue_lock.visible).is_true()
        assert_str(rogue_lock.text.to_lower()).contains("not open")
        assert_str(warrior_state.text.to_lower()).contains("selected")

    assert_str(str(scene.call("GetSelectedCharacterForTest"))).is_equal("warrior")
