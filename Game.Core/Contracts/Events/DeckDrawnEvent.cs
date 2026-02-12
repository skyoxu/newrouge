using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when cards are drawn into hand.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DeckDrawnEvent(
    string RunId,
    string CombatId,
    string ActorId,
    IReadOnlyList<string> DrawnCardInstanceIds,
    int DrawCount,
    int DrawPileCountAfter,
    DateTimeOffset DrawnAt
)
{
    public const string EventType = EventTypes.DeckDrawn;
}
