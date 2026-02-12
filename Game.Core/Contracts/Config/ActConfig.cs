namespace Game.Core.Contracts.Config;

/// <summary>
/// Act-level configuration for map and loot pools.
/// </summary>
public sealed record ActConfig(
    int ActId,
    string Name,
    int Floors,
    string NormalPoolId,
    string ElitePoolId,
    string BossPoolId,
    string ShopPoolId,
    string EventPoolId
);

