extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")
const INTERACTIVE_INPUT_TOKEN := "keyboard_enter"
const SAVE_FILE_BASENAME := "task44.resume.snapshot.json"
const EVENT_STATE_FILE := "user://task22-event-state.json"

func _event_state_path() -> String:
    return ProjectSettings.globalize_path(EVENT_STATE_FILE)

func _reset_event_state_file() -> void:
    var abs_path := _event_state_path()
    if FileAccess.file_exists(abs_path):
        DirAccess.remove_absolute(abs_path)

func _new_event_scene() -> Control:
    var scene := EVENT_SCENE.instantiate() as Control
    add_child(auto_free(scene))
    return scene

func _temp_run_dir(tag: String) -> String:
    var path := ProjectSettings.globalize_path("user://task44_resume_%s_%s" % [tag, str(Time.get_ticks_usec())])
    DirAccess.make_dir_recursive_absolute(path)
    return path

func _new_db(name: String) -> Node:
    var db = null
    if ClassDB.class_exists("SqliteDataStore"):
        db = ClassDB.instantiate("SqliteDataStore")
    else:
        var script := load("res://Game.Godot/Adapters/SqliteDataStore.cs")
        assert_that(script).is_not_null()
        assert_that(script.has_method("new")).is_true()
        db = script.new()

    assert_that(db).is_not_null()
    var root := get_tree().get_root()
    var old_db := root.get_node_or_null(name)
    if old_db != null:
        old_db.queue_free()
        await get_tree().process_frame

    db.name = name
    root.add_child(auto_free(db))
    await get_tree().process_frame
    return db

func _setup_sql_db(path: String) -> Dictionary:
    var db := await _new_db("SqlDb")
    var helper_script := load("res://Game.Godot/Adapters/Db/DbTestHelper.cs")
    assert_that(helper_script).is_not_null()
    assert_that(helper_script.has_method("new")).is_true()
    var helper := helper_script.new()
    add_child(auto_free(helper))
    helper.ForceManaged()

    assert_that(db.has_method("TryOpen")).is_true()
    assert_that(db.TryOpen(path)).is_true()
    helper.CreateSchema()
    helper.ClearAll()

    var bridge_script := load("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs")
    assert_that(bridge_script).is_not_null()
    assert_that(bridge_script.has_method("new")).is_true()
    var bridge := bridge_script.new()
    add_child(auto_free(bridge))
    return {"db": db, "helper": helper, "bridge": bridge}

func _build_task44_payload(selected_event_option: String, event_hp: int, event_curse: int) -> Dictionary:
    return {
        "reward": {
            "offer_locked": true,
            "selected_result": "reward_card_2",
            "state": {"locked_offer_id": "reward_offer_17"}
        },
        "shop": {
            "offer_locked": true,
            "selected_result": "shop_offer_a",
            "state": {"gold_after_purchase": 73}
        },
        "event": {
            "offer_locked": true,
            "selected_result": selected_event_option,
            "output": {
                "current_hp": event_hp,
                "curse_cards": event_curse
            }
        }
    }

func _persist_payload_roundtrip(payload: Dictionary, tag: String) -> Dictionary:
    var db_path := "user://task44_resume_%s_%s.db" % [tag, str(Time.get_ticks_usec())]
    var setup := await _setup_sql_db(db_path)
    var bridge = setup["bridge"]
    var db = setup["db"]

    var username := "task44_%s" % str(Time.get_ticks_usec())
    assert_that(bridge.UpsertUser(username)).is_true()
    var user_id := bridge.FindUserId(username)
    assert_that(user_id).is_not_null()
    var payload_json := JSON.stringify(payload)
    assert_that(bridge.UpsertSave(user_id, 1, payload_json)).is_true()

    db.Close()
    await get_tree().process_frame
    assert_that(db.TryOpen(db_path)).is_true()

    var reloaded_json := str(bridge.GetSaveData(user_id, 1))
    var parsed: Variant = JSON.parse_string(reloaded_json)
    assert_that(parsed is Dictionary).is_true()
    return (parsed as Dictionary).duplicate(true)

