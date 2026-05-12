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


func _write_summary_autosave_with_deferred_metadata_probe(
    run_id: String,
    outcome: String,
    node_progress: int
) -> void:
    var state := {
        "difficulty": {
            "difficulty_id": 9,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.9",
            "ruleset_id": "ruleset.t91",
        },
        "run_summary": {
            "outcome": outcome,
            "node_progress": node_progress,
            "failure_or_recovery_reason": "Deferred metadata should remain unchanged",
            "owner_surface": "HudOverlay",
        },
        "deferred_metadata_probe": {
            "reward_metadata": {"locked": true, "offer_ids": ["r1", "r2", "r3"]},
            "relic_metadata": {"granted": ["Relic-A"], "equipped": ["Relic-A"]},
            "resume_metadata": {"checkpoint": "node-%d" % node_progress, "version": 1}
        }
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": run_id,
        "save_point_id": "node-%d" % node_progress,
        "schema_version": "1.0.0",
        "saved_at": "2026-05-01T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))

func _write_summary_autosave_with_partial_metadata_probe(
    run_id: String,
    outcome: String,
    node_progress: int,
    include_reward: bool,
    include_relic: bool,
    include_resume: bool
) -> void:
    var deferred_probe := {}
    if include_reward:
        deferred_probe["reward_metadata"] = {"offer_ids": ["r1"]}
    if include_relic:
        deferred_probe["relic_metadata"] = {"equipped": ["Relic-A"]}
    if include_resume:
        deferred_probe["resume_metadata"] = {"checkpoint": "node-%d" % node_progress}

    var state := {
        "difficulty": {
            "difficulty_id": 9,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.9",
            "ruleset_id": "ruleset.t91",
        },
        "run_summary": {
            "outcome": outcome,
            "node_progress": node_progress,
            "failure_or_recovery_reason": "Partial metadata probe should be reflected per field",
            "owner_surface": "HudOverlay",
        },
        "deferred_metadata_probe": deferred_probe
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": run_id,
        "save_point_id": "node-%d" % node_progress,
        "schema_version": "1.0.0",
        "saved_at": "2026-05-01T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))


# ACC:T66.2
# ACC:T91.1
# ACC:T91.2
# ACC:T91.4
# ACC:T91.6
# ACC:T113.1
# ACC:T107.1
# ACC:T107.3
# ACC:T107.5
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
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Missing")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Missing")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Missing")

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

# ACC:T113.2
func test_run_summary_surface_does_not_display_resume_evidence_when_stored_reason_is_missing() -> void:
    var state := {
        "difficulty": {
            "difficulty_id": 8,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.8",
            "ruleset_id": "ruleset.t113",
        },
        "run_summary": {
            "outcome": "Victory",
            "node_progress": 9,
            "owner_surface": "HudOverlay",
        }
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": "run-113-missing-reason",
        "save_point_id": "node-9",
        "schema_version": "1.0.0",
        "saved_at": "2026-05-01T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))

    await _publish("core.run.started", "{\"run_id\":\"run-113-missing-reason\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-113-missing-reason\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryReasonTextForTest", "Reason: No stored run summary reason.")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Unknown")
    assert_str(str(_hud.call("GetSummaryNodeProgressTextForTest"))).is_equal("Node Progress: 0")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).is_equal("Reason: No stored run summary reason.")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).contains("No stored run summary reason.")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).not_contains("Recovered from")
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Missing")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Missing")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Missing")

    var autosave_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var parsed = JSON.parse_string(autosave_raw)
    assert_int(int(parsed["state_json"].find("\"failure_or_recovery_reason\""))).is_equal(-1)


