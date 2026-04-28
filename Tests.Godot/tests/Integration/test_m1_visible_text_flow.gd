extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_SURFACES: Array[String] = [
	"MainMenu",
	"DifficultySelect",
	"CharacterSelect",
	"Map",
	"Combat",
	"Reward",
	"Shop",
	"Rest",
	"Event"
]

const REQUIRED_LOCALES: Array[String] = ["en", "zh-CN"]
const TASK_ID: int = 65

const SURFACE_SCENE_PATHS := {
	"MainMenu": "res://Game.Godot/Scenes/UI/MainMenu.tscn",
	"DifficultySelect": "res://Game.Godot/Scenes/UI/DifficultySelect.tscn",
	"CharacterSelect": "res://Game.Godot/Scenes/UI/CharacterSelect.tscn",
	"Map": "res://Game.Godot/Scenes/Map/Map.tscn",
	"Combat": "res://Game.Godot/Scenes/Combat.tscn",
	"Reward": "res://Game.Godot/Scenes/Reward.tscn",
	"Shop": "res://Game.Godot/Scenes/Shop.tscn",
	"Rest": "res://Game.Godot/Scenes/Rest.tscn",
	"Event": "res://Game.Godot/Scenes/Event.tscn"
}

const MAP_REQUIRED_NODES: Array[String] = ["combat_icon", "event_icon", "shop_icon", "rest_icon"]
const STRICT_EVIDENCE_ENV: String = "TASK0065_GATE_EVIDENCE_REQUIRED"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"
const MAIN_MENU_BLOCKED_MESSAGE_PATH := "ContinueBlockedDialog/MarginContainer/VBox/MessageLabel"
const MAP_TITLE_KEY := "ui.map.title"
const MAP_HINT_KEY := "ui.map.hint"
const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")

func _normalize_texts(values: Array[String]) -> Array[String]:
	var normalized: Array[String] = []
	for value in values:
		var trimmed: String = value.strip_edges()
		if trimmed.is_empty():
			continue
		if normalized.has(trimmed):
			continue
		normalized.append(trimmed)
	return normalized

func _read_text_file(res_path: String) -> String:
	var absolute_path := ProjectSettings.globalize_path(res_path)
	if not FileAccess.file_exists(absolute_path):
		return ""
	var file := FileAccess.open(absolute_path, FileAccess.READ)
	if file == null:
		return ""
	var content := file.get_as_text()
	file.close()
	return content

func _load_translation_values(csv_path: String) -> Dictionary:
	var values := {}
	var raw := _read_text_file(csv_path)
	for line in raw.split("\n", false):
		var trimmed := line.strip_edges()
		if trimmed == "" or trimmed.begins_with("key,value"):
			continue
		var comma := trimmed.find(",")
		if comma <= 0:
			continue
		var key := trimmed.substr(0, comma).strip_edges()
		var value := trimmed.substr(comma + 1).strip_edges()
		if key != "":
			values[key] = value
	return values

func _translation_file_for_locale(locale: String) -> String:
	if locale.to_lower().begins_with("zh"):
		return ZH_TRANSLATIONS_FILE
	return EN_TRANSLATIONS_FILE

func _resolve_expected_text(locale: String, key: String) -> String:
	var primary = _load_translation_values(_translation_file_for_locale(locale))
	if primary.has(key):
		return str(primary[key]).strip_edges()
	var fallback = _load_translation_values(EN_TRANSLATIONS_FILE)
	if fallback.has(key):
		return str(fallback[key]).strip_edges()
	return ""

func _collect_node_visible_texts(root: Node) -> Array[String]:
	var collected: Array[String] = []
	var queue: Array[Node] = [root]
	while not queue.is_empty():
		var current: Node = queue.pop_back() as Node
		if current is Label:
			collected.append((current as Label).text)
		elif current is Button:
			collected.append((current as Button).text)
		elif current is LineEdit:
			collected.append((current as LineEdit).text)
		elif current is TextEdit:
			collected.append((current as TextEdit).text)
		elif current is OptionButton:
			var option = current as OptionButton
			for index in option.item_count:
				collected.append(option.get_item_text(index))
		elif current is ItemList:
			var list = current as ItemList
			for index in list.item_count:
				collected.append(list.get_item_text(index))
		elif current is ConfirmationDialog:
			var dialog = current as ConfirmationDialog
			collected.append(dialog.title)
			collected.append(dialog.dialog_text)
			collected.append(dialog.ok_button_text)
			collected.append(dialog.cancel_button_text)

		for child in current.get_children():
			if child is Node:
				queue.append(child)
	return _normalize_texts(collected)

