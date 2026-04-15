using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class MapNavigationSelectionTests
{
    // ACC:T17.9
    [Fact]
    public void ShouldTransitionToNodeEntered_WhenSelectingReachableNode()
    {
        var mapService = CreateSubject();
        var result = mapService.SelectBranch("N-1-2");

        result.Accepted.Should().BeTrue();
        result.StateTransitions.Should().Equal("MapNodeSelected", "MapNodeEntered");
        result.Snapshot.CurrentState.Should().Be("MapNodeEntered");
        result.Snapshot.CurrentNodeId.Should().Be("N-1-2");
        result.Snapshot.NodePreEnterId.Should().Be("N-1-1");
    }

    [Fact]
    public void ShouldKeepStateUnchanged_WhenSelectingUnreachableNode()
    {
        var mapService = CreateSubject();
        var before = mapService.GetSnapshot();
        var result = mapService.SelectBranch("N-9-9");

        result.Accepted.Should().BeFalse();
        result.Code.Should().Be("invalid-branch");
        result.Snapshot.CurrentState.Should().Be(before.CurrentState);
        result.Snapshot.CurrentNodeId.Should().Be(before.CurrentNodeId);
        result.StateTransitions.Should().BeEmpty();
    }

    [Fact]
    public void ShouldReturnDeterministicTransitionSequence_WhenReplayingSameSelection()
    {
        var firstService = CreateSubject();
        var secondService = CreateSubject();

        var firstResult = firstService.SelectBranch("N-1-2");
        var secondResult = secondService.SelectBranch("N-1-2");

        firstResult.Should().BeEquivalentTo(secondResult);
    }

    private static MapService CreateSubject()
    {
        var service = new MapService();
        service.ConfigureAct(
            "Act_1",
            new[]
            {
                new MapNodeDefinition("Act_1", "N-1-1"),
                new MapNodeDefinition("Act_1", "N-1-2"),
                new MapNodeDefinition("Act_1", "N-1-3"),
            },
            new[]
            {
                new MapEdgeDefinition("N-1-1", "N-1-2"),
                new MapEdgeDefinition("N-1-1", "N-1-3"),
            },
            "N-1-1");
        return service;
    }
}
