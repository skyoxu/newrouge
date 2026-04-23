extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const M1_BUTTON_SPECS := [
    {"surface": "run-entry", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "action_path": "VBox/BtnNewRun"},
    {"surface": "map", "scene": "res://Game.Godot/Scenes/Map/Map.tscn", "action_path": "ActionRow/btn_combat"},
    {"surface": "node", "scene": "res://Game.Godot/Scenes/Event.tscn", "action_path": "VBox/Options/BtnLoseHp"},
    {"surface": "reward", "scene": "res://Game.Godot/Scenes/Reward.tscn", "action_path": "VBox/Actions/ConfirmButton"},
    {"surface": "rest", "scene": "res://Game.Godot/Scenes/Rest.tscn", "action_path": "VBox/Option_upgrade"},
    {"surface": "shop", "scene": "res://Game.Godot/Scenes/Shop.tscn", "action_path": "VBox/ServicesRow/BuyButton"},
    {"surface": "combat", "scene": "res://Game.Godot/Scenes/Combat.tscn", "action_path": "HUD/TurnControls/StartTurnButton"},
    {"surface": "continue", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "action_path": "VBox/BtnContinue"}
]

func _instantiate_scene(scene_path: String) -> Node:
    var packed := load(scene_path) as PackedScene
    assert(packed != null, "Missing scene: %s" % scene_path)
    var instance := packed.instantiate()
    add_child(auto_free(instance))
    await get_tree().process_frame
    return instance

func _get_action_button(root: Node, node_path: String) -> BaseButton:
    var button := root.get_node_or_null(node_path)
    assert(button != null, "Missing action node: %s" % node_path)
    assert(button is BaseButton, "Action node must be BaseButton: %s" % node_path)
    return button as BaseButton

func _invoke_by_keyboard(button: BaseButton) -> bool:
    button.grab_focus()
    await get_tree().process_frame
    if button.focus_mode == Control.FOCUS_NONE:
        return false
    if not button.has_focus():
        return false
    var pressed_state := {"hit": false}
    button.pressed.connect(func() -> void: pressed_state["hit"] = true, CONNECT_ONE_SHOT)
    var pressed := InputEventAction.new()
    pressed.action = "ui_accept"
    pressed.pressed = true
    Input.parse_input_event(pressed)
    await get_tree().process_frame
    var released := InputEventAction.new()
    released.action = "ui_accept"
    released.pressed = false
    Input.parse_input_event(released)
    await get_tree().process_frame
    return bool(pressed_state["hit"])

func _invoke_by_controller(button: BaseButton) -> bool:
    button.grab_focus()
    await get_tree().process_frame
    if not button.has_focus():
        return false
    var pressed_state := {"hit": false}
    button.pressed.connect(func() -> void: pressed_state["hit"] = true, CONNECT_ONE_SHOT)
    var pressed := InputEventAction.new()
    pressed.action = "ui_accept"
    pressed.pressed = true
    Input.parse_input_event(pressed)
    await get_tree().process_frame
    var released := InputEventAction.new()
    released.action = "ui_accept"
    released.pressed = false
    Input.parse_input_event(released)
    await get_tree().process_frame
    return bool(pressed_state["hit"])

func _prepare_surface(surface_name: String, scene: Node) -> void:
    match surface_name:
        "continue":
            if scene.has_method("SetAutosaveAvailableForTest"):
                scene.call("SetAutosaveAvailableForTest", true)
        "reward":
            if scene.has_method("SelectChoiceForTest"):
                assert_bool(bool(scene.call("SelectChoiceForTest", 0))).is_true()
        "shop":
            if scene.has_method("SetShopStateForTest"):
                scene.call("SetShopStateForTest", {
                    "gold": 50,
                    "offers": [{"id": "offer_attack", "price": 20, "taken": false}],
                    "owned_offer_ids": [],
                    "removable_cards": ["curse.basic"],
                    "reforge_targets": ["offer_attack"]
                })
        "combat":
            if scene.has_method("ApplySnapshotForTest"):
                scene.call("ApplySnapshotForTest", ["Strike"], 3, 10, 0)

