namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when player confirms one map node selection.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record MapNodeSelectedEvent(
    string RunId,
    int ActId,
    string NodeId,
    DateTimeOffset SelectedAt
)
{
    public const string EventType = EventTypes.MapNodeSelected;
}
