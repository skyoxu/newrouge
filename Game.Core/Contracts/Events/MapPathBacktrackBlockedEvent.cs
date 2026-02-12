namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when path backtracking is blocked by route rules.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record MapPathBacktrackBlockedEvent(
    string RunId,
    string FromNodeId,
    string ToNodeId,
    string ReasonCode,
    DateTimeOffset BlockedAt
)
{
    public const string EventType = EventTypes.MapPathBacktrackBlocked;
}
