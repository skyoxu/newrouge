namespace Game.Core.Contracts.Status;

/// <summary>
/// Pure status operation helpers for stack, duration and deterministic ordering.
/// </summary>
public static class StatusOperations
{
    public const string StrengthStatusId = "status.strength";

    public static bool CanDispel(StatusInstance status)
    {
        if (status.StatusType == StatusType.RuleModifier)
        {
            return false;
        }

        if (string.Equals(status.StatusId, StrengthStatusId, StringComparison.Ordinal))
        {
            return false;
        }

        return true;
    }

    public static IReadOnlyList<StatusInstance> SortByStableId(IEnumerable<StatusInstance> statuses)
    {
        return statuses
            .OrderBy(s => s.StableId, StringComparer.Ordinal)
            .ThenBy(s => s.StatusId, StringComparer.Ordinal)
            .ToArray();
    }

    public static IReadOnlyList<StatusInstance> Dispel(IEnumerable<StatusInstance> statuses)
    {
        return statuses
            .Where(status => !CanDispel(status))
            .ToArray();
    }

    public static StatusInstance Stack(StatusInstance current, StatusInstance incoming)
    {
        if (!IsSameStatus(current, incoming))
        {
            return current;
        }

        return current with
        {
            Stacks = Math.Max(0, current.Stacks + Math.Max(0, incoming.Stacks)),
            DurationTurns = Math.Max(0, current.DurationTurns + Math.Max(0, incoming.DurationTurns)),
            Strength = Math.Max(0, current.Strength + Math.Max(0, incoming.Strength)),
        };
    }

    public static StatusInstance AccumulateDuration(StatusInstance current, int deltaTurns)
    {
        return current with
        {
            DurationTurns = Math.Max(0, current.DurationTurns + Math.Max(0, deltaTurns)),
        };
    }

    public static StatusInstance Decay(StatusInstance current)
    {
        return Decay(current, 1);
    }

    public static StatusInstance Decay(StatusInstance current, int turns)
    {
        return current with
        {
            DurationTurns = Math.Max(0, current.DurationTurns - Math.Max(0, turns)),
        };
    }

    private static bool IsSameStatus(StatusInstance left, StatusInstance right)
    {
        return string.Equals(left.StatusId, right.StatusId, StringComparison.Ordinal) &&
               left.StatusType == right.StatusType;
    }
}
