using FluentAssertions;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class InterfaceContractsTests
{
    [Fact]
    public void InMemoryEventBus_implements_contract_interface()
    {
        typeof(IEventBus).IsAssignableFrom(typeof(InMemoryEventBus)).Should().BeTrue();
    }

    [Fact]
    public void Services_namespace_does_not_define_duplicate_IEventBus_contract()
    {
        var duplicate = typeof(InMemoryEventBus).Assembly.GetType("Game.Core.Services.IEventBus");
        duplicate.Should().BeNull();
    }
}