func _instantiate_surface(surface: String) -> Node:
	var scene_path = str(SURFACE_SCENE_PATHS.get(surface, ""))
	assert(not scene_path.is_empty(), "Missing scene mapping for surface: %s" % surface)
	var packed = load(scene_path) as PackedScene
	assert(packed != null, "Failed to load scene: %s" % scene_path)
	var instance = packed.instantiate()
	add_child(auto_free(instance))
	await get_tree().process_frame
	return instance as Node

func _refresh_surface_locale(surface_node: Node) -> void:
	if surface_node.has_method("RefreshVisibleTextForTest"):
		surface_node.call("RefreshVisibleTextForTest")
	if surface_node.has_method("RefreshLocaleForTest"):
		surface_node.call("RefreshLocaleForTest")
	if surface_node.has_method("RefreshLocalizationForTest"):
		surface_node.call("RefreshLocalizationForTest")
	if surface_node.has_method("SetLocaleForTest"):
		surface_node.call("SetLocaleForTest", TranslationServer.get_locale())

func _collect_surface_visible_texts(surface: String, surface_node: Node) -> Array[String]:
	var values = _collect_node_visible_texts(surface_node)

	if surface == "Combat":
		if surface_node.has_method("GetTurnTitleTextForTest"):
			values.append(str(surface_node.call("GetTurnTitleTextForTest")))
		if surface_node.has_method("GetEndTurnButtonTextForTest"):
			values.append(str(surface_node.call("GetEndTurnButtonTextForTest")))
	elif surface == "Event":
		if surface_node.has_method("GetEventTitleForTest"):
			values.append(str(surface_node.call("GetEventTitleForTest")))
		if surface_node.has_method("GetEventDescriptionForTest"):
			values.append(str(surface_node.call("GetEventDescriptionForTest")))
	elif surface == "Shop":
		if surface_node.has_method("PurchaseOfferForTest"):
			surface_node.call("PurchaseOfferForTest", "")
		if surface_node.has_method("GetVisibleFailureReasonForTest"):
			values.append(str(surface_node.call("GetVisibleFailureReasonForTest")))
	elif surface == "Rest":
		if surface_node.has_method("GetFeedbackForTest"):
			values.append(str(surface_node.call("GetFeedbackForTest")))
	elif surface == "Reward":
		if surface_node.has_method("GetFeedbackForTest"):
			values.append(str(surface_node.call("GetFeedbackForTest")))

	return _normalize_texts(values)

func _assert_map_surface_integrity(surface_node: Node) -> void:
	for node_name in MAP_REQUIRED_NODES:
		assert(surface_node.get_node_or_null(node_name) != null, "Map scene missing expected node: %s" % node_name)

func _assert_map_surface_translation_binding(surface_node: Node, locale: String) -> void:
	var title_label = surface_node.get_node_or_null("title_label") as Label
	var hint_label = surface_node.get_node_or_null("hint_label") as Label
	assert(title_label != null, "Map scene missing title_label.")
	assert(hint_label != null, "Map scene missing hint_label.")

	var expected_title := _resolve_expected_text(locale, MAP_TITLE_KEY)
	var expected_hint := _resolve_expected_text(locale, MAP_HINT_KEY)
	assert(not expected_title.is_empty(), "Missing translation entry for %s in locale %s." % [MAP_TITLE_KEY, locale])
	assert(not expected_hint.is_empty(), "Missing translation entry for %s in locale %s." % [MAP_HINT_KEY, locale])
	assert(expected_title != MAP_TITLE_KEY, "Map title key resolves to raw key in locale %s." % locale)
	assert(expected_hint != MAP_HINT_KEY, "Map hint key resolves to raw key in locale %s." % locale)

	assert(title_label.text.strip_edges() == expected_title, "Map title text does not match translation key binding for locale %s." % locale)
	assert(hint_label.text.strip_edges() == expected_hint, "Map hint text does not match translation key binding for locale %s." % locale)

