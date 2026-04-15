using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0022ContractRefsTests
{
    [Fact]
    public void ShouldExposeCoreEventEnteredContractRef_WhenValidatingTask0022()
    {
        EventEnteredEvent.EventType.Should().Be(EventTypes.EventEntered);
        EventTypes.EventEntered.Should().Be("core.event.entered");
    }

    [Fact]
    public void ShouldExposeCoreEventChoiceCommittedContractRef_WhenValidatingTask0022()
    {
        EventChoiceCommittedEvent.EventType.Should().Be(EventTypes.EventChoiceCommitted);
        EventTypes.EventChoiceCommitted.Should().Be("core.event.choice.committed");
    }

    [Fact]
    public void ShouldExposeCoreDarkCostAppliedContractRef_WhenValidatingTask0022()
    {
        DarkCostAppliedEvent.EventType.Should().Be(EventTypes.DarkCostApplied);
        EventTypes.DarkCostApplied.Should().Be("core.darkcost.applied");
    }
}
