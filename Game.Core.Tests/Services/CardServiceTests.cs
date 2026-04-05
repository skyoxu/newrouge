using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CardServiceTests
{
    private const string NotFoundErrorCode = "card.definition.not_found";
    private const string NotFoundErrorType = "card_definition_not_found";

    private static readonly string[] LookupMethodCandidates =
    {
        "GetDefinitionByCardId",
        "GetCardDefinition",
        "LookupDefinition",
        "FindDefinition",
    };

    private static readonly string[] CreateMethodCandidates =
    {
        "CreateInstance",
        "CreateCardInstance",
    };

    private static readonly string[] UpgradeMethodCandidates =
    {
        "UpgradeToU1",
        "ApplyU1Upgrade",
    };

    private static readonly string[] UltimateMethodCandidates =
    {
        "PromoteToUltimate",
        "AdvanceToUltimate",
    };

    // ADR-0033
    [Fact]
    public void ShouldExposeCardServiceType_WhenInspectingCoreAssembly()
    {
        var serviceType = ResolveCardServiceType();

        serviceType.Should().NotBeNull();
    }

    // ACC:T8.1
    // ACC:T8.2
    // ADR-0033
    [Fact]
    public void ShouldReturnUniqueDefinition_WhenCardIdLookupHits()
    {
        var definitions = CreateDefinitions();
        var lookup = LookupByCardId(definitions, "card.warrior.block");

        lookup.definition.Should().NotBeNull();
        lookup.definition.Should().BeSameAs(definitions.Single(definition => definition.CardId == "card.warrior.block"));
        lookup.errorCode.Should().BeNull();
        lookup.errorType.Should().BeNull();
    }

    // ACC:T8.10
    // ADR-0033
    [Fact]
    public void ShouldReturnDeterministicFailureOutput_WhenCardIdLookupMisses()
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

    // ACC:T8.33
    // ADR-0033
    [Fact]
    public void ShouldRejectInvalidCreateInputsDeterministically_WhenCreatingCardInstance()
    {
        var service = new CardService();
        var definition = CreateDefinition("card.warrior.mage");
        var invalidDefinition = definition with { CardId = string.Empty };

        var missingInstanceIdFirst = CaptureFailureSignature(() => _ = service.CreateCardInstance(definition, ""));
        var missingInstanceIdSecond = CaptureFailureSignature(() => _ = service.CreateCardInstance(definition, ""));
        var missingCardId = CaptureFailureSignature(() => _ = service.CreateCardInstance(invalidDefinition, "instance-0033"));

        missingInstanceIdFirst.Should().Be(missingInstanceIdSecond);
        missingInstanceIdFirst.Should().Contain("ArgumentException");
        missingCardId.Should().Contain("ArgumentException");
    }

    // ACC:T8.3
    // ACC:T8.4
    // ADR-0033
    [Fact]
    public void ShouldInitializeInstanceIdentityAndModifierContainer_WhenCreatingCardInstance()
    {
        var definition = CreateDefinition("card.warrior.slash");
        var instance = CreateBaseInstance(definition, "instance-001");

        instance.InstanceId.Should().Be("instance-001");
        instance.CardId.Should().Be(definition.CardId);
        instance.Form.Should().Be(CardForm.Base);
        instance.Route.Should().BeNull();
        instance.UpgradeTier.Should().Be(0);
        instance.PermanentCardInstanceModifiers.Should().NotBeNull();
        instance.PermanentCardInstanceModifiers.Should().BeEmpty();
    }

    // ACC:T8.5
    // ADR-0033
    [Fact]
    public void ShouldKeepDefinitionIdentityUnchanged_WhenMutatingInstanceShape()
    {
        var definition = CreateDefinition("card.warrior.slash");
        var baseInstance = CreateBaseInstance(definition, "instance-002");
        var upgradedInstance = UpgradeToU1(baseInstance, UpgradeRoute.A);

        upgradedInstance.Form.Should().Be(CardForm.U1A);
        upgradedInstance.CardId.Should().Be(definition.CardId);
        definition.DefaultForm.Should().Be(CardForm.Base);
        definition.CardId.Should().Be("card.warrior.slash");
    }

    // ACC:T8.6
    // ADR-0033
    [Fact]
    public void ShouldPreservePermanentModifiers_WhenPromotingToUltimate()
    {
        var modifiers = new List<CardInstanceModifier>
        {
            new("mod-001", "damage_plus", 2, new DateTimeOffset(2026, 3, 1, 8, 0, 0, TimeSpan.Zero)),
            new("mod-002", "cost_minus", 1, new DateTimeOffset(2026, 3, 1, 8, 1, 0, TimeSpan.Zero)),
        };

        var upgradedInstance = new CardInstance(
            instanceId: "instance-003",
            cardId: "card.warrior.slash",
            form: CardForm.U1B,
            route: UpgradeRoute.B,
            upgradeTier: 1,
            permanentCardInstanceModifiers: modifiers);

        var ultimateInstance = PromoteToUltimate(upgradedInstance);

        ultimateInstance.Form.Should().Be(CardForm.Ultimate);
        ultimateInstance.Route.Should().BeNull();
        ultimateInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(modifiers);
    }

    // ACC:T8.7
    // ADR-0033
    [Fact]
    public void ShouldKeepStateUnchanged_WhenUltimateTransitionIsRejected()
    {
        var modifiers = new List<CardInstanceModifier>
        {
            new("mod-003", "shield_plus", 4, new DateTimeOffset(2026, 3, 2, 9, 0, 0, TimeSpan.Zero)),
        };

        var sourceInstance = new CardInstance(
            instanceId: "instance-004",
            cardId: "card.warrior.guard",
            form: CardForm.U1B,
            route: UpgradeRoute.B,
            upgradeTier: 1,
            permanentCardInstanceModifiers: modifiers);

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: UpgradeRoute.B,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.U1B);
        sourceInstance.Route.Should().Be(UpgradeRoute.B);
        sourceInstance.UpgradeTier.Should().Be(1);
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(modifiers);
    }

    // ACC:T8.29
    // ADR-0033
    [Theory]
    [InlineData(UpgradeRoute.A, CardForm.U1A)]
    [InlineData(UpgradeRoute.B, CardForm.U1B)]
    public void ShouldAcceptRouteAAndRouteB_WhenApplyingU1Upgrade(UpgradeRoute route, CardForm expectedForm)
    {
        var baseInstance = CreateBaseInstance(CreateDefinition("card.warrior.block"), "instance-005");

        var upgradedInstance = UpgradeToU1(baseInstance, route);

        upgradedInstance.Form.Should().Be(expectedForm);
        upgradedInstance.Route.Should().Be(route);
        upgradedInstance.UpgradeTier.Should().Be(1);
    }

    // ACC:T8.13
    // ADR-0033
    [Fact]
    public void ShouldRejectUpgradeToU1WhenSourceIsNotBaseState_WhenApplyingU1Upgrade()
    {
        var sourceInstance = UpgradeToU1(
            CreateBaseInstance(CreateDefinition("card.warrior.block"), "instance-005b"),
            UpgradeRoute.A);
        var beforeSignature = $"{sourceInstance.Form}|{sourceInstance.Route}|{sourceInstance.UpgradeTier}|{sourceInstance.PermanentCardInstanceModifiers.Count}";

        Action act = () => _ = UpgradeToU1(sourceInstance, UpgradeRoute.B);

        act.Should().Throw<ArgumentException>();
        var afterSignature = $"{sourceInstance.Form}|{sourceInstance.Route}|{sourceInstance.UpgradeTier}|{sourceInstance.PermanentCardInstanceModifiers.Count}";
        afterSignature.Should().Be(beforeSignature);
    }

    // ACC:T8.9
    // ADR-0033
    [Fact]
    public void ShouldRejectUnsupportedRouteValue_WhenApplyingU1Upgrade()
    {
        var sourceInstance = CreateBaseInstance(CreateDefinition("card.warrior.block"), "instance-006");
        var invalidRoute = (UpgradeRoute)999;

        Action act = () => _ = UpgradeToU1(sourceInstance, invalidRoute);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.Base);
        sourceInstance.UpgradeTier.Should().Be(0);
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEmpty();
    }

    // ACC:T8.10
    // ADR-0033
    [Fact]
    public void ShouldRejectInvalidTierRouteCombination_WhenApplyingU1Upgrade()
    {
        var sourceInstance = UpgradeToU1(
            CreateBaseInstance(CreateDefinition("card.warrior.slash"), "instance-007"),
            UpgradeRoute.A);

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: UpgradeRoute.A,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.U1A);
        sourceInstance.Route.Should().Be(UpgradeRoute.A);
        sourceInstance.UpgradeTier.Should().Be(1);
    }

    // ACC:T8.8
    // ACC:T8.12
    // ADR-0033
    [Fact]
    public void ShouldPromoteToUltimateForm_WhenUltimateTransitionSucceeds()
    {
        var upgradedInstance = UpgradeToU1(
            CreateBaseInstance(CreateDefinition("card.warrior.strike"), "instance-008"),
            UpgradeRoute.B);

        var ultimateInstance = PromoteToUltimate(upgradedInstance);

        ultimateInstance.Form.Should().Be(CardForm.Ultimate);
        ultimateInstance.IsUltimate.Should().BeTrue();
        ultimateInstance.Route.Should().BeNull();
        ultimateInstance.UpgradeTier.Should().Be(2);
    }

    // ACC:T8.13
    // ADR-0033
    [Fact]
    public void ShouldResolveSubsequentBehaviorFromUltimateState_WhenCardIsUltimate()
    {
        var service = new CardService();
        var upgradedInstance = UpgradeToU1(
            CreateBaseInstance(CreateDefinition("card.warrior.strike"), "instance-009"),
            UpgradeRoute.A);

        var ultimateInstance = PromoteToUltimate(upgradedInstance);
        var effectKey = service.ResolveEffectKey(ultimateInstance);

        effectKey.Should().Be("card.effect.ultimate");
    }

    // ACC:T8.25
    // ACC:T8.34
    // ADR-0033
    [Fact]
    public void ShouldRejectUltimatePromotionWhenSourceIsNotU1State_WhenPromotingToUltimate()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new("mod-precondition", "focus_plus", 1, new DateTimeOffset(2026, 3, 2, 8, 0, 0, TimeSpan.Zero)),
        };
        var sourceInstance = CreateBaseInstance(CreateDefinition("card.warrior.mind"), "instance-009b", sourceModifiers);
        var beforeSignature = $"{sourceInstance.Form}|{sourceInstance.Route}|{sourceInstance.UpgradeTier}|{sourceInstance.PermanentCardInstanceModifiers.Count}";

        Action act = () => _ = PromoteToUltimate(sourceInstance);

        act.Should().Throw<ArgumentException>();
        var afterSignature = $"{sourceInstance.Form}|{sourceInstance.Route}|{sourceInstance.UpgradeTier}|{sourceInstance.PermanentCardInstanceModifiers.Count}";
        afterSignature.Should().Be(beforeSignature);
    }

    // ACC:T8.17
    // ADR-0033
    [Fact]
    public void ShouldKeepCardIdStableAcrossTransitions_WhenApplyingUpgradePath()
    {
        var definition = CreateDefinition("card.warrior.guard");
        var baseInstance = CreateBaseInstance(definition, "instance-010");
        var u1Instance = UpgradeToU1(baseInstance, UpgradeRoute.A);
        var ultimateInstance = PromoteToUltimate(u1Instance);

        baseInstance.CardId.Should().Be(definition.CardId);
        u1Instance.CardId.Should().Be(definition.CardId);
        ultimateInstance.CardId.Should().Be(definition.CardId);
    }

    // ACC:T8.18
    // ADR-0033
    [Fact]
    public void ShouldProduceDistinctU1Outcomes_WhenRouteAOrBIsSelected()
    {
        var service = new CardService();
        var baseInstance = CreateBaseInstance(CreateDefinition("card.warrior.slash"), "instance-011");

        var routeAInstance = UpgradeToU1(baseInstance, UpgradeRoute.A);
        var routeBInstance = UpgradeToU1(baseInstance, UpgradeRoute.B);

        routeAInstance.Form.Should().Be(CardForm.U1A);
        routeBInstance.Form.Should().Be(CardForm.U1B);
        service.ResolveEffectKey(routeAInstance).Should().NotBe(service.ResolveEffectKey(routeBInstance));
    }

    // ACC:T8.19
    // ADR-0033
    [Fact]
    public void ShouldKeepLookupStableAcrossRepeatedReads_WhenCardIdIsSame()
    {
        var definitions = CreateDefinitions();

        var first = LookupByCardId(definitions, "card.warrior.slash");
        var second = LookupByCardId(definitions, "card.warrior.slash");

        first.definition.Should().BeSameAs(second.definition);
        first.errorCode.Should().BeNull();
        second.errorCode.Should().BeNull();
    }

    // ACC:T8.20
    // ADR-0033
    [Theory]
    [InlineData(CardForm.Base, null, "card.effect.base")]
    [InlineData(CardForm.U1A, UpgradeRoute.A, "card.effect.u1.route_a")]
    [InlineData(CardForm.U1B, UpgradeRoute.B, "card.effect.u1.route_b")]
    [InlineData(CardForm.Ultimate, null, "card.effect.ultimate")]
    public void ShouldMapAllowedTransitionsDeterministically_WhenComputingEffectKey(CardForm form, UpgradeRoute? route, string expectedKey)
    {
        var service = new CardService();
        var tier = form == CardForm.Base ? 0 : (form == CardForm.Ultimate ? 2 : 1);
        var instance = new CardInstance(
            instanceId: "instance-012",
            cardId: "card.warrior.guard",
            form: form,
            route: route,
            upgradeTier: tier,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        service.ResolveEffectKey(instance).Should().Be(expectedKey);
    }

    // ACC:T8.21
    // ADR-0033
    [Fact]
    public void ShouldKeepModifiersAndFormUnchanged_WhenU1UpgradeIsRejected()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new("mod-004", "damage_plus", 1, new DateTimeOffset(2026, 3, 3, 8, 0, 0, TimeSpan.Zero)),
        };

        var sourceInstance = CreateBaseInstance(CreateDefinition("card.warrior.block"), "instance-013", sourceModifiers);
        var invalidRoute = (UpgradeRoute)777;

        Action act = () => _ = UpgradeToU1(sourceInstance, invalidRoute);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.Base);
        sourceInstance.UpgradeTier.Should().Be(0);
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(sourceModifiers);
    }

    // ACC:T8.22
    // ADR-0033
    [Fact]
    public void ShouldReturnStableFailureCode_WhenRouteIsInvalid()
    {
        var sourceInstance = CreateBaseInstance(CreateDefinition("card.warrior.block"), "instance-014");
        var invalidRoute = (UpgradeRoute)123;

        var first = CaptureFailureSignature(() => _ = UpgradeToU1(sourceInstance, invalidRoute));
        var second = CaptureFailureSignature(() => _ = UpgradeToU1(sourceInstance, invalidRoute));

        first.Should().Be(second);
        first.Should().Contain("ArgumentException");
    }

    // ACC:T8.23
    // ADR-0033
    [Fact]
    public void ShouldReturnStableFailureType_WhenLookupMissInputRepeats()
    {
        var definitions = CreateDefinitions();

        var first = LookupByCardId(definitions, "card.warrior.void");
        var second = LookupByCardId(definitions, "card.warrior.void");

        first.errorType.Should().Be(NotFoundErrorType);
        second.errorType.Should().Be(first.errorType);
    }

    // ACC:T8.24
    // ADR-0033
    [Fact]
    public void ShouldKeepTierFormAndModifiersUnchanged_WhenTransitionFails()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new("mod-005", "bleed_plus", 2, new DateTimeOffset(2026, 3, 3, 9, 0, 0, TimeSpan.Zero)),
        };

        var sourceInstance = new CardInstance(
            instanceId: "instance-015",
            cardId: "card.warrior.guard",
            form: CardForm.U1A,
            route: UpgradeRoute.A,
            upgradeTier: 1,
            permanentCardInstanceModifiers: sourceModifiers);

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: UpgradeRoute.A,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();
        sourceInstance.Form.Should().Be(CardForm.U1A);
        sourceInstance.UpgradeTier.Should().Be(1);
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(sourceModifiers);
    }

    // ACC:T8.25
    // ADR-0033
    [Fact]
    public void ShouldTreatUltimateAsFinalForm_WhenFurtherPromotionIsRequested()
    {
        var service = new CardService();
        var ultimateInstance = PromoteToUltimate(
            UpgradeToU1(
                CreateBaseInstance(CreateDefinition("card.warrior.slash"), "instance-016"),
                UpgradeRoute.B));

        Action act = () => _ = service.PromoteToUltimate(ultimateInstance);

        act.Should().Throw<InvalidOperationException>();
    }

    // ACC:T8.27
    // ADR-0033
    [Fact]
    public void ShouldReturnSameUltimateEffectKey_WhenEvaluatingTwice()
    {
        var service = new CardService();
        var ultimateInstance = PromoteToUltimate(
            UpgradeToU1(
                CreateBaseInstance(CreateDefinition("card.warrior.guard"), "instance-017"),
                UpgradeRoute.A));

        var first = service.ResolveEffectKey(ultimateInstance);
        var second = service.ResolveEffectKey(ultimateInstance);

        first.Should().Be(second);
        first.Should().Be("card.effect.ultimate");
    }

    // ACC:T8.28
    // ADR-0033
    [Fact]
    public void ShouldCreateDeterministicLookupFailureTuple_WhenCardIdNotFound()
    {
        var definitions = CreateDefinitions();
        var miss = LookupByCardId(definitions, "card.warrior.unknown");
        var tuple = $"{miss.errorType}|{miss.errorCode}";

        tuple.Should().Be($"{NotFoundErrorType}|{NotFoundErrorCode}");
    }

    // ACC:T8.29
    // ADR-0033
    [Fact]
    public void ShouldRejectMissingRouteForU1_WhenApplyingTierRouteInvariant()
    {
        var sourceInstance = CreateBaseInstance(CreateDefinition("card.warrior.guard"), "instance-red-001");

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
    }

    // ACC:T8.30
    // ADR-0033
    [Fact]
    public void ShouldRetainModifierSnapshot_WhenTransitionAttemptsAreRejected()
    {
        var sourceModifiers = new List<CardInstanceModifier>
        {
            new("mod-006", "armor_plus", 3, new DateTimeOffset(2026, 3, 4, 10, 0, 0, TimeSpan.Zero)),
            new("mod-007", "thorns_plus", 1, new DateTimeOffset(2026, 3, 4, 10, 1, 0, TimeSpan.Zero)),
        };

        var sourceInstance = new CardInstance(
            instanceId: "instance-018",
            cardId: "card.warrior.guard",
            form: CardForm.U1B,
            route: UpgradeRoute.B,
            upgradeTier: 1,
            permanentCardInstanceModifiers: sourceModifiers);

        var expectedSnapshot = sourceInstance.PermanentCardInstanceModifiers.ToArray();

        Action act = () => _ = new CardInstance(
            instanceId: sourceInstance.InstanceId,
            cardId: sourceInstance.CardId,
            form: CardForm.Ultimate,
            route: UpgradeRoute.B,
            upgradeTier: 2,
            permanentCardInstanceModifiers: sourceInstance.PermanentCardInstanceModifiers);

        act.Should().Throw<ArgumentException>();
        sourceInstance.PermanentCardInstanceModifiers.Should().BeEquivalentTo(expectedSnapshot);
    }

    // ACC:T8.31
    // ADR-0033
    [Fact]
    public void ShouldExposeMethodCandidates_WhenInspectingCardServiceType()
    {
        var serviceType = ResolveCardServiceType();
        serviceType.Should().NotBeNull();

        var methodNames = serviceType!.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Select(method => method.Name)
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        methodNames.Should().Contain(name => LookupMethodCandidates.Contains(name, StringComparer.Ordinal));
        methodNames.Should().Contain(name => CreateMethodCandidates.Contains(name, StringComparer.Ordinal));
        methodNames.Should().Contain(name => UpgradeMethodCandidates.Contains(name, StringComparer.Ordinal));
        methodNames.Should().Contain(name => UltimateMethodCandidates.Contains(name, StringComparer.Ordinal));
    }

    // ACC:T8.32
    // ADR-0033
    [Fact]
    public void ShouldProvideDeterministicFailureOutputForLookupMiss_WhenInvokedTwice()
    {
        var definitions = CreateDefinitions();

        var first = LookupByCardId(definitions, "card.warrior.nope");
        var second = LookupByCardId(definitions, "card.warrior.nope");

        var firstSignature = $"{first.errorType}|{first.errorCode}";
        var secondSignature = $"{second.errorType}|{second.errorCode}";

        firstSignature.Should().Be(secondSignature);
        firstSignature.Should().Be($"{NotFoundErrorType}|{NotFoundErrorCode}");
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

    private static CardInstance CreateBaseInstance(
        CardDefinition definition,
        string instanceId,
        IReadOnlyList<CardInstanceModifier>? modifiers = null)
    {
        return new CardService().CreateCardInstance(
            definition,
            instanceId,
            modifiers ?? Array.Empty<CardInstanceModifier>());
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

    private static string CaptureFailureSignature(Action action)
    {
        try
        {
            action();
            return "none";
        }
        catch (Exception exception)
        {
            return $"{exception.GetType().Name}|{exception.Message}";
        }
    }

    private static Type? ResolveCardServiceType()
    {
        var coreAssembly = typeof(CardDefinition).Assembly;
        return coreAssembly.GetType("Game.Core.Services.CardService", throwOnError: false, ignoreCase: false);
    }
}
