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
# acceptance anchor: ACC:T73.1
func test_combat_hud_nodes_exist_visible_and_stably_locatable() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	var root := scene as Control

	var required_paths: Array[String] = [
		"HUD/HandTitleLabel",
		"HUD/HandCards",
		"HUD/CardButtonRow",
		"HUD/EnemyStatusPanel",
		"HUD/EnemyStatusPanel/EnemyNameValue",
		"HUD/EnemyStatusPanel/EnemyHpValue",
		"HUD/EnemyStatusPanel/EnemyBlockValue",
		"HUD/EnemyStatusPanel/EnemyStatusValue",
		"HUD/DifficultyValue",
		"HUD/PlayerHpValue",
		"HUD/EnergyValue",
		"HUD/DrawPileValue",
		"HUD/DiscardPileValue",
		"HUD/TurnStateValue",
		"HUD/ActionHintLabel",
		"HUD/TurnControls/PlaySelectedCardButton",
		"HUD/TurnControls/EndTurnButton",
	]
	for path in required_paths:
		var node := root.get_node_or_null(path)
		assert_that(node).is_not_null()
		assert_that((node as CanvasItem).visible).is_true()
		assert_that(str(root.get_path_to(node))).is_equal(path)

	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 24, 24))).is_true()
	var intent_payload := '{"enemyIntents":[{"enemyId":"enemy_m1_slime","iconId":"icon_sword","textKey":"combat.intent.attack_6"},{"enemyId":"enemy_t73_brute","iconId":"icon_shield","textKey":"combat.intent.block_4"}]}'
	assert_that(bool(scene.call("TryApplyEnemyIntentPreviewContractJson", intent_payload))).is_true()
	var targets := scene.call("GetAvailableEnemyTargetIdsForTest") as Array
	assert_that(targets.size()).is_equal(2)
	assert_that(targets.has("enemy_m1_slime")).is_true()
	assert_that(targets.has("enemy_t73_brute")).is_true()
	assert_that(targets.has("enemy_dead")).is_false()
	assert_that(targets.has("enemy_disconnected")).is_false()
	assert_that(targets.has("enemy_locked_slot")).is_false()
	assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(targets.size())
	assert_that(bool(scene.call("IsEnemyIntentPanelVisibleForTest"))).is_true()
	for enemy_id_variant in targets:
		var enemy_id := str(enemy_id_variant)
		assert_that(bool(scene.call("SetTargetEnemyIdForTest", enemy_id))).is_true()
		var enemy_name := (root.get_node("HUD/EnemyStatusPanel/EnemyNameValue") as Label).text.strip_edges()
		var enemy_hp := (root.get_node("HUD/EnemyStatusPanel/EnemyHpValue") as Label).text.strip_edges()
		var enemy_block := (root.get_node("HUD/EnemyStatusPanel/EnemyBlockValue") as Label).text.strip_edges()
		var enemy_status := (root.get_node("HUD/EnemyStatusPanel/EnemyStatusValue") as Label).text.strip_edges()
		var enemy_intent := str(scene.call("GetEnemyIntentDescriptionForTest", enemy_id)).strip_edges()
		assert_that(enemy_name).is_not_empty()
		assert_that(enemy_hp.find("/") >= 0).is_true()
		assert_that(enemy_hp).is_not_equal("0/0")
		assert_that(enemy_block).is_not_empty()
		assert_that(enemy_status).is_not_empty()
		assert_that(bool(scene.call("HasEnemyIntentForTest", enemy_id))).is_true()
		assert_that(enemy_intent).is_not_empty()


