extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const EVENT_SCENE = preload("res://Game.Godot/Scenes/Event.tscn")
const EXPECTED_ADR_REFS = ["ADR-0032", "ADR-0010"]
const EXPECTED_CHAPTER_REFS = ["CH01", "CH06", "CH10", "CH07", "CH05"]
const EXPECTED_TEST_REFS = [
	"Tests.Godot/tests/Tasks/test_task0022_acceptance.gd",
	"Tests.Godot/tests/Scenes/Event/test_event_scene_hp_loss_cost_applies_immediately.gd",
	"Tests.Godot/tests/Scenes/Event/test_event_scene_curse_card_cost_applies_immediately.gd",
	"Game.Core.Tests/Tasks/Task0022ContractRefsTests.cs",
]
const TITLE_KEY = "event.abyss_toll.title"
const DESCRIPTION_KEY = "event.abyss_toll.description"
const LOSE_HP_KEY = "event.option.lose_hp"
const TAKE_CURSE_KEY = "event.option.take_curse"
const TITLE_PATH = "VBox/LblTitle"
const DESCRIPTION_PATH = "VBox/LblDescription"
const LOSE_HP_BUTTON_PATH = "VBox/Options/BtnLoseHp"
const TAKE_CURSE_BUTTON_PATH = "VBox/Options/BtnTakeCurse"


func _new_scene() -> Control:
	var scene = EVENT_SCENE.instantiate() as Control
	add_child(auto_free(scene))
	return scene


func _title_label(scene: Control) -> Label:
	return scene.get_node(TITLE_PATH) as Label


func _description_label(scene: Control) -> Label:
	return scene.get_node(DESCRIPTION_PATH) as Label


func _lose_hp_button(scene: Control) -> Button:
	return scene.get_node(LOSE_HP_BUTTON_PATH) as Button


func _take_curse_button(scene: Control) -> Button:
	return scene.get_node(TAKE_CURSE_BUTTON_PATH) as Button


func _option_ids(options: Array) -> Array:
	var ids: Array = []
	for option in options:
		ids.append(str(option.get("id", "")))
	return ids


func _has_dark_cost(options: Array, cost_type: String) -> bool:
	for option in options:
		for cost in option.get("dark_costs", []):
			if str(cost.get("type", "")) == cost_type:
				return true
	return false


func _load_task22_metadata() -> Dictionary:
	var path = ProjectSettings.globalize_path("res://../.taskmaster/tasks/tasks_gameplay.json")
	if not FileAccess.file_exists(path):
		return {}
	var raw = FileAccess.get_file_as_string(path)
	var parsed = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_ARRAY:
		return {}
	for item in parsed:
		if int(item.get("taskmaster_id", -1)) == 22:
			return item
	return {}


func _translations_dir() -> String:
	return ProjectSettings.globalize_path("res://../Game.Godot/Translations")


func _find_locale_csv(locale_code: String) -> String:
	var locale_lower = locale_code.to_lower()
	var dir = DirAccess.open(_translations_dir())
	if dir == null:
		return ""
	dir.list_dir_begin()
	var entry = dir.get_next()
	while entry != "":
		if not dir.current_is_dir():
			var lower = entry.to_lower()
			if lower.ends_with(".csv") and (lower == locale_lower + ".csv" or lower.begins_with(locale_lower + "_") or lower.findn(locale_lower) != -1):
				dir.list_dir_end()
				return _translations_dir() + "/" + entry
		entry = dir.get_next()
	dir.list_dir_end()
	return ""


func _load_csv_map(path: String) -> Dictionary:
	var translations = {}
	if path == "" or not FileAccess.file_exists(path):
		return translations
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return translations
	while not file.eof_reached():
		var raw_line = file.get_line().strip_edges()
		if raw_line == "" or raw_line.begins_with("#"):
			continue
		var parts = raw_line.split(",", false, 2)
		if parts.size() < 2:
			continue
		var key = str(parts[0]).strip_edges().trim_prefix("\"").trim_suffix("\"")
		var value = str(parts[1]).strip_edges().trim_prefix("\"").trim_suffix("\"")
		if key.to_lower() == "key":
			continue
		if key != "":
			translations[key] = value
	return translations


func _create_translation(locale_code: String, translations: Dictionary) -> Translation:
	var translation = Translation.new()
	translation.set_locale(locale_code)
	for key in translations.keys():
		translation.add_message(str(key), str(translations[key]))
	return translation


