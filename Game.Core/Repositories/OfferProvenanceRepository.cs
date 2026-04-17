using System.Text.Json;
using Game.Core.Contracts.Offers;

namespace Game.Core.Repositories;

public sealed class OfferProvenanceRepository
{
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web);

    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public OfferProvenanceRepository(string rootPath)
    {
        if (string.IsNullOrWhiteSpace(rootPath))
        {
            throw new ArgumentException("Repository root path must be non-empty.", nameof(rootPath));
        }

        Directory.CreateDirectory(rootPath);
        _filePath = Path.Combine(rootPath, "offer-provenance.json");
    }

    public async Task SaveAsync(string offerContextId, OfferProvenance provenance, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            throw new ArgumentException("Offer context id must be non-empty.", nameof(offerContextId));
        }

        ArgumentNullException.ThrowIfNull(provenance);

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var data = await LoadDictionaryInternalAsync(cancellationToken).ConfigureAwait(false);
            data[offerContextId] = provenance;
            await PersistDictionaryInternalAsync(data, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<OfferProvenance?> GetAsync(string offerContextId, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            return null;
        }

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var data = await LoadDictionaryInternalAsync(cancellationToken).ConfigureAwait(false);
            return data.TryGetValue(offerContextId, out var provenance) ? provenance : null;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<Dictionary<string, OfferProvenance>> LoadDictionaryInternalAsync(CancellationToken cancellationToken)
    {
        if (!File.Exists(_filePath))
        {
            return new Dictionary<string, OfferProvenance>(StringComparer.Ordinal);
        }

        await using var stream = new FileStream(
            _filePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 4096,
            useAsync: true);
        var loaded = await JsonSerializer.DeserializeAsync<Dictionary<string, OfferProvenance>>(
            stream,
            SerializerOptions,
            cancellationToken).ConfigureAwait(false);
        return loaded ?? new Dictionary<string, OfferProvenance>(StringComparer.Ordinal);
    }

    private async Task PersistDictionaryInternalAsync(
        Dictionary<string, OfferProvenance> data,
        CancellationToken cancellationToken)
    {
        var tempPath = _filePath + ".tmp";
        await using (var stream = new FileStream(
                         tempPath,
                         FileMode.Create,
                         FileAccess.Write,
                         FileShare.None,
                         bufferSize: 4096,
                         useAsync: true))
        {
            await JsonSerializer.SerializeAsync(stream, data, SerializerOptions, cancellationToken).ConfigureAwait(false);
            await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        File.Move(tempPath, _filePath, overwrite: true);
    }
}
