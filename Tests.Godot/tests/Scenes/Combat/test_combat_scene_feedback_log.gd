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

	var accepted := bool(scene.call("TryApplyAcceptedStrikeForTest"))
	assert_that(accepted).is_true()
	var rejected := bool(scene.call("RequestTurnActionForTest", "invalid_action"))
	assert_that(rejected).is_false()

	var command_history := scene.call("GetFeedbackHistoryForTest") as Array
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(command_history.size()).is_equal(2)
	assert_that(str(command_history[0]).find("accepted") >= 0).is_true()
	assert_that(str(command_history[1]).find("refused") >= 0).is_true()
	assert_that(latest_feedback.find("refused") >= 0).is_true()
	assert_that(latest_feedback.find("invalid action") >= 0).is_true()
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
	scene.call("RequestTurnActionForTest", "start_turn")
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
	assert_that(latest_message.find("invalid action") >= 0).is_true()
	assert_that(latest_message.length()).is_less_equal(80)
	assert_that(feedback_history.size()).is_equal(2)
	assert_that(str(feedback_history[0]).find("accepted") >= 0).is_true()
	assert_that(str(feedback_history[1]).find("refused") >= 0).is_true()
	assert_that(state_after).is_equal(state_before)
	assert_that(enemy_after).is_equal(enemy_before)
	assert_that(selected_after).is_equal(selected_before)
	assert_that(str(state_before["selectedCommandState"]).find("accepted:start_turn") >= 0).is_true()
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
