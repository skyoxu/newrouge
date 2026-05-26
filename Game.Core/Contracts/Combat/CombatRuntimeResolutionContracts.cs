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
/// Structured effect carried by a displayed enemy intent preview.
/// </summary>
public sealed record EnemyIntentEffectInput(
    string Kind,
    int Magnitude = 0,
    string Timing = "",
    string StatusId = "",
    string Target = "self");

/// <summary>
/// Structured preview bundle that runtime must resolve without re-rolling.
/// </summary>
public sealed record EnemyIntentBundleInput(
    string EnemyId,
    string IntentId,
    string ExecutionFingerprint,
    IReadOnlyList<EnemyIntentEffectInput>? Effects);

/// <summary>
/// Shared runtime result for one accepted enemy-intent resolution pass.
/// </summary>
public sealed record EnemyIntentResolutionResult(
    int ImmediateDamage,
    IReadOnlyList<EnemyIntentEffectInput> ImmediateEffects,
    IReadOnlyList<EnemyIntentEffectInput> DelayedEffects,
    string FailureCode,
    string ExecutionFingerprint);

/// <summary>
/// Input contract for resolving incoming end-turn damage from enemy intent.
/// </summary>
public sealed record EndTurnEnemyIntentInput(
    int IntentDamage,
    int FallbackDamage,
    IReadOnlyList<EnemyIntentBundleInput>? PreviewBundles = null);
