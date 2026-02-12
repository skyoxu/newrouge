namespace Game.Core.Contracts.Save;

/// <summary>
/// Metadata shown/validated for continue entry.
/// </summary>
public sealed record ContinueMetadata(
    string RunId,
    int DifficultyId,
    int Act,
    string NodeId,
    string IntegrityHash,
    DateTimeOffset UpdatedAt
);

