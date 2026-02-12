namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when existing status stacks are modified.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record StatusStackedEvent(
    string RunId,
    string CombatId,
    string TargetId,
    string StatusId,
    int PreviousStacks,
    int CurrentStacks,
    DateTimeOffset StackedAt
)
{
    public const string EventType = EventTypes.StatusStacked;
}
