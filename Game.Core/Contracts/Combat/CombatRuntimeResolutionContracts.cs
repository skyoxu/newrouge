namespace Game.Core.Contracts.Combat;

/// <summary>
/// Input contract for shared runtime card-resolution settlement.
/// </summary>
public sealed record CardResolutionInput(
    string Target,
    string TargetEnemyId,
    int AliveEnemyCount,
    int ResolvedDamageFromPipeline,
    int Block,
    string StatusId,
    int StatusStacks,
    bool Exhaust);

/// <summary>
/// Output contract produced by shared runtime card-resolution settlement.
/// </summary>
public sealed record CardResolutionResult(
    int TotalDamage,
    int PerTargetDamage,
    int BlockGain,
    string StatusDetail,
    bool MoveToExhaust);

/// <summary>
/// Input contract for resolving incoming end-turn damage from enemy intent.
/// </summary>
public sealed record EndTurnEnemyIntentInput(int IntentDamage, int FallbackDamage);
