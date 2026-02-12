namespace Game.Core.Contracts.Config;

/// <summary>
/// Immutable run difficulty configuration.
/// </summary>
public sealed record DifficultyConfig(
    int DifficultyId,
    string Name,
    int BaseEnergyPerTurn,
    int BaseDrawPerTurn,
    int OverplayTriggerN,
    bool EnableOverplayTax,
    bool IsUnlocked
);

