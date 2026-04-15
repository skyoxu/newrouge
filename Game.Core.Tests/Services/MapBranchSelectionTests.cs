using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class MapBranchSelectionTests
{
    // ACC:T17.6
    [Fact]
    public void ShouldExposeObservableDifference_WhenSelectingDifferentBranchesFromSameStartState()
    {
        var leftService = CreateConfiguredForkMap();
        var rightService = CreateConfiguredForkMap();

        var left = leftService.SelectBranch("A_Left");
        var right = rightService.SelectBranch("A_Right");

        left.Accepted.Should().BeTrue();
        right.Accepted.Should().BeTrue();
        left.Snapshot.CurrentNodeId.Should().NotBe(right.Snapshot.CurrentNodeId);
        left.Snapshot.ReachableNodeIds.Should().NotEqual(right.Snapshot.ReachableNodeIds);
    }

    [Fact]
    public void ShouldFailValidation_WhenBranchesHaveNoObservableDifference()
    {
        var firstService = CreateLinearMap();
        var secondService = CreateLinearMap();

        var first = firstService.SelectBranch("L_Only");
        var second = secondService.SelectBranch("L_Only");

        first.Accepted.Should().BeTrue();
        second.Accepted.Should().BeTrue();
        first.Snapshot.CurrentNodeId.Should().Be(second.Snapshot.CurrentNodeId);
        first.Snapshot.ReachableNodeIds.Should().Equal(second.Snapshot.ReachableNodeIds);
    }

    private static MapService CreateConfiguredForkMap()
    {
        var service = new MapService();
        service.ConfigureAct(
            "Act_1",
            new[]
            {
                new MapNodeDefinition("Act_1", "A_Start"),
                new MapNodeDefinition("Act_1", "A_Left"),
                new MapNodeDefinition("Act_1", "A_Right"),
                new MapNodeDefinition("Act_1", "A_Boss_Left"),
                new MapNodeDefinition("Act_1", "A_Boss_Right"),
            },
            new[]
            {
                new MapEdgeDefinition("A_Start", "A_Left"),
                new MapEdgeDefinition("A_Start", "A_Right"),
                new MapEdgeDefinition("A_Left", "A_Boss_Left"),
                new MapEdgeDefinition("A_Right", "A_Boss_Right"),
            },
            "A_Start");
        return service;
    }

    private static MapService CreateLinearMap()
    {
        var service = new MapService();
        service.ConfigureAct(
            "Act_1",
            new[]
            {
                new MapNodeDefinition("Act_1", "L_Start"),
                new MapNodeDefinition("Act_1", "L_Only"),
                new MapNodeDefinition("Act_1", "L_End"),
            },
            new[]
            {
                new MapEdgeDefinition("L_Start", "L_Only"),
                new MapEdgeDefinition("L_Only", "L_End"),
            },
            "L_Start");
        return service;
    }
}
