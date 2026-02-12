namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when run difficulty is confirmed and frozen.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0023.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunDifficultySelectedEvent(
    string RunId,
    int DifficultyId,
    DateTimeOffset SelectedAt
)
{
    public const string EventType = EventTypes.RunDifficultySelected;
}
