extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

func _new_scene() -> Node:
	var scene := COMBAT_SCENE.instantiate()
	add_child(auto_free(scene))
	return scene

func _read_hand_cards(list: ItemList) -> Array[String]:
	var cards: Array[String] = []
	for index in range(list.get_item_count()):
		cards.append(list.get_item_text(index))
	return cards


# ACC:T18.1
func test_combat_hud_nodes_exist_visible_and_stably_locatable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var root := scene as Control

	var required_paths: Array[String] = [
		"HUD/HandCards",
		"HUD/DifficultyValue",
		"HUD/PlayerHpValue",
		"HUD/EnergyValue",
		"HUD/DrawPileValue",
		"HUD/DiscardPileValue",
		"HUD/TurnStateValue",
		"HUD/TurnControls/StartTurnButton",
		"HUD/TurnControls/EndTurnButton",
	]
	for path in required_paths:
		var node := root.get_node_or_null(path)
		assert_that(node).is_not_null()
		assert_that((node as CanvasItem).visible).is_true()
		assert_that(str(root.get_path_to(node))).is_equal(path)


# ACC:T18.2
# ACC:T64.1
func test_snapshot_binding_matches_hand_energy_draw_and_discard_values() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend","Bash"],"difficulty":4,"playerHp":31,"energy":2,"drawPileCount":17,"discardPileCount":3,"turnState":"PlayerTurn"}'))
	assert_that(accepted).is_true()

	var root := scene as Control
	var hand_list := root.get_node("HUD/HandCards") as ItemList
	var difficulty := root.get_node("HUD/DifficultyValue") as Label
	var player_hp := root.get_node("HUD/PlayerHpValue") as Label
	var energy := root.get_node("HUD/EnergyValue") as Label
	var draw := root.get_node("HUD/DrawPileValue") as Label
	var discard := root.get_node("HUD/DiscardPileValue") as Label
	var turn_state := root.get_node("HUD/TurnStateValue") as Label

	assert_that(_read_hand_cards(hand_list)).is_equal(["Strike", "Defend", "Bash"])
	assert_that(difficulty.text).is_equal("4")
	assert_that(player_hp.text).is_equal("31")
	assert_that(energy.text).is_equal("2")
	assert_that(draw.text).is_equal("17")
	assert_that(discard.text).is_equal("3")
	assert_that(turn_state.text).is_equal("PlayerTurn")

	var intent_payload := '{"enemyIntents":[{"enemyId":"enemy_a","iconId":"icon_sword","textKey":"intent.enemy.slash"}]}'
	var intent_accepted := bool(scene.call("TryApplyEnemyIntentPreviewContractJson", intent_payload))
	assert_that(intent_accepted).is_true()
	var enemy_intent_panel := root.get_node("HUD/EnemyIntentPanel") as VBoxContainer
	var enemy_intent_list := root.get_node("HUD/EnemyIntentPanel/EnemyIntentList") as VBoxContainer
	var intent_row := enemy_intent_list.get_node_or_null("EnemyIntent_enemy_a") as HBoxContainer
	var icon_id_label := intent_row.get_node("IconIdLabel") as Label
	var description_label := intent_row.get_node("DescriptionLabel") as Label
	assert_that(enemy_intent_panel.visible).is_true()
	assert_that(enemy_intent_list.visible).is_true()
	assert_that(intent_row).is_not_null()
	assert_that(icon_id_label.text).is_equal("icon_sword")
	assert_that(description_label.text).is_not_empty()
	assert_that(description_label.text).is_not_equal("intent.enemy.slash")
	assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_a"))).is_true()
	assert_that(str(scene.call("GetEnemyIntentIconIdForTest", "enemy_a"))).is_equal("icon_sword")
	assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(1)


# ACC:T18.3
func test_rebinding_after_state_changes_is_synchronized_and_deterministic() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	var accepted_a := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":2,"playerHp":24,"energy":1,"drawPileCount":10,"discardPileCount":4}'))
	assert_that(accepted_a).is_true()
	var after_a := scene.call("CaptureUiStateForTest") as Dictionary

	var accepted_b := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Zap"],"difficulty":5,"playerHp":18,"energy":4,"drawPileCount":8,"discardPileCount":8}'))
	assert_that(accepted_b).is_true()
	var after_b_once := scene.call("CaptureUiStateForTest") as Dictionary

	var accepted_b_again := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Zap"],"difficulty":5,"playerHp":18,"energy":4,"drawPileCount":8,"discardPileCount":8}'))
	assert_that(accepted_b_again).is_true()
	var after_b_twice := scene.call("CaptureUiStateForTest") as Dictionary

	assert_that(after_a["hand"]).is_equal(["Strike", "Defend"])
	assert_that(after_a["difficulty"]).is_equal("2")
	assert_that(after_a["playerHp"]).is_equal("24")
	assert_that(after_a["energy"]).is_equal("1")
	assert_that(after_b_once["hand"]).is_equal(["Zap"])
	assert_that(after_b_once["difficulty"]).is_equal("5")
	assert_that(after_b_once["playerHp"]).is_equal("18")
	assert_that(after_b_once["energy"]).is_equal("4")
	assert_that(after_b_once["draw"]).is_equal("8")
	assert_that(after_b_once["discard"]).is_equal("8")
	assert_that(after_b_once).is_equal(after_b_twice)


