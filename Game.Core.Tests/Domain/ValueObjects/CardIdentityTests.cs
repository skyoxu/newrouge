using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Domain.ValueObjects;

public sealed class CardIdentityTests
{
    private const string NotFoundErrorCode = "card.definition.not_found";
    private const string NotFoundErrorType = "card_definition_not_found";

    // ADR-0033
    [Fact]
    public void ShouldMatchDefinition_WhenCardIdLookupHits()
    {
        var definitions = CreateDefinitions();

        var lookup = LookupByCardId(definitions, "card.warrior.block");

        lookup.definition.Should().NotBeNull();
        lookup.definition!.CardId.Should().Be("card.warrior.block");
        lookup.errorCode.Should().BeNull();
        lookup.errorType.Should().BeNull();
    }

    // ADR-0033
    [Fact]
    public void ShouldReturnNotFoundMetadata_WhenCardIdLookupMisses()
    {
        var definitions = CreateDefinitions();

        var first = LookupByCardId(definitions, "card.warrior.missing");
        var second = LookupByCardId(definitions, "card.warrior.missing");

        first.definition.Should().BeNull();
        second.definition.Should().BeNull();
        first.errorCode.Should().Be(NotFoundErrorCode);
        second.errorCode.Should().Be(first.errorCode);
        first.errorType.Should().Be(NotFoundErrorType);
        second.errorType.Should().Be(first.errorType);
    }

    // ADR-0033
    [Theory]
    [InlineData(UpgradeRoute.A, CardForm.U1A)]
    [InlineData(UpgradeRoute.B, CardForm.U1B)]
    public void ShouldSelectU1Form_WhenRouteUpgradeIsApplied(UpgradeRoute route, CardForm expectedForm)
    {
        var baseInstance = CreateBaseInstance("instance-001", "card.warrior.slash");

        var upgradedInstance = UpgradeToU1(baseInstance, route);

        upgradedInstance.Form.Should().Be(expectedForm);
        upgradedInstance.Route.Should().Be(route);
        upgradedInstance.UpgradeTier.Should().Be(1);
        upgradedInstance.CardId.Should().Be(baseInstance.CardId);
    }

    // ACC:T8.6
    // ADR-0033
    [Fact]
    public void ShouldPreserveModifierSnapshot_WhenPromotingToUltimate()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new("mod-001", "damage_plus", 2, new DateTimeOffset(2026, 3, 1, 8, 0, 0, TimeSpan.Zero)),
        };

        var upgradedInstance = new CardInstance(
            instanceId: "instance-002",
            cardId: "card.warrior.slash",
            form: CardForm.U1A,
            route: UpgradeRoute.A,
            upgradeTier: 1,
            permanentCardInstanceModifiers: sourceModifiers);

        var expectedSnapshot = new List<CardInstanceModifier>(upgradedInstance.PermanentCardInstanceModifiers);
        var ultimateInstance = PromoteToUltimate(upgradedInstance);

        sourceModifiers.Add(new CardInstanceModifier(
            ModifierId: "mod-002",
            ModifierType: "cost_minus",
            Value: 1,
            AppliedAt: new DateTimeOffset(2026, 3, 1, 8, 1, 0, TimeSpan.Zero)));

        ultimateInstance.Form.Should().Be(CardForm.Ultimate);
        ultimateInstance.Route.Should().BeNull();
        ultimateInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(expectedSnapshot);
    }

    // ADR-0033
    [Fact]
    public void ShouldRejectMissingRoute_WhenU1TierIsRequested()
    {
        var sourceInstance = CreateBaseInstance("instance-red-001", "card.warrior.guard");

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.U1A,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.Base);
        sourceInstance.Route.Should().BeNull();
        sourceInstance.UpgradeTier.Should().Be(0);
    }

    private static CardDefinition[] CreateDefinitions()
    {
        return new[]
        {
            CreateDefinition("card.warrior.slash"),
            CreateDefinition("card.warrior.block"),
            CreateDefinition("card.warrior.guard"),
        };
    }

    private static CardDefinition CreateDefinition(string cardId)
    {
        return new CardDefinition(
            CardId: cardId,
            NameKey: $"name.{cardId}",
            DefaultForm: CardForm.Base,
            IsCurse: false,
            IsUpgradeable: true,
            IsUltimateEligible: true);
    }

    private static CardInstance CreateBaseInstance(string instanceId, string cardId)
    {
        return new CardService().CreateCardInstance(CreateDefinition(cardId), instanceId);
    }

    private static CardInstance UpgradeToU1(CardInstance sourceInstance, UpgradeRoute route)
    {
        return new CardService().UpgradeToU1(sourceInstance, route);
    }

    private static CardInstance PromoteToUltimate(CardInstance sourceInstance)
    {
        return new CardService().PromoteToUltimate(sourceInstance);
    }

    private static (CardDefinition? definition, string? errorCode, string? errorType) LookupByCardId(
        IReadOnlyCollection<CardDefinition> definitions,
        string cardId)
    {
        return new CardService().GetCardDefinition(definitions, cardId);
    }
}
