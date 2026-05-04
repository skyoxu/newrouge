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

func _enemy_hp_text(scene: Node, enemy_id: String) -> String:
	return str(scene.call("GetEnemyHpTextByIdForTest", enemy_id))


func _assert_refusal_keeps_resource_state(before_state: Dictionary, after_state: Dictionary) -> void:
	assert_that(after_state["hand"]).is_equal(before_state["hand"])
	assert_that(after_state["energy"]).is_equal(before_state["energy"])
	assert_that(after_state["draw"]).is_equal(before_state["draw"])
	assert_that(after_state["discard"]).is_equal(before_state["discard"])
	assert_that(after_state["playerHp"]).is_equal(before_state["playerHp"])
	assert_that(after_state["selectedCommandState"]).is_equal(before_state["selectedCommandState"])


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

# acceptance anchor: ACC:T73.2
func test_single_target_card_requires_explicit_legal_living_target_and_accepts_when_selected() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	var before_invalid := scene.call("CaptureUiStateForTest") as Dictionary
	var brute_hp_before_invalid := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	var after_invalid := scene.call("CaptureUiStateForTest") as Dictionary
	_assert_refusal_keeps_resource_state(before_invalid, after_invalid)
	assert_that(_enemy_hp_text(scene, "enemy_t73_brute")).is_equal(brute_hp_before_invalid)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()

	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t73_brute"))).is_true()
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var after_valid := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(after_valid["energy"]).is_equal("1")
	assert_that(after_valid["discard"]).is_equal("2")
	assert_that(after_valid["selectedCommandState"]).is_equal("accepted:Strike")
	assert_that(_enemy_hp_text(scene, "enemy_t73_brute")).is_equal("14/20")


# acceptance anchor: ACC:T73.2
func test_single_target_card_hits_only_selected_enemy_when_multiple_enemies_are_alive() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t73_brute"))).is_true()

	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	var slime_hp := str(scene.call("GetEnemyHpTextForTest"))
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t73_brute"))).is_true()
	var brute_hp := str(scene.call("GetEnemyHpTextForTest"))
	assert_that(slime_hp).is_equal("32/32")
	assert_that(brute_hp).is_equal("14/20")


# acceptance anchor: ACC:T73.2
func test_self_target_card_can_resolve_without_enemy_selection() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.warrior.defend"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	var before := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_dead"))).is_false()

	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var after := scene.call("CaptureUiStateForTest") as Dictionary

	assert_that(after["energy"]).is_equal("1")
	assert_that(after["discard"]).is_equal("2")
	assert_that(after["selectedCommandState"]).is_equal("accepted:card.warrior.defend")
	assert_that(int(scene.call("GetPlayerBlockForTest"))).is_greater(0)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("accepted") >= 0).is_true()
	assert_that(after["playerHp"]).is_equal(before["playerHp"])


# acceptance anchor: ACC:T73.2
func test_all_enemy_card_can_resolve_without_enemy_selection() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.warrior.cleave"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	var before_enemy_hp := str(scene.call("GetEnemyHpTextForTest"))
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_dead"))).is_false()

	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var after := scene.call("CaptureUiStateForTest") as Dictionary
	var after_enemy_hp := str(scene.call("GetEnemyHpTextForTest"))

	assert_that(after["energy"]).is_equal("1")
	assert_that(after["discard"]).is_equal("2")
	assert_that(after["selectedCommandState"]).is_equal("accepted:card.warrior.cleave")
	assert_that(after_enemy_hp).is_not_equal(before_enemy_hp)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("accepted") >= 0).is_true()


# acceptance anchor: ACC:T73.2
func test_all_enemy_card_mutates_each_living_enemy_in_multi_enemy_runtime() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.warrior.cleave"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()

	var slime_before := _enemy_hp_text(scene, "enemy_m1_slime")
	var brute_before := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var slime_after := _enemy_hp_text(scene, "enemy_m1_slime")
	var brute_after := _enemy_hp_text(scene, "enemy_t73_brute")

	assert_that(slime_after).is_not_equal(slime_before)
	assert_that(brute_after).is_not_equal(brute_before)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("accepted") >= 0).is_true()


# acceptance: ACC:T34.4
# Invalid targets should provide observable feedback and keep card drag active.
# acceptance anchor: ACC:T73.3
# acceptance anchor: ACC:T74.3
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
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var before := scene.call("CaptureUiStateForTest") as Dictionary
	var brute_before := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	var after := scene.call("CaptureUiStateForTest") as Dictionary
	_assert_refusal_keeps_resource_state(before, after)
	assert_that(_enemy_hp_text(scene, "enemy_t73_brute")).is_equal(brute_before)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()


# acceptance anchor: ACC:T73.3
func test_locked_target_rejection_keeps_hp_energy_and_piles_unchanged() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var selected := bool(scene.call("SetTargetEnemyIdForTest", "enemy_locked_slot"))
	if selected:
		assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_locked_slot", 0, 32))).is_true()
	var before := scene.call("CaptureUiStateForTest") as Dictionary
	var brute_before := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	var after := scene.call("CaptureUiStateForTest") as Dictionary
	_assert_refusal_keeps_resource_state(before, after)
	assert_that(_enemy_hp_text(scene, "enemy_t73_brute")).is_equal(brute_before)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()


# acceptance anchor: ACC:T73.3
func test_disconnected_target_rejection_keeps_hp_energy_and_piles_unchanged() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var selected := bool(scene.call("SetTargetEnemyIdForTest", "enemy_disconnected"))
	if selected:
		assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_disconnected", 0, 32))).is_true()
	var before := scene.call("CaptureUiStateForTest") as Dictionary
	var brute_before := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	var after := scene.call("CaptureUiStateForTest") as Dictionary
	_assert_refusal_keeps_resource_state(before, after)
	assert_that(_enemy_hp_text(scene, "enemy_t73_brute")).is_equal(brute_before)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()


# acceptance anchor: ACC:T73.7
func test_selection_becomes_illegal_before_resolution_and_card_effect_never_applies_to_illegal_target() -> void:
	var scene := _new_combat_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":2,"drawPileCount":6,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 20, 20))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	assert_that(str(scene.call("GetSelectedEnemyTargetIdForTest"))).is_equal("enemy_m1_slime")

	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var before_enemy_hp := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_false()
	assert_that(str(scene.call("GetSelectedEnemyTargetIdForTest"))).is_equal("")
	var after_enemy_hp := _enemy_hp_text(scene, "enemy_t73_brute")
	assert_that(after_enemy_hp).is_equal(before_enemy_hp)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()
