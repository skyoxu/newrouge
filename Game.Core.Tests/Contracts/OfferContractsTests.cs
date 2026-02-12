using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class OfferContractsTests
{
    [Fact]
    public void OfferLockSnapshot_preserves_stable_ids_and_order()
    {
        var provenance = new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "combat-floor-3",
            Act: 1,
            Floor: 3,
            NodeId: "N-1-3",
            Difficulty: 4,
            RngStream: "reward",
            StreamPosition: 128
        );

        var snapshot = new OfferLockSnapshot(
            StableIds: new List<string> { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new List<string> { "offer-b", "offer-a", "offer-c" },
            Provenance: provenance,
            RngStream: "reward",
            LockedAt: DateTimeOffset.UtcNow
        );

        snapshot.StableIds.Should().ContainInOrder("offer-a", "offer-b", "offer-c");
        snapshot.DisplayOrder.Should().ContainInOrder("offer-b", "offer-a", "offer-c");
        snapshot.Provenance.SourceType.Should().Be(OfferSourceType.Reward);
    }

    [Fact]
    public void OfferItem_supports_card_form_and_route()
    {
        var item = new OfferItem(
            OfferItemId: "offer-item-1",
            CardId: "warrior.slash",
            Form: CardForm.U1B,
            Route: UpgradeRoute.B,
            Rarity: "rare"
        );

        item.Form.Should().Be(CardForm.U1B);
        item.Route.Should().Be(UpgradeRoute.B);
    }
}
