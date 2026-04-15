using System;

namespace Game.Core.Services;

/// <summary>
/// Runtime card descriptor used for curse namespace discovery.
/// </summary>
public sealed record CurseCardDefinition(
    string Id,
    string Namespace);

/// <summary>
/// Runtime card model for curse operations.
/// </summary>
public sealed record CurseRuntimeCard(
    string Id,
    string Namespace);

/// <summary>
/// Runtime catalog for curse card discovery.
/// </summary>
public static class CurseCardRuntimeCatalog
{
    public static IReadOnlyList<CurseRuntimeCard> DiscoverEnabledCurseCards(IEnumerable<CurseCardDefinition> definitions)
    {
        return definitions
            .Where(definition => definition.Namespace.StartsWith("card.curse.", StringComparison.Ordinal))
            .Select(definition => new CurseRuntimeCard(definition.Id, definition.Namespace))
            .ToArray();
    }
}

/// <summary>
/// Upgrade rules for curse cards.
/// </summary>
public static class CurseUpgradeRules
{
    public static CurseUpgradeAttempt TryUpgrade(CurseRuntimeCard card)
    {
        if (card.Namespace.StartsWith("card.curse.", StringComparison.Ordinal))
        {
            return new CurseUpgradeAttempt(false, card);
        }

        return new CurseUpgradeAttempt(true, card);
    }
}

/// <summary>
/// Result of a card upgrade attempt.
/// </summary>
public sealed record CurseUpgradeAttempt(
    bool IsAccepted,
    CurseRuntimeCard Card);

/// <summary>
/// Allowed origins for curse removal.
/// </summary>
public enum CurseRemovalOrigin
{
    Store,
    Rest,
    Event,
}

/// <summary>
/// Runtime deck card entry.
/// </summary>
public sealed record CurseDeckCard(
    string Id,
    string Namespace);

/// <summary>
/// Mutable deck for curse removal operations.
/// </summary>
public sealed class CurseDeck
{
    public CurseDeck(params CurseDeckCard[] cards)
    {
        Cards = cards.ToList();
    }

    public List<CurseDeckCard> Cards { get; }

    public int Count => Cards.Count;

    public bool Contains(string cardId)
    {
        return Cards.Any(card => card.Id == cardId);
    }
}

/// <summary>
/// Coordinates curse removal across store/rest/event flows.
/// </summary>
public sealed class CurseRemovalCoordinator
{
    public bool RemoveCurse(CurseDeck deck, string targetCardId, CurseRemovalOrigin origin, bool isConfirmed)
    {
        if (!isConfirmed)
        {
            return false;
        }

        if (!Enum.IsDefined(typeof(CurseRemovalOrigin), origin))
        {
            return false;
        }

        var targetIndex = deck.Cards.FindIndex(card =>
            card.Id == targetCardId &&
            card.Namespace.StartsWith("card.curse.", StringComparison.Ordinal));

        if (targetIndex < 0)
        {
            return false;
        }

        deck.Cards.RemoveAt(targetIndex);
        return true;
    }
}
