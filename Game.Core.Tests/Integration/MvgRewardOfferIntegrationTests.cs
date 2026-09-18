using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Integration;

public sealed class MvgRewardOfferIntegrationTests
{
    // Integration scope: production catalog -> pool selector -> offer lock service.
    // This does not claim to exercise the Godot reward provider or player input.
    [Fact]
    public void CatalogSelectionAndOfferLockShouldPreserveFirstOfferAcrossReentry()
    {
        var pool = new CardPoolSelectionService().SelectSinglePool(CardPoolCatalog.GetAll(), 1, "normal");
        var candidates = pool.CardsByRarity["common"].Take(3)
            .Select((id, index) => new OfferItem($"reward-{index}", id, CardForm.Base, null, "common"))
            .ToArray();
        candidates.Should().HaveCount(3);
        var provenance = new OfferProvenance(OfferSourceType.Reward, pool.PoolId,
            1, 1, "combat-01", 1, "offer", 0);
        var service = new DeterministicOfferService();

        var first = service.LockOffer("mvg-reward-01", candidates, provenance);
        var reentered = service.LockOffer("mvg-reward-01", candidates.Reverse().ToArray(), provenance);

        first.DisplayOrder.Should().Equal(candidates.Select(item => item.OfferItemId));
        reentered.Should().BeSameAs(first);
        reentered.DisplayOrder.Should().Equal(first.DisplayOrder);
        reentered.StableIds.Should().Equal(first.StableIds);
        reentered.Provenance.SourceId.Should().Be(pool.PoolId);
        service.GetLockedOffer("mvg-reward-01").Should().BeSameAs(first);
    }
}
