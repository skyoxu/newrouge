namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when Continue is blocked due to invalid or incompatible autosave.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032, ADR-0029.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunContinueBlockedEvent(
    string RunId,
    string ReasonCode,
    string Message,
    DateTimeOffset BlockedAt
)
{
    public const string EventType = EventTypes.RunContinueBlocked;
}

