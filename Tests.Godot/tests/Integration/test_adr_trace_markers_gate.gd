extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const ADR_0032 := "ADR-0032"
const ADR_0025 := "ADR-0025"
const TASK44_SCOPE := "task44_scope"
const TASK44_REPORT_KEYWORDS: Array[String] = ["test_task0044_acceptance", "test_reward_shop_event_resume_determinism"]
const ACCEPTANCE_CHECKLIST_RELATIVE_PATH := "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md"

# RED-FIRST note:
# This local gate intentionally implements weaker logic.
# It allows markers to be split across artifacts and checklist entries.
func _evaluate_trace_gate(test_artifacts: Array[String], checklist_entries: Array[String], scope: String = TASK44_SCOPE) -> bool:
	var scoped_artifacts := _select_scoped_entries(test_artifacts, scope)
	var test_has_0032 := _has_marker(scoped_artifacts, ADR_0032)
	var test_has_0025 := _has_marker(scoped_artifacts, ADR_0025)
	var checklist_has_0032 := _has_marker(checklist_entries, ADR_0032)
	var checklist_has_0025 := _has_marker(checklist_entries, ADR_0025)
	return test_has_0032 and test_has_0025 and checklist_has_0032 and checklist_has_0025

func _select_scoped_entries(entries: Array[String], scope: String) -> Array[String]:
	if scope.is_empty():
		return entries.duplicate()
	var result: Array[String] = []
	for entry in entries:
		if entry.find(scope) >= 0:
			result.append(entry)
	return result

func _has_marker(entries: Array[String], marker: String) -> bool:
	for entry in entries:
		if entry.find(marker) >= 0:
			return true
	return false

func _repo_root_path() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()

