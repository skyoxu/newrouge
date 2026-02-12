namespace Game.Core.Contracts.Save;

/// <summary>
/// Persisted autosave snapshot for single-slot continue.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032.
/// </remarks>
public sealed record AutosaveSnapshot(
    string RunId,
    string SavePointId,
    string SchemaVersion,
    string StateJson,
    DateTimeOffset SavedAt
);

