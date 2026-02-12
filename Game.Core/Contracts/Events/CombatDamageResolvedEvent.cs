namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when combat damage is resolved on a target.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatDamageResolvedEvent(
    string RunId,
    string CombatId,
    string SourceId,
    string TargetId,
    int BaseDamage,
    int FinalDamage,
    bool IsFixedDamage,
    int TargetArmorAfter,
    DateTimeOffset ResolvedAt
)
{
    public const string EventType = EventTypes.CombatDamageResolved;
}
