namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one curse card is removed from run deck.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CurseRemovedEvent(
    string RunId,
    string CardId,
    string SourceType,
    string SourceId,
    DateTimeOffset RemovedAt
)
{
    public const string EventType = EventTypes.CurseRemoved;
}
