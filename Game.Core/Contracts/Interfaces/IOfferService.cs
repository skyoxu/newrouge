using Game.Core.Contracts.Offers;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Deterministic offer generation and locking service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IOfferService
{
    OfferLockSnapshot LockOffer(
        string offerContextId,
        IReadOnlyList<OfferItem> candidates,
        OfferProvenance provenance,
        bool isLockedAtSavePoint = true);
    OfferLockSnapshot? GetLockedOffer(string offerContextId);
}
