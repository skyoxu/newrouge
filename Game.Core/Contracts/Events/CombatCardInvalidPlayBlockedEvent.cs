namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one invalid card play is blocked by combat rules.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CombatCardInvalidPlayBlockedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    string CardInstanceId,
    string ReasonCode,
    DateTimeOffset BlockedAt
)
{
    public const string EventType = EventTypes.CombatCardInvalidPlayBlocked;
}
