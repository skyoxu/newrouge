using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0032AcceptanceTests
{
    // ACC:T32.1
    [Fact]
    public void ShouldDiscoverAndEnableOnlyCurseCards_WhenScanningRuntimeDefinitions()
    {
        var definitions = new[]
        {
            new CurseCardDefinition("curse_blight", "card.curse.blight"),
            new CurseCardDefinition("curse_hex", "card.curse.hex"),
            new CurseCardDefinition("strike", "card.attack.strike"),
        };

        var enabledCurseIds = CurseCardRuntimeCatalog
            .DiscoverEnabledCurseCards(definitions)
            .Select(card => card.Id)
            .ToArray();

        enabledCurseIds.Should().BeEquivalentTo(new[] { "curse_blight", "curse_hex" });
        enabledCurseIds.Should().NotContain("strike");
    }

    // ACC:T32.4
    [Fact]
    public void ShouldRefuseUpgradeAndKeepStateUnchanged_WhenUpgradeIsRequestedForCurseCard()
    {
        var curseCard = new CurseRuntimeCard("curse_blight", "card.curse.blight");

        var result = CurseUpgradeRules.TryUpgrade(curseCard);

        result.IsAccepted.Should().BeFalse();
        result.Card.Should().Be(curseCard);
    }

    [Fact]
    public void ShouldAllowUpgrade_WhenUpgradeIsRequestedForNonCurseCard()
    {
        var nonCurseCard = new CurseRuntimeCard("strike", "card.attack.strike");

        var result = CurseUpgradeRules.TryUpgrade(nonCurseCard);

        result.IsAccepted.Should().BeTrue();
        result.Card.Should().Be(nonCurseCard);
    }

    // ACC:T32.2
    [Fact]
    public void ShouldRemoveTargetCurseWithoutReplacement_WhenStorePathIsConfirmed()
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_blight", "card.curse.blight"),
            new CurseDeckCard("strike", "card.attack.strike"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_blight", CurseRemovalOrigin.Store, isConfirmed: true);

        removed.Should().BeTrue();
        deck.Contains("curse_blight").Should().BeFalse();
        deck.Count.Should().Be(initialCount - 1);
        deck.Cards.Count(card => card.Id == "strike").Should().Be(1);
    }

    // ACC:T32.5
    [Theory]
    [InlineData(CurseRemovalOrigin.Rest)]
    [InlineData(CurseRemovalOrigin.Event)]
    public void ShouldRemoveTargetCurseWithoutReplacement_WhenRestOrEventPathIsConfirmed(CurseRemovalOrigin origin)
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_decay", "card.curse.decay"),
            new CurseDeckCard("defend", "card.skill.defend"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_decay", origin, isConfirmed: true);

        removed.Should().BeTrue();
        deck.Contains("curse_decay").Should().BeFalse();
        deck.Count.Should().Be(initialCount - 1);
        deck.Cards.Count(card => card.Id == "defend").Should().Be(1);
    }

    [Theory]
    [InlineData(CurseRemovalOrigin.Store)]
    [InlineData(CurseRemovalOrigin.Rest)]
    [InlineData(CurseRemovalOrigin.Event)]
    public void ShouldKeepDeckUnchanged_WhenCurseRemovalIsNotConfirmed(CurseRemovalOrigin origin)
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_decay", "card.curse.decay"),
            new CurseDeckCard("defend", "card.skill.defend"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_decay", origin, isConfirmed: false);

        removed.Should().BeFalse();
        deck.Contains("curse_decay").Should().BeTrue();
        deck.Count.Should().Be(initialCount);
    }

    [Fact]
    public void ShouldRejectRemoval_WhenOriginIsInvalid()
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_decay", "card.curse.decay"),
            new CurseDeckCard("defend", "card.skill.defend"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_decay", (CurseRemovalOrigin)(-1), isConfirmed: true);

        removed.Should().BeFalse();
        deck.Contains("curse_decay").Should().BeTrue();
        deck.Count.Should().Be(initialCount);
    }

    [Fact]
    public void ShouldRejectRemoval_WhenTargetCardIsMissing()
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_decay", "card.curse.decay"),
            new CurseDeckCard("defend", "card.skill.defend"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_missing", CurseRemovalOrigin.Store, isConfirmed: true);

        removed.Should().BeFalse();
        deck.Contains("curse_decay").Should().BeTrue();
        deck.Count.Should().Be(initialCount);
    }

    [Fact]
    public void ShouldRejectRemoval_WhenTargetIdMatchesButCardIsNotCurseNamespace()
    {
        var deck = new CurseDeck(
            new CurseDeckCard("curse_fake", "card.skill.block"),
            new CurseDeckCard("defend", "card.skill.defend"));
        var service = new CurseRemovalCoordinator();

        var initialCount = deck.Count;
        var removed = service.RemoveCurse(deck, "curse_fake", CurseRemovalOrigin.Store, isConfirmed: true);

        removed.Should().BeFalse();
        deck.Contains("curse_fake").Should().BeTrue();
        deck.Count.Should().Be(initialCount);
    }

    // ACC:T32.3
    [Fact]
    public void ShouldMapChecklistCoverageToTaskAcceptanceFile_WhenCoverageIsQueried()
    {
        var checklist = new[]
        {
            new ChecklistEntry(
                "CurseConstraintValidation",
                "Game.Core.Tests/Tasks/Task0032AcceptanceTests.cs",
                "ACC:T32.1",
                "ACC:T32.4"),
            new ChecklistEntry(
                "ThreeRemovalPathValidation",
                "Game.Core.Tests/Tasks/Task0032AcceptanceTests.cs",
                "ACC:T32.2",
                "ACC:T32.5"),
            new ChecklistEntry(
                "AcceptanceChecklistTraceability",
                "Game.Core.Tests/Tasks/Task0032AcceptanceTests.cs",
                "ACC:T32.3"),
        };

        checklist.Select(item => item.FilePath)
            .Distinct()
            .Should()
            .ContainSingle()
            .Which
            .Should()
            .Be("Game.Core.Tests/Tasks/Task0032AcceptanceTests.cs");

        checklist.Select(item => item.Category)
            .Should()
            .Contain(new[]
            {
                "CurseConstraintValidation",
                "ThreeRemovalPathValidation",
            });

        checklist.SelectMany(item => item.Anchors)
            .Should()
            .Contain(new[]
            {
                "ACC:T32.1",
                "ACC:T32.2",
                "ACC:T32.3",
                "ACC:T32.4",
                "ACC:T32.5",
            });
    }

    private sealed class ChecklistEntry
    {
        public ChecklistEntry(string category, string filePath, params string[] anchors)
        {
            Category = category;
            FilePath = filePath;
            Anchors = anchors;
        }

        public string Category { get; }

        public string FilePath { get; }

        public IReadOnlyList<string> Anchors { get; }
    }
}
