using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T42")]
public sealed class Task0042AcceptanceTests
{
    // ACC:T42.4
    [Fact]
    [Trait("acceptance", "ACC:T42.4")]
    public void ShouldRefuseBacktrackingAndKeepLockedSelectionUnchanged_WhenAttemptingToReturnToNodePreEnter()
    {
        var mapService = CreateMapWithBacktrackEdge();
        var entryResult = mapService.SelectBranch("N_Left");
        var lockedSnapshot = entryResult.Snapshot;

        var backtrackAttempt = mapService.SelectBranch("N_Start");

        backtrackAttempt.Accepted.Should().BeFalse("entry should lock route options and refuse backtracking to node_pre_enter");
        backtrackAttempt.Code.Should().Be("backtrack-blocked");
        backtrackAttempt.Snapshot.CurrentNodeId.Should().Be(lockedSnapshot.CurrentNodeId);
        backtrackAttempt.Snapshot.ReachableNodeIds.Should().Equal(lockedSnapshot.ReachableNodeIds);
        backtrackAttempt.Snapshot.Version.Should().Be(lockedSnapshot.Version);
    }

    // ACC:T42.5
    [Fact]
    [Trait("acceptance", "ACC:T42.5")]
    public void ShouldKeepLockedStateDeterministic_WhenReplayingSameInput()
    {
        var firstService = CreateDeterministicForkMap();
        var secondService = CreateDeterministicForkMap();

        firstService.SelectBranch("N_Left");
        secondService.SelectBranch("N_Left");
        var firstBeforeMutation = firstService.GetSnapshot();
        var secondBeforeMutation = secondService.GetSnapshot();
        var firstBeforeVersion = firstService.Version;
        var secondBeforeVersion = secondService.Version;

        var firstMutationAttempt = firstService.SelectBranch("N_Right");
        var secondMutationAttempt = secondService.SelectBranch("N_Right");

        firstMutationAttempt.Accepted.Should().BeFalse();
        secondMutationAttempt.Accepted.Should().BeFalse();
        firstMutationAttempt.Code.Should().Be(secondMutationAttempt.Code);
        firstMutationAttempt.Snapshot.Should().BeEquivalentTo(secondMutationAttempt.Snapshot);
        firstMutationAttempt.Code.Should().Be("invalid-branch");
        firstMutationAttempt.Snapshot.CurrentNodeId.Should().Be(firstBeforeMutation.CurrentNodeId);
        firstMutationAttempt.Snapshot.ReachableNodeIds.Should().Equal(firstBeforeMutation.ReachableNodeIds);
        firstMutationAttempt.Snapshot.NodePreEnterId.Should().Be(firstBeforeMutation.NodePreEnterId);
        firstMutationAttempt.Snapshot.CurrentState.Should().Be(firstBeforeMutation.CurrentState);
        firstMutationAttempt.Snapshot.Version.Should().Be(firstBeforeVersion);
        secondMutationAttempt.Snapshot.CurrentNodeId.Should().Be(secondBeforeMutation.CurrentNodeId);
        secondMutationAttempt.Snapshot.ReachableNodeIds.Should().Equal(secondBeforeMutation.ReachableNodeIds);
        secondMutationAttempt.Snapshot.NodePreEnterId.Should().Be(secondBeforeMutation.NodePreEnterId);
        secondMutationAttempt.Snapshot.CurrentState.Should().Be(secondBeforeMutation.CurrentState);
        secondMutationAttempt.Snapshot.Version.Should().Be(secondBeforeVersion);
        firstService.Version.Should().Be(firstBeforeVersion);
        secondService.Version.Should().Be(secondBeforeVersion);
    }

    // ACC:T42.6
    [Fact]
    [Trait("acceptance", "ACC:T42.6")]
    public void ShouldKeepNodePreEnterOrderAndContentIdentical_WhenInputSequenceIsSame()
    {
        var firstTrace = ExecuteNodePreEnterTrace(CreateDeterministicForkMap(), "N_Left", "N_LeftBoss");
        var secondTrace = ExecuteNodePreEnterTrace(CreateDeterministicForkMap(), "N_Left", "N_LeftBoss");

        firstTrace.Should().Equal(secondTrace);
        firstTrace.Should().Equal(
            "N_Start->N_Left|N_LeftBoss|MapNodeSelected>MapNodeEntered",
            "N_Left->N_LeftBoss||MapNodeSelected>MapNodeEntered");
    }

    // ACC:T42.7
    [Fact]
    [Trait("acceptance", "ACC:T42.7")]
    public void ShouldChangeNodePreEnterOrderOrContentByRule_WhenInputSequenceDiffers()
    {
        var leftRouteTrace = ExecuteNodePreEnterTrace(CreateDeterministicForkMap(), "N_Left", "N_LeftBoss");
        var rightRouteTrace = ExecuteNodePreEnterTrace(CreateDeterministicForkMap(), "N_Right", "N_RightBoss");

        leftRouteTrace.Should().NotEqual(rightRouteTrace);
        leftRouteTrace[0].Should().NotBe(rightRouteTrace[0]);
        leftRouteTrace[1].Should().NotBe(rightRouteTrace[1]);
    }

    private static IReadOnlyList<string> ExecuteNodePreEnterTrace(MapService mapService, params string[] branchIds)
    {
        var trace = new List<string>(branchIds.Length);

        foreach (var branchId in branchIds)
        {
            var selectionResult = mapService.SelectBranch(branchId);
            selectionResult.Accepted.Should().BeTrue($"branch '{branchId}' should be reachable in this acceptance route");

            var reachable = string.Join(",", selectionResult.Snapshot.ReachableNodeIds);
            var transitions = string.Join(">", selectionResult.StateTransitions);
            trace.Add($"{selectionResult.Snapshot.NodePreEnterId}->{selectionResult.Snapshot.CurrentNodeId}|{reachable}|{transitions}");
        }

        return trace;
    }

    private static MapService CreateDeterministicForkMap()
    {
        var mapService = new MapService();
        mapService.ConfigureAct(
            "Act_42",
            new[]
            {
                new MapNodeDefinition("Act_42", "N_Start", "event"),
                new MapNodeDefinition("Act_42", "N_Left", "combat"),
                new MapNodeDefinition("Act_42", "N_Right", "shop"),
                new MapNodeDefinition("Act_42", "N_LeftBoss", "combat"),
                new MapNodeDefinition("Act_42", "N_RightBoss", "combat"),
            },
            new[]
            {
                new MapEdgeDefinition("N_Start", "N_Left"),
                new MapEdgeDefinition("N_Start", "N_Right"),
                new MapEdgeDefinition("N_Left", "N_LeftBoss"),
                new MapEdgeDefinition("N_Right", "N_RightBoss"),
            },
            "N_Start");

        return mapService;
    }

    private static MapService CreateMapWithBacktrackEdge()
    {
        var mapService = new MapService();
        mapService.ConfigureAct(
            "Act_42",
            new[]
            {
                new MapNodeDefinition("Act_42", "N_Start", "event"),
                new MapNodeDefinition("Act_42", "N_Left", "combat"),
                new MapNodeDefinition("Act_42", "N_Right", "shop"),
                new MapNodeDefinition("Act_42", "N_LeftBoss", "combat"),
            },
            new[]
            {
                new MapEdgeDefinition("N_Start", "N_Left"),
                new MapEdgeDefinition("N_Start", "N_Right"),
                new MapEdgeDefinition("N_Left", "N_LeftBoss"),
                new MapEdgeDefinition("N_Left", "N_Start"),
            },
            "N_Start");

        return mapService;
    }
}
