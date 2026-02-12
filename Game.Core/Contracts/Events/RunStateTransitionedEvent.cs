using Game.Core.Contracts.Run;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised after run state transitions through command handling.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RunStateTransitionedEvent(
    string RunId,
    RunState FromState,
    RunState ToState,
    string Reason,
    DateTimeOffset TransitionedAt
)
{
    public const string EventType = EventTypes.RunStateTransitioned;
}
