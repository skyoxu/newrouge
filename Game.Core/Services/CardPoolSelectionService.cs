using System;
using System.Collections.Generic;
using System.Linq;
using Game.Core.Contracts.Cards;

namespace Game.Core.Services;

/// <summary>
/// Selects and validates deterministic card pools by Act and encounter type.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0033.
/// </remarks>
public sealed class CardPoolSelectionService
{
    private static readonly string[] RequiredEncounterTypes = { "normal", "elite", "boss", "shop", "event" };
    private static readonly string[] RequiredRarityTiers = { "common", "uncommon", "rare" };

    public CardPoolDefinition SelectSinglePool(IReadOnlyCollection<CardPoolDefinition> pools, int actId, string encounterType)
    {
        ArgumentNullException.ThrowIfNull(pools);
        ArgumentException.ThrowIfNullOrWhiteSpace(encounterType);

        var normalizedInputEncounterType = NormalizeEncounterType(encounterType);
        var candidates = pools
            .Where(pool =>
                pool.ActId == actId &&
                string.Equals(
                    NormalizeEncounterType(pool.EncounterType),
                    normalizedInputEncounterType,
                    StringComparison.Ordinal))
            .ToList();

        if (candidates.Count == 0)
        {
            throw new KeyNotFoundException("No pool was found for the specified act and encounter type.");
        }

        if (candidates.Count > 1)
        {
            throw new InvalidOperationException("Card pool selection must resolve to exactly one match.");
        }

        return candidates[0];
    }

    public bool ValidateActPools(IReadOnlyCollection<CardPoolDefinition> pools, int actId)
    {
        ArgumentNullException.ThrowIfNull(pools);

        var actPools = pools.Where(pool => pool.ActId == actId).ToList();
        var encounterTypes = actPools
            .Select(pool => NormalizeEncounterType(pool.EncounterType))
            .Distinct(StringComparer.Ordinal)
            .ToList();

        var hasAllEncounterTypes = RequiredEncounterTypes.All(required => encounterTypes.Contains(required, StringComparer.Ordinal));
        var hasRarityTiers = actPools.All(HasRequiredRarityTiers);

        return hasAllEncounterTypes && hasRarityTiers;
    }

    private static bool HasRequiredRarityTiers(CardPoolDefinition pool)
    {
        foreach (var requiredTier in RequiredRarityTiers)
        {
            if (!pool.CardsByRarity.TryGetValue(requiredTier, out var cards))
            {
                return false;
            }

            if (cards is null || cards.Count == 0)
            {
                return false;
            }
        }

        return true;
    }

    private static string NormalizeEncounterType(string encounterType)
    {
        return encounterType.Trim().ToLowerInvariant();
    }
}
