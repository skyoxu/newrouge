namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when act configuration is loaded and bound to current run.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ActConfigLoadedEvent(
    string RunId,
    int ActId,
    string ConfigVersion,
    DateTimeOffset LoadedAt
)
{
    public const string EventType = EventTypes.ActConfigLoaded;
}
