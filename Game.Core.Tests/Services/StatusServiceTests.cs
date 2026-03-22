using FluentAssertions;
using Game.Core.Contracts.Status;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class StatusServiceTests
{
    [Fact]
    public void Should_ReturnCurrent_WhenIncomingHasNoPositiveStacksAndDuration()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 2, durationTurns: 3, timing: ExpiresTiming.OwnerEndOfTurnCleanup);
        var incoming = CreateStatus(stacks: 0, durationTurns: 0, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Apply(current, incoming);

        result.Should().Be(current);
    }

    [Fact]
    public void Should_Stack_WhenIncomingHasPositiveStacksOrDuration()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 2, durationTurns: 3, timing: ExpiresTiming.OwnerEndOfTurnCleanup);
        var incoming = CreateStatus(stacks: 1, durationTurns: 2, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Apply(current, incoming);

        result.Stacks.Should().Be(3);
        result.DurationTurns.Should().Be(5);
    }

    [Fact]
    public void Should_ReturnCurrent_WhenTickCalledForNeverExpireStatus()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.Never);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.Should().Be(current);
    }

    [Fact]
    public void Should_ReturnCurrent_WhenTickTimingDoesNotMatchStatusTiming()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.Should().Be(current);
    }

    [Fact]
    public void Should_DecayDuration_WhenTickTimingMatchesStatusTiming()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.OwnerStartOfTurn);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.DurationTurns.Should().Be(3);
    }

    private static StatusInstance CreateStatus(int stacks, int durationTurns, ExpiresTiming timing)
    {
        return new StatusInstance(
            StableId: "combatant-1",
            StatusId: "status.poison",
            StatusType: StatusType.Debuff,
            Stacks: stacks,
            DurationTurns: durationTurns,
            SourceId: "source-1",
            ExpiresTiming: timing,
            Strength: 1);
    }
}