# ACC:T91.2
func test_run_summary_surface_opens_from_victory_flow_with_stored_summary_without_mutation() -> void:
    _write_summary_autosave(
        "run-91-victory",
        6,
        "Victory",
        10,
        "Victory stored summary should be reused"
    )

    await _publish("core.run.started", "{\"run_id\":\"run-91-victory\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-91-victory\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Victory")
    assert_str(str(_hud.call("GetSummaryNodeProgressTextForTest"))).is_equal("Node Progress: 10")
    assert_str(str(_hud.call("GetSummaryReasonTextForTest"))).is_equal("Reason: Victory stored summary should be reused")

    var autosave_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var parsed = JSON.parse_string(autosave_raw)
    assert_int(int(parsed["state_json"].find("\"outcome\":\"Victory\""))).is_not_equal(-1)
    assert_int(int(parsed["state_json"].find("\"node_progress\":10"))).is_not_equal(-1)


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


# ACC:T91.4
func test_run_summary_surface_uses_deterministic_placeholders_when_required_summary_fields_are_missing() -> void:
    var state := {
        "difficulty": {
            "difficulty_id": 5,
            "label_key": "ui.difficulty.label",
            "description_key": "ui.difficulty.5",
            "ruleset_id": "ruleset.t91",
        },
        "run_summary": {
            "failure_or_recovery_reason": "Missing outcome and node progress should keep placeholders",
            "owner_surface": "HudOverlay",
        }
    }
    var state_json := JSON.stringify(state)
    var autosave := {
        "run_id": "run-91-missing-required-fields",
        "save_point_id": "node-missing",
        "schema_version": "1.0.0",
        "saved_at": "2026-05-01T00:00:00Z",
        "state_json": state_json,
        "integrity_hash": _sha256_hex(state_json),
    }
    _write_autosave_payload(JSON.stringify(autosave))

    await _publish("core.run.started", "{\"run_id\":\"run-91-missing-required-fields\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-91-missing\",\"player_won\":true}")
    await get_tree().process_frame

    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Unknown")
    assert_str(str(_hud.call("GetSummaryNodeProgressTextForTest"))).is_equal("Node Progress: 0")

    var autosave_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var parsed = JSON.parse_string(autosave_raw)
    assert_int(int(parsed["state_json"].find("\"outcome\""))).is_equal(-1)
    assert_int(int(parsed["state_json"].find("\"node_progress\""))).is_equal(-1)

# ACC:T91.3
# ACC:T107.4
func test_run_summary_surface_keeps_deferred_metadata_probe_unchanged_on_victory_and_defeat_flows() -> void:
    _write_summary_autosave_with_deferred_metadata_probe("run-91-probe-victory", "Victory", 11)
    var before_victory_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var before_victory_state := str(JSON.parse_string(before_victory_raw)["state_json"])

    await _publish("core.run.started", "{\"run_id\":\"run-91-probe-victory\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-91-probe-victory\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    var after_victory_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var after_victory_state := str(JSON.parse_string(after_victory_raw)["state_json"])
    assert_str(after_victory_state).contains("\"deferred_metadata_probe\"")
    assert_str(after_victory_state).contains("\"reward_metadata\"")
    assert_str(after_victory_state).contains("\"relic_metadata\"")
    assert_str(after_victory_state).contains("\"resume_metadata\"")
    assert_str(after_victory_state).is_equal(before_victory_state)
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Present")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Present")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Present")

    _write_summary_autosave_with_deferred_metadata_probe("run-91-probe-defeat", "Defeat", 3)
    var before_defeat_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var before_defeat_state := str(JSON.parse_string(before_defeat_raw)["state_json"])

    await _publish("core.run.started", "{\"run_id\":\"run-91-probe-defeat\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-91-probe-defeat\",\"player_won\":false}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Defeat")

    var after_defeat_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var after_defeat_state := str(JSON.parse_string(after_defeat_raw)["state_json"])
    assert_str(after_defeat_state).contains("\"deferred_metadata_probe\"")
    assert_str(after_defeat_state).contains("\"reward_metadata\"")
    assert_str(after_defeat_state).contains("\"relic_metadata\"")
    assert_str(after_defeat_state).contains("\"resume_metadata\"")
    assert_str(after_defeat_state).is_equal(before_defeat_state)
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Present")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Present")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Present")


