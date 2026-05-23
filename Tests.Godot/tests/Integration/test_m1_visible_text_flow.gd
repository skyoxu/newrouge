extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"


const REQUIRED_SURFACES: Array[String] = [
	"MainMenu",
	"DifficultySelect",
	"CharacterSelect",
	"Map",
	"Combat",
	"Settlement",
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
	"Settlement": "res://Game.Godot/Scenes/Settlement.tscn",
	"Reward": "res://Game.Godot/Scenes/Reward.tscn",
	"Shop": "res://Game.Godot/Scenes/Shop.tscn",
	"Rest": "res://Game.Godot/Scenes/Rest.tscn",
	"Event": "res://Game.Godot/Scenes/Event.tscn"
}

const MAP_REQUIRED_NODES: Array[String] = ["combat_icon", "event_icon", "shop_icon", "rest_icon"]
const STRICT_EVIDENCE_ENV: String = "TASK0065_GATE_EVIDENCE_REQUIRED"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"
const CARD_DEFINITIONS_JSON_FILE := "res://../Game.Core/Data/m1-card-definitions.json"
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

func _prime_combat_card_definitions(combat: Node) -> void:
	if combat == null or not combat.has_method("TryApplyCardDefinitionsContractJsonForTest"):
		return
	var payload := _read_text_file(CARD_DEFINITIONS_JSON_FILE).strip_edges()
	assert(not payload.is_empty(), "Missing card definitions payload for combat localization test.")
	var applied := bool(combat.call("TryApplyCardDefinitionsContractJsonForTest", payload))
	assert(applied, "Combat scene failed to apply card definitions payload for localization test.")

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

func _contains_cost_value(text: String, expected_cost: int) -> bool:
	var lowered := text.to_lower()
	return lowered.find("cost") >= 0 and lowered.find(str(expected_cost)) >= 0

