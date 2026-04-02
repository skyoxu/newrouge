namespace Game.Core.Contracts.Events;

/// <summary>
/// Lightweight DTO for a card-played contract used by task-level acceptance checks.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0020.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record CardPlayed(
    string RunId,
    string CombatId,
    string CardInstanceId,
    DateTimeOffset PlayedAt
)
{
    public const string EventType = EventTypes.ContractCardPlayed;
}
