extends Control

const TITLE_KEY := "ui.reward.title"
const CARD1_KEY := "ui.reward.card.1.name"
const CARD2_KEY := "ui.reward.card.2.name"
const CARD3_KEY := "ui.reward.card.3.name"
const CONFIRM_KEY := "ui.reward.confirm"
const SKIP_KEY := "ui.reward.skip"
const FEEDBACK_DEFAULT_KEY := "ui.reward.feedback.select_default"
const FEEDBACK_SELECTED_KEY := "ui.reward.feedback.selected"
const FEEDBACK_SELECT_FIRST_KEY := "ui.reward.feedback.select_first"
const FEEDBACK_CONFIRMED_KEY := "ui.reward.feedback.confirmed"
const FEEDBACK_SKIPPED_KEY := "ui.reward.feedback.skipped"
const FEEDBACK_LOCKED_KEY := "reward.locked"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"

@onready var _title_label: Label = $VBox/Title
@onready var _card1_label: Label = $VBox/CardList/Card1
@onready var _card2_label: Label = $VBox/CardList/Card2
@onready var _card3_label: Label = $VBox/CardList/Card3
@onready var _card_list: VBoxContainer = $VBox/CardList
@onready var _confirm_button: Button = $VBox/Actions/ConfirmButton
@onready var _skip_button: Button = $VBox/Actions/SkipButton
@onready var _feedback_label: Label = $VBox/Feedback

var _selected_index: int = -1
var _translations_by_locale := {}

func _ready() -> void:
	_confirm_button.pressed.connect(_on_confirm_pressed)
	_skip_button.pressed.connect(_on_skip_pressed)
	RefreshLocaleForTest()
	_feedback_label.text = _resolve_text(FEEDBACK_DEFAULT_KEY)

func SetLocaleForTest(locale: String) -> void:
	if locale.strip_edges().is_empty():
		return
	TranslationServer.set_locale(locale)
	RefreshLocaleForTest()

func RefreshLocaleForTest() -> void:
	_title_label.text = _resolve_text(TITLE_KEY)
	_card1_label.text = _resolve_text(CARD1_KEY)
	_card2_label.text = _resolve_text(CARD2_KEY)
	_card3_label.text = _resolve_text(CARD3_KEY)
	_confirm_button.text = _resolve_text(CONFIRM_KEY)
	_skip_button.text = _resolve_text(SKIP_KEY)

func SelectChoiceForTest(index: int) -> bool:
	if index < 0 or index >= _card_list.get_child_count():
		return false
	_selected_index = index
	_feedback_label.text = _resolve_text(FEEDBACK_SELECTED_KEY).replace("{0}", str(index + 1))
	return true

func ConfirmSelectedForTest() -> bool:
	if _selected_index < 0:
		_feedback_label.text = _resolve_text(FEEDBACK_SELECT_FIRST_KEY)
		return false
	_feedback_label.text = _resolve_text(FEEDBACK_CONFIRMED_KEY)
	return true

func SkipForTest() -> bool:
	_feedback_label.text = _resolve_text(FEEDBACK_SKIPPED_KEY)
	return true

func ShowLockedFeedbackForTest() -> bool:
	_feedback_label.text = _resolve_text(FEEDBACK_LOCKED_KEY)
	return true

func GetFeedbackForTest() -> String:
	return _feedback_label.text

func GetCardCountForTest() -> int:
	return _card_list.get_child_count()

func _on_confirm_pressed() -> void:
	ConfirmSelectedForTest()

func _on_skip_pressed() -> void:
	SkipForTest()

func _resolve_text(key: String) -> String:
	if key.strip_edges().is_empty():
		return ""
	var localized := TranslationServer.translate(key)
	if localized != key:
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
