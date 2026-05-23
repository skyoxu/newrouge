extends Control

const CARD_FALLBACK_TEXTURE := "res://Game.Godot/Assets/Textures/Cards/card_reward_defend.png"
const FEEDBACK_SELECT_DEFAULT_KEY := "ui.reward.feedback.select_default"
const FEEDBACK_SELECTED_KEY := "ui.reward.feedback.selected"
const FEEDBACK_SELECT_FIRST_KEY := "ui.reward.feedback.select_first"
const FEEDBACK_CONFIRMED_KEY := "ui.reward.feedback.confirmed"
const FEEDBACK_SKIPPED_KEY := "ui.reward.feedback.skipped"
const LEGACY_CARD_NAME_KEYS := [
	"ui.reward.card.1.name",
	"ui.reward.card.2.name",
	"ui.reward.card.3.name"
]

@onready var _legacy_title_label: Label = $VBox/Title
@onready var _legacy_feedback_label: Label = $VBox/Feedback
@onready var _legacy_confirm_button: Button = $VBox/Actions/ConfirmButton
@onready var _legacy_skip_button: Button = $VBox/Actions/SkipButton
@onready var _legacy_card_slots: Array[Control] = [
	$VBox/CardList/CardSlot1,
	$VBox/CardList/CardSlot2,
	$VBox/CardList/CardSlot3
]
@onready var _title_label: Label = $RootMargin/VBox/Title
@onready var _reward_list: VBoxContainer = $RootMargin/VBox/RewardListScroll/RewardList
@onready var _feedback_label: Label = $RootMargin/VBox/Feedback
@onready var _skip_all_button: Button = $RootMargin/VBox/RewardActions/SkipAllButton
@onready var _card_choice_overlay: Control = $CardChoiceOverlay
@onready var _card_choice_title: Label = $CardChoiceOverlay/Shell/ChoiceVBox/ChoiceTitle
@onready var _card_choice_grid: GridContainer = $CardChoiceOverlay/Shell/ChoiceVBox/ChoiceScroll/ChoiceGrid
@onready var _card_choice_back_button: Button = $CardChoiceOverlay/Shell/ChoiceVBox/ChoiceActions/BackButton
@onready var _card_choice_skip_button: Button = $CardChoiceOverlay/Shell/ChoiceVBox/ChoiceActions/SkipButton

var _offer_snapshot: Dictionary = {}
var _entries: Array = []
var _legacy_offer_cards: Array = []
var _active_card_choice_entry: Dictionary = {}
var _selected_index: int = -1
var _is_locked: bool = false
var _feedback_text: String = ""

func _text(key: String, fallback: String = "") -> String:
	var translated := TranslationServer.translate(key)
	if translated != key and not str(translated).strip_edges().is_empty():
		return str(translated).strip_edges()
	var locale := str(TranslationServer.get_locale()).strip_edges().to_lower()
	var csv_path := "res://Game.Godot/Translations/zh-CN.csv" if locale.begins_with("zh") else "res://Game.Godot/Translations/en.csv"
	var absolute_path := ProjectSettings.globalize_path(csv_path)
	if FileAccess.file_exists(absolute_path):
		var file := FileAccess.open(absolute_path, FileAccess.READ)
		if file != null:
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
				if entry_key == key:
					return trimmed.substr(comma + 1).strip_edges()
	if not fallback.is_empty():
		return fallback
	return key

func _ready() -> void:
	_load_offer_snapshot_from_main()
	_card_choice_back_button.pressed.connect(_on_card_choice_back_pressed)
	_card_choice_skip_button.pressed.connect(_on_card_choice_skip_pressed)
	_skip_all_button.pressed.connect(_on_skip_all_pressed)
	_legacy_confirm_button.pressed.connect(_on_legacy_confirm_pressed)
	_legacy_skip_button.pressed.connect(_on_legacy_skip_pressed)
	for index in range(_legacy_card_slots.size()):
		var art_button = _legacy_card_slots[index].get_node("Body/ArtButton") as TextureButton
		art_button.pressed.connect(Callable(self, "_on_legacy_art_pressed").bind(index))
	_rebuild_all_views()

func _resolve_main_controller() -> Node:
	var current: Node = self
	while current != null:
		if current.has_method("ResolveRewardForTest"):
			return current
		current = current.get_parent()
	return get_node_or_null("/root/Main")