func test_invalid_core_snapshot_payload_is_rejected_and_ui_stays_unchanged() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ApplyCoreSnapshotData", ["Strike"], 2, 10, 1)
	var before_invalid := scene.call("CaptureUiStateForTest") as Dictionary

	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":3,"playerHp":22,"energy":-1,"drawPileCount":9,"discardPileCount":2}'))
	var after_invalid := scene.call("CaptureUiStateForTest") as Dictionary

	assert_that(accepted).is_false()
	assert_that(after_invalid).is_equal(before_invalid)


func test_invalid_snapshot_contract_json_is_rejected_without_ui_mutation() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	scene.call("ApplyCoreSnapshotData", ["Strike"], 2, 10, 1)
	var before_invalid := scene.call("CaptureUiStateForTest") as Dictionary

	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":"invalid-shape","energy":2}'))
	var after_invalid := scene.call("CaptureUiStateForTest") as Dictionary

	assert_that(accepted).is_false()
	assert_that(after_invalid).is_equal(before_invalid)


# ACC:T64.4
func test_turn_controls_flow_keeps_command_feedback_observable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")

	var requested := bool(scene.call("RequestTurnActionForTest", "start_turn"))
	assert_that(requested).is_true()

	var dispatched := scene.call("GetDispatchedCommandsForTest") as Array
	var feedback_history := scene.call("GetFeedbackHistoryForTest") as Array
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))

	assert_that(dispatched.size()).is_equal(1)
	assert_that(str(dispatched[0])).is_equal("start_turn")
	assert_that(feedback_history.size()).is_equal(1)
	assert_that(latest_feedback).is_not_empty()
	assert_that(latest_feedback.find("accepted") >= 0).is_true()

	var rejected := bool(scene.call("RequestTurnActionForTest", "invalid_action"))
	var dispatched_after_invalid := scene.call("GetDispatchedCommandsForTest") as Array
	var feedback_history_after_invalid := scene.call("GetFeedbackHistoryForTest") as Array
	var latest_feedback_after_invalid := str(scene.call("GetLatestFeedbackMessageForTest"))

	assert_that(rejected).is_false()
	assert_that(dispatched_after_invalid.size()).is_equal(1)
	assert_that(feedback_history_after_invalid.size()).is_equal(2)
	assert_that(latest_feedback_after_invalid.find("refused") >= 0).is_true()
	assert_that(latest_feedback_after_invalid.find("invalid action") >= 0).is_true()


# ACC:T64.7
func test_accepted_command_snapshot_flow_updates_visible_energy_state() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")

	var before_accept := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":2,"playerHp":20,"energy":2,"drawPileCount":9,"discardPileCount":1}'))
	assert_that(before_accept).is_true()

	var accepted := bool(scene.call("TryApplyAcceptedStrikeForTest"))
	assert_that(accepted).is_true()

	var captured := scene.call("CaptureUiStateForTest") as Dictionary
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(captured["energy"]).is_equal("1")
	assert_that(latest_feedback.find("accepted") >= 0).is_true()


# ACC:T64.8
func test_accepted_command_feedback_includes_player_visible_result_summary() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")

	var before_accept := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":2,"playerHp":20,"energy":2,"drawPileCount":9,"discardPileCount":1}'))
	assert_that(before_accept).is_true()

	var accepted := bool(scene.call("TryApplyAcceptedStrikeForTest"))
	assert_that(accepted).is_true()

	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(latest_feedback.find("accepted") >= 0).is_true()
	assert_that(latest_feedback.find("Energy -1") >= 0).is_true()
	assert_that(latest_feedback.find("remaining 1") >= 0).is_true()


# ACC:T64.6
func test_hover_and_inspect_keep_hud_state_and_feedback_unchanged() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend"],"difficulty":3,"playerHp":26,"energy":2,"drawPileCount":10,"discardPileCount":4,"turnState":"PlayerTurn"}'))
	assert_that(accepted).is_true()
	scene.call("ApplyCommandFeedbackForTest", "debug_invalid", false)

	var state_before := scene.call("CaptureUiStateForTest") as Dictionary
	var feedback_before := str(scene.call("GetLatestFeedbackMessageForTest"))

	scene.call("ApplyHoverPreviewForTest", "card_1")
	scene.call("ApplyTargetInspectionForTest", "enemy_alpha")

	var state_after := scene.call("CaptureUiStateForTest") as Dictionary
	var feedback_after := str(scene.call("GetLatestFeedbackMessageForTest"))

	assert_that(state_after).is_equal(state_before)
	assert_that(feedback_after).is_equal(feedback_before)
