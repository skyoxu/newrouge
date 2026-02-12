namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when reward offer panel is skipped.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RewardOfferSkippedEvent(
    string RunId,
    string OfferContextId,
    DateTimeOffset SkippedAt
)
{
    public const string EventType = EventTypes.RewardOfferSkipped;
}