func _install_runtime_translations(en_map: Dictionary, zh_map: Dictionary) -> Dictionary:
	var installed: Array[Translation] = []
	var previous_locale = TranslationServer.get_locale()
	var en_translation = _create_translation("en", en_map)
	var zh_translation = _create_translation("zh-CN", zh_map)
	var zh_cn_translation = _create_translation("zh_CN", zh_map)
	installed.append(en_translation)
	installed.append(zh_translation)
	installed.append(zh_cn_translation)
	for translation in installed:
		TranslationServer.add_translation(translation)
	return {
		"installed": installed,
		"previous_locale": previous_locale,
	}


func _remove_runtime_translations(context: Dictionary) -> void:
	var installed = context.get("installed", [])
	for translation in installed:
		TranslationServer.remove_translation(translation)
	var previous_locale = str(context.get("previous_locale", "en"))
	TranslationServer.set_locale(previous_locale)


func _fail_result() -> Dictionary:
	return {
		"executed": true,
		"pass_fail": "fail",
		"exit_code": 1,
	}


func _validate_gate_summary(summary: Dictionary) -> Dictionary:
	if bool(summary.get("optional_enabled", true)) == false:
		return {
			"executed": false,
			"pass_fail": "skipped",
			"exit_code": 1,
		}

	if not summary.has("adr_refs"):
		return _fail_result()
	if not summary.has("chapter_refs"):
		return _fail_result()

	if summary.get("adr_refs", []) != EXPECTED_ADR_REFS:
		return _fail_result()
	if summary.get("chapter_refs", []) != EXPECTED_CHAPTER_REFS:
		return _fail_result()

	var test_results = summary.get("test_results", null)
	if typeof(test_results) != TYPE_ARRAY:
		return _fail_result()

	for ref in EXPECTED_TEST_REFS:
		var matched = false
		for row in test_results:
			if str(row.get("path", "")) != ref:
				continue
			matched = true
			if bool(row.get("executed", false)) != true:
				return _fail_result()
			if str(row.get("pass_fail", "")) != "pass":
				return _fail_result()
		if not matched:
			return _fail_result()

	return {
		"executed": true,
		"pass_fail": "pass",
		"exit_code": 0,
	}


# acceptance: ACC:T22.1
func test_event_entry_shows_title_description_and_two_dark_cost_examples() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("EnterEventForTest")

	var title_label = _title_label(scene)
	var description_label = _description_label(scene)
	var lose_hp_button = _lose_hp_button(scene)
	var take_curse_button = _take_curse_button(scene)
	var options = scene.call("GetOptionViewsForTest") as Array

	assert_bool(scene.visible).is_true()
	assert_bool(title_label.visible).is_true()
	assert_bool(description_label.visible).is_true()
	assert_bool(lose_hp_button.visible).is_true()
	assert_bool(take_curse_button.visible).is_true()
	assert_that(title_label.text.length() > 0).is_true()
	assert_that(description_label.text.length() > 0).is_true()
	assert_that(lose_hp_button.text.length() > 0).is_true()
	assert_that(take_curse_button.text.length() > 0).is_true()
	assert_that(options.size() >= 2).is_true()
	assert_that(_has_dark_cost(options, "hp_loss")).is_true()
	assert_that(_has_dark_cost(options, "curse_add")).is_true()


# acceptance: ACC:T22.2
func test_options_lock_on_entry_and_choice_writes_persisted_state_immediately() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("EnterEventForTest")
	var first_ids = _option_ids(scene.call("GetOptionViewsForTest"))

	assert_that(first_ids.size() >= 2).is_true()
	assert_bool(bool(scene.call("ChooseOptionForTest", "lose_hp"))).is_true()
	assert_str(str(scene.call("GetSelectedOptionIdForTest"))).is_equal("lose_hp")
	assert_str(str(scene.call("GetPersistedSelectedOptionIdForTest"))).is_equal("lose_hp")
	assert_int(int(scene.call("GetCurrentHpForTest"))).is_equal(17)


# gate: T22:GATE:reenter-lock
func test_reenter_scene_keeps_previous_choice_locked() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("EnterEventForTest")
	var first_ids = _option_ids(scene.call("GetOptionViewsForTest"))
	assert_bool(bool(scene.call("ChooseOptionForTest", "lose_hp"))).is_true()
	scene.call("ClearRuntimeCacheForTest")

	var reentered_scene = _new_scene()
	await get_tree().process_frame
	var second_ids = _option_ids(reentered_scene.call("GetOptionViewsForTest"))
	assert_that(second_ids).is_equal(first_ids)
	assert_str(str(reentered_scene.call("GetSelectedOptionIdForTest"))).is_equal("lose_hp")
	assert_int(int(reentered_scene.call("GetCurrentHpForTest"))).is_equal(17)

	assert_bool(bool(reentered_scene.call("ChooseOptionForTest", "take_curse"))).is_false()
	assert_str(str(reentered_scene.call("GetSelectedOptionIdForTest"))).is_equal("lose_hp")


