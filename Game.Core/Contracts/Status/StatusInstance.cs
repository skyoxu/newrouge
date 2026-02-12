namespace Game.Core.Contracts.Status;

/// <summary>
/// Status instance applied to a combatant.
/// </summary>
public sealed record StatusInstance(
    string StatusId,
    StatusType StatusType,
    int Stacks,
    int DurationTurns,
    string SourceId,
    ExpiresTiming ExpiresTiming
);

