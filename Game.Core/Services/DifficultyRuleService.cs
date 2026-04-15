using System;
using System.Collections.Generic;
using Game.Core.Contracts.Config;

namespace Game.Core.Services;

/// <summary>
/// Resolves deterministic difficulty rule modifiers from explicit difficulty input only.
/// </summary>
public sealed class DifficultyRuleService
{
    private static readonly IReadOnlyList<string> EasyModifiers = new[]
    {
        "EnemyHealthScale:0.85",
        "EnemyDamageScale:0.90",
        "LootScale:1.15",
    };

    private static readonly IReadOnlyList<string> NormalModifiers = new[]
    {
        "EnemyHealthScale:1.00",
        "EnemyDamageScale:1.00",
        "LootScale:1.00",
    };

    private static readonly IReadOnlyList<string> HardBaseModifiers = new[]
    {
        "EnemyHealthScale:1.20",
        "EnemyDamageScale:1.15",
        "LootScale:0.90",
    };

    public IReadOnlyList<string> GetModifiers(string difficulty)
    {
        if (string.Equals(difficulty, "Easy", StringComparison.OrdinalIgnoreCase))
        {
            return EasyModifiers;
        }

        if (string.Equals(difficulty, "Normal", StringComparison.OrdinalIgnoreCase))
        {
            return NormalModifiers;
        }

        if (string.Equals(difficulty, "Hard", StringComparison.OrdinalIgnoreCase))
        {
            return HardBaseModifiers;
        }

        return Array.Empty<string>();
    }

    public IReadOnlyList<string> ResolveModifiers(int difficultyId)
    {
        var bounded = Math.Clamp(difficultyId, 1, 10);

        if (bounded <= 3)
        {
            return EasyModifiers;
        }

        if (bounded <= 7)
        {
            return NormalModifiers;
        }

        if (bounded < 10)
        {
            return HardBaseModifiers;
        }

        var withOverplayTax = new string[HardBaseModifiers.Count + 1];
        for (var index = 0; index < HardBaseModifiers.Count; index++)
        {
            withOverplayTax[index] = HardBaseModifiers[index];
        }

        withOverplayTax[HardBaseModifiers.Count] = "OverplayTax:12";
        return withOverplayTax;
    }

    public IReadOnlyList<string> ResolveModifiers(DifficultyConfig difficulty)
    {
        ArgumentNullException.ThrowIfNull(difficulty);
        return ResolveModifiers(difficulty.DifficultyId);
    }
}
