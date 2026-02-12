namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a combat encounter starts.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatStartedEvent(
    string RunId,
    string CombatId,
    int Turn,
    DateTimeOffset StartedAt
)
{
    public const string EventType = EventTypes.CombatStarted;
}
