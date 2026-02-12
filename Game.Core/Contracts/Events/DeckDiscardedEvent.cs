using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when cards move from hand to discard pile.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DeckDiscardedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    IReadOnlyList<string> CardInstanceIds,
    int DiscardPileCountAfter,
    DateTimeOffset DiscardedAt
)
{
    public const string EventType = EventTypes.DeckDiscarded;
}
