using System.Collections.Generic;

namespace Game.Core.Contracts.Combat;

/// <summary>
/// Input contract for deterministic end-turn progression.
/// </summary>
public sealed record EndTurnProgressionInput(
    int Difficulty,
    int PlayerHp,
    int PlayerBlock,
    int DrawPileCount,
    int DiscardPileCount,
    int HandCount,
    int IncomingEnemyDamage,
    IReadOnlyList<string> NextHandCards);

/// <summary>
/// Result contract produced by deterministic end-turn progression.
/// </summary>
public sealed record EndTurnProgressionResult(
    int NextPlayerHp,
    int NextPlayerBlock,
    int NextEnergy,
    int NextDrawPileCount,
    int NextDiscardPileCount,
    IReadOnlyList<string> NextHandCards,
    int DamageTaken);
