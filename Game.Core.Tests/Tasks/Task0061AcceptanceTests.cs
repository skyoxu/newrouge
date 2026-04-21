using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0061AcceptanceTests
{
    private static readonly RewardRouteOwnershipService RouteService = new();

    // ACC:T61.1
    [Fact]
    public void ShouldUseStandaloneRewardSceneAsset_WhenGameplayRouteLoadsRewardFlow()
    {
        var routeSnapshot = RouteService.BuildSnapshot();

        routeSnapshot.UsesStandaloneRewardSceneAsset.Should().BeTrue();
        routeSnapshot.RewardSceneAssetPath.Should().Be("res://Game.Godot/Scenes/Reward.tscn");
        routeSnapshot.UsesTestDouble.Should().BeFalse();
        routeSnapshot.UsesPlaceholderOnlyContent.Should().BeFalse();
    }

    // ACC:T61.2
    [Theory]
    [InlineData("Combat", "Confirm")]
    [InlineData("Combat", "Skip")]
    [InlineData("Event", "Confirm")]
    [InlineData("Event", "Skip")]
    public void ShouldEnterRewardAndReturnToMapOnce_WhenEncounterCompletesAndRewardActionChosen(string encounterType, string rewardAction)
    {
        var routeResolution = RouteService.ResolveEncounterCompletion(encounterType, rewardAction);

        routeResolution.RouteAfterEncounterComplete.Should().Be("Reward");
        routeResolution.RouteAfterRewardResolution.Should().Be("Map");
        routeResolution.ResolveCount.Should().Be(1);
    }

    [Fact]
    public void ShouldNotResolveMoreThanOnce_WhenRewardConfirmAndSkipAreBothTriggered()
    {
        var routeResolution = RouteService.ResolveConflictingInputs("Combat");

        routeResolution.RouteAfterEncounterComplete.Should().Be("Reward");
        routeResolution.ResolveCount.Should().BeLessOrEqualTo(1);
        routeResolution.RouteAfterRewardResolution.Should().Be("Map");
    }

    // ACC:T61.6
    [Fact]
    public void ShouldIncludeRequiredAdrEvidence_WhenRewardRouteIntegrationIsRecorded()
    {
        var routeSnapshot = RouteService.BuildSnapshot();
        var requiredAdrIds = new[] { "ADR-0010", "ADR-0025", "ADR-0032" };

        routeSnapshot.AdrEvidence.Should().Contain(requiredAdrIds);
    }
}
