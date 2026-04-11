extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const CHARACTER_SELECT_SCENE := preload("res://Game.Godot/Scenes/UI/CharacterSelect.tscn")
const SUMMARY_KEYS := [
    "ui.character.warrior.summary.rage_buff",
    "ui.character.warrior.summary.power_window",
    "ui.character.warrior.summary.cost_burst"
]

func _new_scene() -> Control:
    var scene := CHARACTER_SELECT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    return scene

# ACC:T16.4
func test_warrior_summary_must_render_three_visible_lines_covering_required_semantics() -> void:
    var scene := _new_scene()
    await get_tree().process_frame
    var lines := scene.call("GetWarriorSummaryLinesForTest") as PackedStringArray
    var keys := scene.call("GetWarriorSummaryKeysForTest")

    assert_int(int(lines.size())).is_equal(3)
    assert_int(int(keys.size())).is_equal(3)

    for i in range(0, 3):
        var key := str(keys[i])
        var actual_line := str(lines[i]).strip_edges()
        var expected_line := str(scene.call("GetLocalizedTextByKeyForTest", key)).strip_edges()
        assert_str(key).is_equal(str(SUMMARY_KEYS[i]))
        assert_str(actual_line).is_not_empty()
        assert_str(actual_line).is_equal(expected_line)
