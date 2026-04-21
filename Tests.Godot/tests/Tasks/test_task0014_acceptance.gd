extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_TEST_PATH := "Tests.Godot/tests/Tasks/test_task0014_acceptance.gd"
const MAIN_MENU_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const AUTOSAVE_PATH := "user://autosave_slot.json"
const OVERLAY_TESTING_FILE := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Testing-M1.md"
const EXECUTION_PLAN_FILE := "res://../execution-plans/2026-04-06-task-14-chapter6-execution.md"
const DECISION_LOG_FILE := "res://../decision-logs/2026-04-06-task-14-manual-flow-evidence.md"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const KEY_PREFIXES := ["ui.", "menu.", "card.", "relic.", "event.", "etc."]
var _previous_locale := ""

func _looks_like_translation_key(value: String) -> bool:
    var text := value.strip_edges().to_lower()
    for prefix in KEY_PREFIXES:
        if text.begins_with(prefix):
            return true
    return false

func _instantiate_main_menu() -> Control:
    var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate() as Control
    add_child(auto_free(menu))
    if menu.has_method("RefreshVisibleTextForTest"):
        menu.call("RefreshVisibleTextForTest")
    return menu

func before() -> void:
    _previous_locale = TranslationServer.get_locale()
    TranslationServer.set_locale("en")
    _remove_autosave()

func after() -> void:
    TranslationServer.set_locale(_previous_locale)
    _remove_autosave()
    if _previous_locale != "":
        TranslationServer.set_locale(_previous_locale)

func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)

func _write_autosave(payload: String) -> void:
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    file.store_string(payload)
    file.close()

func _sha256_hex(text: String) -> String:
    return text.sha256_text()

func _build_valid_autosave_json() -> String:
    var state_json := "{}"
    var integrity_hash := _sha256_hex(state_json)
    return "{\"run_id\":\"run_a\",\"save_point_id\":\"menu\",\"schema_version\":\"1.0.0\",\"saved_at\":\"2026-04-06T00:00:00Z\",\"state_json\":\"%s\",\"integrity_hash\":\"%s\"}" % [state_json, integrity_hash]

func _load_translation_values(csv_path: String) -> Dictionary:
    var values := {}
    var raw := _read_text(csv_path)
    for line in raw.split("\n", false):
        var trimmed := line.strip_edges()
        if trimmed == "" or trimmed.begins_with("key,value"):
            continue
        var comma := trimmed.find(",")
        if comma <= 0:
            continue
        var key := trimmed.substr(0, comma).strip_edges()
        var value := trimmed.substr(comma + 1).strip_edges()
        values[key] = value
    return values

