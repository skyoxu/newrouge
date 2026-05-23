using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class RewardEntryModifierPipelineTests
{
    private readonly RewardEntryModifierPipeline _pipeline = new();

    [Fact]
    public void ShouldApplyAddRemoveAndMutateToNextContextSnapshot()
    {
        var entries = CreateEntries();
        var result = _pipeline.Apply(entries, new[]
        {
            Mutate("gold", amount: 77),
            AddRelic("relic.twilight_coin"),
            Remove("consumable"),
        });

        result.Rejected.Should().BeFalse();
        result.Applied.Should().BeTrue();
        result.Entries.Should().Contain(entry => entry.RewardType == "gold" && ReadInt(entry.Config, "amount") == 77);
        result.Entries.Should().Contain(entry => entry.RewardType == "relic" && ReadString(entry.Config, "relic_id") == "relic.twilight_coin");
        result.Entries.Should().NotContain(entry => entry.RewardType == "consumable");
    }

    [Fact]
    public void ShouldRejectInvalidMutateWithoutPartiallyMutatingSnapshot()
    {
        var entries = CreateEntries();
        var original = entries.Select(RewardEntryModifierPipeline.CloneEntry).ToArray();

        var result = _pipeline.Apply(entries, new[]
        {
            Mutate("gold", amount: -5),
        });

        result.Rejected.Should().BeTrue();
        result.RejectionReason.Should().Be("invalid-mutate:gold");
        result.Entries.Should().BeEquivalentTo(original, options => options.WithStrictOrdering());
    }

    [Fact]
    public void ShouldTreatSameInputsAsDeterministicReplay()
    {
        var entries = CreateEntries();
        var modifiers = new[]
        {
            Mutate("gold", amount: 91),
            AddRelic("relic.obsidian_mirror"),
        };

        var first = _pipeline.Apply(entries, modifiers);
        var second = _pipeline.Apply(entries, modifiers);

        second.Should().BeEquivalentTo(first);
    }

    [Fact]
    public void ShouldRejectUnsupportedAddAtRegistrationTime()
    {
        var canRegister = _pipeline.CanRegister(new RewardEntryModifier(
            Action: "add",
            TargetEntryId: string.Empty,
            RewardType: "unknown",
            Config: new Dictionary<string, object?>()));

        canRegister.Should().BeFalse();
    }

    [Fact]
    public void ShouldRejectInvalidAddDuringApplyWithoutMutatingBaseline()
    {
        var entries = CreateEntries();
        var original = entries.Select(RewardEntryModifierPipeline.CloneEntry).ToArray();

        var result = _pipeline.Apply(entries, new[]
        {
            new RewardEntryModifier(
                Action: "add",
                TargetEntryId: string.Empty,
                RewardType: "relic",
                Config: new Dictionary<string, object?>()),
        });

        result.Rejected.Should().BeTrue();
        result.RejectionReason.Should().Be("invalid-add:relic");
        result.Entries.Should().BeEquivalentTo(original, options => options.WithStrictOrdering());
    }

    private static RewardEntrySnapshot[] CreateEntries()
    {
        return new[]
        {
            new RewardEntrySnapshot("gold", "gold", new Dictionary<string, object?> { ["amount"] = 35 }),
            new RewardEntrySnapshot("consumable", "consumable", new Dictionary<string, object?> { ["item_id"] = "potion.minor_heal" }),
            new RewardEntrySnapshot("common_card_choice", "common_card_choice", new Dictionary<string, object?> { ["pool_id"] = "reward.common", ["pick"] = 3 }),
        };
    }

    private static RewardEntryModifier Mutate(string targetEntryId, int amount)
    {
        return new RewardEntryModifier(
            Action: "mutate",
            TargetEntryId: targetEntryId,
            RewardType: string.Empty,
            Config: new Dictionary<string, object?> { ["amount"] = amount });
    }

    private static RewardEntryModifier Remove(string targetEntryId)
    {
        return new RewardEntryModifier(
            Action: "remove",
            TargetEntryId: targetEntryId,
            RewardType: string.Empty,
            Config: new Dictionary<string, object?>());
    }

    private static RewardEntryModifier AddRelic(string relicId)
    {
        return new RewardEntryModifier(
            Action: "add",
            TargetEntryId: string.Empty,
            RewardType: "relic",
            Config: new Dictionary<string, object?> { ["relic_id"] = relicId });
    }

    private static int ReadInt(IReadOnlyDictionary<string, object?> config, string key)
    {
        return config.TryGetValue(key, out var raw) && raw is int value ? value : 0;
    }

    private static string ReadString(IReadOnlyDictionary<string, object?> config, string key)
    {
        return config.TryGetValue(key, out var raw) && raw is string value ? value : string.Empty;
    }
}
