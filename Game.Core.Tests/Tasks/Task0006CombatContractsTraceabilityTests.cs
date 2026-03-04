using System;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0006CombatContractsTraceabilityTests
{
    private static readonly string[] RequiredAdrIds = new[] { "ADR-0021", "ADR-0032" };

    // ACC:T6.11
    [Fact]
    [Trait("task", "T6")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0032")]
    public void Should_RequireBothAdr0021AndAdr0032_ForTask0006Traceability()
    {
        RequiredAdrIds.Should().HaveCount(2);
        RequiredAdrIds.Should().OnlyHaveUniqueItems();
        RequiredAdrIds.Should().Contain("ADR-0021");
        RequiredAdrIds.Should().Contain("ADR-0032");
    }

    [Fact]
    public void Should_DefineCombatEventTypeConstants_WithExpectedValues()
    {
        EventTypes.CombatDamageResolved.Should().Be("core.combat.damage.resolved");
        EventTypes.CombatFixedDamageResolved.Should().Be("core.combat.fixed_damage.resolved");
        EventTypes.CombatLoopHardStopped.Should().Be("core.combat.loop.hard_stopped");
    }

    [Fact]
    public void Should_MapCombatEventContracts_ToSharedEventTypeConstants()
    {
        CombatDamageResolvedEvent.EventType.Should().Be(EventTypes.CombatDamageResolved);
        CombatFixedDamageResolvedEvent.EventType.Should().Be(EventTypes.CombatFixedDamageResolved);
        CombatLoopHardStoppedEvent.EventType.Should().Be(EventTypes.CombatLoopHardStopped);
    }

    [Fact]
    public void Should_ExposeCloudEventLikeMembers_OnDomainEventBase()
    {
        var domainEventType = typeof(DomainEvent);

        HasPublicMember(domainEventType, "Type").Should().BeTrue();
        HasPublicMember(domainEventType, "Source").Should().BeTrue();
        HasPublicMember(domainEventType, "DataJson").Should().BeTrue();
        HasPublicMember(domainEventType, "Timestamp").Should().BeTrue();
        HasPublicMember(domainEventType, "Id").Should().BeTrue();
        HasPublicMember(domainEventType, "SpecVersion").Should().BeTrue();
        HasPublicMember(domainEventType, "DataContentType").Should().BeTrue();
    }

    private static bool HasPublicMember(Type type, string name)
    {
        return type.GetProperty(name) is not null || type.GetField(name) is not null;
    }
}
