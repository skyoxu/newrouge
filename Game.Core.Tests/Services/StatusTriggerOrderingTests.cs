using FluentAssertions;
using Game.Core.Contracts.Combat;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class StatusTriggerOrderingTests
{
    // ACC:T47.4
    [Fact]
    public void ShouldProduceIdenticalTriggerSequenceAndFinalDamage_WhenSettlingSameInputMultipleTimes()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var input = CreateInput(
            baseDamage: 11,
            strength: 2,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.50,
            isFixedDamage: false,
            rageStacks: 3);

        var firstResult = pipeline.Execute(input);
        var secondResult = pipeline.Execute(input);
        var thirdResult = pipeline.Execute(input);

        firstResult.Success.Should().BeTrue();
        secondResult.Success.Should().BeTrue();
        thirdResult.Success.Should().BeTrue();

        firstResult.ExecutedSteps.Should().Equal(secondResult.ExecutedSteps);
        secondResult.ExecutedSteps.Should().Equal(thirdResult.ExecutedSteps);

        firstResult.StateAfter.FinalDamage.Should().Be(secondResult.StateAfter.FinalDamage);
        secondResult.StateAfter.FinalDamage.Should().Be(thirdResult.StateAfter.FinalDamage);

        firstResult.ExecutionFingerprint.Should().Be(secondResult.ExecutionFingerprint);
        secondResult.ExecutionFingerprint.Should().Be(thirdResult.ExecutionFingerprint);
    }

    [Fact]
    public void ShouldKeepFixedDamageUnchanged_WhenSettlingSameInputMultipleTimesWithSimultaneousTriggers()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var input = CreateInput(
            baseDamage: -5,
            strength: 100,
            weakMultiplier: 0.10,
            vulnerableMultiplier: 3.00,
            isFixedDamage: true,
            rageStacks: 99);

        var firstResult = pipeline.Execute(input);
        var secondResult = pipeline.Execute(input);

        firstResult.Success.Should().BeTrue();
        secondResult.Success.Should().BeTrue();

        firstResult.ExecutedSteps.Should().Equal(secondResult.ExecutedSteps);
        firstResult.StateAfter.FinalDamage.Should().Be(-5);
        secondResult.StateAfter.FinalDamage.Should().Be(-5);
    }

    [Fact]
    public void ShouldProduceDifferentFinalDamage_WhenInputChangesBetweenSettlements()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var firstInput = CreateInput(
            baseDamage: 10,
            strength: 1,
            weakMultiplier: 1.00,
            vulnerableMultiplier: 1.00,
            isFixedDamage: false,
            rageStacks: 0);
        var secondInput = firstInput with { RageStacks = 5 };

        var firstResult = pipeline.Execute(firstInput);
        var secondResult = pipeline.Execute(secondInput);

        firstResult.Success.Should().BeTrue();
        secondResult.Success.Should().BeTrue();
        secondResult.StateAfter.FinalDamage.Should().BeGreaterThan(firstResult.StateAfter.FinalDamage);
    }

    // ACC:T47.4
    [Fact]
    public void ShouldApplyDeclaredTieBreakerOrder_WhenPriorityIsEqualForStatusAndRelic()
    {
        var triggers = new[]
        {
            new CombatTriggerOrderKey("Status.Burn", Priority: 1, RegistrationOrder: 0),
            new CombatTriggerOrderKey("Relic.Thorns", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Status.Weak", Priority: 2, RegistrationOrder: 0),
        };

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(triggers);

        ordered.Should().Equal("Relic.Thorns", "Status.Burn", "Status.Weak");
    }

    // ACC:T47.4
    [Fact]
    public void ShouldKeepTriggerOrderStable_WhenInputEnumerationOrderChanges()
    {
        var orderedA = new[]
        {
            new CombatTriggerOrderKey("Status.Burn", Priority: 1, RegistrationOrder: 0),
            new CombatTriggerOrderKey("Relic.Thorns", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Status.Weak", Priority: 2, RegistrationOrder: 0),
        };
        var orderedB = new[]
        {
            new CombatTriggerOrderKey("Status.Weak", Priority: 2, RegistrationOrder: 0),
            new CombatTriggerOrderKey("Relic.Thorns", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Status.Burn", Priority: 1, RegistrationOrder: 0),
        };

        var resultA = PlayCardResolutionPipeline.ResolveTriggerOrder(orderedA);
        var resultB = PlayCardResolutionPipeline.ResolveTriggerOrder(orderedB);

        resultA.Should().Equal("Relic.Thorns", "Status.Burn", "Status.Weak");
        resultB.Should().Equal(resultA);
    }

    // ACC:T47.4
    [Fact]
    public void ShouldUseRegistrationOrderTieBreaker_WhenSourceTypeAndPriorityAreEqual()
    {
        var triggers = new[]
        {
            new CombatTriggerOrderKey("Status.Poison", Priority: 1, RegistrationOrder: 3),
            new CombatTriggerOrderKey("Status.Burn", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Status.Weak", Priority: 1, RegistrationOrder: 2),
        };

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(triggers);

        ordered.Should().Equal("Status.Burn", "Status.Weak", "Status.Poison");
    }

    private static PlayCardPipelineInput CreateInput(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        bool isFixedDamage,
        int rageStacks)
    {
        return new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 2,
            OverplayTriggerN: 2,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 5,
            BaseDamage: baseDamage,
            Strength: strength,
            WeakMultiplier: weakMultiplier,
            VulnerableMultiplier: vulnerableMultiplier,
            IsFixedDamage: isFixedDamage,
            CombatantId: "combatant.player",
            StableId: "stable.player.001",
            RageStacks: rageStacks);
    }
}
