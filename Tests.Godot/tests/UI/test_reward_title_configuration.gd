extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

# ADR-0007: verify presentation configuration without changing domain rules.
func test_card_choice_titles_follow_configured_pick() -> void:
    var main = auto_free(load("res://Game.Godot/Scripts/Main.gd").new())
    for rarity in ["common", "rare", "epic"]:
        for pick in [1, 2, 3]:
            var title = main.call("_resolve_reward_entry_title", rarity + "_card_choice", {"pick": pick})
            assert_str(title).is_equal(rarity.capitalize() + " Cards %s-Choice" % pick)

func test_card_choice_titles_default_to_three() -> void:
    var main = auto_free(load("res://Game.Godot/Scripts/Main.gd").new())
    for rarity in ["common", "rare", "epic"]:
        assert_str(main.call("_resolve_reward_entry_title", rarity + "_card_choice", {})).is_equal(rarity.capitalize() + " Cards 3-Choice")
