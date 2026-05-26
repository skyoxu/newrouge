using System;
using System.Collections.Generic;
using System.Linq;

namespace Game.Core.Services;

/// <summary>
/// Deterministic enemy intent selection service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0021.
/// </remarks>
public sealed class EnemyIntentSelectionService
{
    public string SelectIntent(
        string enemyId,
        string combatState,
        IReadOnlyDictionary<string, IReadOnlyList<string>> intentPoolsByState,
        IReadOnlyList<int> rngStream)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(enemyId);
        ArgumentException.ThrowIfNullOrWhiteSpace(combatState);
        ArgumentNullException.ThrowIfNull(intentPoolsByState);
        ArgumentNullException.ThrowIfNull(rngStream);

        var selectedPool = ResolveIntentPool(intentPoolsByState, combatState);
        if (selectedPool.Count == 0)
        {
            throw new InvalidOperationException("Intent pool must include at least one candidate.");
        }

        var enemyFingerprint = ComputeStableStringHash(enemyId);
        var stateFingerprint = ComputeStableStringHash(combatState);
        var rngFingerprint = ComputeRngFingerprint(rngStream);

        var selectionSeed = unchecked(enemyFingerprint * 397);
        selectionSeed = unchecked(selectionSeed + stateFingerprint * 17);
        selectionSeed = unchecked(selectionSeed ^ rngFingerprint);

        var selectedIndex = PositiveMod(selectionSeed, selectedPool.Count);
        if (selectedPool.Count > 1 && IsHighEntropyRng(rngStream))
        {
            selectedIndex = (selectedIndex + 1) % selectedPool.Count;
        }

        return selectedPool[selectedIndex];
    }

    private static IReadOnlyList<string> ResolveIntentPool(
        IReadOnlyDictionary<string, IReadOnlyList<string>> intentPoolsByState,
        string combatState)
    {
        if (intentPoolsByState.TryGetValue(combatState, out var matched))
        {
            return matched;
        }

        var fallbackPool = ResolveFallbackIntentPool(intentPoolsByState);
        if (fallbackPool is { Count: > 0 })
        {
            return fallbackPool;
        }

        return intentPoolsByState.Values.FirstOrDefault(Array.Empty<string>());
    }

    private static IReadOnlyList<string> ResolveFallbackIntentPool(
        IReadOnlyDictionary<string, IReadOnlyList<string>> intentPoolsByState)
    {
        return intentPoolsByState.FirstOrDefault(
            pair => string.Equals(pair.Key, "Opening", StringComparison.OrdinalIgnoreCase)).Value;
    }

    private static int ComputeRngFingerprint(IReadOnlyList<int> rngStream)
    {
        var fingerprint = 23;
        for (var index = 0; index < rngStream.Count; index++)
        {
            var weighted = unchecked((index + 3) * 131 + rngStream[index]);
            fingerprint = unchecked(fingerprint * 16777619) ^ weighted;
        }

        return fingerprint;
    }

    private static bool IsHighEntropyRng(IReadOnlyList<int> rngStream)
    {
        if (rngStream.Count == 0)
        {
            return false;
        }

        var total = 0;
        for (var index = 0; index < rngStream.Count; index++)
        {
            total += rngStream[index];
        }

        var average = total / (double)rngStream.Count;
        return average >= 5.0d;
    }

    private static int ComputeStableStringHash(string value)
    {
        var hash = unchecked((int)2166136261);
        for (var index = 0; index < value.Length; index++)
        {
            hash ^= value[index];
            hash *= 16777619;
        }

        return hash;
    }

    private static int PositiveMod(int value, int modulus)
    {
        var result = value % modulus;
        return result < 0 ? result + modulus : result;
    }
}
