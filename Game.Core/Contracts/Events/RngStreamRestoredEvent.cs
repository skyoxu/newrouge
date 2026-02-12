namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when deterministic RNG stream is restored from snapshot.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RngStreamRestoredEvent(
    string RunId,
    string StreamName,
    long PositionAfter,
    string SnapshotHash,
    DateTimeOffset RestoredAt
)
{
    public const string EventType = EventTypes.RngStreamRestored;
}