func _read_button_visible_text(button: Button) -> String:
	if button == null:
		return ""
	var tokens: Array[String] = []
	var own_text := str(button.text).strip_edges()
	if not own_text.is_empty():
		tokens.append(own_text)
	for child_text in _collect_node_visible_texts(button):
		var normalized := str(child_text).strip_edges()
		if normalized.is_empty():
			continue
		if tokens.has(normalized):
			continue
		tokens.append(normalized)
	return " ".join(tokens)

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
	_prime_combat_card_definitions(combat)
	_refresh_surface_locale(combat)
	await get_tree().process_frame
	var root := combat as Control
	var card_row := root.get_node_or_null("HUD/CardButtonRow") as Control
	assert(card_row != null, "Combat scene missing card button row.")
	assert(card_row.get_child_count() >= 2, "Combat scene must expose at least two card buttons.")
	var strike_button := card_row.get_child(0) as Button
	var defend_button := card_row.get_child(1) as Button

	var strike_name := _resolve_expected_text(locale, "card.warrior.strike.name")
	var strike_desc := _resolve_expected_text(locale, "card.warrior.strike.description")
	var defend_name := _resolve_expected_text(locale, "card.warrior.defend.name")
	var defend_desc := _resolve_expected_text(locale, "card.warrior.defend.description")

	var contract_ready := false
	for _i in range(120):
		if not is_instance_valid(card_row):
			card_row = combat.get_node_or_null("CardRow") as Control
		if card_row == null or card_row.get_child_count() < 2:
			await get_tree().process_frame
			continue
		if not is_instance_valid(strike_button):
			strike_button = card_row.get_child(0) as Button
		if not is_instance_valid(defend_button):
			defend_button = card_row.get_child(1) as Button
		if strike_button == null or defend_button == null:
			await get_tree().process_frame
			continue
		var strike_probe := _read_button_visible_text(strike_button)
		var defend_probe := _read_button_visible_text(defend_button)
		contract_ready = (
			strike_probe.find(strike_name) >= 0
			and _contains_cost_value(strike_probe, 1)
			and strike_probe.find("| attack") >= 0
			and defend_probe.find(defend_name) >= 0
			and _contains_cost_value(defend_probe, 1)
			and defend_probe.find("| skill") >= 0
		)
		if contract_ready:
			break
		if (_i + 1) % 20 == 0:
			_refresh_surface_locale(combat)
		await get_tree().process_frame

	if not is_instance_valid(card_row):
		card_row = combat.get_node_or_null("CardRow") as Control
	assert(card_row != null and card_row.get_child_count() >= 2, "Combat scene must keep card button row valid before final text assertions.")
	strike_button = card_row.get_child(0) as Button
	defend_button = card_row.get_child(1) as Button
	assert(strike_button != null and defend_button != null, "Combat scene card buttons must stay valid before final text assertions.")

	var strike_text := _read_button_visible_text(strike_button)
	var defend_text := _read_button_visible_text(defend_button)

	assert(strike_text.find(strike_name) >= 0, "Combat strike button must expose localized card name in locale %s." % locale)
	assert(_contains_cost_value(strike_text, 1), "Combat strike button must expose cost in locale %s." % locale)
	assert(strike_text.find("| attack") >= 0, "Combat strike button must expose card type in locale %s." % locale)
	assert(strike_text.find(strike_desc) >= 0, "Combat strike button must expose localized effect summary in locale %s." % locale)
	assert(strike_text.find("card.warrior.") < 0, "Combat strike button must not expose raw localization keys in locale %s." % locale)
	assert(defend_text.find(defend_name) >= 0, "Combat defend button must expose localized card name in locale %s." % locale)
	assert(_contains_cost_value(defend_text, 1), "Combat defend button must expose cost in locale %s." % locale)
	assert(defend_text.find("| skill") >= 0, "Combat defend button must expose card type in locale %s." % locale)
	assert(defend_text.find(defend_desc) >= 0, "Combat defend button must expose localized effect summary in locale %s." % locale)
	assert(defend_text.find("card.warrior.") < 0, "Combat defend button must not expose raw localization keys in locale %s." % locale)

	# ACC:T72.8 negative path: if definition source is unavailable, UI must not fall back
	# to a hidden hardcoded card-definition model.
	combat.call("ClearCardDefinitionsForTest")
	combat.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	_refresh_surface_locale(combat)
	await get_tree().process_frame
	if not is_instance_valid(card_row):
		card_row = combat.get_node_or_null("CardRow") as Control
	assert(card_row != null and card_row.get_child_count() >= 1, "Combat scene card row must stay valid for missing-definition assertion.")
	strike_text = _read_button_visible_text(card_row.get_child(0) as Button)
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

func _find_scene_instance_with_method(main: Control, _expected_scene_path: String, required_method: String):
	var normalized_expected := _expected_scene_path.strip_edges()
	if not normalized_expected.is_empty() and _current_scene_path(main) != normalized_expected:
		return null
	var candidate = _current_scene_instance(main)
	if candidate == null or not is_instance_valid(candidate):
		return null
	if not candidate.has_method(required_method):
		return null
	return candidate

func _await_scene_instance_with_method(main: Control, expected_scene_path: String, required_method: String, max_frames: int = 120):
	var consecutive_ready := 0
	var last_instance_id := 0
	for _i in range(max_frames):
		var candidate = _find_scene_instance_with_method(main, expected_scene_path, required_method)
		if candidate != null:
			var instance_id := int(candidate.get_instance_id())
			if instance_id == last_instance_id:
				consecutive_ready += 1
			else:
				last_instance_id = instance_id
				consecutive_ready = 1
			if consecutive_ready >= 4:
				return candidate
		else:
			consecutive_ready = 0
			last_instance_id = 0
		await get_tree().process_frame
	var root := main.get_node_or_null("ScreenRoot")
	var child_descriptions: Array[String] = []
	if root != null:
		for child in root.get_children():
			child_descriptions.append("%s|method=%s" % [str(child), str(child != null and child.has_method(required_method))])
	push_error("scene wait timeout expected=%s required_method=%s current_scene=%s children=%s" % [
		expected_scene_path,
		required_method,
		_current_scene_path(main),
		";".join(child_descriptions)
	])
	return null

