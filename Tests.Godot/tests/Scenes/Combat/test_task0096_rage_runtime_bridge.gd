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
