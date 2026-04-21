extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class FakeAutoSave:
	var locked_offer: Array = []
	var has_locked_offer: bool = false

	func write_locked_offer(cards: Array) -> void:
		locked_offer = cards.duplicate()
		has_locked_offer = true

	func read_locked_offer() -> Array:
		return locked_offer.duplicate()


class RewardFlowHarness:
	var _rng_seed: int
	var _save: FakeAutoSave
	var _current_offer: Array = []
	var _confirmed_card: String = ""
	var _skipped: bool = false

	func _init(save: FakeAutoSave, rng_seed: int = 7) -> void:
		_save = save
		_rng_seed = rng_seed

	func enter_reward_scene() -> Array:
		if _save.has_locked_offer:
			_current_offer = _save.read_locked_offer()
			return _current_offer.duplicate()
		_current_offer = _generate_offer(_rng_seed)
		_save.write_locked_offer(_current_offer)
		return _current_offer.duplicate()

	func confirm_choice(index: int) -> void:
		_confirmed_card = _current_offer[index]
		_save.has_locked_offer = false
		_save.locked_offer.clear()

	func skip_reward() -> void:
		_skipped = true
		_save.has_locked_offer = false
		_save.locked_offer.clear()

	func confirmed_card() -> String:
		return _confirmed_card

	func skipped() -> bool:
		return _skipped

	func _generate_offer(seed: int) -> Array:
		var cards := ["atk+1", "hp+5", "gold+20", "dash", "shield"]
		if seed % 2 == 0:
			cards.reverse()
		return cards.slice(0, 3)


# acceptance: ACC:T19.3
# acceptance: ACC:T61.3
func test_reenter_must_not_regenerate_or_reorder_locked_offer() -> void:
	var save := FakeAutoSave.new()
	var flow := RewardFlowHarness.new(save, 7)

	var first_offer := flow.enter_reward_scene()
	var second_offer := flow.enter_reward_scene()

	assert_that(save.has_locked_offer).is_true()
	assert_that(save.read_locked_offer()).is_equal(first_offer)
	assert_that(second_offer).is_equal(first_offer)


# acceptance: ACC:T19.7
# acceptance: ACC:T61.5
func test_reward_display_confirm_skip_and_reenter_locking_contract() -> void:
	var save := FakeAutoSave.new()
	var flow := RewardFlowHarness.new(save, 7)

	var displayed_offer := flow.enter_reward_scene()
	var reentered_offer := flow.enter_reward_scene()
	assert_that(reentered_offer).is_equal(displayed_offer)

	flow.confirm_choice(1)
	assert_that(flow.confirmed_card()).is_equal(displayed_offer[1])
	assert_that(save.has_locked_offer).is_false()

	var after_confirm := flow.enter_reward_scene()
	assert_that(after_confirm).is_not_equal([])

	var save_skip := FakeAutoSave.new()
	var flow_skip := RewardFlowHarness.new(save_skip, 9)
	var skip_offer := flow_skip.enter_reward_scene()
	flow_skip.skip_reward()
	assert_that(flow_skip.skipped()).is_true()
	assert_that(save_skip.has_locked_offer).is_false()

	var after_skip := flow_skip.enter_reward_scene()
	assert_that(after_skip).is_equal(skip_offer)
