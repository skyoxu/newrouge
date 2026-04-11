using FluentAssertions;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task16RunCharacterSelectedContractTests
{
    [Fact]
    public void ShouldExposeRunCharacterSelectedEventType_WhenTask16CharacterSelectionContractIsReferenced()
    {
        var eventType = RunCharacterSelectedEvent.EventType;

        eventType.Should().Be("core.run.character.selected");
    }
}

