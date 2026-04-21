using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0060AcceptanceTests
{
    private static readonly MapNodeRouteOwnershipService RouteService = new();

    // ACC:T60.1
    [Fact]
    public void ShouldCreateActionableRouteEntry_WhenSelectableMapNodeIsChosen()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 0);
        var selectedNode = new MapNodeRouteRequest("combat-01", "combat", IsReachable: true);

        var result = RouteService.StartRoute(selectedNode, initialProgress);

        result.IsSuccess.Should().BeTrue();
        result.Destination.Should().Be(MapNodeRouteDestination.Combat);
        result.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Combat);
    }

    // ACC:T60.2
    [Fact]
    public void ShouldEnterOwnedFlowAndReturnToMap_WhenReachableNodeFlowCompletes()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 0);
        var selectedNode = new MapNodeRouteRequest("shop-01", "shop", IsReachable: true);

        var enterResult = RouteService.StartRoute(selectedNode, initialProgress);
        var completeResult = RouteService.CompleteRoute(enterResult.NewProgress);

        enterResult.IsSuccess.Should().BeTrue();
        enterResult.Destination.Should().Be(MapNodeRouteDestination.Shop);
        completeResult.IsSuccess.Should().BeTrue();
        completeResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        completeResult.NewProgress.CompletedNodeCount.Should().Be(1);
    }

    // ACC:T60.4
    [Fact]
    public void ShouldResolveRouteDestinationFromActualNodeType_WhenMapNodeTypeIsEvent()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 0);
        var selectedNode = new MapNodeRouteRequest("event-01", "event", IsReachable: true);

        var result = RouteService.StartRoute(selectedNode, initialProgress);

        result.IsSuccess.Should().BeTrue();
        result.Destination.Should().Be(MapNodeRouteDestination.Event);
    }

    // ACC:T60.5
    [Theory]
    [InlineData("combat", MapNodeRouteDestination.Combat)]
    [InlineData("event", MapNodeRouteDestination.Event)]
    [InlineData("shop", MapNodeRouteDestination.Shop)]
    [InlineData("rest", MapNodeRouteDestination.Rest)]
    public void ShouldReachOwnedNodeFlow_WhenStartingRouteFromMapSmokeCoverage(string nodeType, MapNodeRouteDestination expectedDestination)
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 0);
        var selectedNode = new MapNodeRouteRequest("node-smoke", nodeType, IsReachable: true);

        var result = RouteService.StartRoute(selectedNode, initialProgress);

        result.IsSuccess.Should().BeTrue();
        result.Destination.Should().Be(expectedDestination);
    }

    // ACC:T60.6
    [Fact]
    public void ShouldRefuseRouteWithExplicitBlockReasonAndKeepRunProgressUnchanged_WhenNodeEntryIsBlocked()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 3);
        var blockedNode = new MapNodeRouteRequest("rest-locked", "rest", IsReachable: false, BlockReason: "NodeLockedByRule");

        var result = RouteService.StartRoute(blockedNode, initialProgress);

        result.IsSuccess.Should().BeFalse();
        result.BlockReason.Should().Be("NodeLockedByRule");
        result.NewProgress.Should().Be(initialProgress);
        result.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        result.NewProgress.CompletedNodeCount.Should().Be(3);
    }

    // ACC:T60.7
    [Fact]
    public void ShouldEitherReturnToMapOrRemainUnchangedWithReason_WhenMapStartsNodeRoute()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 1);
        var reachableNode = new MapNodeRouteRequest("combat-02", "combat", IsReachable: true);
        var blockedNode = new MapNodeRouteRequest("event-locked", "event", IsReachable: false, BlockReason: "RouteBlocked");

        var enterResult = RouteService.StartRoute(reachableNode, initialProgress);
        var completionResult = RouteService.CompleteRoute(enterResult.NewProgress);
        var blockedResult = RouteService.StartRoute(blockedNode, completionResult.NewProgress);

        enterResult.IsSuccess.Should().BeTrue();
        completionResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        completionResult.NewProgress.CompletedNodeCount.Should().Be(2);

        blockedResult.IsSuccess.Should().BeFalse();
        blockedResult.BlockReason.Should().Be("RouteBlocked");
        blockedResult.NewProgress.Should().Be(completionResult.NewProgress);
        blockedResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        blockedResult.NewProgress.CompletedNodeCount.Should().Be(2);
    }

    // ACC:T60.3
    [Fact]
    public void ShouldRejectIllegalNodeTypeAndKeepProgressOnMap_WhenNodeTypeIsUnsupported()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 2);
        var illegalNode = new MapNodeRouteRequest("node-illegal", "unknown-type", IsReachable: true);

        var result = RouteService.StartRoute(illegalNode, initialProgress);

        result.IsSuccess.Should().BeFalse();
        result.BlockReason.Should().Be("unsupported-node-type");
        result.NewProgress.Should().Be(initialProgress);
        result.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        result.NewProgress.CompletedNodeCount.Should().Be(2);
    }
}
