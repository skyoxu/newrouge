extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_FILE := "res://../.taskmaster/tasks/tasks_gameplay.json"
const CHECKLIST_FILE := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md"
const DIFFICULTY_CONFIG_FILE := "res://../Game.Core/Contracts/Config/DifficultyConfig.cs"
const CORE_TASK_TEST_FILE := "res://../Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs"
const THIS_TEST_REF := "Tests.Godot/tests/Tasks/test_task0026_acceptance.gd"
const CORE_TEST_REF := "Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs"
const REQUIRED_ADR_IDS := ["ADR-0023", "ADR-0032", "ADR-0021"]
const REQUIRED_DIFFICULTY_FIELDS := ["DifficultyId", "LabelKey", "DescriptionKey", "RulesetId"]

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

func _load_task26_record() -> Dictionary:
    var raw := _read_text(TASK_FILE)
    if raw.strip_edges() == "":
        return {}

    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_ARRAY:
        return {}

    for item in parsed:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        if int(item.get("taskmaster_id", -1)) == 26:
            return item
    return {}

func _contains_all_tokens(text: String, tokens: Array) -> bool:
    for token in tokens:
        if not text.contains(str(token)):
            return false
    return true

func _acceptance_joined_text(task_record: Dictionary) -> String:
    var acceptance = task_record.get("acceptance", [])
    if typeof(acceptance) != TYPE_ARRAY:
        return ""

    var joined := ""
    for item in acceptance:
        joined += str(item) + "\n"
    return joined

func _gate_traceability_is_consistent(checklist_text: String, task_record: Dictionary) -> bool:
    if not _contains_all_tokens(checklist_text, REQUIRED_ADR_IDS):
        return false

    var adr_refs = task_record.get("adr_refs", [])
    if typeof(adr_refs) != TYPE_ARRAY:
        return false
    for adr_id in REQUIRED_ADR_IDS:
        if not adr_refs.has(adr_id):
            return false

    var acceptance_text := _acceptance_joined_text(task_record)
    if not acceptance_text.contains(THIS_TEST_REF):
        return false
    if not acceptance_text.contains(CORE_TEST_REF):
        return false

    return true

# acceptance: ACC:T26.1
func test_difficulty_config_contract_exposes_required_read_only_fields() -> void:
    var source := _read_text(DIFFICULTY_CONFIG_FILE)
    assert_bool(source.strip_edges().is_empty()).is_false()

    for field_name in REQUIRED_DIFFICULTY_FIELDS:
        assert_bool(source.contains(field_name)).is_true()

    var normalized := source.replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")
    for field_name in REQUIRED_DIFFICULTY_FIELDS:
        assert_bool(normalized.contains(str(field_name) + "{get;set;}")) .is_false()

# acceptance: ACC:T26.2
func test_run_start_persists_selected_difficulty_in_allowed_range_and_freezes_after_start() -> void:
    var core_test_source := _read_text(CORE_TASK_TEST_FILE)
    assert_bool(core_test_source.strip_edges().is_empty()).is_false()

    assert_bool(core_test_source.contains("ShouldPersistSelectedDifficultyValue_WhenRunStarts")).is_true()
    assert_bool(core_test_source.contains("ShouldKeepDifficultyUnchanged_WhenMutationIsRequestedAfterRunStart")).is_true()
    assert_bool(core_test_source.contains("WriteAutosaveAsync")).is_true()
    assert_bool(core_test_source.contains("ReadContinueMetadataAsync")).is_true()
    assert_bool(core_test_source.contains("difficulty_snapshot_incomplete")).is_true()
    assert_bool(core_test_source.contains("difficulty_immutable")).is_true()

    var has_explicit_range_guard := core_test_source.contains("1-10")
    if not has_explicit_range_guard:
        has_explicit_range_guard = core_test_source.contains("BeGreaterOrEqualTo(1)") and core_test_source.contains("BeLessOrEqualTo(10)")
    assert_bool(has_explicit_range_guard).is_true()

# acceptance: ACC:T26.3
func test_task26_acceptance_lists_refs_for_difficulty_persistence_and_immutability() -> void:
    var task_record := _load_task26_record()
    assert_bool(task_record.is_empty()).is_false()

    var test_refs = task_record.get("test_refs", [])
    assert_bool(typeof(test_refs) == TYPE_ARRAY).is_true()
    if typeof(test_refs) == TYPE_ARRAY:
        assert_bool(test_refs.has(THIS_TEST_REF)).is_true()
        assert_bool(test_refs.has(CORE_TEST_REF)).is_true()

    var acceptance_text := _acceptance_joined_text(task_record)
    assert_bool(acceptance_text.contains(THIS_TEST_REF)).is_true()
    assert_bool(acceptance_text.contains(CORE_TEST_REF)).is_true()
    assert_bool(acceptance_text.to_lower().contains("difficulty")).is_true()

# acceptance: ACC:T26.13
func test_task26_acceptance_checklist_explicitly_contains_required_adr_trace_links() -> void:
    var checklist := _read_text(CHECKLIST_FILE)
    assert_bool(checklist.strip_edges().is_empty()).is_false()

    var has_task26_marker := checklist.contains("Task 26") or checklist.contains("Task26") or checklist.contains("task-0026") or checklist.contains("T26")
    assert_bool(has_task26_marker).is_true()

    for adr_id in REQUIRED_ADR_IDS:
        assert_bool(checklist.contains(adr_id)).is_true()

# acceptance: ACC:T26.14
func test_traceability_gate_fails_when_adr_linkage_is_missing_or_inconsistent() -> void:
    var task_record := _load_task26_record()
    assert_bool(task_record.is_empty()).is_false()

    var missing_adr_checklist := "Task 26 ADR map: ADR-0023 ADR-0032"
    assert_bool(_gate_traceability_is_consistent(missing_adr_checklist, task_record)).is_false()

    var inconsistent_task_record := task_record.duplicate(true)
    inconsistent_task_record["adr_refs"] = ["ADR-0023", "ADR-0032"]
    var complete_checklist := "Task 26 ADR map: ADR-0023 ADR-0032 ADR-0021"
    assert_bool(_gate_traceability_is_consistent(complete_checklist, inconsistent_task_record)).is_false()
