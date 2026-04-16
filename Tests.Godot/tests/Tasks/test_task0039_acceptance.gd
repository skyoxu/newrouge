extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK_39_TEST_REF := "Tests.Godot/tests/Tasks/test_task0039_acceptance.gd"
const TASK_39_CS_TEST_REF := "Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs"
const ADR_0010_DOC_PATH := "res://../docs/adr/ADR-0010-internationalization.md"
const OVERLAY_INDEX_PATH := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md"
const OVERLAY_CHECKLIST_PATH := "res://../docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md"
const TASKS_GAMEPLAY_PATH := "res://../.taskmaster/tasks/tasks_gameplay.json"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"
const MAIN_MENU_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_SCENE_FILE := "res://../Game.Godot/Scenes/UI/MainMenu.tscn"
const CHARACTER_SELECT_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/CharacterSelect.tscn"
const DIFFICULTY_SELECT_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/DifficultySelect.tscn"
const MAIN_MENU_SCRIPT_FILE := "res://../Game.Godot/Scripts/UI/MainMenu.cs"
const EVENT_SCENE_SCRIPT_FILE := "res://../Game.Godot/Scripts/UI/EventScene.cs"
const CHARACTER_SELECT_SCRIPT_FILE := "res://../Game.Godot/Scripts/UI/CharacterSelect.cs"
const WARRIOR_DECK_SERVICE_FILE := "res://../Game.Core/Services/WarriorStartingDeckService.cs"
const STARTING_RELIC_SERVICE_FILE := "res://../Game.Core/Services/StartingRelicService.cs"
const VERIFY_SCRIPT_PATH := "res://../scripts/python/verify_m1_translations.py"
const TRACEABILITY_GATE_SCRIPT_PATH := "res://../scripts/python/task39_traceability_gate.py"
const PYTHON_EXE := "py"

const REQUIRED_TRANSLATION_KEYS := [
    "event.abyss_toll.title",
    "event.abyss_toll.description",
    "event.option.lose_hp",
    "event.option.take_curse",
    "ui.menu.new_run",
    "ui.menu.continue",
    "ui.menu.quit",
    "ui.menu.confirm",
    "ui.menu.cancel",
    "ui.character.warrior.summary.rage_buff",
    "ui.character.warrior.summary.power_window",
    "ui.character.warrior.summary.cost_burst"
]


