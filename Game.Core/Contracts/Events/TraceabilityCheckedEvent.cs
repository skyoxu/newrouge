namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when traceability gate completes one check pass.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0005.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record TraceabilityCheckedEvent(
    string RunId,
    string Scope,
    string Status,
    DateTimeOffset CheckedAt
)
{
    public const string EventType = EventTypes.TraceabilityChecked;
}
