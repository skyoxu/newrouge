namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when run character is selected on new run flow.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunCharacterSelectedEvent(
    string RunId,
    string CharacterId,
    DateTimeOffset SelectedAt
)
{
    public const string EventType = EventTypes.RunCharacterSelected;
}
