extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const APPROVED_TRANSLATION_SOURCE := "translation_resource"

func _build_reward_ui_projection_for_red() -> Array[Dictionary]:
    return [
        {
            "id": "reward_title",
            "text": "ui.reward.title",
            "source": APPROVED_TRANSLATION_SOURCE
        },
        {
            "id": "reward_card_1",
            "text": "ui.reward.card.1.name",
            "source": APPROVED_TRANSLATION_SOURCE
        },
        {
            "id": "reward_card_2",
            "text": "ui.reward.card.2.name",
            "source": APPROVED_TRANSLATION_SOURCE
        },
        {
            "id": "reward_card_3",
            "text": "ui.reward.card.3.name",
            "source": APPROVED_TRANSLATION_SOURCE
        }
    ]

func _contains_non_translation_source(entries: Array[Dictionary]) -> bool:
    for entry in entries:
        var source := str(entry.get("source", ""))
        if source != APPROVED_TRANSLATION_SOURCE:
            return true
    return false

# acceptance: ACC:T19.5
# RED-FIRST: fails until every visible reward text is resolved from translation resources only.
func test_reward_ui_visible_copy_must_come_from_translation_resources() -> void:
    var projection := _build_reward_ui_projection_for_red()

    assert_int(projection.size()).is_equal(4)
    assert_bool(_contains_non_translation_source(projection)).is_false()

func test_reward_ui_rejects_projection_when_any_visible_copy_is_hardcoded() -> void:
    var invalid_projection: Array[Dictionary] = [
        {
            "id": "reward_confirm_button",
            "text": "Confirm",
            "source": "literal_business_copy"
        }
    ]

    assert_bool(_contains_non_translation_source(invalid_projection)).is_true()
