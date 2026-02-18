using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task0007AcceptanceTests
{
    [Fact]
    public async Task ShouldPublishAndSubscribeRequiredFiveDomainEvents_WhenEventBusProcessesAllContractEvents()
    {
        IEventBus bus = new InMemoryEventBus();
        var capturedTypes = new List<string>();

        using var _ = bus.Subscribe(evt =>
        {
            capturedTypes.Add(evt.Type);
            return Task.CompletedTask;
        });

        var requiredTypes = new[]
        {
            EventTypes.CombatStarted,
            EventTypes.CombatCardPlayed,
            EventTypes.RewardOfferLocked,
            EventTypes.AutosaveWritten,
            EventTypes.RunStateTransitioned,
        };

        foreach (var type in requiredTypes)
        {
            await bus.PublishAsync(new DomainEvent(
                Type: type,
                Source: nameof(Task0007AcceptanceTests),
                DataJson: "{}",
                Timestamp: DateTimeOffset.UtcNow,
                Id: Guid.NewGuid().ToString("N")
            ));
        }

        capturedTypes.Should().BeEquivalentTo(requiredTypes);
    }

    [Fact]
    public void ShouldMatchTaskContractRefsValues_WhenReadingRequiredFiveEventTypes()
    {
        EventTypes.CombatStarted.Should().Be("core.combat.started");
        EventTypes.CombatCardPlayed.Should().Be("core.combat.card.played");
        EventTypes.RewardOfferLocked.Should().Be("core.reward.offer.locked");
        EventTypes.AutosaveWritten.Should().Be("core.autosave.written");
        EventTypes.RunStateTransitioned.Should().Be("core.run.state.transitioned");
    }
}
