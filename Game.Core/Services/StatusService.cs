using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Status;

namespace Game.Core.Services;

/// <summary>
/// Default status lifecycle service.
/// </summary>
public sealed class StatusService : IStatusService
{
    public StatusInstance Apply(StatusInstance current, StatusInstance incoming)
    {
        if (incoming.Stacks <= 0 && incoming.DurationTurns <= 0)
        {
            return current;
        }

        return StatusOperations.Stack(current, incoming);
    }

    public StatusInstance Tick(StatusInstance current, ExpiresTiming timing)
    {
        if (current.ExpiresTiming == ExpiresTiming.Never)
        {
            return current;
        }

        if (current.ExpiresTiming != timing)
        {
            return current;
        }

        return StatusOperations.Decay(current);
    }
}
