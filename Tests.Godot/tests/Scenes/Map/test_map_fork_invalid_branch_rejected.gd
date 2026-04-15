extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class ForkNavigationModel:
	extends RefCounted

	var current_node_id: String = "fork_A"
	var reachable_nodes: Array = ["fork_A", "left_1", "right_1"]
	var _branches := {
		"left": {"next": "left_1", "reachable": ["left_1", "left_2"]},
		"right": {"next": "right_1", "reachable": ["right_1", "right_2"]}
	}

	func choose_branch(branch_id: String) -> bool:
		if not _branches.has(branch_id):
			return false

		var selected: Dictionary = _branches[branch_id]
		current_node_id = selected["next"]
		reachable_nodes = selected["reachable"].duplicate(true)
		return true

# acceptance: ACC:T17.11
func test_invalid_branch_is_rejected_and_state_is_unchanged() -> void:
	var model := ForkNavigationModel.new()
	var before_node := model.current_node_id
	var before_reachable := model.reachable_nodes.duplicate(true)

	var accepted := model.choose_branch("unknown_branch")

	assert_that(accepted).is_false()
	assert_that(model.current_node_id).is_equal(before_node)
	assert_that(model.reachable_nodes).is_equal(before_reachable)

# acceptance: ACC:T17.12
func test_repeated_invalid_branch_attempts_are_consistent_without_progression() -> void:
	var model := ForkNavigationModel.new()

	var first_result := model.choose_branch("bad_id")
	var state_after_first := {
		"current": model.current_node_id,
		"reachable": model.reachable_nodes.duplicate(true)
	}

	var second_result := model.choose_branch("bad_id")
	var state_after_second := {
		"current": model.current_node_id,
		"reachable": model.reachable_nodes.duplicate(true)
	}

	assert_that(first_result).is_false()
	assert_that(second_result).is_false()
	assert_that(state_after_second).is_equal(state_after_first)
	assert_that(state_after_second["current"]).is_equal("fork_A")

# acceptance: ACC:T17.13
func test_invalid_branch_must_not_advance_navigation_state() -> void:
	var model := ForkNavigationModel.new()

	var accepted_valid := model.choose_branch("left")
	assert_that(accepted_valid).is_true()

	var node_before_invalid := model.current_node_id
	var reachable_before_invalid := model.reachable_nodes.duplicate(true)

	var accepted_invalid := model.choose_branch("not_a_branch")

	assert_that(accepted_invalid).is_false()
	assert_that(model.current_node_id).is_equal(node_before_invalid)
	assert_that(model.reachable_nodes).is_equal(reachable_before_invalid)
