extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_SCENE := preload("res://Game.Godot/Scenes/Main.tscn")
const EVENT_BUS_SCRIPT := preload("res://Game.Godot/Adapters/EventBusAdapter.cs")
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const SHOP_SCENE := "res://Game.Godot/Scenes/Shop.tscn"

var _bus: Node


func before() -> void:
    _bus = EVENT_BUS_SCRIPT.new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))


func _load_main_on_map() -> Control:
    var main := MAIN_SCENE.instantiate() as Control
    add_child(auto_free(main))
    await get_tree().process_frame

    var nav := main.get_node_or_null("ScreenNavigator")
    assert_object(nav).is_not_null()
    nav.UseFadeTransition = false
    if nav.has_method("ClearRouteHistoryForTest"):
        nav.call("ClearRouteHistoryForTest")
    nav.call("SwitchTo", MAP_SCENE)
    await get_tree().process_frame

    if main.has_method("ResetMapRouteProgressForTest"):
        main.call("ResetMapRouteProgressForTest")
    return main


func _route_history(main: Control) -> Array[String]:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetRouteHistoryForTest"):
        return []

    var route_variant = nav.call("GetRouteHistoryForTest")
    var history: Array[String] = []
    for item in route_variant:
        history.append(str(item))
    return history


func _current_scene_path(main: Control) -> String:
    var nav := main.get_node_or_null("ScreenNavigator")
    if nav == null or not nav.has_method("GetCurrentScenePathForTest"):
        return ""
    return str(nav.call("GetCurrentScenePathForTest"))


func _current_scene_instance(main: Control):
    var root := main.get_node_or_null("ScreenRoot")
    if root == null:
        return null
    if root.get_child_count() == 0:
        return null
    return root.get_child(root.get_child_count() - 1)


func _enter_shop_scene(main: Control) -> Node:
    var enter_result := main.call("StartMapNodeRouteForTest", "shop-01", "shop", true, "") as Dictionary
    assert_bool(bool(enter_result.get("ok", false))).is_true()
    assert_str(str(enter_result.get("scene_path", ""))).is_equal(SHOP_SCENE)
    await get_tree().process_frame

    var shop := _current_scene_instance(main)
    assert_object(shop).is_not_null()
    return shop


func _invoke_shop_method(shop: Node, method_name: String, args: Array = []) -> Dictionary:
    if shop == null or not shop.has_method(method_name):
        return {"ok": false, "reason": "missing-hook:%s" % method_name}

    var result = shop.callv(method_name, args)
    if typeof(result) == TYPE_DICTIONARY:
        return result as Dictionary
    if typeof(result) == TYPE_BOOL:
        return {"ok": bool(result), "reason": ""}
    return {"ok": result != null, "reason": "invalid-result"}


func _extract_string_array(items_variant) -> Array[String]:
    var items: Array[String] = []
    if typeof(items_variant) != TYPE_ARRAY:
        return items

    for item in items_variant:
        items.append(str(item))
    return items


func _visible_offer_ids(shop: Node) -> Array[String]:
    var ids: Array[String] = []
    if shop == null or not shop.has_method("GetVisibleOffersForTest"):
        return ids

    var offers_variant = shop.call("GetVisibleOffersForTest")
    if typeof(offers_variant) != TYPE_ARRAY:
        return ids

    for offer in offers_variant:
        if typeof(offer) != TYPE_DICTIONARY:
            continue
        ids.append(str(offer.get("id", "")))
    return ids


func _count_path(history: Array[String], target: String) -> int:
    var count := 0
    for item in history:
        if item == target:
            count += 1
    return count


func _read_text_result(shop: Node, method_name: String) -> String:
    if shop == null or not shop.has_method(method_name):
        return ""
    return str(shop.call(method_name))


func _select_offer_and_buy(shop: Node, offer_id: String) -> Dictionary:
    var list := shop.get_node_or_null("VBox/OfferList") as ItemList
    var buy := shop.get_node_or_null("VBox/ServicesRow/BuyButton") as Button
    if list == null or buy == null:
        return {"ok": false, "reason": "missing-ui"}

    var offers := _visible_offer_ids(shop)
    var target_index := offers.find(offer_id)
    if target_index < 0:
        return {"ok": false, "reason": "missing-offer"}

    list.emit_signal("item_selected", target_index)
    buy.emit_signal("pressed")
    return {"ok": true, "reason": ""}


