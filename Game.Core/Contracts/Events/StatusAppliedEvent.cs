namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a status is applied to a combatant.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record StatusAppliedEvent(
    string RunId,
    string CombatId,
    string TargetId,
    string StatusId,
    int Stacks,
    int DurationTurns,
    string SourceId,
    DateTimeOffset AppliedAt
)
{
    public const string EventType = EventTypes.StatusApplied;
}
