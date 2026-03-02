namespace Game.Core.Contracts.Offers;

/// <summary>
/// Locked offer snapshot persisted for deterministic resume.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032.
/// </remarks>
public sealed record OfferLockSnapshot(
    IReadOnlyList<string> StableIds,
    IReadOnlyList<string> DisplayOrder,
    OfferProvenance Provenance,
    string RngStream,
    bool IsLockedAtSavePoint,
    DateTimeOffset? LockedAt
);
