using System.Collections.Generic;

namespace Game.Core.Contracts.Combat;

/// <summary>
/// Immutable HUD read-model snapshot consumed by scene adapters to render combat UI state.
/// </summary>
public sealed record CombatHudSnapshot(
    IReadOnlyList<string> HandCards,
    int Energy,
    int DrawPileCount,
    int DiscardPileCount,
    int Difficulty = 0,
    int PlayerHp = 0,
    string TurnState = ""
);