# ACC:T75.1
func test_status_surface_shows_explicit_status_labels_stacks_and_feedback_details() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")

	# Ensure deterministic target exists and is selected.
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()

	# Inject two explicit status cards so UI status stacks and feedback details are observable.
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	var injected := bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t75.self_focus","name_key":"card.t75.self_focus.name","description_key":"card.t75.self_focus.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.strength","status_stacks":2}},{"id":"card.t75.enemy_press","name_key":"card.t75.enemy_press.name","description_key":"card.t75.enemy_press.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.weak","status_stacks":1}},{"id":"card.t75.enemy_venom","name_key":"card.t75.enemy_venom.name","description_key":"card.t75.enemy_venom.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.poison","status_stacks":2}},{"id":"card.t75.self_guard","name_key":"card.t75.self_guard.name","description_key":"card.t75.self_guard.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.block","status_stacks":3}},{"id":"card.t75.self_temp","name_key":"card.t75.self_temp.name","description_key":"card.t75.self_temp.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.temp_attack_up","status_stacks":1}},{"id":"card.t75.enemy_brittle","name_key":"card.t75.enemy_brittle.name","description_key":"card.t75.enemy_brittle.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.vulnerable","status_stacks":1}}]}'
	))
	assert_that(injected).is_true()

	# Self status application: verify explicit status ids + stack/value in feedback and player status summary.
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.self_focus","card.t75.self_guard","card.t75.self_temp"],"difficulty":1,"playerHp":80,"energy":4,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	var root := scene as Control
	var card_row := root.get_node("HUD/CardButtonRow") as HBoxContainer
	var self_focus_detail := str((card_row.get_child(0) as Button).text)
	var self_guard_detail := str((card_row.get_child(1) as Button).text)
	var self_temp_detail := str((card_row.get_child(2) as Button).text)
	assert_that(self_focus_detail.find("Apply status.strength +2.") >= 0).is_true()
	assert_that(self_guard_detail.find("Apply status.block +3.") >= 0).is_true()
	assert_that(self_temp_detail.find("Apply status.temp_attack_up +1.") >= 0).is_true()
	assert_that(self_focus_detail.find("card.t75.") < 0).is_true()
	assert_that(self_guard_detail.find("card.t75.") < 0).is_true()
	assert_that(self_temp_detail.find("card.t75.") < 0).is_true()
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var self_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	var player_status_summary := str(scene.call("GetPlayerStatusSummaryForTest"))
	assert_that(self_feedback.find("applied status.temp_attack_up +1 to self") >= 0).is_true()
	assert_that(player_status_summary.find("status.strength:2") >= 0).is_true()
	assert_that(player_status_summary.find("status.block:3") >= 0).is_true()
	assert_that(player_status_summary.find("status.temp_attack_up:1") >= 0).is_true()

	# Enemy status application: verify explicit status ids + stack/value are visible on enemy status surface.
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.enemy_press","card.t75.enemy_venom","card.t75.enemy_brittle"],"difficulty":1,"playerHp":80,"energy":4,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	card_row = root.get_node("HUD/CardButtonRow") as HBoxContainer
	var enemy_press_detail := str((card_row.get_child(0) as Button).text)
	var enemy_venom_detail := str((card_row.get_child(1) as Button).text)
	var enemy_brittle_detail := str((card_row.get_child(2) as Button).text)
	assert_that(enemy_press_detail.find("Apply status.weak +1.") >= 0).is_true()
	assert_that(enemy_venom_detail.find("Apply status.poison +2.") >= 0).is_true()
	assert_that(enemy_brittle_detail.find("Apply status.vulnerable +1.") >= 0).is_true()
	assert_that(enemy_press_detail.find("card.t75.") < 0).is_true()
	assert_that(enemy_venom_detail.find("card.t75.") < 0).is_true()
	assert_that(enemy_brittle_detail.find("card.t75.") < 0).is_true()
	hand = root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	hand.select(0)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	var enemy_status := str(scene.call("GetEnemyStatusForTest", "enemy_m1_slime")).strip_edges()
	var enemy_status_panel := (root.get_node("HUD/EnemyStatusPanel/EnemyStatusValue") as Label).text.strip_edges()
	var enemy_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	for expected_status in ["status.weak +1", "status.poison +2", "status.vulnerable +1"]:
		assert_that(enemy_status.find(expected_status) >= 0).is_true()
		assert_that(enemy_status_panel.find(expected_status) >= 0).is_true()
	assert_that(enemy_feedback.find("applied status.vulnerable +1 to enemy_m1_slime") >= 0).is_true()

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


