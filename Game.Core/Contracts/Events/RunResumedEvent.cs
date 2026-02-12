namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when continue flow resumes one run from autosave.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunResumedEvent(
    string RunId,
    string SavePointId,
    DateTimeOffset ResumedAt
)
{
    public const string EventType = EventTypes.RunResumed;
}
