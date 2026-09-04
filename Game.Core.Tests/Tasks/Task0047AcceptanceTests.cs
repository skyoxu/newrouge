

using FluentAssertions;
using Game.Core.Contracts.Combat;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0047AcceptanceTests
{
    // ACC:T47.1
    [Fact]
    public void ShouldReturnStableSequenceAndResult_WhenResolvingSameInputsTwice()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var input = CreatePipelineInput(
            baseDamage: 11,
            strength: 2,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.50,
            isFixedDamage: false,
            rageStacks: 3);

        var first = pipeline.Execute(input);
        var second = pipeline.Execute(input);

        first.Success.Should().BeTrue(first.FailureReason);
        second.Success.Should().BeTrue(second.FailureReason);
        first.ExecutedSteps.Should().Equal(second.ExecutedSteps);
        first.StateAfter.FinalDamage.Should().Be(second.StateAfter.FinalDamage);
        first.StateAfter.FinalCost.Should().Be(second.StateAfter.FinalCost);
        first.StateAfter.Energy.Should().Be(second.StateAfter.Energy);
        first.ExecutionFingerprint.Should().Be(second.ExecutionFingerprint);
    }

    // ACC:T47.2
    [Fact]
    public void ShouldKeepFixedDamageUnchanged_WhenGlobalDamageModifierApplied()
    {
        var fixedDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: 7,
            strength: 100,
            weakMultiplier: 0.10,
            vulnerableMultiplier: 4.00,
            isFixedDamage: true);
        var mutableDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: 7,
            strength: 100,
            weakMultiplier: 0.10,
            vulnerableMultiplier: 4.00,
            isFixedDamage: false);

        fixedDamage.Should().Be(7);
        mutableDamage.Should().NotBe(fixedDamage);
    }

    // ACC:T47.2
    [Fact]
    public void ShouldKeepFinalDamageUnchanged_WhenOnlyOverplayTaxInputsChange()
    {
        var pipeline = new PlayCardResolutionPipeline();
        var baseInput = CreatePipelineInput(
            baseDamage: 12,
            strength: 2,
            weakMultiplier: 1.0,
            vulnerableMultiplier: 1.0,
            isFixedDamage: true,
            rageStacks: 0);

        var lowTaxInput = baseInput with
        {
            DifficultyId = 9,
            CardsPlayedThisTurn = 1,
            OverplayTriggerN = 3,
            OverplayTaxPerCard = 2,
            EnergyBefore = 10,
        };
        var highTaxInput = baseInput with
        {
            DifficultyId = 10,
            CardsPlayedThisTurn = 5,
            OverplayTriggerN = 3,
            OverplayTaxPerCard = 2,
            EnergyBefore = 10,
        };

        var lowTaxResult = pipeline.Execute(lowTaxInput);
        var highTaxResult = pipeline.Execute(highTaxInput);

        lowTaxResult.Success.Should().BeTrue(lowTaxResult.FailureReason);
        highTaxResult.Success.Should().BeTrue(highTaxResult.FailureReason);
        lowTaxResult.OverplayTax.Should().NotBe(highTaxResult.OverplayTax);
        lowTaxResult.StateAfter.FinalCost.Should().NotBe(highTaxResult.StateAfter.FinalCost);
        lowTaxResult.StateAfter.FinalDamage.Should().Be(highTaxResult.StateAfter.FinalDamage);
    }

    // ACC:T47.3
    [Fact]
    public void ShouldKeepFixedDamageAndChangeMutableDamage_WhenApplyingSameModifiers()
    {
        var fixedResult = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: 9,
            strength: 3,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.25,
            isFixedDamage: true,
            rageStacks: 5);
        var mutableResult = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: 9,
            strength: 3,
            weakMultiplier: 0.75,
            vulnerableMultiplier: 1.25,
            isFixedDamage: false,
            rageStacks: 5);

        fixedResult.Should().Be(9);
        mutableResult.Should().NotBe(fixedResult);
    }

    // ACC:T47.6
    [Fact]
    public void ShouldMatchDeclaredTieBreakerOrder_WhenPriorityIsEqual()
    {
        var triggers = new[]
        {
            new CombatTriggerOrderKey("Status.A", Priority: 1, RegistrationOrder: 0),
            new CombatTriggerOrderKey("Relic.A", Priority: 1, RegistrationOrder: 1),
        };

        var result = PlayCardResolutionPipeline.ResolveTriggerOrder(triggers);

        result.Should().Equal("Relic.A", "Status.A");
    }

    private static PlayCardPipelineInput CreatePipelineInput(
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
