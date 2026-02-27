extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const FIXTURE_NAME := "summary-missing-junit.json"

func _repo_root() -> String:
	var current := ProjectSettings.globalize_path("res://").simplify_path()
	for _idx in range(0, 8):
		if FileAccess.file_exists(current.path_join("NewRouge.sln").simplify_path()):
			return current
		current = current.path_join("..").simplify_path()
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()

func _fixture_repo_relative_path(date_token: String) -> String:
	return "logs/ci/%s/quality-gates/task54-fixtures/%s" % [date_token, FIXTURE_NAME]

func _read_text(absolute_path: String) -> String:
	if not FileAccess.file_exists(absolute_path):
		return ""
	var file := FileAccess.open(absolute_path, FileAccess.READ)
	if file == null:
		return ""
	var content := file.get_as_text()
	file.close()
	return content

func _read_fixture_payload(date_token: String) -> Dictionary:
	var repo_relative := _fixture_repo_relative_path(date_token)
	var absolute := _repo_root().path_join(repo_relative).simplify_path()
	var raw := _read_text(absolute)
	if raw == "":
		return {}
	var parsed = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed

func _is_iso_date_token(value: String) -> bool:
	if value.length() != 10:
		return false
	if value.substr(4, 1) != "-" or value.substr(7, 1) != "-":
		return false
	var compact := value.replace("-", "")
	return compact.length() == 8 and compact.is_valid_int()

# ACC:T54.6
func test_junit_artifact_path_uses_expected_logs_location_from_real_fixture() -> void:
	var date_token := Time.get_date_string_from_system()
	var payload := _read_fixture_payload(date_token)
	assert_bool(payload.is_empty()).is_false()
	assert_bool(payload.has("junit_artifact")).is_true()

	var artifact = payload["junit_artifact"]
	assert_bool(typeof(artifact) == TYPE_DICTIONARY).is_true()
	assert_str(str(artifact["path"])).is_equal("logs/e2e/%s/gdunit/junit.xml" % date_token)
	assert_bool(str(artifact["path"]).ends_with("/gdunit/junit.xml")).is_true()
	assert_bool(_is_iso_date_token(date_token)).is_true()
	assert_bool(payload.has("output")).is_true()
	assert_bool(str(payload["output"]).find(date_token) != -1).is_true()

# ACC:T54.6
func test_missing_junit_summary_requires_explicit_reason_from_real_fixture() -> void:
	var date_token := Time.get_date_string_from_system()
	var payload := _read_fixture_payload(date_token)
	assert_bool(payload.is_empty()).is_false()
	assert_bool(payload.has("junit_artifact")).is_true()

	var artifact = payload["junit_artifact"]
	assert_bool(typeof(artifact) == TYPE_DICTIONARY).is_true()
	assert_str(str(artifact["status"])).is_equal("missing")
	assert_bool(not bool(artifact["exists"])).is_true()
	assert_str(str(artifact["missing_reason"])).is_equal("gdunit_results_xml_not_found")
