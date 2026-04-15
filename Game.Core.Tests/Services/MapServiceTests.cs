using System;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class MapServiceTests
{
    // ACC:T17.11
    [Fact]
    public void ShouldExposeDeterministicNodeSetAndConnections_WhenActTopologyIsConfigured()
    {
        var mapService = CreateSubject();
        ConfigureForkedAct(mapService);

        var initialSnapshot = mapService.GetSnapshot();

        initialSnapshot.CurrentNodeId.Should().Be("A_Start");
        initialSnapshot.ReachableNodeIds.Should().Equal("A_Left", "A_Right");

        mapService.AllNodeIds.Should().BeEquivalentTo("A_Start", "A_Left", "A_Right", "A_Boss");
        mapService.GetOutgoing("A_Left").Should().Equal("A_Boss");
        mapService.GetOutgoing("A_Right").Should().Equal("A_Boss");

        var selectResult = mapService.SelectBranch("A_Left");

        selectResult.Accepted.Should().BeTrue();
        selectResult.Snapshot.CurrentNodeId.Should().Be("A_Left");
        selectResult.Snapshot.ReachableNodeIds.Should().Equal("A_Boss");
    }

    // ACC:T17.4
    [Fact]
    public void ShouldKeepCurrentNodeAndReachableSetUnchanged_WhenInvalidBranchIdIsSubmitted()
    {
        var mapService = CreateSubject();
        ConfigureForkedAct(mapService);

        var before = mapService.GetSnapshot();
        var beforeVersion = mapService.Version;
        var result = mapService.SelectBranch("A_Unknown");

        result.Accepted.Should().BeFalse();
        result.Code.Should().Be("invalid-branch");
        result.Snapshot.CurrentNodeId.Should().Be(before.CurrentNodeId);
        result.Snapshot.ReachableNodeIds.Should().Equal(before.ReachableNodeIds);
        mapService.Version.Should().Be(beforeVersion);
    }

    // ACC:T17.13
    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("NotARealBranch")]
    public void ShouldNotAdvanceNavigationState_WhenBranchInputIsInvalid(string invalidBranchId)
    {
        var mapService = CreateSubject();
        ConfigureForkedAct(mapService);

        var before = mapService.GetSnapshot();
        var beforeVersion = mapService.Version;
        var result = mapService.SelectBranch(invalidBranchId);

        result.Accepted.Should().BeFalse();
        result.Snapshot.CurrentNodeId.Should().Be(before.CurrentNodeId);
        result.Snapshot.ReachableNodeIds.Should().Equal(before.ReachableNodeIds);
        result.Snapshot.CurrentState.Should().Be(before.CurrentState);
        mapService.Version.Should().Be(beforeVersion);
    }

    [Fact]
    public void ShouldRejectConfigureAct_WhenStartNodeIsMissingFromConfiguredActNodes()
    {
        var mapService = CreateSubject();
        var nodeDefinitions = new[]
        {
            new MapNodeDefinition("OtherAct", "A_Start"),
            new MapNodeDefinition("Act_1", "A_Left"),
        };

        var configure = () => mapService.ConfigureAct(
            "Act_1",
            nodeDefinitions,
            Array.Empty<MapEdgeDefinition>(),
            "A_Start");

        configure.Should().Throw<ArgumentException>()
            .WithMessage("*Start node must exist*");
    }

    [Fact]
    public void ShouldIgnoreEdgesThatReferenceUnknownNodes()
    {
        var mapService = CreateSubject();
        var nodes = new[]
        {
            new MapNodeDefinition("Act_1", "S"),
            new MapNodeDefinition("Act_1", "A"),
            new MapNodeDefinition("Act_1", "B"),
        };
        var edges = new[]
        {
            new MapEdgeDefinition("S", "A"),
            new MapEdgeDefinition("S", "A"),
            new MapEdgeDefinition("S", "Missing"),
            new MapEdgeDefinition("Missing", "B"),
        };

        mapService.ConfigureAct("Act_1", nodes, edges, "S");

        mapService.GetOutgoing("S").Should().Equal("A");
    }

    [Fact]
    public void ShouldReturnEmptyOutgoing_ForUnknownNode()
    {
        var mapService = CreateSubject();
        ConfigureForkedAct(mapService);

        mapService.GetOutgoing("DoesNotExist").Should().BeEmpty();
    }

    private static MapService CreateSubject()
    {
        return new MapService();
    }

    private static void ConfigureForkedAct(MapService mapService)
    {
        var nodeDefinitions = new[]
        {
            new MapNodeDefinition("Act_1", "A_Start", "event"),
            new MapNodeDefinition("Act_1", "A_Left", "combat"),
            new MapNodeDefinition("Act_1", "A_Right", "shop"),
            new MapNodeDefinition("Act_1", "A_Boss", "combat"),
        };

        var edges = new[]
        {
            new MapEdgeDefinition("A_Start", "A_Right"),
            new MapEdgeDefinition("A_Start", "A_Left"),
            new MapEdgeDefinition("A_Left", "A_Boss"),
            new MapEdgeDefinition("A_Right", "A_Boss"),
        };

        mapService.ConfigureAct("Act_1", nodeDefinitions, edges, "A_Start");
    }
}
