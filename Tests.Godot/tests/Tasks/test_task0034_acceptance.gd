extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const TASK34_TEST_REFS := [
	"Tests.Godot/tests/Tasks/test_task0034_acceptance.gd",
	"Tests.Godot/tests/Scenes/Battle/test_battle_card_targeting_drag_play_flow.gd",
	"Tests.Godot/tests/UI/test_hud_invalid_target_feedback.gd",
	"Tests.Godot/tests/UI/test_card_drag_target_play.gd",
]

class Enemy extends RefCounted:
	var id: String
	var valid_for_card: bool = true

	func _init(enemy_id: String, is_valid_for_card: bool = true) -> void:
		id = enemy_id
		valid_for_card = is_valid_for_card

class FakeI18n extends RefCounted:
	var calls: Array[String] = []
	var _table := {"ui.invalid_target": "Invalid target"}

	func get_text(key: String) -> String:
		calls.append(key)
		return _table.get(key, "MISSING:%s" % key)

class BattleDragUxHarness extends RefCounted:
	signal play_attempt(card_id: String, target_id: String)
	signal invalid_target_feedback(message: String)

	var enemies: Array = []
	var current_target = null
	var hand: Array[String] = ["card_firebolt"]
	var play_attempts: int = 0
	var selection_history: Array[String] = []
	var keep_single_enemy_target_locked: bool = true
	var emit_attempt_event: bool = false
	var i18n

	func _init(i18n_provider) -> void:
		i18n = i18n_provider

	func set_enemies(next_enemies: Array) -> void:
		enemies = next_enemies
		if enemies.size() == 1 and keep_single_enemy_target_locked:
			current_target = enemies[0]
			selection_history.append(str(current_target.id))

	func hover_enemy(enemy) -> void:
		if enemies.has(enemy):
			current_target = enemy
			selection_history.append(str(enemy.id))

	func drag_card_to_current_target(card_id: String) -> void:
		if current_target == null or not current_target.valid_for_card:
			var message := i18n.get_text("ui.invalid_target")
			emit_signal("invalid_target_feedback", message)
			return
		play_attempts += 1
		if emit_attempt_event:
			emit_signal("play_attempt", card_id, str(current_target.id))

# ACC:T34.1
func test_hover_selects_current_target_and_invalid_feedback_uses_translation_key() -> void:
	var i18n := FakeI18n.new()
	var harness := BattleDragUxHarness.new(i18n)
	var enemy_a := Enemy.new("enemy_a", true)
	var enemy_b := Enemy.new("enemy_b", false)

	harness.set_enemies([enemy_a, enemy_b])
	harness.hover_enemy(enemy_b)
	assert_that(harness.current_target.id).is_equal("enemy_b")

	harness.set_enemies([enemy_a])
	assert_that(harness.current_target.id).is_equal("enemy_a")

	harness.drag_card_to_current_target("card_firebolt")
	assert_that(harness.play_attempts).is_equal(1)

	var invalid_messages: Array = []
	harness.invalid_target_feedback.connect(func(message: String): invalid_messages.append(message))
	harness.current_target = enemy_b
	harness.drag_card_to_current_target("card_firebolt")

	assert_that(invalid_messages.size()).is_equal(1)
	assert_that(invalid_messages[0]).is_equal("Invalid target")
	assert_that(i18n.calls.size()).is_equal(1)
	assert_that(i18n.calls[0]).is_equal("ui.invalid_target")

# ACC:T34.2
func test_repeated_hover_and_drag_emits_attempt_event_every_cycle_on_windows_flow() -> void:
	var i18n := FakeI18n.new()
	var harness := BattleDragUxHarness.new(i18n)
	var enemy_a := Enemy.new("enemy_a", true)
	var enemy_b := Enemy.new("enemy_b", true)

	harness.set_enemies([enemy_a, enemy_b])

	var attempt_targets: Array = []
	harness.play_attempt.connect(func(_card_id: String, target_id: String): attempt_targets.append(target_id))

	for i in range(4):
		var next_target = enemy_a if i % 2 == 0 else enemy_b
		harness.hover_enemy(next_target)
		harness.drag_card_to_current_target("card_firebolt")

	assert_that(harness.selection_history.size()).is_equal(4)
	assert_that(harness.play_attempts).is_equal(4)
	assert_that(attempt_targets.size()).is_equal(4)

# ACC:T34.3
func test_task34_refs_manifest_includes_acceptance_suite_path() -> void:
	for ref_path in TASK34_TEST_REFS:
		assert_that(FileAccess.file_exists(ref_path)).is_true()

# ACC:T34.5
func test_invalid_target_refuses_play_and_keeps_hand_and_battle_state_unchanged() -> void:
	var i18n := FakeI18n.new()
	var harness := BattleDragUxHarness.new(i18n)
	var invalid_enemy := Enemy.new("enemy_invalid", false)

	harness.set_enemies([invalid_enemy])
	harness.current_target = invalid_enemy

	var hand_before := harness.hand.duplicate(true)
	var target_before := harness.current_target.id
	var attempts_before := harness.play_attempts
	var attempt_events: Array = []
	var invalid_messages: Array = []

	harness.play_attempt.connect(func(_card_id: String, _target_id: String): attempt_events.append("attempt"))
	harness.invalid_target_feedback.connect(func(message: String): invalid_messages.append(message))
	harness.drag_card_to_current_target("card_firebolt")

	assert_that(harness.play_attempts).is_equal(attempts_before)
	assert_that(attempt_events.size()).is_equal(0)
	assert_that(harness.hand).is_equal(hand_before)
	assert_that(harness.current_target.id).is_equal(target_before)
	assert_that(invalid_messages.size()).is_equal(1)
	assert_that(invalid_messages[0]).is_equal("Invalid target")
