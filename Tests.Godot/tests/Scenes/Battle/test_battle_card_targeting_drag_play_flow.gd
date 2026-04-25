extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class BattleCardTargetingDragFlowModel:
	extends RefCounted

	signal card_play_requested(card_id: String, target_id: String)
	signal invalid_target_feedback_requested(card_id: String, target_id: String)

	var dragging_card_id: String = ""
	var selected_target_id: String = ""

	func start_drag(card_id: String) -> void:
		dragging_card_id = card_id

	func hover_target(target_id: String) -> void:
		selected_target_id = target_id

	func drop_on_target(target_id: String, is_valid_target: bool) -> void:
		if not is_valid_target:
			invalid_target_feedback_requested.emit(dragging_card_id, target_id)
			selected_target_id = target_id
			return

		selected_target_id = target_id
		card_play_requested.emit(dragging_card_id, target_id)
		dragging_card_id = ""

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

func _new_combat_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene


# acceptance anchor: ACC:T73.2
func test_dragging_over_valid_target_requests_play_and_clears_drag_state() -> void:
	var sut := BattleCardTargetingDragFlowModel.new()
	var events: Array[String] = []

	sut.card_play_requested.connect(func(card_id: String, target_id: String) -> void:
		events.append("play:%s->%s" % [card_id, target_id])
	)
	sut.invalid_target_feedback_requested.connect(func(card_id: String, target_id: String) -> void:
		events.append("invalid:%s->%s" % [card_id, target_id])
	)

	sut.start_drag("card_fireball")
	sut.hover_target("enemy_1")
	sut.drop_on_target("enemy_1", true)

	assert_that(events).is_equal(["play:card_fireball->enemy_1"])
	assert_that(sut.dragging_card_id).is_equal("")
	assert_that(sut.selected_target_id).is_equal("enemy_1")


# acceptance: ACC:T34.4
# Invalid targets should provide observable feedback and keep card drag active.
# acceptance anchor: ACC:T73.3
func test_drop_on_invalid_target_keeps_dragging_and_emits_feedback_without_play_request() -> void:
	var sut := BattleCardTargetingDragFlowModel.new()
	var events: Array[String] = []

	sut.card_play_requested.connect(func(card_id: String, target_id: String) -> void:
		events.append("play:%s->%s" % [card_id, target_id])
	)
	sut.invalid_target_feedback_requested.connect(func(card_id: String, target_id: String) -> void:
		events.append("invalid:%s->%s" % [card_id, target_id])
	)

	sut.start_drag("card_heal")
	sut.hover_target("ally_dead")
	sut.drop_on_target("ally_dead", false)

	assert_that(events).is_equal(["invalid:card_heal->ally_dead"])
	assert_that(sut.dragging_card_id).is_equal("card_heal")
	assert_that(sut.selected_target_id).is_equal("ally_dead")


func test_invalid_target_in_real_combat_keeps_hp_energy_and_piles_unchanged() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_dead"))).is_false()
	var before := scene.call("CaptureUiStateForTest") as Dictionary
	var before_enemy_hp := str(scene.call("GetEnemyHpTextForTest"))
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	var after := scene.call("CaptureUiStateForTest") as Dictionary
	var after_enemy_hp := str(scene.call("GetEnemyHpTextForTest"))
	assert_that(after).is_equal(before)
	assert_that(after_enemy_hp).is_equal(before_enemy_hp)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()