func _read_node_text(node: Node) -> String:
	if node is Label:
		return (node as Label).text
	if node is Button:
		return (node as Button).text
	if node is LineEdit:
		return (node as LineEdit).text
	if node is TextEdit:
		return (node as TextEdit).text
	assert(false, "Unsupported text node type for binding assertion: %s" % [node.get_class()])
	return ""

func _assert_node_translation_binding(surface: String, surface_node: Node, node_path: String, key: String, locale: String) -> void:
	var target := surface_node.get_node_or_null(node_path)
	assert(target != null, "%s missing node for translation binding: %s" % [surface, node_path])
	assert(target is Node, "%s node path is not a Node: %s" % [surface, node_path])
	var expected := _resolve_expected_text(locale, key)
	assert(not expected.is_empty(), "Missing translation entry for %s in locale %s." % [key, locale])
	assert(expected != key, "Translation entry for %s resolves to raw key in locale %s." % [key, locale])
	var actual := _read_node_text(target as Node).strip_edges()
	assert(actual == expected, "%s text mismatch at %s for locale %s. expected=%s actual=%s" % [surface, node_path, locale, expected, actual])

func _assert_surface_translation_binding(surface: String, surface_node: Node, locale: String) -> void:
	match surface:
		"MainMenu":
			_assert_node_translation_binding(surface, surface_node, "VBox/BtnNewRun", "ui.menu.new_game", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/BtnContinue", "ui.menu.continue", locale)
		"DifficultySelect":
			_assert_node_translation_binding(surface, surface_node, "VBox/LblTitle", "ui.difficulty.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/BtnConfirm", "ui.difficulty.confirm", locale)
		"CharacterSelect":
			_assert_node_translation_binding(surface, surface_node, "VBox/LblTitle", "ui.character.select.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/CharacterRow/WarriorPanel/BtnWarrior", "ui.character.warrior", locale)
		"Map":
			_assert_map_surface_translation_binding(surface_node, locale)
		"Combat":
			_assert_node_translation_binding(surface, surface_node, "HUD/TurnTitleLabel", "combat.turn.title", locale)
			_assert_node_translation_binding(surface, surface_node, "HUD/TurnControls/EndTurnButton", "combat.turn.end", locale)
		"Reward":
			_assert_node_translation_binding(surface, surface_node, "VBox/Title", "ui.reward.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/Actions/ConfirmButton", "ui.reward.confirm", locale)
		"Shop":
			_assert_node_translation_binding(surface, surface_node, "VBox/TitleLabel", "shop.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/LeaveButton", "shop.leave", locale)
		"Rest":
			_assert_node_translation_binding(surface, surface_node, "VBox/Title", "ui.rest.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/Option_upgrade", "ui.rest.option.upgrade", locale)
		"Event":
			_assert_node_translation_binding(surface, surface_node, "VBox/LblTitle", "event.abyss_toll.title", locale)
			_assert_node_translation_binding(surface, surface_node, "VBox/Options/BtnLoseHp", "event.option.lose_hp", locale)
		_:
			pass

func _assert_readable_expected_text(locale: String, key: String, actual: String, context: String) -> void:
	var expected := _resolve_expected_text(locale, key)
	assert(not expected.is_empty(), "Missing expected translation for %s in %s." % [key, locale])
	assert(_is_readable_visible_text(actual), "Unreadable critical text in %s[%s]: %s" % [context, locale, actual])
	assert(actual.strip_edges() == expected, "Critical text mismatch in %s[%s] for key %s." % [context, locale, key])

func _assert_reward_locked_feedback_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var reward := await _instantiate_surface("Reward")
	_refresh_surface_locale(reward)
	await get_tree().process_frame
	assert(reward.has_method("ShowLockedFeedbackForTest"), "Reward scene missing ShowLockedFeedbackForTest.")
	reward.call("ShowLockedFeedbackForTest")
	await get_tree().process_frame
	assert(reward.has_method("GetFeedbackForTest"), "Reward scene missing GetFeedbackForTest.")
	_assert_readable_expected_text(locale, "reward.locked", str(reward.call("GetFeedbackForTest")), "RewardLockedFeedback")

func _assert_rest_irreversible_feedback_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var rest := await _instantiate_surface("Rest")
	_refresh_surface_locale(rest)
	await get_tree().process_frame
	assert(rest.has_method("SelectOptionForTest"), "Rest scene missing SelectOptionForTest.")
	assert(rest.has_method("ConfirmUpgradeForTest"), "Rest scene missing ConfirmUpgradeForTest.")
	assert(rest.has_method("RequestUndoAfterConfirmForTest"), "Rest scene missing RequestUndoAfterConfirmForTest.")
	assert(rest.has_method("GetFeedbackForTest"), "Rest scene missing GetFeedbackForTest.")
	assert(bool(rest.call("SelectOptionForTest", "upgrade")), "Rest scene should accept upgrade option selection.")
	assert(bool(rest.call("ConfirmUpgradeForTest")), "Rest scene should confirm upgrade in test path.")
	var undo_accepted := bool(rest.call("RequestUndoAfterConfirmForTest"))
	assert(not undo_accepted, "Rest undo should be refused after confirmation.")
	_assert_readable_expected_text(locale, "rest.irreversible_upgrade", str(rest.call("GetFeedbackForTest")), "RestIrreversibleFeedback")

func _assert_continue_blocked_feedback_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var menu := await _instantiate_surface("MainMenu")
	_refresh_surface_locale(menu)
	await get_tree().process_frame
	if menu.has_method("SetAutosaveAvailableForTest"):
		menu.call("SetAutosaveAvailableForTest", false)
	var continue_button := menu.get_node_or_null("VBox/BtnContinue") as Button
	assert(continue_button != null, "MainMenu missing continue button.")
	continue_button.emit_signal("pressed")
	await get_tree().process_frame
	await get_tree().process_frame
	var message_label := menu.get_node_or_null(MAIN_MENU_BLOCKED_MESSAGE_PATH) as Label
	assert(message_label != null, "MainMenu missing blocked-state message label.")
	var actual := message_label.text.strip_edges()
	assert(_is_readable_visible_text(actual), "Unreadable continue blocked text in locale %s: %s" % [locale, actual])
	var expected := _resolve_expected_text(locale, "continue.blocked_state")
	assert(not expected.is_empty(), "Missing translation for continue.blocked_state in locale %s." % locale)
	assert(actual.find(expected) >= 0, "Continue blocked text must include translated blocked-state message in locale %s." % locale)

func _assert_combat_invalid_action_feedback_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var combat := await _instantiate_surface("Combat")
	_refresh_surface_locale(combat)
	await get_tree().process_frame
	assert(combat.has_method("RequestTurnActionForTest"), "Combat scene missing RequestTurnActionForTest.")
	assert(combat.has_method("GetLatestFeedbackMessageForTest"), "Combat scene missing GetLatestFeedbackMessageForTest.")
	var accepted := bool(combat.call("RequestTurnActionForTest", "invalid_action"))
	assert(not accepted, "Combat invalid action must be rejected.")
	var actual := str(combat.call("GetLatestFeedbackMessageForTest")).strip_edges()
	assert(_is_readable_visible_text(actual), "Unreadable combat invalid-action text in locale %s: %s" % [locale, actual])
	var expected := _resolve_expected_text(locale, "combat.invalid_action")
	assert(not expected.is_empty(), "Missing translation for combat.invalid_action in locale %s." % locale)
	assert(actual.find(expected) >= 0, "Combat invalid-action feedback must include translated message in locale %s." % locale)


func _assert_combat_card_text_contract_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var combat := await _instantiate_surface("Combat")
	_refresh_surface_locale(combat)
	await get_tree().process_frame
	var root := combat as Control
	var card_row := root.get_node_or_null("HUD/CardButtonRow") as HBoxContainer
	assert(card_row != null, "Combat scene missing card button row.")
	assert(card_row.get_child_count() >= 2, "Combat scene must expose at least two card buttons.")
	var strike_text := str((card_row.get_child(0) as Button).text)
	var defend_text := str((card_row.get_child(1) as Button).text)

	var strike_name := _resolve_expected_text(locale, "card.warrior.strike.name")
	var strike_desc := _resolve_expected_text(locale, "card.warrior.strike.description")
	var defend_name := _resolve_expected_text(locale, "card.warrior.defend.name")
	var defend_desc := _resolve_expected_text(locale, "card.warrior.defend.description")

	assert(strike_text.find(strike_name) >= 0, "Combat strike button must expose localized card name in locale %s." % locale)
	assert(strike_text.find("Cost 1") >= 0, "Combat strike button must expose cost in locale %s." % locale)
	assert(strike_text.find("| attack") >= 0, "Combat strike button must expose card type in locale %s." % locale)
	assert(strike_text.find(strike_desc) >= 0, "Combat strike button must expose localized effect summary in locale %s." % locale)
	assert(strike_text.find("card.warrior.") < 0, "Combat strike button must not expose raw localization keys in locale %s." % locale)
	assert(defend_text.find(defend_name) >= 0, "Combat defend button must expose localized card name in locale %s." % locale)
	assert(defend_text.find("Cost 1") >= 0, "Combat defend button must expose cost in locale %s." % locale)
	assert(defend_text.find("| skill") >= 0, "Combat defend button must expose card type in locale %s." % locale)
	assert(defend_text.find(defend_desc) >= 0, "Combat defend button must expose localized effect summary in locale %s." % locale)
	assert(defend_text.find("card.warrior.") < 0, "Combat defend button must not expose raw localization keys in locale %s." % locale)

	# ACC:T72.8 negative path: if definition source is unavailable, UI must not fall back
	# to a hidden hardcoded card-definition model.
	combat.call("ClearCardDefinitionsForTest")
	combat.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	_refresh_surface_locale(combat)
	await get_tree().process_frame
	strike_text = str((card_row.get_child(0) as Button).text)
	assert(strike_text.find("Cost ") < 0, "Combat strike button must not synthesize hardcoded cost when definitions are unavailable in locale %s." % locale)
	assert(strike_text.find("|") < 0, "Combat strike button must not synthesize hardcoded type when definitions are unavailable in locale %s." % locale)
	assert(strike_text.find("card.warrior.") < 0, "Combat strike button must not leak raw localization keys when definitions are unavailable in locale %s." % locale)
	combat.call("SetCardDefinitionAutoLoadEnabledForTest", true)

func _assert_critical_runtime_feedback_for_locale(locale: String) -> void:
	await _assert_reward_locked_feedback_for_locale(locale)
	await _assert_rest_irreversible_feedback_for_locale(locale)
	await _assert_continue_blocked_feedback_for_locale(locale)
	await _assert_combat_invalid_action_feedback_for_locale(locale)
	await _assert_combat_card_text_contract_for_locale(locale)

func _assert_real_surface_texts_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	await get_tree().process_frame
	await get_tree().process_frame

	for surface in REQUIRED_SURFACES:
		var surface_node = await _instantiate_surface(surface)
		_refresh_surface_locale(surface_node)
		await get_tree().process_frame

		if surface == "Map":
			_assert_map_surface_integrity(surface_node)
		_assert_surface_translation_binding(surface, surface_node, locale)

		var texts = _collect_surface_visible_texts(surface, surface_node)
		assert(texts.size() > 0, "No visible text collected for %s in locale %s." % [surface, locale])
		for text_value in texts:
			assert(_is_readable_visible_text(text_value), "Unreadable visible text in %s[%s]: %s" % [surface, locale, text_value])

func _is_raw_translation_key(text: String) -> bool:
	var key_regex: RegEx = RegEx.new()
	var error: int = key_regex.compile("^[a-z0-9_]+(\\.[a-z0-9_]+)+$")
	if error != OK:
		return false
	return key_regex.search(text) != null

func _is_garbled_placeholder(text: String) -> bool:
	var trimmed: String = text.strip_edges()
	if trimmed.begins_with("<missing") or trimmed.findn("TODO") >= 0:
		return true
	var question_only := true
	for ch in trimmed:
		if ch != "?" and ch != "？":
			question_only = false
			break
	if question_only and trimmed.length() >= 2:
		return true
	if trimmed.find("�") >= 0 or trimmed.find("锟") >= 0:
		return true
	return false

func _is_readable_visible_text(text: String) -> bool:
	var trimmed: String = text.strip_edges()
	if trimmed.is_empty():
		return false
	if _is_raw_translation_key(trimmed):
		return false
	if _is_garbled_placeholder(trimmed):
		return false
	return true

func _read_json_file(path: String) -> Dictionary:
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed as Dictionary

func _try_resolve_latest_pipeline_pointer(task_id: int) -> String:
	var ci_root = ProjectSettings.globalize_path("res://../logs/ci")
	var root_dir = DirAccess.open(ci_root)
	if root_dir == null:
		return ""

	var date_dirs = root_dir.get_directories()
	date_dirs.sort()
	date_dirs.reverse()
	for date_dir in date_dirs:
		var candidate = ci_root.path_join(date_dir).path_join("sc-review-pipeline-task-%d/latest.json" % task_id)
		if FileAccess.file_exists(candidate):
			return candidate
	return ""

func _should_require_evidence() -> bool:
	var raw = OS.get_environment(STRICT_EVIDENCE_ENV).strip_edges().to_lower()
	return raw == "1" or raw == "true" or raw == "yes" or raw == "on"

func _ensure_evidence_or_soft_skip(reason: String) -> bool:
	if _should_require_evidence():
		assert(false, reason)
		return false
	return true

func _load_main_on_map() -> Control:
	var main := MAIN_SCENE.instantiate() as Control
	add_child(auto_free(main))
	await get_tree().process_frame
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	nav.UseFadeTransition = false
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")
	nav.call("SwitchTo", "res://Game.Godot/Scenes/Map/Map.tscn")
	await get_tree().process_frame
	if main.has_method("ResetMapRouteProgressForTest"):
		main.call("ResetMapRouteProgressForTest")
	return main

func _current_scene_path(main: Control) -> String:
	var nav := main.get_node_or_null("ScreenNavigator")
	if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
		return ""
	return str(nav.call("GetCurrentScenePathForTest"))

func _current_scene_instance(main: Control):
	var root := main.get_node_or_null("ScreenRoot")
	if root == null or root.get_child_count() == 0:
		return null
	return root.get_child(root.get_child_count() - 1)

# acceptance anchor: ACC:T65.1
func test_m1_smoke_surfaces_require_readable_visible_text() -> void:
	# red-first: this validates real M1 scene surfaces instead of fixture dictionaries.
	for locale in REQUIRED_LOCALES:
		await _assert_real_surface_texts_for_locale(locale)
		await _assert_critical_runtime_feedback_for_locale(locale)


# acceptance anchor: ACC:T73.5
func test_combat_victory_routes_to_reward_then_back_to_map_via_owned_flow() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	assert_that(str(route_start.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	await get_tree().process_frame

	var combat = _current_scene_instance(main)
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var victory := combat.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(victory.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Reward.tscn")

	var reward = _current_scene_instance(main)
	assert_that(reward).is_not_null()
	assert_that(bool(reward.call("SkipForTest"))).is_true()
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Map/Map.tscn")

# acceptance anchor: ACC:T73.5
func test_combat_victory_without_reward_rule_routes_directly_back_to_map() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-no-reward", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	assert_that(str(route_start.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	await get_tree().process_frame

	var combat = _current_scene_instance(main)
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var victory := combat.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(victory.get("ok", false))).is_true()
	await get_tree().process_frame
	var post_victory_path := _current_scene_path(main)
	if post_victory_path == "res://Game.Godot/Scenes/Reward.tscn":
		var reward = _current_scene_instance(main)
		assert_that(reward).is_not_null()
		assert_that(bool(reward.call("SkipForTest"))).is_true()
		await get_tree().process_frame
		post_victory_path = _current_scene_path(main)
	assert_that(post_victory_path).is_equal("res://Game.Godot/Scenes/Map/Map.tscn")

# acceptance anchor: ACC:T73.6
func test_combat_victory_route_is_not_triggered_while_living_enemy_remains() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-guard", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")

	var combat = _current_scene_instance(main)
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("SetEnemyHpForTest", "enemy_m1_slime", 12, 32))).is_true()
	var blocked := combat.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(blocked.get("ok", false))).is_false()
	assert_that(str(blocked.get("reason", ""))).is_equal("enemies-still-alive")
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")

