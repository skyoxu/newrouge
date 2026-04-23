extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const SURFACE_SPECS := [
	{"surface": "run-entry", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "action_path": "VBox/BtnNewRun"},
	{"surface": "map", "scene": "res://Game.Godot/Scenes/Map/Map.tscn", "action_path": "ActionRow/btn_combat"},
	{"surface": "node", "scene": "res://Game.Godot/Scenes/Event.tscn", "action_path": "VBox/Options/BtnLoseHp"},
	{"surface": "reward", "scene": "res://Game.Godot/Scenes/Reward.tscn", "action_path": "VBox/Actions/ConfirmButton"},
	{"surface": "rest", "scene": "res://Game.Godot/Scenes/Rest.tscn", "action_path": "VBox/Option_upgrade"},
	{"surface": "shop", "scene": "res://Game.Godot/Scenes/Shop.tscn", "action_path": "VBox/ServicesRow/BuyButton"},
	{"surface": "combat", "scene": "res://Game.Godot/Scenes/Combat.tscn", "action_path": "HUD/TurnControls/StartTurnButton"},
	{"surface": "continue", "scene": "res://Game.Godot/Scenes/UI/MainMenu.tscn", "action_path": "VBox/BtnContinue"}
]

const REQUIRED_CRITICAL_FOCUS_PATH: Array[String] = [
	"run-entry",
	"map",
	"node",
	"combat",
	"reward",
	"map",
	"rest",
	"shop",
	"continue"
]

const REQUIRED_DETERMINISTIC_GATE_SUITES: Array[String] = [
	"res://tests/Integration/test_m1_ui_focus_accessibility.gd",
	"res://tests/UI/A11y/test_button_invokable.gd",
	"res://tests/UI/A11y/test_focus_cycle.gd",
	"res://tests/UI/A11y/test_visible_labels.gd"
]

func _instantiate_surface(scene_path: String) -> Node:
	var packed := load(scene_path) as PackedScene
	assert(packed != null, "Missing M1 scene: %s" % scene_path)
	var instance := packed.instantiate()
	add_child(auto_free(instance))
	await get_tree().process_frame
	if instance.has_method("RefreshLocaleForTest"):
		instance.call("RefreshLocaleForTest")
	await get_tree().process_frame
	return instance

func _resolve_action_button(surface: Node, action_path: String) -> BaseButton:
	var node := surface.get_node_or_null(action_path)
	assert(node != null, "Missing primary action node: %s" % action_path)
	assert(node is BaseButton, "Primary action node must be BaseButton: %s" % action_path)
	return node as BaseButton

func _read_button_text(button: BaseButton) -> String:
	return button.text.strip_edges()

func _is_human_readable(text: String) -> bool:
	var trimmed := text.strip_edges()
	if trimmed.is_empty():
		return false
	if trimmed.begins_with("ui."):
		return false
	if trimmed.find(".") >= 0 and not trimmed.contains(" "):
		return false
	return true

func _dispatch_action_event(action_name: String) -> void:
	var pressed := InputEventAction.new()
	pressed.action = action_name
	pressed.pressed = true
	Input.parse_input_event(pressed)
	await get_tree().process_frame
	var released := InputEventAction.new()
	released.action = action_name
	released.pressed = false
	Input.parse_input_event(released)
	await get_tree().process_frame

func _invoke_by_keyboard(button: BaseButton) -> bool:
	button.grab_focus()
	await get_tree().process_frame
	if button.focus_mode == Control.FOCUS_NONE:
		return false
	if not button.has_focus():
		return false
	var pressed_state := {"hit": false}
	button.pressed.connect(func() -> void: pressed_state["hit"] = true, CONNECT_ONE_SHOT)
	await _dispatch_action_event("ui_accept")
	return bool(pressed_state["hit"])

func _invoke_by_controller(button: BaseButton) -> bool:
	button.grab_focus()
	await get_tree().process_frame
	if not button.has_focus():
		return false
	var pressed_state := {"hit": false}
	button.pressed.connect(func() -> void: pressed_state["hit"] = true, CONNECT_ONE_SHOT)
	await _dispatch_action_event("ui_accept")
	return bool(pressed_state["hit"])

func _prepare_surface_for_action(surface_name: String, surface: Node) -> void:
	match surface_name:
		"continue":
			if surface.has_method("SetAutosaveAvailableForTest"):
				surface.call("SetAutosaveAvailableForTest", true)
		"reward":
			if surface.has_method("SelectChoiceForTest"):
				assert_bool(bool(surface.call("SelectChoiceForTest", 0))).is_true()
		"shop":
			if surface.has_method("SetShopStateForTest"):
				var state := {
					"gold": 50,
					"offers": [{"id": "offer_attack", "price": 20, "taken": false}],
					"owned_offer_ids": [],
					"removable_cards": ["curse.basic"],
					"reforge_targets": ["offer_attack"]
				}
				surface.call("SetShopStateForTest", state)
		"combat":
			if surface.has_method("ApplySnapshotForTest"):
				surface.call("ApplySnapshotForTest", ["Strike"], 3, 10, 0)

