using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Game.Core.Services;
using Godot;

namespace Game.Godot.Scripts.Reward;

[GlobalClass]
public partial class RewardEntryModifierPipelineBridge : RefCounted
{
    private readonly RewardEntryModifierPipeline _pipeline = new();

    public global::Godot.Collections.Dictionary Apply(
        global::Godot.Collections.Array<global::Godot.Collections.Dictionary> entries,
        global::Godot.Collections.Array<global::Godot.Collections.Dictionary> modifiers)
    {
        var typedEntries = entries.Select(ConvertGodotEntry).ToArray();
        var typedModifiers = modifiers.Select(ConvertGodotModifier).ToArray();
        var result = _pipeline.Apply(typedEntries, typedModifiers);

        var rebuiltEntries = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
        foreach (var entry in result.Entries)
        {
            rebuiltEntries.Add(ConvertToGodotEntry(entry));
        }

        return new global::Godot.Collections.Dictionary
        {
            { "entries", rebuiltEntries },
            { "applied", result.Applied },
            { "rejected", result.Rejected },
            { "rejection_reason", result.RejectionReason },
        };
    }

    private static RewardEntrySnapshot ConvertGodotEntry(global::Godot.Collections.Dictionary source)
    {
        var entryId = Convert.ToString(source["entry_id"]) ?? string.Empty;
        var rewardType = Convert.ToString(source["reward_type"]) ?? string.Empty;
        var config = TryReadConfigDictionary(source, "config");
        return new RewardEntrySnapshot(entryId, rewardType, new ReadOnlyDictionary<string, object?>(config));
    }

    private static RewardEntryModifier ConvertGodotModifier(global::Godot.Collections.Dictionary source)
    {
        var action = source.ContainsKey("action") ? Convert.ToString(source["action"]) ?? string.Empty : string.Empty;
        var targetEntryId = source.ContainsKey("target_entry_id") ? Convert.ToString(source["target_entry_id"]) ?? string.Empty : string.Empty;
        var rewardType = source.ContainsKey("reward_type") ? Convert.ToString(source["reward_type"]) ?? string.Empty : string.Empty;
        var config = TryReadConfigDictionary(source, "config");
        return new RewardEntryModifier(action, targetEntryId, rewardType, new ReadOnlyDictionary<string, object?>(config));
    }

    private static Dictionary<string, object?> TryReadConfigDictionary(global::Godot.Collections.Dictionary source, string key)
    {
        if (!source.ContainsKey(key))
        {
            return new Dictionary<string, object?>(StringComparer.Ordinal);
        }

        var configVariant = source[key];
        if (configVariant.VariantType != Variant.Type.Dictionary)
        {
            return new Dictionary<string, object?>(StringComparer.Ordinal);
        }

        var config = configVariant.AsGodotDictionary();
        return config.ToDictionary(pair => pair.Key.ToString(), pair => (object?)pair.Value, StringComparer.Ordinal);
    }

    private static global::Godot.Collections.Dictionary ConvertToGodotEntry(RewardEntrySnapshot entry)
    {
        var config = new global::Godot.Collections.Dictionary();
        foreach (var pair in entry.Config)
        {
            config[pair.Key] = Variant.From(pair.Value);
        }

        return new global::Godot.Collections.Dictionary
        {
            { "entry_id", entry.EntryId },
            { "reward_type", entry.RewardType },
            { "config", config },
        };
    }
}
