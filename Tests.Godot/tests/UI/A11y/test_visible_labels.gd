extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const M1_LABEL_SPECS := [
    {"surface": "run-entry", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "label_path": "VBox/BtnNewRun"},
    {"surface": "map", "scene": "res://Game.Godot/Scenes/Map/Map.tscn", "label_path": "RouteTree/Floor1/combat_01"},
    {"surface": "node", "scene": "res://Game.Godot/Scenes/Event.tscn", "label_path": "VBox/Options/BtnLoseHp"},
    {"surface": "reward", "scene": "res://Game.Godot/Scenes/Reward.tscn", "label_path": "VBox/Actions/ConfirmButton"},
    {"surface": "rest", "scene": "res://Game.Godot/Scenes/Rest.tscn", "label_path": "VBox/Option_remove_curse"},
    {"surface": "shop", "scene": "res://Game.Godot/Scenes/Shop.tscn", "label_path": "VBox/LeaveButton"},
    {"surface": "combat", "scene": "res://Game.Godot/Scenes/Combat.tscn", "label_path": "HUD/TurnControls/PlaySelectedCardButton"},
    {"surface": "continue", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "label_path": "VBox/BtnContinue"}
]

func _instantiate_scene(scene_path: String) -> Node:
    var packed := load(scene_path) as PackedScene
    assert(packed != null, "Missing scene: %s" % scene_path)
    var instance := packed.instantiate()
    add_child(auto_free(instance))
    await get_tree().process_frame
    return instance

func _read_visible_text(node: Node) -> String:
    if node is Label:
        return (node as Label).text
    if node is Button:
        return (node as Button).text
    assert(false, "Unsupported text node type: %s" % node.get_class())
    return ""

func _is_readable(text: String) -> bool:
    var trimmed := text.strip_edges()
    if trimmed.is_empty():
        return false
    if trimmed.begins_with("ui."):
        return false
    if trimmed.find(".") >= 0 and not trimmed.contains(" "):
        return false
    return true

# acceptance: ACC:T68.4
func test_m1_primary_action_labels_are_visible_and_human_readable() -> void:
    for spec in M1_LABEL_SPECS:
        var scene := await _instantiate_scene(str(spec["scene"]))
        if scene.has_method("RefreshLocaleForTest"):
            scene.call("RefreshLocaleForTest")
        await get_tree().process_frame

        var node := scene.get_node_or_null(str(spec["label_path"]))
        assert(node != null, "Missing label node for %s: %s" % [str(spec["surface"]), str(spec["label_path"])])
        var text := _read_visible_text(node as Node)
        assert(_is_readable(text), "Unreadable label on surface %s: %s" % [str(spec["surface"]), text])

