using System.Security.Cryptography;
using System.Text;
using Game.Core.Contracts;
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
    private static readonly HashSet<string> AllowedRngStreams = new(StringComparer.Ordinal)
    {
        RngStreamType.Run,
        RngStreamType.Combat,
        RngStreamType.Event,
        RngStreamType.Loot,
        RngStreamType.Shop,
        RngStreamType.Offer,
    };

    private readonly Dictionary<string, OfferLockSnapshot> _lockedOffers = new(StringComparer.Ordinal);

    public OfferLockSnapshot LockOffer(
        string offerContextId,
        IReadOnlyList<OfferItem> candidates,
        OfferProvenance provenance,
        bool isLockedAtSavePoint = true)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            throw new ArgumentException("Offer context id must be non-empty.", nameof(offerContextId));
        }

        ArgumentNullException.ThrowIfNull(candidates);
        ArgumentNullException.ThrowIfNull(provenance);
        ValidateProvenanceRngContext(provenance);

        var displayOrder = candidates
            .Select(static candidate => candidate.OfferItemId)
            .ToArray();

        var stableIds = BuildStableIds(candidates);
        var snapshot = new OfferLockSnapshot(
            StableIds: stableIds,
            DisplayOrder: displayOrder,
            Provenance: provenance,
            RngStream: provenance.RngStream,
            IsLockedAtSavePoint: isLockedAtSavePoint,
            LockedAt: isLockedAtSavePoint ? DateTimeOffset.UtcNow : null);

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

    private static void ValidateProvenanceRngContext(OfferProvenance provenance)
    {
        var streamCategory = ExtractStreamCategory(provenance.RngStream);
        if (string.IsNullOrWhiteSpace(streamCategory) || !AllowedRngStreams.Contains(streamCategory))
        {
            throw new ArgumentException(
                $"Unsupported rng_stream '{provenance.RngStream}'. Expected one of: {string.Join(", ", AllowedRngStreams)}.",
                nameof(provenance));
        }

        if (provenance.StreamPosition < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(provenance),
                provenance.StreamPosition,
                "stream_pos must be non-negative.");
        }
    }

    private static string ExtractStreamCategory(string streamName)
    {
        if (string.IsNullOrWhiteSpace(streamName))
        {
            return string.Empty;
        }

        var normalized = streamName.Trim().ToLowerInvariant();
        var parts = normalized.Split(new[] { '.', '/', ':' }, StringSplitOptions.RemoveEmptyEntries);
        return parts.Length == 0 ? normalized : parts[^1];
    }
}
