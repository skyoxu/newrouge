using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0017AcceptanceTests
{
    // ACC:T17.12
    [Fact]
    [Trait("acceptance", "ACC:T17.12")]
    public void ShouldReturnConsistentRejection_WhenExecutingSameInvalidInputRepeatedly()
    {
        var mapService = CreateSubject();

        var firstAttempt = mapService.SelectBranch("invalid-branch");
        var secondAttempt = mapService.SelectBranch("invalid-branch");

        firstAttempt.Accepted.Should().BeFalse();
        secondAttempt.Accepted.Should().BeFalse();
        firstAttempt.Code.Should().Be(secondAttempt.Code);
        firstAttempt.Snapshot.Should().BeEquivalentTo(secondAttempt.Snapshot);
    }

    // ACC:T17.12
    [Fact]
    [Trait("acceptance", "ACC:T17.12")]
    public void ShouldKeepStateUnchanged_WhenExecutingSameInvalidInputRepeatedly()
    {
        var mapService = CreateSubject();
        var initialSnapshot = mapService.GetSnapshot();
        var initialVersion = mapService.Version;

        mapService.SelectBranch("invalid-branch");
        mapService.SelectBranch("invalid-branch");

        mapService.GetSnapshot().Should().BeEquivalentTo(initialSnapshot);
        mapService.Version.Should().Be(initialVersion, "rejected invalid inputs must not advance state");
    }

    private static MapService CreateSubject()
    {
        var service = new MapService();
        service.ConfigureAct(
            "Act_1",
            new[]
            {
                new MapNodeDefinition("Act_1", "S-1"),
                new MapNodeDefinition("Act_1", "S-2"),
            },
            new[]
            {
                new MapEdgeDefinition("S-1", "S-2"),
            },
            "S-1");
        return service;
    }
}
