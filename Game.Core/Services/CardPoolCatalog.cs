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
    private static readonly IReadOnlyList<CardPoolDefinition> AllPools =
        BuildAllPools();
    private static readonly IReadOnlyList<CardPoolDefinition> SelectionPools =
        BuildSelectionPools();
    private static readonly IReadOnlyDictionary<string, CardPoolDefinition> PoolsByKey =
        BuildPoolsByKey(SelectionPools);
    private static readonly IReadOnlyDictionary<string, CardPoolDefinition> PoolsById =
        BuildPoolsById(AllPools);

    public static bool TryGetPool(int actId, string encounterType, out CardPoolDefinition pool)
    {
        var key = BuildKey(actId, encounterType);
        return PoolsByKey.TryGetValue(key, out pool!);
    }

    public static bool TryGetPoolById(string poolId, out CardPoolDefinition pool)
    {
        var normalizedPoolId = poolId.Trim();
        return PoolsById.TryGetValue(normalizedPoolId, out pool!);
    }

    public static IReadOnlyCollection<CardPoolDefinition> GetAll()
    {
        return (IReadOnlyCollection<CardPoolDefinition>)SelectionPools;
    }

    private static IReadOnlyList<CardPoolDefinition> BuildSelectionPools()
    {
        var pools = new List<CardPoolDefinition>();
        for (var actId = 1; actId <= 3; actId++)
        {
            if (actId == 1)
            {
                pools.Add(
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "normal",
                        poolId: "act1-normal-pool",
                        commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.battle_focus" },
                        rareCards: new[] { "card.warrior.power_through" }));
                pools.Add(
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "elite",
                        poolId: "act1-elite-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.heavy_strike" },
                        rareCards: new[] { "card.warrior.power_through" }));
                pools.Add(
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "boss",
                        poolId: "act1-boss-pool",
                        commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.iron_wave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.cleave" },
                        rareCards: new[] { "card.warrior.power_through" }));
                pools.Add(
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "shop",
                        poolId: "act1-shop-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.cleave" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.heavy_strike" },
                        rareCards: new[] { "card.warrior.power_through" }));
                pools.Add(
                    BuildPoolWithCards(
                        actId: 1,
                        encounterType: "event",
                        poolId: "act1-event-pool",
                        commonCards: new[] { "card.warrior.iron_wave", "card.warrior.heavy_strike" },
                        uncommonCards: new[] { "card.warrior.power_through", "card.warrior.cleave" },
                        rareCards: new[] { "card.warrior.power_through" }));
                continue;
            }

            pools.Add(BuildPool(actId, "normal", $"act{actId}-normal-pool", $"a{actId}n"));
            pools.Add(BuildPool(actId, "elite", $"act{actId}-elite-pool", $"a{actId}e"));
            pools.Add(BuildPool(actId, "boss", $"act{actId}-boss-pool", $"a{actId}b"));
            pools.Add(BuildPool(actId, "shop", $"act{actId}-shop-pool", $"a{actId}s"));
            pools.Add(BuildPool(actId, "event", $"act{actId}-event-pool", $"a{actId}v"));
        }

        return pools;
    }

    private static IReadOnlyList<CardPoolDefinition> BuildAllPools()
    {
        var pools = new List<CardPoolDefinition>(BuildSelectionPools());

        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "normal",
                poolId: "reward.act1.normal_1",
                commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.cleave" },
                uncommonCards: new[] { "card.warrior.defend", "card.warrior.power_through" },
                rareCards: new[] { "card.warrior.power_through" }));
        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "normal",
                poolId: "reward.act1.normal_2",
                commonCards: new[] { "card.warrior.iron_wave", "card.warrior.heavy_strike" },
                uncommonCards: new[] { "card.warrior.defend", "card.warrior.battle_focus" },
                rareCards: new[] { "card.warrior.power_through" }));
        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "normal",
                poolId: "reward.act1.normal_3",
                commonCards: new[] { "card.warrior.cleave", "card.warrior.iron_wave" },
                uncommonCards: new[] { "card.warrior.power_through", "card.warrior.defend" },
                rareCards: new[] { "card.warrior.power_through" }));
        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "elite",
                poolId: "reward.act1.elite_1",
                commonCards: new[] { "card.warrior.iron_wave", "card.warrior.cleave" },
                uncommonCards: new[] { "card.warrior.power_through", "card.warrior.defend" },
                rareCards: new[] { "card.warrior.power_through" }));
        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "boss",
                poolId: "reward.act1.boss_1",
                commonCards: new[] { "card.warrior.heavy_strike", "card.warrior.cleave" },
                uncommonCards: new[] { "card.warrior.power_through", "card.warrior.defend" },
                rareCards: new[] { "card.warrior.power_through" }));
        pools.Add(
            BuildPoolWithCards(
                actId: 1,
                encounterType: "event",
                poolId: "reward.act1.event_1",
                commonCards: new[] { "card.warrior.iron_wave" },
                uncommonCards: new[] { "card.warrior.power_through", "card.warrior.defend" },
                rareCards: new[] { "card.warrior.power_through" }));

        return pools;
    }

    private static IReadOnlyDictionary<string, CardPoolDefinition> BuildPoolsByKey(IReadOnlyList<CardPoolDefinition> pools)
    {
        var map = new Dictionary<string, CardPoolDefinition>(StringComparer.Ordinal);
        foreach (var pool in pools)
        {
            var key = BuildKey(pool.ActId, pool.EncounterType);
            if (!map.ContainsKey(key))
            {
                map[key] = pool;
            }
        }

        return map;
    }

    private static IReadOnlyDictionary<string, CardPoolDefinition> BuildPoolsById(IReadOnlyList<CardPoolDefinition> pools)
    {
        var map = new Dictionary<string, CardPoolDefinition>(StringComparer.Ordinal);
        foreach (var pool in pools)
        {
            map[pool.PoolId] = pool;
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
