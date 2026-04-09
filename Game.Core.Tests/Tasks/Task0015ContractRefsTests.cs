using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0015ContractRefsTests
{
    // ACC:T15.3
    [Fact]
    public void ShouldMatchRunDifficultySelectedContractRef_WhenValidatingTask0015()
    {
        RunDifficultySelectedEvent.EventType.Should().Be(EventTypes.RunDifficultySelected);
        EventTypes.RunDifficultySelected.Should().Be("core.run.difficulty.selected");
    }

    // ACC:T15.3
    [Fact]
    public void ShouldStoreSelectedDifficultyInGlobalState_WhenConfirmed()
    {
        RunDifficultyState.SetConfirmedDifficulty(6);
        RunDifficultyState.GetConfirmedDifficulty().Should().Be(6);

        RunDifficultyState.SetConfirmedDifficulty(10);
        RunDifficultyState.GetConfirmedDifficulty().Should().Be(10);
    }
}