func _load_offer_snapshot_from_main() -> void:
	_offer_snapshot.clear()
	_entries.clear()
	_legacy_offer_cards.clear()
	var main = _resolve_main_controller()
	if main == null or not main.has_method("GetRewardOfferSnapshotForScene"):
		return
	var snapshot_variant = main.call("GetRewardOfferSnapshotForScene")
	if typeof(snapshot_variant) != TYPE_DICTIONARY:
		return
	_offer_snapshot = (snapshot_variant as Dictionary).duplicate(true)
	var entries_variant = _offer_snapshot.get("entries", [])
	if typeof(entries_variant) == TYPE_ARRAY:
		for item in (entries_variant as Array):
			if typeof(item) == TYPE_DICTIONARY:
				_entries.append((item as Dictionary).duplicate(true))
	var offers_variant = _offer_snapshot.get("offers", [])
	if typeof(offers_variant) == TYPE_ARRAY:
		for item in (offers_variant as Array):
			if typeof(item) == TYPE_DICTIONARY:
				_legacy_offer_cards.append((item as Dictionary).duplicate(true))

func _rebuild_all_views() -> void:
	_filter_resolved_entries()
	_refresh_feedback_labels()
	_rebuild_reward_list()
	_sync_legacy_card_surface()
	_refresh_legacy_action_state()

func _rebuild_reward_list() -> void:
	for child in _reward_list.get_children():
		_reward_list.remove_child(child)
		child.queue_free()
	for entry_variant in _entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = entry_variant as Dictionary
		_reward_list.add_child(_build_reward_row(entry))
	_feedback_label.text = _feedback_text

func _build_reward_row(entry: Dictionary) -> Control:
	var row: HBoxContainer = HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.custom_minimum_size = Vector2(0, 88)

	var icon: TextureRect = TextureRect.new()
	icon.custom_minimum_size = Vector2(72, 72)
	icon.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.texture = _load_texture_from_file(str(entry.get("icon_path", CARD_FALLBACK_TEXTURE)))
	row.add_child(icon)

	var name_button: Button = Button.new()
	name_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	name_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_button.text = str(entry.get("title", "")).strip_edges()
	name_button.tooltip_text = str(entry.get("tooltip", "")).strip_edges()
	name_button.disabled = _is_locked
	name_button.pressed.connect(func() -> void: _on_reward_entry_pressed(entry))
	row.add_child(name_button)

	var tip: Label = Label.new()
	tip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tip.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tip.text = str(entry.get("tooltip", "")).strip_edges()
	row.add_child(tip)

	return row

func _on_reward_entry_pressed(entry: Dictionary) -> void:
	if _is_locked:
		return
	var reward_type: String = str(entry.get("reward_type", "")).strip_edges()
	if reward_type.ends_with("_card_choice"):
		_open_card_choice_overlay(entry)
		return
	_claim_reward(reward_type, "", -1)

func _open_card_choice_overlay(entry: Dictionary) -> void:
	_active_card_choice_entry = entry.duplicate(true)
	_card_choice_overlay.visible = true
	_card_choice_title.text = str(entry.get("title", "Choose Reward")).strip_edges()
	for child in _card_choice_grid.get_children():
		_card_choice_grid.remove_child(child)
		child.queue_free()
	var cards_variant = entry.get("cards", [])
	if typeof(cards_variant) != TYPE_ARRAY:
		return
	for item in (cards_variant as Array):
		if typeof(item) != TYPE_DICTIONARY:
			continue
		_card_choice_grid.add_child(_build_card_choice_button(item as Dictionary))

func _build_card_choice_button(card: Dictionary) -> Control:
	var button: Button = Button.new()
	button.custom_minimum_size = Vector2(260, 360)
	button.text = "%s\n%s" % [
		str(card.get("display_name", card.get("name", ""))).strip_edges(),
		str(card.get("display_description", card.get("description", ""))).strip_edges()
	]
	button.tooltip_text = button.text
	button.disabled = _is_locked
	button.pressed.connect(func() -> void:
		var reward_type: String = str(_active_card_choice_entry.get("reward_type", "")).strip_edges()
		_claim_reward(reward_type, str(card.get("id", "")).strip_edges(), int(card.get("offer_index", -1)) - 1)
	)
	return button

