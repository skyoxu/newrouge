using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when reward offer candidates are presented to the player.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RewardOfferPresentedEvent(
    string RunId,
    string OfferContextId,
    IReadOnlyList<string> CandidateIds,
    IReadOnlyList<string> DisplayOrder,
    DateTimeOffset PresentedAt
)
{
    public const string EventType = EventTypes.RewardOfferPresented;
}
