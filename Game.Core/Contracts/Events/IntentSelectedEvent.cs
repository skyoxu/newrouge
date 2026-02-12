namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when enemy intent is selected for current turn.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record IntentSelectedEvent(
    string RunId,
    string CombatId,
    string ActorId,
    string IntentId,
    DateTimeOffset SelectedAt
)
{
    public const string EventType = EventTypes.IntentSelected;
}
