using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class CardInstanceTests
{
    // ACC:T8.4
    [Fact]
    public void ShouldPreserveModifierSnapshot_WhenMigratingFromU1ToUltimate()
    {
        var firstModifier = new CardInstanceModifier(
            ModifierId: "mod-001",
            ModifierType: "damage_plus",
            Value: 2,
            AppliedAt: new DateTimeOffset(2026, 3, 1, 8, 0, 0, TimeSpan.Zero));

        var sourceModifiers = new List<CardInstanceModifier> { firstModifier };
        var upgradedInstance = CreateUpgradedInstance(sourceModifiers);
        var expectedSnapshot = new List<CardInstanceModifier>(upgradedInstance.PermanentCardInstanceModifiers);

        var ultimateInstance = new CardInstance(
            instanceId: upgradedInstance.InstanceId,
            cardId: upgradedInstance.CardId,
            form: CardForm.Ultimate,
            route: null,
            upgradeTier: 2,
            permanentCardInstanceModifiers: upgradedInstance.PermanentCardInstanceModifiers);

        sourceModifiers.Add(new CardInstanceModifier(
            ModifierId: "mod-002",
            ModifierType: "cost_minus",
            Value: 1,
            AppliedAt: new DateTimeOffset(2026, 3, 1, 8, 1, 0, TimeSpan.Zero)));

        ultimateInstance.Form.Should().Be(CardForm.Ultimate);
        ultimateInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(expectedSnapshot);
    }

    // ACC:T8.4
    [Fact]
    public void ShouldKeepFormAndModifiersUnchanged_WhenUltimateMigrationIsRejected()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new(
                ModifierId: "mod-010",
                ModifierType: "shield_plus",
                Value: 4,
                AppliedAt: new DateTimeOffset(2026, 3, 2, 9, 0, 0, TimeSpan.Zero)),
        };

        var sourceInstance = CreateUpgradedInstance(sourceModifiers);
        var expectedForm = sourceInstance.Form;
        var expectedRoute = sourceInstance.Route;
        var expectedTier = sourceInstance.UpgradeTier;
        var expectedModifiers = new List<CardInstanceModifier>(sourceInstance.PermanentCardInstanceModifiers);

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: UpgradeRoute.A,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();

        sourceInstance.Form.Should().Be(expectedForm);
        sourceInstance.Route.Should().Be(expectedRoute);
        sourceInstance.UpgradeTier.Should().Be(expectedTier);
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(expectedModifiers);
    }

    private static CardInstance CreateUpgradedInstance(IReadOnlyList<CardInstanceModifier> modifiers)
    {
        return new CardInstance(
            instanceId: "instance-001",
            cardId: "card.warrior.slash",
            form: CardForm.U1A,
            route: UpgradeRoute.A,
            upgradeTier: 1,
            permanentCardInstanceModifiers: modifiers);
    }
}
