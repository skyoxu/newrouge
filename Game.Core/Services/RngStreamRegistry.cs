using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;

namespace Game.Core.Services;

/// <summary>
/// Deterministic registry for named RNG streams.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0021.
/// </remarks>
public sealed class RngStreamRegistry : IRngStreamRegistry
{
    private static readonly string[] CanonicalStreams =
    {
        RngStreamType.Run,
        RngStreamType.Combat,
        RngStreamType.Event,
        RngStreamType.Loot,
        RngStreamType.Shop,
        RngStreamType.Offer,
    };

    private readonly Dictionary<string, StreamState> _streams;
    private readonly ulong _seed;

    public RngStreamRegistry(int seed)
    {
        _streams = new Dictionary<string, StreamState>(StringComparer.Ordinal);
        _seed = unchecked((ulong)(long)seed);
        var baseSeed = _seed;
        foreach (var streamName in CanonicalStreams)
        {
            var streamHash = ComputeStableHash64(streamName);
            var initialState = Mix64(baseSeed ^ streamHash);
            _streams[streamName] = new StreamState(initialState, 0L);
        }
    }

    public long GetPosition(string streamName)
    {
        var state = ResolveStream(streamName);
        return state.Position;
    }

    public int NextInt(string streamName, int minInclusive, int maxExclusive)
    {
        if (maxExclusive <= minInclusive)
        {
            throw new ArgumentOutOfRangeException(
                nameof(maxExclusive),
                maxExclusive,
                "maxExclusive must be greater than minInclusive.");
        }

        var state = ResolveStream(streamName);
        var nextValue = NextUInt64(state);
        var range = (ulong)(maxExclusive - minInclusive);
        var sampled = (int)(nextValue % range) + minInclusive;
        state.Position++;
        return sampled;
    }

    public string Snapshot(string streamName)
    {
        var state = ResolveStream(streamName);
        return $"{streamName}|{_seed:X16}|{state.State:X16}|{state.Position}";
    }

    public void Restore(string streamName, string snapshot)
    {
        var target = ResolveStream(streamName);
        if (string.IsNullOrWhiteSpace(snapshot))
        {
            throw new ArgumentException("Snapshot must be non-empty.", nameof(snapshot));
        }

        var parts = snapshot.Split('|');
        if (parts.Length != 4)
        {
            throw new FormatException("Snapshot format must be '<stream>|<hex-seed>|<hex-state>|<position>'.");
        }

        var snapshotStream = parts[0];
        if (!string.Equals(snapshotStream, streamName, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Snapshot stream '{snapshotStream}' does not match target stream '{streamName}'.");
        }

        if (!ulong.TryParse(parts[1], System.Globalization.NumberStyles.HexNumber, null, out var snapshotSeed))
        {
            throw new FormatException($"Snapshot seed is not valid hex: {parts[1]}");
        }

        if (snapshotSeed != _seed)
        {
            throw new InvalidOperationException(
                $"Snapshot seed '{snapshotSeed:X16}' does not match registry seed '{_seed:X16}'.");
        }

        if (!ulong.TryParse(parts[2], System.Globalization.NumberStyles.HexNumber, null, out var restoredState))
        {
            throw new FormatException($"Snapshot state is not valid hex: {parts[2]}");
        }

        if (!long.TryParse(parts[3], out var restoredPosition) || restoredPosition < 0)
        {
            throw new FormatException($"Snapshot position is not valid: {parts[3]}");
        }

        target.State = restoredState;
        target.Position = restoredPosition;
    }

    private StreamState ResolveStream(string streamName)
    {
        if (string.IsNullOrWhiteSpace(streamName))
        {
            throw new ArgumentException("Stream name must be non-empty.", nameof(streamName));
        }

        if (!_streams.TryGetValue(streamName, out var state))
        {
            throw new ArgumentException($"Unknown RNG stream '{streamName}'.", nameof(streamName));
        }

        return state;
    }

    private static ulong NextUInt64(StreamState state)
    {
        state.State += 0x9E3779B97F4A7C15UL;
        var z = state.State;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
        return z ^ (z >> 31);
    }

    private static ulong Mix64(ulong value)
    {
        value ^= value >> 30;
        value *= 0xBF58476D1CE4E5B9UL;
        value ^= value >> 27;
        value *= 0x94D049BB133111EBUL;
        value ^= value >> 31;
        return value;
    }

    private static ulong ComputeStableHash64(string text)
    {
        const ulong offset = 14695981039346656037UL;
        const ulong prime = 1099511628211UL;
        var hash = offset;
        foreach (var ch in text)
        {
            hash ^= ch;
            hash *= prime;
        }

        return hash;
    }

    private sealed class StreamState
    {
        public StreamState(ulong state, long position)
        {
            State = state;
            Position = position;
        }

        public ulong State { get; set; }

        public long Position { get; set; }
    }
}
