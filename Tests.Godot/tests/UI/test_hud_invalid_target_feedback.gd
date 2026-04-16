extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class FakeHud extends Control:
	var hand_cards: Array[String] = []
	var feedback_visible := false
	var feedback_text := ""
	var event_log: Array[String] = []

	func setup_hand(cards: Array[String]) -> void:
		hand_cards.clear()
		for card_id in cards:
			hand_cards.append(card_id)

	func drag_play(card_id: String, target_name: String, target_is_valid: bool) -> void:
		event_log.append("drag_started:%s" % card_id)
		event_log.append("target_selected:%s" % target_name)

		if target_is_valid:
			hand_cards.erase(card_id)
			event_log.append("card_played:%s" % card_id)
			feedback_visible = false
			feedback_text = ""
			return

		event_log.append("play_refused:%s" % card_id)
		feedback_visible = true
		feedback_text = "Invalid target: %s" % target_name


# acceptance: ACC:T34.4
func test_drag_play_with_invalid_target_shows_feedback_and_refuses_play() -> void:
	var hud := FakeHud.new()
	hud.setup_hand(["card-001", "card-002"])

	hud.drag_play("card-001", "enemy-slot-2", false)

	assert_bool(hud.feedback_visible).is_true()
	assert_str(hud.feedback_text).contains("Invalid target")
	assert_str(hud.feedback_text).contains("enemy-slot-2")
	assert_array(hud.hand_cards).is_equal(["card-001", "card-002"])
	assert_array(hud.event_log).is_equal([
		"drag_started:card-001",
		"target_selected:enemy-slot-2",
		"play_refused:card-001"
	])


func test_drag_play_with_valid_target_consumes_card_and_clears_feedback() -> void:
	var hud := FakeHud.new()
	hud.setup_hand(["card-001", "card-002"])

	hud.drag_play("card-001", "enemy-slot-2", true)

	assert_bool(hud.feedback_visible).is_false()
	assert_str(hud.feedback_text).is_empty()
	assert_array(hud.hand_cards).is_equal(["card-002"])
	assert_array(hud.event_log).is_equal([
		"drag_started:card-001",
		"target_selected:enemy-slot-2",
		"card_played:card-001"
	])
