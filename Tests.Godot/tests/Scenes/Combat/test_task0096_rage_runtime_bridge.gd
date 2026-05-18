extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

func _new_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene


# ACC:T96.3
func test_task0096_combat_scene_rage_effect_surface_uses_single_status_contract_path() -> void:
	var summaries: Array[String] = []
	var cards := [
		{"id": "card.t96.rage_shorthand"},
		{"id": "card.t96.rage_explicit"}
	]

	for card in cards:
		var scene := _new_scene()
		await get_tree().process_frame
		TranslationServer.set_locale("en")
		scene.call("ClearCardDefinitionsForTest")
		scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
		assert_that(bool(scene.call(
			"TryApplyCardDefinitionsContractJsonForTest",
			'{"cards":[{"id":"card.t96.rage_shorthand","name_key":"card.t96.rage_shorthand.name","description_key":"card.t96.rage_shorthand.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":2}},{"id":"card.t96.rage_explicit","name_key":"card.t96.rage_explicit.name","description_key":"card.t96.rage_explicit.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.rage","status_stacks":2}}]}'
		))).is_true()
		assert_that(bool(scene.call(
			"TryApplyCoreSnapshotContractJson",
			'{"handCards":["%s"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}' % card["id"]
		))).is_true()
		var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
		hand.select(0)
		assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
		var summary := str(scene.call("GetPlayerStatusSummaryForTest"))
		var feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
		summaries.append(summary)
		assert_that(summary.find("status.rage:2") >= 0).is_true()
		assert_that(feedback.find("status.rage") >= 0).is_true()
		assert_that(feedback.find("+2") >= 0).is_true()
		scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)

	assert_that(summaries[1]).is_equal(summaries[0])

	var reset_scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	reset_scene.call("ClearCardDefinitionsForTest")
	reset_scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(reset_scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t96.rage_reset","name_key":"card.t96.rage_reset.name","description_key":"card.t96.rage_reset.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":2}}]}'
	))).is_true()
	assert_that(bool(reset_scene.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["card.t96.rage_reset"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	var reset_hand := (reset_scene as Control).get_node("HUD/HandCards") as ItemList
	reset_hand.select(0)
	assert_that(bool(reset_scene.call("RequestPlaySelectedCardForTest"))).is_true()
	assert_that(str(reset_scene.call("GetPlayerStatusSummaryForTest")).find("status.rage:2") >= 0).is_true()
	assert_that(bool(reset_scene.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	assert_that(str(reset_scene.call("GetPlayerStatusSummaryForTest")).find("status.rage") >= 0).is_true()
	reset_scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


# ACC:T96.5
func test_task0096_zero_rage_input_keeps_player_visible_status_stable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t96.rage_zero","name_key":"card.t96.rage_zero.name","description_key":"card.t96.rage_zero.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":0}}]}'
	))).is_true()
	assert_that(bool(scene.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["card.t96.rage_zero"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	var status_before := str(scene.call("GetPlayerStatusSummaryForTest"))
	assert_that(status_before).is_equal("")
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var status_after := str(scene.call("GetPlayerStatusSummaryForTest"))
	var feedback := str(scene.call("GetLatestFeedbackMessageForTest")).to_lower()
	assert_that(status_after).is_equal(status_before)
	assert_that(feedback.find("status.rage") < 0).is_true()
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


# ACC:T96.7
# ACC:T96.10
func test_task0096_rage_changes_live_combat_damage_through_shared_play_card_pipeline() -> void:
	var baseline := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	baseline.call("ClearCardDefinitionsForTest")
	baseline.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(baseline.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t96.attack_probe","name_key":"card.t96.attack_probe.name","description_key":"card.t96.attack_probe.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":6}},{"id":"card.t96.rage_then_attack","name_key":"card.t96.rage_then_attack.name","description_key":"card.t96.rage_then_attack.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":2}}]}'
	))).is_true()
	assert_that(bool(baseline.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["card.t96.attack_probe"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	assert_that(bool(baseline.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(baseline.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	var baseline_hand := (baseline as Control).get_node("HUD/HandCards") as ItemList
	baseline_hand.select(0)
	assert_that(bool(baseline.call("RequestPlaySelectedCardForTest"))).is_true()
	var baseline_hp_text := str(baseline.call("GetEnemyHpTextForTest"))
	baseline.call("SetCardDefinitionAutoLoadEnabledForTest", true)

	var boosted := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	boosted.call("ClearCardDefinitionsForTest")
	boosted.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(boosted.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t96.attack_probe","name_key":"card.t96.attack_probe.name","description_key":"card.t96.attack_probe.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":6}},{"id":"card.t96.rage_then_attack","name_key":"card.t96.rage_then_attack.name","description_key":"card.t96.rage_then_attack.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":2}}]}'
	))).is_true()
	assert_that(bool(boosted.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["card.t96.rage_then_attack","card.t96.attack_probe"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	assert_that(bool(boosted.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(boosted.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
	var boosted_hand := (boosted as Control).get_node("HUD/HandCards") as ItemList
	boosted_hand.select(0)
	assert_that(bool(boosted.call("RequestPlaySelectedCardForTest"))).is_true()
	assert_that(str(boosted.call("GetPlayerStatusSummaryForTest")).find("status.rage:2") >= 0).is_true()
	boosted_hand = (boosted as Control).get_node("HUD/HandCards") as ItemList
	boosted_hand.select(0)
	assert_that(bool(boosted.call("RequestPlaySelectedCardForTest"))).is_true()
	var boosted_hp_text := str(boosted.call("GetEnemyHpTextForTest"))
	boosted.call("SetCardDefinitionAutoLoadEnabledForTest", true)

	assert_that(baseline_hp_text).is_equal("26/32")
	assert_that(boosted_hp_text).is_not_equal(baseline_hp_text)
	assert_that(boosted_hp_text).is_equal("24/32")


# ACC:T96.4
func test_task0096_rage_persists_across_end_turn_while_temp_player_status_expires() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t96.rage_bridge","name_key":"card.t96.rage_bridge.name","description_key":"card.t96.rage_bridge.description","cost":1,"type":"skill","target":"self","base_effect":{"rage":2}},{"id":"card.t96.temp_bridge","name_key":"card.t96.temp_bridge.name","description_key":"card.t96.temp_bridge.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.temp_attack_up","status_stacks":1}}]}'
	))).is_true()
	assert_that(bool(scene.call(
		"TryApplyCoreSnapshotContractJson",
		'{"handCards":["card.t96.rage_bridge","card.t96.temp_bridge"],"difficulty":1,"playerHp":80,"energy":4,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'
	))).is_true()
	var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand = (scene as Control).get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()

	var before_end := str(scene.call("GetPlayerStatusSummaryForTest"))
	assert_that(before_end.find("status.rage:2") >= 0).is_true()
	assert_that(before_end.find("status.temp_attack_up:1") >= 0).is_true()

	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()
	var after_end := str(scene.call("GetPlayerStatusSummaryForTest"))
	var end_turn_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))

	assert_that(after_end.find("status.rage:2") >= 0).is_true()
	assert_that(after_end.find("status.temp_attack_up") < 0).is_true()
	assert_that(end_turn_feedback.find("expired status.temp_attack_up on self") >= 0).is_true()
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)
