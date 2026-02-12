namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when dark-cost payment is applied to current run state.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DarkCostAppliedEvent(
    string RunId,
    string SourceId,
    string CostType,
    int Amount,
    DateTimeOffset AppliedAt
)
{
    public const string EventType = EventTypes.DarkCostApplied;
}
