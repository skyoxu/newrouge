using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class WarriorDeckManifestValidationTests
{
    private static readonly string[] ExpectedM1WarriorCardIds =
    {
        "card.warrior.cleave",
        "card.warrior.guard",
        "card.warrior.rage_surge",
        "card.warrior.bloodrush",
        "card.warrior.taunt",
        "card.warrior.shield_wall",
        "card.warrior.overpower",
        "card.warrior.battlecry",
        "card.warrior.crush",
        "card.warrior.relentless",
    };

    // ACC:T24.5
    [Fact]
    public void ShouldFailWithDiffDetails_WhenManifestMismatchesM1ContentList()
    {
        var actualCardIds = ExpectedM1WarriorCardIds
            .Where(cardId => !string.Equals(cardId, "card.warrior.crush", StringComparison.Ordinal))
            .Append("card.warrior.placeholder")
            .ToArray();

        var result = ValidateManifestAgainstM1(ExpectedM1WarriorCardIds, actualCardIds);

        result.IsValid.Should().BeFalse("a mismatch against the M1 content list must fail validation");
        result.DiffLines.Should().Contain("missing: card.warrior.crush");
        result.DiffLines.Should().Contain("extra: card.warrior.placeholder");
        result.Summary.Should().ContainEquivalentOf("missing");
        result.Summary.Should().ContainEquivalentOf("extra");
    }

    [Fact]
    public void ShouldNotPassSilently_WhenManifestIsMissingRequiredCards()
    {
        var actualCardIds = ExpectedM1WarriorCardIds
            .Where(cardId => !string.Equals(cardId, "card.warrior.relentless", StringComparison.Ordinal))
            .ToArray();

        var result = ValidateManifestAgainstM1(ExpectedM1WarriorCardIds, actualCardIds);

        result.IsValid.Should().BeFalse("missing cards must never be treated as pass");
        result.DiffLines.Should().Contain("missing: card.warrior.relentless");
        result.DiffLines.Should().NotBeEmpty("validator must emit concrete diff lines instead of silent pass");
    }

    [Fact]
    public void ShouldReturnValidResult_WhenManifestMatchesM1Exactly()
    {
        var actualCardIds = ExpectedM1WarriorCardIds.ToArray();

        var result = ValidateManifestAgainstM1(ExpectedM1WarriorCardIds, actualCardIds);

        result.IsValid.Should().BeTrue();
        result.DiffLines.Should().BeEmpty();
        result.Summary.Should().Be("manifest matches m1 content list");
    }

    private static WarriorDeckManifestValidationResult ValidateManifestAgainstM1(
        IReadOnlyCollection<string> expectedCardIds,
        IReadOnlyCollection<string> actualCardIds)
    {
        WarriorStartingDeckService.Definitions
            .Select(card => card.CardId)
            .Should()
            .BeEquivalentTo(expectedCardIds, options => options.WithoutStrictOrdering());

        return WarriorStartingDeckService.ValidateManifestAgainstM1(actualCardIds);
    }
}
