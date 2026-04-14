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

    public IReadOnlyList<StatusInstance> Dispel(IEnumerable<StatusInstance> statuses)
    {
        return StatusOperations.Dispel(statuses);
    }

    public void ApplyToTarget(IDictionary<string, StatusInstance> targetStatuses, StatusInstance incoming)
    {
        if (!targetStatuses.TryGetValue(incoming.StatusId, out var existing))
        {
            targetStatuses[incoming.StatusId] = incoming;
            return;
        }

        targetStatuses[incoming.StatusId] = Apply(existing, incoming);
    }

    public void ProcessTurnPhase(IDictionary<string, StatusInstance> targetStatuses, ExpiresTiming timing)
    {
        var keys = targetStatuses.Keys.ToArray();
        foreach (var key in keys)
        {
            var decayed = Tick(targetStatuses[key], timing);
            if (decayed.DurationTurns <= 0 && decayed.ExpiresTiming == timing && decayed.ExpiresTiming != ExpiresTiming.Never)
            {
                targetStatuses.Remove(key);
                continue;
            }

            targetStatuses[key] = decayed;
        }
    }

    public void DispelDebuffs(IDictionary<string, StatusInstance> targetStatuses)
    {
        var retained = Dispel(targetStatuses.Values);
        targetStatuses.Clear();
        foreach (var status in retained)
        {
            targetStatuses[status.StatusId] = status;
        }
    }
}
