using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0018ContractRefsTests
{
    [Fact]
    [Trait("task", "T18")]
    public void ShouldExposeCombatStartedContractRef_WhenValidatingTask0018()
    {
        CombatStartedEvent.EventType.Should().Be(EventTypes.CombatStarted);
        EventTypes.CombatStarted.Should().Be("core.combat.started");
    }

    [Fact]
    [Trait("task", "T18")]
    public void ShouldExposeCombatTurnStartedContractRef_WhenValidatingTask0018()
    {
        CombatTurnStartedEvent.EventType.Should().Be(EventTypes.CombatTurnStarted);
        EventTypes.CombatTurnStarted.Should().Be("core.combat.turn.started");
    }

    [Fact]
    [Trait("task", "T18")]
    public void ShouldExposeCombatDamageResolvedContractRef_WhenValidatingTask0018()
    {
        CombatDamageResolvedEvent.EventType.Should().Be(EventTypes.CombatDamageResolved);
        EventTypes.CombatDamageResolved.Should().Be("core.combat.damage.resolved");
    }

    [Fact]
    [Trait("task", "T18")]
    public void ShouldExposeCombatEndedContractRef_WhenValidatingTask0018()
    {
        CombatEndedEvent.EventType.Should().Be(EventTypes.CombatEnded);
        EventTypes.CombatEnded.Should().Be("core.combat.ended");
    }

    [Fact]
    [Trait("task", "T18")]
    public void ShouldExposeIntentSelectedContractRef_WhenValidatingTask0018()
    {
        IntentSelectedEvent.EventType.Should().Be(EventTypes.IntentSelected);
        EventTypes.IntentSelected.Should().Be("core.intent.selected");
    }
}
