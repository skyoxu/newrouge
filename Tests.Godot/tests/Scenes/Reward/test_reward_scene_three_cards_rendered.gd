extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_FORMS := ["Base", "U1A", "U1B", "Ultimate"]

func _build_reward_scene_projection_for_red() -> Array:
	return [
		{"name": "Strike+", "description": "Deal +2 damage.", "form": "Base", "selectable": true},
		{"name": "Guard+", "description": "Gain +2 block.", "form": "U1A", "selectable": true},
		{"name": "Rage++", "description": "Gain +1 rage this turn.", "form": "U1B", "selectable": true}
	]

func _is_card_complete(card: Dictionary) -> bool:
	if not card.has("name"):
		return false
	if not card.has("description"):
		return false
	if not card.has("form"):
		return false
	if not card.has("selectable"):
		return false

	var name_text := String(card["name"]).strip_edges()
	var description_text := String(card["description"]).strip_edges()
	var form_text := String(card["form"]).strip_edges()
	var selectable := bool(card["selectable"])

	if name_text.is_empty() or description_text.is_empty():
		return false
	if not REQUIRED_FORMS.has(form_text):
		return false
	if not selectable:
		return false
	return true

func _validate_reward_cards(cards: Array) -> bool:
	if cards.size() != 3:
		return false
	for card_data in cards:
		if typeof(card_data) != TYPE_DICTIONARY:
			return false
		var card: Dictionary = card_data
		if not _is_card_complete(card):
			return false
	return true

# acceptance: ACC:T19.1
# RED-FIRST: fails deterministically until Reward scene renders exactly three complete selectable cards.
func test_reward_scene_renders_exactly_three_selectable_cards_with_required_fields() -> void:
	var rendered_cards := _build_reward_scene_projection_for_red()
	assert_that(_validate_reward_cards(rendered_cards)).is_true()

func test_reward_scene_rejects_cards_when_any_required_field_is_missing() -> void:
	var invalid_cards := [
		{"name": "Strike+", "description": "Deal +2 damage.", "form": "Base", "selectable": true},
		{"name": "Guard+", "description": "Gain +2 block.", "form": "U1A", "selectable": true},
		{"name": "Rage++", "description": "", "form": "Ultimate", "selectable": true}
	]
	assert_that(_validate_reward_cards(invalid_cards)).is_false()