# gate: T22:GATE:persist-fail-signal
func test_choice_commit_must_fail_closed_when_persist_write_fails() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("SetPersistFailureForTest", true)

	assert_bool(bool(scene.call("ChooseOptionForTest", "lose_hp"))).is_false()
	assert_int(int(scene.call("GetCurrentHpForTest"))).is_equal(20)
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(0)
	assert_str(str(scene.call("GetSelectedOptionIdForTest"))).is_equal("")
	assert_str(str(scene.call("GetPersistedSelectedOptionIdForTest"))).is_equal("")
	assert_that(str(scene.call("GetLastPersistErrorForTest")).length() > 0).is_true()

	scene.call("SetPersistFailureForTest", false)


# acceptance: ACC:T22.3
func test_all_display_texts_come_from_translation_and_change_with_locale() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	var en_map = _load_csv_map(_find_locale_csv("en"))
	var zh_map = _load_csv_map(_find_locale_csv("zh-CN"))
	assert_bool(en_map.has(TITLE_KEY)).is_true()
	assert_bool(en_map.has(DESCRIPTION_KEY)).is_true()
	assert_bool(en_map.has(LOSE_HP_KEY)).is_true()
	assert_bool(en_map.has(TAKE_CURSE_KEY)).is_true()
	assert_bool(zh_map.has(TITLE_KEY)).is_true()
	assert_bool(zh_map.has(DESCRIPTION_KEY)).is_true()
	assert_bool(zh_map.has(LOSE_HP_KEY)).is_true()
	assert_bool(zh_map.has(TAKE_CURSE_KEY)).is_true()
	var context = _install_runtime_translations(en_map, zh_map)

	scene.call("SetLocaleForTest", "en")
	var en_title = _title_label(scene).text
	var en_description = _description_label(scene).text
	var en_lose_hp_text = _lose_hp_button(scene).text
	var en_take_curse_text = _take_curse_button(scene).text

	scene.call("SetLocaleForTest", "zh-CN")
	var zh_title = _title_label(scene).text
	var zh_description = _description_label(scene).text
	var zh_lose_hp_text = _lose_hp_button(scene).text
	var zh_take_curse_text = _take_curse_button(scene).text

	assert_that(zh_title).is_not_equal(en_title)
	assert_that(zh_description).is_not_equal(en_description)
	assert_that(zh_lose_hp_text).is_not_equal(en_lose_hp_text)
	assert_that(zh_take_curse_text).is_not_equal(en_take_curse_text)
	assert_that(en_title).is_not_equal(TITLE_KEY)
	assert_that(zh_title).is_not_equal(TITLE_KEY)
	assert_that(en_description).is_not_equal(DESCRIPTION_KEY)
	assert_that(zh_description).is_not_equal(DESCRIPTION_KEY)
	assert_that(en_lose_hp_text).is_not_equal(LOSE_HP_KEY)
	assert_that(zh_lose_hp_text).is_not_equal(LOSE_HP_KEY)
	assert_that(en_take_curse_text).is_not_equal(TAKE_CURSE_KEY)
	assert_that(zh_take_curse_text).is_not_equal(TAKE_CURSE_KEY)
	assert_that(en_title).is_equal(str(en_map[TITLE_KEY]))
	assert_that(zh_title).is_equal(str(zh_map[TITLE_KEY]))
	assert_that(en_description).is_equal(str(en_map[DESCRIPTION_KEY]))
	assert_that(zh_description).is_equal(str(zh_map[DESCRIPTION_KEY]))
	assert_that(en_lose_hp_text).is_equal(str(en_map[LOSE_HP_KEY]))
	assert_that(zh_lose_hp_text).is_equal(str(zh_map[LOSE_HP_KEY]))
	assert_that(en_take_curse_text).is_equal(str(en_map[TAKE_CURSE_KEY]))
	assert_that(zh_take_curse_text).is_equal(str(zh_map[TAKE_CURSE_KEY]))
	_remove_runtime_translations(context)


# acceptance: ACC:T22.6
func test_event_scene_controls_are_visible_and_interactable_before_choice() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)

	var title_label = _title_label(scene)
	var description_label = _description_label(scene)
	var lose_hp_button = _lose_hp_button(scene)
	var take_curse_button = _take_curse_button(scene)

	assert_bool(scene.visible).is_true()
	assert_bool(title_label.visible).is_true()
	assert_bool(description_label.visible).is_true()
	assert_bool(lose_hp_button.visible).is_true()
	assert_bool(take_curse_button.visible).is_true()
	assert_bool(lose_hp_button.disabled).is_false()
	assert_bool(take_curse_button.disabled).is_false()


