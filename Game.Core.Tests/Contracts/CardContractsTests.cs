using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Services;
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
            upgradeTier: 2,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>()
        );

        instance.IsUltimate.Should().BeTrue();
        instance.Route.Should().BeNull();
    }

    // ACC:T8.11
    [Fact]
    public void ShouldCardDefinitionAndModifierHaveStronglyTypedFields_WhenExecuted()
    {
        var fixedAppliedAt = new DateTimeOffset(2026, 3, 5, 10, 0, 0, TimeSpan.Zero);
        var modifier = new CardInstanceModifier(
            ModifierId: "m1",
            ModifierType: "damage_plus",
            Value: 3,
            AppliedAt: fixedAppliedAt
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
        definition.CardId.Should().NotBeNullOrWhiteSpace();
        definition.NameKey.Should().NotBeNullOrWhiteSpace();
        modifier.AppliedAt.Should().Be(fixedAppliedAt);
        instance.Route.Should().Be(UpgradeRoute.A);
        instance.CardId.Should().Be(definition.CardId);
        instance.InstanceId.Should().Be("card-inst-2");
        instance.PermanentCardInstanceModifiers.Should().HaveCount(1);
    }

    // ACC:T8.14
    // ACC:T8.16
    [Fact]
    public void ShouldMapCardDefinitionToInstanceFieldsExactly_WhenCreatingCardInstance()
    {
        var service = new CardService();
        var definition = new CardDefinition(
            CardId: "warrior.guard",
            NameKey: "card.warrior.guard",
            DefaultForm: CardForm.Base,
            IsCurse: false,
            IsUpgradeable: true,
            IsUltimateEligible: true);

        var modifiers = new List<CardInstanceModifier>
        {
            new("mod-map-1", "armor_plus", 2, new DateTimeOffset(2026, 3, 6, 9, 0, 0, TimeSpan.Zero)),
        };

        var instance = service.CreateCardInstance(definition, "card-inst-map", modifiers);
        var instancePropertyNames = typeof(CardInstance).GetProperties()
            .Select(p => p.Name)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray();

        instance.InstanceId.Should().Be("card-inst-map");
        instance.CardId.Should().Be(definition.CardId);
        instance.Form.Should().Be(CardForm.Base);
        instance.Route.Should().BeNull();
        instance.UpgradeTier.Should().Be(0);
        instance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(modifiers);
        instance.IsUltimate.Should().BeFalse();
        instancePropertyNames.Should().BeEquivalentTo(
            "CardId",
            "Form",
            "InstanceId",
            "IsUltimate",
            "PermanentCardInstanceModifiers",
            "Route",
            "UpgradeTier");
    }

    // ACC:T8.14
    // ACC:T8.15
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

    // ACC:T8.15
    [Fact]
    public void ShouldRejectMissingRequiredInputsAndIllegalTierRouteCombination_WhenConstructingCardContracts()
    {
        var service = new CardService();
        var definition = new CardDefinition(
            CardId: "warrior.block",
            NameKey: "card.warrior.block",
            DefaultForm: CardForm.Base,
            IsCurse: false,
            IsUpgradeable: true,
            IsUltimateEligible: true);

        var emptyCardIdDefinition = definition with { CardId = string.Empty };

        Action missingInstanceId = () => _ = service.CreateCardInstance(definition, "");
        Action missingCardId = () => _ = service.CreateCardInstance(emptyCardIdDefinition, "card-inst-err");
        Action missingRouteForU1 = () => _ = new CardInstance(
            instanceId: "card-inst-err-2",
            cardId: definition.CardId,
            form: CardForm.U1A,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        missingInstanceId.Should().Throw<ArgumentException>();
        missingCardId.Should().Throw<ArgumentException>();
        missingRouteForU1.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void ShouldRejectOutOfRangeUpgradeTier_WhenConstructingCardInstance()
    {
        Action act = () => _ = new CardInstance(
            instanceId: "card-inst-tier",
            cardId: "warrior.block",
            form: CardForm.Base,
            route: null,
            upgradeTier: 99,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*upgradeTier*between 0 and 2*");
    }

    [Fact]
    public void ShouldNotReferenceGodotAssemblies_WhenInspectingCardContractsAssembly()
    {
        var refs = typeof(CardDefinition).Assembly.GetReferencedAssemblies().Select(a => a.Name).ToArray();
        refs.Should().NotContain(name =>
            !string.IsNullOrWhiteSpace(name) && name!.StartsWith("Godot", StringComparison.OrdinalIgnoreCase));
    }
}
