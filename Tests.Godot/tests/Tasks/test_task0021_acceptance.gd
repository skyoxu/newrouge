extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RestFlowDouble:
    var cards: Dictionary = {}
    var pending_card_id: String = ""
    var pending_route: String = ""
    var upgrade_hits: int = 0

    func _init() -> void:
        cards = {
            "c1": {"upgraded": false},
            "c2": {"upgraded": false}
        }

    func available_rest_options() -> Array[String]:
        # Red-first gap: upgrade is intentionally absent to force a deterministic failure.
        return ["heal", "remove_curse"]

    func can_upgrade_card(card_id: String) -> bool:
        return cards.has(card_id) and not bool(cards[card_id].get("upgraded", false))

    func begin_upgrade(card_id: String, route: String) -> bool:
        if not can_upgrade_card(card_id):
            return false
        if route != "route_a" and route != "route_b":
            return false
        pending_card_id = card_id
        pending_route = route
        return true

    func cancel_before_confirm() -> void:
        pending_card_id = ""
        pending_route = ""

    func confirm_upgrade() -> bool:
        if pending_card_id == "":
            return false
        cards[pending_card_id]["upgraded"] = true
        upgrade_hits += 1
        pending_card_id = ""
        pending_route = ""
        return true

    func immutable_warning_text(key: String) -> String:
        var table := {
            "rest.upgrade.irreversible": "This action cannot be undone."
        }
        return str(table.get(key, "[missing translation]"))

    func snapshot() -> Dictionary:
        return cards.duplicate(true)

class GateSummaryValidatorDouble:
    var required_adr: Array[String] = ["ADR-0033", "ADR-0010"]
    var required_chapters: Array[String] = ["CH01", "CH06", "CH10", "CH07", "CH05"]

    func _same_set(left: Array, right: Array) -> bool:
        if left.size() != right.size():
            return false
        for item in left:
            if not right.has(item):
                return false
        return true

    func validate(summary: Dictionary) -> Dictionary:
        var reasons: Array[String] = []
        var exit_code := 0

        var adr_refs := summary.get("adr_refs", [])
        if not _same_set(adr_refs, required_adr):
            reasons.append("adr_refs mismatch")

        var chapter_refs := summary.get("chapter_refs", [])
        if not _same_set(chapter_refs, required_chapters):
            reasons.append("chapter_refs mismatch")

        var executions := summary.get("executions", [])
        if executions.is_empty():
            reasons.append("no execution evidence")

        for row_variant in executions:
            var row: Dictionary = row_variant
            if not row.has("executed") or not row.has("pass_fail"):
                reasons.append("execution row missing executed/pass_fail")
                continue

            var required := bool(row.get("required", true))
            var executed := bool(row.get("executed", false))
            var pass_fail := str(row.get("pass_fail", ""))

            if required and (not executed or pass_fail != "pass"):
                reasons.append("required evidence not passing")
            if (not required) and (not executed) and pass_fail != "skipped":
                reasons.append("optional evidence must be skipped when not executed")

        if summary.get("missing_required_links", []).size() > 0:
            reasons.append("missing required back-links")

        if reasons.size() > 0:
            exit_code = 2

        return {
            "exit_code": exit_code,
            "reasons": reasons
        }

func _count_upgraded_cards(state: Dictionary) -> int:
    var count := 0
    for card_id in state.keys():
        if bool(state[card_id].get("upgraded", false)):
            count += 1
    return count

func _base_gate_summary() -> Dictionary:
    return {
        "adr_refs": ["ADR-0033", "ADR-0010"],
        "chapter_refs": ["CH01", "CH06", "CH10", "CH07", "CH05"],
        "executions": [
            {
                "name": "Tests.Godot/tests/Tasks/test_task0021_acceptance.gd",
                "required": true,
                "executed": true,
                "pass_fail": "pass"
            }
        ],
        "missing_required_links": []
    }

# acceptance: ACC:T21.1
func test_rest_scene_exposes_upgrade_heal_and_remove_curse_options() -> void:
    var flow := RestFlowDouble.new()
    var options := flow.available_rest_options()

    assert(options.has("upgrade"), "Upgrade must be visible and selectable in Rest scene.")
    assert(options.has("heal"), "Heal must be visible and selectable in Rest scene.")
    assert(options.has("remove_curse"), "Remove curse must be visible and selectable in Rest scene.")
    assert(options.size() == 3, "Rest scene must expose exactly three options.")

