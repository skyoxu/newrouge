namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when save data is loaded for continue.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record SaveLoadedEvent(
    string RunId,
    string SavePointId,
    string SchemaVersion,
    DateTimeOffset LoadedAt
)
{
    public const string EventType = EventTypes.SaveLoaded;
}