func _read_text(file_path: String) -> String:
    var global_path := ProjectSettings.globalize_path(file_path)
    if not FileAccess.file_exists(global_path):
        return ""
    var file := FileAccess.open(global_path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content

func _matches_extension(file_name: String, extensions: Array) -> bool:
    if extensions.is_empty():
        return true
    for extension in extensions:
        if file_name.ends_with(String(extension)):
            return true
    return false

func _directory_contains_token(directory_path: String, token: String, extensions: Array = []) -> bool:
    var global_path := ProjectSettings.globalize_path(directory_path)
    var dir := DirAccess.open(global_path)
    if dir == null:
        return false

    var lowered_token := token.to_lower()
    dir.list_dir_begin()
    var entry := dir.get_next()
    while entry != "":
        if entry.begins_with("."):
            entry = dir.get_next()
            continue

        var full_path := global_path.path_join(entry)
        if dir.current_is_dir():
            if _directory_contains_token(full_path, token, extensions):
                dir.list_dir_end()
                return true
        elif _matches_extension(entry, extensions):
            var content := _read_text(full_path).to_lower()
            if content.contains(lowered_token):
                dir.list_dir_end()
                return true

        entry = dir.get_next()
    dir.list_dir_end()
    return false

func _directory_contains_file_name_token(directory_path: String, token: String) -> bool:
    var global_path := ProjectSettings.globalize_path(directory_path)
    var dir := DirAccess.open(global_path)
    if dir == null:
        return false

    var lowered_token := token.to_lower()
    dir.list_dir_begin()
    var entry := dir.get_next()
    while entry != "":
        if entry.begins_with("."):
            entry = dir.get_next()
            continue

        var full_path := global_path.path_join(entry)
        if dir.current_is_dir():
            if _directory_contains_file_name_token(full_path, token):
                dir.list_dir_end()
                return true
        elif entry.to_lower().contains(lowered_token):
            dir.list_dir_end()
            return true

        entry = dir.get_next()
    dir.list_dir_end()
    return false

# ACC:T14.1
# ACC:T59.4
func test_main_menu_initializes_continue_and_new_run_from_real_autosave_file() -> void:
    _write_autosave(_build_valid_autosave_json())
    var menu := _instantiate_main_menu()
    await get_tree().process_frame

    var new_run_btn := menu.get_node_or_null("VBox/BtnNewRun") as Button
    var continue_btn := menu.get_node_or_null("VBox/BtnContinue") as Button
    assert_bool(new_run_btn != null).is_true()
    assert_bool(continue_btn != null).is_true()
    assert_bool(continue_btn.disabled).is_false()
    new_run_btn.emit_signal("pressed")
    await get_tree().process_frame

    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    assert_bool(dialog != null).is_true()
    assert_bool(dialog.visible).is_true()

# ACC:T14.1
func test_main_menu_disables_continue_when_autosave_is_missing() -> void:
    _remove_autosave()
    var menu := _instantiate_main_menu()
    await get_tree().process_frame

    var continue_btn := menu.get_node_or_null("VBox/BtnContinue") as Button
    assert_bool(continue_btn != null).is_true()
    if continue_btn == null:
        return
    assert_bool(continue_btn.disabled).is_true()

# ACC:T14.2
# ACC:T59.4
func test_menu_and_confirmation_texts_are_from_translation_values() -> void:
    var expected := _load_translation_values(EN_TRANSLATIONS_FILE)
    var menu := _instantiate_main_menu()
    await get_tree().process_frame

    var new_run_btn := menu.get_node_or_null("VBox/BtnNewRun") as Button
    var continue_btn := menu.get_node_or_null("VBox/BtnContinue") as Button
    var quit_btn := menu.get_node_or_null("VBox/BtnQuit") as Button
    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog

    assert_bool(new_run_btn != null).is_true()
    assert_bool(continue_btn != null).is_true()
    assert_bool(quit_btn != null).is_true()
    assert_bool(dialog != null).is_true()

    assert_str(new_run_btn.text.strip_edges()).is_equal(str(expected["ui.menu.new_run"]))
    assert_str(continue_btn.text.strip_edges()).is_equal(str(expected["ui.menu.continue"]))
    assert_str(quit_btn.text.strip_edges()).is_equal(str(expected["ui.menu.quit"]))
    assert_str(dialog.title.strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.title"]))
    assert_str(dialog.dialog_text.strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.body"]))
    assert_str(dialog.ok_button_text.strip_edges()).is_equal(str(expected["ui.menu.confirm"]))
    assert_str(dialog.cancel_button_text.strip_edges()).is_equal(str(expected["ui.menu.cancel"]))
    assert_bool(_looks_like_translation_key(new_run_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(continue_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(quit_btn.text)).is_false()
    assert_bool(_looks_like_translation_key(dialog.title)).is_false()

# ACC:T14.3
func test_overlay_08_contains_task_test_ref_for_traceability() -> void:
    var has_trace_ref := _read_text(OVERLAY_TESTING_FILE).contains(TASK_TEST_PATH)
    assert_bool(has_trace_ref).is_true()

# ACC:T14.9
func test_manual_menu_flow_record_exists_for_new_run_and_continue_autosave() -> void:
    var plan_text := _read_text(EXECUTION_PLAN_FILE).to_lower()
    var decision_text := _read_text(DECISION_LOG_FILE).to_lower()

    assert_bool(plan_text.contains("task 14")).is_true()
    assert_bool(plan_text.contains("overwrite confirmation")).is_true()
    assert_bool(plan_text.contains("default to cancel")).is_true()
    assert_bool(plan_text.contains("valid autosave snapshot")).is_true()
    assert_bool(decision_text.contains("task 14")).is_true()

# ACC:T14.10
func test_manual_record_is_auditable_with_accessible_log_linkage() -> void:
    var plan_text := _read_text(EXECUTION_PLAN_FILE)
    var decision_text := _read_text(DECISION_LOG_FILE)

    assert_bool(plan_text.contains("logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json")).is_true()
    assert_bool(decision_text.contains("logs/ci/2026-04-06/sc-review-pipeline-task-14/latest.json")).is_true()
    assert_bool(decision_text.contains("logs/ci/2026-04-06/sc-review-pipeline-task-14-")).is_true()

# ACC:T14.11
func test_artifacts_reference_adr_0032_and_adr_0010() -> void:
    var plan_text := _read_text(EXECUTION_PLAN_FILE)
    var decision_text := _read_text(DECISION_LOG_FILE)

    assert_bool(plan_text.contains("ADR-0032")).is_true()
    assert_bool(plan_text.contains("ADR-0010")).is_true()
    assert_bool(decision_text.contains("ADR-0032")).is_true()
    assert_bool(decision_text.contains("ADR-0010")).is_true()
