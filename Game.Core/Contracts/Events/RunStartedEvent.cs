namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised after a new run is created and initialized.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunStartedEvent(
    string RunId,
    int DifficultyId,
    DateTimeOffset StartedAt
)
{
    public const string EventType = EventTypes.RunStarted;
}

