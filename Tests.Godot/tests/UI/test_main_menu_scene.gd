extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

# ACC:T14.4
func test_main_menu_scene_instantiates() -> void:
    var scene := preload("res://Game.Godot/Scenes/UI/MainMenu.tscn").instantiate()
    add_child(auto_free(scene))
    await get_tree().process_frame
    assert_bool(scene.visible).is_true()

    var new_run := scene.get_node_or_null("VBox/BtnNewRun") as Button
    var continue_btn := scene.get_node_or_null("VBox/BtnContinue") as Button
    var quit_btn := scene.get_node_or_null("VBox/BtnQuit") as Button

    assert_bool(new_run != null).is_true()
    assert_bool(continue_btn != null).is_true()
    assert_bool(quit_btn != null).is_true()
    assert_bool(new_run.visible).is_true()
    assert_bool(continue_btn.visible).is_true()
    assert_bool(quit_btn.visible).is_true()