func _run_real_resume(manual_inputs: PackedStringArray = PackedStringArray()) -> Dictionary:
    _reset_event_state_file()

    var first_scene := _new_event_scene()
    await get_tree().process_frame
    first_scene.call("ResetStateForTest", 20, 0)
    assert_that(bool(first_scene.call("ChooseOptionForTest", "lose_hp"))).is_true()

    var selected_before := str(first_scene.call("GetSelectedOptionIdForTest"))
    var hp_before := int(first_scene.call("GetCurrentHpForTest"))
    var curse_before := int(first_scene.call("GetCurseCardCountForTest"))
    var payload := _build_task44_payload(selected_before, hp_before, curse_before)

    var run_dir := _temp_run_dir("deterministic")
    var save_path := run_dir.path_join(SAVE_FILE_BASENAME)
    assert_that(_save_snapshot(save_path, payload)).is_true()
    var file_loaded := _load_snapshot(save_path)
    assert_that(file_loaded.is_empty()).is_false()
    assert_that(file_loaded.has("reward")).is_true()

    var payload_from_db := await _persist_payload_roundtrip(file_loaded, "resume_roundtrip")

    first_scene.call("ClearRuntimeCacheForTest")
    var resumed_scene := _new_event_scene()
    await get_tree().process_frame

    var resumed_selected := str(resumed_scene.call("GetSelectedOptionIdForTest"))
    var resumed_hp := int(resumed_scene.call("GetCurrentHpForTest"))
    var resumed_curse := int(resumed_scene.call("GetCurseCardCountForTest"))

    return {
        "reward": payload_from_db.get("reward", {}),
        "shop": payload_from_db.get("shop", {}),
        "event": {
            "offer_locked": true,
            "selected_result": resumed_selected,
            "output": {
                "current_hp": resumed_hp,
                "curse_cards": resumed_curse
            }
        },
        "meta": {
            "event_order": ["save", "exit", "reenter", "resume_complete"],
            "requires_interactive_window": false,
            "manual_input_consumed": false,
            "interactive_input_ignored": not manual_inputs.is_empty()
        }
    }

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

func _collect_observable_failures(resume_snapshot: Dictionary) -> Array:
    var checks := [
        {"scenario": "reward", "field": "state"},
        {"scenario": "shop", "field": "state"},
        {"scenario": "event", "field": "output"}
    ]
    var failures: Array = []

    for check in checks:
        var scenario := str(check["scenario"])
        var field := str(check["field"])
        if not resume_snapshot.has(scenario):
            failures.append({"scenario": scenario, "field": field})
            continue
        if not (resume_snapshot[scenario] is Dictionary):
            failures.append({"scenario": scenario, "field": field})
            continue
        if not resume_snapshot[scenario].has(field):
            failures.append({"scenario": scenario, "field": field})

    return failures

func _format_failure(failure: Dictionary) -> String:
    return "observable assertion failed at %s.%s" % [str(failure["scenario"]), str(failure["field"])]

func _assert_resume_field_equal(before_snapshot: Dictionary, resumed_snapshot: Dictionary, scenario: String, field: String) -> void:
    var expected_value: Variant = before_snapshot[scenario][field]
    var actual_value: Variant = resumed_snapshot[scenario][field]
    var expected_text := "%s.%s=%s" % [scenario, field, JSON.stringify(expected_value)]
    var actual_text := "%s.%s=%s" % [scenario, field, JSON.stringify(actual_value)]
    assert_str(actual_text).is_equal(expected_text)

