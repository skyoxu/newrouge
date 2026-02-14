namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Registry for named deterministic RNG streams.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IRngStreamRegistry
{
    long GetPosition(string streamName);
    int NextInt(string streamName, int minInclusive, int maxExclusive);
    string Snapshot(string streamName);
    void Restore(string streamName, string snapshot);
}