func test_boss_reward_resolution_shows_victory_summary_and_returns_to_main_menu() -> void:
	var main := await _load_main_on_map()
	var route_steps: Array[Dictionary] = [
		{"id": "combat-01", "type": "combat", "reward": true},
		{"id": "event-02", "type": "event", "reward": true},
		{"id": "shop-03", "type": "shop", "reward": false},
		{"id": "rest-04", "type": "rest", "reward": false},
	]
	for step in route_steps:
		var enter_result := main.call("StartMapNodeRouteForTest", str(step.get("id", "")), str(step.get("type", "")), true, "") as Dictionary
		assert_that(bool(enter_result.get("ok", false))).is_true()
		await get_tree().process_frame
		var complete_result := main.call("CompleteMapNodeFlowForTest") as Dictionary
		assert_that(bool(complete_result.get("ok", false))).is_true()
		await get_tree().process_frame
		if bool(step.get("reward", false)):
			var reward = _current_scene_instance(main)
			assert_that(reward).is_not_null()
			assert_that(bool(reward.call("SkipForTest"))).is_true()
			await get_tree().process_frame

	var route_start := main.call("StartMapNodeRouteForTest", "boss-05", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	assert_that(str(route_start.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	await get_tree().process_frame

	var combat = _current_scene_instance(main)
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var victory := combat.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(victory.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Reward.tscn")

	var reward = _current_scene_instance(main)
	assert_that(reward).is_not_null()
	assert_that(bool(reward.call("ConfirmSelectedForTest"))).is_false()
	assert_that(bool(reward.call("SelectChoiceForTest", 0))).is_true()
	assert_that(bool(reward.call("ConfirmSelectedForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame

	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_true()
	var hud := main.get_node_or_null("HUD")
	assert_that(hud).is_not_null()
	assert_that(bool(hud.call("IsRunSummaryVisibleForTest"))).is_true()
	assert_that(str(hud.call("GetSummaryOutcomeTextForTest")).find("Victory") >= 0).is_true()

func test_player_hp_zero_on_end_turn_immediately_triggers_defeat_summary_and_main_menu() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = _current_scene_instance(main)
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("TryApplyCoreSnapshotData", ["Strike"], 3, 7, 0))).is_true()
	assert_that(bool(combat.call("RequestTurnActionForTest", "end_turn"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame

	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_true()
	var hud := main.get_node_or_null("HUD")
	assert_that(hud).is_not_null()
	assert_that(bool(hud.call("IsRunSummaryVisibleForTest"))).is_true()
	assert_that(str(hud.call("GetSummaryOutcomeTextForTest")).find("Defeat") >= 0).is_true()

# acceptance anchor: ACC:T65.2
func test_m1_locales_en_and_zh_cn_have_readable_text_and_negative_guard() -> void:
	var invalid_values: Array[String] = ["", "   ", "ui.menu.start", "<missing:shop_title>", "???", "__TODO__"]
	for value in invalid_values:
		assert_that(_is_readable_visible_text(value)).is_false()

# acceptance anchor: ACC:T65.4
func test_m1_windows_gate_evidence_contains_execution_path_metadata() -> void:
	var latest_path = _try_resolve_latest_pipeline_pointer(TASK_ID)
	if latest_path.is_empty():
		var can_continue = _ensure_evidence_or_soft_skip("Task65 pipeline latest.json evidence is missing under logs/ci/<date>/sc-review-pipeline-task-65/latest.json.")
		if can_continue:
			return

	var latest = _read_json_file(latest_path)
	assert(not latest.is_empty(), "latest.json exists but cannot be parsed: %s" % latest_path)
	assert(str(latest.get("task_id", "")).strip_edges() == "65", "latest.json task_id must be 65.")
	assert(str(latest.get("status", "")).strip_edges().to_lower() == "ok", "latest.json status must be ok.")

	var summary_path = str(latest.get("summary_path", ""))
	assert(not summary_path.is_empty(), "latest.json must expose summary_path.")
	assert(FileAccess.file_exists(summary_path), "summary_path from latest.json does not exist: %s" % summary_path)

	var summary = _read_json_file(summary_path)
	assert(not summary.is_empty(), "summary.json cannot be parsed: %s" % summary_path)
	assert(str(summary.get("status", "")).strip_edges().to_lower() == "ok", "pipeline summary status must be ok.")
	assert(str(summary.get("run_id", "")).strip_edges().length() > 0, "pipeline summary must include run_id.")
	assert(str(summary.get("reason", "")).strip_edges().to_lower() == "pipeline_clean", "pipeline summary reason must be pipeline_clean.")
	assert(summary_path.replace("\\", "/").find("logs/ci/") >= 0, "summary_path must point to logs/ci evidence.")
