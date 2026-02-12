namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when a shop item is purchased from locked inventory.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ShopItemPurchasedEvent(
    string RunId,
    string ShopId,
    string ItemId,
    string ItemType,
    int Price,
    DateTimeOffset PurchasedAt
)
{
    public const string EventType = EventTypes.ShopItemPurchased;
}
