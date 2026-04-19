extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK44_KEYWORD := "task0044"

func _repo_root() -> String:
    var current := ProjectSettings.globalize_path("res://").simplify_path()
    for _idx in range(0, 8):
        if FileAccess.file_exists(current.path_join("NewRouge.sln").simplify_path()):
            return current
        current = current.path_join("..").simplify_path()
    return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()

func _read_text_file(path: String) -> String:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return ""
    var text := file.get_as_text()
    file.close()
    return text

func _find_all_xml_in_tree(root_dir: String) -> Array[String]:
    var found: Array[String] = []
    var pending: Array[String] = [root_dir]
    while pending.size() > 0:
        var current: String = str(pending.pop_back())
        var dir := DirAccess.open(current)
        if dir == null:
            continue

        dir.list_dir_begin()
        while true:
            var entry_name: String = str(dir.get_next())
            if entry_name == "":
                break
            if entry_name == "." or entry_name == "..":
                continue

            var full_path: String = current.path_join(entry_name)
            if dir.current_is_dir():
                pending.push_back(full_path)
            elif entry_name.to_lower().ends_with(".xml"):
                found.append(full_path)
        dir.list_dir_end()
    return found

func _count_xml_files_in_tree(root_dir: String) -> int:
    var count := 0
    var pending: Array[String] = [root_dir]
    while pending.size() > 0:
        var current: String = str(pending.pop_back())
        var dir := DirAccess.open(current)
        if dir == null:
            continue
        dir.list_dir_begin()
        while true:
            var entry_name: String = str(dir.get_next())
            if entry_name == "":
                break
            if entry_name == "." or entry_name == "..":
                continue
            var full_path: String = current.path_join(entry_name)
            if dir.current_is_dir():
                pending.push_back(full_path)
            elif entry_name.to_lower().ends_with(".xml"):
                count += 1
        dir.list_dir_end()
    return count

func _is_readable_xml(path: String) -> bool:
    var parser := XMLParser.new()
    return parser.open(path) == OK

func _has_task_related_case(_xml_text: String) -> bool:
    return (
        _xml_text.find("test_task0044_acceptance") >= 0
        or _xml_text.find("test_reward_shop_event_resume_determinism") >= 0
    )

func _find_latest_real_xml_under_logs_e2e() -> String:
    var e2e_root := _repo_root().path_join("logs").path_join("e2e").simplify_path()
    var xmls := _find_all_xml_in_tree(e2e_root)
    if xmls.is_empty():
        return ""
    for xml_path in xmls:
        var lower := xml_path.to_lower()
        if lower.find("/logs/e2e/") == -1 and lower.find("\\logs\\e2e\\") == -1:
            continue
        if lower.find(TASK44_KEYWORD) == -1:
            continue
        var xml_text := _read_text_file(xml_path)
        if _has_task_related_case(xml_text):
            return xml_path
    return ""

# acceptance: ACC:T44.6
func test_headless_junit_xml_artifact_is_readable_and_contains_task_related_cases() -> void:
    var e2e_root := _repo_root().path_join("logs").path_join("e2e").simplify_path()
    assert_that(DirAccess.dir_exists_absolute(e2e_root)).is_true()
    assert_that(_count_xml_files_in_tree(e2e_root) > 0).is_true()
    var discovered := _find_latest_real_xml_under_logs_e2e()
    assert_that(discovered.is_empty()).is_false()
    assert_that(discovered.find("/logs/e2e/") >= 0 or discovered.find("\\logs\\e2e\\") >= 0).is_true()
    assert_that(discovered.to_lower().find(TASK44_KEYWORD) >= 0).is_true()
    assert_that(_is_readable_xml(discovered)).is_true()

    var xml_text := _read_text_file(discovered)
    assert_that(xml_text.find("<testsuite") >= 0).is_true()
    assert_that(_has_task_related_case(xml_text)).is_true()

func test_headless_junit_xml_without_task_related_case_is_rejected() -> void:
    var xml_text := (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        + "<testsuite name=\"headless\" tests=\"1\" failures=\"0\">\n"
        + "  <testcase classname=\"Integration\" name=\"test_unrelated_feature\" />\n"
        + "</testsuite>\n"
    )
    assert_that(_has_task_related_case(xml_text)).is_false()
