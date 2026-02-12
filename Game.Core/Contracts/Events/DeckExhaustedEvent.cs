namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a card is moved to exhaust pile.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DeckExhaustedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    string CardInstanceId,
    int ExhaustPileCountAfter,
    DateTimeOffset ExhaustedAt
)
{
    public const string EventType = EventTypes.DeckExhausted;
}