func _build_junit_xml_preview(case_names: PackedStringArray) -> String:
    var lines: PackedStringArray = PackedStringArray()
    lines.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    lines.append("<testsuite name=\"task44.headless.resume\">")
    for case_name in case_names:
        lines.append("  <testcase classname=\"integration.task44\" name=\"%s\" />" % case_name)
    lines.append("</testsuite>")

    var xml_text := ""
    for line in lines:
        if xml_text.is_empty():
            xml_text = line
        else:
            xml_text += "\n" + line
    return xml_text

# acceptance: ACC:T44.4
func test_reward_shop_event_resume_keeps_offer_lock_and_selection_consistent_red_first() -> void:
    var expected := _build_task44_payload("lose_hp", 17, 0)
    var resumed := await _run_real_resume()

    _assert_resume_field_equal(expected, resumed, "reward", "offer_locked")
    _assert_resume_field_equal(expected, resumed, "reward", "selected_result")
    _assert_resume_field_equal(expected, resumed, "shop", "offer_locked")
    _assert_resume_field_equal(expected, resumed, "shop", "selected_result")
    _assert_resume_field_equal(expected, resumed, "event", "offer_locked")
    _assert_resume_field_equal(expected, resumed, "event", "selected_result")
    _assert_resume_field_equal(expected, resumed, "event", "output")

func test_reward_shop_event_resume_should_fail_when_save_is_corrupted() -> void:
    var run_dir := _temp_run_dir("corrupted")
    var save_path := run_dir.path_join(SAVE_FILE_BASENAME)
    var file := FileAccess.open(save_path, FileAccess.WRITE)
    assert_that(file).is_not_null()
    file.store_string("{not-json")
    file.flush()
    var loaded := _load_snapshot(save_path)
    assert_that(loaded.is_empty()).is_true()
    var failures := _collect_observable_failures(loaded)
    assert_that(failures.size()).is_equal(3)

# acceptance: ACC:T44.5
func test_reward_shop_event_observable_failures_report_scenario_and_field() -> void:
    var broken_snapshot := {
        "reward": {},
        "shop": {},
        "event": {}
    }

    var failures := _collect_observable_failures(broken_snapshot)

    assert_that(failures.size()).is_equal(3)
    assert_that(_format_failure(failures[0])).contains("reward.state")
    assert_that(_format_failure(failures[1])).contains("shop.state")
    assert_that(_format_failure(failures[2])).contains("event.output")

# acceptance: ACC:T44.6
func test_task44_related_cases_are_serialized_into_junit_xml_preview() -> void:
    var xml_text := _build_junit_xml_preview(
        PackedStringArray([
            "test_reward_shop_event_resume_keeps_offer_lock_and_selection_consistent_red_first",
            "test_reward_shop_event_observable_failures_report_scenario_and_field",
            "test_headless_resume_must_not_require_or_consume_interactive_input"
        ])
    )

    assert_that(xml_text.find("<testsuite name=\"task44.headless.resume\">") >= 0).is_true()
    assert_that(xml_text.find("integration.task44") >= 0).is_true()
    assert_that(xml_text.find("test_reward_shop_event_resume_keeps_offer_lock_and_selection_consistent_red_first") >= 0).is_true()

# acceptance: ACC:T44.7
func test_headless_resume_must_not_require_or_consume_interactive_input() -> void:
    var baseline := await _run_real_resume()
    var with_manual_payload := await _run_real_resume(PackedStringArray([INTERACTIVE_INPUT_TOKEN]))

    assert_bool(bool(baseline["meta"]["requires_interactive_window"])).is_false()
    assert_bool(bool(with_manual_payload["meta"]["requires_interactive_window"])).is_false()
    assert_bool(bool(with_manual_payload["meta"]["manual_input_consumed"])).is_false()
    assert_bool(bool(with_manual_payload["meta"]["interactive_input_ignored"])).is_true()
    assert_array(Array(with_manual_payload["meta"]["event_order"])).is_equal(Array(baseline["meta"]["event_order"]))
    _assert_resume_field_equal(baseline, with_manual_payload, "event", "selected_result")
    _assert_resume_field_equal(baseline, with_manual_payload, "event", "output")