func _read_text(res_path: String) -> String:
    var absolute_path := ProjectSettings.globalize_path(res_path)
    if not FileAccess.file_exists(absolute_path):
        return ""
    var file := FileAccess.open(absolute_path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content


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
        if key != "":
            values[key] = value
    return values


func _regex_matches(source_text: String, pattern: String) -> Array[String]:
    var regex := RegEx.new()
    var error := regex.compile(pattern)
    if error != OK:
        return []
    var values: Array[String] = []
    for item in regex.search_all(source_text):
        if item.get_group_count() >= 1:
            var value := str(item.get_string(1)).strip_edges()
            if value != "" and not values.has(value):
                values.append(value)
    return values


func _extract_card_translation_keys() -> Array[String]:
    var text := _read_text(WARRIOR_DECK_SERVICE_FILE)
    var card_ids := _regex_matches(text, '"(card\\.warrior\\.[a-z0-9_]+)"')
    var keys: Array[String] = []
    for card_id in card_ids:
        var key := "%s.name" % card_id
        if not keys.has(key):
            keys.append(key)
    return keys


func _extract_relic_translation_keys() -> Array[String]:
    var text := _read_text(STARTING_RELIC_SERVICE_FILE)
    return _regex_matches(text, '"(relic\\.name\\.[a-z0-9_]+)"')


func _extract_event_translation_keys() -> Array[String]:
    var text := _read_text(EVENT_SCENE_SCRIPT_FILE)
    var keys := _regex_matches(text, 'private const string \\w*Key = "(event\\.[a-z0-9_.]+)"')
    for key in _regex_matches(text, 'new EventOption\\("[^"]+",\\s*"(event\\.[a-z0-9_.]+)"'):
        if not keys.has(key):
            keys.append(key)
    return keys


func _extract_ui_prompt_translation_keys() -> Array[String]:
    var keys: Array[String] = []

    var scene_text := _read_text(MAIN_MENU_SCENE_FILE)
    for key in _regex_matches(scene_text, '(?:text|title|dialog_text|ok_button_text|cancel_button_text)\\s*=\\s*"((?:ui|event)\\.[a-z0-9_.]+)"'):
        if not keys.has(key):
            keys.append(key)

    var main_menu_text := _read_text(MAIN_MENU_SCRIPT_FILE)
    for key in _regex_matches(main_menu_text, 'ResolveVisibleText\\("((?:ui|event)\\.[a-z0-9_.]+)"\\)'):
        if not keys.has(key):
            keys.append(key)

    var character_select_text := _read_text(CHARACTER_SELECT_SCRIPT_FILE)
    for key in _regex_matches(character_select_text, 'ResolveVisibleText\\("((?:ui|event)\\.[a-z0-9_.]+)"\\)'):
        if not keys.has(key):
            keys.append(key)

    return keys


func _required_translation_keys_for_task39() -> Array[String]:
    var keys: Array[String] = []
    for key in REQUIRED_TRANSLATION_KEYS:
        var text_key := str(key).strip_edges()
        if text_key != "" and not keys.has(text_key):
            keys.append(text_key)
    for key in _extract_card_translation_keys():
        if not keys.has(key):
            keys.append(key)
    for key in _extract_relic_translation_keys():
        if not keys.has(key):
            keys.append(key)
    for key in _extract_event_translation_keys():
        if not keys.has(key):
            keys.append(key)
    for key in _extract_ui_prompt_translation_keys():
        if not keys.has(key):
            keys.append(key)
    return keys


func _collect_missing_translation_entries(required_keys: Array, en_map: Dictionary, zh_map: Dictionary) -> Array[String]:
    var missing: Array[String] = []
    for key in required_keys:
        var text_key := str(key)
        if not en_map.has(text_key):
            missing.append("en::%s" % text_key)
        elif not _is_translation_value_valid(text_key, str(en_map[text_key]), "en"):
            missing.append("en::%s::invalid_value" % text_key)
        if not zh_map.has(text_key):
            missing.append("zh-CN::%s" % text_key)
        elif not _is_translation_value_valid(text_key, str(zh_map[text_key]), "zh-CN"):
            missing.append("zh-CN::%s::invalid_value" % text_key)
    return missing


func _is_translation_value_valid(key: String, value: String, locale: String) -> bool:
    var trimmed := value.strip_edges()
    if trimmed == "":
        return false
    if trimmed == key:
        return false
    var only_question := true
    for ch in trimmed:
        if ch != "?" and ch != "？":
            only_question = false
            break
    if only_question:
        return false
    if trimmed.contains("�"):
        return false
    if locale == "zh-CN" and trimmed.contains("(ZH)"):
        return false
    return true


func _contains_hardcoded_scene_ui_text(source_text: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('(text|title|dialog_text|ok_button_text|cancel_button_text)\\s*=\\s*"(?!ui\\.|event\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(source_text) != null


func _contains_hardcoded_csharp_ui_text(source_text: String) -> bool:
    var regex := RegEx.new()
    var error := regex.compile('(\\.Text|\\.Title|\\.DialogText|\\.OkButtonText|\\.CancelButtonText)\\s*=\\s*"(?!ui\\.|event\\.)[^"]+"')
    if error != OK:
        return false
    return regex.search(source_text) != null


func _contains_non_key_literal_in_card_or_relic_definitions(source_text: String) -> bool:
    var relic_bad := RegEx.new()
    var relic_err := relic_bad.compile('StartingRelicDefinition\\("relic\\.[^"]+",\\s*"(?!relic\\.name\\.)[^"]+"')
    if relic_err == OK and relic_bad.search(source_text) != null:
        return true

    var card_bad := RegEx.new()
    var card_err := card_bad.compile('WarriorStartingDeckCardDefinition\\("(?!card\\.warrior\\.)[^"]+"')
    if card_err == OK and card_bad.search(source_text) != null:
        return true

    return false


func _task39_metadata() -> Dictionary:
    var raw := _read_text(TASKS_GAMEPLAY_PATH)
    if raw == "":
        return {}
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_ARRAY:
        return {}
    for item in parsed:
        if typeof(item) == TYPE_DICTIONARY and int(item.get("taskmaster_id", -1)) == 39:
            return item
    return {}


func _as_string_array(value: Variant) -> Array[String]:
    var result: Array[String] = []
    if typeof(value) != TYPE_ARRAY:
        return result
    for item in value:
        var text := str(item).strip_edges()
        if text != "":
            result.append(text)
    return result


func _has_adr_traceability_in_docs() -> bool:
    var overlay_index := _read_text(OVERLAY_INDEX_PATH)
    var checklist := _read_text(OVERLAY_CHECKLIST_PATH)
    return overlay_index.contains("ADR-0010") and checklist.contains("ADR-0010")


func _validate_gate_contract(adr_refs: Array[String], test_refs: Array[String]) -> bool:
    var has_adr := adr_refs.has("ADR-0010")
    var has_task_gd_ref := test_refs.has(TASK_39_TEST_REF)
    var has_task_cs_ref := test_refs.has(TASK_39_CS_TEST_REF)
    return has_adr and has_task_gd_ref and has_task_cs_ref


func _build_real_checklist_snapshot() -> Dictionary:
    var script_exists := _read_text(VERIFY_SCRIPT_PATH) != ""
    var script_cmd := "py -3 scripts/python/verify_m1_translations.py --task-id 39 --output logs/ci/manual/task-39-translation-check.json"
    var en_map := _load_translation_values(EN_TRANSLATIONS_FILE)
    var zh_map := _load_translation_values(ZH_TRANSLATIONS_FILE)
    var missing := _collect_missing_translation_entries(REQUIRED_TRANSLATION_KEYS, en_map, zh_map)
    return {
        "script_exists": script_exists,
        "script": script_cmd,
        "steps": [
            "Extract M1-visible keys from real UI/event scripts.",
            "Compare extracted keys against Game.Godot/Translations/en.csv and zh-CN.csv.",
            "Persist result JSON for CI evidence."
        ],
        "missing_keys": missing
    }


func _execute_python_script(args: PackedStringArray) -> Dictionary:
    var output := []
    var exit_code := OS.execute(PYTHON_EXE, args, output, true)
    return {
        "exit_code": exit_code,
        "stdout": "\n".join(PackedStringArray(output))
    }


func _load_json_file(file_path: String) -> Dictionary:
    var raw := _read_text(file_path)
    if raw == "":
        return {}
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        return {}
    return parsed


func _run_translation_check(output_rel_path: String) -> Dictionary:
    var output_abs := ProjectSettings.globalize_path("res://../" + output_rel_path)
    var run := _execute_python_script(PackedStringArray([
        "-3",
        "scripts/python/verify_m1_translations.py",
        "--task-id",
        "39",
        "--output",
        output_abs
    ]))
    var payload := _load_json_file("res://../" + output_rel_path)
    return {
        "run": run,
        "payload": payload,
        "output_rel_path": output_rel_path
    }


func _run_traceability_gate(output_rel_path: String, overlays_root: String = "") -> Dictionary:
    var output_abs := ProjectSettings.globalize_path("res://../" + output_rel_path)
    var args := PackedStringArray([
        "-3",
        "scripts/python/task39_traceability_gate.py",
        "--task-id",
        "39",
        "--output",
        output_abs
    ])
    if overlays_root != "":
        args.append("--overlay-index")
        args.append(overlays_root + "/_index.md")
        args.append("--overlay-checklist")
        args.append(overlays_root + "/ACCEPTANCE_CHECKLIST.md")
    var run := _execute_python_script(args)
    var payload := _load_json_file("res://../" + output_rel_path)
    return {
        "run": run,
        "payload": payload,
        "output_rel_path": output_rel_path
    }


# acceptance: ACC:T39.1
func test_m1_visible_text_keys_exist_in_en_and_zh_cn_resources() -> void:
    var en_map := _load_translation_values(EN_TRANSLATIONS_FILE)
    var zh_map := _load_translation_values(ZH_TRANSLATIONS_FILE)
    var card_keys := _extract_card_translation_keys()
    var relic_keys := _extract_relic_translation_keys()
    var event_keys := _extract_event_translation_keys()
    var ui_prompt_keys := _extract_ui_prompt_translation_keys()
    assert_that(card_keys.is_empty()).is_false()
    assert_that(relic_keys.is_empty()).is_false()
    assert_that(event_keys.is_empty()).is_false()
    assert_that(ui_prompt_keys.is_empty()).is_false()

    var required_keys := _required_translation_keys_for_task39()
    var missing := _collect_missing_translation_entries(required_keys, en_map, zh_map)
    assert_that(missing).is_empty()


# acceptance: ACC:T39.1
func test_invalid_translation_values_are_rejected_by_validation_rule() -> void:
    assert_that(_is_translation_value_valid("event.abyss_toll.title", "", "en")).is_false()
    assert_that(_is_translation_value_valid("event.abyss_toll.title", "event.abyss_toll.title", "en")).is_false()
    assert_that(_is_translation_value_valid("event.abyss_toll.title", "???", "en")).is_false()
    assert_that(_is_translation_value_valid("event.abyss_toll.title", "锟?", "en")).is_false()
    assert_that(_is_translation_value_valid("event.abyss_toll.title", "(ZH) placeholder", "zh-CN")).is_false()


# acceptance: ACC:T39.2
func test_runtime_visible_text_refuses_hardcoded_literals() -> void:
    var scene_source := _read_text(MAIN_MENU_SCENE_FILE)
    var main_menu_script := _read_text(MAIN_MENU_SCRIPT_FILE)
    var event_scene_script := _read_text(EVENT_SCENE_SCRIPT_FILE)
    var character_select_script := _read_text(CHARACTER_SELECT_SCRIPT_FILE)
    var warrior_service_script := _read_text(WARRIOR_DECK_SERVICE_FILE)
    var relic_service_script := _read_text(STARTING_RELIC_SERVICE_FILE)

    assert_that(scene_source).is_not_equal("")
    assert_that(main_menu_script).is_not_equal("")
    assert_that(event_scene_script).is_not_equal("")
    assert_that(character_select_script).is_not_equal("")
    assert_that(warrior_service_script).is_not_equal("")
    assert_that(relic_service_script).is_not_equal("")

    assert_that(_contains_hardcoded_scene_ui_text(scene_source)).is_false()
    assert_that(_contains_hardcoded_csharp_ui_text(main_menu_script)).is_false()
    assert_that(_contains_hardcoded_csharp_ui_text(event_scene_script)).is_false()
    assert_that(_contains_hardcoded_csharp_ui_text(character_select_script)).is_false()
    assert_that(_contains_non_key_literal_in_card_or_relic_definitions(warrior_service_script)).is_false()
    assert_that(_contains_non_key_literal_in_card_or_relic_definitions(relic_service_script)).is_false()

    var bad_script_snippet := "dialog.Title = \"Hardcoded Event\";\nbutton.Text = \"Confirm\";\n"
    assert_that(_contains_hardcoded_csharp_ui_text(bad_script_snippet)).is_true()


    var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame
    var new_run_btn := menu.get_node_or_null("VBox/BtnNewRun") as Button
    var continue_btn := menu.get_node_or_null("VBox/BtnContinue") as Button
    var quit_btn := menu.get_node_or_null("VBox/BtnQuit") as Button
    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog
    assert_that(new_run_btn != null).is_true()
    assert_that(continue_btn != null).is_true()
    assert_that(quit_btn != null).is_true()
    assert_that(dialog != null).is_true()

    var allowed_values := _collect_allowed_translation_values()
    var runtime_visible_texts: Array = [
        new_run_btn.text,
        continue_btn.text,
        quit_btn.text,
        dialog.title,
        dialog.dialog_text,
        dialog.ok_button_text,
        dialog.cancel_button_text
    ]
    var violations := _collect_runtime_visible_literal_violations(runtime_visible_texts, allowed_values)
    assert_that(violations).is_empty()

    var bad_runtime_visible_texts: Array = runtime_visible_texts.duplicate()
    bad_runtime_visible_texts.append("Hardcoded Event")
    var bad_violations := _collect_runtime_visible_literal_violations(bad_runtime_visible_texts, allowed_values)
    assert_that(bad_violations.is_empty()).is_false()

    var character_select := preload(CHARACTER_SELECT_SCENE_RESOURCE).instantiate()
    add_child(auto_free(character_select))
    await get_tree().process_frame
    var difficulty_select := preload(DIFFICULTY_SELECT_SCENE_RESOURCE).instantiate()
    add_child(auto_free(difficulty_select))
    await get_tree().process_frame

    var cs_runtime_texts: Array = [
        character_select.get_node("VBox/CharacterRow/WarriorPanel/BtnWarrior").text,
        character_select.get_node("VBox/CharacterRow/MagePanel/BtnMage").text,
        character_select.get_node("VBox/CharacterRow/RoguePanel/BtnRogue").text,
        character_select.get_node("VBox/Summary/LblSummaryLine1").text
    ]
    var cs_violations := _collect_runtime_visible_literal_violations(cs_runtime_texts, allowed_values)
    assert_that(cs_violations).is_empty()

    var ds_runtime_texts: Array = [
        difficulty_select.get_node("VBox/LblTitle").text,
        difficulty_select.get_node("VBox/BtnConfirm").text,
        difficulty_select.get_node("VBox/LblDescription").text
    ]
    var ds_violations := _collect_runtime_visible_literal_violations(ds_runtime_texts, allowed_values)
    assert_that(ds_violations).is_empty()

    var event_scene := EventScene.new()
    add_child(auto_free(event_scene))
    event_scene.EnterEventForTest()
    var event_options: Array = event_scene.GetOptionViewsForTest()
    var event_visible_texts: Array = [event_scene.GetEventTitleForTest(), event_scene.GetEventDescriptionForTest()]
    for option in event_options:
        event_visible_texts.append(str(option.get("text", "")))
    var event_violations := _collect_runtime_visible_literal_violations(event_visible_texts, allowed_values)
    assert_that(event_violations).is_empty()

    var bad_extended_texts: Array = []
    bad_extended_texts.append_array(cs_runtime_texts)
    bad_extended_texts.append_array(ds_runtime_texts)
    bad_extended_texts.append_array(event_visible_texts)
    bad_extended_texts.append("Hardcoded Runtime Label")
    var bad_extended_violations := _collect_runtime_visible_literal_violations(bad_extended_texts, allowed_values)
    assert_that(bad_extended_violations.is_empty()).is_false()


# governance: traceability-linkage
func test_overlay_test_refs_trace_to_translation_and_smoke_evidence() -> void:
    var metadata := _task39_metadata()
    var test_refs := _as_string_array(metadata.get("test_refs", []))
    var overlay_index := _read_text(OVERLAY_INDEX_PATH)
    var overlay_checklist := _read_text(OVERLAY_CHECKLIST_PATH)

    assert_that(test_refs.has(TASK_39_TEST_REF)).is_true()
    assert_that(test_refs.has(TASK_39_CS_TEST_REF)).is_true()
    assert_that(overlay_index.contains("Test-Refs")).is_true()
    assert_that(overlay_checklist.contains("Test-Refs")).is_true()
    assert_that(overlay_index.contains(TASK_39_TEST_REF)).is_true()
    assert_that(overlay_checklist.contains(TASK_39_TEST_REF)).is_true()
    assert_that(overlay_index.contains(TASK_39_CS_TEST_REF)).is_true()
    assert_that(overlay_checklist.contains(TASK_39_CS_TEST_REF)).is_true()
    assert_that(overlay_index.contains("scripts/python/verify_m1_translations.py")).is_true()
    assert_that(overlay_checklist.contains("scripts/python/verify_m1_translations.py")).is_true()


# acceptance: ACC:T39.1
func test_runtime_visible_m1_ui_text_keys_are_bilingual_and_not_prompts_only() -> void:
    var ui_keys := [
        "ui.menu.confirm",
        "ui.menu.cancel",
        "ui.menu.new_run",
        "ui.menu.continue",
        "ui.menu.quit",
        "ui.character.warrior.summary.rage_buff",
        "ui.character.warrior.summary.power_window",
        "ui.character.warrior.summary.cost_burst",
        "ui.difficulty.title",
        "ui.difficulty.confirm",
        "ui.difficulty.1.desc"
    ]
    var en_map := _load_translation_values(EN_TRANSLATIONS_FILE)
    var zh_map := _load_translation_values(ZH_TRANSLATIONS_FILE)
    var missing := _collect_missing_translation_entries(ui_keys, en_map, zh_map)
    assert_that(missing).is_empty()
    assert_that(_contains_key_with_prefix(ui_keys, "ui.menu.")).is_true()
    assert_that(_contains_key_with_prefix(ui_keys, "ui.character.")).is_true()
    assert_that(_contains_key_with_prefix(ui_keys, "ui.difficulty.")).is_true()


func _contains_key_with_prefix(values: Array, prefix: String, suffix: String = "") -> bool:
    for item in values:
        var text := str(item).strip_edges()
        if text.begins_with(prefix) and (suffix == "" or text.ends_with(suffix)):
            return true
    return false


func _collect_allowed_translation_values() -> Dictionary:
    var allowed := {}
    var en_map := _load_translation_values(EN_TRANSLATIONS_FILE)
    var zh_map := _load_translation_values(ZH_TRANSLATIONS_FILE)

    for value in en_map.values():
        var text := str(value).strip_edges()
        if text != "":
            allowed[text] = true
    for value in zh_map.values():
        var text := str(value).strip_edges()
        if text != "":
            allowed[text] = true
    return allowed


func _collect_runtime_visible_literal_violations(texts: Array, allowed_values: Dictionary) -> Array[String]:
    var violations: Array[String] = []
    for item in texts:
        var text := str(item).strip_edges()
        if text == "":
            continue
        if not allowed_values.has(text) and not violations.has(text):
            violations.append(text)
    return violations


# acceptance: ACC:T39.3
func test_runtime_visible_ui_text_resolves_valid_locale_output() -> void:
    var expected := _load_translation_values(EN_TRANSLATIONS_FILE)
    var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
    add_child(auto_free(menu))
    await get_tree().process_frame

    var new_run_btn := menu.get_node_or_null("VBox/BtnNewRun") as Button
    var continue_btn := menu.get_node_or_null("VBox/BtnContinue") as Button
    var quit_btn := menu.get_node_or_null("VBox/BtnQuit") as Button
    var dialog := menu.get_node_or_null("OverwriteConfirmDialog") as ConfirmationDialog

    assert_that(new_run_btn != null).is_true()
    assert_that(continue_btn != null).is_true()
    assert_that(quit_btn != null).is_true()
    assert_that(dialog != null).is_true()

    assert_that(str(new_run_btn.text).strip_edges()).is_equal(str(expected["ui.menu.new_run"]))
    assert_that(str(continue_btn.text).strip_edges()).is_equal(str(expected["ui.menu.continue"]))
    assert_that(str(quit_btn.text).strip_edges()).is_equal(str(expected["ui.menu.quit"]))
    assert_that(str(dialog.title).strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.title"]))
    assert_that(str(dialog.dialog_text).strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.body"]))
    assert_that(str(dialog.ok_button_text).strip_edges()).is_equal(str(expected["ui.menu.confirm"]))
    assert_that(str(dialog.cancel_button_text).strip_edges()).is_equal(str(expected["ui.menu.cancel"]))

    assert_that(_is_translation_value_valid("ui.menu.new_run", str(new_run_btn.text), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.continue", str(continue_btn.text), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.quit", str(quit_btn.text), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm_overwrite.title", str(dialog.title), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm_overwrite.body", str(dialog.dialog_text), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm", str(dialog.ok_button_text), "en")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.cancel", str(dialog.cancel_button_text), "en")).is_true()

    TranslationServer.set_locale("zh-CN")
    await get_tree().process_frame
    await get_tree().process_frame

    var expected_zh := _load_translation_values(ZH_TRANSLATIONS_FILE)
    assert_that(_is_translation_value_valid("ui.menu.new_run", str(expected_zh["ui.menu.new_run"]), "zh-CN")).is_true()
    assert_that(str(new_run_btn.text).strip_edges()).is_equal(str(expected_zh["ui.menu.new_run"]))
    assert_that(str(continue_btn.text).strip_edges()).is_equal(str(expected_zh["ui.menu.continue"]))
    assert_that(str(quit_btn.text).strip_edges()).is_equal(str(expected_zh["ui.menu.quit"]))
    assert_that(str(dialog.title).strip_edges()).is_equal(str(expected_zh["ui.menu.confirm_overwrite.title"]))
    assert_that(str(dialog.dialog_text).strip_edges()).is_equal(str(expected_zh["ui.menu.confirm_overwrite.body"]))
    assert_that(str(dialog.ok_button_text).strip_edges()).is_equal(str(expected_zh["ui.menu.confirm"]))
    assert_that(str(dialog.cancel_button_text).strip_edges()).is_equal(str(expected_zh["ui.menu.cancel"]))

    assert_that(_is_translation_value_valid("ui.menu.new_run", str(new_run_btn.text), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.continue", str(continue_btn.text), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.quit", str(quit_btn.text), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm_overwrite.title", str(dialog.title), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm_overwrite.body", str(dialog.dialog_text), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.confirm", str(dialog.ok_button_text), "zh-CN")).is_true()
    assert_that(_is_translation_value_valid("ui.menu.cancel", str(dialog.cancel_button_text), "zh-CN")).is_true()

    TranslationServer.set_locale("en")
    await get_tree().process_frame
    await get_tree().process_frame

    # Assert round-trip on the same UI nodes: zh-CN -> en must restore expected en values.
    assert_that(str(new_run_btn.text).strip_edges()).is_equal(str(expected["ui.menu.new_run"]))
    assert_that(str(continue_btn.text).strip_edges()).is_equal(str(expected["ui.menu.continue"]))
    assert_that(str(quit_btn.text).strip_edges()).is_equal(str(expected["ui.menu.quit"]))
    assert_that(str(dialog.title).strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.title"]))
    assert_that(str(dialog.dialog_text).strip_edges()).is_equal(str(expected["ui.menu.confirm_overwrite.body"]))
    assert_that(str(dialog.ok_button_text).strip_edges()).is_equal(str(expected["ui.menu.confirm"]))
    assert_that(str(dialog.cancel_button_text).strip_edges()).is_equal(str(expected["ui.menu.cancel"]))

    # Runtime negative check: if translation binding breaks, text may fall back to key/literal.
    assert_that(str(new_run_btn.text).strip_edges()).is_not_equal("ui.menu.new_run")
    assert_that(str(dialog.title).strip_edges()).is_not_equal("ui.menu.confirm_overwrite.title")


# acceptance: ACC:T39.4
func test_reproducible_checklist_exists_and_reports_no_missing_keys() -> void:
    var checklist := _build_real_checklist_snapshot()
    var steps: Array = checklist.get("steps", [])
    var missing_keys: Array = checklist.get("missing_keys", [])
    assert_that(bool(checklist.get("script_exists", false))).is_true()
    assert_that(str(checklist.get("script", "")).is_empty()).is_false()
    assert_that(steps.size() >= 3).is_true()
    assert_that(missing_keys).is_empty()

    var translation_run := _run_translation_check("logs/ci/manual/task-39-translation-check-gdunit.json")
    var run := translation_run.get("run", {})
    var payload := translation_run.get("payload", {})
    assert_that(int(run.get("exit_code", -1))).is_equal(0)
    assert_that(str(payload.get("status", ""))).is_equal("ok")
    var payload_missing: Array = payload.get("missing_keys", [])
    assert_that(payload_missing).is_empty()
    var payload_required_keys: Array = payload.get("required_keys", [])
    assert_that(_contains_key_with_prefix(payload_required_keys, "card.warrior.", ".name")).is_true()
    assert_that(_contains_key_with_prefix(payload_required_keys, "relic.name.")).is_true()
    assert_that(_contains_key_with_prefix(payload_required_keys, "event.")).is_true()

    assert_that(_contains_key_with_prefix(payload_required_keys, "ui.menu.")).is_true()
    assert_that(_contains_key_with_prefix(payload_required_keys, "ui.character.")).is_true()
    assert_that(_contains_key_with_prefix(payload_required_keys, "ui.difficulty.")).is_true()

    var payload_scanned_files: Array = payload.get("scanned_files", [])
    assert_that(payload_scanned_files.has("Game.Godot/Scenes/UI/MainMenu.tscn")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scenes/UI/CharacterSelect.tscn")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scenes/UI/DifficultySelect.tscn")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scripts/UI/MainMenu.cs")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scripts/UI/CharacterSelect.cs")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scripts/UI/DifficultySelect.cs")).is_true()
    assert_that(payload_scanned_files.has("Game.Godot/Scripts/UI/EventScene.cs")).is_true()

    var payload_patterns: Array = payload.get("extraction_patterns", [])
    assert_that(payload_patterns.has("ui_key_in_tscn_pattern")).is_true()
    assert_that(payload_patterns.has("ui_key_in_resolve_call_pattern")).is_true()
    assert_that(payload_patterns.has("ui_key_in_resolve_text_call_pattern")).is_true()
    assert_that(payload_patterns.has("ui_key_literal_pattern")).is_true()

    var trace_run := _run_traceability_gate("logs/ci/manual/task-39-traceability-gate-gdunit.json")
    var trace_exec := trace_run.get("run", {})
    var trace_payload := trace_run.get("payload", {})
    assert_that(int(trace_exec.get("exit_code", -1))).is_equal(0)
    assert_that(str(trace_payload.get("status", ""))).is_equal("ok")
    var trace_errors: Array = trace_payload.get("errors", [])
    assert_that(trace_errors).is_empty()


# supplemental: hardcoded-literal-coverage
func test_cards_relics_events_and_ui_detect_hardcoded_visible_text() -> void:
    var event_scene_script := _read_text(EVENT_SCENE_SCRIPT_FILE)
    var character_select_script := _read_text(CHARACTER_SELECT_SCRIPT_FILE)
    var warrior_service_script := _read_text(WARRIOR_DECK_SERVICE_FILE)
    var relic_service_script := _read_text(STARTING_RELIC_SERVICE_FILE)
    var card_keys := _extract_card_translation_keys()
    var relic_keys := _extract_relic_translation_keys()

    assert_that(_contains_hardcoded_csharp_ui_text(event_scene_script)).is_false()
    assert_that(_contains_hardcoded_csharp_ui_text(character_select_script)).is_false()
    assert_that(_contains_non_key_literal_in_card_or_relic_definitions(warrior_service_script)).is_false()
    assert_that(_contains_non_key_literal_in_card_or_relic_definitions(relic_service_script)).is_false()
    assert_that(event_scene_script.contains("event.abyss_toll.title")).is_true()
    assert_that(character_select_script.contains("ui.character.warrior.summary.rage_buff")).is_true()
    assert_that(card_keys.is_empty()).is_false()
    assert_that(relic_keys.is_empty()).is_false()

    var bad_event_snippet := "label.Text = \"Event Start\";\n"
    var bad_character_snippet := "summary.Text = \"Rage summary\";\n"
    var bad_relic_snippet := "new StartingRelicDefinition(\"relic.fake\", \"Hardcoded Name\", \"effect.x\", new[] { \"m1\" })"
    assert_that(_contains_hardcoded_csharp_ui_text(bad_event_snippet)).is_true()
    assert_that(_contains_hardcoded_csharp_ui_text(bad_character_snippet)).is_true()
    assert_that(_contains_non_key_literal_in_card_or_relic_definitions(bad_relic_snippet)).is_true()


# governance: adr-traceability
func test_task39_artifacts_include_explicit_adr0010_traceability() -> void:
    var metadata := _task39_metadata()
    var adr_refs := _as_string_array(metadata.get("adr_refs", []))
    assert_that(adr_refs.has("ADR-0010")).is_true()
    assert_that(_has_adr_traceability_in_docs()).is_true()
    assert_that(_read_text(ADR_0010_DOC_PATH)).is_not_equal("")


# governance: gate-fail-path
func test_gate_rejects_when_overlay_or_tests_miss_adr0010_evidence() -> void:
    var metadata := _task39_metadata()
    var adr_refs := _as_string_array(metadata.get("adr_refs", []))
    var test_refs := _as_string_array(metadata.get("test_refs", []))

    assert_that(_validate_gate_contract(adr_refs, test_refs)).is_true()

    var missing_adr: Array[String] = []
    var missing_tests := [TASK_39_TEST_REF]
    assert_that(_validate_gate_contract(missing_adr, test_refs)).is_false()
    assert_that(_validate_gate_contract(adr_refs, missing_tests)).is_false()

    var bad_root := "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08-missing-anchor"
    var run := _run_traceability_gate(
        "logs/ci/manual/task-39-traceability-gate-negative.json",
        bad_root
    )
    var execution := run.get("run", {})
    var payload := run.get("payload", {})
    assert_that(int(execution.get("exit_code", 0))).is_not_equal(0)
    assert_that(str(payload.get("status", ""))).is_equal("fail")
    var errors: Array = payload.get("errors", [])
    assert_that(errors.is_empty()).is_false()
