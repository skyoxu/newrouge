extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

func _collect_observable_failures(resume_snapshot: Dictionary) -> Array:
    var failures: Array = []

    if not resume_snapshot.has("reward") or not resume_snapshot["reward"].has("state"):
        failures.append(_build_failure("reward", "state"))
	if not resume_snapshot.has("shop") or not resume_snapshot["shop"].has("state"):
		failures.append(_build_failure("shop", "state"))
	if not resume_snapshot.has("event") or not resume_snapshot["event"].has("output"):
		failures.append(_build_failure("event", "output"))

    return failures

func _build_failure(scenario: String, field: String) -> Dictionary:
    return {
        "scenario": scenario,
        "field": field,
    }

func _format_failure(failure: Dictionary) -> String:
    return "observable assertion failed at %s.%s" % [failure["scenario"], failure["field"]]

func test_reward_and_shop_diagnostics_include_scenario_and_field() -> void:
	var snapshot := {
		"reward": {},
		"shop": {},
		"event": {"output": {"type": "resume-complete"}}
	}

    var failures := _collect_observable_failures(snapshot)

    assert_that(failures.size()).is_equal(2)
    assert_that(_format_failure(failures[0])).contains("reward.state")
    assert_that(_format_failure(failures[1])).contains("shop.state")

# acceptance: ACC:T44.5
func test_event_observable_assertion_reports_event_output_field() -> void:
	var snapshot := {
		"reward": {"state": {"gold_delta": 5}},
		"shop": {"state": {"inventory_delta": -1}},
		"event": {"emitted": {"name": "reward_applied"}}
	}

    var failures := _collect_observable_failures(snapshot)

    assert_that(failures.size()).is_equal(1)
    assert_that(failures[0]["scenario"]).is_equal("event")
    assert_that(failures[0]["field"]).is_equal("output")
    assert_that(_format_failure(failures[0])).contains("event.output")
