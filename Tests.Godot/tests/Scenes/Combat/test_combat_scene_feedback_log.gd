extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

func _new_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene

# acceptance: ACC:T64.2
# After each command attempt, HUD must show accepted/refused outcome text.
# ACC:T78.2
# ACC:T78.5
# ACC:T78.6
# ACC:T78.8
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
# ACC:T77.2
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
# ACC:T77.4
# ACC:T77.5
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


# ACC:T77.2
func test_identical_command_sequence_produces_identical_feedback_history_and_state_deltas() -> void:
	var snapshots: Array[Dictionary] = []
	var histories: Array[Array] = []
	var latest_messages: Array[String] = []
	for _run in range(2):
		var scene := _new_scene()
		await get_tree().process_frame
		TranslationServer.set_locale("en")
		assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t77_seq", 24, 24))).is_true()
		assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t77_seq"))).is_true()
		assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend","Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
		var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
		hand.select(0)
		assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
		assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
		snapshots.append(scene.call("CaptureUiStateForTest") as Dictionary)
		histories.append(scene.call("GetFeedbackHistoryForTest") as Array)
		latest_messages.append(str(scene.call("GetLatestFeedbackMessageForTest")))

	assert_that(snapshots[1]).is_equal(snapshots[0])
	assert_that(histories[1]).is_equal(histories[0])
	assert_that(latest_messages[1]).is_equal(latest_messages[0])


# ACC:T77.2
func test_turn_start_and_turn_end_hooks_are_both_invoked_on_runtime_path() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var dispatched_before := scene.call("GetDispatchedCommandsForTest") as Array
	assert_that(dispatched_before.size()).is_equal(0)

	assert_that(bool(scene.call("RequestTurnActionForTest", "start_turn"))).is_true()
	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var dispatched_after := scene.call("GetDispatchedCommandsForTest") as Array
	assert_that(dispatched_after.size()).is_equal(2)
	assert_that(str(dispatched_after[0])).is_equal("start_turn")
	assert_that(str(dispatched_after[1])).is_equal("end_turn")


# ACC:T77.4
func test_turn_resolution_route_completion_remains_route_owned_and_not_trigger_autonomous() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t77_route_guard", 24, 24))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t77_route_guard"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()

	var dispatched_before := scene.call("GetDispatchedCommandsForTest") as Array
	assert_that(dispatched_before.size()).is_equal(0)

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var dispatched_after := scene.call("GetDispatchedCommandsForTest") as Array
	assert_that(dispatched_after.size()).is_equal(1)
	assert_that(str(dispatched_after[0])).is_equal("end_turn")

	var selected_target_after := str(scene.call("GetSelectedEnemyTargetIdForTest"))
	assert_that(selected_target_after).is_not_empty()
	assert_that(selected_target_after).is_equal("enemy_t77_route_guard")
	assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_t77_route_guard"))).is_true()
	assert_that(str(scene.call("GetEnemyIntentDescriptionForTest", "enemy_t77_route_guard")).strip_edges()).is_not_empty()

	var route_result_while_enemy_alive := scene.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(route_result_while_enemy_alive.get("ok", false))).is_false()
	assert_that(str(route_result_while_enemy_alive.get("reason", ""))).is_equal("enemies-still-alive")


# ACC:T77.7
func test_lethal_damage_triggers_single_death_check_before_route_owned_completion_consumption() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t77_lethal", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t77_lethal"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":1,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var defeat_before := int(scene.call("GetDefeatResolveCountForTest"))
	var eligible_before := int(scene.call("GetDefeatEligibleTransitionCountForTest"))
	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var defeat_after_first := int(scene.call("GetDefeatResolveCountForTest"))
	var eligible_after_first := int(scene.call("GetDefeatEligibleTransitionCountForTest"))
	assert_that(defeat_after_first - defeat_before).is_equal(1)
	assert_that(eligible_after_first - eligible_before).is_equal(1)
	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var defeat_after_second := int(scene.call("GetDefeatResolveCountForTest"))
	assert_that(defeat_after_second).is_equal(defeat_after_first)


