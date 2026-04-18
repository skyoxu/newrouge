extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

class RestUpgradeFlowHarness:
	extends RefCounted

	var pre_upgrade_tier: int = 1
	var current_tier: int = 1
	var _confirmed: bool = false

	func confirm_upgrade() -> bool:
		if _confirmed:
			return false
		current_tier += 1
		_confirmed = true
		return true

	func request_undo() -> bool:
		# Intentional bug for RED-first: undo is still allowed after confirmation.
		if not _confirmed:
			return false
		current_tier = pre_upgrade_tier
		_confirmed = false
		return true

	func request_restore_pre_upgrade_snapshot() -> bool:
		# Intentional bug for RED-first: restore path should be blocked.
		current_tier = pre_upgrade_tier
		return true

# acceptance: ACC:T21.5
func test_confirmed_upgrade_cannot_be_undone_in_same_flow() -> void:
	var sut := RestUpgradeFlowHarness.new()

	var confirmed := sut.confirm_upgrade()
	var tier_after_confirm := sut.current_tier
	var undo_accepted := sut.request_undo()

	assert_bool(confirmed).is_true()
	assert_bool(undo_accepted).is_false()
	assert_int(sut.current_tier).is_equal(tier_after_confirm)

# acceptance: ACC:T21.5
func test_confirmed_upgrade_refuses_restore_to_pre_upgrade_state() -> void:
	var sut := RestUpgradeFlowHarness.new()

	var confirmed := sut.confirm_upgrade()
	var tier_after_confirm := sut.current_tier
	var restore_accepted := sut.request_restore_pre_upgrade_snapshot()

	assert_bool(confirmed).is_true()
	assert_bool(restore_accepted).is_false()
	assert_int(sut.current_tier).is_equal(tier_after_confirm)