# gate: T22:GATE:execution-repeatability
func test_option_execution_applies_hp_loss_and_curse_add_repeatably() -> void:
	var hp_scene = _new_scene()
	await get_tree().process_frame
	hp_scene.call("ResetStateForTest", 20, 0)
	assert_bool(bool(hp_scene.call("ChooseOptionForTest", "lose_hp"))).is_true()
	assert_int(int(hp_scene.call("GetCurrentHpForTest"))).is_equal(17)

	var curse_scene = _new_scene()
	await get_tree().process_frame
	curse_scene.call("ResetStateForTest", 20, 0)
	assert_bool(bool(curse_scene.call("ChooseOptionForTest", "take_curse"))).is_true()
	assert_int(int(curse_scene.call("GetCurseCardCountForTest"))).is_equal(1)


# gate: T22:GATE:reenter-lock
func test_reenter_keeps_lock_and_refuses_reselection() -> void:
	var scene = _new_scene()
	await get_tree().process_frame
	scene.call("ResetStateForTest", 20, 0)
	scene.call("ChooseOptionForTest", "lose_hp")

	var hp_after_first = int(scene.call("GetCurrentHpForTest"))
	var curse_after_first = int(scene.call("GetCurseCardCountForTest"))

	scene.call("EnterEventForTest")
	assert_bool(bool(scene.call("ChooseOptionForTest", "take_curse"))).is_false()
	assert_int(int(scene.call("GetCurrentHpForTest"))).is_equal(hp_after_first)
	assert_int(int(scene.call("GetCurseCardCountForTest"))).is_equal(curse_after_first)


# gate: T22:GATE:adr-refs
func test_gate_summary_requires_exact_adr_refs_and_mismatch_fails() -> void:
	var result = _validate_gate_summary({
		"adr_refs": ["ADR-0032"],
		"chapter_refs": EXPECTED_CHAPTER_REFS,
		"test_results": [],
	})
	assert_that(int(result.get("exit_code", 0)) != 0).is_true()
	assert_that(str(result.get("pass_fail", ""))).is_equal("fail")


# gate: T22:GATE:chapter-refs
func test_gate_summary_requires_exact_chapter_refs_and_mismatch_fails() -> void:
	var result = _validate_gate_summary({
		"adr_refs": EXPECTED_ADR_REFS,
		"chapter_refs": ["CH01", "CH06", "CH10"],
		"test_results": [],
	})
	assert_that(int(result.get("exit_code", 0)) != 0).is_true()
	assert_that(str(result.get("pass_fail", ""))).is_equal("fail")


# gate: T22:GATE:test-refs
func test_missing_or_failed_test_refs_must_fail_task_gate() -> void:
	var result = _validate_gate_summary({
		"adr_refs": EXPECTED_ADR_REFS,
		"chapter_refs": EXPECTED_CHAPTER_REFS,
		"test_results": [
			{
				"path": "Tests.Godot/tests/Tasks/test_task0022_acceptance.gd",
				"executed": false,
				"pass_fail": "skipped",
			}
		],
	})
	assert_that(int(result.get("exit_code", 0)) != 0).is_true()
	assert_that(str(result.get("pass_fail", ""))).is_equal("fail")


# gate: T22:GATE:optional-switch
func test_disabled_optional_switch_reports_skipped_not_pass() -> void:
	var result = _validate_gate_summary({
		"optional_enabled": false,
		"adr_refs": EXPECTED_ADR_REFS,
		"chapter_refs": EXPECTED_CHAPTER_REFS,
	})
	assert_bool(bool(result.get("executed", true))).is_false()
	assert_that(str(result.get("pass_fail", ""))).is_equal("skipped")


# gate: T22:GATE:fail-closed
func test_missing_required_links_or_artifacts_fails_closed_with_nonzero_exit() -> void:
	var result = _validate_gate_summary({
		"chapter_refs": EXPECTED_CHAPTER_REFS,
	})
	assert_that(int(result.get("exit_code", 0)) != 0).is_true()
	assert_that(str(result.get("pass_fail", ""))).is_equal("fail")
	assert_that(result.has("warning")).is_false()


func test_task_metadata_contains_expected_refs_for_task22() -> void:
	var task = _load_task22_metadata()
	assert_that(task.is_empty()).is_false()
	assert_that(task.get("adr_refs", [])).is_equal(EXPECTED_ADR_REFS)
	assert_that(task.get("chapter_refs", [])).is_equal(EXPECTED_CHAPTER_REFS)
	assert_that(task.get("test_refs", [])).is_equal(EXPECTED_TEST_REFS)