# ACC:T77.7
func test_non_lethal_damage_does_not_trigger_death_check_and_route_flow_stays_unchanged() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t77_non_lethal", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t77_non_lethal"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var defeat_before := int(scene.call("GetDefeatResolveCountForTest"))
	var eligible_before := int(scene.call("GetDefeatEligibleTransitionCountForTest"))
	var route_before := scene.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(route_before.get("ok", false))).is_false()
	assert_that(str(route_before.get("reason", ""))).is_equal("enemies-still-alive")

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var defeat_after := int(scene.call("GetDefeatResolveCountForTest"))
	var eligible_after := int(scene.call("GetDefeatEligibleTransitionCountForTest"))
	assert_that(defeat_after).is_equal(defeat_before)
	assert_that(eligible_after).is_equal(eligible_before)
	var route_after := scene.call("RequestVictoryRouteToRewardForTest") as Dictionary
	assert_that(bool(route_after.get("ok", false))).is_false()
	assert_that(str(route_after.get("reason", ""))).is_equal("enemies-still-alive")


# ACC:T77.5
func test_t77_scope_does_not_introduce_power_relic_or_potion_effect_integration() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t77.guard","name_key":"card.t77.guard.name","description_key":"card.t77.guard.description","cost":1,"type":"skill","target":"self","base_effect":{"block":4}}]}'
	))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t77.guard"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var block_before := int(scene.call("GetPlayerBlockForTest"))
	var accepted_count_before := int(scene.call("GetAcceptedCommandCountForTest"))
	var hp_events_before := int(scene.call("GetHpChangedEmissionCountForTest"))
	var defeat_events_before := int(scene.call("GetDefeatResolveCountForTest"))
	var cards_played_before := int(scene.call("GetCardsPlayedThisTurnForTest"))

	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var block_after := int(scene.call("GetPlayerBlockForTest"))
	var accepted_count_after := int(scene.call("GetAcceptedCommandCountForTest"))
	var hp_events_after := int(scene.call("GetHpChangedEmissionCountForTest"))
	var defeat_events_after := int(scene.call("GetDefeatResolveCountForTest"))
	var cards_played_after := int(scene.call("GetCardsPlayedThisTurnForTest"))
	var feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	var history := scene.call("GetFeedbackHistoryForTest") as Array
	var status_text := str(scene.call("GetEnemyStatusTextForTest")).to_lower()
	assert_that(state_after["energy"]).is_equal("2")
	assert_that(state_after["discard"]).is_equal("1")
	assert_that(state_after["hand"]).is_equal([])
	assert_that(block_after - block_before).is_equal(4)
	assert_that(accepted_count_after - accepted_count_before).is_equal(1)
	assert_that(hp_events_after).is_equal(hp_events_before)
	assert_that(defeat_events_after).is_equal(defeat_events_before)
	assert_that(cards_played_after - cards_played_before).is_equal(1)
	assert_that(feedback.find("relic") < 0).is_true()
	assert_that(feedback.find("potion") < 0).is_true()
	assert_that(feedback.find("power") < 0).is_true()
	assert_that(status_text.find("relic") < 0).is_true()
	assert_that(status_text.find("potion") < 0).is_true()
	assert_that(status_text.find("power") < 0).is_true()
	for item in history:
		var line := str(item).to_lower()
		assert_that(line.find("relic") < 0).is_true()
		assert_that(line.find("potion") < 0).is_true()
		assert_that(line.find("power") < 0).is_true()

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


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

# ACC:T106.3
# ACC:T106.5
func test_t106_shared_trigger_order_and_runtime_outcome_are_player_observable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")

	var runtime_snapshot := '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn","powers":[{"id":"berserk_aura","inspectText":"Power Berserk Aura: +2 attack this turn","priority":10,"registrationOrder":3,"outcomeMessage":"Power dealt +2 bonus damage"}],"relics":[{"id":"obsidian_mirror","inspectText":"Relic Obsidian Mirror: copy first attack","priority":10,"registrationOrder":1,"outcomeMessage":"Relic copied first attack"}]}'
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", runtime_snapshot))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t106_runtime", 24, 24))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t106_runtime"))).is_true()
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()

	var trigger_order := scene.call("GetLastPowerRelicTriggerOrderForTest") as Array
	assert_that(trigger_order.size()).is_equal(2)
	assert_that(str(trigger_order[0])).is_equal("Relic.obsidian_mirror")
	assert_that(str(trigger_order[1])).is_equal("Power.berserk_aura")

	var outcome_messages := scene.call("GetLastPowerRelicOutcomeMessagesForTest") as Array
	assert_that(outcome_messages.size()).is_equal(2)
	assert_that(str(outcome_messages[0]).find("Relic.obsidian_mirror") >= 0).is_true()
	assert_that(str(outcome_messages[1]).find("Power.berserk_aura") >= 0).is_true()
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(latest_feedback.find("Power.berserk_aura") >= 0).is_true()


