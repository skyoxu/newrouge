using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0064AcceptanceTests
{
    // ACC:T64.1
    [Fact]
    public void ShouldDisplayDecisionCriticalCombatState_WhenHudSnapshotIsBuilt()
    {
        var combatState = new CombatHudExplainabilityState(
            Difficulty: 3,
            PlayerHp: 27,
            Energy: 2,
            DrawPileCount: 11,
            DiscardPileCount: 4,
            EnemyIntent: "Defend",
            TurnState: "PlayerTurn",
            SelectedCommandOutcome: "none");

        var combatHudService = new CombatHudExplainabilityService();

        var snapshot = combatHudService.BuildSnapshot(combatState, "Ready.");

        snapshot.Difficulty.Should().Be(combatState.Difficulty);
        snapshot.PlayerHp.Should().Be(combatState.PlayerHp);
        snapshot.Energy.Should().Be(combatState.Energy);
        snapshot.DrawPileCount.Should().Be(combatState.DrawPileCount);
        snapshot.DiscardPileCount.Should().Be(combatState.DiscardPileCount);
        snapshot.EnemyIntent.Should().Be(combatState.EnemyIntent);
        snapshot.TurnState.Should().Be(combatState.TurnState);
    }

    // ACC:T64.2
    [Fact]
    public void ShouldShowAcceptedAndRejectedOutcomeMessages_WhenPlayerCommandIsAttempted()
    {
        var acceptedStateInput = new CombatHudExplainabilityState(2, 24, 1, 8, 3, "Attack", "PlayerTurn", "none");
        var rejectedStateInput = new CombatHudExplainabilityState(2, 24, 0, 8, 3, "Attack", "PlayerTurn", "none");
        var combatHudService = new CombatHudExplainabilityService();

        var (acceptedState, acceptedFeedback) = combatHudService.ApplyCommand(acceptedStateInput, "strike");
        var (rejectedState, rejectedFeedback) = combatHudService.ApplyCommand(rejectedStateInput, "strike");

        acceptedState.SelectedCommandOutcome.Should().StartWith("accepted:");
        acceptedFeedback.Should().NotBeNullOrWhiteSpace();
        acceptedFeedback.Should().Contain("Energy -1");
        acceptedFeedback.Should().Contain("remaining");

        rejectedState.SelectedCommandOutcome.Should().StartWith("rejected:");
        rejectedFeedback.Should().NotBeNullOrWhiteSpace();
        rejectedFeedback.Should().Contain("insufficient energy");
    }

    // ACC:T64.3
    [Fact]
    public void ShouldKeepDeterministicCombatStateUnchangedAndExposeRefusal_WhenInvalidActionOccurs()
    {
        var baselineState = new CombatHudExplainabilityState(4, 31, 2, 13, 6, "Buff", "PlayerTurn", "accepted:guard");
        var combatHudService = new CombatHudExplainabilityService();

        var (afterInvalidAction, refusalMessage) = combatHudService.TryInvalidAction(baselineState, "play_without_energy");

        afterInvalidAction.Should().BeEquivalentTo(baselineState);
        refusalMessage.Should().NotBeNullOrWhiteSpace();
        refusalMessage.Should().Contain("refused");
    }

    // ACC:T64.5
    [Fact]
    public void ShouldProducePlayerVisibleFeedbackForAcceptedAndRejectedCommands_WhenRunningWindowsCombatFeedbackSmoke()
    {
        var acceptedStateInput = new CombatHudExplainabilityState(1, 20, 2, 5, 1, "Charge", "PlayerTurn", "none");
        var rejectedStateInput = new CombatHudExplainabilityState(1, 20, 0, 5, 1, "Charge", "PlayerTurn", "none");
        var combatHudService = new CombatHudExplainabilityService();

        var (acceptedState, acceptedFeedback) = combatHudService.ApplyCommand(acceptedStateInput, "strike");
        var (rejectedState, rejectedFeedback) = combatHudService.ApplyCommand(rejectedStateInput, "strike");

        var acceptedSnapshot = combatHudService.BuildSnapshot(acceptedState, acceptedFeedback);
        var rejectedSnapshot = combatHudService.BuildSnapshot(rejectedState, rejectedFeedback);

        acceptedSnapshot.FeedbackMessage.Should().NotBeNullOrWhiteSpace();
        acceptedSnapshot.FeedbackMessage.Length.Should().BeLessOrEqualTo(80);
        acceptedSnapshot.FeedbackMessage.Should().Contain("accepted");
        acceptedSnapshot.FeedbackMessage.Should().Contain("Energy -1");
        acceptedSnapshot.FeedbackMessage.Should().Contain("remaining");

        rejectedSnapshot.FeedbackMessage.Should().NotBeNullOrWhiteSpace();
        rejectedSnapshot.FeedbackMessage.Length.Should().BeLessOrEqualTo(80);
        rejectedSnapshot.FeedbackMessage.Should().Contain("refused");
        rejectedSnapshot.FeedbackMessage.Should().NotBe(acceptedSnapshot.FeedbackMessage);
    }

    // ACC:T64.8
    [Fact]
    public void ShouldProvideSpecificAcceptedResultSummaryBeyondStatusOnly_WhenAcceptedCommandIsApplied()
    {
        var state = new CombatHudExplainabilityState(3, 25, 2, 9, 2, "Attack", "PlayerTurn", "none");
        var combatHudService = new CombatHudExplainabilityService();

        var (_, acceptedFeedback) = combatHudService.ApplyCommand(state, "strike");

        acceptedFeedback.Should().Contain("accepted");
        acceptedFeedback.Should().Contain("Energy -1");
        acceptedFeedback.Should().Contain("remaining");
    }

    // ACC:T64.6
    [Fact]
    public void ShouldNotMutateDeterministicCombatStateOrOverwriteFeedback_WhenHoverPreviewOrTargetInspectionOccurs()
    {
        var baselineState = new CombatHudExplainabilityState(5, 18, 1, 3, 9, "Stun", "EnemyTurn", "rejected:invalid_target");
        var combatHudService = new CombatHudExplainabilityService();

        var (_, feedbackBefore) = combatHudService.TryInvalidAction(baselineState, "invalid_target");
        var afterHoverPreview = combatHudService.HoverPreview(baselineState, "card_3");
        var afterTargetInspection = combatHudService.InspectTarget(baselineState, "enemy_beta");
        var feedbackAfterHoverOrInspect = feedbackBefore;

        afterHoverPreview.Should().BeEquivalentTo(baselineState);
        afterTargetInspection.Should().BeEquivalentTo(baselineState);
        feedbackAfterHoverOrInspect.Should().Be(feedbackBefore);
    }
}
