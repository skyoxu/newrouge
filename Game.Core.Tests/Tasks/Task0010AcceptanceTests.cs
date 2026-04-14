using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Status;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task0010AcceptanceTests
{
    // ACC:T10.1
    [Fact]
    [Trait("acceptance", "ACC:T10.1")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0029")]
    public void ShouldStackDuration_WhenApplyingExistingStatus()
    {
        var sut = new StatusService();
        var targetStatuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);

        sut.ApplyToTarget(
            targetStatuses,
            NewStatus("status.poison", StatusType.Debuff, durationTurns: 3));
        targetStatuses.Should().ContainKey("status.poison");
        targetStatuses["status.poison"].StatusId.Should().Be("status.poison");
        targetStatuses["status.poison"].StatusType.Should().Be(StatusType.Debuff);
        targetStatuses["status.poison"].Stacks.Should().Be(1);
        targetStatuses["status.poison"].DurationTurns.Should().Be(3);

        sut.ApplyToTarget(
            targetStatuses,
            NewStatus("status.poison", StatusType.Debuff, durationTurns: 2));

        targetStatuses["status.poison"].Stacks.Should().Be(2);
        targetStatuses["status.poison"].DurationTurns.Should().Be(5);
    }

    // ACC:T10.2
    [Fact]
    [Trait("acceptance", "ACC:T10.2")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0029")]
    public void ShouldDecayDurationOnlyOnOwnerEndOfTurnCleanup_WhenTurnPhaseIsProcessed()
    {
        var sut = new StatusService();
        var targetStatuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        sut.ApplyToTarget(
            targetStatuses,
            NewStatus("status.regen", StatusType.Buff, durationTurns: 3));

        sut.ProcessTurnPhase(targetStatuses, ExpiresTiming.OwnerStartOfTurn);
        targetStatuses["status.regen"].DurationTurns.Should().Be(3);

        sut.ProcessTurnPhase(targetStatuses, ExpiresTiming.OwnerEndOfTurnCleanup);
        targetStatuses["status.regen"].DurationTurns.Should().Be(2);

        var edgeStatuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        edgeStatuses["status.edge"] = NewStatus("status.edge", StatusType.Debuff, durationTurns: 1);

        sut.ProcessTurnPhase(edgeStatuses, ExpiresTiming.OwnerStartOfTurn);
        edgeStatuses.Should().ContainKey("status.edge");
        edgeStatuses["status.edge"].DurationTurns.Should().Be(1);

        sut.ProcessTurnPhase(edgeStatuses, ExpiresTiming.OwnerEndOfTurnCleanup);
        edgeStatuses.Should().NotContainKey("status.edge");
    }

    // ACC:T10.3
    [Fact]
    [Trait("acceptance", "ACC:T10.3")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0029")]
    public void ShouldRemoveDebuffsAndKeepBuffOnlyTargetUnchanged_WhenDispelIsExecuted()
    {
        var sut = new StatusService();

        var mixedTarget = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        mixedTarget["status.shield"] = NewStatus("status.shield", StatusType.Buff, durationTurns: 4);
        mixedTarget["status.burn"] = NewStatus("status.burn", StatusType.Debuff, durationTurns: 2);
        mixedTarget["status.rule"] = NewStatus("status.rule", StatusType.RuleModifier, durationTurns: 6);

        var buffOnlyTarget = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        buffOnlyTarget["status.focus"] = NewStatus("status.focus", StatusType.Buff, durationTurns: 5);

        sut.DispelDebuffs(mixedTarget);
        sut.DispelDebuffs(buffOnlyTarget);

        mixedTarget.ContainsKey("status.burn").Should().BeFalse();
        mixedTarget.ContainsKey("status.shield").Should().BeTrue();
        mixedTarget["status.shield"].DurationTurns.Should().Be(4);
        mixedTarget.ContainsKey("status.rule").Should().BeTrue();
        mixedTarget["status.rule"].DurationTurns.Should().Be(6);

        buffOnlyTarget.Should().ContainKey("status.focus");
        buffOnlyTarget["status.focus"].DurationTurns.Should().Be(5);
    }

    // ACC:T10.4
    [Fact]
    [Trait("acceptance", "ACC:T10.4")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0029")]
    public void ShouldKeepCurrentStatus_WhenIncomingHasNoPositiveStacksAndDuration()
    {
        var sut = new StatusService();
        var current = NewStatus("status.poison", StatusType.Debuff, durationTurns: 3);
        var noOpIncoming = new StatusInstance(
            StableId: "stable.status.poison",
            StatusId: "status.poison",
            StatusType: StatusType.Debuff,
            Stacks: 0,
            DurationTurns: 0,
            SourceId: "task-10",
            ExpiresTiming: ExpiresTiming.OwnerEndOfTurnCleanup,
            Strength: 0);

        var result = sut.Apply(current, noOpIncoming);

        result.Should().Be(current);
    }

    // ACC:T10.5
    [Fact]
    [Trait("acceptance", "ACC:T10.5")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0029")]
    public void ShouldRemoveExpiredStatus_WhenCleanupConsumesLastDuration()
    {
        var sut = new StatusService();
        var targetStatuses = new Dictionary<string, StatusInstance>(StringComparer.Ordinal);
        targetStatuses["status.poison"] = NewStatus("status.poison", StatusType.Debuff, durationTurns: 1);

        sut.ProcessTurnPhase(targetStatuses, ExpiresTiming.OwnerEndOfTurnCleanup);

        targetStatuses.Should().NotContainKey("status.poison");
    }

    private static StatusInstance NewStatus(
        string statusId,
        StatusType statusType,
        int durationTurns)
    {
        return new StatusInstance(
            StableId: $"stable.{statusId}",
            StatusId: statusId,
            StatusType: statusType,
            Stacks: 1,
            DurationTurns: durationTurns,
            SourceId: "task-10",
            ExpiresTiming: ExpiresTiming.OwnerEndOfTurnCleanup,
            Strength: 1);
    }
}
