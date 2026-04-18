extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RewardSceneFlowHarness:
    extends RefCounted

    var _offer_id: String = ""
    var _cards: Array[String] = []
    var _selected_index: int = -1
    var _is_confirmed: bool = false
    var _is_skipped: bool = false
    var _in_scene: bool = false

    func enter_offer(offer_id: String, cards: Array[String]) -> void:
        _offer_id = offer_id
        _cards = cards.duplicate()
        _selected_index = -1
        _is_confirmed = false
        _is_skipped = false
        _in_scene = true

    func show_cards() -> Array[String]:
        return _cards.duplicate()

    func select_choice(index: int) -> bool:
        if not _in_scene:
            return false
        if _is_confirmed or _is_skipped:
            return false
        if index < 0 or index >= _cards.size():
            return false
        _selected_index = index
        return true

    func confirm_selected() -> bool:
        if not _in_scene:
            return false
        if _is_confirmed or _is_skipped:
            return false
        if _selected_index == -1:
            return false
        _is_confirmed = true
        return true

    func skip_offer() -> void:
        if _in_scene and not _is_confirmed:
            _is_skipped = true

    func leave_scene() -> void:
        _in_scene = false

    func reenter_scene() -> void:
        _in_scene = true

    func current_offer_id() -> String:
        return _offer_id

    func selected_index() -> int:
        return _selected_index

    func is_confirmed() -> bool:
        return _is_confirmed

    func is_skipped() -> bool:
        return _is_skipped


func test_reward_offer_displays_three_choices_on_enter() -> void:
    var harness := RewardSceneFlowHarness.new()

    harness.enter_offer("offer_001", ["atk", "hp", "gold"])

    assert_int(harness.show_cards().size()).is_equal(3)
    assert_that(harness.show_cards()[0]).is_equal("atk")
    assert_that(harness.show_cards()[1]).is_equal("hp")
    assert_that(harness.show_cards()[2]).is_equal("gold")


func test_confirm_refuses_without_single_selection_and_keeps_state_unchanged() -> void:
    var harness := RewardSceneFlowHarness.new()

    harness.enter_offer("offer_001", ["atk", "hp", "gold"])
    var confirmed := harness.confirm_selected()

    assert_bool(confirmed).is_false()
    assert_bool(harness.is_confirmed()).is_false()
    assert_int(harness.selected_index()).is_equal(-1)


func test_confirm_locks_single_selected_choice_and_prevents_reselection() -> void:
    var harness := RewardSceneFlowHarness.new()

    harness.enter_offer("offer_001", ["atk", "hp", "gold"])
    var selected := harness.select_choice(1)
    var confirmed := harness.confirm_selected()
    var changed_after_confirm := harness.select_choice(2)

    assert_bool(selected).is_true()
    assert_bool(confirmed).is_true()
    assert_bool(changed_after_confirm).is_false()
    assert_int(harness.selected_index()).is_equal(1)


func test_skip_marks_offer_skipped_and_blocks_confirmation() -> void:
    var harness := RewardSceneFlowHarness.new()

    harness.enter_offer("offer_001", ["atk", "hp", "gold"])
    var selected := harness.select_choice(0)
    harness.skip_offer()
    var confirmed_after_skip := harness.confirm_selected()

    assert_bool(selected).is_true()
    assert_bool(harness.is_skipped()).is_true()
    assert_bool(confirmed_after_skip).is_false()
    assert_bool(harness.is_confirmed()).is_false()


# acceptance: ACC:T19.7
func test_reenter_after_skip_keeps_same_offer_id_until_offer_resolved() -> void:
    var harness := RewardSceneFlowHarness.new()

    harness.enter_offer("offer_001", ["atk", "hp", "gold"])
    harness.skip_offer()
    harness.leave_scene()
    harness.reenter_scene()

    assert_that(harness.current_offer_id()).is_equal("offer_001")