# ACC:T75.5
func test_status_texts_on_combat_surface_render_in_en_and_zh_cn_without_raw_keys() -> void:
	var scene := _new_scene()
	await get_tree().process_frame

	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	assert_that(bool(scene.call(
		"TryApplyCardDefinitionsContractJsonForTest",
		'{"cards":[{"id":"card.t75.locale_status","name_key":"card.t75.locale_status.name","description_key":"card.t75.locale_status.description","cost":1,"type":"skill","target":"enemy","base_effect":{"rage":1}}]}'
	))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()

	for locale in ["en", "zh-CN"]:
		TranslationServer.set_locale(locale)
		scene.call("RefreshLocaleForTest")
		assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.locale_status"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
		var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
		hand.select(0)
		assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
		var status_panel := str(scene.call("GetEnemyStatusTextForTest")).strip_edges()
		var feedback := str(scene.call("GetLatestFeedbackMessageForTest")).strip_edges()
		assert_that(status_panel).is_not_empty()
		assert_that(status_panel.find("combat.enemy.status.") < 0).is_true()
		assert_that(feedback.find("status.rage +1") >= 0).is_true()
		assert_that(feedback.find("card.t75.") < 0).is_true()

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


# ACC:T72.1
func test_combat_scene_surfaces_actionable_first_run_guidance() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	scene.call("RefreshLocaleForTest")

	var root := scene as Control
	var action_hint := root.get_node("HUD/ActionHintLabel") as Label
	var hand_title := root.get_node("HUD/HandTitleLabel") as Label
	var play_button := root.get_node("HUD/TurnControls/PlaySelectedCardButton") as Button

	assert_that(action_hint.text).is_not_empty()
	assert_that(action_hint.text).is_not_equal("combat.action.hint")
	assert_that(action_hint.text.find("Select a card") >= 0).is_true()
	assert_that(hand_title.text).is_equal("Hand")
	assert_that(play_button.text).is_equal("Play Selected Card")
	assert_that((root.get_node("HUD/TurnControls/StartTurnButton") as Button).visible).is_false()
	assert_that(_read_hand_cards(root.get_node("HUD/HandCards") as ItemList)).is_equal(["Strike", "Defend", "Strike"])
	var card_row := root.get_node("HUD/CardButtonRow") as HBoxContainer
	assert_that(card_row.get_child_count()).is_equal(3)
	var strike_text := (card_row.get_child(0) as Button).text
	var defend_text := (card_row.get_child(1) as Button).text
	assert_that(strike_text.find("Strike") >= 0).is_true()
	assert_that(strike_text.find("Cost 1") >= 0).is_true()
	assert_that(strike_text.find("attack") >= 0).is_true()
	assert_that(strike_text.find("Deal 6 damage.") >= 0).is_true()
	assert_that(strike_text.find("card.warrior.") < 0).is_true()
	assert_that(defend_text.find("Defend") >= 0).is_true()
	assert_that(defend_text.find("Cost 1") >= 0).is_true()
	assert_that(defend_text.find("skill") >= 0).is_true()
	assert_that(defend_text.find("Gain 5 block.") >= 0).is_true()
	assert_that(defend_text.find("card.warrior.") < 0).is_true()

	var enemy_name := root.get_node("HUD/EnemyStatusPanel/EnemyNameValue") as Label
	var enemy_hp := root.get_node("HUD/EnemyStatusPanel/EnemyHpValue") as Label
	var enemy_block := root.get_node("HUD/EnemyStatusPanel/EnemyBlockValue") as Label
	var enemy_status := root.get_node("HUD/EnemyStatusPanel/EnemyStatusValue") as Label
	assert_that(enemy_name.text).is_equal("Slime Scout")
	assert_that(enemy_hp.text).is_equal("32/32")
	assert_that(enemy_block.text).is_equal("0")
	assert_that(enemy_status.text).is_equal("None")
	assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(1)
	assert_that(str(scene.call("GetEnemyIntentDescriptionForTest", "enemy_m1_slime")).find("Attack") >= 0).is_true()

	var accepted_default := bool(scene.call("RequestPlaySelectedCardForTest"))
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(accepted_default).is_true()
	assert_that(latest_feedback).is_not_empty()
	assert_that(latest_feedback.find("Energy -1") >= 0).is_true()

	var hand_list := root.get_node("HUD/HandCards") as ItemList
	hand_list.deselect_all()
	var refused := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(refused).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("Select a card") >= 0).is_true()
	hand_list.select(0)
	var accepted := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(accepted).is_true()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("Energy -1") >= 0).is_true()


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


