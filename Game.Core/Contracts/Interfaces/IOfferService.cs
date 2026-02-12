using Game.Core.Contracts.Offers;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Deterministic offer generation and locking service.
/// </summary>
public interface IOfferService
{
    OfferLockSnapshot LockOffer(string offerContextId, IReadOnlyList<OfferItem> candidates, OfferProvenance provenance);
    OfferLockSnapshot? GetLockedOffer(string offerContextId);
}

