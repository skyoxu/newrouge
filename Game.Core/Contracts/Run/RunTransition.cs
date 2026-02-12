namespace Game.Core.Contracts.Run;

/// <summary>
/// Deterministic transition result from one run state to another.
/// </summary>
public sealed record RunTransition(
    RunState FromState,
    RunState ToState,
    string Reason,
    string CorrelationId,
    DateTimeOffset TransitionedAt
);

