using System;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Xunit;

namespace Game.Core.Tests.Domain;

public class GameEventContractsTests
{
    // ACC:T7.4
    [Fact]
    public void ShouldExposeCardPlayedAndCombatStartedDtos_WhenScanningContractsNamespace()
    {
        var contractsAssembly = typeof(EventTypes).Assembly;

        var dtoTypes = contractsAssembly
            .GetTypes()
            .Where(type =>
                type.IsClass &&
                !type.IsAbstract &&
                (type.Name == "CardPlayed" || type.Name == "CombatStarted"))
            .OrderBy(type => type.Name)
            .ToArray();

        dtoTypes.Should().HaveCount(
            2,
            "Task T7 requires CardPlayed and CombatStarted DTO contracts in Game.Core/Contracts.");

        dtoTypes
            .Select(type => type.Namespace)
            .Should()
            .OnlyContain(
                ns => ns != null && ns.StartsWith("Game.Core.Contracts", StringComparison.Ordinal),
                "event DTO contracts must live under Game.Core/Contracts.");
    }

    [Fact]
    public void ShouldUseDistinctEventTypeDiscriminators_WhenComparingEventDtos()
    {
        var contractsAssembly = typeof(EventTypes).Assembly;
        var cardPlayedType = ResolveDtoType(contractsAssembly, "CardPlayed");
        var combatStartedType = ResolveDtoType(contractsAssembly, "CombatStarted");

        cardPlayedType.Should().NotBeNull("CardPlayed DTO should exist in contracts.");
        combatStartedType.Should().NotBeNull("CombatStarted DTO should exist in contracts.");

        var cardPlayedEventType = ReadEventTypeDiscriminator(cardPlayedType!);
        var combatStartedEventType = ReadEventTypeDiscriminator(combatStartedType!);

        cardPlayedEventType.Should().NotBeNullOrWhiteSpace(
            "CardPlayed DTO must expose an event-type discriminator field or constant.");
        combatStartedEventType.Should().NotBeNullOrWhiteSpace(
            "CombatStarted DTO must expose an event-type discriminator field or constant.");

        cardPlayedEventType.Should().StartWith("core.");
        combatStartedEventType.Should().StartWith("core.");
        cardPlayedEventType.Should().NotBe(
            combatStartedEventType,
            "different event DTOs must have distinct discriminators for event-bus routing.");
    }

    private static Type? ResolveDtoType(Assembly contractsAssembly, string dtoName)
    {
        return contractsAssembly
            .GetTypes()
            .FirstOrDefault(type =>
                type.IsClass &&
                !type.IsAbstract &&
                type.Name == dtoName &&
                type.Namespace is not null &&
                type.Namespace.StartsWith("Game.Core.Contracts", StringComparison.Ordinal));
    }

    private static string? ReadEventTypeDiscriminator(Type dtoType)
    {
        var field = dtoType.GetField(
            "EventType",
            BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy);

        if (field?.FieldType == typeof(string))
        {
            return field.GetValue(null) as string;
        }

        var property = dtoType.GetProperty(
            "EventType",
            BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy);

        if (property?.PropertyType == typeof(string))
        {
            return property.GetValue(null) as string;
        }

        return null;
    }
}
