extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RewardSceneSelectionHarness:
	var _success_count: int = 0
	var _round_locked: bool = false
	var _selected_offer_index: int = -1

	func select_offer(offer_index: int) -> bool:
		if _round_locked:
			return false
		if offer_index < 0:
			return false
		_selected_offer_index = offer_index
		return true

	func confirm_offer(offer_index: int) -> bool:
		if _round_locked:
			return false
		if _selected_offer_index < 0:
			return false
		if offer_index != _selected_offer_index:
			return false
		_success_count += 1
		_round_locked = true
		return true

	func can_confirm_offer(offer_index: int) -> bool:
		return not _round_locked and _selected_offer_index == offer_index

	func success_count() -> int:
		return _success_count

# acceptance: ACC:T19.2
func test_allows_only_one_successful_confirm_per_reward_round() -> void:
	var sut := RewardSceneSelectionHarness.new()

	var selected := sut.select_offer(0)
	var can_confirm_selected := sut.can_confirm_offer(0)
	var can_confirm_other := sut.can_confirm_offer(1)
	var first := sut.confirm_offer(0)
	var can_confirm_after_confirm := sut.can_confirm_offer(0)
	var second := sut.confirm_offer(1)
	var third := sut.confirm_offer(2)

	assert_bool(selected).is_true()
	assert_bool(can_confirm_selected).is_true()
	assert_bool(can_confirm_other).is_false()
	assert_bool(first).is_true()
	assert_bool(can_confirm_after_confirm).is_false()
	assert_bool(second).is_false()
	assert_bool(third).is_false()
	assert_int(sut.success_count()).is_equal(1)

# acceptance: ACC:T19.2
func test_disables_other_offers_immediately_after_first_confirm() -> void:
	var sut := RewardSceneSelectionHarness.new()

	var selected := sut.select_offer(0)
	var first := sut.confirm_offer(0)
	var can_confirm_second := sut.can_confirm_offer(1)
	var can_confirm_third := sut.can_confirm_offer(2)

	assert_bool(selected).is_true()
	assert_bool(first).is_true()
	assert_bool(can_confirm_second).is_false()
	assert_bool(can_confirm_third).is_false()

func test_rejects_confirm_without_selection_and_keeps_state_unchanged() -> void:
	var sut := RewardSceneSelectionHarness.new()

	var can_confirm_without_selection := sut.can_confirm_offer(0)
	var confirmed_without_selection := sut.confirm_offer(0)

	assert_bool(can_confirm_without_selection).is_false()
	assert_bool(confirmed_without_selection).is_false()
	assert_int(sut.success_count()).is_equal(0)
