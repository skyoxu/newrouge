using System.Text.Json;
using Game.Core.Contracts.Offers;

namespace Game.Core.Repositories;

public sealed class OfferLockRepository
{
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web);

    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public OfferLockRepository(string rootPath)
    {
        if (string.IsNullOrWhiteSpace(rootPath))
        {
            throw new ArgumentException("Repository root path must be non-empty.", nameof(rootPath));
        }

        Directory.CreateDirectory(rootPath);
        _filePath = Path.Combine(rootPath, "offer-locks.json");
    }

    public async Task SaveAsync(string offerContextId, OfferLockSnapshot snapshot, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            throw new ArgumentException("Offer context id must be non-empty.", nameof(offerContextId));
        }

        ArgumentNullException.ThrowIfNull(snapshot);

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var data = await LoadDictionaryInternalAsync(cancellationToken).ConfigureAwait(false);
            data[offerContextId] = snapshot;
            await PersistDictionaryInternalAsync(data, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<OfferLockSnapshot?> GetAsync(string offerContextId, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(offerContextId))
        {
            return null;
        }

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var data = await LoadDictionaryInternalAsync(cancellationToken).ConfigureAwait(false);
            return data.TryGetValue(offerContextId, out var snapshot) ? snapshot : null;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<Dictionary<string, OfferLockSnapshot>> LoadDictionaryInternalAsync(CancellationToken cancellationToken)
    {
        if (!File.Exists(_filePath))
        {
            return new Dictionary<string, OfferLockSnapshot>(StringComparer.Ordinal);
        }

        await using var stream = new FileStream(
            _filePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 4096,
            useAsync: true);
        var loaded = await JsonSerializer.DeserializeAsync<Dictionary<string, OfferLockSnapshot>>(
            stream,
            SerializerOptions,
            cancellationToken).ConfigureAwait(false);
        return loaded ?? new Dictionary<string, OfferLockSnapshot>(StringComparer.Ordinal);
    }

    private async Task PersistDictionaryInternalAsync(
        Dictionary<string, OfferLockSnapshot> data,
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
