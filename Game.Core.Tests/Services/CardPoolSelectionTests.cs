using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CardPoolSelectionTests
{
    // ACC:T29.4
    [Fact]
    public void ShouldResolveBossPoolOnly_WhenActAndEncounterTypeMapToSingleEntry()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll();

        var selectedPool = service.SelectSinglePool(pools, actId: 1, encounterType: "boss");

        selectedPool.PoolId.Should().Be("act1-boss-pool");
        selectedPool.EncounterType.Should().Be("boss");
        pools.Count(pool => pool.ActId == 1 && pool.EncounterType == "boss").Should().Be(1);
    }

    // ACC:T29.4
    [Fact]
    public void ShouldThrowInvalidOperationException_WhenMoreThanOnePoolMatchesActAndEncounterType()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll()
            .Concat(
                new[]
                {
                    new CardPoolDefinition(
                        ActId: 1,
                        EncounterType: "normal",
                        PoolId: "act1-normal-pool-duplicate",
                        CardsByRarity: new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
                        {
                            ["common"] = new[] { "card.dup.common.01" },
                            ["uncommon"] = new[] { "card.dup.uncommon.01" },
                            ["rare"] = new[] { "card.dup.rare.01" },
                        }),
                })
            .ToList();

        Action act = () => service.SelectSinglePool(pools, actId: 1, encounterType: "normal");

        act.Should().Throw<InvalidOperationException>()
            .WithMessage("*exactly one*");
    }

    // ACC:T29.4
    [Fact]
    public void ShouldThrowKeyNotFoundException_WhenEncounterTypeIsNotDefinedForAct()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll();

        Action act = () => service.SelectSinglePool(pools, actId: 2, encounterType: "raid");

        act.Should().Throw<KeyNotFoundException>();
    }

    // ACC:T29.4
    [Fact]
    public void ShouldContainFiveEncounterPoolsWithRarityTiers_WhenActPoolsAreValidated()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll();

        var isValid = service.ValidateActPools(pools, actId: 1);

        isValid.Should().BeTrue();
    }

    [Fact]
    public void ShouldReturnFalse_WhenActPoolsMissRequiredEncounterType()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll()
            .Where(pool => !(pool.ActId == 1 && pool.EncounterType == "event"))
            .ToList();

        var isValid = service.ValidateActPools(pools, actId: 1);

        isValid.Should().BeFalse();
    }

    [Fact]
    public void ShouldReturnFalse_WhenAnyPoolMissesRequiredRarityTier()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll().ToList();
        var target = pools.Single(pool => pool.ActId == 2 && pool.EncounterType == "shop");
        pools.Remove(target);

        var mutatedCardsByRarity = target.CardsByRarity
            .Where(pair => !string.Equals(pair.Key, "rare", StringComparison.Ordinal))
            .ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);

        pools.Add(target with { CardsByRarity = mutatedCardsByRarity });

        var isValid = service.ValidateActPools(pools, actId: 2);

        isValid.Should().BeFalse();
    }

    [Fact]
    public void ShouldReturnFalse_WhenAnyRequiredRarityTierIsEmpty()
    {
        var service = new CardPoolSelectionService();
        var pools = CardPoolCatalog.GetAll().ToList();
        var target = pools.Single(pool => pool.ActId == 3 && pool.EncounterType == "event");
        pools.Remove(target);

        var mutatedCardsByRarity = target.CardsByRarity
            .ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        mutatedCardsByRarity["uncommon"] = Array.Empty<string>();

        pools.Add(target with { CardsByRarity = mutatedCardsByRarity });

        var isValid = service.ValidateActPools(pools, actId: 3);

        isValid.Should().BeFalse();
    }
}
