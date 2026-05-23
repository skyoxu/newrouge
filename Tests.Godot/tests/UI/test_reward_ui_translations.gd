extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"
const EN_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://../Game.Godot/Translations/zh-CN.csv"

const EXPECTED_BINDINGS := {
	"VBox/Title": "ui.reward.title",
	"VBox/Actions/ConfirmButton": "ui.reward.confirm",
	"VBox/Actions/SkipButton": "ui.reward.skip",
	"VBox/Feedback": "ui.reward.feedback.select_default",
	"RootMargin/VBox/Title": "ui.reward.title"
}

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
	var values: Dictionary = {}
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

func _translations_for_locale(locale: String) -> Dictionary:
	if locale.to_lower().begins_with("zh"):
		return _load_translation_values(ZH_TRANSLATIONS_FILE)
	return _load_translation_values(EN_TRANSLATIONS_FILE)

func _is_raw_translation_key(text: String) -> bool:
	var regex := RegEx.new()
	if regex.compile("^[a-z0-9_]+(\\.[a-z0-9_]+)+$") != OK:
		return false
	return regex.search(text) != null

func _is_garbled_placeholder(text: String) -> bool:
	var trimmed := text.strip_edges()
	if trimmed.begins_with("<missing") or trimmed.findn("TODO") >= 0:
		return true
	var question_only := true
	for ch in trimmed:
		if ch != "?":
			question_only = false
			break
	if question_only and trimmed.length() >= 2:
		return true
	return trimmed.find("�") >= 0

func _is_readable_visible_text(text: String) -> bool:
	var trimmed := text.strip_edges()
	if trimmed == "":
		return false
	if _is_raw_translation_key(trimmed):
		return false
	if _is_garbled_placeholder(trimmed):
		return false
	return true

func _assert_reward_bindings_for_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
	var scene := load(REWARD_SCENE) as PackedScene
	assert(scene != null, "Reward scene must load.")
	var reward = scene.instantiate()
	add_child(auto_free(reward))
	await get_tree().process_frame
	if reward.has_method("SetLocaleForTest"):
		reward.call("SetLocaleForTest", locale)
	if reward.has_method("RefreshLocaleForTest"):
		reward.call("RefreshLocaleForTest")
	await get_tree().process_frame

	var expected := _translations_for_locale(locale)
	for node_path in EXPECTED_BINDINGS.keys():
		var key := str(EXPECTED_BINDINGS[node_path])
		assert(expected.has(key), "Missing translation key %s for locale %s" % [key, locale])
		var node := reward.get_node_or_null(str(node_path))
		assert(node != null, "Reward scene missing node: %s" % node_path)
		var actual := ""
		if node is Label:
			actual = (node as Label).text
		elif node is Button:
			actual = (node as Button).text
		else:
			assert(false, "Unsupported node type for binding check: %s" % [node.get_class()])
		var expected_text := str(expected[key]).strip_edges()
		assert(_is_readable_visible_text(actual), "Unreadable reward text for %s[%s]: %s" % [locale, node_path, actual])
		assert(actual.strip_edges() == expected_text, "Reward binding mismatch at %s for %s." % [node_path, locale])

# acceptance: ACC:T19.5
func test_reward_ui_visible_copy_must_come_from_translation_resources() -> void:
	await _assert_reward_bindings_for_locale("en")
	await _assert_reward_bindings_for_locale("zh-CN")

func test_reward_ui_rejects_unreadable_placeholders_and_raw_keys() -> void:
	var invalid_values := ["", "   ", "ui.reward.title", "??", "????", "<missing:reward>", "�"]
	for value in invalid_values:
		assert_bool(_is_readable_visible_text(str(value))).is_false()
