using System;
using System.Text.Json.Serialization;

namespace Game.Core.Contracts.Save;

/// <summary>
/// Stored run summary metadata shown by the selected owner surface.
/// </summary>
public sealed class RunSummaryMetadata
{
    [JsonPropertyName("run_id")]
    public string RunId { get; }

    [JsonPropertyName("difficulty_id")]
    public int DifficultyId { get; }

    [JsonPropertyName("outcome")]
    public string Outcome { get; }

    [JsonPropertyName("node_progress")]
    public int NodeProgress { get; }

    [JsonPropertyName("failure_or_recovery_reason")]
    public string FailureOrRecoveryReason { get; }

    [JsonPropertyName("owner_surface")]
    public RunSummaryOwnerSurface OwnerSurface { get; }

    [JsonPropertyName("has_reward_metadata_evidence")]
    public bool HasRewardMetadataEvidence { get; }

    [JsonPropertyName("has_relic_metadata_evidence")]
    public bool HasRelicMetadataEvidence { get; }

    [JsonPropertyName("has_resume_evidence")]
    public bool HasResumeEvidence { get; }

    public RunSummaryMetadata(
        string RunId,
        int DifficultyId,
        string Outcome,
        int NodeProgress,
        string FailureOrRecoveryReason,
        RunSummaryOwnerSurface OwnerSurface,
        bool HasRewardMetadataEvidence,
        bool HasRelicMetadataEvidence,
        bool HasResumeEvidence)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(RunId);
        ArgumentOutOfRangeException.ThrowIfLessThan(DifficultyId, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(DifficultyId, 10);
        ArgumentException.ThrowIfNullOrWhiteSpace(Outcome);
        ArgumentOutOfRangeException.ThrowIfLessThan(NodeProgress, 0);
        ArgumentException.ThrowIfNullOrWhiteSpace(FailureOrRecoveryReason);

        this.RunId = RunId;
        this.DifficultyId = DifficultyId;
        this.Outcome = Outcome;
        this.NodeProgress = NodeProgress;
        this.FailureOrRecoveryReason = FailureOrRecoveryReason;
        this.OwnerSurface = OwnerSurface;
        this.HasRewardMetadataEvidence = HasRewardMetadataEvidence;
        this.HasRelicMetadataEvidence = HasRelicMetadataEvidence;
        this.HasResumeEvidence = HasResumeEvidence;
    }
}
