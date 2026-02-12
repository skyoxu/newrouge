namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when autosave snapshot is persisted to the single slot.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record AutosaveWrittenEvent(
    string RunId,
    string SavePointId,
    DateTimeOffset SavedAt,
    string SchemaVersion
)
{
    public const string EventType = EventTypes.AutosaveWritten;
}