# acceptance: ACC:T67.1
# acceptance: ACC:T67.6
# RED-FIRST: this fails until the actual Shop scene binds purchase, remove, reforge, and leave to owned scene behavior.
func test_shop_scene_binds_purchase_remove_reforge_and_leave_to_owned_route_on_actual_scene() -> void:
    assert_bool(ResourceLoader.exists(SHOP_SCENE)).is_true()

    var main := await _load_main_on_map()
    var shop := await _enter_shop_scene(main)

    assert_str(str(shop.scene_file_path)).is_equal(SHOP_SCENE)
    assert_object(shop.get_node_or_null("VBox/OfferList")).is_not_null()
    assert_object(shop.get_node_or_null("VBox/ServicesRow/BuyButton")).is_not_null()
    assert_object(shop.get_node_or_null("VBox/ServicesRow/RemoveButton")).is_not_null()
    assert_object(shop.get_node_or_null("VBox/ServicesRow/ReforgeButton")).is_not_null()
    assert_object(shop.get_node_or_null("VBox/LeaveButton")).is_not_null()

    assert_bool(shop.has_method("SetShopStateForTest")).is_true()
    assert_bool(main.has_method("GetActiveShopStateForScene")).is_true()
    assert_bool(shop.has_method("GetVisibleOffersForTest")).is_true()
    assert_bool(shop.has_method("GetOwnedOfferIdsForTest")).is_true()
    assert_bool(shop.has_method("GetLastRemovedCardIdForTest")).is_true()
    assert_bool(shop.has_method("GetLastReforgedOfferIdForTest")).is_true()
    assert_bool(shop.has_method("PurchaseOfferForTest")).is_true()
    assert_bool(shop.has_method("RemoveCurseForTest")).is_true()
    assert_bool(shop.has_method("ReforgeOfferForTest")).is_true()
    assert_bool(shop.has_method("LeaveShopForTest")).is_true()

    var offers_before := _visible_offer_ids(shop)
    assert_int(offers_before.size()).is_greater(0)
    var target_offer_id := offers_before[0]
    var purchase_ui := _select_offer_and_buy(shop, target_offer_id)
    var remove_result := _invoke_shop_method(shop, "RemoveCurseForTest", ["curse_doubt"])
    var reforge_result := _invoke_shop_method(shop, "ReforgeOfferForTest", ["shop-01_offer_b"])
    var leave_result := _invoke_shop_method(shop, "LeaveShopForTest")
    await get_tree().process_frame

    var offers_after := _visible_offer_ids(shop)
    var owned_ids := _extract_string_array(shop.call("GetOwnedOfferIdsForTest")) if shop.has_method("GetOwnedOfferIdsForTest") else []
    var route_state := main.call("GetActiveShopStateForScene") as Dictionary

    assert_bool(bool(purchase_ui.get("ok", false))).is_true()
    assert_bool(bool(remove_result.get("ok", false))).is_true()
    assert_bool(bool(reforge_result.get("ok", false))).is_true()
    assert_bool(bool(leave_result.get("ok", false))).is_true()
    assert_bool(offers_after.has(target_offer_id)).is_false()
    assert_bool(owned_ids.has(target_offer_id)).is_true()
    assert_str(_read_text_result(shop, "GetLastRemovedCardIdForTest")).is_equal("curse_doubt")
    assert_str(_read_text_result(shop, "GetLastReforgedOfferIdForTest")).is_equal("shop-01_offer_b")
    assert_that(route_state).is_not_null()
    assert_int(int(route_state.get("gold", 0))).is_greater_equal(0)
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(1)


