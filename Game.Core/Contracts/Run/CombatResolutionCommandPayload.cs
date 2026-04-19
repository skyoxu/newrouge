using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Game.Core.Contracts.Run;

/// <summary>
/// Structured payload carried by end-of-combat run commands.
/// </summary>
public sealed record CombatResolutionCommandPayload(
    [property: JsonPropertyName("settlement_completed")] bool SettlementCompleted,
    [property: JsonPropertyName("death_triggers_resolved")] bool DeathTriggersResolved,
    [property: JsonPropertyName("reward_offer_presented")] bool RewardOfferPresented,
    [property: JsonPropertyName("run_state_persisted")] bool RunStatePersisted,
    [property: JsonPropertyName("settlement_stages")] string[] SettlementStages,
    [property: JsonPropertyName("reward_handoff")] RewardHandoffPayload? RewardHandoff)
{
    private static readonly string[] RequiredVictoryStages =
    {
        "death_triggers_resolved",
        "reward_offer_presented",
        "run_state_persisted",
    };

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = false,
    };

    public static bool TryParse(string payloadJson, out CombatResolutionCommandPayload? payload)
    {
        payload = null;
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return false;
        }

        try
        {
            payload = JsonSerializer.Deserialize<CombatResolutionCommandPayload>(payloadJson, SerializerOptions);
            return payload is not null;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public bool MeetsVictoryTransitionRequirements()
    {
        return SettlementCompleted
            && DeathTriggersResolved
            && RewardOfferPresented
            && RunStatePersisted
            && ContainsInOrder(SettlementStages ?? Array.Empty<string>(), RequiredVictoryStages)
            && RewardHandoff is not null
            && RewardHandoff.IsConsumable();
    }

    private static bool ContainsInOrder(IReadOnlyList<string> source, IReadOnlyList<string> required)
    {
        if (source.Count == 0 || required.Count == 0)
        {
            return false;
        }

        var requiredIndex = 0;
        for (var sourceIndex = 0; sourceIndex < source.Count && requiredIndex < required.Count; sourceIndex++)
        {
            if (string.Equals(source[sourceIndex], required[requiredIndex], StringComparison.Ordinal))
            {
                requiredIndex++;
            }
        }

        return requiredIndex == required.Count;
    }
}

/// <summary>
/// Reward handoff data consumed by the reward scene and autosave resume flow.
/// </summary>
public sealed record RewardHandoffPayload(
    [property: JsonPropertyName("reward_context_id")] string RewardContextId,
    [property: JsonPropertyName("offer_ids")] string[] OfferIds,
    [property: JsonPropertyName("run_snapshot_id")] string RunSnapshotId)
{
    public bool IsConsumable()
    {
        if (string.IsNullOrWhiteSpace(RewardContextId) || string.IsNullOrWhiteSpace(RunSnapshotId))
        {
            return false;
        }

        return OfferIds is { Length: > 0 } && OfferIds.All(id => !string.IsNullOrWhiteSpace(id));
    }
}
