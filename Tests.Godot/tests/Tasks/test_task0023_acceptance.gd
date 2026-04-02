extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAIN_MENU_SCENE_RESOURCE := "res://Game.Godot/Scenes/UI/MainMenu.tscn"
const MAIN_MENU_PLAY_BUTTON_PATH := "VBox/BtnPlay"
const APPROVED_PREFIXES := ["ui.", "card.", "relic.", "event.", "etc."]

func _translations_dir() -> String:
	return ProjectSettings.globalize_path("res://../Game.Godot/Translations")

func _find_locale_csv(locale_code: String) -> String:
	var locale_lower := locale_code.to_lower()
	var dir := DirAccess.open(_translations_dir())
	if dir == null:
		return ""
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if not dir.current_is_dir():
			var lower := entry.to_lower()
			if lower.ends_with(".csv") and (lower == locale_lower + ".csv" or lower.begins_with(locale_lower + "_") or lower.findn(locale_lower) != -1):
				dir.list_dir_end()
				return _translations_dir() + "/" + entry
		entry = dir.get_next()
	dir.list_dir_end()
	return ""

func _load_csv_map(path: String) -> Dictionary:
	var translations := {}
	if path == "" or not FileAccess.file_exists(path):
		return translations
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return translations
	while not file.eof_reached():
		var raw_line := file.get_line().strip_edges()
		if raw_line == "" or raw_line.begins_with("#"):
			continue
		var parts := raw_line.split(",", false, 2)
		if parts.size() < 2:
			continue
		var key := str(parts[0]).strip_edges().trim_prefix("\"").trim_suffix("\"")
		var value := str(parts[1]).strip_edges().trim_prefix("\"").trim_suffix("\"")
		if key.to_lower() == "key":
			continue
		if key != "":
			translations[key] = value
	return translations

func _find_first_shared_ui_key(en_map: Dictionary, zh_map: Dictionary) -> String:
	for key in en_map.keys():
		var text_key := str(key)
		if text_key.begins_with("ui.") and zh_map.has(text_key):
			return text_key
	return ""

func _find_shared_placeholder_key(en_map: Dictionary, zh_map: Dictionary) -> String:
	for key in en_map.keys():
		var text_key := str(key)
		if not text_key.begins_with("ui."):
			continue
		if not zh_map.has(text_key):
			continue
		var en_value := str(en_map[text_key])
		var zh_value := str(zh_map[text_key])
		if en_value.find("{name}") != -1 and zh_value.find("{name}") != -1:
			return text_key
	return ""

func _collect_domain_keys(translations: Dictionary) -> Array[String]:
	var keys: Array[String] = []
	for key in translations.keys():
		var text_key := str(key)
		if _has_approved_prefix(text_key):
			keys.append(text_key)
	return keys

func _has_approved_prefix(key: String) -> bool:
	for prefix in APPROVED_PREFIXES:
		if key.begins_with(prefix):
			return true
	return false

func _collect_invalid_keys(translations: Dictionary) -> Array[String]:
	var invalid: Array[String] = []
	for key in translations.keys():
		var text_key := str(key)
		if not _has_approved_prefix(text_key):
			invalid.append(text_key)
	return invalid

func _render_for_key(translations: Dictionary, key: String) -> String:
	if translations.has(key):
		return str(translations[key])
	return key

func _is_render_text_localized(key: String, rendered: String) -> bool:
	var normalized := rendered.strip_edges()
	if normalized == "":
		return false
	if normalized == key:
		return false
	if normalized.find("{") != -1 or normalized.find("}") != -1:
		return false
	if normalized.begins_with("missing:") or normalized.begins_with("fallback:"):
		return false
	return true

func _contains_hardcoded_ui_literal(source_text: String) -> bool:
	var regex := RegEx.new()
	var error := regex.compile('text\\s*=\\s*"[^"]+"')
	if error != OK:
		return false
	return regex.search(source_text) != null

func _create_translation(locale_code: String, translations: Dictionary) -> Translation:
	var translation := Translation.new()
	translation.set_locale(locale_code)
	for key in translations.keys():
		translation.add_message(str(key), str(translations[key]))
	return translation

