extends Control

const DEFAULT_PAYLOAD := {
	"outcome": "Unknown",
	"node_progress": 0,
	"reason": "No settlement reason.",
	"title": "Run Settlement",
	"action_label": "Return to Main Menu"
}

var _title_label: Label
var _outcome_label: Label
var _progress_label: Label
var _reason_label: Label
var _return_button: Button

func _ready() -> void:
	_title_label = get_node("Center/Panel/Margin/VBox/Title") as Label
	_outcome_label = get_node("Center/Panel/Margin/VBox/Outcome") as Label
	_progress_label = get_node("Center/Panel/Margin/VBox/Progress") as Label
	_reason_label = get_node("Center/Panel/Margin/VBox/Reason") as Label
	_return_button = get_node("Center/Panel/Margin/VBox/ReturnButton") as Button
	_return_button.pressed.connect(_on_return_pressed)
	_apply_payload(_resolve_payload())

func Enter() -> void:
	_apply_payload(_resolve_payload())

func GetOutcomeTextForTest() -> String:
	return _outcome_label.text

func GetReasonTextForTest() -> String:
	return _reason_label.text

func RequestReturnToMainMenuForTest() -> bool:
	return _return_to_main_menu()

func _resolve_main():
	var current: Node = self
	while current != null:
		if current.has_method("GetSettlementPayloadForScene") and current.has_method("ReturnToMainMenuFromSettlementForTest"):
			return current
		current = current.get_parent()
	return get_tree().root.get_node_or_null("Main")

func _resolve_payload() -> Dictionary:
	var main = _resolve_main()
	if main != null and main.has_method("GetSettlementPayloadForScene"):
		var payload = main.call("GetSettlementPayloadForScene")
		if typeof(payload) == TYPE_DICTIONARY:
			return (payload as Dictionary).duplicate(true)
	return DEFAULT_PAYLOAD.duplicate(true)

func _apply_payload(payload: Dictionary) -> void:
	var outcome := str(payload.get("outcome", DEFAULT_PAYLOAD["outcome"])).strip_edges()
	var node_progress := int(payload.get("node_progress", DEFAULT_PAYLOAD["node_progress"]))
	var reason := str(payload.get("reason", DEFAULT_PAYLOAD["reason"])).strip_edges()
	var title := str(payload.get("title", DEFAULT_PAYLOAD["title"])).strip_edges()
	var action_label := str(payload.get("action_label", DEFAULT_PAYLOAD["action_label"])).strip_edges()

	_title_label.text = title if not title.is_empty() else str(DEFAULT_PAYLOAD["title"])
	_outcome_label.text = "Outcome: %s" % [outcome if not outcome.is_empty() else str(DEFAULT_PAYLOAD["outcome"])]
	_progress_label.text = "Node Progress: %d" % [node_progress]
	_reason_label.text = "Reason: %s" % [reason if not reason.is_empty() else str(DEFAULT_PAYLOAD["reason"])]
	_return_button.text = action_label if not action_label.is_empty() else str(DEFAULT_PAYLOAD["action_label"])

func _on_return_pressed() -> void:
	_return_to_main_menu()

func _return_to_main_menu() -> bool:
	var main = _resolve_main()
	if main == null or not main.has_method("ReturnToMainMenuFromSettlementForTest"):
		return false
	var result = main.call("ReturnToMainMenuFromSettlementForTest")
	if typeof(result) == TYPE_DICTIONARY:
		return bool((result as Dictionary).get("ok", false))
	return bool(result)
