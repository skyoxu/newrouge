namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a combat encounter ends.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatEndedEvent(
    string RunId,
    string CombatId,
    bool PlayerWon,
    int Turns,
    DateTimeOffset EndedAt
)
{
    public const string EventType = EventTypes.CombatEnded;
}
