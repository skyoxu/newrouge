extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const COMBAT_SCENE := preload("res://Game.Godot/Scenes/Combat.tscn")

var _translation: Translation

func before_test() -> void:
    _translation = Translation.new()
    _translation.locale = "en"
    _translation.add_message("combat.intent.title", "Enemy Intent")
    _translation.add_message("intent.enemy.slash", "Slash")
    _translation.add_message("intent.enemy.guard", "Guard")
    _translation.add_message("intent.enemy.heavy_strike", "Heavy Strike")
    _translation.add_message("intent.enemy.poison", "Apply Poison")
    _translation.add_message("intent.enemy.bite", "Bite")
    _translation.add_message("intent.enemy.defend", "Defend")
    TranslationServer.add_translation(_translation)
    TranslationServer.set_locale("en")

func after_test() -> void:
    if _translation != null:
        TranslationServer.remove_translation(_translation)
        _translation = null

func _new_scene() -> Node:
    var scene := COMBAT_SCENE.instantiate()
    add_child(auto_free(scene))
    return scene

func _apply_preview(scene: Node, rows: Array) -> bool:
    var payload := {"enemyIntents": rows}
    var encoded := JSON.stringify(payload)
    return bool(scene.call("TryApplyEnemyIntentPreviewContractJson", encoded))

# ACC:T41.1
func test_intent_panel_refresh_replaces_old_turn_data_and_does_not_show_stale_enemy_intent() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var accepted_first := _apply_preview(scene, [
        {"enemyId": "enemy_a", "iconId": "icon_sword", "textKey": "intent.enemy.slash"},
        {"enemyId": "enemy_b", "iconId": "icon_shield", "textKey": "intent.enemy.guard"}
    ])
    assert_that(accepted_first).is_true()

    var accepted_second := _apply_preview(scene, [
        {"enemyId": "enemy_a", "iconId": "icon_shield", "textKey": "intent.enemy.guard"}
    ])
    assert_that(accepted_second).is_true()

    assert_that(scene.call("GetEnemyIntentIconIdForTest", "enemy_a")).is_equal("icon_shield")
    assert_that(scene.call("GetEnemyIntentDescriptionForTest", "enemy_a")).is_equal("Guard")
    # Expected by acceptance: enemy_b should not keep old turn intent.
    assert_that(bool(scene.call("HasEnemyIntentForTest", "enemy_b"))).is_false()

# ACC:T41.2
func test_intent_text_uses_translation_result_not_raw_key() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var accepted := _apply_preview(scene, [
        {"enemyId": "enemy_a", "iconId": "icon_heavy", "textKey": "intent.enemy.heavy_strike"}
    ])
    assert_that(accepted).is_true()

    var rendered_text := str(scene.call("GetEnemyIntentDescriptionForTest", "enemy_a"))
    assert_that(rendered_text).is_equal("Heavy Strike")
    assert_that(rendered_text).is_not_equal("intent.enemy.heavy_strike")
    assert_that(rendered_text.begins_with("intent.")).is_false()

# ACC:T41.3
func test_preview_model_exposes_icon_description_and_turn_for_acceptance_observability() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var accepted := _apply_preview(scene, [
        {"enemyId": "enemy_a", "iconId": "icon_poison", "textKey": "intent.enemy.poison"}
    ])
    assert_that(accepted).is_true()

    assert_that(scene.call("GetEnemyIntentIconIdForTest", "enemy_a")).is_equal("icon_poison")
    assert_that(scene.call("GetEnemyIntentDescriptionForTest", "enemy_a")).is_equal("Apply Poison")
    assert_that(bool(scene.call("HasEnemyIntentIconTextureForTest", "enemy_a"))).is_true()
    assert_that(int(scene.call("GetEnemyIntentTurnForTest", "enemy_a"))).is_equal(1)
    assert_that(int(scene.call("GetEnemyIntentRowCountForTest"))).is_equal(1)
    assert_that(bool(scene.call("IsEnemyIntentPanelVisibleForTest"))).is_true()

# ACC:T41.4
func test_enemy_intent_is_visible_correct_and_updates_on_turn_start() -> void:
    var scene := _new_scene()
    await get_tree().process_frame

    var accepted_first := _apply_preview(scene, [
        {"enemyId": "wolf", "iconId": "icon_bite", "textKey": "intent.enemy.bite"}
    ])
    assert_that(accepted_first).is_true()

    assert_that(bool(scene.call("HasEnemyIntentForTest", "wolf"))).is_true()
    assert_that(scene.call("GetEnemyIntentIconIdForTest", "wolf")).is_equal("icon_bite")
    assert_that(scene.call("GetEnemyIntentDescriptionForTest", "wolf")).is_equal("Bite")
    assert_that(bool(scene.call("HasEnemyIntentIconTextureForTest", "wolf"))).is_true()

    var accepted_second := _apply_preview(scene, [
        {"enemyId": "wolf", "iconId": "icon_shield", "textKey": "intent.enemy.defend"}
    ])
    assert_that(accepted_second).is_true()

    assert_that(scene.call("GetEnemyIntentIconIdForTest", "wolf")).is_equal("icon_shield")
    assert_that(scene.call("GetEnemyIntentDescriptionForTest", "wolf")).is_equal("Defend")
    assert_that(bool(scene.call("HasEnemyIntentIconTextureForTest", "wolf"))).is_true()
    assert_that(int(scene.call("GetEnemyIntentTurnForTest", "wolf"))).is_equal(2)
