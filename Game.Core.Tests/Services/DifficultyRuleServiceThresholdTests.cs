using System;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class DifficultyRuleServiceThresholdTests
{
    // ACC:T27.5
    [Theory]
    [InlineData(1, "EnemyHealthScale:0.85", false)]
    [InlineData(3, "EnemyHealthScale:0.85", false)]
    [InlineData(4, "EnemyHealthScale:1.00", false)]
    [InlineData(7, "EnemyHealthScale:1.00", false)]
    [InlineData(8, "EnemyHealthScale:1.20", false)]
    [InlineData(9, "EnemyHealthScale:1.20", false)]
    [InlineData(10, "EnemyHealthScale:1.20", true)]
    [InlineData(12, "EnemyHealthScale:1.20", true)]
    [Trait("acceptance", "ACC:T27.5")]
    public void ShouldMapDifficultyBandsAndOverplayThresholdWhenResolvingByDifficultyId(
        int difficultyId,
        string expectedHealthModifier,
        bool expectOverplayTax)
    {
        var sut = new DifficultyRuleService();

        var modifiers = sut.ResolveModifiers(difficultyId);

        modifiers.Should().Contain(expectedHealthModifier);
        if (string.Equals(expectedHealthModifier, "EnemyHealthScale:1.20", StringComparison.Ordinal))
        {
            modifiers.Should().Contain("EnemyDamageScale:1.15");
        }

        if (expectOverplayTax)
        {
            modifiers.Should().Contain("OverplayTax:12");
        }
        else
        {
            modifiers.Should().NotContain("OverplayTax:12");
        }
    }

    // ACC:T27.5
    [Fact]
    [Trait("acceptance", "ACC:T27.5")]
    public void ShouldKeepOverplayTaxRuleConsistent_WhenResolvingFromDifficultyConfig()
    {
        var sut = new DifficultyRuleService();
        var belowThreshold = new DifficultyConfig(
            DifficultyId: 9,
            LabelKey: "difficulty.label.9",
            DescriptionKey: "difficulty.description.9",
            RulesetId: "ruleset.9");
        var threshold = new DifficultyConfig(
            DifficultyId: 10,
            LabelKey: "difficulty.label.10",
            DescriptionKey: "difficulty.description.10",
            RulesetId: "ruleset.10");

        var belowResult = sut.ResolveModifiers(belowThreshold);
        var thresholdResult = sut.ResolveModifiers(threshold);

        belowResult.Should().NotContain("OverplayTax:12");
        thresholdResult.Should().Contain("OverplayTax:12");
    }

    // ACC:T27.6
    [Theory]
    [InlineData(1)]
    [InlineData(5)]
    [InlineData(10)]
    [Trait("acceptance", "ACC:T27.6")]
    public void ShouldReturnDeterministicOutput_WhenResolvedRepeatedly(int difficultyId)
    {
        var sut = new DifficultyRuleService();

        var first = sut.ResolveModifiers(difficultyId);
        var second = sut.ResolveModifiers(difficultyId);

        second.Should().Equal(first);
    }

    [Fact]
    public void ShouldThrowArgumentNullException_WhenDifficultyConfigIsNull()
    {
        var sut = new DifficultyRuleService();

        Action act = () => sut.ResolveModifiers((DifficultyConfig)null!);

        act.Should().Throw<ArgumentNullException>();
    }
}
