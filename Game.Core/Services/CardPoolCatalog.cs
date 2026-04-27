using System;
using System.Collections.Generic;
using Game.Core.Contracts.Cards;

namespace Game.Core.Services;

/// <summary>
/// Built-in card pool catalog for deterministic task-scoped pool selection.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0033.
/// </remarks>
public static class CardPoolCatalog
{
    private static readonly IReadOnlyDictionary<string, CardPoolDefinition> Pools =
        BuildPools();

    public static bool TryGetPool(int actId, string encounterType, out CardPoolDefinition pool)
    {
        var key = BuildKey(actId, encounterType);
        return Pools.TryGetValue(key, out pool!);
    }

    public static IReadOnlyCollection<CardPoolDefinition> GetAll()
    {
        return (IReadOnlyCollection<CardPoolDefinition>)Pools.Values;
    }

    private static IReadOnlyDictionary<string, CardPoolDefinition> BuildPools()
    {
        var map = new Dictionary<string, CardPoolDefinition>(StringComparer.Ordinal);
        for (var actId = 1; actId <= 3; actId++)
        {
            if (actId == 1)
            {
                Add(
                    map,
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "normal",
                        poolId: "act1-normal-pool",
                        commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.battle_focus" },
                        rareCards: new[] { "card.warrior.power_through" }));
                Add(
                    map,
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "elite",
                        poolId: "act1-elite-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.heavy_strike" },
                        rareCards: new[] { "card.warrior.power_through" }));
                Add(
                    map,
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "boss",
                        poolId: "act1-boss-pool",
                        commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.iron_wave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.cleave" },
                        rareCards: new[] { "card.warrior.power_through" }));
                Add(
                    map,
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "shop",
                        poolId: "act1-shop-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.heavy_strike" },
                        rareCards: new[] { "card.warrior.power_through" }));
                Add(
                    map,
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "event",
                        poolId: "act1-event-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.heavy_strike" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.cleave" },
                        rareCards: new[] { "card.warrior.power_through" }));
                continue;
            }

            Add(map, BuildPool(actId, "normal", $"act{actId}-normal-pool", $"a{actId}n"));
            Add(map, BuildPool(actId, "elite", $"act{actId}-elite-pool", $"a{actId}e"));
            Add(map, BuildPool(actId, "boss", $"act{actId}-boss-pool", $"a{actId}b"));
            Add(map, BuildPool(actId, "shop", $"act{actId}-shop-pool", $"a{actId}s"));
            Add(map, BuildPool(actId, "event", $"act{actId}-event-pool", $"a{actId}v"));
        }

        return map;
    }

    private static CardPoolDefinition BuildPool(int actId, string encounterType, string poolId, string prefix)
    {
        var cardsByRarity = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            ["common"] = new[] { $"card.{prefix}.c.01", $"card.{prefix}.c.02" },
            ["uncommon"] = new[] { $"card.{prefix}.u.01", $"card.{prefix}.u.02" },
            ["rare"] = new[] { $"card.{prefix}.r.01" },
        };

        return new CardPoolDefinition(
            ActId: actId,
            EncounterType: encounterType,
            PoolId: poolId,
            CardsByRarity: cardsByRarity);
    }

    private static CardPoolDefinition BuildPoolWithCards(
        int actId,
        string encounterType,
        string poolId,
        IReadOnlyList<string> commonCards,
        IReadOnlyList<string> uncommonCards,
        IReadOnlyList<string> rareCards)
    {
        var cardsByRarity = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            ["common"] = commonCards,
            ["uncommon"] = uncommonCards,
            ["rare"] = rareCards,
        };

        return new CardPoolDefinition(
            ActId: actId,
            EncounterType: encounterType,
            PoolId: poolId,
            CardsByRarity: cardsByRarity);
    }

    private static void Add(IDictionary<string, CardPoolDefinition> map, CardPoolDefinition pool)
    {
        map[BuildKey(pool.ActId, pool.EncounterType)] = pool;
    }

    private static string BuildKey(int actId, string encounterType)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(encounterType);
        return actId + ":" + NormalizeEncounterType(encounterType);
    }

    private static string NormalizeEncounterType(string encounterType)
    {
        return encounterType.Trim().ToLowerInvariant();
    }
}
