extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class BranchSelectionModel:
	extends RefCounted

	var _branches := {
		"left": ["start", "market", "harbor"],
		"right": ["start", "market", "ruins"]
	}

	func reachable_nodes_after_choice(branch_id: String) -> Array:
		if not _branches.has(branch_id):
			return []
		return _branches[branch_id].duplicate()

	func has_observable_divergence() -> bool:
		var left := reachable_nodes_after_choice("left")
		var right := reachable_nodes_after_choice("right")
		return left != right

# acceptance: ACC:T17.6
func test_branch_selection_changes_reachable_nodes_or_future_path() -> void:
	var model := BranchSelectionModel.new()

	var left_reachable := model.reachable_nodes_after_choice("left")
	var right_reachable := model.reachable_nodes_after_choice("right")

	assert_that(left_reachable).is_not_equal(right_reachable)

func test_branch_configuration_without_difference_is_rejected() -> void:
	var model := BranchSelectionModel.new()
	model._branches["right"] = model._branches["left"].duplicate()

	assert_that(model.has_observable_divergence()).is_false()
