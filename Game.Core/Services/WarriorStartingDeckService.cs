using System.Collections.ObjectModel;
using System.Linq;

namespace Game.Core.Services;

/// <summary>
/// ADR-0033: canonical M1 warrior starter deck manifest for deterministic tests and initialization.
/// </summary>
public sealed class WarriorStartingDeckService
{
    private static readonly IReadOnlyList<WarriorStartingDeckCardDefinition> M1Definitions = new ReadOnlyCollection<WarriorStartingDeckCardDefinition>(
        new[]
        {
            new WarriorStartingDeckCardDefinition("card.warrior.cleave", "common", "attack", true, new[] { "rage", "aoe" }, "damage"),
            new WarriorStartingDeckCardDefinition("card.warrior.guard", "common", "skill", true, new[] { "rage", "defense" }, "defense"),
            new WarriorStartingDeckCardDefinition("card.warrior.rage_surge", "common", "skill", true, new[] { "rage", "engine" }, "setup"),
            new WarriorStartingDeckCardDefinition("card.warrior.bloodrush", "common", "attack", true, new[] { "rage", "risk", "finisher" }, "burst"),
            new WarriorStartingDeckCardDefinition("card.warrior.taunt", "common", "skill", true, new[] { "control", "defense" }, "control"),
            new WarriorStartingDeckCardDefinition("card.warrior.shield_wall", "uncommon", "skill", true, new[] { "defense", "engine" }, "sustain"),
            new WarriorStartingDeckCardDefinition("card.warrior.overpower", "uncommon", "attack", true, new[] { "rage", "finisher" }, "finisher"),
            new WarriorStartingDeckCardDefinition("card.warrior.battlecry", "common", "skill", true, new[] { "engine", "draw" }, "engine"),
            new WarriorStartingDeckCardDefinition("card.warrior.crush", "common", "attack", true, new[] { "rage", "single_target" }, "damage"),
            new WarriorStartingDeckCardDefinition("card.warrior.relentless", "rare", "power", true, new[] { "engine", "rage" }, "archetype"),
        });

    public static IReadOnlyList<WarriorStartingDeckCardDefinition> Definitions => M1Definitions;

    public static IReadOnlyList<WarriorStartingDeckCardDefinition> BuildStartingDeck() => M1Definitions;

    public static WarriorDeckManifestValidationResult ValidateManifestAgainstM1(IReadOnlyCollection<string> actualCardIds)
    {
        var expected = new HashSet<string>(M1Definitions.Select(card => card.CardId), StringComparer.Ordinal);
        var actual = new HashSet<string>(actualCardIds, StringComparer.Ordinal);

        var missing = expected
            .Except(actual)
            .OrderBy(cardId => cardId, StringComparer.Ordinal)
            .Select(cardId => $"missing: {cardId}");

        var extra = actual
            .Except(expected)
            .OrderBy(cardId => cardId, StringComparer.Ordinal)
            .Select(cardId => $"extra: {cardId}");

        var diffLines = missing.Concat(extra).ToArray();
        var isValid = diffLines.Length == 0;
        var summary = isValid
            ? "manifest matches m1 content list"
            : string.Join("; ", diffLines);

        return new WarriorDeckManifestValidationResult(isValid, diffLines, summary);
    }
}

public sealed record WarriorStartingDeckCardDefinition(
    string CardId,
    string Rarity,
    string CardType,
    bool IsStarterDeck,
    IReadOnlyList<string> Tags,
    string Intent);

public sealed record WarriorDeckManifestValidationResult(
    bool IsValid,
    IReadOnlyList<string> DiffLines,
    string Summary);
