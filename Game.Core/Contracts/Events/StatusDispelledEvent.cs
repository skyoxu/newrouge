namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a status is dispelled before natural expiration.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record StatusDispelledEvent(
    string RunId,
    string CombatId,
    string TargetId,
    string StatusId,
    string Reason,
    DateTimeOffset DispelledAt
)
{
    public const string EventType = EventTypes.StatusDispelled;
}
