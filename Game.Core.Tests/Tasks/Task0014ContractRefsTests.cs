using FluentAssertions;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0014ContractRefsTests
{
    [Fact]
    public void ShouldExposeCoreRunStartedContractRef_WhenValidatingTask0014()
    {
        RunStartedEvent.EventType.Should().Be("core.run.started");
    }

    [Fact]
    public void ShouldExposeCoreRunResumedContractRef_WhenValidatingTask0014()
    {
        RunResumedEvent.EventType.Should().Be("core.run.resumed");
    }

    [Fact]
    public void ShouldExposeCoreRunContinueBlockedContractRef_WhenValidatingTask0014()
    {
        RunContinueBlockedEvent.EventType.Should().Be("core.run.continue.blocked");
    }
}
