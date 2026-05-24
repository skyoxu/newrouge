using System.Collections.ObjectModel;
using System.Linq;

namespace Game.Core.Services;

/// <summary>
/// Canonical M1 starting relic catalog with deterministic uniqueness validation.
/// </summary>
public static class StartingRelicService
{
    private static readonly IReadOnlyList<StartingRelicDefinition> M1Definitions = new ReadOnlyCollection<StartingRelicDefinition>(
        new[]
        {
            new StartingRelicDefinition("relic.ashen_hourglass", "relic.name.ashen_hourglass", "effect.turn_start_plus_energy", new[] { "m1", "economy" }),
            new StartingRelicDefinition("relic.obsidian_mirror", "relic.name.obsidian_mirror", "effect.first_card_copy", new[] { "m1", "engine" }),
            new StartingRelicDefinition("relic.blood_oath", "relic.name.blood_oath", "effect.low_hp_attack_up", new[] { "m1", "risk" }),
            new StartingRelicDefinition("relic.rusted_compass", "relic.name.rusted_compass", "effect.map_preview_plus_one", new[] { "m1", "map" }),
            new StartingRelicDefinition("relic.twilight_coin", "relic.name.twilight_coin", "effect.shop_discount_small", new[] { "m1", "economy" }),
            new StartingRelicDefinition("relic.embershard", "relic.name.embershard", "effect.burn_on_hit", new[] { "m1", "offense" }),
            new StartingRelicDefinition("relic.frostbite_ring", "relic.name.frostbite_ring", "effect.slow_enemy_on_skill", new[] { "m1", "control" }),
            new StartingRelicDefinition("relic.gale_charm", "relic.name.gale_charm", "effect.first_draw_plus_one", new[] { "m1", "draw" }),
            new StartingRelicDefinition("relic.iron_vow", "relic.name.iron_vow", "effect.block_when_damaged", new[] { "m1", "defense" }),
            new StartingRelicDefinition("relic.moonlit_compass", "relic.name.moonlit_compass", "effect.event_choice_extra_info", new[] { "m1", "map" }),
            new StartingRelicDefinition("relic.nightwatch_lantern", "relic.name.nightwatch_lantern", "effect.dark_cost_reduce_once", new[] { "m1", "utility" }),
            new StartingRelicDefinition("relic.oaken_talisman", "relic.name.oaken_talisman", "effect.max_hp_plus_small", new[] { "m1", "survival" }),
            new StartingRelicDefinition("relic.phantom_quill", "relic.name.phantom_quill", "effect.reward_reroll_once", new[] { "m1", "reward" }),
            new StartingRelicDefinition("relic.quicksilver_seal", "relic.name.quicksilver_seal", "effect.energy_on_combo", new[] { "m1", "engine" }),
            new StartingRelicDefinition("relic.raven_feather", "relic.name.raven_feather", "effect.curse_remove_discount", new[] { "m1", "curse" }),
            new StartingRelicDefinition("relic.sunken_idol", "relic.name.sunken_idol", "effect.rare_reward_chance_up", new[] { "m1", "reward" }),
            new StartingRelicDefinition("relic.thorn_crown", "relic.name.thorn_crown", "effect.thorns_small", new[] { "m1", "defense" }),
            new StartingRelicDefinition("relic.umbral_shard", "relic.name.umbral_shard", "effect.dark_cost_convert_once", new[] { "m1", "dark" }),
            new StartingRelicDefinition("relic.vigilant_emblem", "relic.name.vigilant_emblem", "effect.first_turn_block_plus", new[] { "m1", "defense" }),
            new StartingRelicDefinition("relic.warden_mark", "relic.name.warden_mark", "effect.hp_floor_guard", new[] { "m1", "survival" }),
        });

    private static readonly IReadOnlyList<StartingRelicDefinition> LiveM1Definitions = new ReadOnlyCollection<StartingRelicDefinition>(
        new[]
        {
            new StartingRelicDefinition("relic.ashen_hourglass", "relic.name.ashen_hourglass", "effect.turn_start_plus_energy", new[] { "m1", "economy", "live" }),
            new StartingRelicDefinition("relic.twilight_coin", "relic.name.twilight_coin", "effect.shop_discount_small", new[] { "m1", "economy", "live" }),
        });

    public static IReadOnlyList<StartingRelicDefinition> Definitions => M1Definitions;

    public static IReadOnlyList<StartingRelicDefinition> LiveDefinitions => LiveM1Definitions;

    public static StartingRelicCatalogValidationResult ValidateUniqueRelicIds(IEnumerable<StartingRelicDefinition> definitions)
    {
        var duplicateRelicIds = definitions
            .GroupBy(item => item.RelicId, StringComparer.Ordinal)
            .Where(group => group.Count() > 1)
            .Select(group => group.Key)
            .OrderBy(item => item, StringComparer.Ordinal)
            .ToArray();

        return new StartingRelicCatalogValidationResult(
            duplicateRelicIds.Length == 0,
            duplicateRelicIds);
    }
}

public sealed record StartingRelicDefinition(
    string RelicId,
    string TranslationKey,
    string EffectDescriptor,
    IReadOnlyList<string> Tags);

public sealed record StartingRelicCatalogValidationResult(
    bool IsValid,
    IReadOnlyList<string> DuplicateRelicIds);
