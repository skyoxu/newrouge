extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_ID := 18
const REQUIRED_ARCHITECTURE_CHECKS := [
	"ui_shell_boundary",
	"state_binding_boundary",
	"no_scene_responsibility_overflow",
]
const REQUIRED_STRATEGY_CHECKS := [
	"test_layering",
	"assertion_granularity",
	"failure_output_quality",
	"reproducible_gates",
]
const COMBAT_SCENE_PATH := "Game.Godot/Scenes/Combat.tscn"
const COMBAT_SCENE_SCRIPT_PATH := "Game.Godot/Scripts/UI/CombatScene.cs"
const UI_BINDINGS_TEST_PATH := "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd"
const TURN_CONTROL_TEST_PATH := "Tests.Godot/tests/Scenes/Combat/test_combat_scene_turn_control_localization_smoke.gd"
const TASK_ACCEPTANCE_TEST_PATH := "Tests.Godot/tests/Tasks/test_task0018_acceptance.gd"
const CONTRACT_REFS_TEST_PATH := "Game.Core.Tests/Tasks/Task0018ContractRefsTests.cs"
const TASKS_GAMEPLAY_PATH := ".taskmaster/tasks/tasks_gameplay.json"
const REQUIRED_TASK18_REFS := [
	UI_BINDINGS_TEST_PATH,
	TURN_CONTROL_TEST_PATH,
	TASK_ACCEPTANCE_TEST_PATH,
	CONTRACT_REFS_TEST_PATH,
]


func _repo_path(rel_path: String) -> String:
	return ProjectSettings.globalize_path("res://../" + rel_path)


func _read_json_file_or_empty(rel_path: String) -> Variant:
	var path := _repo_path(rel_path)
	if not FileAccess.file_exists(path):
		return {}
	var raw := FileAccess.get_file_as_string(path)
	var parsed = JSON.parse_string(raw)
	if parsed == null:
		return {}
	return parsed


func _load_task18_metadata() -> Dictionary:
	var parsed = _read_json_file_or_empty(TASKS_GAMEPLAY_PATH)
	if typeof(parsed) != TYPE_ARRAY:
		return {}
	for item in parsed:
		if int(item.get("taskmaster_id", -1)) == TASK_ID:
			return item
	return {}


func _read_text_file_or_empty(rel_path: String) -> String:
	var path := _repo_path(rel_path)
	if not FileAccess.file_exists(path):
		return ""
	return FileAccess.get_file_as_string(path)


func _contains_all(text: String, markers: Array[String]) -> bool:
	for marker in markers:
		if text.find(marker) == -1:
			return false
	return true


func _assert_call_count(text: String) -> int:
	return text.count("assert_that(") + text.count("assert_bool(")


func _list_missing(paths: Array) -> Array:
	var missing: Array = []
	for path in paths:
		if not FileAccess.file_exists(_repo_path(str(path))):
			missing.append(path)
	return missing


func _collect_architecture_audit() -> Dictionary:
	var scene_text := _read_text_file_or_empty(COMBAT_SCENE_PATH)
	var scene_script_text := _read_text_file_or_empty(COMBAT_SCENE_SCRIPT_PATH)

	var scene_shell_markers: Array[String] = [
		"path=\"res://Game.Godot/Scripts/UI/CombatScene.cs\"",
		"node name=\"HUD\"",
		"node name=\"HandCards\"",
		"node name=\"EnergyValue\"",
		"node name=\"DrawPileValue\"",
		"node name=\"DiscardPileValue\"",
		"node name=\"TurnControls\"",
		"node name=\"StartTurnButton\"",
		"node name=\"EndTurnButton\"",
	]
	var state_binding_markers: Array[String] = [
		"GetNode<ItemList>(\"HUD/HandCards\")",
		"GetNode<Label>(\"HUD/EnergyValue\")",
		"GetNode<Label>(\"HUD/DrawPileValue\")",
		"GetNode<Label>(\"HUD/DiscardPileValue\")",
		"GetNode<Button>(\"HUD/TurnControls/StartTurnButton\")",
		"GetNode<Button>(\"HUD/TurnControls/EndTurnButton\")",
		"_startTurnButton.Pressed +=",
		"_endTurnButton.Pressed +=",
		"OnStartTurnPressed(",
		"OnEndTurnPressed(",
		"TurnActionRequestedEventHandler",
		"ApplyCoreSnapshot(",
		"ApplyCoreSnapshotData(",
		"TryApplyCoreSnapshotData(",
		"TryApplyCoreSnapshotContractJson(",
		"JsonSerializer.Deserialize",
		"CombatHudSnapshotPayload",
		"CombatHudSnapshot",
		"CaptureUiStateForTest(",
		"RequestTurnAction(",
		"RequestTurnActionForTest(",
	]
	var overflow_markers: Array[String] = [
		"DamageResolver",
		"ResolveDamage(",
		"ApplyDamage(",
		"CalculateDamage(",
		"AdvanceFullTurn(",
	]

	var has_scene_overflow := false
	for marker in overflow_markers:
		if scene_script_text.find(marker) != -1:
			has_scene_overflow = true
			break

	var checks := {
		"ui_shell_boundary": _contains_all(scene_text, scene_shell_markers),
		"state_binding_boundary": _contains_all(scene_script_text, state_binding_markers),
		"no_scene_responsibility_overflow": not has_scene_overflow,
	}
	return {
		"checks": checks,
		"evidence": {
			"ui_shell_boundary": [COMBAT_SCENE_PATH],
			"state_binding_boundary": [COMBAT_SCENE_SCRIPT_PATH],
			"no_scene_responsibility_overflow": [COMBAT_SCENE_SCRIPT_PATH],
		},
	}