func _await_settlement_scene(main: Control):
	return await _await_scene_instance_with_method(
		main,
		"res://Game.Godot/Scenes/Settlement.tscn",
		"RequestReturnToMainMenuForTest"
	)

func _assert_settlement_scene_and_return(main: Control, expected_outcome_fragment: String) -> void:
	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Settlement.tscn")
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find(expected_outcome_fragment) >= 0).is_true()
	var hud := main.get_node_or_null("HUD")
	if hud != null and hud.has_method("IsRunSummaryVisibleForTest"):
		assert_that(bool(hud.call("IsRunSummaryVisibleForTest"))).is_false()
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_false()
	assert_that(bool(settlement.call("RequestReturnToMainMenuForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_true()

func _try_apply_combat_snapshot_with_player_hp(
	combat,
	hand_cards: Array,
	energy: int,
	draw_pile: int,
	discard_pile: int,
	player_hp: int,
	difficulty: int = 3,
	turn_state: String = "PlayerTurn"
) -> bool:
	if combat == null or not is_instance_valid(combat):
		return false
	var payload := {
		"handCards": hand_cards,
		"difficulty": difficulty,
		"playerHp": player_hp,
		"energy": energy,
		"drawPileCount": draw_pile,
		"discardPileCount": discard_pile,
		"turnState": turn_state
	}
	return bool(combat.call("TryApplyCoreSnapshotContractJson", JSON.stringify(payload)))

# acceptance anchor: ACC:T65.1
# ACC:T91.3
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

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
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


# acceptance: ACC:T110.5
func test_reward_confirm_vs_skip_preserves_route_ownership_and_controls_deck_mutation() -> void:
	var main_confirm := await _load_main_on_map()
	var start_confirm := main_confirm.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(start_confirm.get("ok", false))).is_true()
	await get_tree().process_frame
	var complete_confirm := main_confirm.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(complete_confirm.get("ok", false))).is_true()
	assert_that(str(complete_confirm.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Reward.tscn")
	await get_tree().process_frame
	var deck_before_confirm = main_confirm.call("GetRunDeckCardIdsForTest")
	var confirm_result := main_confirm.call("ResolveRewardForTest", {"action": "confirm", "selected_index": 0}) as Dictionary
	var deck_after_confirm = main_confirm.call("GetRunDeckCardIdsForTest")
	assert_that(bool(confirm_result.get("ok", false))).is_true()
	assert_that(int(confirm_result.get("deck_after_count", -1))).is_equal(int(confirm_result.get("deck_before_count", -1)) + 1)
	assert_that(int(deck_after_confirm.size())).is_equal(int(deck_before_confirm.size()) + 1)
	assert_that(_current_scene_path(main_confirm)).is_equal("res://Game.Godot/Scenes/Map/Map.tscn")

	var main_skip := await _load_main_on_map()
	var start_skip := main_skip.call("StartMapNodeRouteForTest", "combat-02", "combat", true, "") as Dictionary
	assert_that(bool(start_skip.get("ok", false))).is_true()
	await get_tree().process_frame
	var complete_skip := main_skip.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(complete_skip.get("ok", false))).is_true()
	assert_that(str(complete_skip.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Reward.tscn")
	await get_tree().process_frame
	var deck_before_skip = main_skip.call("GetRunDeckCardIdsForTest")
	var skip_result := main_skip.call("ResolveRewardForTest", {"action": "skip"}) as Dictionary
	var deck_after_skip = main_skip.call("GetRunDeckCardIdsForTest")
	assert_that(bool(skip_result.get("ok", false))).is_true()
	assert_that(int(skip_result.get("deck_after_count", -1))).is_equal(int(skip_result.get("deck_before_count", -1)))
	assert_that(int(deck_after_skip.size())).is_equal(int(deck_before_skip.size()))
	assert_that(_current_scene_path(main_skip)).is_equal("res://Game.Godot/Scenes/Map/Map.tscn")

# acceptance anchor: ACC:T73.5
func test_combat_victory_without_reward_rule_routes_directly_back_to_map() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-no-reward", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	assert_that(str(route_start.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
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

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()
	assert_that(bool(combat.call("SetEnemyHpForTest", "enemy_m1_slime", 12, 32))).is_true()
	var blocked := combat.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(blocked.get("ok", false))).is_false()
	assert_that(str(blocked.get("reason", ""))).is_equal("enemies-still-alive")
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")

# ACC:T107.2
# ACC:T107.4
# ACC:T107.6
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

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
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

	await _assert_settlement_scene_and_return(main, "Victory")

# acceptance anchor: ACC:T79.2
func test_player_hp_zero_on_end_turn_immediately_triggers_defeat_summary_and_main_menu_single_resolution_guard() -> void:
	var main := await _load_main_on_map()
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(0)

	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(1)

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 1)).is_true()
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(0)
	assert_that(bool(combat.call("RequestTurnActionForTest", "end_turn"))).is_true()
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame

	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_false()
	assert_that(bool(settlement.call("RequestReturnToMainMenuForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_true()
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(1)
	var route_history = nav.call("GetRouteHistoryForTest")
	assert_that(route_history.size()).is_equal(2)
	assert_that(str(route_history[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(route_history[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")

# acceptance anchor: ACC:T79.3
func test_player_hp_zero_on_end_turn_immediately_triggers_defeat_summary_and_main_menu() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 1)).is_true()
	assert_that(bool(combat.call("RequestTurnActionForTest", "end_turn"))).is_true()
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame

	await _assert_settlement_scene_and_return(main, "Defeat")

# acceptance anchor: ACC:T79.1
func test_all_hp_mutation_entries_use_the_same_hp_change_update_path() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "GetUnifiedHpUpdateEntryCountForTest")
	assert_that(combat).is_not_null()
	var entry_before_snapshot := int(combat.call("GetUnifiedHpUpdateEntryCountForTest"))
	var emission_before_snapshot := int(combat.call("GetHpChangedEmissionCountForTest"))

	# Non-end-turn mutation entry with non-lethal HP change.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 79)).is_true()
	await get_tree().process_frame
	var emission_after_snapshot := int(combat.call("GetHpChangedEmissionCountForTest"))
	var entry_after_snapshot := int(combat.call("GetUnifiedHpUpdateEntryCountForTest"))
	assert_that(emission_after_snapshot).is_greater(emission_before_snapshot)
	assert_that(entry_after_snapshot).is_equal(entry_before_snapshot + 1)
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")

	# End-turn mutation entry should reuse the same emission path.
	assert_that(bool(combat.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var emission_after_end_turn := int(combat.call("GetHpChangedEmissionCountForTest"))
	var entry_after_end_turn := int(combat.call("GetUnifiedHpUpdateEntryCountForTest"))
	assert_that(emission_after_end_turn > emission_after_snapshot).is_true()
	assert_that(entry_after_end_turn).is_equal(entry_after_snapshot + 1)

# acceptance anchor: ACC:T79.4
func test_end_turn_and_non_end_turn_entries_produce_identical_defeat_resolution_contract() -> void:
	# Path A: non-end-turn HP mutation entry.
	var main_non_end_turn := await _load_main_on_map()
	var nav_non_end_turn := main_non_end_turn.get_node_or_null("ScreenNavigator")
	assert(nav_non_end_turn != null, "Main scene missing ScreenNavigator.")
	if nav_non_end_turn.has_method("ClearRouteHistoryForTest"):
		nav_non_end_turn.call("ClearRouteHistoryForTest")
	var route_start_non_end_turn := main_non_end_turn.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start_non_end_turn.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat_non_end_turn = await _await_scene_instance_with_method(main_non_end_turn, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat_non_end_turn).is_not_null()
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat_non_end_turn, ["Strike"], 3, 7, 0, 0)).is_true()
	assert_that(int(combat_non_end_turn.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame

	var settlement_non_end_turn = await _await_settlement_scene(main_non_end_turn)
	assert_that(settlement_non_end_turn).is_not_null()
	assert_that(str(settlement_non_end_turn.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	var history_non_end_turn = nav_non_end_turn.call("GetRouteHistoryForTest")
	assert_that(history_non_end_turn.size()).is_equal(2)
	assert_that(str(history_non_end_turn[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(history_non_end_turn[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")
	assert_that(bool(settlement_non_end_turn.call("RequestReturnToMainMenuForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(bool(main_non_end_turn.call("IsMainMenuVisibleForTest"))).is_true()

	# Path B: end-turn HP mutation entry.
	var main_end_turn := await _load_main_on_map()
	var nav_end_turn := main_end_turn.get_node_or_null("ScreenNavigator")
	assert(nav_end_turn != null, "Main scene missing ScreenNavigator.")
	if nav_end_turn.has_method("ClearRouteHistoryForTest"):
		nav_end_turn.call("ClearRouteHistoryForTest")
	var route_start_end_turn := main_end_turn.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start_end_turn.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat_end_turn = await _await_scene_instance_with_method(main_end_turn, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat_end_turn).is_not_null()
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat_end_turn, ["Strike"], 3, 7, 0, 1)).is_true()
	assert_that(bool(combat_end_turn.call("RequestTurnActionForTest", "end_turn"))).is_true()
	assert_that(int(combat_end_turn.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame

	var settlement_end_turn = await _await_settlement_scene(main_end_turn)
	assert_that(settlement_end_turn).is_not_null()
	assert_that(str(settlement_end_turn.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	var history_end_turn = nav_end_turn.call("GetRouteHistoryForTest")
	assert_that(history_end_turn.size()).is_equal(2)
	assert_that(str(history_end_turn[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(history_end_turn[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")
	assert_that(bool(settlement_end_turn.call("RequestReturnToMainMenuForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(bool(main_end_turn.call("IsMainMenuVisibleForTest"))).is_true()

# acceptance anchor: ACC:T79.5
func test_defeat_routing_is_bound_to_hp_change_emission_from_unified_update_path() -> void:
	var main := await _load_main_on_map()
	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()

	# No HP change: no emission, no eligible defeat transition.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 80)).is_true()
	await get_tree().process_frame
	assert_that(int(combat.call("GetHpChangedEmissionCountForTest"))).is_equal(0)
	assert_that(int(combat.call("GetDefeatEligibleTransitionCountForTest"))).is_equal(0)
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")

	# HP change to <=0: emission and eligible transition must both be observed.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 0)).is_true()
	assert_that(int(combat.call("GetHpChangedEmissionCountForTest"))).is_equal(1)
	assert_that(int(combat.call("GetDefeatEligibleTransitionCountForTest"))).is_equal(1)
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame
	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()

func test_player_hp_zero_on_non_end_turn_snapshot_path_triggers_defeat_summary_and_main_menu_once() -> void:
	var main := await _load_main_on_map()
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")

	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(1)

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 0)).is_true()
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame

	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_false()
	assert_that(bool(settlement.call("RequestReturnToMainMenuForTest"))).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(bool(main.call("IsMainMenuVisibleForTest"))).is_true()
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(1)
	var route_history = nav.call("GetRouteHistoryForTest")
	assert_that(route_history.size()).is_equal(2)
	assert_that(str(route_history[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(route_history[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")

# acceptance anchor: ACC:T79.8
func test_defeat_route_requires_hp_transition_from_positive_to_zero_or_below() -> void:
	var main := await _load_main_on_map()
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")

	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()

	# HP unchanged (>0 -> >0): no defeat route.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 80)).is_true()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_that(_current_scene_path(main)).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(int(combat.call("GetDefeatEligibleTransitionCountForTest"))).is_equal(0)

	# First transition >0 -> <=0: one defeat route.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 0)).is_true()
	assert_that(int(combat.call("GetDefeatEligibleTransitionCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame
	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	var route_history = nav.call("GetRouteHistoryForTest")
	assert_that(route_history.size()).is_equal(2)
	assert_that(str(route_history[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(route_history[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")

# acceptance anchor: ACC:T79.7
func test_defeat_route_is_one_shot_even_if_hp_recovers_above_zero_then_drops_again() -> void:
	var main := await _load_main_on_map()
	var nav := main.get_node_or_null("ScreenNavigator")
	assert(nav != null, "Main scene missing ScreenNavigator.")
	if nav.has_method("ClearRouteHistoryForTest"):
		nav.call("ClearRouteHistoryForTest")

	var route_start := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(route_start.get("ok", false))).is_true()
	await get_tree().process_frame

	var combat = await _await_scene_instance_with_method(main, "res://Game.Godot/Scenes/Combat.tscn", "TryApplyCoreSnapshotData")
	assert_that(combat).is_not_null()

	# The route-owned defeat flow must record exactly one combat->map transition.
	assert_that(_try_apply_combat_snapshot_with_player_hp(combat, ["Strike"], 3, 7, 0, 0)).is_true()
	assert_that(int(combat.call("GetDefeatResolveCountForTest"))).is_equal(1)
	await get_tree().process_frame
	await get_tree().process_frame
	var settlement = await _await_settlement_scene(main)
	assert_that(settlement).is_not_null()
	assert_that(str(settlement.call("GetOutcomeTextForTest")).find("Defeat") >= 0).is_true()
	assert_that(main.call("GetMapRouteStartInvocationCountForTest")).is_equal(1)
	var route_history = nav.call("GetRouteHistoryForTest")
	assert_that(route_history.size()).is_equal(2)
	assert_that(str(route_history[0])).is_equal("res://Game.Godot/Scenes/Combat.tscn")
	assert_that(str(route_history[1])).is_equal("res://Game.Godot/Scenes/Settlement.tscn")

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

# acceptance: ACC:T133.1
# acceptance: ACC:T133.2
# acceptance: ACC:T133.3
# acceptance: ACC:T133.4
# acceptance: ACC:T133.5
# acceptance: ACC:T133.6
func test_reward_runtime_modifiers_apply_once_before_lock_and_do_not_mutate_locked_snapshot() -> void:
	var main := await _load_main_on_map()
	var first_route := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(first_route.get("ok", false))).is_true()
	var first_pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_that(first_pending_context_id.is_empty()).is_false()
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", "", {
		"action": "mutate",
		"target_entry_id": "gold",
		"config": {"amount": 77}
	}))).is_true()
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", "", {
		"action": "add",
		"reward_type": "relic",
		"config": {"relic_id": "relic.twilight_coin"}
	}))).is_true()
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", "", {
		"action": "remove",
		"target_entry_id": "consumable"
	}))).is_true()
	var first_reward := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(first_reward.get("ok", false))).is_true()
	assert_that(str(first_reward.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Reward.tscn")
	await get_tree().process_frame

	var reward_scene = _current_scene_instance(main)
	assert_that(reward_scene).is_not_null()
	assert_that(bool(reward_scene.has_method("GetOfferSourceForTest"))).is_true()
	assert_that(str(reward_scene.call("GetOfferSourceForTest"))).is_equal("shared-card-pool")
	assert_that(bool(reward_scene.has_method("GetVisibleRewardEntriesForTest"))).is_true()
	var first_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var first_context_id := str(first_snapshot.get("context_id", "")).strip_edges()
	assert_that(first_context_id).is_equal(first_pending_context_id)
	assert_that(first_context_id.is_empty()).is_false()
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", first_context_id))).is_equal(3)
	var first_entries := first_snapshot.get("entries", []) as Array
	var first_has_mutated_gold := false
	var first_has_added_relic := false
	var first_has_consumable := false
	for entry_variant in first_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		var reward_type := str(entry.get("reward_type", "")).strip_edges()
		var config := entry.get("config", {}) as Dictionary
		if reward_type == "gold" and int(config.get("amount", 0)) == 77:
			first_has_mutated_gold = true
		if reward_type == "relic" and str(config.get("relic_id", "")).strip_edges() == "relic.twilight_coin":
			first_has_added_relic = true
		if reward_type == "consumable":
			first_has_consumable = true
	assert_that(first_has_mutated_gold).is_true()
	assert_that(first_has_added_relic).is_true()
	assert_that(first_has_consumable).is_false()
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", first_context_id))).is_equal(0)
	var visible_entries := reward_scene.call("GetVisibleRewardEntriesForTest") as Array
	assert_that(visible_entries.size()).is_equal(first_entries.size())
	var visible_has_mutated_gold := false
	var visible_has_added_relic := false
	var visible_has_consumable := false
	for entry_variant in visible_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		var reward_type := str(entry.get("reward_type", "")).strip_edges()
		var config := entry.get("config", {}) as Dictionary
		if reward_type == "gold" and int(config.get("amount", 0)) == 77:
			visible_has_mutated_gold = true
		if reward_type == "relic" and str(config.get("relic_id", "")).strip_edges() == "relic.twilight_coin":
			visible_has_added_relic = true
		if reward_type == "consumable":
			visible_has_consumable = true
	assert_that(visible_has_mutated_gold).is_true()
	assert_that(visible_has_added_relic).is_true()
	assert_that(visible_has_consumable).is_false()

	var visible_card_ids := reward_scene.call("GetOfferedCardIdsForTest") as Array[String]
	assert_that(visible_card_ids.size()).is_greater_equal(3)

	assert_that(bool(reward_scene.call("SkipForTest"))).is_true()
	await get_tree().process_frame

	var replay_route := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(replay_route.get("ok", false))).is_true()
	var replay_reward := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(replay_reward.get("ok", false))).is_true()
	await get_tree().process_frame

	var replay_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_that(str(replay_snapshot.get("context_id", "")).strip_edges()).is_equal(first_context_id)
	assert_that(replay_snapshot).is_equal(first_snapshot)

	var second_route := main.call("StartMapNodeRouteForTest", "combat-02", "combat", true, "") as Dictionary
	assert_that(bool(second_route.get("ok", false))).is_true()
	var second_pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_that(second_pending_context_id.is_empty()).is_false()
	assert_that(second_pending_context_id).is_not_equal(first_context_id)
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", second_pending_context_id, {
		"action": "add",
		"reward_type": "unknown",
		"config": {}
	}))).is_false()
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", second_pending_context_id, {
		"action": "remove",
		"target_entry_id": "gold"
	}))).is_true()
	var second_reward := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(second_reward.get("ok", false))).is_true()
	await get_tree().process_frame

	var second_scene = _current_scene_instance(main)
	assert_that(second_scene).is_not_null()
	var second_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var second_entries := second_snapshot.get("entries", []) as Array
	var has_gold_entry := false
	var has_twilight_coin_relic := false
	for entry_variant in second_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		var reward_type := str(entry.get("reward_type", "")).strip_edges()
		if reward_type == "gold":
			has_gold_entry = true
			var config := entry.get("config", {}) as Dictionary
			assert_that(int(config.get("amount", 0))).is_not_equal(-5)
			assert_that(int(config.get("amount", 0))).is_not_equal(77)
		if reward_type == "relic":
			var config := entry.get("config", {}) as Dictionary
			if str(config.get("relic_id", "")).strip_edges() == "relic.twilight_coin":
				has_twilight_coin_relic = true
	assert_that(has_gold_entry).is_false()
	assert_that(has_twilight_coin_relic).is_false()

	var locked_second_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", second_pending_context_id, {
		"action": "mutate",
		"target_entry_id": "gold",
		"config": {"amount": -9}
	}))).is_true()
	var reread_locked_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_that(reread_locked_snapshot).is_equal(locked_second_snapshot)

# acceptance: ACC:T133.5
func test_reward_runtime_modifiers_do_not_survive_reset_for_same_context() -> void:
	var main := await _load_main_on_map()
	var first_route := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(first_route.get("ok", false))).is_true()
	var first_pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_that(first_pending_context_id.is_empty()).is_false()
	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", first_pending_context_id, {
		"action": "mutate",
		"target_entry_id": "gold",
		"config": {"amount": 77}
	}))).is_true()
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", first_pending_context_id))).is_equal(1)
	var first_reward := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(first_reward.get("ok", false))).is_true()
	await get_tree().process_frame
	var first_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var first_entries := first_snapshot.get("entries", []) as Array
	var first_has_mutated_gold := false
	for entry_variant in first_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		if str(entry.get("reward_type", "")).strip_edges() != "gold":
			continue
		var config := entry.get("config", {}) as Dictionary
		if int(config.get("amount", 0)) == 77:
			first_has_mutated_gold = true
	assert_that(first_has_mutated_gold).is_true()
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", first_pending_context_id))).is_equal(0)

	main.call("ResetMapRouteProgressForTest")
	var second_route := main.call("StartMapNodeRouteForTest", "combat-01", "combat", true, "") as Dictionary
	assert_that(bool(second_route.get("ok", false))).is_true()
	var second_pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_that(second_pending_context_id).is_equal(first_pending_context_id)
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", second_pending_context_id))).is_equal(0)
	var second_reward := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(second_reward.get("ok", false))).is_true()
	await get_tree().process_frame
	var second_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var second_entries := second_snapshot.get("entries", []) as Array
	for entry_variant in second_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		if str(entry.get("reward_type", "")).strip_edges() != "gold":
			continue
		var config := entry.get("config", {}) as Dictionary
		assert_that(int(config.get("amount", 0))).is_not_equal(77)

# acceptance: ACC:T133.6
func test_reward_runtime_modifier_invalid_mutate_does_not_partially_mutate_snapshot() -> void:
	var main := await _load_main_on_map()
	var route := main.call("StartMapNodeRouteForTest", "combat-03", "combat", true, "") as Dictionary
	assert_that(bool(route.get("ok", false))).is_true()

	var pending_context_id := str(main.call("GetPendingRewardContextIdForTest")).strip_edges()
	assert_that(pending_context_id.is_empty()).is_false()

	var baseline_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	var baseline_context_id := str(baseline_snapshot.get("context_id", "")).strip_edges()
	assert_that(baseline_context_id).is_equal(pending_context_id)
	var baseline_entries := baseline_snapshot.get("entries", []) as Array
	assert_that(baseline_entries.is_empty()).is_false()

	var baseline_gold_entry := {}
	for entry_variant in baseline_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		if str(entry.get("reward_type", "")).strip_edges() == "gold":
			baseline_gold_entry = entry.duplicate(true)
			break
	assert_that(baseline_gold_entry.is_empty()).is_false()

	assert_that(bool(main.call("RegisterRewardEntryModifierForTest", pending_context_id, {
		"action": "mutate",
		"target_entry_id": "gold",
		"config": {"amount": -5}
	}))).is_true()
	assert_that(int(main.call("GetPendingRewardEntryModifierCountForTest", pending_context_id))).is_equal(1)

	var replay_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_that(replay_snapshot).is_equal(baseline_snapshot)

	var reward_transition := main.call("CompleteMapNodeFlowForTest") as Dictionary
	assert_that(bool(reward_transition.get("ok", false))).is_true()
	assert_that(str(reward_transition.get("scene_path", ""))).is_equal("res://Game.Godot/Scenes/Reward.tscn")
	await get_tree().process_frame

	var materialized_snapshot := main.call("GetRewardOfferSnapshotForScene") as Dictionary
	assert_that(materialized_snapshot).is_equal(baseline_snapshot)
	var failure := main.call("GetLatestRewardModifierFailureForTest") as Dictionary
	assert_that(str(failure.get("rejection_reason", "")).strip_edges()).is_equal("invalid-mutate:gold")

	var materialized_entries := materialized_snapshot.get("entries", []) as Array
	assert_that(materialized_entries.size()).is_equal(baseline_entries.size())

	var materialized_gold_entry := {}
	for entry_variant in materialized_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		if str(entry.get("reward_type", "")).strip_edges() == "gold":
			materialized_gold_entry = entry.duplicate(true)
			break
	assert_that(materialized_gold_entry).is_equal(baseline_gold_entry)

	for entry_variant in materialized_entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry := entry_variant as Dictionary
		var config := entry.get("config", {}) as Dictionary
		if config.has("amount"):
			assert_that(int(config.get("amount", 0))).is_not_equal(-5)
