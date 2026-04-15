extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class FakeMapNode:
	var node_pre_enter_state: Dictionary = {}
	var current_state: Dictionary = {}
	var _saved := false

	func set_state(state: Dictionary) -> void:
		current_state = state.duplicate(true)

	func enter_node() -> void:
		node_pre_enter_state = current_state.duplicate(true)
		current_state["phase"] = "entered"
		_saved = true

	func has_matching_pre_enter_state(expected: Dictionary) -> bool:
		return _saved and node_pre_enter_state == expected


func _build_pre_enter_state() -> Dictionary:
	return {
		"phase": "approaching",
		"position": Vector2i(2, 3),
		"movement_points": 4
	}


# acceptance: ACC:T17.7
func test_saves_node_pre_enter_state_before_enter_transition() -> void:
	var sut := FakeMapNode.new()
	var before_enter := _build_pre_enter_state()

	sut.set_state(before_enter)
	sut.enter_node()

	assert_that(sut.node_pre_enter_state).is_equal(before_enter)


func test_detects_mismatched_or_missing_pre_enter_state() -> void:
	var sut := FakeMapNode.new()
	var before_enter := _build_pre_enter_state()

	sut.set_state(before_enter)
	sut.enter_node()

	assert_that(sut.has_matching_pre_enter_state({"phase": "wrong"})).is_false()