func _claim_reward(reward_type: String, selected_card_id: String, selected_index: int) -> void:
	var main = _resolve_main_controller()
	if main == null or not main.has_method("ResolveRewardForTest"):
		return
	var result_variant = main.call("ResolveRewardForTest", {
		"action": "confirm",
		"selected_reward_type": reward_type,
		"selected_card_id": selected_card_id,
		"selected_index": selected_index
	})
	var result: Dictionary = result_variant as Dictionary if typeof(result_variant) == TYPE_DICTIONARY else {}
	var still_on_reward: bool = str(result.get("scene_path", "")).strip_edges() == "res://Game.Godot/Scenes/Reward.tscn"
	_is_locked = not still_on_reward
	_feedback_text = _text(FEEDBACK_CONFIRMED_KEY, "Reward confirmed.")
	_card_choice_overlay.visible = false
	_active_card_choice_entry.clear()
	_selected_index = -1
	_reload_and_refresh()

func _on_card_choice_back_pressed() -> void:
	_card_choice_overlay.visible = false
	_active_card_choice_entry.clear()

func _on_card_choice_skip_pressed() -> void:
	if _is_locked:
		return
	var reward_type: String = str(_active_card_choice_entry.get("reward_type", "")).strip_edges()
	var main = _resolve_main_controller()
	if main != null and main.has_method("ResolveRewardForTest"):
		var result_variant = main.call("ResolveRewardForTest", {
			"action": "skip",
			"skip_reward_type": reward_type
		})
		var result: Dictionary = result_variant as Dictionary if typeof(result_variant) == TYPE_DICTIONARY else {}
		var still_on_reward: bool = str(result.get("scene_path", "")).strip_edges() == "res://Game.Godot/Scenes/Reward.tscn"
		_is_locked = not still_on_reward
	_feedback_text = _text(FEEDBACK_SKIPPED_KEY, "Reward skipped.")
	_card_choice_overlay.visible = false
	_active_card_choice_entry.clear()
	_selected_index = -1
	_reload_and_refresh()

func _on_skip_all_pressed() -> void:
	if _is_locked:
		return
	var main = _resolve_main_controller()
	if main == null or not main.has_method("SkipRemainingRewardsForTest"):
		return
	var result_variant = main.call("SkipRemainingRewardsForTest")
	var result: Dictionary = result_variant as Dictionary if typeof(result_variant) == TYPE_DICTIONARY else {}
	var still_on_reward: bool = str(result.get("scene_path", "")).strip_edges() == "res://Game.Godot/Scenes/Reward.tscn"
	_is_locked = not still_on_reward
	_feedback_text = _text(FEEDBACK_SKIPPED_KEY, "Reward skipped.")
	_card_choice_overlay.visible = false
	_active_card_choice_entry.clear()
	_selected_index = -1
	_reload_and_refresh()

func _reload_and_refresh() -> void:
	_load_offer_snapshot_from_main()
	_rebuild_all_views()

func _filter_resolved_entries() -> void:
	var main = _resolve_main_controller()
	if main == null:
		return
	var context_id: String = str(_offer_snapshot.get("context_id", "")).strip_edges()
	if context_id.is_empty():
		return
	var state = main.get("_reward_selection_state_by_context")
	if typeof(state) != TYPE_DICTIONARY:
		return
	var state_by_context: Dictionary = state as Dictionary
	if not state_by_context.has(context_id):
		return
	var selection_state = state_by_context[context_id]
	if typeof(selection_state) != TYPE_DICTIONARY:
		return
	var resolved_types: Dictionary = {}
	for key in ["claimed_reward_types", "skipped_reward_types"]:
		var value = (selection_state as Dictionary).get(key, [])
		if typeof(value) != TYPE_ARRAY:
			continue
		for reward_type in (value as Array):
			resolved_types[str(reward_type).strip_edges()] = true
	var filtered: Array = []
	for entry_variant in _entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var reward_type: String = str((entry_variant as Dictionary).get("reward_type", "")).strip_edges()
		if resolved_types.has(reward_type):
			continue
		filtered.append((entry_variant as Dictionary).duplicate(true))
	_entries = filtered

func _load_texture_from_file(resource_path: String) -> Texture2D:
	if resource_path.strip_edges().is_empty():
		return null
	var absolute_path: String = ProjectSettings.globalize_path(resource_path)
	if not FileAccess.file_exists(absolute_path):
		return null
	var image: Image = Image.new()
	if image.load(absolute_path) != OK:
		return null
	return ImageTexture.create_from_image(image)