# --- T111 anchors start ---
# keep T111 anchors isolated from T106 relic/power assertions so
# semantic evidence snippets map to potion-specific behavior only.















# ACC:T111.3
# ACC:T111.4
func test_t111_potion_shared_trigger_order_and_feedback_are_deterministic_and_player_visible() -> void:
	var first_order: Array = []
	var second_order: Array = []
	var first_history: Array = []
	var second_history: Array = []

	for run_index in range(2):
		var scene := _new_scene()
		await get_tree().process_frame
		TranslationServer.set_locale("en")

		var runtime_snapshot := '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn","potions":[{"id":"frost_tonic","inspectText":"Potion Frost Tonic: apply chill","priority":10,"registrationOrder":4,"outcomeMessage":"Potion applied chill"},{"id":"ember_vial","inspectText":"Potion Ember Vial: apply burn","priority":10,"registrationOrder":1,"outcomeMessage":"Potion applied burn"}]}'
		assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", runtime_snapshot))).is_true()
		assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t111_runtime", 24, 24))).is_true()
		assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t111_runtime"))).is_true()
		var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
		hand.select(0)
		assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()

		var trigger_order := scene.call("GetLastPowerRelicTriggerOrderForTest") as Array
		assert_that(trigger_order.size()).is_equal(2)
		assert_that(str(trigger_order[0])).is_equal("Potion.ember_vial")
		assert_that(str(trigger_order[1])).is_equal("Potion.frost_tonic")
		var outcome_messages := scene.call("GetLastPowerRelicOutcomeMessagesForTest") as Array
		assert_that(outcome_messages.size()).is_equal(2)
		assert_that(str(outcome_messages[0]).find("Potion.ember_vial") >= 0).is_true()
		assert_that(str(outcome_messages[1]).find("Potion.frost_tonic") >= 0).is_true()
		assert_that(str(outcome_messages[0]).find("Power.") < 0).is_true()
		assert_that(str(outcome_messages[1]).find("Power.") < 0).is_true()
		assert_that(str(outcome_messages[0]).find("Relic.") < 0).is_true()
		assert_that(str(outcome_messages[1]).find("Relic.") < 0).is_true()
		assert_that(bool(scene.call("WasPotionRuntimeClosureExecutedForTest"))).is_true()

		var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
		assert_that(latest_feedback.find("Potion.frost_tonic") >= 0).is_true()
		assert_that(latest_feedback.find("applied chill") >= 0).is_true()
		assert_that(latest_feedback.find("Power.") < 0).is_true()
		assert_that(latest_feedback.find("Relic.") < 0).is_true()
		var history := scene.call("GetFeedbackHistoryForTest") as Array
		var joined := "\n".join(history)
		assert_that(joined.find("Potion.ember_vial") >= 0).is_true()
		assert_that(joined.find("Potion.frost_tonic") >= 0).is_true()
		assert_that(joined.find("Power.") < 0).is_true()
		assert_that(joined.find("Relic.") < 0).is_true()

		if run_index == 0:
			first_order = trigger_order
			first_history = history
		else:
			second_order = trigger_order
			second_history = history

	assert_that(second_order).is_equal(first_order)
	assert_that(second_history).is_equal(first_history)


