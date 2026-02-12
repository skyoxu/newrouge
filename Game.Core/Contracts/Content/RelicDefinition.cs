namespace Game.Core.Contracts.Content;

/// <summary>
/// Relic definition metadata.
/// </summary>
public sealed record RelicDefinition(
    string RelicId,
    string NameKey,
    string Rarity,
    bool UniquePerRun,
    string EffectKey
);

