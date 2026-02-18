using FluentAssertions;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class InterfaceContractsTests
{
    [Fact]
    public void ShouldInMemoryEventBusImplementsContractInterface_WhenExecuted()
    {
        typeof(IEventBus).IsAssignableFrom(typeof(InMemoryEventBus)).Should().BeTrue();
    }

    [Fact]
    public void ShouldServicesNamespaceDoesNotDefineDuplicateIEventBusContract_WhenExecuted()
    {
        var duplicate = typeof(InMemoryEventBus).Assembly.GetType("Game.Core.Services.IEventBus");
        duplicate.Should().BeNull();
    }
}
