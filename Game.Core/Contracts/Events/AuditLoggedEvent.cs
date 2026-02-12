namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one audit entry is written to structured audit log.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0003, ADR-0019.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record AuditLoggedEvent(
    string RunId,
    string Action,
    string Reason,
    string Target,
    string Caller,
    DateTimeOffset LoggedAt
)
{
    public const string EventType = EventTypes.AuditLogged;
}
