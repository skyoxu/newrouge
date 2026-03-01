using System.Security.Cryptography;
using System.Text;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Offers;

namespace Game.Core.Services;

/// <summary>
/// Deterministic offer locking service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032.
/// </remarks>
public sealed class DeterministicOfferService : IOfferService
{
    private readonly Dictionary<string, OfferLockSnapshot> _lockedOffers = new(StringComparer.Ordinal);

    public OfferLockSnapshot LockOffer(
        string offerContextId,
        IReadOnlyList<OfferItem> candidates,
        OfferProvenance provenance)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            throw new ArgumentException("Offer context id must be non-empty.", nameof(offerContextId));
        }

        ArgumentNullException.ThrowIfNull(candidates);
        ArgumentNullException.ThrowIfNull(provenance);

        var displayOrder = candidates
            .Select(static candidate => candidate.OfferItemId)
            .ToArray();

        var stableIds = BuildStableIds(candidates);
        var snapshot = new OfferLockSnapshot(
            StableIds: stableIds,
            DisplayOrder: displayOrder,
            Provenance: provenance,
            RngStream: provenance.RngStream,
            LockedAt: DateTimeOffset.UtcNow);

        _lockedOffers[offerContextId] = snapshot;
        return snapshot;
    }

    public OfferLockSnapshot? GetLockedOffer(string offerContextId)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            return null;
        }

        return _lockedOffers.TryGetValue(offerContextId, out var snapshot) ? snapshot : null;
    }

    private static IReadOnlyList<string> BuildStableIds(IReadOnlyList<OfferItem> candidates)
    {
        var canonicalRows = candidates
            .Select(static candidate => BuildCanonicalContentKey(candidate))
            .OrderBy(static key => key, StringComparer.Ordinal)
            .ToArray();

        var result = new List<string>(canonicalRows.Length);
        var countByKey = new Dictionary<string, int>(StringComparer.Ordinal);

        foreach (var key in canonicalRows)
        {
            countByKey.TryGetValue(key, out var sequence);
            countByKey[key] = sequence + 1;

            var stableInput = $"{key}#{sequence}";
            result.Add($"offer_{ToDeterministicHash(stableInput)}");
        }

        return result;
    }

    private static string BuildCanonicalContentKey(OfferItem candidate)
    {
        var route = candidate.Route?.ToString() ?? "none";
        return string.Join(
            "|",
            candidate.OfferItemId,
            candidate.CardId,
            candidate.Form.ToString(),
            route,
            candidate.Rarity);
    }

    private static string ToDeterministicHash(string input)
    {
        var bytes = Encoding.UTF8.GetBytes(input);
        var hash = SHA256.HashData(bytes);
        return Convert.ToHexString(hash).ToLowerInvariant()[..16];
    }
}