func _sync_legacy_card_surface() -> void:
	var visible_cards: Array = _visible_legacy_cards()
	for index in range(_legacy_card_slots.size()):
		var slot = _legacy_card_slots[index]
		var slot_is_visible: bool = index < visible_cards.size()
		slot.visible = slot_is_visible
		if not slot_is_visible:
			continue
		var card: Dictionary = visible_cards[index] as Dictionary
		var name_label = slot.get_node("Body/Name") as Label
		var description_label = slot.get_node("Body/Description") as Label
		var art_button = slot.get_node("Body/ArtButton") as TextureButton
		name_label.text = str(card.get("display_name", card.get("name", tr(LEGACY_CARD_NAME_KEYS[index])))).strip_edges()
		description_label.text = str(card.get("display_description", card.get("description", ""))).strip_edges()
		var texture: Texture2D = _load_texture_from_file(str(card.get("art_path", CARD_FALLBACK_TEXTURE)))
		art_button.texture_normal = texture
		art_button.texture_pressed = texture
		art_button.texture_hover = texture

func _on_legacy_art_pressed(index: int) -> void:
	SelectChoiceForTest(index)

func _refresh_legacy_action_state() -> void:
	_legacy_title_label.text = _text("ui.reward.title", "Reward")
	_title_label.text = _text("ui.reward.title", "Reward")
	_legacy_feedback_label.text = _feedback_text if not _feedback_text.is_empty() else _text(FEEDBACK_SELECT_DEFAULT_KEY, "Select a reward.")
	_legacy_confirm_button.text = _text("ui.reward.confirm", "Confirm")
	_legacy_skip_button.text = _text("ui.reward.skip", "Skip")
	_skip_all_button.text = _text("ui.reward.skip_all", "Skip Remaining Rewards")
	_skip_all_button.disabled = _is_locked or _entries.is_empty()
	_card_choice_back_button.text = _text("ui.menu.cancel", "Back")
	_card_choice_skip_button.text = _text("ui.reward.skip", "Pass Reward")
	_legacy_confirm_button.disabled = _is_locked or _selected_index < 0 or _legacy_offer_cards.is_empty()
	_legacy_skip_button.disabled = _is_locked or _legacy_offer_cards.is_empty()
	for index in range(_legacy_card_slots.size()):
		var slot = _legacy_card_slots[index]
		var art_button = slot.get_node("Body/ArtButton") as TextureButton
		art_button.disabled = _is_locked or not slot.visible

func _refresh_feedback_labels() -> void:
	if _feedback_text.is_empty():
		_feedback_text = _text(FEEDBACK_SELECT_DEFAULT_KEY, "Select a reward.")
	_feedback_label.text = _feedback_text
	_legacy_feedback_label.text = _feedback_text

func _on_legacy_confirm_pressed() -> void:
	ConfirmSelectedForTest()

func _on_legacy_skip_pressed() -> void:
	SkipForTest()

func _first_card_choice_entry() -> Dictionary:
	var fallback: Dictionary = {}
	for entry_variant in _entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = entry_variant as Dictionary
		var reward_type: String = str(entry.get("reward_type", "")).strip_edges()
		if not reward_type.ends_with("_card_choice"):
			continue
		var cards_variant = entry.get("cards", [])
		if typeof(cards_variant) == TYPE_ARRAY and (cards_variant as Array).size() >= 3:
			return entry.duplicate(true)
		if fallback.is_empty():
			fallback = entry.duplicate(true)
	return fallback

func _visible_legacy_cards() -> Array:
	var entry: Dictionary = _first_card_choice_entry()
	if entry.is_empty():
		return []
	var cards_variant = entry.get("cards", [])
	if typeof(cards_variant) != TYPE_ARRAY:
		return []
	return (cards_variant as Array).duplicate(true)

func GetOfferSourceForTest() -> String:
	return str(_offer_snapshot.get("source", "")).strip_edges()

func GetOfferedCardIdsForTest() -> Array[String]:
	var ids: Array[String] = []
	for card_variant in _visible_legacy_cards():
		if typeof(card_variant) != TYPE_DICTIONARY:
			continue
		ids.append(str((card_variant as Dictionary).get("id", "")).strip_edges())
	return ids

func GetVisibleRewardEntriesForTest() -> Array[Dictionary]:
	var visible_entries: Array[Dictionary] = []
	for entry_variant in _entries:
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		visible_entries.append((entry_variant as Dictionary).duplicate(true))
	return visible_entries

func GetCardCountForTest() -> int:
	return GetOfferedCardIdsForTest().size()

func GetVisibleCardSlotCountForTest() -> int:
	var count: int = 0
	for slot in _legacy_card_slots:
		if slot.visible:
			count += 1
	return count

func GetSelectedIndexForTest() -> int:
	return _selected_index

func CanConfirmSelectedForTest(index: int) -> bool:
	return not _is_locked and _selected_index == index and index >= 0 and index < GetCardCountForTest()

