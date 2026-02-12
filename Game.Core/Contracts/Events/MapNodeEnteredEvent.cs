namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when run enters one map node.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record MapNodeEnteredEvent(
    string RunId,
    int ActId,
    string NodeId,
    string NodeType,
    DateTimeOffset EnteredAt
)
{
    public const string EventType = EventTypes.MapNodeEntered;
}
