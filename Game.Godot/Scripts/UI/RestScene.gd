extends Control

const TITLE_KEY := "ui.rest.title"
const DESCRIPTION_KEY := "ui.rest.description"
const OPTION_HEAL_KEY := "ui.rest.option.heal"
const OPTION_UPGRADE_KEY := "ui.rest.option.upgrade"
const OPTION_REMOVE_CURSE_KEY := "ui.rest.option.remove_curse"
const FEEDBACK_UPGRADE_PENDING_KEY := "ui.rest.feedback.upgrade_pending"
const FEEDBACK_UPGRADE_CONFIRMED_KEY := "ui.rest.feedback.upgrade_confirmed"
const FEEDBACK_UPGRADE_CANCELLED_KEY := "ui.rest.feedback.upgrade_cancelled"
const FEEDBACK_HEAL_RESOLVED_KEY := "ui.rest.feedback.heal_resolved"
const FEEDBACK_REMOVE_CURSE_RESOLVED_KEY := "ui.rest.feedback.remove_curse_resolved"
const FEEDBACK_MISSING_TARGET_KEY := "ui.rest.feedback.missing_target"
const FEEDBACK_RETURN_ROUTE_KEY := "ui.rest.feedback.return_route"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"

@onready var _vbox: VBoxContainer = $VBox
@onready var _title_label: Label = $VBox/Title
@onready var _description_label: Label = $VBox/Description

var _selected_option: String = ""
var _next_route: String = ""
var _upgrade_confirm_pending: bool = false
var _upgrade_confirmed: bool = false
var _upgrade_target_mutated: bool = false
var _curse_removed: bool = false
var _feedback: String = ""
var _translations_by_locale := {}

func _ready() -> void:
	_ensure_option_button(OPTION_HEAL_KEY, "heal")
	_ensure_option_button(OPTION_UPGRADE_KEY, "upgrade")
	_ensure_option_button(OPTION_REMOVE_CURSE_KEY, "remove_curse")
	RefreshLocaleForTest()

func SetLocaleForTest(locale: String) -> void:
	if locale.strip_edges().is_empty():
		return
	TranslationServer.set_locale(locale)
	RefreshLocaleForTest()

func RefreshLocaleForTest() -> void:
	_title_label.text = _resolve_text(TITLE_KEY)
	_description_label.text = _resolve_text(DESCRIPTION_KEY)
	_ensure_option_button(OPTION_HEAL_KEY, "heal")
	_ensure_option_button(OPTION_UPGRADE_KEY, "upgrade")
	_ensure_option_button(OPTION_REMOVE_CURSE_KEY, "remove_curse")

func _ensure_option_button(text_key: String, option_id: String) -> void:
	var button_name := "Option_" + option_id
	var existing := _vbox.get_node_or_null(button_name)
	if existing != null and existing is Button:
		(existing as Button).text = _resolve_text(text_key)
		return
	var button := Button.new()
	button.name = button_name
	button.text = _resolve_text(text_key)
	button.pressed.connect(func() -> void: _on_option_pressed(option_id))
	_vbox.add_child(button)

func _on_option_pressed(option_id: String) -> void:
	_selected_option = option_id
	_curse_removed = false
	if option_id == "upgrade":
		_upgrade_confirm_pending = true
		_feedback = _resolve_text(FEEDBACK_UPGRADE_PENDING_KEY)
		return

	if option_id == "remove_curse":
		_curse_removed = true
		_feedback = _resolve_text(FEEDBACK_REMOVE_CURSE_RESOLVED_KEY)
	else:
		_feedback = _resolve_text(FEEDBACK_HEAL_RESOLVED_KEY)
	_upgrade_confirm_pending = false
	_next_route = "map"

func SelectOptionForTest(option_id: String) -> bool:
	var normalized := option_id.strip_edges().to_lower()
	if normalized != "heal" and normalized != "upgrade" and normalized != "remove_curse":
		return false
	_on_option_pressed(normalized)
	return true

