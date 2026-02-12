namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when autosave write fails.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record SaveWriteFailedEvent(
    string RunId,
    string SavePointId,
    string ReasonCode,
    string Message,
    DateTimeOffset FailedAt
)
{
    public const string EventType = EventTypes.SaveWriteFailed;
}
