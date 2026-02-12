namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised at the beginning of one combat turn before main phase.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatTurnStartedEvent(
    string RunId,
    string CombatId,
    int Turn,
    string ActorId,
    int Energy,
    int DrawCount,
    DateTimeOffset StartedAt
)
{
    public const string EventType = EventTypes.CombatTurnStarted;
}
