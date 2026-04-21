extends Control

@onready var _card_list: VBoxContainer = $VBox/CardList
@onready var _confirm_button: Button = $VBox/Actions/ConfirmButton
@onready var _skip_button: Button = $VBox/Actions/SkipButton
@onready var _feedback_label: Label = $VBox/Feedback

var _selected_index: int = -1

func _ready() -> void:
    _confirm_button.pressed.connect(_on_confirm_pressed)
    _skip_button.pressed.connect(_on_skip_pressed)
    _feedback_label.text = "Select a reward."

func SelectChoiceForTest(index: int) -> bool:
    if index < 0 or index >= _card_list.get_child_count():
        return false
    _selected_index = index
    _feedback_label.text = "Selected reward %d" % (index + 1)
    return true

func ConfirmSelectedForTest() -> bool:
    if _selected_index < 0:
        _feedback_label.text = "Select a reward first."
        return false
    _feedback_label.text = "Reward confirmed."
    return true

func SkipForTest() -> bool:
    _feedback_label.text = "Reward skipped."
    return true

func GetFeedbackForTest() -> String:
    return _feedback_label.text

func GetCardCountForTest() -> int:
    return _card_list.get_child_count()

func _on_confirm_pressed() -> void:
    ConfirmSelectedForTest()

func _on_skip_pressed() -> void:
    SkipForTest()

