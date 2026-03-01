using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Offers;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0004AcceptanceTests
{
    // ACC:T4.11
    [Fact]
    public void Should_Expose_OfferLockingContracts_As_ConcreteClassTypes_When_ValidatedByReflection()
    {
        var requiredContractTypes = new[]
        {
            typeof(OfferLockSnapshot),
            typeof(OfferProvenance),
            typeof(OfferItem),
        };

        requiredContractTypes.Should().OnlyContain(type => type.IsClass);
        requiredContractTypes.Should().OnlyContain(type => !type.IsAbstract);
        requiredContractTypes.Should().OnlyContain(type =>
            type.Namespace != null &&
            type.Namespace.StartsWith("Game.Core.Contracts.Offers", StringComparison.Ordinal));
    }

    // ACC:T4.12
    [Fact]
    public void Should_Reject_SchemaOnlyRepresentations_When_EnforcingConcreteOfferContractGate()
    {
        Action dictionaryShape = () => EnsureConcreteOfferContractType(typeof(Dictionary<string, object>), nameof(OfferLockSnapshot));
        Action scalarShape = () => EnsureConcreteOfferContractType(typeof(string), nameof(OfferProvenance));

        dictionaryShape.Should().Throw<InvalidOperationException>()
            .WithMessage("*schema-only*dictionary-only*");
        scalarShape.Should().Throw<InvalidOperationException>()
            .WithMessage("*schema-only*dictionary-only*");
    }

    [Fact]
    public void Should_Keep_RewardOfferEventTypeConstants_Stable_When_MappingContractRefs()
    {
        EventTypes.RewardOfferLocked.Should().Be("core.reward.offer.locked");
        EventTypes.RewardOfferPresented.Should().Be("core.reward.offer.presented");
        EventTypes.RewardOfferSelected.Should().Be("core.reward.offer.selected");
        EventTypes.RewardOfferSkipped.Should().Be("core.reward.offer.skipped");

        RewardOfferLockedEvent.EventType.Should().Be(EventTypes.RewardOfferLocked);
        RewardOfferPresentedEvent.EventType.Should().Be(EventTypes.RewardOfferPresented);
        RewardOfferSelectedEvent.EventType.Should().Be(EventTypes.RewardOfferSelected);
        RewardOfferSkippedEvent.EventType.Should().Be(EventTypes.RewardOfferSkipped);
    }

    private static void EnsureConcreteOfferContractType(Type candidateType, string contractName)
    {
        var inContractsNamespace = candidateType.Namespace is not null &&
            candidateType.Namespace.StartsWith("Game.Core.Contracts", StringComparison.Ordinal);

        if (!candidateType.IsClass || candidateType.IsAbstract || !inContractsNamespace)
        {
            throw new InvalidOperationException(
                $"{contractName} must be a concrete C# contract type, not a schema-only/dictionary-only representation.");
        }
    }
}