# ACC:T71.3
func test_playing_existing_cards_updates_visible_combat_state_and_piles() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend","Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))
	assert_that(accepted).is_true()

	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var played_strike := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(played_strike).is_true()

	var state_after_strike := scene.call("CaptureUiStateForTest") as Dictionary
	var strike_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(state_after_strike["hand"]).is_equal(["Defend", "Strike"])
	assert_that(state_after_strike["energy"]).is_equal("2")
	assert_that(state_after_strike["discard"]).is_equal("1")
	assert_that(str(scene.call("GetEnemyHpTextForTest"))).is_equal("26/32")
	assert_that(strike_feedback.find("dealt 6 damage") >= 0).is_true()

	hand.select(0)
	var played_defend := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(played_defend).is_true()

	var state_after_defend := scene.call("CaptureUiStateForTest") as Dictionary
	var defend_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(state_after_defend["hand"]).is_equal(["Strike"])
	assert_that(state_after_defend["energy"]).is_equal("1")
	assert_that(state_after_defend["discard"]).is_equal("2")
	assert_that(str(defend_feedback).find("gained 5 block") >= 0).is_true()


# ACC:T72.2
# ACC:T75.2
func test_mixed_effect_card_updates_hp_block_energy_and_piles_from_definition() -> void:
	var snapshots: Array[Dictionary] = []
	var feedbacks: Array[String] = []
	var player_blocks: Array[int] = []
	var enemy_hps: Array[String] = []
	var discard_counts: Array[int] = []
	var exhaust_counts: Array[int] = []

	for _run in range(2):
		var scene := _new_scene()
		await get_tree().process_frame
		TranslationServer.set_locale("en")
		assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Iron Wave"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()

		var root := scene as Control
		var hand := root.get_node("HUD/HandCards") as ItemList
		hand.select(0)
		var played := bool(scene.call("RequestPlaySelectedCardForTest"))
		assert_that(played).is_true()

		snapshots.append(scene.call("CaptureUiStateForTest") as Dictionary)
		feedbacks.append(str(scene.call("GetLatestFeedbackMessageForTest")))
		player_blocks.append(int(scene.call("GetPlayerBlockForTest")))
		enemy_hps.append(str(scene.call("GetEnemyHpTextForTest")))
		discard_counts.append(int(scene.call("GetDiscardPileCountForTest")))
		exhaust_counts.append(int(scene.call("GetExhaustPileCountForTest")))

	assert_that(enemy_hps[0]).is_equal("27/32")
	assert_that(player_blocks[0]).is_equal(5)
	assert_that(snapshots[0]["energy"]).is_equal("2")
	assert_that(snapshots[0]["draw"]).is_equal("7")
	assert_that(snapshots[0]["discard"]).is_equal("1")
	assert_that(discard_counts[0]).is_equal(1)
	assert_that(exhaust_counts[0]).is_equal(0)
	assert_that(feedbacks[0].find("dealt 5 damage") >= 0).is_true()
	assert_that(feedbacks[0].find("gained 5 block") >= 0).is_true()
	assert_that(feedbacks[0].find("Energy -1") >= 0).is_true()

	# Determinism assertion: same initial state + same action sequence => identical outcomes.
	assert_that(enemy_hps[1]).is_equal(enemy_hps[0])
	assert_that(player_blocks[1]).is_equal(player_blocks[0])
	assert_that(snapshots[1]).is_equal(snapshots[0])
	assert_that(feedbacks[1]).is_equal(feedbacks[0])
	assert_that(discard_counts[1]).is_equal(discard_counts[0])
	assert_that(exhaust_counts[1]).is_equal(exhaust_counts[0])

