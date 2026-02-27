extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_ID := 54
const TASKS_BACK_PATH := ".taskmaster/tasks/tasks_back.json"
const TASKS_GAMEPLAY_PATH := ".taskmaster/tasks/tasks_gameplay.json"
const REQUIRED_TEST_REFS := [
	"Tests.Godot/tests/ci/test_gdunit_suite_wiring.gd",
	"Game.Core.Tests/Tasks/Task32AcceptanceTests.cs",
	"Game.Core.Tests/Tasks/Task54CiDecisionSyncTests.cs"
]
const REQUIRED_EVIDENCE_REFS := [
	"logs/ci/<date>/task-0054.json",
	"logs/ci/<date>/quality-gates/summary.json",
	"logs/e2e/<date>/gdunit/junit.xml"
]

func _repo_root() -> String:
	var current := ProjectSettings.globalize_path("res://").simplify_path()
	for _idx in range(0, 8):
		if FileAccess.file_exists(current.path_join("NewRouge.sln").simplify_path()):
			return current
		current = current.path_join("..").simplify_path()
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()

func _read_repo_text(repo_relative_path: String) -> String:
	var absolute := _repo_root().path_join(repo_relative_path).simplify_path()
	if not FileAccess.file_exists(absolute):
		return ""
	var file := FileAccess.open(absolute, FileAccess.READ)
	if file == null:
		return ""
	var text := file.get_as_text()
	file.close()
	return text

func _load_task_from_view(view_path: String, task_id: int) -> Dictionary:
	var raw := _read_repo_text(view_path)
	if raw == "":
		return {}
	var parsed = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_ARRAY:
		return {}
	for item in parsed:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if not item.has("taskmaster_id"):
			continue
		if int(item["taskmaster_id"]) == task_id:
			return item
	return {}

func _is_stable_test_ref(path: String) -> bool:
	return path.ends_with(".gd") or path.ends_with(".cs")

func _is_stable_evidence_ref(path: String) -> bool:
	return path.begins_with("logs/") or path.begins_with("docs/")

func _contains_all_refs(values: Array, expected: Array) -> bool:
	for token in expected:
		if not values.has(token):
			return false
	return true

func _assert_wiring(task_item: Dictionary) -> void:
	assert_bool(task_item.has("test_refs")).is_true()
	assert_bool(task_item.has("evidence_refs")).is_true()
	var test_refs = task_item["test_refs"]
	var evidence_refs = task_item["evidence_refs"]
	assert_bool(typeof(test_refs) == TYPE_ARRAY).is_true()
	assert_bool(typeof(evidence_refs) == TYPE_ARRAY).is_true()
	for ref in test_refs:
		assert_bool(_is_stable_test_ref(str(ref))).is_true()
	for ref in evidence_refs:
		assert_bool(_is_stable_evidence_ref(str(ref))).is_true()
	assert_bool(_contains_all_refs(test_refs, REQUIRED_TEST_REFS)).is_true()
	assert_bool(_contains_all_refs(evidence_refs, REQUIRED_EVIDENCE_REFS)).is_true()

func test_task54_ci_wiring_keeps_test_refs_and_evidence_refs_separated() -> void:
	var task_back := _load_task_from_view(TASKS_BACK_PATH, TASK_ID)
	var task_gameplay := _load_task_from_view(TASKS_GAMEPLAY_PATH, TASK_ID)
	assert_bool(task_back.is_empty()).is_false()
	assert_bool(task_gameplay.is_empty()).is_false()
	_assert_wiring(task_back)
	_assert_wiring(task_gameplay)

func test_task54_ci_suite_wiring_contains_expected_core_refs() -> void:
	var task_back := _load_task_from_view(TASKS_BACK_PATH, TASK_ID)
	var task_gameplay := _load_task_from_view(TASKS_GAMEPLAY_PATH, TASK_ID)
	assert_bool(task_back.is_empty()).is_false()
	assert_bool(task_gameplay.is_empty()).is_false()
	var back_test_refs = task_back["test_refs"]
	var gameplay_test_refs = task_gameplay["test_refs"]
	assert_bool(_contains_all_refs(back_test_refs, REQUIRED_TEST_REFS)).is_true()
	assert_bool(_contains_all_refs(gameplay_test_refs, REQUIRED_TEST_REFS)).is_true()
	assert_int(TASK_ID).is_equal(54)