# acceptance: ACC:T21.2
func test_upgrade_cancel_before_confirm_keeps_cards_and_resources_unchanged() -> void:
    var flow := RestFlowDouble.new()
    var before_cards := flow.snapshot()

    var started := flow.begin_upgrade("c1", "route_a")
    assert(started, "Upgrade flow must start with a valid card and route.")

    flow.cancel_before_confirm()
    var after_cards := flow.snapshot()

    assert(before_cards == after_cards, "Cancel before confirm must not mutate any card state.")
    assert(flow.upgrade_hits == 0, "Cancel before confirm must not emit an upgrade result.")

# acceptance: ACC:T21.3
func test_upgrade_irreversible_prompt_uses_resolved_translation_text() -> void:
    var flow := RestFlowDouble.new()
    var text := flow.immutable_warning_text("rest.upgrade.irreversible")

    assert(text.length() > 0, "Warning text must not be empty.")
    assert(text.find("rest.upgrade.irreversible") == -1, "UI must not render translation key names.")
    assert(text.find("{{") == -1, "UI must not show placeholder tokens.")
    assert(not text.begins_with("["), "UI must not show fallback error-like text.")

# acceptance: ACC:T21.6
func test_upgrade_confirm_mutates_only_selected_single_card() -> void:
    var flow := RestFlowDouble.new()
    var before := flow.snapshot()

    assert(flow.begin_upgrade("c1", "route_b"), "Upgrade flow should allow selecting route_b.")
    assert(flow.confirm_upgrade(), "Confirm should succeed after selecting card and route.")
    var after := flow.snapshot()

    assert(bool(after["c1"]["upgraded"]), "Selected card must be upgraded.")
    assert(after["c2"]["upgraded"] == before["c2"]["upgraded"], "Unselected card must remain unchanged.")
    assert(_count_upgraded_cards(after) == 1, "Exactly one card must be upgraded.")

# acceptance: ACC:T21.9
func test_gate_summary_requires_exact_adr_refs_and_fails_closed_on_mismatch() -> void:
    var validator := GateSummaryValidatorDouble.new()
    var summary := _base_gate_summary()
    summary["adr_refs"] = ["ADR-0033"]

    var result := validator.validate(summary)
    assert(int(result["exit_code"]) != 0, "Gate must exit non-zero when adr_refs mismatch.")

# acceptance: ACC:T21.10
func test_gate_summary_requires_exact_chapter_refs_and_fails_closed_on_mismatch() -> void:
    var validator := GateSummaryValidatorDouble.new()
    var summary := _base_gate_summary()
    summary["chapter_refs"] = ["CH01", "CH06"]

    var result := validator.validate(summary)
    assert(int(result["exit_code"]) != 0, "Gate must exit non-zero when chapter_refs mismatch.")

# acceptance: ACC:T21.11
func test_required_test_refs_must_be_executed_and_passed() -> void:
    var validator := GateSummaryValidatorDouble.new()
    var summary := _base_gate_summary()
    summary["executions"] = [
        {
            "name": "Tests.Godot/tests/Tasks/test_task0021_acceptance.gd",
            "required": true,
            "executed": false,
            "pass_fail": "skipped"
        }
    ]

    var result := validator.validate(summary)
    assert(int(result["exit_code"]) != 0, "Gate must fail when required test evidence is not executed and passed.")

# acceptance: ACC:T21.12
func test_optional_switch_off_must_record_skipped_not_pass() -> void:
    var validator := GateSummaryValidatorDouble.new()

    var valid_summary := _base_gate_summary()
    valid_summary["executions"] = [
        {
            "name": "optional_feature_guard",
            "required": false,
            "executed": false,
            "pass_fail": "skipped"
        }
    ]
    var valid_result := validator.validate(valid_summary)
    assert(int(valid_result["exit_code"]) == 0, "Optional disabled evidence with skipped status should not fail gate.")

    var invalid_summary := _base_gate_summary()
    invalid_summary["executions"] = [
        {
            "name": "optional_feature_guard",
            "required": false,
            "executed": false,
            "pass_fail": "pass"
        }
    ]
    var invalid_result := validator.validate(invalid_summary)
    assert(int(invalid_result["exit_code"]) != 0, "Optional disabled evidence must not be marked as pass.")

# acceptance: ACC:T21.13
func test_missing_required_links_or_evidence_fields_fail_closed() -> void:
    var validator := GateSummaryValidatorDouble.new()
    var summary := _base_gate_summary()
    summary["executions"] = [
        {
            "name": "required_evidence",
            "required": true,
            "executed": true
        }
    ]
    summary["missing_required_links"] = ["test_refs"]

    var result := validator.validate(summary)
    assert(int(result["exit_code"]) != 0, "Missing required links or execution fields must fail closed.")
