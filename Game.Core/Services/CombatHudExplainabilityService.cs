using System.Collections.Generic;

namespace Game.Core.Services;

public sealed record CombatHudExplainabilityState(
    int Difficulty,
    int PlayerHp,
    int Energy,
    int DrawPileCount,
    int DiscardPileCount,
    string EnemyIntent,
    string TurnState,
    string SelectedCommandOutcome);

public sealed record CombatHudExplainabilitySnapshot(
    int Difficulty,
    int PlayerHp,
    int Energy,
    int DrawPileCount,
    int DiscardPileCount,
    string EnemyIntent,
    string TurnState,
    string FeedbackMessage);

public sealed class CombatHudExplainabilityService
{
    public CombatHudExplainabilitySnapshot BuildSnapshot(CombatHudExplainabilityState combatState, string feedbackMessage)
    {
        return new CombatHudExplainabilitySnapshot(
            combatState.Difficulty,
            combatState.PlayerHp,
            combatState.Energy,
            combatState.DrawPileCount,
            combatState.DiscardPileCount,
            combatState.EnemyIntent,
            combatState.TurnState,
            feedbackMessage);
    }

    public (CombatHudExplainabilityState NewState, string FeedbackMessage) ApplyCommand(CombatHudExplainabilityState combatState, string commandId)
    {
        if (commandId == "strike" && combatState.Energy > 0)
        {
            var acceptedState = combatState with
            {
                Energy = combatState.Energy - 1,
                SelectedCommandOutcome = "accepted:strike",
            };

            return (acceptedState, $"Strike accepted. Energy -1 (remaining {acceptedState.Energy}).");
        }

        var rejectedState = combatState with
        {
            SelectedCommandOutcome = "rejected:insufficient_energy",
        };

        return (rejectedState, "Command refused: insufficient energy.");
    }

    public (CombatHudExplainabilityState NewState, string FeedbackMessage) TryInvalidAction(
        CombatHudExplainabilityState combatState,
        string actionId)
    {
        return (combatState, "Command refused: invalid action.");
    }

    public CombatHudExplainabilityState HoverPreview(CombatHudExplainabilityState combatState, string previewId)
    {
        return combatState;
    }

    public CombatHudExplainabilityState InspectTarget(CombatHudExplainabilityState combatState, string targetId)
    {
        return combatState;
    }
}
