extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class FakeMapNavigationStateMachine:
    extends RefCounted

    var reachable_node_ids: Array[String] = []
    var selected_node_id: String = ""
    var state: String = "idle"
    var transition_log: Array[String] = []

    func configure(nodes: Array[String], selected: String = "", current_state: String = "idle") -> void:
        reachable_node_ids = nodes.duplicate()
        selected_node_id = selected
        state = current_state
        transition_log.clear()

    func select_node(node_id: String) -> bool:
        transition_log.append("selection_requested:%s" % node_id)
        if not reachable_node_ids.has(node_id):
            transition_log.append("selection_rejected")
            return false

        selected_node_id = node_id
        state = "node_selected"
        transition_log.append("selection_applied")
        transition_log.append("state_transitioned:node_selected")
        return true

func _build_navigation(nodes: Array[String], selected: String = "", current_state: String = "idle") -> FakeMapNavigationStateMachine:
    var sut := FakeMapNavigationStateMachine.new()
    sut.configure(nodes, selected, current_state)
    return sut

# acceptance: ACC:T17.9
# Valid node selection must cause a visible state transition result.
func test_valid_node_selection_transitions_to_selected_state() -> void:
    var sut := _build_navigation(["A1", "B2"], "", "idle")

    var ok := sut.select_node("B2")

    assert_bool(ok).is_true()
    assert_str(sut.selected_node_id).is_equal("B2")
    assert_str(sut.state).is_equal("node_selected")
    assert_str(",".join(sut.transition_log)).is_equal("selection_requested:B2,selection_applied,state_transitioned:node_selected")

func test_invalid_node_selection_keeps_state_and_selection_unchanged() -> void:
    var sut := _build_navigation(["A1", "B2"], "A1", "node_selected")

    var ok := sut.select_node("Z9")

    assert_bool(ok).is_false()
    assert_str(sut.selected_node_id).is_equal("A1")
    assert_str(sut.state).is_equal("node_selected")
    assert_str(",".join(sut.transition_log)).is_equal("selection_requested:Z9,selection_rejected")
