namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one card instance is promoted to ultimate form.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CardUltimatePromotedEvent(
    string RunId,
    string CardInstanceId,
    string CardId,
    Game.Core.Contracts.Cards.CardForm FromForm,
    Game.Core.Contracts.Cards.CardForm ToForm,
    DateTimeOffset PromotedAt
)
{
    public const string EventType = EventTypes.CardUltimatePromoted;
}
