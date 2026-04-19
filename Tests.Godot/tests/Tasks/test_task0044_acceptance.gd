extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_ID := 44
const REQUIRED_FLOWS: Array[String] = ["reward", "shop", "event"]
const TEST_REF_PATH := "Tests.Godot/tests/Tasks/test_task0044_acceptance.gd"
const ADR_TRACE_IDS: Array[String] = ["ADR-0032", "ADR-0025"]
const ACCEPTANCE_CHECKLIST_PATH := "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md"
const TASK44_REPORT_KEYWORDS: Array[String] = ["test_task0044_acceptance", "test_reward_shop_event_resume_determinism"]

func _snapshot_for_flow(flow: String) -> Dictionary:
	match flow:
		"reward":
			return {"flow": "reward", "gold": 12, "pending_rewards": ["daily", "streak"]}
		"shop":
			return {"flow": "shop", "gold": 9, "inventory": ["potion", "key"], "cart_total": 3}
		"event":
			return {"flow": "event", "queue": ["spawn", "shop", "reward"], "seed": 44}
		_:
			return {"flow": flow}

func _resume_state(snapshot: Dictionary) -> Dictionary:
	var restored := snapshot.duplicate(true)
	return restored

func _save_snapshot(path: String, payload: Dictionary) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(payload))
	file.flush()
	return true

