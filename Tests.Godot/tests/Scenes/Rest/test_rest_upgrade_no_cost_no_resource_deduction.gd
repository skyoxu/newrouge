extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RestUpgradeNoCostHarness:
    extends RefCounted

    var gold: int = 120
    var shards: int = 3
    var payment_prompt_visible: bool = false
    var payment_flow_trigger_count: int = 0
    var upgraded: bool = false

    func confirm_free_upgrade() -> void:
        upgraded = true
        # Intentional bug for RED-first: free upgrade still opens payment and deducts gold.
        payment_prompt_visible = true
        payment_flow_trigger_count += 1
        gold -= 25

    func has_payment_entry() -> bool:
        return payment_flow_trigger_count > 0

# acceptance: ACC:T21.4
func test_confirm_free_upgrade_must_not_show_charge_prompt_or_trigger_payment_flow() -> void:
    var sut := RestUpgradeNoCostHarness.new()

    sut.confirm_free_upgrade()

    assert_bool(sut.upgraded).is_true()
    assert_bool(sut.payment_prompt_visible).is_false()
    assert_int(sut.payment_flow_trigger_count).is_equal(0)

# acceptance: ACC:T21.4
func test_confirm_free_upgrade_must_not_deduct_measurable_resources() -> void:
    var sut := RestUpgradeNoCostHarness.new()
    var gold_before := sut.gold
    var shards_before := sut.shards

    sut.confirm_free_upgrade()

    assert_bool(sut.upgraded).is_true()
    assert_int(sut.gold).is_equal(gold_before)
    assert_int(sut.shards).is_equal(shards_before)

# acceptance: ACC:T21.4
func test_confirm_free_upgrade_must_keep_payment_entry_unavailable() -> void:
    var sut := RestUpgradeNoCostHarness.new()

    sut.confirm_free_upgrade()

    assert_bool(sut.has_payment_entry()).is_false()
