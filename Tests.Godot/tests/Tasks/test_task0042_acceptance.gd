extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class MapNodeEntryGate:
    var locked_options: Array = []
    var selected_node_id: String = ""
    var pre_enter_events: Array = []
    var _entry_locked: bool = false
    var _event_counter: int = 0

    func node_pre_enter(options: Array) -> Dictionary:
        if not _entry_locked:
            locked_options = options.duplicate()
            _entry_locked = true

        var event := {
            "order": _event_counter,
            "options": locked_options.duplicate()
        }
        pre_enter_events.append(event)
        _event_counter += 1
        return event

    func try_change_locked_options(new_options: Array) -> bool:
        if _entry_locked:
            return false
        locked_options = new_options.duplicate()
        return true

    func select_node(node_id: String) -> bool:
        if node_id.strip_edges().is_empty():
            return false
        selected_node_id = node_id
        _entry_locked = true
        return true

    func try_backtrack_or_reselect(node_id: String) -> bool:
        if _entry_locked:
            return false
        selected_node_id = node_id
        return true

func _new_gate() -> MapNodeEntryGate:
    return MapNodeEntryGate.new()

# acceptance: ACC:T42.1
func test_node_pre_enter_is_deterministic_and_rejects_late_option_change() -> void:
    var gate := _new_gate()
    var fixed_input := ["city", "market", "camp"]

    var first_event := gate.node_pre_enter(fixed_input)
    var second_event := gate.node_pre_enter(fixed_input)
    var changed := gate.try_change_locked_options(["boss_only"])

    assert_that(first_event["options"]).is_equal(second_event["options"])
    assert_that(changed).is_false()
    assert_that(gate.locked_options).is_equal(fixed_input)

# acceptance: ACC:T42.2
func test_backtrack_or_reselect_is_rejected_after_node_choice() -> void:
    var gate := _new_gate()

    var selected := gate.select_node("node_a")
    var changed := gate.try_backtrack_or_reselect("node_b")

    assert_that(selected).is_true()
    assert_that(changed).is_false()
    assert_that(gate.selected_node_id).is_equal("node_a")

# acceptance: ACC:T42.3
func test_reject_result_is_stable_when_replaying_same_backtrack_input() -> void:
    var first_gate := _new_gate()
    var second_gate := _new_gate()

    first_gate.node_pre_enter(["city", "market", "camp"])
    second_gate.node_pre_enter(["city", "market", "camp"])
    first_gate.select_node("node_a")
    second_gate.select_node("node_a")

    var first_rejected := first_gate.try_backtrack_or_reselect("node_b")
    var second_rejected := second_gate.try_backtrack_or_reselect("node_b")

    assert_that(first_rejected).is_false()
    assert_that(second_rejected).is_false()
    assert_that(first_gate.selected_node_id).is_equal("node_a")
    assert_that(second_gate.selected_node_id).is_equal("node_a")
    assert_that(first_gate.locked_options).is_equal(second_gate.locked_options)
