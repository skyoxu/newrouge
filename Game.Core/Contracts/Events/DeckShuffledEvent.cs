namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when discard pile is shuffled into draw pile.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DeckShuffledEvent(
    string RunId,
    string CombatId,
    int DrawPileCountBefore,
    int DiscardPileCountBefore,
    int DrawPileCountAfter,
    int DiscardPileCountAfter,
    DateTimeOffset ShuffledAt
)
{
    public const string EventType = EventTypes.DeckShuffled;
}
