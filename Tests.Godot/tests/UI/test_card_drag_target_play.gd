extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class FakeTarget:
	extends RefCounted
	var id: String
	var accepts_card: bool

	func _init(target_id: String, can_accept_card: bool) -> void:
		id = target_id
		accepts_card = can_accept_card

	func can_accept(_card_id: String) -> bool:
		return accepts_card


class BuggyCardDragPlayController:
	extends RefCounted
	signal play_attempted(card_id: String, target_id: String)
	signal play_succeeded(card_id: String, target_id: String)

	var hand: Array[String] = []

	func _init(initial_hand: Array[String]) -> void:
		hand = initial_hand.duplicate()

	func drag_card_to_target(card_id: String, target: FakeTarget) -> void:
		play_attempted.emit(card_id, target.id)
		if target.can_accept(card_id):
			hand.erase(card_id)
			play_succeeded.emit(card_id, target.id)
			return


class SignalProbe:
	extends RefCounted
	var attempted_count: int = 0
	var succeeded_count: int = 0

	func on_play_attempted(_card_id: String, _target_id: String) -> void:
		attempted_count += 1

	func on_play_succeeded(_card_id: String, _target_id: String) -> void:
		succeeded_count += 1


# acceptance: ACC:T34.6
func test_drag_to_valid_target_plays_card_and_removes_from_hand() -> void:
	var controller := BuggyCardDragPlayController.new(["card_firebolt", "card_shield"])
	var target := FakeTarget.new("enemy_slot_1", true)
	var probe := SignalProbe.new()

	controller.play_succeeded.connect(Callable(probe, "on_play_succeeded"))
	controller.drag_card_to_target("card_firebolt", target)

	assert_bool(controller.hand.has("card_firebolt")).is_false()
	assert_int(probe.succeeded_count).is_equal(1)


# acceptance: ACC:T34.8
func test_drag_to_valid_target_reports_success_not_attempt_only() -> void:
	var controller := BuggyCardDragPlayController.new(["card_firebolt"])
	var target := FakeTarget.new("enemy_slot_1", true)
	var probe := SignalProbe.new()

	controller.play_attempted.connect(Callable(probe, "on_play_attempted"))
	controller.play_succeeded.connect(Callable(probe, "on_play_succeeded"))
	controller.drag_card_to_target("card_firebolt", target)

	assert_int(probe.attempted_count).is_equal(1)
	assert_int(probe.succeeded_count).is_equal(1)
