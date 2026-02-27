extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const SUMMARY_PATH_TEMPLATE := "logs/ci/%s/quality-gates/summary.json"
const TASK_RECORD_PATH_TEMPLATE := "logs/ci/%s/task-0054.json"

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

func _read_repo_json_dict(repo_relative_path: String) -> Dictionary:
	var raw := _read_repo_text(repo_relative_path)
	if raw == "":
		return {}
	var parsed = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed

func _today_token() -> String:
	return Time.get_date_string_from_system()

func _read_today_summary() -> Dictionary:
	return _read_repo_json_dict(SUMMARY_PATH_TEMPLATE % _today_token())

func _read_today_task_record() -> Dictionary:
	return _read_repo_json_dict(TASK_RECORD_PATH_TEMPLATE % _today_token())

func _has_required_suite_state_fields(summary: Dictionary) -> bool:
	if not summary.has("gdunit_suites"):
		return false
	var suites = summary["gdunit_suites"]
	if typeof(suites) != TYPE_DICTIONARY:
		return false
	for name in ["adapters", "security", "integration", "ui"]:
		if not suites.has(name):
			return false
		var item = suites[name]
		if typeof(item) != TYPE_DICTIONARY:
			return false
		if not item.has("selected") or not item.has("executed") or not item.has("state") or not item.has("gate_level"):
			return false
	return true

# ACC:T54.1
func test_windows_with_gdunit_toggle_records_suite_execution_and_gate_type() -> void:
	var summary := _read_today_summary()
	assert_bool(summary.is_empty()).is_false()
	assert_bool(_has_required_suite_state_fields(summary)).is_true()
	assert_bool(summary.has("selected_gdunit_suites")).is_true()

	var selected_raw = summary["selected_gdunit_suites"]
	var selected := PackedStringArray()
	for value in selected_raw:
		selected.append(str(value))

	var suites = summary["gdunit_suites"]
	for name in ["adapters", "security", "integration", "ui"]:
		var item = suites[name]
		assert_bool(bool(item["selected"])).is_equal(selected.has(name))
		assert_str(str(item["state"])).is_equal("executed" if bool(item["selected"]) else "skipped")

# ACC:T54.2
func test_windows_powershell_parse_and_execution_result_maps_to_exit_code() -> void:
	var summary := _read_today_summary()
	var task_record := _read_today_task_record()
	assert_bool(summary.is_empty()).is_false()
	assert_bool(task_record.is_empty()).is_false()
	assert_bool(summary.has("overall_gate_conclusion")).is_true()
	assert_bool(task_record.has("platform")).is_true()
	assert_bool(task_record.has("exit_code")).is_true()

	var overall := str(summary["overall_gate_conclusion"])
	assert_str(str(task_record["platform"])).is_equal("windows-powershell")
	assert_bool(overall == "pass" or overall == "fail").is_true()
	assert_int(int(task_record["exit_code"])).is_equal(0 if overall == "pass" else 1)

# ACC:T54.3
func test_suite_classification_is_hard_soft_per_contract() -> void:
	var summary := _read_today_summary()
	assert_bool(summary.is_empty()).is_false()
	assert_bool(summary.has("gdunit_suites")).is_true()
	assert_bool(summary.has("suites")).is_true()

	var suites = summary["gdunit_suites"]
	assert_str(str(suites["adapters"]["gate_level"])).is_equal("hard")
	assert_str(str(suites["security"]["gate_level"])).is_equal("hard")
	assert_str(str(suites["integration"]["gate_level"])).is_equal("soft")
	assert_str(str(suites["ui"]["gate_level"])).is_equal("soft")

	var grouped = summary["suites"]
	assert_str(str(grouped["adapters_security"]["gate_level"])).is_equal("hard")
	assert_str(str(grouped["integration_ui"]["gate_level"])).is_equal("soft")

# EVIDENCE:T54
func test_summary_exposes_run_or_skipped_status_without_missing_fields() -> void:
	var summary := _read_today_summary()
	assert_bool(summary.is_empty()).is_false()
	assert_bool(_has_required_suite_state_fields(summary)).is_true()
	var suites = summary["gdunit_suites"]
	for name in ["adapters", "security", "integration", "ui"]:
		var state := str(suites[name]["state"])
		assert_bool(state == "executed" or state == "skipped").is_true()