# ACC:T130.2
func test_run_summary_surface_declares_required_standalone_surfaces() -> void:
    var summary_panel := _hud.get_node_or_null("RunSummaryPanel")
    var settlement_panel := _hud.get_node_or_null("RunSummaryPanel/VBox/SettlementMetadataPanel")
    var resume_panel := _hud.get_node_or_null("RunSummaryPanel/VBox/ResumeEvidencePanel")
    assert_object(summary_panel).is_not_null()
    assert_object(settlement_panel).is_not_null()
    assert_object(resume_panel).is_not_null()
    assert_bool(summary_panel.visible).is_false()
    assert_bool(settlement_panel.visible).is_true()
    assert_bool(resume_panel.visible).is_true()


# ACC:T130.7
func test_run_summary_surface_satisfies_scope_traceability_in_same_run_context() -> void:
    _write_summary_autosave_with_partial_metadata_probe("run-130-scope-traceability", "Victory", 12, true, false, true)
    await _publish("core.run.started", "{\"run_id\":\"run-130-scope-traceability\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-scope-traceability\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetSummaryOutcomeTextForTest"))).is_equal("Outcome: Victory")
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Present")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Missing")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Present")


# ACC:T130.4
func test_run_summary_surface_stays_hidden_without_stored_run_data() -> void:
    await _publish("core.run.started", "{\"run_id\":\"run-130-no-autosave\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-no-autosave\",\"player_won\":true}")
    await get_tree().process_frame

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_false()


# ACC:T130.5
func test_run_summary_surface_marks_reward_only_metadata_as_partial_missing() -> void:
    _write_summary_autosave_with_partial_metadata_probe("run-130-reward-only", "Victory", 6, true, false, false)
    await _publish("core.run.started", "{\"run_id\":\"run-130-reward-only\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-reward-only\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Present")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Missing")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Missing")


# ACC:T130.5
func test_run_summary_surface_marks_relic_only_metadata_as_partial_missing() -> void:
    _write_summary_autosave_with_partial_metadata_probe("run-130-relic-only", "Victory", 6, false, true, false)
    await _publish("core.run.started", "{\"run_id\":\"run-130-relic-only\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-relic-only\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Missing")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Present")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Missing")


# ACC:T130.5
func test_run_summary_surface_marks_resume_only_metadata_as_partial_missing() -> void:
    _write_summary_autosave_with_partial_metadata_probe("run-130-resume-only", "Victory", 6, false, false, true)
    await _publish("core.run.started", "{\"run_id\":\"run-130-resume-only\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-resume-only\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    assert_bool(bool(_hud.call("IsRunSummaryVisibleForTest"))).is_true()
    assert_str(str(_hud.call("GetRewardMetadataTextForTest"))).is_equal("Reward Metadata: Missing")
    assert_str(str(_hud.call("GetRelicMetadataTextForTest"))).is_equal("Relic Metadata: Missing")
    assert_str(str(_hud.call("GetResumeEvidenceTextForTest"))).is_equal("Resume Evidence: Present")


# ACC:T130.8
func test_run_summary_surface_interaction_does_not_mutate_autosave_state() -> void:
    _write_summary_autosave_with_deferred_metadata_probe("run-130-no-side-effects", "Victory", 7)
    var before_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var before_state := str(JSON.parse_string(before_raw)["state_json"])

    await _publish("core.run.started", "{\"run_id\":\"run-130-no-side-effects\"}")
    await _publish("core.combat.ended", "{\"combat_id\":\"c-130-no-side-effects\",\"player_won\":true}")
    await _wait_for_summary_text("GetSummaryOutcomeTextForTest", "Outcome: Victory")

    var summary_panel := _hud.get_node("RunSummaryPanel") as Control
    summary_panel.visible = false
    await get_tree().process_frame
    summary_panel.visible = true
    await get_tree().process_frame

    var after_raw := FileAccess.get_file_as_string(ProjectSettings.globalize_path(AUTOSAVE_PATH))
    var after_state := str(JSON.parse_string(after_raw)["state_json"])

    assert_str(after_state).is_equal(before_state)