# ACC:T75.2
func test_status_modifier_cards_keep_deterministic_results_across_repeated_runs() -> void:
	var snapshots: Array[Dictionary] = []
	var feedbacks: Array[String] = []
	var enemy_statuses: Array[String] = []
	var player_statuses: Array[String] = []
	var enemy_hps: Array[String] = []

	for _run in range(2):
		var scene := _new_scene()
		await get_tree().process_frame
		TranslationServer.set_locale("en")
		assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 32, 32))).is_true()
		assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()
		scene.call("ClearCardDefinitionsForTest")
		scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
		assert_that(bool(scene.call(
			"TryApplyCardDefinitionsContractJsonForTest",
			'{"cards":[{"id":"card.t75.mod.block","name_key":"card.t75.mod.block.name","description_key":"card.t75.mod.block.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.block","status_stacks":2}},{"id":"card.t75.mod.temp_up","name_key":"card.t75.mod.temp_up.name","description_key":"card.t75.mod.temp_up.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.temp_attack_up","status_stacks":1}},{"id":"card.t75.mod.temp_down","name_key":"card.t75.mod.temp_down.name","description_key":"card.t75.mod.temp_down.description","cost":1,"type":"skill","target":"self","base_effect":{"status_id":"status.temp_attack_down","status_stacks":1}},{"id":"card.t75.mod.poison","name_key":"card.t75.mod.poison.name","description_key":"card.t75.mod.poison.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.poison","status_stacks":2}},{"id":"card.t75.mod.weak","name_key":"card.t75.mod.weak.name","description_key":"card.t75.mod.weak.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.weak","status_stacks":1}},{"id":"card.t75.mod.vulnerable","name_key":"card.t75.mod.vulnerable.name","description_key":"card.t75.mod.vulnerable.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":1,"status_id":"status.vulnerable","status_stacks":1}}]}'
		))).is_true()
		assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["card.t75.mod.block","card.t75.mod.temp_up","card.t75.mod.temp_down","card.t75.mod.poison","card.t75.mod.weak","card.t75.mod.vulnerable"],"difficulty":1,"playerHp":80,"energy":8,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
		var hand := (scene as Control).get_node("HUD/HandCards") as ItemList
		for _i in range(6):
			hand.select(0)
			assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
			hand = (scene as Control).get_node("HUD/HandCards") as ItemList

		snapshots.append(scene.call("CaptureUiStateForTest") as Dictionary)
		feedbacks.append(str(scene.call("GetLatestFeedbackMessageForTest")))
		enemy_statuses.append(str(scene.call("GetEnemyStatusForTest", "enemy_m1_slime")))
		player_statuses.append(str(scene.call("GetPlayerStatusSummaryForTest")))
		enemy_hps.append(str(scene.call("GetEnemyHpTextForTest")))
		scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)

	assert_that(enemy_statuses[0].find("status.poison +2") >= 0).is_true()
	assert_that(enemy_statuses[0].find("status.weak +1") >= 0).is_true()
	assert_that(enemy_statuses[0].find("status.vulnerable +1") >= 0).is_true()
	assert_that(player_statuses[0].find("status.block:2") >= 0).is_true()
	assert_that(player_statuses[0].find("status.temp_attack_up:1") >= 0).is_true()
	assert_that(player_statuses[0].find("status.temp_attack_down:1") >= 0).is_true()
	assert_that(feedbacks[0].find("applied status.vulnerable +1 to enemy_m1_slime") >= 0).is_true()
	assert_that(enemy_hps[0]).is_not_equal("32/32")

	assert_that(snapshots[1]).is_equal(snapshots[0])
	assert_that(feedbacks[1]).is_equal(feedbacks[0])
	assert_that(enemy_statuses[1]).is_equal(enemy_statuses[0])
	assert_that(player_statuses[1]).is_equal(player_statuses[0])
	assert_that(enemy_hps[1]).is_equal(enemy_hps[0])