func _read_text_file(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	return file.get_as_text()

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

func _is_iso_date_token(value: String) -> bool:
	if value.length() != 10:
		return false
	if value.substr(4, 1) != "-" or value.substr(7, 1) != "-":
		return false
	var compact := value.replace("-", "")
	return compact.length() == 8 and compact.is_valid_int()

func _contains_any_task44_keyword(text: String) -> bool:
	for keyword in TASK44_REPORT_KEYWORDS:
		if text.find(keyword) >= 0:
			return true
	return false

func _resolve_checklist_path() -> String:
	return _repo_root_path().path_join(ACCEPTANCE_CHECKLIST_RELATIVE_PATH)

func _resolve_real_task44_task_views_dir() -> String:
	return _repo_root_path().path_join(".taskmaster").path_join("tasks")

func _load_artifact_entries_from_dir(artifact_dir: String) -> Array[String]:
	var entries: Array[String] = []
	var files := _collect_files_recursive(artifact_dir)
	for path in files:
		var lower := path.to_lower()
		if not (lower.ends_with(".xml") or lower.ends_with(".html") or lower.ends_with(".log") or lower.ends_with(".json") or lower.ends_with(".txt")):
			continue
		var text := _read_text_file(path)
		if text.strip_edges().is_empty():
			continue
		if _contains_any_task44_keyword(text) or text.find(ADR_0032) >= 0 or text.find(ADR_0025) >= 0:
			entries.append("%s file=%s %s" % [TASK44_SCOPE, path, text])
	return entries

func _load_checklist_entries_from_file(path: String) -> Array[String]:
	var text := _read_text_file(path)
	if text.is_empty():
		return []
	return text.split("\n")

func _evaluate_trace_gate_from_files(artifact_dir: String, checklist_path: String) -> bool:
	var artifacts := _load_artifact_entries_from_dir(artifact_dir)
	var checklist_entries := _load_checklist_entries_from_file(checklist_path)
	return _evaluate_trace_gate(artifacts, checklist_entries, TASK44_SCOPE)

func _delete_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	while true:
		var entry_name := str(dir.get_next())
		if entry_name == "":
			break
		if entry_name == "." or entry_name == "..":
			continue
		var child := path.path_join(entry_name)
		if dir.current_is_dir():
			_delete_tree(child)
		else:
			DirAccess.remove_absolute(child)
	dir.list_dir_end()
	DirAccess.remove_absolute(path)

func _create_temp_trace_dir(tag: String) -> String:
	var date_token := Time.get_date_string_from_system()
	var dir_path := ProjectSettings.globalize_path("user://task44_trace_gate").path_join("logs").path_join("e2e").path_join(date_token).path_join("%s_%s" % [tag, str(Time.get_ticks_usec())])
	_delete_tree(dir_path)
	DirAccess.make_dir_recursive_absolute(dir_path)
	return dir_path

func _write_text_file(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return
	file.store_string(content)
	file.flush()

func _task44_xml_with_trace(markers: Array[String]) -> String:
	return (
		"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
		+ "<testsuite name=\"test_task0044_acceptance\" tests=\"1\" failures=\"0\" errors=\"0\">\n"
		+ "  <testcase classname=\"test_task0044_acceptance\" name=\"test_task_44_artifacts_include_adr_0032_and_adr_0025_traceability\" />\n"
		+ "  <system-out>%s %s %s</system-out>\n"
		+ "</testsuite>\n"
	) % [TASK44_SCOPE, " ".join(markers), TASK44_REPORT_KEYWORDS[0]]

# acceptance: ACC:T44.10
func test_gate_rejects_when_adr_0032_is_missing_from_test_artifacts() -> void:
	var test_artifacts: Array[String] = ["task44_scope trace: ADR-0025 present"]
	var checklist_entries: Array[String] = ["checklist includes ADR-0032 and ADR-0025"]
	var result := _evaluate_trace_gate(test_artifacts, checklist_entries)
	assert_bool(result).is_false()

func test_gate_rejects_when_adr_0025_is_missing_from_checklist_entries() -> void:
	var test_artifacts: Array[String] = ["task44_scope artifact ADR-0032", "task44_scope artifact ADR-0025"]
	var checklist_entries: Array[String] = ["checklist only ADR-0032"]
	var result := _evaluate_trace_gate(test_artifacts, checklist_entries)
	assert_bool(result).is_false()

func test_gate_accepts_when_both_markers_exist_in_both_sources() -> void:
	var test_artifacts: Array[String] = ["task44_scope artifact ADR-0032", "task44_scope artifact ADR-0025"]
	var checklist_entries: Array[String] = ["checklist ADR-0032", "checklist ADR-0025"]
	var result := _evaluate_trace_gate(test_artifacts, checklist_entries)
	assert_bool(result).is_true()

func test_gate_rejects_markers_that_exist_outside_task44_scope() -> void:
	var test_artifacts: Array[String] = ["other_scope artifact ADR-0032", "other_scope artifact ADR-0025"]
	var checklist_entries: Array[String] = ["checklist ADR-0032", "checklist ADR-0025"]
	var result := _evaluate_trace_gate(test_artifacts, checklist_entries)
	assert_bool(result).is_false()

func test_gate_accepts_real_task44_task_views_and_checklist_when_both_include_required_markers() -> void:
	var artifact_dir := _resolve_real_task44_task_views_dir()
	assert_that(artifact_dir.is_empty()).is_false()
	assert_that(DirAccess.dir_exists_absolute(artifact_dir)).is_true()
	var checklist_path := _resolve_checklist_path()
	assert_that(FileAccess.file_exists(checklist_path)).is_true()
	var result := _evaluate_trace_gate_from_files(artifact_dir, checklist_path)
	assert_bool(result).is_true()

func test_gate_rejects_real_file_inputs_when_checklist_loses_adr_0025() -> void:
	var artifact_dir := _create_temp_trace_dir("artifact_with_markers")
	_write_text_file(artifact_dir.path_join("results.xml"), _task44_xml_with_trace([ADR_0032, ADR_0025]))

	var checklist_path := _create_temp_trace_dir("checklist_missing_marker").path_join("ACCEPTANCE_CHECKLIST.md")
	_write_text_file(checklist_path, "# Checklist\n- ADR-0032\n")
	var result := _evaluate_trace_gate_from_files(artifact_dir, checklist_path)
	assert_bool(result).is_false()

func test_gate_accepts_real_file_inputs_when_artifact_and_checklist_both_include_required_adr_markers() -> void:
	var artifact_dir := _create_temp_trace_dir("artifact_ok")
	_write_text_file(artifact_dir.path_join("results.xml"), _task44_xml_with_trace([ADR_0032, ADR_0025]))

	var checklist_path := _create_temp_trace_dir("checklist_ok").path_join("ACCEPTANCE_CHECKLIST.md")
	_write_text_file(checklist_path, "# Checklist\n- ADR-0032\n- ADR-0025\n")
	var result := _evaluate_trace_gate_from_files(artifact_dir, checklist_path)
	assert_bool(result).is_true()
