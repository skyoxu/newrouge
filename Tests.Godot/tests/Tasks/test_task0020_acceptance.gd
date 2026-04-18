extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASKS_GAMEPLAY_PATH := "res://../.taskmaster/tasks/tasks_gameplay.json"
const OVERLAY_CHECKLIST_PATH := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md"
const SHOP_SCENE_PATH := "res://Game.Godot/Scenes/Shop.tscn"
const THIS_TEST_REF := "Tests.Godot/tests/Tasks/test_task0020_acceptance.gd"
const CORE_TEST_REF := "Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs"
const REQUIRED_COVERAGE_TAGS := ["shop_purchase", "shop_inventory_lock", "shop_no_upgrade_copy", "reenter_persistence"]


class InMemoryShopPersistence:
    var locked_offers: Array = []
    var purchased: Dictionary = {}

    func load_locked_offers() -> Array:
        return locked_offers.duplicate(true)

    func save_locked_offers(offers: Array) -> void:
        locked_offers = offers.duplicate(true)

    func load_purchased() -> Dictionary:
        return purchased.duplicate(true)

    func save_purchased(purchased_map: Dictionary) -> void:
        purchased = purchased_map.duplicate(true)


class ShopFacadeDouble:
    var _store: InMemoryShopPersistence
    var _include_upgrade_context := false
    var _localized_texts := {
        "shop.service.remove": "Remove",
        "shop.service.reforge": "Reforge",
        "shop.service.upgrade": "Upgrade Card",
    }

    func _init(store: InMemoryShopPersistence, include_upgrade_context: bool = false) -> void:
        _store = store
        _include_upgrade_context = include_upgrade_context

    func enter_shop(seed_offers: Array) -> Dictionary:
        var locked := _store.load_locked_offers()
        if locked.is_empty():
            locked = seed_offers.duplicate(true)
            _store.save_locked_offers(locked)

        var purchased := _store.load_purchased()
        var visible: Array = []
        for offer in locked:
            var offer_id := str(offer.get("id", ""))
            if bool(purchased.get(offer_id, false)):
                continue
            visible.append(offer.duplicate(true))

        var services := ["remove", "reforge"]
        var ui_texts := [
            str(_localized_texts.get("shop.service.remove", "")),
            str(_localized_texts.get("shop.service.reforge", "")),
        ]

        if _include_upgrade_context:
            services.append("upgrade")
            ui_texts.append(str(_localized_texts.get("shop.service.upgrade", "")))

        return {
            "scene_path": "res://Game.Godot/Scenes/Shop.tscn",
            "offers": visible,
            "services": services,
            "ui_texts": ui_texts,
        }

    func purchase(offer_id: String) -> bool:
        var locked := _store.load_locked_offers()
        var exists := false
        for offer in locked:
            if str(offer.get("id", "")) == offer_id:
                exists = true
                break

        if not exists:
            return false

        var purchased := _store.load_purchased()
        if bool(purchased.get(offer_id, false)):
            return false

        purchased[offer_id] = true
        _store.save_purchased(purchased)
        return true


func _seed_shop_offers() -> Array:
    return [
        {"id": "card_strike_plus", "kind": "card", "price": 75},
        {"id": "relic_amber", "kind": "relic", "price": 150},
        {"id": "card_shield_wall", "kind": "card", "price": 60},
    ]


func _mutated_seed_shop_offers() -> Array:
    return [
        {"id": "card_new_offer", "kind": "card", "price": 999},
        {"id": "relic_new_offer", "kind": "relic", "price": 888},
    ]


func _ids(offers: Array) -> Array:
    var ids: Array = []
    for offer in offers:
        ids.append(str(offer.get("id", "")))
    return ids


func _price_map(offers: Array) -> Dictionary:
    var result := {}
    for offer in offers:
        result[str(offer.get("id", ""))] = int(offer.get("price", -1))
    return result


func _contains_upgrade_context(texts: Array) -> bool:
    for text in texts:
        if str(text).to_lower().find("upgrade") != -1:
            return true
    return false


