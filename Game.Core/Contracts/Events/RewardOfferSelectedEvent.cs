namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one reward offer is selected.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RewardOfferSelectedEvent(
    string RunId,
    string OfferContextId,
    string SelectedId,
    int SelectedIndex,
    DateTimeOffset SelectedAt
)
{
    public const string EventType = EventTypes.RewardOfferSelected;
}
