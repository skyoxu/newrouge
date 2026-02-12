namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Registry for named deterministic RNG streams.
/// </summary>
public interface IRngStreamRegistry
{
    long GetPosition(string streamName);
    int NextInt(string streamName, int minInclusive, int maxExclusive);
    string Snapshot(string streamName);
    void Restore(string streamName, string snapshot);
}

