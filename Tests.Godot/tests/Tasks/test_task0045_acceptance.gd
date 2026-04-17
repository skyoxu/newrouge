extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const HUD_SCENE := preload("res://Game.Godot/Scenes/UI/HUD.tscn")
const TASK_FILE := "res://../.taskmaster/tasks/tasks_gameplay.json"
const THIS_TEST_REF := "Tests.Godot/tests/Tasks/test_task0045_acceptance.gd"
const CORE_TEST_REF := "Game.Core.Tests/Tasks/Task0045AcceptanceTests.cs"
const TRANSLATION_FALLBACK_FILE := "res://Game.Godot/Translations/en.csv"

var _bus: Node = null
var _hud: Node = null
var _translation_fallbacks := {}
var _custom_translation: Translation = null
var _saved_locale := ""


func before_test() -> void:
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))

    _hud = HUD_SCENE.instantiate()
    add_child(auto_free(_hud))
    await get_tree().process_frame


func after_test() -> void:
    if _custom_translation != null:
        TranslationServer.remove_translation(_custom_translation)
        _custom_translation = null

    if _saved_locale != "":
        TranslationServer.set_locale(_saved_locale)
        _saved_locale = ""

    _hud = null
    _bus = null
    await get_tree().process_frame


func _publish(type: String, payload_json: String) -> void:
    _bus.PublishSimple(type, "task45-test", payload_json)
    await get_tree().process_frame


func _hud_difficulty_text() -> String:
    return str(_hud.call("GetHudDifficultyTextForTest"))


func _summary_difficulty_text() -> String:
    return str(_hud.call("GetSummaryDifficultyTextForTest"))


func _summary_visible() -> bool:
    return bool(_hud.call("IsRunSummaryVisibleForTest"))


func _summary_title_text() -> String:
    if _hud == null:
        return ""
    var node := _hud.get_node_or_null("RunSummaryPanel/VBox/TitleLabel")
    if node == null:
        return ""
    return str(node.text)


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


func _load_task45_record() -> Dictionary:
    var raw := _read_text(TASK_FILE)
    if raw.strip_edges() == "":
        return {}

    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_ARRAY:
        return {}

    for item in parsed:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        if int(item.get("taskmaster_id", -1)) == 45:
            return item
    return {}


func _acceptance_joined_text(task_record: Dictionary) -> String:
    var acceptance = task_record.get("acceptance", [])
    if typeof(acceptance) != TYPE_ARRAY:
        return ""

    var joined := ""
    for item in acceptance:
        joined += str(item) + "\n"
    return joined


func _extract_difficulty_phrase(text: String) -> String:
    var sep := text.find(":")
    if sep < 0:
        return text.strip_edges()
    return text.substr(sep + 1).strip_edges()


func _translation_fallback(key: String) -> String:
    if _translation_fallbacks.is_empty():
        var raw := _read_text(TRANSLATION_FALLBACK_FILE)
        for line in raw.split("\n"):
            var trimmed := line.strip_edges()
            if trimmed == "" or trimmed.begins_with("key,value"):
                continue
            var sep := trimmed.find(",")
            if sep <= 0:
                continue
            var k := trimmed.substr(0, sep).strip_edges()
            var v := trimmed.substr(sep + 1).strip_edges()
            if k != "" and v != "":
                _translation_fallbacks[k] = v
    return str(_translation_fallbacks.get(key, key))


func _resolve_translated_text(key: String) -> String:
    var translated := TranslationServer.translate(key)
    if translated != key:
        return translated
    return _translation_fallback(key)


func _expected_difficulty_text(difficulty_id: int) -> String:
    var label := _resolve_translated_text("ui.difficulty.label")
    var difficulty := _resolve_translated_text("ui.difficulty.%d" % difficulty_id)
    if label.strip_edges() == "":
        return difficulty
    return "%s: %s" % [label, difficulty]


# ACC:T45.1
func test_hud_and_run_summary_show_same_selected_difficulty_on_run_start() -> void:
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":2}")
    await _publish("core.run.started", "{\"run_id\":\"r-45-1\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-45\",\"player_won\":true}")

    var expected := _expected_difficulty_text(2)
    assert_bool(_summary_visible()).is_true()
    assert_str(_hud_difficulty_text()).is_equal(expected)
    assert_str(_summary_difficulty_text()).is_equal(expected)