func _install_runtime_translations(en_map: Dictionary, zh_map: Dictionary) -> Dictionary:
	var installed: Array[Translation] = []
	var previous_locale := TranslationServer.get_locale()
	var en_translation := _create_translation("en", en_map)
	var zh_translation := _create_translation("zh-CN", zh_map)
	var zh_cn_translation := _create_translation("zh_CN", zh_map)
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
	var previous_locale := str(context.get("previous_locale", "en"))
	TranslationServer.set_locale(previous_locale)

func _render_for_locale(node: Node, key: String, locale_code: String) -> String:
	TranslationServer.set_locale(locale_code)
	return str(node.tr(key))

func _render_button_text_for_locale(button: Button, key: String, locale_code: String) -> String:
	TranslationServer.set_locale(locale_code)
	button.text = str(button.tr(key))
	return button.text

# acceptance: ACC:T23.1
func test_has_en_and_zh_cn_translation_csv_and_localized_ui_value() -> void:
	var en_path := _find_locale_csv("en")
	var zh_path := _find_locale_csv("zh-CN")
	assert_that(en_path).is_not_equal("")
	assert_that(zh_path).is_not_equal("")
	var en_map := _load_csv_map(en_path)
	var zh_map := _load_csv_map(zh_path)
	var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
	add_child(auto_free(menu))
	await get_tree().process_frame
	assert_bool(menu.has_node(MAIN_MENU_PLAY_BUTTON_PATH)).is_true()
	if not menu.has_node(MAIN_MENU_PLAY_BUTTON_PATH):
		return
	var button := menu.get_node(MAIN_MENU_PLAY_BUTTON_PATH) as Button
	var ui_key := button.text.strip_edges()
	assert_that(ui_key).is_not_equal("")
	assert_that(en_map.has(ui_key)).is_true()
	assert_that(zh_map.has(ui_key)).is_true()
	var translation_context := _install_runtime_translations(en_map, zh_map)
	var rendered_en := _render_button_text_for_locale(button, ui_key, "en")
	var rendered_zh := _render_button_text_for_locale(button, ui_key, "zh-CN")
	_remove_runtime_translations(translation_context)
	assert_that(rendered_en).is_equal(str(en_map[ui_key]))
	assert_that(rendered_zh).is_equal(str(zh_map[ui_key]))
	assert_that(_is_render_text_localized(ui_key, rendered_en)).is_true()
	assert_that(_is_render_text_localized(ui_key, rendered_zh)).is_true()

# acceptance: ACC:T23.2
func test_translation_keys_follow_approved_domain_prefixes() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	var invalid_en := _collect_invalid_keys(en_map)
	var invalid_zh := _collect_invalid_keys(zh_map)
	assert_that(invalid_en).is_empty()
	assert_that(invalid_zh).is_empty()

# support: translation coverage sanity checks
func test_acceptance_coverage_includes_loading_and_key_validation_paths() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	assert_that(en_map.size()).is_greater(0)
	assert_that(zh_map.size()).is_greater(0)
	assert_that(_collect_invalid_keys(en_map)).is_empty()
	assert_that(_collect_invalid_keys(zh_map)).is_empty()
	var placeholder_key := _find_shared_placeholder_key(en_map, zh_map)
	assert_that(placeholder_key).is_not_equal("")

# acceptance: ACC:T23.3
func test_approved_domain_key_sets_match_between_en_and_zh_cn() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	var en_domain_keys := _collect_domain_keys(en_map)
	var zh_domain_keys := _collect_domain_keys(zh_map)
	var missing_in_zh: Array[String] = []
	var missing_in_en: Array[String] = []
	for key in en_domain_keys:
		if not zh_map.has(key):
			missing_in_zh.append(key)
	for key in zh_domain_keys:
		if not en_map.has(key):
			missing_in_en.append(key)
	assert_that(missing_in_zh).is_empty()
	assert_that(missing_in_en).is_empty()

