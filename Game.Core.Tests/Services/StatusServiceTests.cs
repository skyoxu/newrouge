using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Status;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class StatusServiceTests
{
    [Fact]
    public void ShouldReturnCurrent_WhenIncomingHasNoPositiveStacksAndDuration()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 2, durationTurns: 3, timing: ExpiresTiming.OwnerEndOfTurnCleanup);
        var incoming = CreateStatus(stacks: 0, durationTurns: 0, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Apply(current, incoming);

        result.Should().Be(current);
    }

    [Fact]
    public void ShouldStack_WhenIncomingHasPositiveStacksOrDuration()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 2, durationTurns: 3, timing: ExpiresTiming.OwnerEndOfTurnCleanup);
        var incoming = CreateStatus(stacks: 1, durationTurns: 2, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Apply(current, incoming);

        result.Stacks.Should().Be(3);
        result.DurationTurns.Should().Be(5);
    }

    [Fact]
    public void ShouldReturnCurrent_WhenTickCalledForNeverExpireStatus()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.Never);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.Should().Be(current);
    }

    [Fact]
    public void ShouldReturnCurrent_WhenTickTimingDoesNotMatchStatusTiming()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.OwnerEndOfTurnCleanup);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.Should().Be(current);
    }

    [Fact]
    public void ShouldDecayDuration_WhenTickTimingMatchesStatusTiming()
    {
        var service = new StatusService();
        var current = CreateStatus(stacks: 1, durationTurns: 4, timing: ExpiresTiming.OwnerStartOfTurn);

        var result = service.Tick(current, ExpiresTiming.OwnerStartOfTurn);

        result.DurationTurns.Should().Be(3);
    }

    [Fact]
    public void ShouldAddThenStack_WhenApplyToTargetIsCalledWithSameStatusId()
    {
        var service = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        service.ApplyToTarget(statuses, CreateStatus(stacks: 1, durationTurns: 3, timing: ExpiresTiming.OwnerEndOfTurnCleanup));
        service.ApplyToTarget(statuses, CreateStatus(stacks: 2, durationTurns: 2, timing: ExpiresTiming.OwnerEndOfTurnCleanup));

        statuses.Should().ContainKey("status.poison");
        statuses["status.poison"].Stacks.Should().Be(3);
        statuses["status.poison"].DurationTurns.Should().Be(5);
    }

    [Fact]
    public void ShouldRemoveExpiredStatus_WhenProcessTurnPhaseConsumesLastTurn()
    {
        var service = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            ["status.poison"] = CreateStatus(stacks: 1, durationTurns: 1, timing: ExpiresTiming.OwnerEndOfTurnCleanup),
        };

        service.ProcessTurnPhase(statuses, ExpiresTiming.OwnerEndOfTurnCleanup);

        statuses.Should().NotContainKey("status.poison");
    }

    [Fact]
    public void ShouldDispelOnlyDebuffs_WhenDispelDebuffsIsCalled()
    {
        var service = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            ["status.poison"] = CreateStatus(stacks: 1, durationTurns: 2, timing: ExpiresTiming.OwnerEndOfTurnCleanup),
            ["status.shield"] = CreateStatus("status.shield", StatusType.Buff, stacks: 1, durationTurns: 4, timing: ExpiresTiming.OwnerEndOfTurnCleanup),
        };

        service.DispelDebuffs(statuses);

        statuses.Should().NotContainKey("status.poison");
        statuses.Should().ContainKey("status.shield");
    }

    [Fact]
    public void ShouldApplyAndStackRageOnlyForAllowedSources_WhenTryApplyRageIsCalled()
    {
        var service = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        var applied = service.TryApplyRage(statuses, stacks: 2, sourceId: "card.warrior.rage_surge");
        var blocked = service.TryApplyRage(statuses, stacks: 2, sourceId: "card.unknown");
        var stacked = service.TryApplyRage(statuses, stacks: 1, sourceId: "card.warrior.battlecry");

        applied.Should().BeTrue();
        blocked.Should().BeFalse();
        stacked.Should().BeTrue();
        statuses.Should().ContainKey(StatusOperations.RageStatusId);
        statuses[StatusOperations.RageStatusId].StatusType.Should().Be(StatusType.Buff);
        statuses[StatusOperations.RageStatusId].ExpiresTiming.Should().Be(ExpiresTiming.Never);
        statuses[StatusOperations.RageStatusId].Stacks.Should().Be(3);
        service.GetRageStacks(statuses).Should().Be(3);
    }

    [Fact]
    public void ShouldResetOnlyRage_WhenResetCombatOnlyStatusesIsCalled()
    {
        var service = new StatusService();
        var statuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal)
        {
            [StatusOperations.RageStatusId] = new StatusInstance(
                StableId: "stable.status.rage",
                StatusId: StatusOperations.RageStatusId,
                StatusType: StatusType.Buff,
                Stacks: 2,
                DurationTurns: 0,
                SourceId: "card.warrior.rage_surge",
                ExpiresTiming: ExpiresTiming.Never,
                Strength: 0),
            ["status.shield"] = CreateStatus(
                statusId: "status.shield",
                statusType: StatusType.Buff,
                stacks: 1,
                durationTurns: 3,
                timing: ExpiresTiming.OwnerEndOfTurnCleanup),
        };

        service.ResetCombatOnlyStatuses(statuses);

        statuses.Should().NotContainKey(StatusOperations.RageStatusId);
        statuses.Should().ContainKey("status.shield");
    }

    private static StatusInstance CreateStatus(int stacks, int durationTurns, ExpiresTiming timing)
    {
        return CreateStatus("status.poison", StatusType.Debuff, stacks, durationTurns, timing);
    }

    private static StatusInstance CreateStatus(
        string statusId,
        StatusType statusType,
        int stacks,
        int durationTurns,
        ExpiresTiming timing)
    {
        return new StatusInstance(
            StableId: "combatant-1",
            StatusId: statusId,
            StatusType: statusType,
            Stacks: stacks,
            DurationTurns: durationTurns,
            SourceId: "source-1",
            ExpiresTiming: timing,
            Strength: 1);
    }
}
