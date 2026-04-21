extends Control

@onready var _vbox: VBoxContainer = $VBox

var _selected_option: String = ""
var _next_route: String = ""
var _upgrade_confirm_pending: bool = false
var _upgrade_confirmed: bool = false
var _upgrade_target_mutated: bool = false
var _curse_removed: bool = false
var _feedback: String = ""


func _ready() -> void:
	_ensure_option_button("Heal", "heal")
	_ensure_option_button("Upgrade", "upgrade")
	_ensure_option_button("Remove Curse", "remove_curse")


func _ensure_option_button(text_value: String, option_id: String) -> void:
	var button_name := "Option_" + option_id
	var existing := _vbox.get_node_or_null(button_name)
	if existing != null:
		return
	var button := Button.new()
	button.name = button_name
	button.text = text_value
	button.pressed.connect(func() -> void: _on_option_pressed(option_id))
	_vbox.add_child(button)


func _on_option_pressed(option_id: String) -> void:
	_selected_option = option_id
	_curse_removed = false
	if option_id == "upgrade":
		_upgrade_confirm_pending = true
		_feedback = "Upgrade pending confirmation."
		return

	if option_id == "remove_curse":
		_curse_removed = true
	_upgrade_confirm_pending = false
	_feedback = option_id + " resolved."
	_next_route = "map"


func SelectOptionForTest(option_id: String) -> bool:
	var normalized := option_id.strip_edges().to_lower()
	if normalized != "heal" and normalized != "upgrade" and normalized != "remove_curse":
		return false
	_on_option_pressed(normalized)
	return true


func ConfirmUpgradeForTest() -> bool:
	if not _upgrade_confirm_pending:
		return false
	_upgrade_confirm_pending = false
	_upgrade_confirmed = true
	_upgrade_target_mutated = true
	_feedback = "Upgrade confirmed."
	_next_route = "map"
	return true


func CancelUpgradeForTest() -> bool:
	if not _upgrade_confirm_pending:
		return false
	_upgrade_confirm_pending = false
	_selected_option = ""
	_upgrade_target_mutated = false
	_feedback = "Upgrade cancelled."
	return true


func RequestUndoAfterConfirmForTest() -> bool:
	if not _upgrade_confirmed:
		return false
	return false


func RequestRestorePreUpgradeSnapshotForTest() -> bool:
	if not _upgrade_confirmed:
		return false
	return false


func GetAvailableOptionsForTest() -> Array[String]:
	return ["heal", "upgrade", "remove_curse"]


func GetNextRouteForTest() -> String:
	return _next_route


func IsUpgradeConfirmPendingForTest() -> bool:
	return _upgrade_confirm_pending


func IsUpgradeConfirmedForTest() -> bool:
	return _upgrade_confirmed


func WasUpgradeTargetMutatedForTest() -> bool:
	return _upgrade_target_mutated


func WasCurseRemovedForTest() -> bool:
	return _curse_removed


func GetFeedbackForTest() -> String:
	return _feedback
