using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

namespace Game.Core.Services;

public sealed record RewardEntrySnapshot(
    string EntryId,
    string RewardType,
    IReadOnlyDictionary<string, object?> Config);

public sealed record RewardEntryModifier(
    string Action,
    string TargetEntryId,
    string RewardType,
    IReadOnlyDictionary<string, object?> Config);

public sealed record RewardEntryModifierApplyResult(
    IReadOnlyList<RewardEntrySnapshot> Entries,
    bool Applied,
    bool Rejected,
    string RejectionReason);

public sealed class RewardEntryModifierPipeline
{
    private static readonly HashSet<string> SupportedRewardTypes = new(StringComparer.Ordinal)
    {
        "gold",
        "consumable",
        "relic",
        "common_card_choice",
        "rare_card_choice",
        "epic_card_choice",
    };

    public bool CanRegister(RewardEntryModifier modifier)
    {
        var action = Normalize(modifier.Action);
        if (action is not ("add" or "remove" or "mutate"))
        {
            return false;
        }

        if (action == "add")
        {
            return !string.IsNullOrWhiteSpace(modifier.RewardType)
                && IsSupportedRewardType(modifier.RewardType)
                && IsValidRewardEntryConfig(modifier.RewardType, modifier.Config);
        }

        if (string.IsNullOrWhiteSpace(modifier.TargetEntryId))
        {
            return false;
        }

        return action != "mutate" || modifier.Config is not null;
    }

    public RewardEntryModifierApplyResult Apply(
        IReadOnlyList<RewardEntrySnapshot> entries,
        IReadOnlyList<RewardEntryModifier> modifiers)
    {
        var original = entries.Select(CloneEntry).ToList();
        var working = entries.Select(CloneEntry).ToList();

        foreach (var modifier in modifiers)
        {
            var action = Normalize(modifier.Action);
            switch (action)
            {
                case "add":
                    if (!IsSupportedRewardType(modifier.RewardType) || !IsValidRewardEntryConfig(modifier.RewardType, modifier.Config))
                    {
                        return new RewardEntryModifierApplyResult(
                            Entries: original,
                            Applied: false,
                            Rejected: true,
                            RejectionReason: $"invalid-add:{modifier.RewardType.Trim()}");
                    }
                    working.Add(new RewardEntrySnapshot(
                        EntryId: modifier.RewardType.Trim(),
                        RewardType: modifier.RewardType.Trim(),
                        Config: CloneConfig(modifier.Config)));
                    break;
                case "remove":
                {
                    var targetId = modifier.TargetEntryId.Trim();
                    var index = working.FindIndex(entry => string.Equals(entry.EntryId, targetId, StringComparison.Ordinal));
                    if (index >= 0)
                    {
                        working.RemoveAt(index);
                    }
                    break;
                }
                case "mutate":
                {
                    var targetId = modifier.TargetEntryId.Trim();
                    var index = working.FindIndex(entry => string.Equals(entry.EntryId, targetId, StringComparison.Ordinal));
                    if (index < 0)
                    {
                        break;
                    }

                    var current = working[index];
                    var nextConfig = current.Config.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
                    foreach (var pair in modifier.Config)
                    {
                        nextConfig[pair.Key] = pair.Value;
                    }

                    if (!IsValidRewardEntryConfig(current.RewardType, nextConfig))
                    {
                        return new RewardEntryModifierApplyResult(
                            Entries: original,
                            Applied: false,
                            Rejected: true,
                            RejectionReason: $"invalid-mutate:{targetId}");
                    }

                    working[index] = new RewardEntrySnapshot(
                        EntryId: current.EntryId,
                        RewardType: current.RewardType,
                        Config: new ReadOnlyDictionary<string, object?>(nextConfig));
                    break;
                }
                default:
                    return new RewardEntryModifierApplyResult(
                        Entries: original,
                        Applied: false,
                        Rejected: true,
                        RejectionReason: $"unsupported-action:{action}");
            }
        }

        return new RewardEntryModifierApplyResult(
            Entries: working,
            Applied: modifiers.Count > 0,
            Rejected: false,
            RejectionReason: string.Empty);
    }

    public static RewardEntrySnapshot CloneEntry(RewardEntrySnapshot entry)
    {
        return new RewardEntrySnapshot(
            EntryId: entry.EntryId,
            RewardType: entry.RewardType,
            Config: CloneConfig(entry.Config));
    }

    private static IReadOnlyDictionary<string, object?> CloneConfig(IReadOnlyDictionary<string, object?> config)
    {
        return new ReadOnlyDictionary<string, object?>(
            config.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal));
    }

    private static bool IsSupportedRewardType(string rewardType)
    {
        return SupportedRewardTypes.Contains(rewardType.Trim());
    }

    private static bool IsValidRewardEntryConfig(string rewardType, IReadOnlyDictionary<string, object?> config)
    {
        var normalized = Normalize(rewardType);
        return normalized switch
        {
            "gold" => TryReadInt(config, "amount", out var amount) && amount >= 0,
            "consumable" => TryReadNonEmptyString(config, "item_id"),
            "relic" => TryReadNonEmptyString(config, "relic_id"),
            "common_card_choice" or "rare_card_choice" or "epic_card_choice"
                => TryReadNonEmptyString(config, "pool_id") && TryReadInt(config, "pick", out var pick) && pick > 0,
            _ => false,
        };
    }

    private static bool TryReadInt(IReadOnlyDictionary<string, object?> config, string key, out int value)
    {
        value = 0;
        if (!config.TryGetValue(key, out var raw) || raw is null)
        {
            return false;
        }

        switch (raw)
        {
            case int i:
                value = i;
                return true;
            case long l when l is >= int.MinValue and <= int.MaxValue:
                value = (int)l;
                return true;
            case string s when int.TryParse(s, out var parsed):
                value = parsed;
                return true;
            default:
                return false;
        }
    }

    private static bool TryReadNonEmptyString(IReadOnlyDictionary<string, object?> config, string key)
    {
        return config.TryGetValue(key, out var raw)
            && raw is string text
            && !string.IsNullOrWhiteSpace(text);
    }

    private static string Normalize(string value)
    {
        return (value ?? string.Empty).Trim().ToLowerInvariant();
    }
}
