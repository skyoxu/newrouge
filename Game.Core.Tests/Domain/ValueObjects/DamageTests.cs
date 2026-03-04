using FluentAssertions;
using Game.Core.Domain.ValueObjects;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Domain.ValueObjects;

public sealed class DamageTests
{
    [Fact]
    public void ShouldClampEffectiveAmountToZero_WhenRawAmountIsNegative()
    {
        var damage = new Damage(-10, DamageType.Physical);

        damage.EffectiveAmount.Should().Be(0);
    }

    [Theory]
    [InlineData(-10, 0)]
    [InlineData(0, 0)]
    [InlineData(5, 5)]
    public void ShouldPreserveNonNegativeEffectiveAmount_WhenConstructingDamage(int rawAmount, int expected)
    {
        var damage = new Damage(rawAmount, DamageType.Physical);

        damage.EffectiveAmount.Should().Be(expected);
    }

    // ACC:T6.6
    // ACC:T6.9
    // ACC:T6.17
    // ACC:T6.18
    // ACC:T6.19
    [Theory]
    [InlineData(10, 0, 1.0, 1.0, false, 10)]    // normal
    [InlineData(10, 2, 1.0, 1.0, false, 12)]    // strength
    [InlineData(10, 0, 0.75, 1.0, false, 8)]    // weak
    [InlineData(10, 0, 1.0, 1.5, false, 15)]    // vulnerable
    [InlineData(10, 2, 0.75, 1.5, false, 14)]   // combined multipliers
    [InlineData(10, -20, 1.0, 1.0, false, 0)]   // negative strength clamp
    [InlineData(10, 10, -1.0, 2.0, false, 0)]   // invalid weak multiplier
    [InlineData(10, 10, 1.0, -2.0, false, 0)]   // invalid vulnerable multiplier
    [InlineData(-5, 3, 1.0, 1.0, false, 3)]     // negative base damage clamp
    [InlineData(10, 999, 0.5, 0.5, true, 10)]   // fixed damage exempt
    [InlineData(-5, 2, 1.5, 1.5, true, 0)]      // fixed damage + negative base
    public void ShouldCalculateStatusMultiplierDamageByTheoryMatrix_WhenInputVaries(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        bool isFixedDamage,
        int expected)
    {
        var result = CombatService.CalculateDamageWithStatusMultipliers(
            baseDamage: baseDamage,
            strength: strength,
            weakMultiplier: weakMultiplier,
            vulnerableMultiplier: vulnerableMultiplier,
            isFixedDamage: isFixedDamage);

        result.Should().Be(expected);
    }
}