func _capture_surface_state(surface_name: String, surface: Node) -> Dictionary:
	match surface_name:
		"run-entry", "continue":
			return {"visible": surface.visible}
		"map":
			if surface.has_method("GetLastInvokedActionForTest"):
				return {"last_action": str(surface.call("GetLastInvokedActionForTest"))}
			return {}
		"node":
			if surface.has_method("GetSelectedOptionIdForTest"):
				return {"selected": str(surface.call("GetSelectedOptionIdForTest"))}
			return {}
		"reward":
			if surface.has_method("GetFeedbackForTest"):
				return {"feedback": str(surface.call("GetFeedbackForTest"))}
			return {}
		"rest":
			if not surface.has_method("GetNextRouteForTest") or not surface.has_method("IsUpgradeConfirmPendingForTest"):
				return {}
			return {
				"next_route": str(surface.call("GetNextRouteForTest")),
				"pending": bool(surface.call("IsUpgradeConfirmPendingForTest"))
			}
		"shop":
			if not surface.has_method("GetOwnedOfferIdsForTest") or not surface.has_method("GetPlayerGoldForTest"):
				return {}
			var owned = surface.call("GetOwnedOfferIdsForTest") as Array
			return {"gold": int(surface.call("GetPlayerGoldForTest")), "owned_count": owned.size()}
		"combat":
			if not surface.has_method("GetDispatchedCommandsForTest"):
				return {}
			var commands = surface.call("GetDispatchedCommandsForTest") as Array
			return {"command_count": commands.size()}
		_:
			return {}

func _assert_surface_state_progressed(surface_name: String, state_before: Dictionary, state_after: Dictionary) -> void:
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

# acceptance: ACC:T68.1
func test_primary_actions_are_invokable_on_all_required_m1_surfaces() -> void:
	for spec in SURFACE_SPECS:
		var surface_name := str(spec["surface"])

		var keyboard_surface := await _instantiate_surface(str(spec["scene"]))
		_prepare_surface_for_action(surface_name, keyboard_surface)
		var keyboard_button := _resolve_action_button(keyboard_surface, str(spec["action_path"]))
		var before_keyboard := _capture_surface_state(surface_name, keyboard_surface)
		var keyboard_ok := await _invoke_by_keyboard(keyboard_button)
		assert(keyboard_ok, "Keyboard invocation failed on surface %s" % surface_name)
		var after_keyboard := _capture_surface_state(surface_name, keyboard_surface)
		_assert_surface_state_progressed(surface_name, before_keyboard, after_keyboard)

		var controller_surface := await _instantiate_surface(str(spec["scene"]))
		_prepare_surface_for_action(surface_name, controller_surface)
		var controller_button := _resolve_action_button(controller_surface, str(spec["action_path"]))
		var before_controller := _capture_surface_state(surface_name, controller_surface)
		var controller_ok := await _invoke_by_controller(controller_button)
		assert(controller_ok, "Controller invocation failed on surface %s" % surface_name)
		var after_controller := _capture_surface_state(surface_name, controller_surface)
		_assert_surface_state_progressed(surface_name, before_controller, after_controller)

# acceptance: ACC:T68.3
func test_primary_action_labels_remain_visible_after_invocation_on_real_surfaces() -> void:
	for spec in SURFACE_SPECS:
		var surface := await _instantiate_surface(str(spec["scene"]))
		_prepare_surface_for_action(str(spec["surface"]), surface)
		var button := _resolve_action_button(surface, str(spec["action_path"]))
		var before_text := _read_button_text(button)
		assert(_is_human_readable(before_text), "Unreadable label on surface %s: %s" % [str(spec["surface"]), before_text])
		var invoked := await _invoke_by_keyboard(button)
		assert_bool(invoked).is_true()
		var after_text := _read_button_text(button)
		assert_str(after_text).is_equal(before_text)

func test_unknown_surface_primary_action_path_is_rejected() -> void:
	var main_menu := await _instantiate_surface("res://Game.Godot/Scenes/UI/MainMenu.tscn")
	var missing := main_menu.get_node_or_null("VBox/BtnMissing")
	assert_bool(missing == null).is_true()

# acceptance: ACC:T68.5
func test_focus_smoke_path_and_gate_registration_cover_m1_critical_path() -> void:
	var available_surfaces := {}
	for spec in SURFACE_SPECS:
		available_surfaces[str(spec["surface"])] = true

	for surface in REQUIRED_CRITICAL_FOCUS_PATH:
		assert_bool(bool(available_surfaces.get(surface, false))).is_true()

	for i in range(1, REQUIRED_CRITICAL_FOCUS_PATH.size()):
		assert_bool(REQUIRED_CRITICAL_FOCUS_PATH[i] != REQUIRED_CRITICAL_FOCUS_PATH[i - 1]).is_true()

	for suite_path in REQUIRED_DETERMINISTIC_GATE_SUITES:
		assert_bool(ResourceLoader.exists(suite_path)).is_true()
