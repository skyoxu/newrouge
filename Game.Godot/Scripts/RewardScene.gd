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
const FEEDBACK_MISSING_CONTENT_KEY := "ui.fallback.missing_content"
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
var _is_confirmed: bool = false
var _is_skipped: bool = false
var _translations_by_locale := {}
var _offer_snapshot: Dictionary = {}
var _offered_cards: Array = []
var _offer_snapshot_valid: bool = true
var _card_labels: Array[Label] = []

func _ready() -> void:
	_confirm_button.pressed.connect(_on_confirm_pressed)
	_skip_button.pressed.connect(_on_skip_pressed)
	_card_labels = [_card1_label, _card2_label, _card3_label]
	_load_offer_snapshot_from_main()
	_refresh_offer_snapshot_validity()
	RefreshLocaleForTest()
	_reset_resolution_state()
	_feedback_label.text = _resolve_text(FEEDBACK_DEFAULT_KEY) if _offer_snapshot_valid else _resolve_text(FEEDBACK_MISSING_CONTENT_KEY)

func SetLocaleForTest(locale: String) -> void:
	if locale.strip_edges().is_empty():
		return
	TranslationServer.set_locale(locale)
	RefreshLocaleForTest()

func RefreshLocaleForTest() -> void:
	_title_label.text = _resolve_text(TITLE_KEY)
	_confirm_button.text = _resolve_text(CONFIRM_KEY)
	_skip_button.text = _resolve_text(SKIP_KEY)
	_refresh_offer_labels()

func SelectChoiceForTest(index: int) -> bool:
	if not _offer_snapshot_valid:
		_feedback_label.text = _resolve_text(FEEDBACK_MISSING_CONTENT_KEY)
		return false
	if _is_resolution_locked():
		_feedback_label.text = _resolve_text(FEEDBACK_LOCKED_KEY)
		return false
	if index < 0 or index >= _card_list.get_child_count():
		return false
	_selected_index = index
	_feedback_label.text = _resolve_text(FEEDBACK_SELECTED_KEY).replace("{0}", str(index + 1))
	return true

func CanConfirmSelectedForTest(index: int) -> bool:
	if not _offer_snapshot_valid:
		return false
	if _is_resolution_locked():
		return false
	return _selected_index == index and index >= 0

func ConfirmSelectedForTest() -> bool:
	if not _offer_snapshot_valid:
		_feedback_label.text = _resolve_text(FEEDBACK_MISSING_CONTENT_KEY)
		return false
	if _is_resolution_locked():
		_feedback_label.text = _resolve_text(FEEDBACK_LOCKED_KEY)
		return false
	if _selected_index < 0:
		_feedback_label.text = _resolve_text(FEEDBACK_SELECT_FIRST_KEY)
		return false
	_is_confirmed = true
	_feedback_label.text = _resolve_text(FEEDBACK_CONFIRMED_KEY)
	_resolve_route_and_return("confirm")
	return true

func SkipForTest() -> bool:
	if not _offer_snapshot_valid:
		_feedback_label.text = _resolve_text(FEEDBACK_MISSING_CONTENT_KEY)
		return false
	if _is_resolution_locked():
		_feedback_label.text = _resolve_text(FEEDBACK_LOCKED_KEY)
		return false
	_is_skipped = true
	_feedback_label.text = _resolve_text(FEEDBACK_SKIPPED_KEY)
	_resolve_route_and_return("skip")
	return true

func GetSelectedIndexForTest() -> int:
	return _selected_index

func IsLockedForTest() -> bool:
	return _is_resolution_locked()

func ShowLockedFeedbackForTest() -> bool:
	_feedback_label.text = _resolve_text(FEEDBACK_LOCKED_KEY)
	return true

func GetFeedbackForTest() -> String:
	return _feedback_label.text

func GetCardCountForTest() -> int:
	return _offered_cards.size() if _offer_snapshot_valid else 0

func GetVisibleCardSlotCountForTest() -> int:
	var count := 0
	for label in _card_labels:
		if is_instance_valid(label) and label.visible:
			count += 1
	return count

