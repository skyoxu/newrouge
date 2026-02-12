namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when curse removal service is purchased in shop.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0033.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ShopCurseRemovedEvent(
    string RunId,
    string ShopId,
    string CardId,
    int Price,
    DateTimeOffset RemovedAt
)
{
    public const string EventType = EventTypes.ShopCurseRemoved;
}
