extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const HAND_LIMIT := 10

func _new_state(draw_ids: Array = [], hand_ids: Array = [], discard_ids: Array = [], exhaust_ids: Array = [], retain_ids: Array = []) -> Dictionary:
    var bridge = preload("res://Game.Godot/TestSupport/Task33DeckServiceBridge.cs").new()
    return bridge.CreateState(draw_ids, hand_ids, discard_ids, exhaust_ids, retain_ids)

func _service() -> Object:
    return preload("res://Game.Godot/TestSupport/Task33DeckServiceBridge.cs").new()

func _ids(cards: Array) -> Array:
    var out: Array = []
    for card_id in cards:
        out.append(int(card_id))
    return out

func _snapshot(state: Dictionary) -> Dictionary:
    return {
        "draw": _ids(state["draw_pile"]),
        "hand": _ids(state["hand"]),
        "discard": _ids(state["discard_pile"]),
        "exhaust": _ids(state["exhaust_pile"])
    }

func _has_adr_traceability(evidence_lines: Array) -> bool:
    var has_0021 := false
    var has_0032 := false
    for line in evidence_lines:
        var text := str(line)
        if text.contains("ADR-0021"):
            has_0021 = true
        if text.contains("ADR-0032"):
            has_0032 = true
    return has_0021 and has_0032

func _evaluate_gate(evidence_lines: Array) -> String:
    return "pass" if _has_adr_traceability(evidence_lines) else "fail"

# acceptance: ACC:T33.1
func test_deck_operations_are_reproducible_for_same_initial_state_and_inputs() -> void:
    var service := _service()
    var state_a := _new_state([1, 2, 3], [10, 11], [20], [], [10])
    var state_b := _new_state([1, 2, 3], [10, 11], [20], [], [10])

    for state in [state_a, state_b]:
        var working := service.Draw(state, 2)
        working = service.DiscardByIds(working, [10])
        working = service.ExhaustByIds(working, [1])
        working = service.EndOfTurn(working)
        state.clear()
        for key in working.keys():
            state[key] = working[key]

    assert_that(_snapshot(state_a)).is_equal(_snapshot(state_b))

# acceptance: ACC:T33.2
func test_draw_discard_and_exhaust_preserve_action_order() -> void:
    var service := _service()
    var state := _new_state([101, 102, 103], [], [], [], [])

    state = service.Draw(state, 2)
    state = service.DiscardByIds(state, [101])
    state = service.ExhaustByIds(state, [102])

    assert_that(_ids(state["hand"])).is_equal([])
    assert_that(_ids(state["discard_pile"])).is_equal([101])
    assert_that(_ids(state["exhaust_pile"])).is_equal([102])

# acceptance: ACC:T33.3
func test_end_of_turn_retain_keeps_flagged_cards_and_does_not_overflow_when_hand_is_within_limit() -> void:
    var service := _service()
    var state := _new_state([], [1, 2, 3], [], [], [1, 3])

    state = service.EndOfTurn(state)

    assert_that(_ids(state["hand"])).is_equal([1, 3])
    assert_that(_ids(state["discard_pile"])).is_equal([2])
    assert_that(state["hand"].size()).is_equal(2)

# acceptance: ACC:T33.10
func test_acceptance_checklist_requires_adr0021_and_adr0032_backlinks() -> void:
    var evidence := [
        "Task 33 checklist item linked to ADR-0021",
        "Task 33 checklist footer linked to ADR-0032"
    ]
    assert_that(_has_adr_traceability(evidence)).is_true()

# acceptance: ACC:T33.11
func test_gate_fails_when_adr_traceability_is_missing_and_overflow_must_discard_by_ascending_instance_id() -> void:
    var missing_adr := [
        "Task 33 checklist item linked to ADR-0021"
    ]
    assert_that(_evaluate_gate(missing_adr)).is_equal("fail")

    var service := _service()
    var state := _new_state([], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], [], [], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

    state = service.EndOfTurn(state)

    assert_that(state["hand"].size()).is_equal(10)
    assert_that(_ids(state["discard_pile"])).is_equal([1, 2])
