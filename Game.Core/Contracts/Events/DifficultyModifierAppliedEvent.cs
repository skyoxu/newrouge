namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when one difficulty modifier is applied during run.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0023.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DifficultyModifierAppliedEvent(
    string RunId,
    int DifficultyId,
    string ModifierId,
    int Value,
    DateTimeOffset AppliedAt
)
{
    public const string EventType = EventTypes.DifficultyModifierApplied;
}
