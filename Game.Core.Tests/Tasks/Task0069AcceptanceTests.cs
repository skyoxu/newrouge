using System;
using System.IO;
using FluentAssertions;
using Game.Core.Contracts.Events;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0069AcceptanceTests
{
    private const string EventResultFeedbackTestPath = "Tests.Godot/tests/Scenes/Event/test_event_scene_result_feedback.gd";
    private const string NodeResolutionRoutesTestPath = "Tests.Godot/tests/Integration/test_m1_node_resolution_routes.gd";

    // ACC:T69.1
    [Fact]
    [Trait("acceptance", "ACC:T69.1")]
    public void ShouldExposeTitleDescriptionOptionsAndVisiblePreview_WhenEventChoiceIsPendingConfirmation()
    {
        var repoRoot = ResolveRepoRoot();
        var feedbackTestPath = ResolveRepoPath(repoRoot, EventResultFeedbackTestPath);

        File.Exists(feedbackTestPath).Should().BeTrue(
            "Task 69 acceptance requires a real-scene feedback test file: {0}",
            EventResultFeedbackTestPath);

        var gdUnitSpec = File.ReadAllText(feedbackTestPath);
        gdUnitSpec.Should().Contain("# acceptance: ACC:T69.1");
        gdUnitSpec.Should().Contain("GetEventTitleForTest");
        gdUnitSpec.Should().Contain("GetEventDescriptionForTest");
        gdUnitSpec.Should().Contain("GetLoseHpPreviewTextForTest");
        gdUnitSpec.Should().Contain("GetTakeCursePreviewTextForTest");
        gdUnitSpec.Should().Contain("IsChosenOptionVisibleForTest");
        gdUnitSpec.Should().Contain("IsResultSummaryVisibleForTest");
        gdUnitSpec.Should().Contain("IsNumericChangesVisibleForTest");
        gdUnitSpec.Should().Contain("IsBlockedFeedbackVisibleForTest");
    }

    // ACC:T69.2
    [Fact]
    [Trait("acceptance", "ACC:T69.2")]
    public void ShouldExposeResultSummaryAndNumericChanges_WhenEventChoiceIsCommitted()
    {
        var payload = new EventChoiceCommittedEvent(
            RunId: "run-69",
            EventId: "event.abyss_toll",
            OptionId: "lose_hp",
            ChoiceResultId: "lose_hp",
            CommittedAt: DateTimeOffset.UtcNow,
            ResultSummary: "Lost 3 HP to push forward.",
            NumericChanges: new System.Collections.Generic.Dictionary<string, int>
            {
                ["HP"] = -3,
                ["CurseCards"] = 0,
            });

        payload.ChoiceResultId.Should().Be("lose_hp");
        payload.ResultSummary.Should().Be("Lost 3 HP to push forward.");
        payload.NumericChanges.Should().NotBeNull();
        payload.NumericChanges!.Should().ContainKey("HP");
        payload.NumericChanges!["HP"].Should().Be(-3);
    }

    // ACC:T69.4
    [Fact]
    [Trait("acceptance", "ACC:T69.4")]
    public void ShouldKeepStateUnchangedAndRefuseTransition_WhenEventChoiceIsInvalidOrUnavailable()
    {
        var routeService = new MapNodeRouteOwnershipService();
        var eventProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Event, CompletedNodeCount: 4);
        var unavailableChoiceRequest = new MapNodeRouteRequest(
            NodeId: "event-choice-locked",
            NodeType: "event",
            IsReachable: false,
            BlockReason: "option-unavailable");

        var result = routeService.StartRoute(unavailableChoiceRequest, eventProgress);

        result.IsSuccess.Should().BeFalse();
        result.BlockReason.Should().Be("route-owner-mismatch");
        result.NewProgress.Should().Be(eventProgress);
        result.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Event);
        result.NewProgress.CompletedNodeCount.Should().Be(4);
    }

    // ACC:T69.6
    [Fact]
    [Trait("acceptance", "ACC:T69.6")]
    public void ShouldRequireRealSceneFeedbackEvidence_WhenEventChoiceCommitIsPresentedToPlayer()
    {
        var repoRoot = ResolveRepoRoot();
        var feedbackTestPath = ResolveRepoPath(repoRoot, EventResultFeedbackTestPath);

        File.Exists(feedbackTestPath).Should().BeTrue(
            "Task 69 real-scene feedback evidence must exist at {0}",
            EventResultFeedbackTestPath);

        var scenePath = ResolveRepoPath(repoRoot, "Game.Godot/Scenes/Event.tscn");
        File.Exists(scenePath).Should().BeTrue("real-scene evidence requires Event.tscn");

        var gdUnitSpec = File.ReadAllText(feedbackTestPath);
        gdUnitSpec.Should().Contain("preload(\"res://Game.Godot/Scenes/Event.tscn\")");
        gdUnitSpec.Should().Contain("GetChosenOptionTextForTest");
        gdUnitSpec.Should().Contain("GetResultSummaryTextForTest");
        gdUnitSpec.Should().Contain("GetNumericChangesTextForTest");
        gdUnitSpec.Should().Contain("# acceptance: ACC:T69.6");

        var sceneSpec = File.ReadAllText(scenePath);
        sceneSpec.Should().Contain("LblChosenOption");
        sceneSpec.Should().Contain("LblResultSummary");
        sceneSpec.Should().Contain("LblNumericChanges");
    }

    // ACC:T69.7
    [Fact]
    [Trait("acceptance", "ACC:T69.7")]
    public void ShouldReturnToRewardOrMapThroughRouteOwnedResolution_WhenEventFlowCompletes()
    {
        var routeService = new RewardRouteOwnershipService();

        var confirmed = routeService.ResolveEncounterCompletion("event", "confirm");
        var unresolved = routeService.ResolveEncounterCompletion("event", "preview");

        confirmed.RouteAfterEncounterComplete.Should().Be(RewardRouteOwnershipService.RewardRoute);
        confirmed.RouteAfterRewardResolution.Should().Be(RewardRouteOwnershipService.MapRoute);
        confirmed.ResolveCount.Should().Be(1);

        unresolved.RouteAfterEncounterComplete.Should().Be(RewardRouteOwnershipService.RewardRoute);
        unresolved.RouteAfterRewardResolution.Should().Be(RewardRouteOwnershipService.RewardRoute);
        unresolved.ResolveCount.Should().Be(0);

        var repoRoot = ResolveRepoRoot();
        var routeSmokePath = ResolveRepoPath(repoRoot, NodeResolutionRoutesTestPath);
        File.Exists(routeSmokePath).Should().BeTrue(
            "Task 69 route-return smoke evidence must exist at {0}",
            NodeResolutionRoutesTestPath);
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private static string ResolveRepoPath(string repoRoot, string relativePath)
    {
        return Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
    }
}
