namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a card is successfully played in combat.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatCardPlayedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    string TargetId,
    string CardInstanceId,
    int EnergyCost,
    int Sequence,
    DateTimeOffset PlayedAt
)
{
    public const string EventType = EventTypes.CombatCardPlayed;
}
