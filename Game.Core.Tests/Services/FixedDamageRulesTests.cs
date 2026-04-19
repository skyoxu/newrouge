using FluentAssertions;
using Game.Core.Contracts.Combat;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class FixedDamageRulesTests
{
    // ACC:T47.5
    [Fact]
    public void ShouldKeepFixedDamageUnchanged_WhenBaseDamageIsNegative()
    {
        var baseDamage = -3;
        var strength = 9;
        var weakMultiplier = 0.10;
        var vulnerableMultiplier = 3.00;

        var fixedDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: true);

        fixedDamage.Should().Be(-3, "fixed damage should keep the original value unchanged during settlement");
    }

    // ACC:T47.5
    [Fact]
    public void ShouldReturnDifferentDamage_WhenComparingFixedAndMutableRules()
    {
        var baseDamage = 12;
        var strength = 4;
        var weakMultiplier = 0.50;
        var vulnerableMultiplier = 2.00;

        var fixedDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: true);

        var mutableDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: false);

        fixedDamage.Should().Be(12);
        mutableDamage.Should().Be(16);
        mutableDamage.Should().NotBe(fixedDamage);
    }

    [Fact]
    public void ShouldNotApplyStatusModifiers_WhenDamageIsFixed()
    {
        var baseDamage = 7;
        var strength = 100;
        var weakMultiplier = 0.10;
        var vulnerableMultiplier = 4.00;

        var fixedDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: true);

        var mutableDamage = PlayCardResolutionPipeline.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: false);

        fixedDamage.Should().Be(7);
        mutableDamage.Should().Be(43);
        fixedDamage.Should().NotBe(mutableDamage);
    }
}
