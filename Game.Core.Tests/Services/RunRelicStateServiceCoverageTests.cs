using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Domain;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class RunRelicStateServiceCoverageTests
{
    [Fact]
    public async Task ShouldPublishGrantedAndEquippedEvents_WhenEventBusSucceeds()
    {
        var inventory = new InventoryService(new Inventory());
        var bus = new RecordingEventBus();
        var service = new RunRelicStateService(
            inventoryService: inventory,
            displayNameResolver: id => id,
            eventBus: bus,
            publishFailureObserver: null,
            validRelicIdSet: new HashSet<string>(StringComparer.Ordinal) { "relic.a" });

        service.TryGrantAndEquip("relic.a").Should().BeTrue();
        await Task.Delay(50);

        bus.PublishedTypes.Should().Contain(EventTypes.RelicGranted);
        bus.PublishedTypes.Should().Contain(EventTypes.RelicEquipped);
    }

    [Fact]
    public async Task ShouldIgnorePublishFailuresAndKeepStateStable_WhenEventBusThrows()
    {
        var inventory = new InventoryService(new Inventory());
        var failures = new List<string>();
        var service = new RunRelicStateService(
            inventoryService: inventory,
            displayNameResolver: id => $"display:{id}",
            eventBus: new ThrowingEventBus(),
            publishFailureObserver: (eventType, _) => failures.Add(eventType),
            validRelicIdSet: new HashSet<string>(StringComparer.Ordinal) { "relic.a", "relic.b" });

        service.TryGrantAndEquip(" relic.a ").Should().BeTrue();
        await Task.Delay(50);
        var snapshotAfterGrant = service.CreateSnapshot();
        snapshotAfterGrant.EquippedRelicId.Should().Be("relic.a");
        snapshotAfterGrant.EquippedDisplayName.Should().Be("display:relic.a");
        snapshotAfterGrant.AcquiredRelicIds.Should().Contain("relic.a");
        failures.Should().Contain(EventTypes.RelicGranted);
        failures.Should().Contain(EventTypes.RelicEquipped);

        service.TryGrantAndEquip("relic.a").Should().BeFalse();
        service.TryEquipExisting("missing").Should().BeFalse();
        service.TryEquipExisting("relic.b").Should().BeFalse();
        service.TryGrantAndEquip("not-relic").Should().BeFalse();

        service.ClearEquipped();
        var cleared = service.CreateSnapshot();
        cleared.EquippedRelicId.Should().BeEmpty();
        cleared.EquippedDisplayName.Should().BeEmpty();
    }

    private sealed class ThrowingEventBus : IEventBus
    {
        public Task PublishAsync(DomainEvent evt)
        {
            throw new InvalidOperationException("publish failed");
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => NoopDisposable.Instance;
    }

    private sealed class RecordingEventBus : IEventBus
    {
        public List<string> PublishedTypes { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            PublishedTypes.Add(evt.Type);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => NoopDisposable.Instance;
    }

    private sealed class NoopDisposable : IDisposable
    {
        public static NoopDisposable Instance { get; } = new();
        public void Dispose()
        {
        }
    }
}
