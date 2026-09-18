using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class MvgRewardMutationProbeTests
{
    [Theory]
    [InlineData(0, false)]
    [InlineData(-1, true)]
    public void GoldBoundaryShouldPreserveOriginalWhenRejected(int amount, bool rejected)
    {
        var pipeline = new RewardEntryModifierPipeline();
        var original = new RewardEntrySnapshot("gold", "gold",
            new Dictionary<string, object?> { ["amount"] = 35 });
        var modifier = new RewardEntryModifier("mutate", "gold", "gold",
            new Dictionary<string, object?> { ["amount"] = amount });
        var result = pipeline.Apply(new[] { original }, new[] { modifier });
        result.Rejected.Should().Be(rejected);
        result.Entries[0].Config["amount"].Should().Be(rejected ? 35 : amount);
        original.Config["amount"].Should().Be(35);
    }

    [Fact]
    public void UnknownRewardTypeShouldBeRejectedBeforeRegistration()
    {
        new RewardEntryModifierPipeline().CanRegister(new RewardEntryModifier(
            "add", "", "unknown", new Dictionary<string, object?> { ["amount"] = 1 }))
            .Should().BeFalse();
    }
}