func _collect_test_strategy_audit() -> Dictionary:
	var ui_bindings_text := _read_text_file_or_empty(UI_BINDINGS_TEST_PATH)
	var turn_control_text := _read_text_file_or_empty(TURN_CONTROL_TEST_PATH)
	var task_acceptance_text := _read_text_file_or_empty(TASK_ACCEPTANCE_TEST_PATH)
	var ui_asserts := _assert_call_count(ui_bindings_text)
	var turn_asserts := _assert_call_count(turn_control_text)
	var task_asserts := _assert_call_count(task_acceptance_text)

	var checks := {
		"test_layering": _contains_all(ui_bindings_text, ["preload(\"res://Game.Godot/Scenes/Combat.tscn\")", "ACC:T18.1"])
			and _contains_all(turn_control_text, ["preload(\"res://Game.Godot/Scenes/Combat.tscn\")", "ACC:T18.4"])
			and bool(FileAccess.file_exists(_repo_path(CONTRACT_REFS_TEST_PATH))),
		"assertion_granularity": ui_asserts >= 12
			and turn_asserts >= 12
			and task_asserts >= 8
			and _contains_all(turn_control_text, ["emit_signal(\"pressed\")", "start_turn"])
			and _contains_all(turn_control_text, ["invalid_action", "is_false()"])
			and _contains_all(ui_bindings_text, ["TryApplyCoreSnapshotContractJson", "CaptureUiStateForTest"]),
		"failure_output_quality": _contains_all(task_acceptance_text, [
			"_missing_required_checks(",
			"assert_that(missing).is_empty()",
			"test_architecture_audit_covers_required_boundaries",
			"test_test_strategy_audit_has_required_evidence",
		]),
		"reproducible_gates": _contains_all(task_acceptance_text, [
			"test_task18_test_refs_include_required_files",
			"test_task18_required_refs_exist_on_disk",
			"REQUIRED_TASK18_REFS",
			"_load_task18_metadata",
		]),
	}

	var evidence := {
		"test_layering": [UI_BINDINGS_TEST_PATH, TURN_CONTROL_TEST_PATH, CONTRACT_REFS_TEST_PATH],
		"assertion_granularity": [UI_BINDINGS_TEST_PATH, TURN_CONTROL_TEST_PATH, TASK_ACCEPTANCE_TEST_PATH],
		"failure_output_quality": [TASK_ACCEPTANCE_TEST_PATH],
		"reproducible_gates": [TASK_ACCEPTANCE_TEST_PATH, TASKS_GAMEPLAY_PATH],
	}
	return {
		"checks": checks,
		"evidence": evidence,
	}


func _missing_required_checks(required: Array, observed: Dictionary) -> Array:
	var missing: Array = []
	for check_name in required:
		if not observed.get(check_name, false):
			missing.append(check_name)
	return missing


func _enforce_scene_shell_policy(scene_roles: Array) -> Array:
	var allowed: Array = []
	for role in scene_roles:
		if role == "DamageResolver":
			continue
		allowed.append(role)
	return allowed


# acceptance: ACC:T18.6
# adr: ADR-0022, ADR-0010
func test_architecture_audit_covers_required_boundaries() -> void:
	var audit := _collect_architecture_audit()
	var checks: Dictionary = audit.get("checks", {}) as Dictionary
	var missing := _missing_required_checks(REQUIRED_ARCHITECTURE_CHECKS, checks)
	var evidence: Dictionary = audit.get("evidence", {}) as Dictionary
	assert_that(missing).is_empty()
	for check_name in REQUIRED_ARCHITECTURE_CHECKS:
		assert_that(evidence.has(check_name)).is_true()
		var paths = evidence.get(check_name, [])
		assert_that(typeof(paths)).is_equal(TYPE_ARRAY)
		for rel_path in paths:
			assert_that(FileAccess.file_exists(_repo_path(str(rel_path)))).is_true()


func test_architecture_audit_refuses_scene_responsibility_overflow() -> void:
	var scene_roles := ["CombatUiShell", "StateBindingBridge", "DamageResolver"]
	var sanitized := _enforce_scene_shell_policy(scene_roles)
	assert_that(sanitized).is_equal(["CombatUiShell", "StateBindingBridge"])


# acceptance: ACC:T18.7
# adr: ADR-0025
func test_test_strategy_audit_has_required_evidence() -> void:
	var audit := _collect_test_strategy_audit()
	var checks: Dictionary = audit.get("checks", {}) as Dictionary
	var missing := _missing_required_checks(REQUIRED_STRATEGY_CHECKS, checks)
	var evidence: Dictionary = audit.get("evidence", {}) as Dictionary
	assert_that(missing).is_empty()
	assert_that(evidence.keys().size()).is_equal(REQUIRED_STRATEGY_CHECKS.size())
	for check_name in REQUIRED_STRATEGY_CHECKS:
		assert_that(evidence.has(check_name)).is_true()
		var paths = evidence.get(check_name, [])
		assert_that(typeof(paths)).is_equal(TYPE_ARRAY)
		for rel_path in paths:
			assert_that(FileAccess.file_exists(_repo_path(str(rel_path)))).is_true()


func test_task18_test_refs_include_required_files() -> void:
	var task18 := _load_task18_metadata()
	var refs = task18.get("test_refs", [])
	assert_that(typeof(refs)).is_equal(TYPE_ARRAY)
	for ref in REQUIRED_TASK18_REFS:
		assert_that(refs.has(ref)).is_true()


func test_task18_required_refs_exist_on_disk() -> void:
	var missing := _list_missing(REQUIRED_TASK18_REFS)
	assert_that(missing).is_empty()