# ACC:T72.2
func test_exhaust_routing_is_definition_driven_for_non_power_through_card() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Iron Wave"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	var injected := bool(scene.call("TryApplyCardDefinitionsContractJsonForTest", '{"cards":[{"id":"card.warrior.iron_wave","name_key":"card.warrior.iron_wave.name","description_key":"card.warrior.iron_wave.description","cost":1,"type":"attack","target":"enemy","base_effect":{"damage":5,"block":5,"exhaust":true}}]}'))
	assert_that(injected).is_true()

	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var played := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(played).is_true()
	assert_that(str(scene.call("GetEnemyHpTextForTest"))).is_equal("27/32")
	assert_that(int(scene.call("GetPlayerBlockForTest"))).is_equal(5)
	assert_that(int(scene.call("GetDiscardPileCountForTest"))).is_equal(0)
	assert_that(int(scene.call("GetExhaustPileCountForTest"))).is_equal(1)
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("moved to exhaust") >= 0).is_true()

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


# ACC:T72.8
# ACC:T75.6
# ACC:T75.7
func test_missing_definition_source_rejects_play_and_never_uses_hardcoded_card_fallback() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	scene.call("ClearCardDefinitionsForTest")
	scene.call("SetCardDefinitionAutoLoadEnabledForTest", false)
	scene.call("RefreshLocaleForTest")

	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(0)
	var card_row := root.get_node("HUD/CardButtonRow") as HBoxContainer
	var strike_text := str((card_row.get_child(0) as Button).text)
	assert_that(strike_text).is_equal("Strike")
	assert_that(strike_text.find("Cost ") < 0).is_true()

	var state_before_missing_definition := scene.call("CaptureUiStateForTest") as Dictionary
	var played := bool(scene.call("RequestPlaySelectedCardForTest"))
	var state_after_missing_definition := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(played).is_false()
	assert_that(str(scene.call("GetLatestFeedbackMessageForTest")).find("missing card definition") >= 0).is_true()
	assert_that(state_after_missing_definition).is_equal(state_before_missing_definition)

	scene.call("SetCardDefinitionAutoLoadEnabledForTest", true)


func test_end_turn_resolves_enemy_intent_and_starts_next_player_turn() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	var accepted := bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike","Defend","Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":7,"discardPileCount":0,"turnState":"PlayerTurn"}'))
	assert_that(accepted).is_true()

	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(1)
	assert_that(bool(scene.call("RequestPlaySelectedCardForTest"))).is_true()
	assert_that(bool(scene.call("RequestTurnActionForTest", "end_turn"))).is_true()

	var state_after_end := scene.call("CaptureUiStateForTest") as Dictionary
	var feedback := str(scene.call("GetLatestFeedbackMessageForTest"))
	assert_that(state_after_end["playerHp"]).is_equal("79")
	assert_that(state_after_end["energy"]).is_equal("3")
	assert_that(state_after_end["turnState"]).is_equal("PlayerTurn")
	assert_that(int(scene.call("GetTurnIndexForTest"))).is_equal(2)
	assert_that(state_after_end["hand"]).is_equal(["Strike", "Defend", "Strike"])
	assert_that(state_after_end["discard"]).is_equal("3")
	assert_that(feedback.find("Enemy dealt 1 damage") >= 0).is_true()


