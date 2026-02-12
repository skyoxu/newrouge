using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when cards are retained across turn boundary.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DeckRetainedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    IReadOnlyList<string> CardInstanceIds,
    DateTimeOffset RetainedAt
)
{
    public const string EventType = EventTypes.DeckRetained;
}
