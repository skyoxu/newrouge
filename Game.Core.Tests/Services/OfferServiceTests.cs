using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class OfferServiceTests
{
    // ACC:T46.4
    [Fact]
    public void ShouldReturnQueryableCandidatesAndRejectSilentEmptyResult_WhenGivenRngStreamAndInput()
    {
        var service = CreateService();
        var offerContextId = "ctx.t46.observable";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 11L);

        var lockedSnapshot = service.LockOffer(offerContextId, candidates, provenance);
        var queriedSnapshot = service.GetLockedOffer(offerContextId);

        queriedSnapshot.Should().NotBeNull();
        queriedSnapshot!.DisplayOrder.Should().Equal(candidates.Select(candidate => candidate.OfferItemId));
        queriedSnapshot.StableIds.Should().HaveCount(candidates.Count);
        lockedSnapshot.DisplayOrder.Should().Equal(queriedSnapshot.DisplayOrder);

        var emptyCandidates = Array.Empty<OfferItem>();
        Action lockWithEmptyCandidates = () => service.LockOffer("ctx.t46.empty", emptyCandidates, provenance);

        lockWithEmptyCandidates.Should().Throw<Exception>(
            "the service must not return an empty result without explicit error feedback");
    }

    // ACC:T46.5
    [Fact]
    public void ShouldKeepStableIdsAndDisplayOrderUnchanged_WhenRegeneratedAfterReloadWithSameInputAndRngStream()
    {
        var offerContextId = "ctx.t46.persist";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 128L);

        var firstService = CreateService();
        var firstSnapshot = firstService.LockOffer(offerContextId, candidates, provenance);

        var reloadedService = CreateService();
        var regeneratedSnapshot = reloadedService.LockOffer(offerContextId, candidates, provenance);

        regeneratedSnapshot.StableIds.Should().Equal(firstSnapshot.StableIds);
        regeneratedSnapshot.DisplayOrder.Should().Equal(firstSnapshot.DisplayOrder);
    }

    // ACC:T46.6
    [Fact]
    public void ShouldKeepExistingStableIdsAndDisplayOrder_WhenLockOfferIsTriggeredAgainForLockedContext()
    {
        var service = CreateService();
        var offerContextId = "ctx.t46.relock";
        var provenance = CreateProvenance("reward.offer", 256L);
        var initialCandidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var changedCandidates = CreateCandidates("offer.delta", "offer.epsilon", "offer.zeta");

        var firstSnapshot = service.LockOffer(offerContextId, initialCandidates, provenance);
        _ = service.LockOffer(offerContextId, changedCandidates, provenance);

        var snapshotAfterRelock = service.GetLockedOffer(offerContextId);

        snapshotAfterRelock.Should().NotBeNull();
        snapshotAfterRelock!.StableIds.Should().Equal(firstSnapshot.StableIds,
            "re-triggering lock for an already locked offer must not rewrite stable_id");
        snapshotAfterRelock.DisplayOrder.Should().Equal(firstSnapshot.DisplayOrder,
            "re-triggering lock for an already locked offer must not rewrite display_order");
    }

    // ACC:T46.7
    [Fact]
    public void ShouldPersistProvenanceWithRngStreamAndGenerationBatch_WhenOfferIsLockedAndQueried()
    {
        var service = CreateService();
        var offerContextId = "ctx.t46.provenance";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 512L);

        _ = service.LockOffer(offerContextId, candidates, provenance);
        var queriedSnapshot = service.GetLockedOffer(offerContextId);

        queriedSnapshot.Should().NotBeNull();
        queriedSnapshot!.Provenance.RngStream.Should().Be("reward.offer");
        queriedSnapshot.Provenance.StreamPosition.Should().Be(512L);
        queriedSnapshot.Provenance.SourceType.Should().Be(OfferSourceType.Reward);
        queriedSnapshot.Provenance.SourceId.Should().Be("reward.node.t46");
    }

    // ACC:T46.8
    [Fact]
    public void ShouldKeepLockedResultConsistentBeforeAndAfterReload_WhenUsingSameInputAndRngStream()
    {
        var offerContextId = "ctx.t46.reload-consistency";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 1024L);

        var beforeReloadService = CreateService();
        var beforeReloadSnapshot = beforeReloadService.LockOffer(offerContextId, candidates, provenance);

        var afterReloadService = CreateService();
        var afterReloadSnapshot = afterReloadService.LockOffer(offerContextId, candidates, provenance);

        afterReloadSnapshot.StableIds.Should().Equal(beforeReloadSnapshot.StableIds,
            "the assertion result must directly reflect reload consistency for locked offers");
        afterReloadSnapshot.DisplayOrder.Should().Equal(beforeReloadSnapshot.DisplayOrder,
            "the assertion result must directly reflect reload consistency for locked offers");
        afterReloadSnapshot.Provenance.Should().Be(beforeReloadSnapshot.Provenance);
    }

    private static DeterministicOfferService CreateService()
    {
        return new DeterministicOfferService();
    }

    private static IReadOnlyList<OfferItem> CreateCandidates(params string[] offerItemIds)
    {
        return offerItemIds
            .Select((offerItemId, index) => new OfferItem(
                OfferItemId: offerItemId,
                CardId: $"card.{offerItemId}",
                Form: index % 2 == 0 ? CardForm.Base : CardForm.U1A,
                Route: index % 2 == 0 ? null : UpgradeRoute.A,
                Rarity: index % 2 == 0 ? "common" : "rare"))
            .ToArray();
    }

    private static OfferProvenance CreateProvenance(string rngStream, long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.t46",
            Act: 2,
            Floor: 9,
            NodeId: "N-2-9",
            Difficulty: 3,
            RngStream: rngStream,
            StreamPosition: streamPosition);
    }
}
