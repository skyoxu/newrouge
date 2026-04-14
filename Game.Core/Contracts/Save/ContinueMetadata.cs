using System;
using System.Text.Json.Serialization;

namespace Game.Core.Contracts.Save;

/// <summary>
/// Metadata shown/validated for continue entry.
/// </summary>
public sealed class ContinueMetadata
{
    [JsonPropertyName("run_id")]
    public string RunId { get; }

    [JsonPropertyName("difficulty_id")]
    public int DifficultyId { get; }

    [JsonPropertyName("label_key")]
    public string LabelKey { get; }

    [JsonPropertyName("description_key")]
    public string DescriptionKey { get; }

    [JsonPropertyName("ruleset_id")]
    public string RulesetId { get; }

    [JsonPropertyName("act")]
    public int Act { get; }

    [JsonPropertyName("node_id")]
    public string NodeId { get; }

    [JsonPropertyName("integrity_hash")]
    public string IntegrityHash { get; }

    [JsonPropertyName("updated_at")]
    public DateTimeOffset UpdatedAt { get; }

    public ContinueMetadata(
        string RunId,
        int DifficultyId,
        string LabelKey,
        string DescriptionKey,
        string RulesetId,
        int Act,
        string NodeId,
        string IntegrityHash,
        DateTimeOffset UpdatedAt)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(RunId);
        ArgumentOutOfRangeException.ThrowIfLessThan(DifficultyId, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(DifficultyId, 10);
        ArgumentException.ThrowIfNullOrWhiteSpace(LabelKey);
        ArgumentException.ThrowIfNullOrWhiteSpace(DescriptionKey);
        ArgumentException.ThrowIfNullOrWhiteSpace(RulesetId);
        ArgumentException.ThrowIfNullOrWhiteSpace(NodeId);
        ArgumentException.ThrowIfNullOrWhiteSpace(IntegrityHash);

        this.RunId = RunId;
        this.DifficultyId = DifficultyId;
        this.LabelKey = LabelKey;
        this.DescriptionKey = DescriptionKey;
        this.RulesetId = RulesetId;
        this.Act = Act;
        this.NodeId = NodeId;
        this.IntegrityHash = IntegrityHash;
        this.UpdatedAt = UpdatedAt;
    }
}