func _capture_state(surface_name: String, scene: Node) -> Dictionary:
    match surface_name:
        "run-entry", "continue":
            return {"visible": scene.visible}
        "map":
            if scene.has_method("GetLastInvokedActionForTest"):
                return {"last_action": str(scene.call("GetLastInvokedActionForTest"))}
            return {}
        "node":
            if scene.has_method("GetSelectedOptionIdForTest"):
                return {"selected": str(scene.call("GetSelectedOptionIdForTest"))}
            return {}
        "reward":
            if scene.has_method("GetFeedbackForTest"):
                return {"feedback": str(scene.call("GetFeedbackForTest"))}
            return {}
        "rest":
            if scene.has_method("IsUpgradeConfirmPendingForTest"):
                return {"pending": bool(scene.call("IsUpgradeConfirmPendingForTest"))}
            return {}
        "shop":
            if not scene.has_method("GetOwnedOfferIdsForTest") or not scene.has_method("GetPlayerGoldForTest"):
                return {}
            var owned = scene.call("GetOwnedOfferIdsForTest") as Array
            return {"gold": int(scene.call("GetPlayerGoldForTest")), "owned_count": owned.size()}
        "combat":
            if not scene.has_method("GetDispatchedCommandsForTest"):
                return {}
            var commands = scene.call("GetDispatchedCommandsForTest") as Array
            return {"command_count": commands.size()}
        _:
            return {}

func _assert_state_progress(surface_name: String, state_before: Dictionary, state_after: Dictionary) -> void:
    match surface_name:
        "run-entry", "continue":
            assert_bool(bool(state_after.get("visible", true))).is_false()
        "map":
            if state_after.has("last_action"):
                assert_str(str(state_after.get("last_action", ""))).is_equal("combat")
        "node":
            if state_after.has("selected"):
                assert_str(str(state_after.get("selected", ""))).is_equal("lose_hp")
        "reward":
            if state_after.has("feedback"):
                assert_str(str(state_after.get("feedback", ""))).is_not_equal(str(state_before.get("feedback", "")))
        "rest":
            if state_after.has("pending"):
                assert_bool(bool(state_after.get("pending", false))).is_true()
        "shop":
            if state_after.has("owned_count") and state_after.has("gold"):
                assert_int(int(state_after.get("owned_count", 0))).is_equal(int(state_before.get("owned_count", 0)) + 1)
                assert_int(int(state_after.get("gold", 0))).is_less(int(state_before.get("gold", 0)))
        "combat":
            if state_after.has("command_count"):
                assert_int(int(state_after.get("command_count", 0))).is_equal(int(state_before.get("command_count", 0)) + 1)

# acceptance: ACC:T68.4
func test_m1_primary_buttons_emit_pressed_on_real_surfaces() -> void:
    for spec in M1_BUTTON_SPECS:
        var surface_name := str(spec["surface"])

        var keyboard_scene := await _instantiate_scene(str(spec["scene"]))
        if keyboard_scene.has_method("RefreshLocaleForTest"):
            keyboard_scene.call("RefreshLocaleForTest")
        _prepare_surface(surface_name, keyboard_scene)
        await get_tree().process_frame

        var keyboard_button := _get_action_button(keyboard_scene, str(spec["action_path"]))
        assert_bool(keyboard_button.visible).is_true()
        var keyboard_before := _capture_state(surface_name, keyboard_scene)
        var keyboard_ok := await _invoke_by_keyboard(keyboard_button)
        assert(keyboard_ok, "Keyboard invocation failed on surface %s" % surface_name)
        var keyboard_after := _capture_state(surface_name, keyboard_scene)
        _assert_state_progress(surface_name, keyboard_before, keyboard_after)

        var controller_scene := await _instantiate_scene(str(spec["scene"]))
        if controller_scene.has_method("RefreshLocaleForTest"):
            controller_scene.call("RefreshLocaleForTest")
        _prepare_surface(surface_name, controller_scene)
        await get_tree().process_frame

        var controller_button := _get_action_button(controller_scene, str(spec["action_path"]))
        assert_bool(controller_button.visible).is_true()
        var controller_before := _capture_state(surface_name, controller_scene)
        var controller_ok := await _invoke_by_controller(controller_button)
        assert(controller_ok, "Controller invocation failed on surface %s" % surface_name)
        var controller_after := _capture_state(surface_name, controller_scene)
        _assert_state_progress(surface_name, controller_before, controller_after)