func GetOfferSourceForTest() -> String:
	return str(_offer_snapshot.get("source", ""))

func GetOfferedCardIdsForTest() -> Array[String]:
	var ids: Array[String] = []
	for card_data in _offered_cards:
		if typeof(card_data) != TYPE_DICTIONARY:
			continue
		var card := card_data as Dictionary
		var card_id := str(card.get("id", ""))
		if card_id.is_empty():
			card_id = str(card.get("name", ""))
		if not card_id.is_empty():
			ids.append(card_id)
	return ids

func _on_confirm_pressed() -> void:
	ConfirmSelectedForTest()

func _on_skip_pressed() -> void:
	SkipForTest()

func _resolve_route_and_return(action: String) -> void:
	var main = _resolve_main_controller()
	if main != null and main.has_method("ResolveRewardForTest"):
		var payload := {
			"action": action,
			"selected_index": _selected_index,
			"selected_card_id": _resolve_selected_card_id()
		}
		main.call("ResolveRewardForTest", payload)

func _resolve_main_controller() -> Node:
	var current: Node = self
	while current != null:
		if current.has_method("ResolveRewardForTest"):
			return current
		current = current.get_parent()
	return get_node_or_null("/root/Main")

func _load_offer_snapshot_from_main() -> void:
	_offer_snapshot.clear()
	_offered_cards.clear()
	var main = _resolve_main_controller()
	if main == null or not main.has_method("GetRewardOfferSnapshotForScene"):
		return
	var snapshot_variant = main.call("GetRewardOfferSnapshotForScene")
	if typeof(snapshot_variant) != TYPE_DICTIONARY:
		return
	_offer_snapshot = (snapshot_variant as Dictionary).duplicate(true)
	var offers_variant = _offer_snapshot.get("offers", [])
	if typeof(offers_variant) != TYPE_ARRAY:
		return
	for item in (offers_variant as Array):
		if typeof(item) == TYPE_DICTIONARY:
			_offered_cards.append((item as Dictionary).duplicate(true))

func _refresh_offer_snapshot_validity() -> void:
	_offer_snapshot_valid = _offered_cards.size() >= 3

func _reset_resolution_state() -> void:
	_selected_index = -1
	_is_confirmed = false
	_is_skipped = false

func _is_resolution_locked() -> bool:
	return _is_confirmed or _is_skipped

func _resolve_offer_label_text(index: int, fallback_key: String) -> String:
	if index < 0 or index >= _offered_cards.size():
		return _resolve_text(fallback_key)
	var card_data = _offered_cards[index]
	if typeof(card_data) != TYPE_DICTIONARY:
		return _resolve_text(fallback_key)
	var card := card_data as Dictionary
	var name_key := str(card.get("name_key", "")).strip_edges()
	if not name_key.is_empty():
		return _resolve_text(name_key)
	var name := str(card.get("name", "")).strip_edges()
	if name.is_empty():
		name = str(card.get("id", "")).strip_edges()
	if name.is_empty():
		return _resolve_text(fallback_key)
	if name.begins_with("card.") and name.ends_with(".name"):
		return _resolve_text(name)
	return name

func _refresh_offer_labels() -> void:
	if not _offer_snapshot_valid:
		for label in _card_labels:
			if is_instance_valid(label):
				label.visible = false
		return
	for label in _card_labels:
		if is_instance_valid(label):
			label.visible = true
	_card1_label.text = _resolve_offer_label_text(0, CARD1_KEY)
	_card2_label.text = _resolve_offer_label_text(1, CARD2_KEY)
	_card3_label.text = _resolve_offer_label_text(2, CARD3_KEY)

func _resolve_selected_card_id() -> String:
	if _selected_index < 0 or _selected_index >= _offered_cards.size():
		return ""
	var card_data = _offered_cards[_selected_index]
	if typeof(card_data) != TYPE_DICTIONARY:
		return ""
	var card := card_data as Dictionary
	var card_id := str(card.get("id", "")).strip_edges()
	if card_id.is_empty():
		card_id = str(card.get("name", "")).strip_edges()
	return card_id

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
