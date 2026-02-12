namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one combat loop hard-stop threshold is reached.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatLoopHardStoppedEvent(
    string RunId,
    string CombatId,
    int PlayedCardsCount,
    int Threshold,
    string ReasonCode,
    DateTimeOffset StoppedAt
)
{
    public const string EventType = EventTypes.CombatLoopHardStopped;
}