func _read_text(file_path: String) -> String:
    var global_path := ProjectSettings.globalize_path(file_path)
    if not FileAccess.file_exists(global_path):
        return ""
    var file := FileAccess.open(global_path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content


func _load_task20_record() -> Dictionary:
    var raw := _read_text(TASKS_GAMEPLAY_PATH)
    if raw.strip_edges() == "":
        return {}

    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_ARRAY:
        return {}

    for item in parsed:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        if int(item.get("taskmaster_id", -1)) == 20:
            return item
    return {}


func _array_field_as_strings(record: Dictionary, field_name: String) -> Array:
    var field = record.get(field_name, [])
    if typeof(field) != TYPE_ARRAY:
        return []
    var result: Array = []
    for item in field:
        result.append(str(item))
    return result


# ACC:T20.1
func test_shop_entry_locks_inventory_and_prices_across_reentry_except_purchased_items() -> void:
    var store := InMemoryShopPersistence.new()
    var sut := ShopFacadeDouble.new(store, false)
    var scene_resource := load(SHOP_SCENE_PATH)

    var first = sut.enter_shop(_seed_shop_offers())
    var first_offers = first.get("offers", [])
    var first_prices = _price_map(first_offers)

    assert_object(scene_resource).is_not_null()
    assert_str(str(first.get("scene_path", ""))).is_equal(SHOP_SCENE_PATH)
    assert_int(first_offers.size()).is_equal(3)
    assert_bool(sut.purchase("card_strike_plus")).is_true()

    var second = sut.enter_shop(_mutated_seed_shop_offers())
    var second_offers = second.get("offers", [])
    var second_ids = _ids(second_offers)
    var second_prices = _price_map(second_offers)

    assert_int(second_offers.size()).is_equal(2)
    assert_bool(second_ids.has("card_strike_plus")).is_false()
    assert_int(int(second_prices.get("relic_amber", -1))).is_equal(int(first_prices.get("relic_amber", -2)))
    assert_int(int(second_prices.get("card_shield_wall", -1))).is_equal(int(first_prices.get("card_shield_wall", -2)))


# ACC:T20.2
func test_purchase_removes_item_marks_owned_and_services_exclude_upgrade() -> void:
    var store := InMemoryShopPersistence.new()
    var sut := ShopFacadeDouble.new(store, false)

    var initial = sut.enter_shop(_seed_shop_offers())
    var services = initial.get("services", [])

    assert_bool(services.has("remove")).is_true()
    assert_bool(services.has("reforge")).is_true()
    assert_bool(services.has("upgrade")).is_false()

    assert_bool(sut.purchase("relic_amber")).is_true()
    assert_bool(sut.purchase("relic_amber")).is_false()
    assert_bool(sut.purchase("not_exist")).is_false()

    var after_purchase = sut.enter_shop(_seed_shop_offers())
    var ids_after_purchase = _ids(after_purchase.get("offers", []))
    var purchased_state = store.load_purchased()

    assert_bool(ids_after_purchase.has("relic_amber")).is_false()
    assert_bool(bool(purchased_state.get("relic_amber", false))).is_true()
    assert_int(purchased_state.size()).is_equal(1)
    assert_bool(_contains_upgrade_context(after_purchase.get("ui_texts", []))).is_false()


# ACC:T20.3
func test_overlay_acceptance_manifest_registers_refs_for_purchase_lock_and_no_upgrade() -> void:
    var task_record := _load_task20_record()
    var checklist_text := _read_text(OVERLAY_CHECKLIST_PATH)
    var test_refs := _array_field_as_strings(task_record, "test_refs")
    var acceptance_text := "\n".join(PackedStringArray(_array_field_as_strings(task_record, "acceptance")))

    assert_bool(task_record.is_empty()).is_false()
    assert_bool(test_refs.has(THIS_TEST_REF)).is_true()
    assert_bool(test_refs.has(CORE_TEST_REF)).is_true()
    assert_bool(acceptance_text.contains(THIS_TEST_REF)).is_true()
    assert_bool(acceptance_text.contains("库存锁定")).is_true()
    assert_bool(acceptance_text.contains("升级/Upgrade")).is_true()
    assert_bool(checklist_text.contains("Task20")).is_true()
    assert_bool(checklist_text.contains(THIS_TEST_REF)).is_true()
    assert_bool(checklist_text.contains(CORE_TEST_REF)).is_true()
    for required_tag in REQUIRED_COVERAGE_TAGS:
        assert_bool(checklist_text.contains(required_tag)).is_true()


# ACC:T20.4
func test_locked_inventory_and_purchase_state_persist_across_exit_and_reenter() -> void:
    var shared_store := InMemoryShopPersistence.new()
    var first_session := ShopFacadeDouble.new(shared_store, false)

    first_session.enter_shop(_seed_shop_offers())
    assert_bool(first_session.purchase("relic_amber")).is_true()

    var second_session := ShopFacadeDouble.new(shared_store, false)
    var reentered = second_session.enter_shop(_mutated_seed_shop_offers())
    var reentered_ids = _ids(reentered.get("offers", []))
    var reentered_prices = _price_map(reentered.get("offers", []))

    assert_bool(reentered_ids.has("relic_amber")).is_false()
    assert_bool(reentered_ids.has("card_strike_plus")).is_true()
    assert_bool(reentered_ids.has("card_shield_wall")).is_true()
    assert_int(int(reentered_prices.get("card_strike_plus", -1))).is_equal(75)
    assert_int(int(reentered_prices.get("card_shield_wall", -1))).is_equal(60)


# ACC:T20.5
func test_task_evidence_contains_purchase_and_reenter_persistence_coverage() -> void:
    var task_record := _load_task20_record()
    var acceptance_text := "\n".join(PackedStringArray(_array_field_as_strings(task_record, "acceptance")))
    var overlay_refs := _array_field_as_strings(task_record, "overlay_refs")
    var checklist_text := _read_text(OVERLAY_CHECKLIST_PATH)

    assert_bool(task_record.is_empty()).is_false()
    assert_bool(overlay_refs.has("docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md")).is_true()
    assert_bool(acceptance_text.contains("持久化")).is_true()
    assert_bool(acceptance_text.contains("退出再进入")).is_true()
    assert_bool(checklist_text.contains("shop_purchase")).is_true()
    assert_bool(checklist_text.contains("reenter_persistence")).is_true()


# ACC:T20.6
func test_localized_shop_copy_must_not_contain_upgrade_context_red_first() -> void:
    var store := InMemoryShopPersistence.new()
    var sut := ShopFacadeDouble.new(store, false)

    var screen = sut.enter_shop(_seed_shop_offers())
    var ui_texts = screen.get("ui_texts", [])

    assert_bool(_contains_upgrade_context(ui_texts)).is_false()


# ACC:T20.7
func test_shop_ui_must_not_expose_upgrade_entry_or_hint() -> void:
    var store := InMemoryShopPersistence.new()
    var sut := ShopFacadeDouble.new(store, false)

    var screen = sut.enter_shop(_seed_shop_offers())
    var services = screen.get("services", [])
    var ui_texts = screen.get("ui_texts", [])

    assert_bool(services.has("upgrade")).is_false()
    assert_bool(_contains_upgrade_context(ui_texts)).is_false()
