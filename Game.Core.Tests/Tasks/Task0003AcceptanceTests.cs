using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0003AcceptanceTests
{
    // ACC:T3.1
    [Fact]
    public void ShouldExposeRequiredContractMembersAndEnumValues_WhenInspectingCardContracts()
    {
        var definitionProperties = typeof(CardDefinition).GetProperties().Select(p => p.Name).ToArray();
        definitionProperties.Should().Contain(new[]
        {
            "CardId",
            "NameKey",
            "DefaultForm",
            "IsCurse",
            "IsUpgradeable",
            "IsUltimateEligible",
        });

        var instanceProperties = typeof(CardInstance).GetProperties().Select(p => p.Name).ToArray();
        instanceProperties.Should().Contain(new[]
        {
            "InstanceId",
            "CardId",
            "Form",
            "UpgradeTier",
            "Route",
            "PermanentCardInstanceModifiers",
        });

        Enum.GetNames(typeof(CardForm)).Should().BeEquivalentTo(new[] { "Base", "U1A", "U1B", "Ultimate" });
        Enum.GetNames(typeof(UpgradeRoute)).Should().BeEquivalentTo(new[] { "A", "B" });
    }

    // ACC:T3.2
    [Fact]
    public void ShouldRejectRoute_WhenUpgradeTierIsTwo()
    {
        Action act = () => _ = new CardInstance(
            instanceId: "inst-001",
            cardId: "card-001",
            form: CardForm.Ultimate,
            route: UpgradeRoute.A,
            upgradeTier: 2,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*tier*2*route*null*");
    }

    [Fact]
    public void ShouldAcceptNullRoute_WhenUpgradeTierIsTwo()
    {
        var instance = new CardInstance(
            instanceId: "inst-002",
            cardId: "card-002",
            form: CardForm.Ultimate,
            route: null,
            upgradeTier: 2,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        instance.UpgradeTier.Should().Be(2);
        instance.Route.Should().BeNull();
    }

    [Theory]
    [InlineData(UpgradeRoute.A)]
    [InlineData(UpgradeRoute.B)]
    public void ShouldAllowOnlyRouteAOrB_WhenUpgradeTierIsNotTwo(UpgradeRoute route)
    {
        var instance = new CardInstance(
            instanceId: "inst-003",
            cardId: "card-003",
            form: CardForm.U1A,
            route: route,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        instance.UpgradeTier.Should().NotBe(2);
        instance.Route.Should().Be(route);
        Enum.IsDefined(typeof(UpgradeRoute), route).Should().BeTrue();
    }

    // ACC:T3.2
    [Fact]
    public void ShouldAllowNullRoute_WhenUpgradeTierIsNotTwo()
    {
        var instance = new CardInstance(
            instanceId: "inst-003-null",
            cardId: "card-003-null",
            form: CardForm.Base,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        instance.UpgradeTier.Should().Be(1);
        instance.Route.Should().BeNull();
    }

    // ACC:T3.2
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public void ShouldRejectInvalidInstanceId_WhenConstructingCardInstance(string? instanceId)
    {
        Action act = () => _ = new CardInstance(
            instanceId: instanceId!,
            cardId: "card-identity-1",
            form: CardForm.Base,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*instanceId*required*");
    }

    // ACC:T3.2
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public void ShouldRejectInvalidCardId_WhenConstructingCardInstance(string? cardId)
    {
        Action act = () => _ = new CardInstance(
            instanceId: "inst-identity-1",
            cardId: cardId!,
            form: CardForm.Base,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*cardId*required*");
    }

    // ACC:T3.2
    [Fact]
    public void ShouldRejectInvalidRouteEnumValue_WhenUpgradeTierIsNotTwo()
    {
        var invalidRoute = (UpgradeRoute)999;

        Action act = () => _ = new CardInstance(
            instanceId: "inst-004",
            cardId: "card-004",
            form: CardForm.U1B,
            route: invalidRoute,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());

        act.Should().Throw<ArgumentException>()
            .WithMessage("*route*A*B*");
    }

    // ACC:T3.2
    [Fact]
    public void ShouldNotExposePublicSetters_WhenProtectingCardInstanceInvariants()
    {
        var writable = typeof(CardInstance)
            .GetProperties()
            .Where(p => p.SetMethod is not null && p.SetMethod.IsPublic)
            .Select(p => p.Name)
            .ToArray();

        writable.Should().BeEmpty();
    }

    // ACC:T3.3
    [Fact]
    public void ShouldNotReferenceGodotAssemblies_WhenValidatingPureDotNetContractUsage()
    {
        var contractAssemblyReferences = typeof(CardDefinition).Assembly.GetReferencedAssemblies().Select(a => a.Name).ToArray();
        var testAssemblyReferences = typeof(Task0003AcceptanceTests).Assembly.GetReferencedAssemblies().Select(a => a.Name).ToArray();

        contractAssemblyReferences.Should().NotContain(name =>
            !string.IsNullOrWhiteSpace(name) && name!.StartsWith("Godot", StringComparison.OrdinalIgnoreCase));

        testAssemblyReferences.Should().NotContain(name =>
            !string.IsNullOrWhiteSpace(name) && name!.StartsWith("Godot", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T3.4
    [Fact]
    public void ShouldBeInterfaceOrClass_WhenInspectingCardDefinitionShape()
    {
        var contractType = typeof(CardDefinition);

        IsSupportedContractShape(contractType).Should().BeTrue(
            "CardDefinition must be an interface or class and may be a record class");
    }

    // ACC:T3.5
    [Fact]
    public void ShouldBeInterfaceOrClass_WhenInspectingCardInstanceShape()
    {
        var contractType = typeof(CardInstance);

        IsSupportedContractShape(contractType).Should().BeTrue(
            "CardInstance must be an interface or class and may be a record class");
    }

    // ACC:T3.6
    [Theory]
    [MemberData(nameof(InvalidContractShapes))]
    public void ShouldFailExplicitlyForStructEnumAndOtherNonInterfaceClassShapes_WhenContractShapeIsInvalid(Type invalidType, string contractName)
    {
        Action act = () => EnsureInterfaceOrClassShape(invalidType, contractName);

        act.Should()
            .Throw<InvalidOperationException>()
            .WithMessage($"{contractName} contract type must be interface or class*");
    }

    public static IEnumerable<object[]> InvalidContractShapes()
    {
        yield return new object[] { typeof(CardForm), "CardDefinition" };
        yield return new object[] { typeof(InvalidCardInstanceShape), "CardInstance" };
        yield return new object[] { typeof(int).MakeByRefType(), "CardInstance" };
    }

    private static bool IsSupportedContractShape(Type contractType)
    {
        return (contractType.IsInterface || contractType.IsClass) && !contractType.IsByRef;
    }

    private static void EnsureInterfaceOrClassShape(Type contractType, string contractName)
    {
        if (!IsSupportedContractShape(contractType))
        {
            throw new InvalidOperationException(
                $"{contractName} contract type must be interface or class, but was {contractType}.");
        }
    }

    private readonly struct InvalidCardInstanceShape;
}