# ACC:T78.1
# ACC:T78.6
func test_t78_card_play_feedback_exposes_damage_block_and_command_channels() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t78_fx", 30, 30))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t78_fx"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList

	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var strike_feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(strike_feedback.find("dealt") >= 0).is_true()
	assert_that(strike_feedback.find("damage") >= 0).is_true()

	hand = (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var defend_feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(defend_feedback.find("gained") >= 0).is_true()
	assert_that(defend_feedback.find("block") >= 0).is_true()

	var history := scene.call("GetFeedbackHistoryForTest") as Array
	assert_that(history.size()).is_greater_equal(2)
	var cues := scene.call("GetPresentationCueHistoryForTest") as Array
	assert_that(cues.size()).is_equal(7)
	assert_that(str(cues[0])).is_equal("card_play_motion")
	assert_that(str(cues[1])).is_equal("damage_number")
	assert_that(str(cues[2])).is_equal("hit_feedback")
	assert_that(str(cues[3])).is_equal("card_play_motion")
	assert_that(str(cues[4])).is_equal("block_gain_number")
	assert_that(cues.count("card_play_motion")).is_equal(2)
	assert_that(cues.count("damage_number")).is_equal(1)
	assert_that(cues.count("hit_feedback")).is_equal(1)
	assert_that(cues.count("block_gain_number")).is_equal(1)
	var sfx_hooks := scene.call("GetSfxHookHistoryForTest") as Array
	assert_that(sfx_hooks.size()).is_equal(4)
	assert_that(str(sfx_hooks[0])).is_equal("card_play")
	assert_that(str(sfx_hooks[1])).is_equal("hit")
	assert_that(str(sfx_hooks[2])).is_equal("card_play")
	assert_that(str(sfx_hooks[3])).is_equal("block")
	assert_that(sfx_hooks.count("card_play")).is_equal(2)
	assert_that(sfx_hooks.count("hit")).is_equal(1)
	assert_that(sfx_hooks.count("block")).is_equal(1)


# ACC:T78.2
# ACC:T78.5
# ACC:T78.7
# ACC:T78.9
func test_t78_enemy_action_and_invalid_action_feedback_are_independently_observable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var enemy_state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var enemy_rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var enemy_action_feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(enemy_action_feedback.find("enemy dealt") >= 0).is_true()
	var enemy_state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var enemy_rng_after := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(enemy_state_after).is_not_equal(enemy_state_before)
	assert_that(enemy_rng_after).is_greater_equal(enemy_rng_before)

	var invalid_state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var invalid_rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))
	var rejected := bool(scene.call("RequestTurnActionForTest", "invalid_action"))
	assert_that(rejected).is_false()
	var invalid_feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(invalid_feedback.find("refused") >= 0).is_true()
	assert_that(invalid_feedback.find("invalid") >= 0).is_true()
	var invalid_state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var invalid_rng_after := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(invalid_state_after).is_equal(invalid_state_before)
	assert_that(invalid_rng_after).is_equal(invalid_rng_before)
	var sfx_hooks := scene.call("GetSfxHookHistoryForTest") as Array
	var cues := scene.call("GetPresentationCueHistoryForTest") as Array
	assert_that(cues.has("enemy_action_feedback")).is_true()
	assert_that(sfx_hooks.has("enemy_action")).is_true()
	assert_that(sfx_hooks.has("invalid_action")).is_true()
	assert_that(sfx_hooks.has("card_play")).is_false()
	assert_that(str(enemy_state_before["playerHp"])).is_not_empty()
	assert_that(str(enemy_state_after["playerHp"])).is_not_empty()