# acceptance: ACC:T23.4
func test_named_placeholder_renders_runtime_value_for_en_and_zh_cn() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	var placeholder_key := _find_shared_placeholder_key(en_map, zh_map)
	assert_that(placeholder_key).is_not_equal("")
	var context := _install_runtime_translations(en_map, zh_map)
	var preview := Label.new()
	add_child(auto_free(preview))

	TranslationServer.set_locale("en")
	preview.text = str(preview.tr(placeholder_key)).format({"name": "Alice"})
	assert_that(preview.text.find("{name}") == -1).is_true()
	assert_that(preview.text.find("Alice") != -1).is_true()
	assert_that(_is_render_text_localized(placeholder_key, preview.text)).is_true()

	TranslationServer.set_locale("zh-CN")
	preview.text = str(preview.tr(placeholder_key)).format({"name": "Alice"})
	assert_that(preview.text.find("{name}") == -1).is_true()
	assert_that(preview.text.find("Alice") != -1).is_true()
	assert_that(_is_render_text_localized(placeholder_key, preview.text)).is_true()

	preview.text = str(preview.tr(placeholder_key))
	assert_that(preview.text.find("{name}") != -1).is_true()
	assert_that(_is_render_text_localized(placeholder_key, preview.text)).is_false()
	_remove_runtime_translations(context)

# acceptance: ACC:T23.6
func test_same_ui_node_renders_exact_expected_text_for_en_and_zh_cn() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
	add_child(auto_free(menu))
	await get_tree().process_frame
	assert_bool(menu.has_node(MAIN_MENU_PLAY_BUTTON_PATH)).is_true()
	if not menu.has_node(MAIN_MENU_PLAY_BUTTON_PATH):
		return
	var button := menu.get_node(MAIN_MENU_PLAY_BUTTON_PATH) as Button
	var ui_key := button.text.strip_edges()
	assert_that(ui_key).is_not_equal("")
	assert_that(en_map.has(ui_key)).is_true()
	assert_that(zh_map.has(ui_key)).is_true()
	var expected_en := _render_for_key(en_map, ui_key)
	var expected_zh := _render_for_key(zh_map, ui_key)
	var translation_context := _install_runtime_translations(en_map, zh_map)
	var rendered_en := _render_button_text_for_locale(button, ui_key, "en")
	var rendered_zh := _render_button_text_for_locale(button, ui_key, "zh-CN")
	_remove_runtime_translations(translation_context)
	assert_that(rendered_en).is_equal(expected_en)
	assert_that(rendered_zh).is_equal(expected_zh)
	assert_that(rendered_en).is_not_equal(ui_key)
	assert_that(rendered_zh).is_not_equal(ui_key)

# acceptance: ACC:T23.7
func test_rejects_key_name_or_fallback_render_output() -> void:
	var key := "ui.main_menu.start"
	var rendered := key
	assert_that(_is_render_text_localized(key, rendered)).is_false()

func test_runtime_render_rejects_key_name_or_fallback_outputs() -> void:
	var en_map := _load_csv_map(_find_locale_csv("en"))
	var zh_map := _load_csv_map(_find_locale_csv("zh-CN"))
	var menu := preload(MAIN_MENU_SCENE_RESOURCE).instantiate()
	add_child(auto_free(menu))
	await get_tree().process_frame
	var context := _install_runtime_translations(en_map, zh_map)
	var missing_key := "ui.this.key.does.not.exist"
	var fallback_render := _render_for_locale(menu, missing_key, "en")
	_remove_runtime_translations(context)
	assert_that(_is_render_text_localized(missing_key, fallback_render)).is_false()

func test_refuses_key_name_placeholder_and_fallback_text() -> void:
	var key := "ui.combat.result"
	assert_that(_is_render_text_localized(key, key)).is_false()
	assert_that(_is_render_text_localized(key, "Victory {count}")).is_false()
	assert_that(_is_render_text_localized(key, "fallback:" + key)).is_false()

# acceptance: ACC:T23.8
func test_rejects_unapproved_prefixes_and_hardcoded_ui_literals() -> void:
	var key_map := {
		"ui.menu.start": "Start",
		"legacy.menu.exit": "Exit"
	}
	var invalid := _collect_invalid_keys(key_map)
	assert_that(invalid.has("legacy.menu.exit")).is_true()
	var script_like_source := "title.text = \"Start Game\"\ntitle.text = tr(\"ui.menu.start\")\n"
	assert_that(_contains_hardcoded_ui_literal(script_like_source)).is_true()
