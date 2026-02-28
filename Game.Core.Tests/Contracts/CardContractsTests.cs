using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class CardContractsTests
{
    [Fact]
    public void ShouldCardInstanceMarksUltimateFormCorrectly_WhenExecuted()
    {
        var instance = new CardInstance(
            instanceId: "card-inst-1",
            cardId: "warrior.strike",
            form: CardForm.Ultimate,
            route: null,
            upgradeTier: 99,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>()
        );

        instance.IsUltimate.Should().BeTrue();
        instance.Route.Should().BeNull();
    }

    [Fact]
    public void ShouldCardDefinitionAndModifierHaveStronglyTypedFields_WhenExecuted()
    {
        var modifier = new CardInstanceModifier(
            ModifierId: "m1",
            ModifierType: "damage_plus",
            Value: 3,
            AppliedAt: DateTimeOffset.UtcNow
        );

        var definition = new CardDefinition(
            CardId: "warrior.slash",
            NameKey: "card.warrior.slash",
            DefaultForm: CardForm.Base,
            IsCurse: false,
            IsUpgradeable: true,
            IsUltimateEligible: true
        );

        var instance = new CardInstance(
            instanceId: "card-inst-2",
            cardId: definition.CardId,
            form: CardForm.U1A,
            route: UpgradeRoute.A,
            upgradeTier: 1,
            permanentCardInstanceModifiers: new List<CardInstanceModifier> { modifier }
        );

        definition.DefaultForm.Should().Be(CardForm.Base);
        instance.Route.Should().Be(UpgradeRoute.A);
        instance.PermanentCardInstanceModifiers.Should().HaveCount(1);
    }

    [Fact]
    public void ShouldRejectRoute_WhenUpgradeTierIsTwo()
    {
        Action act = () => _ = new CardInstance(
            instanceId: "card-inst-3",
            cardId: "warrior.block",
            form: CardForm.Ultimate,
            route: UpgradeRoute.A,
            upgradeTier: 2,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*tier*2*route*null*");
    }

    [Fact]
    public void ShouldRejectInvalidRoute_WhenUpgradeTierIsNotTwo()
    {
        var invalidRoute = (UpgradeRoute)999;

        Action act = () => _ = new CardInstance(
            instanceId: "card-inst-4",
            cardId: "warrior.block",
            form: CardForm.U1B,
            route: invalidRoute,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*route*A*B*");
    }

    [Fact]
    public void ShouldAllowNullRoute_WhenUpgradeTierIsNotTwo()
    {
        var instance = new CardInstance(
            instanceId: "card-inst-5",
            cardId: "warrior.block",
            form: CardForm.Base,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        instance.UpgradeTier.Should().Be(1);
        instance.Route.Should().BeNull();
    }

    [Fact]
    public void ShouldNotReferenceGodotAssemblies_WhenInspectingCardContractsAssembly()
    {
        var refs = typeof(CardDefinition).Assembly.GetReferencedAssemblies().Select(a => a.Name).ToArray();
        refs.Should().NotContain(name =>
            !string.IsNullOrWhiteSpace(name) && name!.StartsWith("Godot", StringComparison.OrdinalIgnoreCase));
    }
}
