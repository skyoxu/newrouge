extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const FOCUS_SCENES := [
	{
		"surface": "run-entry",
		"scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn",
		"order": ["VBox/BtnNewRun", "VBox/BtnContinue", "VBox/BtnSettings", "VBox/BtnQuit"],
		"strict_next": true
	},
	{
		"surface": "map",
		"scene": "res://Game.Godot/Scenes/Map/Map.tscn",
		"order": ["RouteTree/Floor1/combat_01"],
		"strict_next": false
	},
	{
		"surface": "node",
		"scene": "res://Game.Godot/Scenes/Event.tscn",
		"order": ["VBox/Options/BtnLoseHp", "VBox/Options/BtnTakeCurse"],
		"strict_next": false
	},
	{
		"surface": "reward",
		"scene": "res://Game.Godot/Scenes/Reward.tscn",
		"order": ["VBox/Actions/ConfirmButton", "VBox/Actions/SkipButton"],
		"strict_next": false
	},
	{
		"surface": "rest",
		"scene": "res://Game.Godot/Scenes/Rest.tscn",
		"order": ["VBox/Option_heal", "VBox/Option_upgrade", "VBox/Option_remove_curse"],
		"strict_next": false
	},
	{
		"surface": "shop",
		"scene": "res://Game.Godot/Scenes/Shop.tscn",
		"order": ["VBox/ServicesRow/BuyButton", "VBox/ServicesRow/RemoveButton", "VBox/ServicesRow/ReforgeButton", "VBox/LeaveButton"],
		"strict_next": false
	},
	{
		"surface": "combat",
		"scene": "res://Game.Godot/Scenes/Combat.tscn",
		"order": ["HUD/TurnControls/PlaySelectedCardButton", "HUD/TurnControls/EndTurnButton"],
		"strict_next": false
	},
	{
		"surface": "continue",
		"scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn",
		"order": ["VBox/BtnContinue", "VBox/BtnSettings", "VBox/BtnQuit"],
		"strict_next": true
	}
]

func _instantiate_scene(scene_path: String) -> Node:
	var packed := load(scene_path) as PackedScene
	assert(packed != null, "Missing scene: %s" % scene_path)
	var instance := packed.instantiate()
	add_child(auto_free(instance))
	await get_tree().process_frame
	return instance

func _prepare_scene(surface_name: String, scene: Node) -> void:
	if scene.has_method("RefreshLocaleForTest"):
		scene.call("RefreshLocaleForTest")
	if surface_name == "continue" and scene.has_method("SetAutosaveAvailableForTest"):
		scene.call("SetAutosaveAvailableForTest", true)
	if surface_name == "reward" and scene.has_method("SelectChoiceForTest"):
		scene.call("SelectChoiceForTest", 0)
	if surface_name == "shop" and scene.has_method("SetShopStateForTest"):
		scene.call("SetShopStateForTest", {
			"gold": 50,
			"offers": [{"id": "offer_attack", "price": 20, "taken": false}],
			"owned_offer_ids": [],
			"removable_cards": ["curse.basic"],
			"reforge_targets": ["offer_attack"]
		})
	if surface_name == "combat" and scene.has_method("ApplySnapshotForTest"):
		scene.call("ApplySnapshotForTest", ["Strike"], 3, 10, 0)
	await get_tree().process_frame

func _dispatch_focus_next() -> void:
	var pressed := InputEventAction.new()
	pressed.action = "ui_focus_next"
	pressed.pressed = true
	Input.parse_input_event(pressed)
	await get_tree().process_frame
	var released := InputEventAction.new()
	released.action = "ui_focus_next"
	released.pressed = false
	Input.parse_input_event(released)
	await get_tree().process_frame

func _resolve_focus_controls(scene: Node, paths: Array) -> Array[Control]:
	var controls: Array[Control] = []
	for path in paths:
		var node := scene.get_node_or_null(str(path))
		assert(node != null, "Missing focus node: %s" % str(path))
		assert(node is Control, "Focus node must be Control: %s" % str(path))
		controls.append(node as Control)
	return controls

func _focused_index(controls: Array[Control]) -> int:
	for index in range(controls.size()):
		if controls[index].has_focus():
			return index
	return -1

# acceptance: ACC:T68.2
func test_m1_focus_traversal_uses_real_ui_focus_navigation_without_trap_or_skip() -> void:
	for spec in FOCUS_SCENES:
		var surface_name := str(spec["surface"])
		var scene := await _instantiate_scene(str(spec["scene"]))
		await _prepare_scene(surface_name, scene)
		var controls := _resolve_focus_controls(scene, spec["order"])
		for control in controls:
			assert_bool(control.visible).is_true()
			assert_bool(control.focus_mode != Control.FOCUS_NONE).is_true()
			control.grab_focus()
			await get_tree().process_frame
			assert_bool(control.has_focus()).is_true()

		if not bool(spec.get("strict_next", false)) or controls.size() == 1:
			continue

		controls[0].grab_focus()
		await get_tree().process_frame
		assert_bool(controls[0].has_focus()).is_true()

		var visited: Array[int] = [0]
		for step in range(1, controls.size()):
			await _dispatch_focus_next()
			var index := _focused_index(controls)
			assert_bool(index >= 0).is_true()
			assert_int(index).is_equal(step)
			visited.append(index)

		var visited_set := {}
		for index in visited:
			visited_set[index] = true
		assert_int(visited_set.size()).is_equal(controls.size())
