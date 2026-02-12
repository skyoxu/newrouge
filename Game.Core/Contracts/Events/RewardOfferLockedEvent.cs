namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when reward candidates are first shown and locked.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RewardOfferLockedEvent(
    string RunId,
    string OfferContextId,
    IReadOnlyList<string> StableIds,
    IReadOnlyList<string> DisplayOrder,
    DateTimeOffset LockedAt
)
{
    public const string EventType = EventTypes.RewardOfferLocked;
}

