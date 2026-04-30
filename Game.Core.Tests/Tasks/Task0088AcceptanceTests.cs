using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Domain;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0088AcceptanceTests
{
    private const string FirstRelicId = "relic.ashen_hourglass";
    private const string SecondRelicId = "relic.obsidian_mirror";
    private static readonly IReadOnlySet<string> KnownRelicIds = StartingRelicService.Definitions
        .Select(definition => definition.RelicId)
        .ToHashSet(StringComparer.Ordinal);

    // ACC:T88.1
    [Fact]
    public void ShouldRecordAcquiredAndEquippedOwnershipOnSharedRunPath_WhenGrantingRelic()
    {
        var service = BuildService();

        var granted = service.TryGrantAndEquip(FirstRelicId);
        var snapshot = service.CreateSnapshot();

        granted.Should().BeTrue();
        snapshot.AcquiredRelicIds.Should().ContainSingle().Which.Should().Be(FirstRelicId);
        snapshot.EquippedRelicId.Should().Be(FirstRelicId);
        snapshot.EquippedDisplayName.Should().Be($"name::{FirstRelicId}");
    }

    // ACC:T88.2
    [Fact]
    public void ShouldExposeAndClearEquippedRelicForPlayerFacingVisibility_WhenEquipStateChanges()
    {
        var service = BuildService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();

        var equipped = service.CreateSnapshot();
        equipped.EquippedRelicId.Should().Be(FirstRelicId);
        equipped.EquippedDisplayName.Should().Be($"name::{FirstRelicId}");

        service.ClearEquipped();
        var cleared = service.CreateSnapshot();
        cleared.EquippedRelicId.Should().BeEmpty();
        cleared.EquippedDisplayName.Should().BeEmpty();
    }

    // ACC:T88.3
    [Fact]
    public void ShouldKeepScopeLimitedToOwnershipAndVisibilityWithoutCombatEffectExecution_WhenGrantingAndEquipping()
    {
        var spyBus = new SpyEventBus();
        var service = BuildService(spyBus);

        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        service.TryGrantAndEquip(SecondRelicId).Should().BeTrue();
        service.TryEquipExisting(FirstRelicId).Should().BeTrue();

        var snapshot = service.CreateSnapshot();
        snapshot.AcquiredRelicIds.Should().BeEquivalentTo(new[] { FirstRelicId, SecondRelicId });
        snapshot.EquippedRelicId.Should().Be(FirstRelicId);
        spyBus.PublishedTypes.Should().Contain(EventTypes.RelicGranted);
        spyBus.PublishedTypes.Should().Contain(EventTypes.RelicEquipped);
        spyBus.PublishedTypes.Should().NotContain(EventTypes.CombatRelicTriggered);

        var eventTypes = typeof(Game.Core.Contracts.EventTypes);
        eventTypes.GetField("CombatRelicTriggered", BindingFlags.Public | BindingFlags.Static)
            .Should()
            .NotBeNull("combat-time relic execution remains deferred for task 88");
    }

    // ACC:T88.3
    [Fact]
    public void ShouldExposeNonBlockingPublishFailuresForObservation_WhenEventBusThrows()
    {
        var observedFailures = new List<string>();
        var service = BuildService(
            new ThrowingEventBus(),
            (eventType, _) => observedFailures.Add(eventType));

        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        observedFailures.Should().Contain(EventTypes.RelicGranted);
        observedFailures.Should().Contain(EventTypes.RelicEquipped);
    }

    // ACC:T88.4
    [Fact]
    public void ShouldKeepOwnershipOnExistingInventoryPathWithoutSecondaryOwnershipStore_WhenInspectingSnapshot()
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        var service = new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            validRelicIdSet: KnownRelicIds);

        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        service.TryGrantAndEquip(SecondRelicId).Should().BeTrue();

        inventory.Items.Keys.Should().Contain(new[] { FirstRelicId, SecondRelicId });
        service.CreateSnapshot().AcquiredRelicIds.Should().BeEquivalentTo(
            inventoryService.GetItemIds().Where(id => id.StartsWith("relic.", StringComparison.Ordinal)));
    }

    // ACC:T88.5
    [Fact]
    public void ShouldRejectDuplicateGrantWithUnchangedOwnershipAndEquippedState_WhenRelicAlreadyAcquired()
    {
        var service = BuildService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();

        var before = service.CreateSnapshot();
        var duplicateResult = service.TryGrantAndEquip(FirstRelicId);
        var after = service.CreateSnapshot();

        duplicateResult.Should().BeFalse();
        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
    }

    [Fact]
    public void ShouldRejectConflictingGrantWithUnchangedOwnershipAndEquippedState_WhenInventoryCannotAddNewRelic()
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 1);
        var service = new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            validRelicIdSet: KnownRelicIds);

        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();
        var before = service.CreateSnapshot();

        var conflictingResult = service.TryGrantAndEquip(SecondRelicId);
        var after = service.CreateSnapshot();

        conflictingResult.Should().BeFalse();
        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
    }

    // ACC:T88.7
    [Fact]
    public void ShouldRejectUndefinedRelicGrantWithUnchangedOwnershipAndEquippedState_WhenRelicIdIsNotInDefinitions()
    {
        var service = BuildService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();

        var before = service.CreateSnapshot();
        var undefinedResult = service.TryGrantAndEquip("relic.undefined_marker");
        var after = service.CreateSnapshot();

        undefinedResult.Should().BeFalse();
        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
    }

    // ACC:T88.7
    [Fact]
    public void ShouldRejectUndefinedRelicEquipWithUnchangedOwnershipAndVisibility_WhenRelicIdIsNotInDefinitions()
    {
        var service = BuildService();
        service.TryGrantAndEquip(FirstRelicId).Should().BeTrue();

        var before = service.CreateSnapshot();
        var undefinedEquipResult = service.TryEquipExisting("relic.undefined_marker");
        var after = service.CreateSnapshot();

        undefinedEquipResult.Should().BeFalse();
        after.AcquiredRelicIds.Should().Equal(before.AcquiredRelicIds);
        after.EquippedRelicId.Should().Be(before.EquippedRelicId);
        after.EquippedDisplayName.Should().Be(before.EquippedDisplayName);
    }

    private static RunRelicStateService BuildService()
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        return new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            validRelicIdSet: KnownRelicIds);
    }

    private static RunRelicStateService BuildService(IEventBus eventBus)
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        return new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            eventBus,
            publishFailureObserver: null,
            validRelicIdSet: KnownRelicIds);
    }

    private static RunRelicStateService BuildService(
        IEventBus eventBus,
        Action<string, Exception> publishFailureObserver)
    {
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        return new RunRelicStateService(
            inventoryService,
            id => $"name::{id}",
            eventBus,
            publishFailureObserver,
            KnownRelicIds);
    }

    private sealed class SpyEventBus : IEventBus
    {
        public List<string> PublishedTypes { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            PublishedTypes.Add(evt.Type);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler)
        {
            return new NoopDisposable();
        }

        private sealed class NoopDisposable : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }

    private sealed class ThrowingEventBus : IEventBus
    {
        public Task PublishAsync(DomainEvent evt)
        {
            throw new InvalidOperationException($"simulated publish failure: {evt.Type}");
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler)
        {
            return new NoopDisposable();
        }

        private sealed class NoopDisposable : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }
}
