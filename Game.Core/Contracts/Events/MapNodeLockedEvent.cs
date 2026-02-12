namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one map node becomes unavailable and locked.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record MapNodeLockedEvent(
    string RunId,
    int ActId,
    string NodeId,
    string ReasonCode,
    DateTimeOffset LockedAt
)
{
    public const string EventType = EventTypes.MapNodeLocked;
}
