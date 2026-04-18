extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RewardSceneDouble:
    var _rng_state: int = 100
    var _current_offer: Array = []
    var _available_pool: Array = ["CardA", "CardB", "CardC", "CardD", "CardE", "CardF"]

    func get_rng_state() -> int:
        return _rng_state

    func get_visible_offer() -> Array:
        return _current_offer.duplicate()

    func enter_reward_scene() -> Array:
        if _current_offer.is_empty():
            _current_offer = _draw_offer()
        return get_visible_offer()

    func skip_offer() -> void:
        # Skip keeps the already locked offer and does not advance RNG state.
        pass

    func _draw_offer() -> Array:
        var start: int = _rng_state % (_available_pool.size() - 2)
        _rng_state += 1
        return [
            _available_pool[start],
            _available_pool[start + 1],
            _available_pool[start + 2]
        ]

# ACC:T19.4
# Skip must not advance RNG state and must preserve the same three-card offer on re-entry.
func test_skip_preserves_offer_and_rng_state_on_reentry() -> void:
    var reward_scene := RewardSceneDouble.new()
    var first_offer: Array = reward_scene.enter_reward_scene()
    var rng_before_skip: int = reward_scene.get_rng_state()

    reward_scene.skip_offer()

    var second_offer: Array = reward_scene.enter_reward_scene()
    var rng_after_reentry: int = reward_scene.get_rng_state()

    assert_that(second_offer).is_equal(first_offer)
    assert_that(rng_after_reentry).is_equal(rng_before_skip)