# ACC:T45.2
func test_difficulty_display_remains_unchanged_through_flow_and_player_operations() -> void:
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":3}")
    await _publish("core.run.started", "{\"run_id\":\"r-45-2\"}")
    var initial_hud := _hud_difficulty_text()
    var initial_summary := _summary_difficulty_text()

    await _publish("core.score.updated", "{\"value\":10}")
    await _publish("core.health.updated", "{\"value\":95}")
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":9}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-45-2\",\"player_won\":false}")

    assert_str(_hud_difficulty_text()).is_equal(initial_hud)
    assert_str(_summary_difficulty_text()).is_equal(initial_summary)
    assert_str(_summary_difficulty_text()).is_equal(_hud_difficulty_text())
    assert_str(_hud_difficulty_text()).is_equal(_expected_difficulty_text(3))


# ACC:T45.3
func test_hud_and_summary_render_difficulty_via_translation_keys_not_raw_literals() -> void:
    _saved_locale = TranslationServer.get_locale()
    _custom_translation = Translation.new()
    _custom_translation.set_locale("task45-sentinel")
    _custom_translation.add_message("ui.difficulty.label", "Task45LabelSentinel")
    _custom_translation.add_message("ui.difficulty.1", "Task45DifficultyOneSentinel")
    _custom_translation.add_message("ui.run.summary.title", "Task45SummaryTitleSentinel")
    TranslationServer.add_translation(_custom_translation)
    TranslationServer.set_locale(_custom_translation.get_locale())

    if _hud != null:
        _hud.queue_free()
        await get_tree().process_frame
    _hud = HUD_SCENE.instantiate()
    add_child(auto_free(_hud))
    await get_tree().process_frame

    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":1}")
    await _publish("core.run.started", "{\"run_id\":\"r-45-3\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-45-3\",\"player_won\":true}")

    var hud_text := _hud_difficulty_text()
    var summary_text := _summary_difficulty_text()
    var expected := "Task45LabelSentinel: Task45DifficultyOneSentinel"

    assert_str(hud_text).is_equal(expected)
    assert_str(summary_text).is_equal(expected)
    assert_str(_summary_title_text()).is_equal("Task45SummaryTitleSentinel")
    assert_str(hud_text).is_not_equal("ui.difficulty.label: ui.difficulty.1")


# ACC:T45.4
func test_hud_displays_selected_difficulty_after_run_start() -> void:
    assert_bool(_hud.has_node("TopBar/HBox/DifficultyLabel")).is_true()
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":10}")
    await _publish("core.run.started", "{\"run_id\":\"r-45-4\"}")

    assert_str(_hud_difficulty_text()).is_equal(_expected_difficulty_text(10))


# ACC:T45.5
func test_hud_difficulty_display_stays_constant_during_run_progression() -> void:
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":2}")
    assert_str(_hud_difficulty_text()).is_equal(_expected_difficulty_text(2))

    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":7}")
    assert_str(_hud_difficulty_text()).is_equal(_expected_difficulty_text(7))

    await _publish("core.run.started", "{\"run_id\":\"r-45-5\"}")
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":4}")
    await _publish("core.score.updated", "{\"value\":21}")
    await _publish("core.health.updated", "{\"value\":81}")
    await _publish("core.score.updated", "{\"value\":45}")

    assert_str(_hud_difficulty_text()).is_equal(_expected_difficulty_text(7))


# ACC:T45.6
func test_run_summary_panel_exists_and_is_visible_in_summary_stage() -> void:
    await _publish("core.run.difficulty.selected", "{\"difficulty_id\":5}")

    assert_bool(_summary_visible()).is_false()
    await _publish("core.run.started", "{\"run_id\":\"r-45-6\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-45-6\",\"player_won\":true}")
    assert_bool(_summary_visible()).is_true()
    assert_str(_summary_difficulty_text()).is_equal(_expected_difficulty_text(5))
    assert_str(_summary_difficulty_text()).is_equal(_hud_difficulty_text())


# governance refs
func test_task45_acceptance_lists_refs_for_task0045_tests() -> void:
    var task_record := _load_task45_record()
    assert_bool(task_record.is_empty()).is_false()

    var test_refs = task_record.get("test_refs", [])
    assert_bool(typeof(test_refs) == TYPE_ARRAY).is_true()
    if typeof(test_refs) == TYPE_ARRAY:
        assert_bool(test_refs.has(THIS_TEST_REF)).is_true()
        assert_bool(test_refs.has(CORE_TEST_REF)).is_true()

    var acceptance_text := _acceptance_joined_text(task_record)
    assert_bool(acceptance_text.contains(THIS_TEST_REF)).is_true()
    assert_bool(acceptance_text.contains(CORE_TEST_REF)).is_true()
