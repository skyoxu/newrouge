namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when score changes and new value is committed.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0003.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ScoreUpdatedEvent(
    string RunId,
    int PreviousScore,
    int CurrentScore,
    int Delta,
    DateTimeOffset UpdatedAt
)
{
    public const string EventType = EventTypes.ScoreUpdated;
}
