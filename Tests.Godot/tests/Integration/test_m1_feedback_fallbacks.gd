extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAP_SCENE := preload("res://Game.Godot/Scenes/Map/Map.tscn")
const SHOP_SCENE := preload("res://Game.Godot/Scenes/Shop.tscn")
const REST_SCENE := preload("res://Game.Godot/Scenes/Rest.tscn")
const HUD_SCENE := preload("res://Game.Godot/Scenes/UI/HUD.tscn")


func _assert_readable(text: String, context: String) -> void:
	var trimmed := text.strip_edges()
	var details := "%s -> '%s'" % [context, trimmed]
	assert_bool(trimmed.is_empty()).override_failure_message("empty feedback: " + details).is_false()
	assert_bool(trimmed.contains("ui.")).override_failure_message("raw ui key in feedback: " + details).is_false()
	assert_bool(trimmed.contains("feedback.")).override_failure_message("raw feedback key in feedback: " + details).is_false()
	assert_bool(trimmed.contains("??")).override_failure_message("unreadable question marks in feedback: " + details).is_false()
	assert_bool(trimmed.contains("\uFFFD")).override_failure_message("replacement character in feedback: " + details).is_false()


func test_map_surface_exposes_visible_feedback_for_route_blocking_completion_and_return() -> void:
	var map: Node = MAP_SCENE.instantiate()
	add_child(auto_free(map))
	await get_tree().process_frame

	assert_bool(map.has_method("ShowRouteFeedbackForTest")).is_true()
	assert_bool(map.has_method("GetFeedbackForTest")).is_true()

	for kind in ["locked_node", "invalid_branch", "completed_node", "returned_to_map", "missing_content"]:
		assert_bool(bool(map.call("ShowRouteFeedbackForTest", kind, "node-a"))).is_true()
		_assert_readable(str(map.call("GetFeedbackForTest")), "map:%s" % kind)


func test_shop_surface_localizes_denials_results_and_leave_route_feedback() -> void:
	var shop: Node = SHOP_SCENE.instantiate()
	add_child(auto_free(shop))
	await get_tree().process_frame

	shop.call("SetShopStateForTest", {
		"gold": 40,
		"offers": [
			{"id": "expensive_card", "price": 125, "taken": false},
			{"id": "taken_card", "price": 10, "taken": true}
		],
		"owned_offer_ids": [],
		"removable_cards": ["curse_doubt"],
		"reforge_targets": ["expensive_card"],
		"removed_outcome": ""
	})

	shop.call("PurchaseOfferForTest", "expensive_card")
	_assert_readable(str(shop.call("GetVisibleFailureReasonForTest")), "shop:insufficient")
	shop.call("PurchaseOfferForTest", "taken_card")
	_assert_readable(str(shop.call("GetVisibleFailureReasonForTest")), "shop:taken")
	shop.call("RemoveCurseForTest", "curse_doubt")
	_assert_readable(str(shop.call("GetLastRemovedOutcomeTextForTest")), "shop:remove")
	shop.call("ReforgeOfferForTest", "expensive_card")
	_assert_readable(str(shop.call("GetLastReforgedOutcomeTextForTest")), "shop:reforge")
	shop.call("ShowLeaveRouteFeedbackForTest")
	_assert_readable(str(shop.call("GetVisibleFailureReasonForTest")), "shop:leave")


func test_rest_surface_exposes_heal_amount_missing_target_and_return_feedback() -> void:
	var rest: Node = REST_SCENE.instantiate()
	add_child(auto_free(rest))
	await get_tree().process_frame

	assert_bool(bool(rest.call("SelectOptionForTest", "heal"))).is_true()
	_assert_readable(str(rest.call("GetFeedbackForTest")), "rest:heal")
	assert_bool(bool(rest.call("ShowMissingTargetFeedbackForTest"))).is_true()
	_assert_readable(str(rest.call("GetFeedbackForTest")), "rest:missing-target")
	assert_bool(bool(rest.call("ShowReturnRouteFeedbackForTest"))).is_true()
	_assert_readable(str(rest.call("GetFeedbackForTest")), "rest:return")


func test_run_summary_surface_uses_localized_labels_for_outcome_progress_and_reason() -> void:
	var hud: Node = HUD_SCENE.instantiate()
	add_child(auto_free(hud))
	await get_tree().process_frame

	assert_bool(hud.has_method("ShowRunSummaryForTest")).is_true()
	hud.call("ShowRunSummaryForTest", "m1_endpoint", 6, "M1 endpoint reached.")

	assert_bool(bool(hud.call("IsRunSummaryVisibleForTest"))).is_true()
	_assert_readable(str(hud.call("GetSummaryOutcomeTextForTest")), "summary:outcome")
	_assert_readable(str(hud.call("GetSummaryNodeProgressTextForTest")), "summary:progress")
	_assert_readable(str(hud.call("GetSummaryReasonTextForTest")), "summary:reason")
