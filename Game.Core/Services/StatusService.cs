using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Status;

namespace Game.Core.Services;

/// <summary>
/// Default status lifecycle service.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0033, ADR-0021.
/// </remarks>
public sealed class StatusService : IStatusService
{
    private static readonly HashSet<string> RageAllowedSources = new(StringComparer.Ordinal)
    {
        "card.warrior.rage_surge",
        "card.warrior.bloodrush",
        "card.warrior.battlecry",
    };

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

    public bool TryApplyRage(IDictionary<string, StatusInstance> targetStatuses, int stacks, string sourceId)
    {
        ArgumentNullException.ThrowIfNull(targetStatuses);

        if (stacks <= 0 || !RageAllowedSources.Contains(sourceId))
        {
            return false;
        }

        ApplyToTarget(
            targetStatuses,
            new StatusInstance(
                StableId: "stable.status.rage",
                StatusId: StatusOperations.RageStatusId,
                StatusType: StatusType.Buff,
                Stacks: stacks,
                DurationTurns: 0,
                SourceId: sourceId,
                ExpiresTiming: ExpiresTiming.Never,
                Strength: 0));
        return true;
    }

    public int GetRageStacks(IReadOnlyDictionary<string, StatusInstance> targetStatuses)
    {
        ArgumentNullException.ThrowIfNull(targetStatuses);
        if (!targetStatuses.TryGetValue(StatusOperations.RageStatusId, out var rage))
        {
            return 0;
        }

        return Math.Max(0, rage.Stacks);
    }

    public void ResetCombatOnlyStatuses(IDictionary<string, StatusInstance> targetStatuses)
    {
        ArgumentNullException.ThrowIfNull(targetStatuses);
        targetStatuses.Remove(StatusOperations.RageStatusId);
    }
}
