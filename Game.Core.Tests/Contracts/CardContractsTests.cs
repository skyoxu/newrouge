using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class CardContractsTests
{
    [Fact]
    public void CardInstance_marks_Ultimate_form_correctly()
    {
        var instance = new CardInstance(
            InstanceId: "card-inst-1",
            CardId: "warrior.strike",
            Form: CardForm.Ultimate,
            Route: null,
            UpgradeTier: 99,
            PermanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>()
        );

        instance.IsUltimate.Should().BeTrue();
        instance.Route.Should().BeNull();
    }

    [Fact]
    public void CardDefinition_and_modifier_have_strongly_typed_fields()
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
            InstanceId: "card-inst-2",
            CardId: definition.CardId,
            Form: CardForm.U1A,
            Route: UpgradeRoute.A,
            UpgradeTier: 1,
            PermanentCardInstanceModifiers: new List<CardInstanceModifier> { modifier }
        );

        definition.DefaultForm.Should().Be(CardForm.Base);
        instance.Route.Should().Be(UpgradeRoute.A);
        instance.PermanentCardInstanceModifiers.Should().HaveCount(1);
    }
}