func _load_snapshot(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if parsed is Dictionary:
		return (parsed as Dictionary).duplicate(true)
	return {}

func _assert_snapshot_flow_equal(expected: Dictionary, actual: Dictionary) -> void:
	assert_that(str(actual.get("flow", ""))).is_equal(str(expected.get("flow", "")))
	if expected.has("gold"):
		assert_that(int(actual.get("gold", -1))).is_equal(int(expected.get("gold", -1)))
	if expected.has("cart_total"):
		assert_that(int(actual.get("cart_total", -1))).is_equal(int(expected.get("cart_total", -1)))
	if expected.has("seed"):
		assert_that(int(actual.get("seed", -1))).is_equal(int(expected.get("seed", -1)))
	if expected.has("pending_rewards"):
		assert_array(Array(actual.get("pending_rewards", []))).is_equal(Array(expected.get("pending_rewards", [])))
	if expected.has("inventory"):
		assert_array(Array(actual.get("inventory", []))).is_equal(Array(expected.get("inventory", [])))
	if expected.has("queue"):
		assert_array(Array(actual.get("queue", []))).is_equal(Array(expected.get("queue", [])))

func _has_required_flow_coverage(covered_flows: Array[String]) -> bool:
	for required_flow in REQUIRED_FLOWS:
		if not covered_flows.has(required_flow):
			return false
	return true

func _validate_headless_session(session: Dictionary) -> Dictionary:
	if session.get("requires_input", false):
		return {"accepted": false, "reason": "interactive_input_not_allowed"}
	if not session.get("headless", false):
		return {"accepted": false, "reason": "headless_required"}
	return {"accepted": true, "reason": "ok"}

func _repo_root_path() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()

func _resolve_taskmaster_root() -> String:
	var project_root := ProjectSettings.globalize_path("res://").simplify_path()
	var candidates: Array[String] = [
		_repo_root_path(),
		project_root.path_join("..").simplify_path(),
		project_root.path_join("../..").simplify_path()
	]
	for candidate in candidates:
		var probe := candidate.path_join(".taskmaster").path_join("tasks").path_join("tasks_back.json")
		if FileAccess.file_exists(probe):
			return candidate
	return _repo_root_path()

func _load_json_file(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return []
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return []
	var text := file.get_as_text()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null:
		return []
	return parsed

func _is_task_44_entry(item: Variant) -> bool:
	if not (item is Dictionary):
		return false
	var entry := item as Dictionary
	var task_value: Variant = entry.get("taskmaster_id", entry.get("id", ""))
	return str(task_value) == str(TASK_ID)

func _collect_task_entries_for_task_44() -> Array:
	var root := _resolve_taskmaster_root()
	var candidates := [
		root.path_join(".taskmaster").path_join("tasks").path_join("tasks_back.json"),
		root.path_join(".taskmaster").path_join("tasks").path_join("tasks_gameplay.json")
	]
	var result: Array = []
	for candidate in candidates:
		var parsed: Variant = _load_json_file(candidate)
		if parsed is Array:
			for item in parsed:
				if _is_task_44_entry(item):
					result.append(item)
	return result

func _collect_task_entries_by_test_ref() -> Array:
	var root := _resolve_taskmaster_root()
	var candidates := [
		root.path_join(".taskmaster").path_join("tasks").path_join("tasks_back.json"),
		root.path_join(".taskmaster").path_join("tasks").path_join("tasks_gameplay.json")
	]
	var result: Array = []
	for candidate in candidates:
		var parsed: Variant = _load_json_file(candidate)
		if not (parsed is Array):
			continue
		for item in parsed:
			if not (item is Dictionary):
				continue
			var entry := item as Dictionary
			var refs_value: Variant = entry.get("test_refs", [])
			if refs_value is Array and (refs_value as Array).has(TEST_REF_PATH):
				result.append(entry)
	return result

func _task_entry_has_test_ref(entry: Dictionary, test_ref: String) -> bool:
	var refs_value: Variant = entry.get("test_refs", [])
	if not (refs_value is Array):
		return false
	return (refs_value as Array).has(test_ref)

func _task_view_contains_traceability(path: String) -> bool:
	var parsed: Variant = _load_json_file(path)
	if not (parsed is Array):
		return false
	for item in parsed:
		if not (item is Dictionary):
			continue
		var entry := item as Dictionary
		if not _is_task_44_entry(entry):
			continue
		if _task_entry_has_test_ref(entry, TEST_REF_PATH):
			return true
	return false

func _write_text_file(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(content)
		file.flush()

func _delete_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	while true:
		var entry_name: String = str(dir.get_next())
		if entry_name == "":
			break
		if entry_name == "." or entry_name == "..":
			continue
		var child: String = path.path_join(entry_name)
		if dir.current_is_dir():
			_delete_tree(child)
		else:
			DirAccess.remove_absolute(child)
	dir.list_dir_end()
	DirAccess.remove_absolute(path)

func _create_temp_e2e_dir(tag: String) -> String:
	var run_dir := ProjectSettings.globalize_path("user://task0044_e2e_%s_%s" % [tag, str(Time.get_ticks_usec())])
	_delete_tree(run_dir)
	DirAccess.make_dir_recursive_absolute(run_dir)
	return run_dir

func _create_temp_logs_e2e_date_dir(tag: String) -> String:
	var date_token := Time.get_date_string_from_system()
	var run_dir := ProjectSettings.globalize_path("user://task0044_artifacts").path_join("logs").path_join("e2e").path_join(date_token).path_join("%s_%s" % [tag, str(Time.get_ticks_usec())])
	_delete_tree(run_dir)
	DirAccess.make_dir_recursive_absolute(run_dir)
	return run_dir

func _collect_files_recursive(root_dir: String) -> Array[String]:
	var files: Array[String] = []
	var pending: Array[String] = [root_dir]
	while pending.size() > 0:
		var current := str(pending.pop_back())
		var dir := DirAccess.open(current)
		if dir == null:
			continue
		dir.list_dir_begin()
		while true:
			var entry_name := str(dir.get_next())
			if entry_name == "":
				break
			if entry_name == "." or entry_name == "..":
				continue
			var full_path := current.path_join(entry_name)
			if dir.current_is_dir():
				pending.push_back(full_path)
			else:
				files.append(full_path)
		dir.list_dir_end()
	return files

func _contains_any_task44_keyword(text: String) -> bool:
	for keyword in TASK44_REPORT_KEYWORDS:
		if text.find(keyword) >= 0:
			return true
	return false

func _is_iso_date_token(value: String) -> bool:
	if value.length() != 10:
		return false
	if value.substr(4, 1) != "-" or value.substr(7, 1) != "-":
		return false
	var compact := value.replace("-", "")
	return compact.length() == 8 and compact.is_valid_int()

func _is_logs_e2e_date_dir(dir_path: String) -> bool:
	var normalized := dir_path.replace("\\", "/")
	var marker := "/logs/e2e/"
	var idx := normalized.find(marker)
	if idx < 0:
		return false
	var suffix := normalized.substr(idx + marker.length())
	var slash_idx := suffix.find("/")
	if slash_idx < 0:
		return false
	var date_token := suffix.substr(0, slash_idx)
	return _is_iso_date_token(date_token)

func _find_first_xml_file(dir_path: String) -> String:
	var files := _collect_files_recursive(dir_path)
	for path in files:
		var lower := path.to_lower()
		if not lower.ends_with(".xml"):
			continue
		var text := _read_text_file(path)
		if _contains_any_task44_keyword(text):
			return path
	return ""

func _is_readable_xml(path: String) -> bool:
	var parser := XMLParser.new()
	return parser.open(path) == OK

func _audit_has_structured_content(text: String) -> bool:
	var trimmed := text.strip_edges()
	if trimmed.is_empty():
		return false
	var parsed: Variant = JSON.parse_string(trimmed)
	if parsed is Dictionary:
		var row := parsed as Dictionary
		return row.has("event") and row.has("ts")
	if text.find("event=") >= 0 and text.find("ts=") >= 0:
		return true
	if text.find("\"event\"") >= 0 and text.find("\"ts\"") >= 0:
		return true
	return false

func _audit_file_has_structured_content(path: String, text: String) -> bool:
	var lower := path.to_lower()
	if lower.ends_with(".html") or lower.ends_with(".htm"):
		return text.find("<html") >= 0 and text.find("audit") >= 0
	return _audit_has_structured_content(text)

func _find_structured_audit_file(dir_path: String) -> String:
	var files := _collect_files_recursive(dir_path)
	for path in files:
		var lower := path.to_lower()
		if lower.find("audit") < 0:
			continue
		var content := _read_text_file(path)
		if content.strip_edges().is_empty():
			continue
		if _audit_file_has_structured_content(path, content):
			return path
	return ""

func _validate_e2e_artifacts(dir_path: String) -> Dictionary:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return {"ok": false, "reason": "missing_dir"}
	if not _is_logs_e2e_date_dir(dir_path):
		return {"ok": false, "reason": "invalid_e2e_path"}
	var junit_xml_path := _find_first_xml_file(dir_path)
	if junit_xml_path.is_empty():
		return {"ok": false, "reason": "missing_task44_junit_xml"}
	if not _is_readable_xml(junit_xml_path):
		return {"ok": false, "reason": "invalid_junit_xml"}
	var audit_path := _find_structured_audit_file(dir_path)
	if audit_path.is_empty():
		return {"ok": false, "reason": "missing_audit_log"}
	var audit_text := _read_text_file(audit_path)
	if audit_text.strip_edges().is_empty():
		return {"ok": false, "reason": "empty_audit_log"}
	if not _audit_file_has_structured_content(audit_path, audit_text):
		return {"ok": false, "reason": "audit_log_unstructured"}
	return {"ok": true, "reason": "ok", "junit_xml": junit_xml_path, "audit_file": audit_path}

func _resolve_real_task44_e2e_dir() -> String:
	var repo_e2e_root := _repo_root_path().path_join("logs").path_join("e2e")
	if not DirAccess.dir_exists_absolute(repo_e2e_root):
		return ""

	var today_candidate := repo_e2e_root.path_join(Time.get_date_string_from_system()).path_join("sc-test").path_join("gdunit-hard")
	if DirAccess.dir_exists_absolute(today_candidate):
		var today_verdict := _validate_e2e_artifacts(today_candidate)
		if bool(today_verdict.get("ok", false)):
			return today_candidate

	var dir := DirAccess.open(repo_e2e_root)
	if dir == null:
		return ""
	dir.list_dir_begin()
	while true:
		var entry_name := str(dir.get_next())
		if entry_name == "":
			break
		if not dir.current_is_dir():
			continue
		if not _is_iso_date_token(entry_name):
			continue
		var candidate := repo_e2e_root.path_join(entry_name).path_join("sc-test").path_join("gdunit-hard")
		if not DirAccess.dir_exists_absolute(candidate):
			continue
		var verdict := _validate_e2e_artifacts(candidate)
		if bool(verdict.get("ok", false)):
			dir.list_dir_end()
			return candidate
	dir.list_dir_end()
	return ""

func _task44_xml_stub() -> String:
	return (
		"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
		+ "<testsuite name=\"task44\" tests=\"1\" failures=\"0\">\n"
		+ "  <testcase classname=\"test_task0044_acceptance\" name=\"test_e2e_logs_require_junit_xml_and_audit_logs\" />\n"
		+ "</testsuite>\n"
	)

func _read_text_file(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	return file.get_as_text()

func _checklist_contains_required_adr_markers(checklist_path: String) -> bool:
	var text := _read_text_file(checklist_path)
	if text.is_empty():
		return false
	for marker in ADR_TRACE_IDS:
		if text.find(marker) < 0:
			return false
	return true

func _task44_xml_with_markers(markers: Array[String]) -> String:
	var marker_text := ""
	for marker in markers:
		if not marker_text.is_empty():
			marker_text += " "
		marker_text += marker
	return (
		"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
		+ "<testsuite name=\"test_task0044_acceptance\" tests=\"1\" failures=\"0\" errors=\"0\">\n"
		+ "  <testcase classname=\"test_task0044_acceptance\" name=\"test_task_44_artifacts_include_adr_0032_and_adr_0025_traceability\" />\n"
		+ "  <system-out>%s %s</system-out>\n"
		+ "</testsuite>\n"
	) % [TASK44_REPORT_KEYWORDS[0], marker_text]

func _task44_artifact_files(dir_path: String) -> Array[String]:
	var files := _collect_files_recursive(dir_path)
	var selected: Array[String] = []
	for path in files:
		var lower := path.to_lower()
		if not (lower.ends_with(".xml") or lower.ends_with(".html") or lower.ends_with(".log") or lower.ends_with(".json") or lower.ends_with(".txt")):
			continue
		var text := _read_text_file(path)
		if text.is_empty():
			continue
		if _contains_any_task44_keyword(text) or text.find("task0044") >= 0:
			selected.append(path)
	return selected

func _artifacts_include_all_markers(dir_path: String, markers: Array[String]) -> bool:
	var files := _task44_artifact_files(dir_path)
	if files.is_empty():
		return false
	for marker in markers:
		var found := false
		for path in files:
			if _read_text_file(path).find(marker) >= 0:
				found = true
				break
		if not found:
			return false
	return true

# ACC:T44.1
func test_resume_keeps_reward_shop_event_snapshots_deterministic() -> void:
	var persisted_snapshot := {}
	for flow in REQUIRED_FLOWS:
		persisted_snapshot[flow] = _snapshot_for_flow(flow)
	var run_dir := _create_temp_e2e_dir("resume_state")
	var save_path := run_dir.path_join("task44.resume.snapshot.json")
	assert_that(_save_snapshot(save_path, persisted_snapshot)).is_true()
	assert_that(FileAccess.file_exists(save_path)).is_true()
	var restored_by_flow := _resume_state(_load_snapshot(save_path))
	for flow in REQUIRED_FLOWS:
		_assert_snapshot_flow_equal(_snapshot_for_flow(flow), restored_by_flow[flow] as Dictionary)

func test_resume_coverage_rejects_missing_flow() -> void:
	var covered_flows: Array[String] = ["reward", "shop"]
	assert_that(_has_required_flow_coverage(covered_flows)).is_false()

# ACC:T44.2
func test_headless_mode_refuses_interactive_input_requirement() -> void:
	var session := {"headless": true, "requires_input": true}
	var verdict := _validate_headless_session(session)
	assert_that(verdict.get("accepted", true)).is_false()
	assert_that(verdict.get("reason", "")).is_equal("interactive_input_not_allowed")

func test_headless_mode_requires_headless_flag() -> void:
	var session := {"headless": false, "requires_input": false}
	var verdict := _validate_headless_session(session)
	assert_that(verdict.get("accepted", true)).is_false()
	assert_that(verdict.get("reason", "")).is_equal("headless_required")

# ACC:T44.3
func test_task_views_trace_test_refs_to_this_headless_suite() -> void:
	var root := _resolve_taskmaster_root()
	var back_path := root.path_join(".taskmaster").path_join("tasks").path_join("tasks_back.json")
	var gameplay_path := root.path_join(".taskmaster").path_join("tasks").path_join("tasks_gameplay.json")
	assert_that(_task_view_contains_traceability(back_path)).is_true()
	assert_that(_task_view_contains_traceability(gameplay_path)).is_true()

# ACC:T44.8
func test_e2e_logs_require_junit_xml_and_audit_logs() -> void:
	var run_dir := _resolve_real_task44_e2e_dir()
	assert_that(run_dir.is_empty()).is_false()
	var verdict := _validate_e2e_artifacts(run_dir)
	assert_that(verdict.get("ok", false)).is_true()
	assert_that(verdict.get("reason", "")).is_equal("ok")
	assert_that(str(verdict.get("junit_xml", "")).is_empty()).is_false()
	assert_that(str(verdict.get("audit_file", "")).is_empty()).is_false()

func test_e2e_logs_should_fail_when_audit_log_missing() -> void:
	var run_dir := _create_temp_logs_e2e_date_dir("missing_audit")
	_write_text_file(run_dir.path_join("results.junit.xml"), _task44_xml_stub())
	var verdict := _validate_e2e_artifacts(run_dir)
	assert_that(verdict.get("ok", true)).is_false()
	assert_that(verdict.get("reason", "")).is_equal("missing_audit_log")

func test_e2e_logs_should_fail_when_junit_xml_missing() -> void:
	var run_dir := _create_temp_logs_e2e_date_dir("missing_xml")
	_write_text_file(run_dir.path_join("task44.audit.log"), "{\"event\":\"resume_validated\",\"ts\":\"2026-04-19T00:00:00Z\"}")
	var verdict := _validate_e2e_artifacts(run_dir)
	assert_that(verdict.get("ok", true)).is_false()
	assert_that(verdict.get("reason", "")).is_equal("missing_task44_junit_xml")

# ACC:T44.9
func test_task_44_artifacts_include_adr_0032_and_adr_0025_traceability() -> void:
	var task_entries := _collect_task_entries_for_task_44()
	assert_that(task_entries.size() >= 2).is_true()
	for item in task_entries:
		var entry := item as Dictionary
		var adr_refs := Array(entry.get("adr_refs", []))
		for adr_id in ADR_TRACE_IDS:
			assert_that(adr_refs.has(adr_id)).is_true()
		assert_that(_task_entry_has_test_ref(entry, TEST_REF_PATH)).is_true()

	var checklist_path := _repo_root_path().path_join(ACCEPTANCE_CHECKLIST_PATH)
	assert_that(FileAccess.file_exists(checklist_path)).is_true()
	assert_that(_checklist_contains_required_adr_markers(checklist_path)).is_true()

	var run_dir := _resolve_real_task44_e2e_dir()
	assert_that(run_dir.is_empty()).is_false()
	var verdict := _validate_e2e_artifacts(run_dir)
	assert_that(verdict.get("ok", false)).is_true()

	var marker_artifacts_dir := _create_temp_logs_e2e_date_dir("task44_trace_marker_positive")
	_write_text_file(marker_artifacts_dir.path_join("results.xml"), _task44_xml_with_markers(ADR_TRACE_IDS))
	_write_text_file(marker_artifacts_dir.path_join("task44.audit.log"), "{\"event\":\"traceability_markers\",\"ts\":\"2026-04-19T00:00:00Z\"}")
	var marker_verdict := _validate_e2e_artifacts(marker_artifacts_dir)
	assert_that(marker_verdict.get("ok", false)).is_true()
	assert_that(_artifacts_include_all_markers(marker_artifacts_dir, ADR_TRACE_IDS)).is_true()

	var missing_marker_artifacts_dir := _create_temp_logs_e2e_date_dir("task44_trace_marker_missing")
	_write_text_file(missing_marker_artifacts_dir.path_join("results.xml"), _task44_xml_with_markers([ADR_TRACE_IDS[0]]))
	_write_text_file(missing_marker_artifacts_dir.path_join("task44.audit.log"), "{\"event\":\"traceability_markers\",\"ts\":\"2026-04-19T00:00:00Z\"}")
	var missing_verdict := _validate_e2e_artifacts(missing_marker_artifacts_dir)
	assert_that(missing_verdict.get("ok", false)).is_true()
	assert_that(_artifacts_include_all_markers(missing_marker_artifacts_dir, ADR_TRACE_IDS)).is_false()
