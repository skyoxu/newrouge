namespace Game.Core.Contracts.Status;

/// <summary>
/// Status instance applied to a combatant.
/// </summary>
public sealed record StatusInstance(
    string StableId,
    string StatusId,
    StatusType StatusType,
    int Stacks,
    int DurationTurns,
    string SourceId,
    ExpiresTiming ExpiresTiming,
    int Strength
)
{
    public StatusInstance StackWith(StatusInstance incoming)
    {
        return StatusOperations.Stack(this, incoming);
    }

    public StatusInstance AccumulateDuration(int deltaTurns)
    {
        return StatusOperations.AccumulateDuration(this, deltaTurns);
    }

    public StatusInstance Decay(int turns = 1)
    {
        return StatusOperations.Decay(this, turns);
    }
}
