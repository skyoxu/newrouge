namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when health value changes for one combatant.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record HealthUpdatedEvent(
    string RunId,
    string TargetId,
    int PreviousHealth,
    int CurrentHealth,
    int Delta,
    DateTimeOffset UpdatedAt
)
{
    public const string EventType = EventTypes.HealthUpdated;
}
