using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when entering a deterministic event node.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record EventEnteredEvent(
    string RunId,
    string EventId,
    string NodeId,
    IReadOnlyList<string> OptionIds,
    DateTimeOffset EnteredAt
)
{
    public const string EventType = EventTypes.EventEntered;
}
