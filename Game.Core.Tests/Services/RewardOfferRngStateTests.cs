using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public class RewardOfferRngStateTests
{
    // ACC:T19.4
    [Fact]
    public void ShouldKeepOfferAndRngStateUnchanged_WhenSkippingAndReopeningSameLockedContext()
    {
        var service = new DeterministicOfferService();
        var offerContextId = "reward.act1.floor3.nodeA";
        var initialCandidates = CreateCandidates("offer.a", "offer.b", "offer.c");
        var initialProvenance = CreateProvenance(streamPosition: 120L);

        var snapshotBeforeSkip = service.LockOffer(offerContextId, initialCandidates, initialProvenance);

        var candidatesIfRegenerated = CreateCandidates("offer.x", "offer.y", "offer.z");
        var advancedProvenance = CreateProvenance(streamPosition: 121L);
        var snapshotAfterSkip = service.LockOffer(offerContextId, candidatesIfRegenerated, advancedProvenance);

        snapshotAfterSkip.DisplayOrder.Should().Equal(snapshotBeforeSkip.DisplayOrder,
            "skip must not regenerate a new three-card offer for the same locked context");
        snapshotAfterSkip.StableIds.Should().Equal(snapshotBeforeSkip.StableIds,
            "skip must keep the same locked offer identity set");
        snapshotAfterSkip.Provenance.StreamPosition.Should().Be(snapshotBeforeSkip.Provenance.StreamPosition,
            "skip must not advance the RNG state for an already locked offer context");
    }

    [Fact]
    public void ShouldShowSameThreeCards_WhenReenteringRewardWithoutGeneratingNewOffer()
    {
        var offerContextId = "reward.act1.floor3.nodeB";
        var candidates = CreateCandidates("offer.1", "offer.2", "offer.3");
        var provenance = CreateProvenance(streamPosition: 300L);

        var firstService = new DeterministicOfferService();
        var snapshotBeforeLeave = firstService.LockOffer(offerContextId, candidates, provenance);

        var reopenedService = new DeterministicOfferService();
        var snapshotAfterReenter = reopenedService.LockOffer(offerContextId, candidates, provenance);

        snapshotAfterReenter.DisplayOrder.Should().Equal(snapshotBeforeLeave.DisplayOrder,
            "re-entering reward without generating a new offer should keep the same three-card display order");
        snapshotAfterReenter.StableIds.Should().Equal(snapshotBeforeLeave.StableIds,
            "re-entering reward without generating a new offer should keep the same locked three-card identity set");
        snapshotAfterReenter.Provenance.StreamPosition.Should().Be(snapshotBeforeLeave.Provenance.StreamPosition);
    }

    private static IReadOnlyList<OfferItem> CreateCandidates(string first, string second, string third)
    {
        return new List<OfferItem>
        {
            new OfferItem(first, $"card.{first}", CardForm.Base, null, "common"),
            new OfferItem(second, $"card.{second}", CardForm.U1A, UpgradeRoute.A, "rare"),
            new OfferItem(third, $"card.{third}", CardForm.U1B, UpgradeRoute.B, "uncommon"),
        };
    }

    private static OfferProvenance CreateProvenance(long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node",
            Act: 1,
            Floor: 3,
            NodeId: "N-1-3",
            Difficulty: 0,
            RngStream: RngStreamType.Offer,
            StreamPosition: streamPosition);
    }
}
