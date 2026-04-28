extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

func _new_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene

# acceptance: ACC:T64.2
# After each command attempt, HUD must show accepted/refused outcome text.
func test_hud_feedback_shows_outcome_for_each_command_attempt() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	var baseline := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":2,"playerHp":22,"energy":2,"drawPileCount":7,"discardPileCount":3,"turnState":"PlayerTurn"}'))
	assert_that(baseline).is_true()
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)

	var accepted := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(accepted).is_true()
	var rejected := bool(scene.call("RequestTurnActionForTest", "invalid_action"))
	assert_that(rejected).is_false()

	var command_history := scene.call("GetFeedbackHistoryForTest") as Array
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(command_history.size()).is_equal(2)
	assert_that(str(command_history[0]).find("accepted") >= 0).is_true()
	assert_that(str(command_history[1]).find("refused") >= 0).is_true()
	assert_that(latest_feedback.find("refused") >= 0).is_true()
	assert_that(latest_feedback.find("That action is invalid") >= 0).is_true()
	var accepted_again := bool(scene.call("TryApplyAcceptedStrikeForTest"))
	assert_that(accepted_again).is_true()
	var accepted_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(accepted_feedback.find("accepted") >= 0).is_true()
	assert_that(accepted_feedback.find("Energy -1") >= 0).is_true()
	assert_that(accepted_feedback.find("remaining") >= 0).is_true()
	assert_that(str(command_history[0]).length()).is_less_equal(80)
	assert_that(str(command_history[1]).length()).is_less_equal(80)
	TranslationServer.set_locale(previous_locale)

# acceptance: ACC:T64.5
# Windows smoke: accepted and rejected commands both produce player-visible HUD feedback.
func test_windows_smoke_rejected_command_keeps_state_and_shows_refusal_message() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	assert_that(OS.get_name()).is_equal("Windows")
	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	var baseline := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":3,"playerHp":26,"energy":2,"drawPileCount":10,"discardPileCount":4,"turnState":"PlayerTurn"}'))
	assert_that(baseline).is_true()
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	scene.call("RequestPlaySelectedCardForTest")
	var accepted_before := int(scene.call("GetAcceptedCommandCountForTest"))
	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var enemy_before := int(scene.call("GetEnemyIntentRowCountForTest"))
	var selected_before := str(scene.call("GetSelectedCommandStateForTest"))

	var rejected := bool(scene.call("RequestTurnActionForTest", "invalid_action"))
	assert_that(rejected).is_false()
	var accepted_after := int(scene.call("GetAcceptedCommandCountForTest"))
	var latest_message := str(scene.call("GetLatestFeedbackMessageForTest"))
	var feedback_history := scene.call("GetFeedbackHistoryForTest") as Array
	var state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var enemy_after := int(scene.call("GetEnemyIntentRowCountForTest"))
	var selected_after := str(scene.call("GetSelectedCommandStateForTest"))

	assert_that(accepted_after).is_equal(accepted_before)
	assert_that(latest_message.find("refused") >= 0).is_true()
	assert_that(latest_message.find("That action is invalid") >= 0).is_true()
	assert_that(latest_message.length()).is_less_equal(80)
	assert_that(feedback_history.size()).is_equal(2)
	assert_that(str(feedback_history[0]).find("accepted") >= 0).is_true()
	assert_that(str(feedback_history[1]).find("refused") >= 0).is_true()
	assert_that(state_after).is_equal(state_before)
	assert_that(enemy_after).is_equal(enemy_before)
	assert_that(selected_after).is_equal(selected_before)
	assert_that(str(state_before["selectedCommandState"]).find("accepted:Strike") >= 0).is_true()
	TranslationServer.set_locale(previous_locale)

# acceptance: ACC:T64.2
func test_feedback_text_resolves_for_en_and_zh_cn_locales() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	scene.call("ApplyCommandFeedbackForTest", "strike", true)
	var en_text := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(en_text).is_not_empty()
	assert_that(en_text.find("accepted") >= 0).is_true()

	TranslationServer.set_locale("zh-CN")
	scene.call("ApplyCommandFeedbackForTest", "strike", true)
	var zh_text := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(zh_text).is_not_empty()
	assert_that(zh_text).is_not_equal("combat.feedback.accepted")
	assert_that(zh_text.find("\u547d\u4ee4") >= 0).is_true()
	assert_that(zh_text.find("\u5df2\u63a5\u53d7") >= 0).is_true()
	assert_that(zh_text.find("strike") >= 0).is_true()
	assert_that(zh_text.find("accepted") < 0).is_true()

	TranslationServer.set_locale(previous_locale)


