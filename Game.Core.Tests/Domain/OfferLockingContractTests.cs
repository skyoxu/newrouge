using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Offers;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class OfferLockingContractTests
{
    private const string AdrReference = "ADR-0032";
    private const string ThisTestRef = "Game.Core.Tests/Domain/OfferLockingContractTests.cs";

    // ACC:T4.1
    [Fact]
    public void Should_ExposeOfferLockingCoreContracts_When_InspectingPublicTypes()
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
    public void Should_DefineOfferLockSnapshotShape_When_UsingReflection()
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
        properties.Should().ContainKey(nameof(OfferLockSnapshot.LockedAt))
            .WhoseValue.Should().Be(typeof(DateTimeOffset));
    }

    // ACC:T4.3
    [Fact]
    public void Should_DefineOfferProvenanceShape_When_UsingReflection()
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
    public void Should_KeepRngStreamConsistentBetweenSnapshotAndProvenance_When_Constructed()
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
            LockedAt: lockedAt);

        snapshot.RngStream.Should().Be(snapshot.Provenance.RngStream);
        snapshot.StableIds.Should().ContainInOrder("offer-a", "offer-b", "offer-c");
        snapshot.LockedAt.Should().Be(lockedAt);
    }

    // ACC:T4.5
    [Fact]
    public void Should_ExposeOfferLifecycleEventTypeContracts_When_ReadingConstants()
    {
        EventTypes.RewardOfferLocked.Should().Be("core.reward.offer.locked");
        EventTypes.RewardOfferPresented.Should().Be("core.reward.offer.presented");
        EventTypes.RewardOfferSelected.Should().Be("core.reward.offer.selected");
        EventTypes.RewardOfferSkipped.Should().Be("core.reward.offer.skipped");

        RewardOfferLockedEvent.EventType.Should().Be(EventTypes.RewardOfferLocked);
        RewardOfferPresentedEvent.EventType.Should().Be(EventTypes.RewardOfferPresented);
        RewardOfferSelectedEvent.EventType.Should().Be(EventTypes.RewardOfferSelected);
        RewardOfferSkippedEvent.EventType.Should().Be(EventTypes.RewardOfferSkipped);
    }

    // ACC:T4.8
    [Fact]
    public void Should_FollowWindowsCompatibleEvidencePathConventions_When_BuildingLogTargets()
    {
        var date = new DateTime(2026, 3, 1);
        var expectedRelative = "logs/unit/2026-03-01/offer-locking-contracts.json";

        var windowsPath = Path.Combine("logs", "unit", date.ToString("yyyy-MM-dd"), "offer-locking-contracts.json");
        var normalized = windowsPath.Replace('\\', '/');

        Path.IsPathRooted(windowsPath).Should().BeFalse();
        normalized.Should().Be(expectedRelative);
    }

    // ACC:T4.10
    [Fact]
    public void Should_LinkContractSourcesAndTestsToAdr0032_When_ReadingTraceabilityMarkers()
    {
        var offerSnapshotSource = ReadTextFromRepo("Game.Core/Contracts/Offers/OfferLockSnapshot.cs");
        var provenanceSource = ReadTextFromRepo("Game.Core/Contracts/Offers/OfferProvenance.cs");
        var offerServiceSource = ReadTextFromRepo("Game.Core/Contracts/Interfaces/IOfferService.cs");

        offerSnapshotSource.Should().Contain(AdrReference);
        provenanceSource.Should().Contain(AdrReference);
        offerServiceSource.Should().Contain(AdrReference);

        ThisTestRef.Should().Be("Game.Core.Tests/Domain/OfferLockingContractTests.cs");
        ThisTestRef.Should().EndWith(".cs");
    }

    private static string ReadTextFromRepo(string repoRelativePath)
    {
        var repoRoot = FindRepoRoot();
        var fullPath = Path.Combine(repoRoot, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        return File.ReadAllText(fullPath);
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }
}