# acceptance: ACC:T67.2
# RED-FIRST: this fails until the actual Shop scene exposes prices, player resources, outcomes, and visible failure feedback.
func test_shop_scene_exposes_observable_state_and_visible_failure_reason_for_insufficient_taken_and_invalid_offer() -> void:
    var main := await _load_main_on_map()
    var shop := await _enter_shop_scene(main)

    assert_bool(shop.has_method("SetShopStateForTest")).is_true()
    assert_bool(shop.has_method("GetVisibleOffersForTest")).is_true()
    assert_bool(shop.has_method("GetPlayerGoldForTest")).is_true()
    assert_bool(shop.has_method("GetOwnedOfferIdsForTest")).is_true()
    assert_bool(shop.has_method("GetLastRemovedCardIdForTest")).is_true()
    assert_bool(shop.has_method("GetVisibleFailureReasonForTest")).is_true()
    assert_bool(shop.has_method("PurchaseOfferForTest")).is_true()

    shop.call("SetShopStateForTest", {
        "gold": 40,
        "offers": [
            {"id": "expensive_relic", "price": 125, "taken": false},
            {"id": "taken_card", "price": 10, "taken": true}
        ],
        "owned_offer_ids": [],
        "removable_cards": [],
        "reforge_targets": [],
        "removed_outcome": ""
    })

    var visible_offers := _visible_offer_ids(shop)
    var too_expensive_result := _invoke_shop_method(shop, "PurchaseOfferForTest", ["expensive_relic"])
    var taken_result := _invoke_shop_method(shop, "PurchaseOfferForTest", ["taken_card"])
    var invalid_offer_result := _invoke_shop_method(shop, "PurchaseOfferForTest", ["missing_offer"])
    var feedback := _read_text_result(shop, "GetVisibleFailureReasonForTest").to_lower()

    assert_int(visible_offers.size()).is_equal(1)
    assert_bool(visible_offers.has("expensive_relic")).is_true()
    assert_bool(visible_offers.has("taken_card")).is_false()
    assert_int(int(shop.call("GetPlayerGoldForTest"))).is_equal(40)
    assert_bool(bool(too_expensive_result.get("ok", false))).is_false()
    assert_str(str(too_expensive_result.get("reason", ""))).is_equal("insufficient-resources")
    assert_bool(bool(taken_result.get("ok", false))).is_false()
    assert_str(str(taken_result.get("reason", ""))).is_equal("offer-already-taken")
    assert_bool(bool(invalid_offer_result.get("ok", false))).is_false()
    assert_str(str(invalid_offer_result.get("reason", ""))).is_equal("invalid-offer")
    assert_int(_extract_string_array(shop.call("GetOwnedOfferIdsForTest")).size()).is_equal(0)
    assert_str(_read_text_result(shop, "GetLastRemovedCardIdForTest")).is_equal("")
    assert_that(feedback).contains("insufficient")
    assert_that(feedback).contains("taken")
    assert_that(feedback).contains("invalid")


