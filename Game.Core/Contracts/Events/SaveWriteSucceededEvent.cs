namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when autosave write succeeds.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record SaveWriteSucceededEvent(
    string RunId,
    string SavePointId,
    string SchemaVersion,
    string IntegrityHash,
    DateTimeOffset WrittenAt
)
{
    public const string EventType = EventTypes.SaveWriteSucceeded;
}
