namespace Game.Core.Contracts.Status;

/// <summary>
/// Canonical status contract for Task 5 acceptance semantics.
/// </summary>
public sealed record Status(
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
    public Status StackWith(Status incoming)
    {
        return FromInstance(ToInstance().StackWith(incoming.ToInstance()));
    }

    public Status AccumulateDuration(int deltaTurns)
    {
        return FromInstance(ToInstance().AccumulateDuration(deltaTurns));
    }

    public Status Decay(int turns = 1)
    {
        return FromInstance(ToInstance().Decay(turns));
    }

    internal StatusInstance ToInstance()
    {
        return new StatusInstance(
            StableId: StableId,
            StatusId: StatusId,
            StatusType: StatusType,
            Stacks: Stacks,
            DurationTurns: DurationTurns,
            SourceId: SourceId,
            ExpiresTiming: ExpiresTiming,
            Strength: Strength);
    }

    internal static Status FromInstance(StatusInstance instance)
    {
        return new Status(
            StableId: instance.StableId,
            StatusId: instance.StatusId,
            StatusType: instance.StatusType,
            Stacks: instance.Stacks,
            DurationTurns: instance.DurationTurns,
            SourceId: instance.SourceId,
            ExpiresTiming: instance.ExpiresTiming,
            Strength: instance.Strength);
    }
}
