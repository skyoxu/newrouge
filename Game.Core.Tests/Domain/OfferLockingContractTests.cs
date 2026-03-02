using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class OfferLockingContractTests
{
    // ACC:T4.1
    [Fact]
    public void ShouldExposeOfferLockingCoreContracts_WhenInspectingPublicTypes()
    {
        typeof(OfferLockSnapshot).IsPublic.Should().BeTrue();
        typeof(OfferProvenance).IsPublic.Should().BeTrue();
        typeof(OfferItem).IsPublic.Should().BeTrue();
        typeof(IOfferService).IsInterface.Should().BeTrue();
        typeof(IRngStreamRegistry).IsInterface.Should().BeTrue();

        var lockOffer = typeof(IOfferService).GetMethod(nameof(IOfferService.LockOffer));
        var getLockedOffer = typeof(IOfferService).GetMethod(nameof(IOfferService.GetLockedOffer));
        var getPosition = typeof(IRngStreamRegistry).GetMethod(nameof(IRngStreamRegistry.GetPosition));

        lockOffer.Should().NotBeNull();
        getLockedOffer.Should().NotBeNull();
        getPosition.Should().NotBeNull();
    }

    // ACC:T4.2
    [Fact]
    public void ShouldDefineOfferLockSnapshotShape_WhenUsingReflection()
    {
        var properties = typeof(OfferLockSnapshot)
            .GetProperties()
            .ToDictionary(property => property.Name, property => property.PropertyType);

        properties.Should().ContainKey(nameof(OfferLockSnapshot.StableIds))
            .WhoseValue.Should().Be(typeof(IReadOnlyList<string>));
        properties.Should().ContainKey(nameof(OfferLockSnapshot.DisplayOrder))
            .WhoseValue.Should().Be(typeof(IReadOnlyList<string>));
        properties.Should().ContainKey(nameof(OfferLockSnapshot.Provenance))
            .WhoseValue.Should().Be(typeof(OfferProvenance));
        properties.Should().ContainKey(nameof(OfferLockSnapshot.RngStream))
            .WhoseValue.Should().Be(typeof(string));
        properties.Should().ContainKey(nameof(OfferLockSnapshot.IsLockedAtSavePoint))
            .WhoseValue.Should().Be(typeof(bool));
        properties.Should().ContainKey(nameof(OfferLockSnapshot.LockedAt))
            .WhoseValue.Should().Be(typeof(DateTimeOffset?));
    }

    // ACC:T4.3
    [Fact]
    public void ShouldDefineOfferProvenanceShape_WhenUsingReflection()
    {
        var properties = typeof(OfferProvenance)
            .GetProperties()
            .ToDictionary(property => property.Name, property => property.PropertyType);

        properties.Should().ContainKey(nameof(OfferProvenance.SourceType))
            .WhoseValue.Should().Be(typeof(OfferSourceType));
        properties.Should().ContainKey(nameof(OfferProvenance.SourceId))
            .WhoseValue.Should().Be(typeof(string));
        properties.Should().ContainKey(nameof(OfferProvenance.Act))
            .WhoseValue.Should().Be(typeof(int));
        properties.Should().ContainKey(nameof(OfferProvenance.Floor))
            .WhoseValue.Should().Be(typeof(int));
        properties.Should().ContainKey(nameof(OfferProvenance.NodeId))
            .WhoseValue.Should().Be(typeof(string));
        properties.Should().ContainKey(nameof(OfferProvenance.Difficulty))
            .WhoseValue.Should().Be(typeof(int));
        properties.Should().ContainKey(nameof(OfferProvenance.RngStream))
            .WhoseValue.Should().Be(typeof(string));
        properties.Should().ContainKey(nameof(OfferProvenance.StreamPosition))
            .WhoseValue.Should().Be(typeof(long));
    }

    // ACC:T4.4
    [Fact]
    public void ShouldKeepRngStreamConsistentBetweenSnapshotAndProvenance_WhenConstructed()
    {
        const string rngStream = "reward.offer.stream";
        var lockedAt = new DateTimeOffset(2026, 2, 1, 12, 0, 0, TimeSpan.Zero);

        var provenance = new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.1",
            Act: 1,
            Floor: 2,
            NodeId: "N-1-2",
            Difficulty: 3,
            RngStream: rngStream,
            StreamPosition: 42);

        var snapshot = new OfferLockSnapshot(
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-b", "offer-c", "offer-a" },
            Provenance: provenance,
            RngStream: rngStream,
            IsLockedAtSavePoint: true,
            LockedAt: lockedAt);

        snapshot.RngStream.Should().Be(snapshot.Provenance.RngStream);
        snapshot.StableIds.Should().ContainInOrder("offer-a", "offer-b", "offer-c");
        snapshot.IsLockedAtSavePoint.Should().BeTrue();
        snapshot.LockedAt.Should().Be(lockedAt);
    }

    // ACC:T4.5
    [Fact]
    public void ShouldPreserveProvenanceStreamPosition_WhenLockingOfferThroughService()
    {
        var service = new DeterministicOfferService();
        var provenance = new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.3",
            Act: 2,
            Floor: 8,
            NodeId: "N-2-8",
            Difficulty: 5,
            RngStream: "reward.offer",
            StreamPosition: 256L);
        var candidates = new[]
        {
            new OfferItem("offer-1", "card.a", Game.Core.Contracts.Cards.CardForm.Base, null, "common"),
            new OfferItem("offer-2", "card.b", Game.Core.Contracts.Cards.CardForm.U1A, Game.Core.Contracts.Cards.UpgradeRoute.A, "rare"),
        };

        var snapshot = service.LockOffer("ctx-stream-pos", candidates, provenance);

        snapshot.Provenance.Should().Be(provenance);
        snapshot.RngStream.Should().Be(provenance.RngStream);
        snapshot.Provenance.StreamPosition.Should().Be(256L);
        snapshot.IsLockedAtSavePoint.Should().BeTrue();
        snapshot.LockedAt.Should().NotBeNull();
    }

    // ACC:T4.8
    [Fact]
    public void ShouldKeepBooleanSavePointSemanticSeparatedFromTimestamp_WhenCreatingSnapshotContracts()
    {
        var service = new DeterministicOfferService();
        var provenance = new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.1",
            Act: 1,
            Floor: 2,
            NodeId: "N-1-2",
            Difficulty: 3,
            RngStream: "reward.offer",
            StreamPosition: 42L);

        var candidates = new[]
        {
            new OfferItem("offer-a", "card.a", Game.Core.Contracts.Cards.CardForm.Base, null, "common"),
        };

        var lockAtSavePoint = service.LockOffer("ctx-savepoint", candidates, provenance, isLockedAtSavePoint: true);
        var lockOutsideSavePoint = service.LockOffer("ctx-non-savepoint", candidates, provenance, isLockedAtSavePoint: false);
        var repeatedLockInSameContext = service.LockOffer("ctx-savepoint", candidates, provenance, isLockedAtSavePoint: true);

        lockAtSavePoint.IsLockedAtSavePoint.Should().BeTrue();
        lockAtSavePoint.LockedAt.Should().NotBeNull();
        lockOutsideSavePoint.IsLockedAtSavePoint.Should().BeFalse();
        lockOutsideSavePoint.LockedAt.Should().BeNull();
        repeatedLockInSameContext.IsLockedAtSavePoint.Should().Be(lockAtSavePoint.IsLockedAtSavePoint);
    }

    // ACC:T4.10
    [Fact]
    public void ShouldPreserveDeterministicSemanticsWhenRetrievingLockedOffer_WhenContextIsSame()
    {
        var service = new DeterministicOfferService();
        var provenance = new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.10",
            Act: 2,
            Floor: 10,
            NodeId: "N-2-10",
            Difficulty: 5,
            RngStream: "reward.offer",
            StreamPosition: 777L);
        var candidates = new[]
        {
            new OfferItem("offer-a", "card.a", Game.Core.Contracts.Cards.CardForm.Base, null, "common"),
            new OfferItem("offer-b", "card.b", Game.Core.Contracts.Cards.CardForm.U1B, Game.Core.Contracts.Cards.UpgradeRoute.B, "rare"),
        };

        var locked = service.LockOffer("ctx-get-locked", candidates, provenance, isLockedAtSavePoint: true);
        var retrieved = service.GetLockedOffer("ctx-get-locked");

        retrieved.Should().NotBeNull();
        retrieved!.StableIds.Should().Equal(locked.StableIds);
        retrieved.DisplayOrder.Should().Equal(locked.DisplayOrder);
        retrieved.Provenance.Should().Be(locked.Provenance);
        retrieved.RngStream.Should().Be(locked.RngStream);
        retrieved.IsLockedAtSavePoint.Should().BeTrue();
        service.GetLockedOffer("ctx-missing").Should().BeNull();
    }
}
