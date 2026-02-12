namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when fixed damage is resolved and bypass rules are applied.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatFixedDamageResolvedEvent(
    string RunId,
    string CombatId,
    string SourceId,
    string TargetId,
    int Amount,
    int TargetArmorAfter,
    DateTimeOffset ResolvedAt
)
{
    public const string EventType = EventTypes.CombatFixedDamageResolved;
}