# acceptance anchor: ACC:T73.4
func test_dead_enemy_is_removed_from_target_set_and_remaining_enemy_state_stays_deterministic_with_visible_intent() -> void:
	var scene := _new_scene()
	await get_tree().process_frame
	TranslationServer.set_locale("en")
	assert_that(bool(scene.call("TryApplyCoreSnapshotContractJson", '{"handCards":["Strike"],"difficulty":1,"playerHp":80,"energy":3,"drawPileCount":6,"discardPileCount":0,"turnState":"PlayerTurn"}'))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 20, 32))).is_true()
	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_t73_brute", 18, 24))).is_true()
	var intent_payload := '{"enemyIntents":[{"enemyId":"enemy_m1_slime","iconId":"icon_sword","textKey":"combat.intent.attack_6"},{"enemyId":"enemy_t73_brute","iconId":"icon_shield","textKey":"combat.intent.block_4"}]}'
	assert_that(bool(scene.call("TryApplyEnemyIntentPreviewContractJson", intent_payload))).is_true()

	var initial_targets := scene.call("GetAvailableEnemyTargetIdsForTest") as Array
	assert_that(initial_targets.size()).is_equal(2)
	assert_that(initial_targets.has("enemy_m1_slime")).is_true()
	assert_that(initial_targets.has("enemy_t73_brute")).is_true()
	assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(2)
	assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_t73_brute"))).is_true()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_true()

	assert_that(bool(scene.call("SetEnemyHpForTest", "enemy_m1_slime", 0, 32))).is_true()
	var targets_after_kill := scene.call("GetAvailableEnemyTargetIdsForTest") as Array
	assert_that(targets_after_kill.size()).is_equal(1)
	assert_that(str(targets_after_kill[0])).is_equal("enemy_t73_brute")
	assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_m1_slime"))).is_false()
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_m1_slime"))).is_false()
	assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_t73_brute"))).is_true()
	assert_that(str(scene.call("GetEnemyIntentDescriptionForTest", "enemy_t73_brute")).strip_edges()).is_not_empty()
	assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(1)
	assert_that(bool(scene.call("SetTargetEnemyIdForTest", "enemy_t73_brute"))).is_true()

	var root := scene as Control
	var enemy_name := (root.get_node("HUD/EnemyStatusPanel/EnemyNameValue") as Label).text.strip_edges()
	var enemy_hp := (root.get_node("HUD/EnemyStatusPanel/EnemyHpValue") as Label).text.strip_edges()
	var enemy_block := (root.get_node("HUD/EnemyStatusPanel/EnemyBlockValue") as Label).text.strip_edges()
	var enemy_status := (root.get_node("HUD/EnemyStatusPanel/EnemyStatusValue") as Label).text.strip_edges()
	assert_that(enemy_name).is_not_empty()
	assert_that(enemy_hp).is_equal("18/24")
	assert_that(enemy_block).is_not_empty()
	assert_that(enemy_status).is_not_empty()

	var state_after_kill_once := scene.call("CaptureUiStateForTest") as Dictionary
	var targets_after_kill_repeat := scene.call("GetAvailableEnemyTargetIdsForTest") as Array
	var state_after_kill_twice := scene.call("CaptureUiStateForTest") as Dictionary
	assert_that(targets_after_kill_repeat).is_equal(targets_after_kill)
	assert_that(state_after_kill_twice).is_equal(state_after_kill_once)


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
	var root := scene as Control
	var hand := root.get_node("HUD/HandCards") as ItemList
	hand.select(0)

	var requested := bool(scene.call("RequestPlaySelectedCardForTest"))
	assert_that(requested).is_true()

	var dispatched := scene.call("GetDispatchedCommandsForTest") as Array
	var feedback_history := scene.call("GetFeedbackHistoryForTest") as Array
	var latest_feedback := str(scene.call("GetLatestFeedbackMessageForTest"))

	assert_that(dispatched.size()).is_equal(1)
	assert_that(str(dispatched[0])).is_equal("play_card")
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
	assert_that(latest_feedback_after_invalid.find("That action is invalid") >= 0).is_true()


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