func IsLockedForTest() -> bool:
	return _is_locked

func GetFeedbackForTest() -> String:
	return _feedback_text

func ShowLockedFeedbackForTest() -> void:
	_is_locked = true
	_feedback_text = _text("reward.locked", "Reward is locked.")
	_refresh_feedback_labels()
	_refresh_legacy_action_state()

func SelectChoiceForTest(index: int) -> bool:
	if _is_locked:
		return false
	if index < 0 or index >= GetCardCountForTest():
		_feedback_text = _text(FEEDBACK_SELECT_FIRST_KEY, "Select a reward first.")
		_refresh_feedback_labels()
		_refresh_legacy_action_state()
		return false
	_selected_index = index
	var cards: Array = _visible_legacy_cards()
	var selected_name: String = str(cards[index].get("display_name", cards[index].get("name", ""))).strip_edges()
	_feedback_text = _text(FEEDBACK_SELECTED_KEY, "Selected reward {0}").replace("{0}", selected_name)
	_refresh_feedback_labels()
	_refresh_legacy_action_state()
	return true

func ConfirmSelectedForTest() -> bool:
	if _is_locked:
		return false
	var cards: Array = _visible_legacy_cards()
	if _selected_index < 0 or _selected_index >= cards.size():
		_feedback_text = _text(FEEDBACK_SELECT_FIRST_KEY, "Select a reward first.")
		_refresh_feedback_labels()
		_refresh_legacy_action_state()
		return false
	var entry: Dictionary = _first_card_choice_entry()
	if entry.is_empty():
		_feedback_text = _text(FEEDBACK_SELECT_FIRST_KEY, "Select a reward first.")
		_refresh_feedback_labels()
		_refresh_legacy_action_state()
		return false
	var card: Dictionary = cards[_selected_index] as Dictionary
	_claim_reward(
		str(entry.get("reward_type", "")).strip_edges(),
		str(card.get("id", "")).strip_edges(),
		_selected_index
	)
	_compat_resolve_remaining_entries_after_legacy_confirm()
	return true

func SkipForTest() -> bool:
	if _is_locked:
		return false
	var entry: Dictionary = _first_card_choice_entry()
	if entry.is_empty():
		_feedback_text = _text(FEEDBACK_SELECT_FIRST_KEY, "Select a reward first.")
		_refresh_feedback_labels()
		_refresh_legacy_action_state()
		return false
	var reward_type: String = str(entry.get("reward_type", "")).strip_edges()
	var main = _resolve_main_controller()
	if main == null or not main.has_method("ResolveRewardForTest"):
		return false
	var result_variant = main.call("ResolveRewardForTest", {
		"action": "skip",
		"skip_reward_type": reward_type
	})
	var result: Dictionary = result_variant as Dictionary if typeof(result_variant) == TYPE_DICTIONARY else {}
	var still_on_reward: bool = str(result.get("scene_path", "")).strip_edges() == "res://Game.Godot/Scenes/Reward.tscn"
	_is_locked = not still_on_reward
	_feedback_text = _text(FEEDBACK_SKIPPED_KEY, "Reward skipped.")
	_selected_index = -1
	_reload_and_refresh()
	return true

func RefreshLocaleForTest() -> void:
	_feedback_text = _text(FEEDBACK_SELECT_DEFAULT_KEY, "Select a reward.")
	_rebuild_all_views()

func SetLocaleForTest(locale: String) -> void:
	TranslationServer.set_locale(locale)
	RefreshLocaleForTest()

func _compat_resolve_remaining_entries_after_legacy_confirm() -> void:
	var main = _resolve_main_controller()
	if main == null or not main.has_method("ResolveRewardForTest"):
		return
	while true:
		_load_offer_snapshot_from_main()
		_filter_resolved_entries()
		if _entries.is_empty():
			break
		var entry_variant = _entries[0]
		if typeof(entry_variant) != TYPE_DICTIONARY:
			break
		var entry: Dictionary = (entry_variant as Dictionary).duplicate(true)
		if entry.is_empty():
			break
		var result_variant = main.call("ResolveRewardForTest", {
			"action": "skip",
			"skip_reward_type": str(entry.get("reward_type", "")).strip_edges()
		})
		if typeof(result_variant) != TYPE_DICTIONARY:
			break
		var result: Dictionary = result_variant as Dictionary
		if str(result.get("scene_path", "")).strip_edges() != "res://Game.Godot/Scenes/Reward.tscn":
			_is_locked = true
			break
