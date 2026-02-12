namespace Game.Core.Contracts.Content;

/// <summary>
/// Relic instance in a run inventory.
/// </summary>
public sealed record RelicInstance(
    string InstanceId,
    string RelicId,
    DateTimeOffset ObtainedAt,
    string Source
);