# ACC:T72.4
# ACC:T75.4
func test_rejected_play_paths_keep_state_unchanged_for_energy_missing_definition_and_invalid_target() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList

	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":0,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	hand.select(0)
	var state_before_energy := scene.call("CaptureUiStateForTest") as Dictionary
	var energy_rejected := bool(scene.call("RequestPlaySelectedCardForTest"))
	var state_after_energy := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(energy_rejected).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("insufficient energy") >= 0).is_true()
	assert_that(state_after_energy).is_equal(state_before_energy)

	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["UnknownCard"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	hand = root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var state_before_missing := scene.call("CaptureUiStateForTest") as Dictionary
	var missing_rejected := bool(scene.call("RequestPlaySelectedCardForTest"))
	var state_after_missing := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(missing_rejected).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("missing card definition") >= 0).is_true()
	assert_that(state_after_missing).is_equal(state_before_missing)

	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	hand = root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var state_before_target := scene.call("CaptureUiStateForTest") as Dictionary
	var target_rejected := bool(scene.call("RequestPlaySelectedCardForTest"))
	var state_after_target := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(target_rejected).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid target") >= 0).is_true()
	assert_that(state_after_target).is_equal(state_before_target)

	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.invalid_status"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t75.invalid_status","name_key":"card.t75.invalid_status.name","description_key":"card.t75.invalid_status.description","cost":1,"type":"skill","target":"enemy","base_effect":{"status_id":"status.expired_reference","status_stacks":1}}]}'
	))).is_true()
	hand = root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var state_before_invalid_status := scene.call("CaptureUiStateForTest") as Dictionary
	var invalid_status_rejected := bool(scene.call("RequestPlaySelectedCardForTest"))
	var state_after_invalid_status := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(invalid_status_rejected).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("invalid status reference") >= 0).is_true()
	assert_that(state_after_invalid_status).is_equal(state_before_invalid_status)
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)

	TranslationServer.set_locale(previous_locale)


# ACC:T75.3
func test_turn_boundary_keeps_status_stack_changes_visible_in_hud_and_feedback_flow() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()

	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t75.weak_one","name_key":"card.t75.weak_one.name","description_key":"card.t75.weak_one.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.weak","status_stacks":1}},{"id":"card.t75.weak_two","name_key":"card.t75.weak_two.name","description_key":"card.t75.weak_two.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.weak","status_stacks":2}}]}'
	))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.weak_one","card.t75.weak_two"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()

	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var first_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(first_feedback.find("applied status.weak +1 to enemy_m1_slime") >= 0).is_true()
	assert_that(str(scene.call("GetEnemyStatusForTest", "enemy_m1_slime")).find("status.weak +1") >= 0).is_true()

	hand = (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var second_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(second_feedback.find("applied status.weak +2 to enemy_m1_slime") >= 0).is_true()
	assert_that(str(scene.call("GetEnemyStatusForTest", "enemy_m1_slime")).find("status.weak +3") >= 0).is_true()

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var end_turn_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	var enemy_status_after_turn := str(scene.call("GetEnemyStatusTextForTest")).strip_edges()
	assert_that(end_turn_feedback.find("Enemy dealt") >= 0).is_true()
	assert_that(end_turn_feedback.find("decayed status.weak to 2 on enemy_m1_slime") >= 0).is_true()
	assert_that(end_turn_feedback.find("Turn ") >= 0).is_true()
	assert_that(enemy_status_after_turn.find("status.weak +2") >= 0).is_true()
	assert_that(enemy_status_after_turn).is_not_equal("None")

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)
	TranslationServer.set_locale(previous_locale)


# ACC:T72.7
func test_status_card_and_exhaust_card_apply_expected_target_and_pile_routing() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var previous_locale := TranslationServer.get_locale()
	TranslationServer.set_locale("en")
	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList

	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Battle Focus"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	hand.select(0)
	var played_status := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(played_status).is_true()
	var feedback_status := str(scene.call("GetLatestFeedbackMessageForTest"))
	var enemy_status := str(scene.call("GetEnemyStatusForTest", "enemy_m1_slime"))
	assert_that(enemy_status.find("status.rage") < 0).is_true()
	assert_that(str(scene.call("GetPlayerStatusSummaryForTest")).find("status.rage:2") >= 0).is_true()
	assert_that(feedback_status.find("status.rage") >= 0).is_true()
	assert_that(feedback_status.find("to self") >= 0).is_true()

	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Power Through"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	hand = root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var played_exhaust := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(played_exhaust).is_true()
	var feedback_exhaust := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(int(scene.call("GetDiscardPileCountForTest"))).is_equal(0)
	assert_that(int(scene.call("GetExhaustPileCountForTest"))).is_equal(1)
	assert_that(feedback_exhaust.find("moved to exhaust") >= 0).is_true()

	TranslationServer.set_locale(previous_locale)
