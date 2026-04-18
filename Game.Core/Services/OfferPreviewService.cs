using System;
using System.Collections.Generic;
using System.Linq;
using Game.Core.Contracts.Cards;

namespace Game.Core.Services;

/// <summary>
/// Deterministic preview helper for card offer selection that never mutates external RNG state.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0033.
/// </remarks>
public sealed class OfferPreviewService
{
    public OfferPreviewResult PreviewSelection(
        int act,
        string encounterType,
        int seed,
        long streamPosition,
        int pickCount)
    {
        if (act <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(act));
        }

        if (streamPosition < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(streamPosition));
        }

        if (pickCount <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(pickCount));
        }

        var pool = ResolvePool(act, encounterType);
        var rng = new Random(DeriveStableSeed(act, NormalizeEncounterType(encounterType), seed, streamPosition));
        var selectedCardIds = new List<string>(pickCount);

        for (var index = 0; index < pickCount; index++)
        {
            var rarity = DrawRarity(rng, ResolveWeights(encounterType));
            if (!pool.CardsByRarity.TryGetValue(rarity, out var cards) || cards.Count == 0)
            {
                throw new InvalidOperationException($"Missing non-empty rarity tier '{rarity}' in pool '{pool.PoolId}'.");
            }

            var card = cards[rng.Next(cards.Count)];
            selectedCardIds.Add(card);
        }

        return new OfferPreviewResult(selectedCardIds, streamPosition);
    }

    public IReadOnlyList<string> DrawRarities(int act, string encounterType, int seed, int drawCount)
    {
        if (act <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(act));
        }

        if (drawCount <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(drawCount));
        }

        _ = ResolvePool(act, encounterType);
        var rng = new Random(DeriveStableSeed(act, NormalizeEncounterType(encounterType), seed, streamPosition: 0));
        var weights = ResolveWeights(encounterType);
        var result = new List<string>(drawCount);

        for (var index = 0; index < drawCount; index++)
        {
            result.Add(DrawRarity(rng, weights));
        }

        return result;
    }

    private static CardPoolDefinition ResolvePool(int act, string encounterType)
    {
        var normalizedEncounterType = NormalizeEncounterType(encounterType);
        if (!CardPoolCatalog.TryGetPool(act, normalizedEncounterType, out var pool))
        {
            throw new ArgumentException("Unsupported Act + encounter type combination.", nameof(encounterType));
        }

        return pool;
    }

    private static (double common, double uncommon, double rare) ResolveWeights(string encounterType)
    {
        var normalized = NormalizeEncounterType(encounterType);
        return normalized switch
        {
            "normal" => (0.70, 0.25, 0.05),
            "elite" => (0.40, 0.35, 0.25),
            "boss" => (0.30, 0.35, 0.35),
            "shop" => (0.55, 0.30, 0.15),
            "event" => (0.60, 0.30, 0.10),
            _ => throw new ArgumentException("Unsupported encounter type.", nameof(encounterType)),
        };
    }

    private static string DrawRarity(Random rng, (double common, double uncommon, double rare) weights)
    {
        var roll = rng.NextDouble();

        if (roll < weights.rare)
        {
            return "rare";
        }

        if (roll < weights.rare + weights.uncommon)
        {
            return "uncommon";
        }

        return "common";
    }

    private static string NormalizeEncounterType(string encounterType)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(encounterType);
        var normalized = encounterType.Trim().ToLowerInvariant();
        return normalized switch
        {
            "combat_normal" => "normal",
            "combat_elite" => "elite",
            _ => normalized,
        };
    }

    private static int DeriveStableSeed(int act, string normalizedEncounterType, int seed, long streamPosition)
    {
        var hash = FnvOffsetBasis;
        hash = MixInt32(hash, act);
        hash = MixString(hash, normalizedEncounterType);
        hash = MixInt32(hash, seed);
        hash = MixInt64(hash, streamPosition);

        var deterministicSeed = (int)(hash & int.MaxValue);
        return deterministicSeed == 0 ? 1 : deterministicSeed;
    }

    private static uint MixString(uint hash, string value)
    {
        foreach (var b in System.Text.Encoding.UTF8.GetBytes(value))
        {
            hash ^= b;
            hash *= FnvPrime;
        }

        return hash;
    }

    private static uint MixInt32(uint hash, int value)
    {
        unchecked
        {
            hash ^= (byte)value;
            hash *= FnvPrime;
            hash ^= (byte)(value >> 8);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 16);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 24);
            hash *= FnvPrime;
        }

        return hash;
    }

    private static uint MixInt64(uint hash, long value)
    {
        unchecked
        {
            hash ^= (byte)value;
            hash *= FnvPrime;
            hash ^= (byte)(value >> 8);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 16);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 24);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 32);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 40);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 48);
            hash *= FnvPrime;
            hash ^= (byte)(value >> 56);
            hash *= FnvPrime;
        }

        return hash;
    }

    private const uint FnvOffsetBasis = 2166136261;
    private const uint FnvPrime = 16777619;
}

public sealed record OfferPreviewResult(
    IReadOnlyList<string> SelectedCardIds,
    long StreamPositionAfterPreview
);
