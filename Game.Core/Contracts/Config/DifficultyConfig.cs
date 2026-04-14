using System;
using System.Text.Json.Serialization;

namespace Game.Core.Contracts.Config;

/// <summary>
/// Immutable run difficulty snapshot selected at run start.
/// </summary>
public sealed class DifficultyConfig
{
    [JsonPropertyName("difficulty_id")]
    public int DifficultyId { get; }

    [JsonPropertyName("label_key")]
    public string LabelKey { get; }

    [JsonPropertyName("description_key")]
    public string DescriptionKey { get; }

    [JsonPropertyName("ruleset_id")]
    public string RulesetId { get; }

    public DifficultyConfig(int DifficultyId, string LabelKey, string DescriptionKey, string RulesetId)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(DifficultyId, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(DifficultyId, 10);
        ArgumentException.ThrowIfNullOrWhiteSpace(LabelKey);
        ArgumentException.ThrowIfNullOrWhiteSpace(DescriptionKey);
        ArgumentException.ThrowIfNullOrWhiteSpace(RulesetId);

        this.DifficultyId = DifficultyId;
        this.LabelKey = LabelKey;
        this.DescriptionKey = DescriptionKey;
        this.RulesetId = RulesetId;
    }
}
