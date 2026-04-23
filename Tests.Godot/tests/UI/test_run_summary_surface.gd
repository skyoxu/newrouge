extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const HUD_SCENE := preload("res://Game.Godot/Scenes/UI/HUD.tscn")
const COMPOSITION_ROOT_SCRIPT := preload("res://Game.Godot/Autoloads/CompositionRoot.cs")
const AUTOSAVE_PATH := "user://saves/autosave.json"

var _composition_root: Node = null
var _bus: Node = null
var _hud: Node = null


func before_test() -> void:
    _remove_autosave()
    _composition_root = COMPOSITION_ROOT_SCRIPT.new()
    _composition_root.name = "CompositionRoot"
    get_tree().get_root().add_child(auto_free(_composition_root))
    await get_tree().process_frame
    _bus = preload("res://Game.Godot/Adapters/EventBusAdapter.cs").new()
    _bus.name = "EventBus"
    get_tree().get_root().add_child(auto_free(_bus))

    _hud = HUD_SCENE.instantiate()
    add_child(auto_free(_hud))
    await get_tree().process_frame


func after_test() -> void:
    _remove_autosave()
    _hud = null
    _bus = null
    _composition_root = null
    await get_tree().process_frame


func _remove_autosave() -> void:
    var absolute_path := ProjectSettings.globalize_path(AUTOSAVE_PATH)
    if FileAccess.file_exists(AUTOSAVE_PATH):
        DirAccess.remove_absolute(absolute_path)


func _publish(type: String, payload_json: String) -> void:
    _bus.PublishSimple(type, "task66-test", payload_json)
    await get_tree().process_frame


func _wait_for_summary_text(method_name: String, expected: String) -> void:
    for _index in range(30):
        if str(_hud.call(method_name)) == expected:
            return
        await get_tree().process_frame


func _write_autosave_payload(payload: String) -> void:
    var dir := DirAccess.open("user://")
    if dir != null and not dir.dir_exists("saves"):
        dir.make_dir("saves")
    var file := FileAccess.open(AUTOSAVE_PATH, FileAccess.WRITE)
    file.store_string(payload)
    file.close()


func _sha256_hex(text: String) -> String:
    return text.sha256_text()


func _write_summary_autosave(
    run_id: String,
    difficulty_id: int,
    outcome: String,
    node_progress: int,
    reason: String
) -> void:
    var state := {
        "difficulty": {
            "difficulty_id": difficulty_id,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.%d" % difficulty_id,
            "ruleset_id": "ruleset.t66",
        },
        "run_summary": {
            "outcome": outcome,
            "node_progress": node_progress,
            "failure_or_recovery_reason": reason,
            "owner_surface": "HudOverlay",
        }
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": run_id,
        "save_point_id": "node-%d" % node_progress,
        "schema_version": "1.0.0",
        "saved_at": "2026-04-21T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))


# ACC:T66.2
func test_run_summary_surface_displays_stored_metadata_without_recompute_or_mutation() -> void:
    _write_summary_autosave(
        "run-66-a",
        7,
        "Defeat",
        4,
        "Recovered from last checkpoint"
    )

    await _publish("core.run.started", "{\"run_id\":\"run-66-a\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-66-a\",\"player_won\":false}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Defeat")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Defeat")
    assert_str(str(_hud.call("GetSummaryNodeProgressTextForTest"))).is_equal("Node Progress: 4")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).is_equal("Reason: Recovered from last checkpoint")

    var autosave_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var parsed = JSON.parse_string(autosave_raw)
    assert_int(int(parsed["state_json"].find("\"node_progress\":4"))).is_not_equal(-1)


func test_run_summary_surface_uses_stored_reason_instead_of_derived_replacement() -> void:
    _write_summary_autosave(
        "run-66-b",
        3,
        "Victory",
        8,
        "Boss defeated with one HP"
    )

    await _publish("core.run.started", "{\"run_id\":\"run-66-b\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-66-b\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryReasonTextForTest", "Reason: Boss defeated with one HP")

    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).is_equal("Reason: Boss defeated with one HP")


func test_run_summary_surface_does_not_apply_non_hud_owner_metadata() -> void:
    var state := {
        "difficulty": {
            "difficulty_id": 4,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.4",
            "ruleset_id": "ruleset.t66",
        },
        "run_summary": {
            "outcome": "Victory",
            "node_progress": 5,
            "failure_or_recovery_reason": "Should not appear on HUD owner mismatch",
            "owner_surface": "MainMenuMetadataPanel",
        }
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": "run-66-owner-mismatch",
        "save_point_id": "node-5",
        "schema_version": "1.0.0",
        "saved_at": "2026-04-21T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))

    await _publish("core.run.started", "{\"run_id\":\"run-66-owner-mismatch\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-66-owner-mismatch\",\"player_won\":true}")
    await get_tree().process_frame

    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Unknown")
    assert_str(str(_hud.call("GetSummaryNodeProgressTextForTest"))).is_equal("Node Progress: 0")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).is_equal("Reason: No stored run summary reason.")