# ACC:T78.2
func test_t78_missing_audio_resource_noop_keeps_resolution_and_visible_feedback() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("SetSimulateMissingSfxForTest", true)
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t78_noaudio", 24, 24))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t78_noaudio"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))

	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand = (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	assert_that(bool(scene.call("RequestTurnActionForTest", "invalid_action"))).is_false()

	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	var history := scene.call("GetFeedbackHistoryForTest") as Array
	var history_joined := "\n".join(history).to_lower()
	var sfx_hooks := scene.call("GetSfxHookHistoryForTest") as Array
	var missing_hooks := scene.call("GetMissingSfxNoopHistoryForTest") as Array
	var state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_after := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(latest_feedback).contains("refused")
	assert_that(history.size()).is_greater_equal(3)
	assert_that(history_joined.find("accepted") >= 0).is_true()
	assert_that(history_joined.find("dealt") >= 0).is_true()
	assert_that(history_joined.find("enemy dealt") >= 0).is_true()
	assert_that(sfx_hooks.size()).is_equal(0)
	assert_that(missing_hooks.has("card_play")).is_true()
	assert_that(missing_hooks.has("hit")).is_true()
	assert_that(missing_hooks.has("block")).is_true()
	assert_that(missing_hooks.has("enemy_action")).is_true()
	assert_that(missing_hooks.has("invalid_action")).is_true()
	var cues := scene.call("GetPresentationCueHistoryForTest") as Array
	assert_that(cues.has("block_gain_number")).is_true()
	assert_that(str(state_after["turnState"])).is_equal("PlayerTurn")
	assert_that(rng_after).is_greater_equal(rng_before)
	assert_that(str(state_before["playerHp"])).is_not_empty()


# ACC:T78.5
func test_t78_reduced_motion_mode_keeps_deterministic_feedback_without_wall_clock_dependency() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("SetReducedMotionForTest", true)
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))

	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand = (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(feedback.find("enemy dealt") >= 0).is_true()
	var cues := scene.call("GetPresentationCueHistoryForTest") as Array
	assert_that(cues.has("card_play_motion")).is_true()
	assert_that(cues.has("damage_number")).is_true()
	assert_that(cues.has("block_gain_number")).is_true()
	assert_that(cues.has("hit_feedback")).is_true()
	assert_that(cues.has("reduced_motion:card_play_motion")).is_true()
	assert_that(cues.has("reduced_motion:damage_number")).is_true()
	assert_that(cues.has("reduced_motion:block_gain_number")).is_true()
	assert_that(cues.has("reduced_motion:hit_feedback")).is_true()
	assert_that(cues.has("enemy_action_feedback")).is_true()
	assert_that(cues.has("reduced_motion:enemy_action_feedback")).is_true()
	scene.call("ApplyHoverPreviewForTest", "t78_reduced_preview")
	scene.call("CloseHoverPreviewForTest")
	scene.call("HideTargetInspectionForTest")
	cues = scene.call("GetPresentationCueHistoryForTest") as Array
	assert_that(cues.has("reduced_motion:card_preview")).is_true()
	assert_that(cues.has("reduced_motion:card_preview_closed")).is_true()
	assert_that(cues.has("reduced_motion:intent_detail_hidden")).is_true()
	var state_after_enemy := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_after_enemy := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(state_after_enemy).is_not_equal(state_before)
	assert_that(rng_after_enemy).is_greater_equal(rng_before)

	var invalid_before := scene.call("CaptureUiStateForTest") as Dictionary
	var invalid_rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(bool(scene.call("RequestTurnActionForTest", "invalid_action"))).is_false()
	var invalid_after := scene.call("CaptureUiStateForTest") as Dictionary
	var invalid_rng_after := int(scene.call("GetCombatRngStreamPositionForTest"))
	assert_that(invalid_after).is_equal(invalid_before)
	assert_that(invalid_rng_after).is_equal(invalid_rng_before)


# ACC:T78.8
func test_t78_preview_negative_path_keeps_runtime_state_stable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":2,"playerHp":20,"energy":2,"drawPileCount":9,"discardPileCount":1,"turnState":"PlayerTurn"}'))).is_true()
	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_before := int(scene.call("GetCombatRngStreamPositionForTest"))
	var accepted_before := int(scene.call("GetAcceptedCommandCountForTest"))

	# invalid preview payload must be rejected and only emit refusal feedback
	assert_that(bool(scene.call("TryGenerateEnemyIntentPreviewFromAiDefinitionsContractJsonForTest", '{"combatState":"Opening","rngStream":[0],"enemies":[{"enemyId":"enemy_t78_neg","intents":[]}]}'))).is_false()
	var feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(feedback.find("refused") >= 0).is_true()

	var state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var rng_after := int(scene.call("GetCombatRngStreamPositionForTest"))
	var accepted_after := int(scene.call("GetAcceptedCommandCountForTest"))
	assert_that(state_after).is_equal(state_before)
	assert_that(rng_after).is_equal(rng_before)
	assert_that(accepted_after).is_equal(accepted_before)


# ACC:T78.9
func test_t78_presentation_helpers_do_not_duplicate_runtime_resolution_or_rng_progression() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t78_guard", 30, 30))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t78_guard"))).is_true()
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()

	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var after_card_state := scene.call("CaptureUiStateForTest") as Dictionary
	var after_card_rng := int(scene.call("GetCombatRngStreamPositionForTest"))
	var after_card_accepted := int(scene.call("GetAcceptedCommandCountForTest"))
	var enemy_hp_after_card := int(scene.call("GetEnemyHpForTest", "enemy_t78_guard"))

	scene.call("ApplyHoverPreviewForTest", "t78_guard_preview")
	scene.call("CloseHoverPreviewForTest")
	scene.call("HideTargetInspectionForTest")
	scene.call("ApplyTargetInspectionForTest", "enemy_t78_guard")

	var after_helpers_state := scene.call("CaptureUiStateForTest") as Dictionary
	var after_helpers_rng := int(scene.call("GetCombatRngStreamPositionForTest"))
	var after_helpers_accepted := int(scene.call("GetAcceptedCommandCountForTest"))
	var enemy_hp_after_helpers := int(scene.call("GetEnemyHpForTest", "enemy_t78_guard"))
	assert_that(after_helpers_state).is_equal(after_card_state)
	assert_that(after_helpers_rng).is_equal(after_card_rng)
	assert_that(after_helpers_accepted).is_equal(after_card_accepted)
	assert_that(enemy_hp_after_helpers).is_equal(enemy_hp_after_card)
