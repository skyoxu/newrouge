namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when shop inventory is first presented and locked.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ShopInventoryLockedEvent(
    string RunId,
    string ShopId,
    System.Collections.Generic.IReadOnlyList<string> StableIds,
    System.Collections.Generic.IReadOnlyList<string> DisplayOrder,
    DateTimeOffset LockedAt
)
{
    public const string EventType = EventTypes.ShopInventoryLocked;
}
