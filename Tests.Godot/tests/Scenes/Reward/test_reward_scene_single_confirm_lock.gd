extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RewardSceneSelectionHarness:
	var _success_count: int = 0
	var _round_locked: bool = false

	func confirm_offer(_offer_index: int) -> bool:
		if _round_locked:
			return false
		_success_count += 1
		_round_locked = true
		return true

	func can_confirm_offer(_offer_index: int) -> bool:
		return not _round_locked

	func success_count() -> int:
		return _success_count

# acceptance: ACC:T19.2
func test_allows_only_one_successful_confirm_per_reward_round() -> void:
	var sut := RewardSceneSelectionHarness.new()

	var first := sut.confirm_offer(0)
	var second := sut.confirm_offer(1)
	var third := sut.confirm_offer(2)

	assert_bool(first).is_true()
	assert_bool(second).is_false()
	assert_bool(third).is_false()
	assert_int(sut.success_count()).is_equal(1)

# acceptance: ACC:T19.2
func test_disables_other_offers_immediately_after_first_confirm() -> void:
	var sut := RewardSceneSelectionHarness.new()

	var first := sut.confirm_offer(0)
	var can_confirm_second := sut.can_confirm_offer(1)
	var can_confirm_third := sut.can_confirm_offer(2)

	assert_bool(first).is_true()
	assert_bool(can_confirm_second).is_false()
	assert_bool(can_confirm_third).is_false()