# acceptance: ACC:T67.3
# RED-FIRST: this fails until re-entered Shop keeps locked inventory and rejects duplicate purchases with visible feedback.
func test_shop_reenter_keeps_locked_inventory_and_rejects_duplicate_or_invalid_offer_with_visible_feedback() -> void:
    var main := await _load_main_on_map()
    var first_shop := await _enter_shop_scene(main)

    var locked_offer_ids_before := _visible_offer_ids(first_shop)
    assert_int(locked_offer_ids_before.size()).is_greater(0)
    var locked_offer_id := locked_offer_ids_before[0]
    var purchase_ui := _select_offer_and_buy(first_shop, locked_offer_id)
    var duplicate_result := _invoke_shop_method(first_shop, "PurchaseOfferForTest", [locked_offer_id])
    var leave_first := _invoke_shop_method(first_shop, "LeaveShopForTest")
    await get_tree().process_frame

    assert_bool(bool(purchase_ui.get("ok", false))).is_true()
    assert_bool(bool(duplicate_result.get("ok", false))).is_false()
    assert_str(str(duplicate_result.get("reason", ""))).is_equal("offer-already-taken")
    assert_bool(bool(leave_first.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)

    var second_shop := await _enter_shop_scene(main)
    var locked_offer_ids_after := _visible_offer_ids(second_shop)
    var invalid_result := _invoke_shop_method(second_shop, "PurchaseOfferForTest", ["offer_missing"])
    var feedback := _read_text_result(second_shop, "GetVisibleFailureReasonForTest").to_lower()
    var leave_second := _invoke_shop_method(second_shop, "LeaveShopForTest")
    await get_tree().process_frame

    assert_array(locked_offer_ids_after).is_equal(locked_offer_ids_before)
    assert_bool(locked_offer_ids_after.has(locked_offer_id)).is_true()
    assert_bool(bool(invalid_result.get("ok", false))).is_false()
    assert_str(str(invalid_result.get("reason", ""))).is_equal("invalid-offer")
    assert_that(feedback).contains("invalid")
    assert_bool(bool(leave_second.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)


# acceptance: ACC:T67.5
# RED-FIRST: this fails until leaving Shop returns through the same owned route and refuses a second leave without mutating history.
func test_leaving_shop_returns_to_map_through_owned_route_and_second_leave_is_refused_without_history_mutation() -> void:
    var main := await _load_main_on_map()
    var shop := await _enter_shop_scene(main)

    assert_bool(shop.has_method("LeaveShopForTest")).is_true()

    var first_leave := _invoke_shop_method(shop, "LeaveShopForTest")
    await get_tree().process_frame
    var history_after_first := _route_history(main)

    var second_leave := _invoke_shop_method(shop, "LeaveShopForTest")
    await get_tree().process_frame
    var history_after_second := _route_history(main)

    assert_bool(bool(first_leave.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(1)
    assert_bool(history_after_first.has(SHOP_SCENE)).is_true()
    assert_bool(history_after_first.has(MAP_SCENE)).is_true()
    assert_bool(bool(second_leave.get("ok", false))).is_false()
    assert_int(history_after_second.size()).is_equal(history_after_first.size())


# acceptance: ACC:T67.7
# RED-FIRST: this fails until Map-to-Shop entry and Shop-to-Map return use the same route owner model in both directions.
func test_map_to_shop_and_shop_to_map_roundtrip_use_same_route_owner_model_in_both_directions() -> void:
    var main := await _load_main_on_map()

    var first_enter := main.call("StartMapNodeRouteForTest", "shop-01", "shop", true, "") as Dictionary
    await get_tree().process_frame
    var first_shop := _current_scene_instance(main)
    assert_object(first_shop).is_not_null()
    var first_leave := _invoke_shop_method(first_shop, "LeaveShopForTest")
    await get_tree().process_frame

    var second_enter := main.call("StartMapNodeRouteForTest", "shop-02", "shop", true, "") as Dictionary
    await get_tree().process_frame
    var second_shop := _current_scene_instance(main)
    assert_object(second_shop).is_not_null()
    var second_leave := _invoke_shop_method(second_shop, "LeaveShopForTest")
    await get_tree().process_frame

    var history := _route_history(main)

    assert_bool(bool(first_enter.get("ok", false))).is_true()
    assert_bool(bool(first_leave.get("ok", false))).is_true()
    assert_bool(bool(second_enter.get("ok", false))).is_true()
    assert_bool(bool(second_leave.get("ok", false))).is_true()
    assert_str(_current_scene_path(main)).is_equal(MAP_SCENE)
    assert_int(int(main.call("GetMapRouteCompletedNodeCountForTest"))).is_equal(2)
    assert_int(_count_path(history, SHOP_SCENE)).is_equal(2)
    assert_str(history[history.size() - 1]).is_equal(MAP_SCENE)


# acceptance: ACC:T67.4
# RED-FIRST: this fails until runtime Shop behavior excludes upgrade/rest semantics and returns visible rejection feedback.
func test_shop_runtime_excludes_upgrade_and_rest_semantics_with_visible_rejection_feedback() -> void:
    var main := await _load_main_on_map()
    var shop := await _enter_shop_scene(main)

    assert_object(shop.get_node_or_null("VBox/ServicesRow/UpgradeButton")).is_null()
    assert_object(shop.get_node_or_null("VBox/RestButton")).is_null()
    assert_object(shop.get_node_or_null("VBox/CampfireButton")).is_null()
    assert_bool(shop.has_method("UpgradeOfferForTest")).is_false()
    assert_bool(shop.has_method("RestForTest")).is_false()
    assert_bool(shop.has_method("EnterCampfireForTest")).is_false()

    shop.call("SetShopStateForTest", {
        "gold": 150,
        "offers": [
            {"id": "offer_guard", "price": 40},
            {"id": "offer_strike", "price": 60}
        ],
        "owned_offer_ids": []
    })

    var visible_before := _visible_offer_ids(shop)
    var upgrade_like_result := _invoke_shop_method(shop, "PurchaseOfferForTest", ["upgrade_card"])
    var feedback := _read_text_result(shop, "GetVisibleFailureReasonForTest").to_lower()
    var visible_after := _visible_offer_ids(shop)

    assert_bool(bool(upgrade_like_result.get("ok", false))).is_false()
    assert_str(str(upgrade_like_result.get("reason", ""))).is_equal("invalid-offer")
    assert_array(visible_after).is_equal(visible_before)
    assert_that(feedback).contains("invalid")