func ConfirmUpgradeForTest() -> bool:
	if not _upgrade_confirm_pending:
		return false
	_upgrade_confirm_pending = false
	_upgrade_confirmed = true
	_upgrade_target_mutated = true
	_feedback = _resolve_text(FEEDBACK_UPGRADE_CONFIRMED_KEY)
	_next_route = "map"
	return true

func CancelUpgradeForTest() -> bool:
	if not _upgrade_confirm_pending:
		return false
	_upgrade_confirm_pending = false
	_selected_option = ""
	_upgrade_target_mutated = false
	_feedback = _resolve_text(FEEDBACK_UPGRADE_CANCELLED_KEY)
	return true

func RequestUndoAfterConfirmForTest() -> bool:
	if not _upgrade_confirmed:
		return false
	_feedback = _resolve_text("rest.irreversible_upgrade")
	return false

func RequestRestorePreUpgradeSnapshotForTest() -> bool:
	if not _upgrade_confirmed:
		return false
	_feedback = _resolve_text("rest.irreversible_upgrade")
	return false

func ShowMissingTargetFeedbackForTest() -> bool:
	_feedback = _resolve_text(FEEDBACK_MISSING_TARGET_KEY)
	return true

func ShowReturnRouteFeedbackForTest() -> bool:
	_next_route = "map"
	_feedback = _resolve_text(FEEDBACK_RETURN_ROUTE_KEY)
	return true

func GetAvailableOptionsForTest() -> Array[String]:
	return ["heal", "upgrade", "remove_curse"]

func GetNextRouteForTest() -> String:
	return _next_route

func IsUpgradeConfirmPendingForTest() -> bool:
	return _upgrade_confirm_pending

func IsUpgradeConfirmedForTest() -> bool:
	return _upgrade_confirmed

func WasUpgradeTargetMutatedForTest() -> bool:
	return _upgrade_target_mutated

func WasCurseRemovedForTest() -> bool:
	return _curse_removed

func GetFeedbackForTest() -> String:
	return _feedback

func _resolve_text(key: String) -> String:
	if key.strip_edges().is_empty():
		return ""
	var localized := TranslationServer.translate(key)
	if localized != key and _is_readable_visible_text(localized):
		return localized
	var locale := _normalize_locale(TranslationServer.get_locale())
	var primary := _load_translation_values(_translation_file_for_locale(locale))
	if primary.has(key):
		return str(primary[key]).strip_edges()
	if locale != "en":
		var fallback := _load_translation_values(EN_TRANSLATIONS_FILE)
		if fallback.has(key):
			return str(fallback[key]).strip_edges()
	return key

func _is_readable_visible_text(value: String) -> bool:
	return not value.strip_edges().is_empty() and not value.contains("??") and not value.contains("\uFFFD")

func _translation_file_for_locale(locale: String) -> String:
	if locale.begins_with("zh"):
		return ZH_TRANSLATIONS_FILE
	return EN_TRANSLATIONS_FILE

func _normalize_locale(locale: String) -> String:
	if locale.strip_edges().is_empty():
		return "en"
	return locale.strip_edges().replace("_", "-").to_lower()

func _load_translation_values(csv_path: String) -> Dictionary:
	if _translations_by_locale.has(csv_path):
		return _translations_by_locale[csv_path]
	var values := {}
	var absolute_path := ProjectSettings.globalize_path(csv_path)
	if not FileAccess.file_exists(absolute_path):
		_translations_by_locale[csv_path] = values
		return values
	var file := FileAccess.open(absolute_path, FileAccess.READ)
	if file == null:
		_translations_by_locale[csv_path] = values
		return values
	var raw := file.get_as_text()
	file.close()
	for line in raw.split("\n", false):
		var trimmed := line.strip_edges()
		if trimmed == "" or trimmed.begins_with("key,value"):
			continue
		var comma := trimmed.find(",")
		if comma <= 0:
			continue
		var entry_key := trimmed.substr(0, comma).strip_edges()
		var entry_value := trimmed.substr(comma + 1).strip_edges()
		if entry_key != "" and entry_value != "":
			values[entry_key] = entry_value
	_translations_by_locale[csv_path] = values
	return values
