using System;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CardPoolRarityDistributionTests
{
    // ACC:T29.6
    [Fact]
    public void ShouldReturnSameRaritySequence_WhenSelectingFromSameActEncounterAndSeed()
    {
        var service = new OfferPreviewService();

        var firstRun = service.DrawRarities(act: 1, encounterType: "combat_normal", seed: 12345, drawCount: 64);
        var secondRun = service.DrawRarities(act: 1, encounterType: "combat_normal", seed: 12345, drawCount: 64);

        firstRun.Should().Equal(secondRun);
    }

    // ACC:T29.6
    [Fact]
    public void ShouldMatchEliteRarityDistribution_WhenSamplingLargeBatchFromElitePool()
    {
        var service = new OfferPreviewService();

        var rarities = service.DrawRarities(act: 1, encounterType: "combat_elite", seed: 7, drawCount: 2000);
        var rareRatio = rarities.Count(rarity => rarity == "rare") / (double)rarities.Count;
        var uncommonRatio = rarities.Count(rarity => rarity == "uncommon") / (double)rarities.Count;
        var commonRatio = rarities.Count(rarity => rarity == "common") / (double)rarities.Count;

        rareRatio.Should().BeApproximately(0.25, 0.03);
        uncommonRatio.Should().BeApproximately(0.35, 0.03);
        commonRatio.Should().BeApproximately(0.40, 0.03);
    }

    [Fact]
    public void ShouldRefuseUnknownEncounterType_WhenSelectingPoolForEncounter()
    {
        var service = new OfferPreviewService();

        Action act = () => service.DrawRarities(act: 1, encounterType: "raid", seed: 99, drawCount: 1);

        act.Should().Throw<ArgumentException>();
    }
}
