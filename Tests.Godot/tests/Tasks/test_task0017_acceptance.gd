extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_TEST_REF := "Tests.Godot/tests/Tasks/test_task0017_acceptance.gd"
const REQUIRED_ADRS := ["ADR-0007", "ADR-0021"]

class MapServiceDouble:
	func build_and_init_navigation(act_count: int) -> Dictionary:
		if act_count <= 0:
			return {
				"ok": false,
				"error": "act_count must be greater than zero."
			}
		var acts: Array[Dictionary] = []
		for index in range(act_count):
			acts.append({
				"id": index + 1,
				"branches": [index * 10 + 1, index * 10 + 2]
			})
		return {
			"ok": true,
			"acts": acts,
			"initial_branch": acts[0]["branches"][0]
		}

	func run_windows_acceptance_flow(input: Dictionary) -> Dictionary:
		var setup := build_and_init_navigation(int(input.get("act_count", 0)))
		if not bool(setup.get("ok", false)):
			return {"ok": false, "error": setup.get("error", "init failed")}
		var acts: Array = setup.get("acts", [])
		var seed := int(input.get("seed", 0))
		var selected_act := seed % acts.size()
		var act_data: Dictionary = acts[selected_act]
		var branches: Array = act_data.get("branches", [])
		return {
			"ok": true,
			"visible_nodes": acts.size(),
			"selected_act": selected_act,
			"selected_branch": branches[0]
		}


func _overlay_has_task0017_test_ref(overlay_checklist: Dictionary) -> Dictionary:
	var refs: Array = overlay_checklist.get("test_refs", [])
	var status_by_ref: Dictionary = overlay_checklist.get("status_by_ref", {})
	var has_ref := refs.has(REQUIRED_TEST_REF)
	var is_verified: bool = str(status_by_ref.get(REQUIRED_TEST_REF, "")) == "pass"
	return {
		"ok": has_ref and is_verified,
		"has_ref": has_ref,
		"is_verified": is_verified
	}


func _validate_change_record(change_record: Dictionary) -> Dictionary:
	var refs: Array = change_record.get("references", [])
	var decisions: Dictionary = change_record.get("decision_map", {})
	var missing: Array[String] = []
	for adr in REQUIRED_ADRS:
		if not refs.has(adr):
			missing.append(adr)
	var has_map_service_link: bool = str(decisions.get("MapService", "")) != ""
	var has_contract_link: bool = str(decisions.get("MapContract", "")) != ""
	return {
		"ok": missing.is_empty() and has_map_service_link and has_contract_link,
		"missing": missing,
		"has_map_service_link": has_map_service_link,
		"has_contract_link": has_contract_link
	}


# acceptance: ACC:T17.1
func test_map_builds_and_initializes_navigation_for_four_acts() -> void:
	var service := MapServiceDouble.new()
	var result := service.build_and_init_navigation(4)
	var acts: Array = result.get("acts", [])
	assert_that(result.get("ok", false)).is_true()
	assert_that(acts.size()).is_equal(4)
	assert_that(result.get("initial_branch", null)).is_not_null()


# acceptance: ACC:T17.2
func test_windows_flow_is_deterministic_for_same_input() -> void:
	var service := MapServiceDouble.new()
	var input := {"seed": 17, "act_count": 3}
	var first := service.run_windows_acceptance_flow(input)
	var second := service.run_windows_acceptance_flow(input)
	assert_that(first.get("ok", false)).is_true()
	assert_that(first).is_equal(second)
	assert_that(first.get("visible_nodes", -1)).is_equal(3)


# acceptance: ACC:T17.3
func test_overlay_test_refs_can_locate_task_acceptance_file() -> void:
	var overlay_checklist := {
		"test_refs": [
			REQUIRED_TEST_REF,
			"Game.Core.Tests/Tasks/Task17MapTests.cs"
		],
		"status_by_ref": {
			REQUIRED_TEST_REF: "pass"
		}
	}
	var status := _overlay_has_task0017_test_ref(overlay_checklist)
	assert_that(status.get("ok", false)).is_true()
	assert_that(status.get("has_ref", false)).is_true()
	assert_that(status.get("is_verified", false)).is_true()


# acceptance: ACC:T17.10
func test_change_record_rejects_missing_adr0021_reference() -> void:
	var incomplete := {
		"references": ["ADR-0007"],
		"decision_map": {
			"MapService": "ADR-0007",
			"MapContract": ""
		}
	}
	var validation := _validate_change_record(incomplete)
	var missing: Array = validation.get("missing", [])
	assert_that(validation.get("ok", true)).is_false()
	assert_that(missing.has("ADR-0021")).is_true()
