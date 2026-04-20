using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Cards;
using Game.Core.Domain;
using Game.Core.Services;
using Game.Core.Utilities;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class ContractInstantiationCoverageTests
{
    [Fact]
    public void ShouldEventContractRecordsShouldBeInstantiableAndHaveCoreEventType_WhenExecuted()
    {
        var eventTypes = typeof(EventTypes).Assembly
            .GetTypes()
            .Where(t =>
                t.IsClass &&
                !t.IsAbstract &&
                t.Namespace is not null &&
                t.Namespace.StartsWith("Game.Core.Contracts.Events", StringComparison.Ordinal))
            .OrderBy(t => t.FullName)
            .ToArray();

        eventTypes.Should().NotBeEmpty();

        var unsupported = new List<string>();
        var created = 0;

        foreach (var type in eventTypes)
        {
            if (!TryCreate(type, out var instance, out var reason))
            {
                unsupported.Add($"{type.FullName}: {reason}");
                continue;
            }

            instance.Should().NotBeNull();
            TouchObjectMembers(instance!);
            created++;

            var eventTypeField = type.GetField("EventType");
            if (eventTypeField?.FieldType == typeof(string))
            {
                var value = eventTypeField.GetValue(null) as string;
                value.Should().NotBeNullOrWhiteSpace();
                value!.Should().StartWith("core.");
            }
        }

        unsupported.Should().BeEmpty("all event contracts should be constructible with deterministic sample values");
        created.Should().BeGreaterThan(0);
    }

    // ACC:T8.14
    // ACC:T8.16
    [Fact]
    public void ShouldNonEventContractRecordsShouldBeInstantiableWithSupportedConstructorShapes_WhenExecuted()
    {
        var contractTypes = typeof(EventTypes).Assembly
            .GetTypes()
            .Where(t =>
                t.IsClass &&
                !t.IsAbstract &&
                t.Namespace is not null &&
                t.Namespace.StartsWith("Game.Core.Contracts", StringComparison.Ordinal) &&
                !t.Namespace.StartsWith("Game.Core.Contracts.Events", StringComparison.Ordinal))
            .OrderBy(t => t.FullName)
            .ToArray();

        contractTypes.Should().NotBeEmpty();

        var unsupported = new List<string>();
        var created = 0;

        foreach (var type in contractTypes)
        {
            if (!TryCreate(type, out var instance, out var reason))
            {
                unsupported.Add($"{type.FullName}: {reason}");
                continue;
            }

            instance.Should().NotBeNull();
            TouchObjectMembers(instance!);
            created++;
        }

        unsupported.Should().BeEmpty("all contract records/classes should be constructible with deterministic sample values");
        created.Should().BeGreaterThan(0);

        var service = new CardService();
        var definition = new CardDefinition(
            CardId: "warrior.coverage",
            NameKey: "card.warrior.coverage",
            DefaultForm: CardForm.Base,
            IsCurse: false,
            IsUpgradeable: true,
            IsUltimateEligible: true);
        var createdInstance = service.CreateCardInstance(definition, "inst-coverage");
        var actualProperties = typeof(CardInstance).GetProperties()
            .Select(property => property.Name)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray();

        createdInstance.InstanceId.Should().Be("inst-coverage");
        createdInstance.CardId.Should().Be(definition.CardId);
        createdInstance.Form.Should().Be(CardForm.Base);
        createdInstance.Route.Should().BeNull();
        createdInstance.UpgradeTier.Should().Be(0);
        createdInstance.PermanentCardInstanceModifiers.Should().BeEmpty();
        actualProperties.Should().BeEquivalentTo(
            "CardId",
            "Form",
            "InstanceId",
            "IsUltimate",
            "PermanentCardInstanceModifiers",
            "Route",
            "UpgradeTier");

        Action illegalTierRoute = () => _ = new CardInstance(
            instanceId: "inst-coverage-illegal",
            cardId: definition.CardId,
            form: CardForm.U1A,
            route: null,
            upgradeTier: 1,
            permanentCardInstanceModifiers: Array.Empty<CardInstanceModifier>());
        illegalTierRoute.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void ShouldDomainRecordsAndEntitiesShouldBeConstructibleAndMutableMembersShouldBeTouched_WhenExecuted()
    {
        var result = new GameResult(
            FinalScore: 120,
            LevelReached: 3,
            PlayTimeSeconds: 1800,
            Achievements: new[] { "achv-1" },
            Statistics: new GameStatistics(10, 2, 4, 123.4, 0.35)
        );

        result.FinalScore.Should().Be(120);
        result.Statistics.EnemiesDefeated.Should().Be(4);
        TouchObjectMembers(result);
        TouchObjectMembers(result.Statistics);

        var domainTypes = typeof(GameResult).Assembly
            .GetTypes()
            .Where(t =>
                t.IsClass &&
                !t.IsAbstract &&
                t.Namespace is not null &&
                t.Namespace.StartsWith("Game.Core.Domain.Entities", StringComparison.Ordinal))
            .OrderBy(t => t.FullName)
            .ToArray();

        domainTypes.Should().NotBeEmpty();

        foreach (var type in domainTypes)
        {
            TryCreate(type, out var instance, out var reason).Should().BeTrue($"{type.FullName} should be constructible: {reason}");
            instance.Should().NotBeNull();
            TouchObjectMembers(instance!);
        }
    }

    [Fact]
    public void ShouldRandomHelperShouldGenerateValuesInExpectedRanges_WhenExecuted()
    {
        var number = RandomHelper.NextInt(1, 3);
        number.Should().BeGreaterThanOrEqualTo(1);
        number.Should().BeLessThan(3);

        var ratio = RandomHelper.NextDouble();
        ratio.Should().BeGreaterThanOrEqualTo(0d);
        ratio.Should().BeLessThan(1d);
    }

    private static bool TryCreate(Type type, out object? instance, out string reason, int depth = 0)
    {
        instance = null;
        reason = string.Empty;

        var constructors = type.GetConstructors()
            .OrderBy(c => c.GetParameters().Length)
            .ToArray();
        if (constructors.Length == 0)
        {
            reason = "no public constructor";
            return false;
        }

        object? seed = null;
        var anySucceeded = false;
        string? lastFailure = null;

        foreach (var ctor in constructors)
        {
            var parameters = ctor.GetParameters();
            var args = new object?[parameters.Length];
            var canInvoke = true;

            for (var i = 0; i < parameters.Length; i++)
            {
                var parameterType = parameters[i].ParameterType;
                if (parameterType == type)
                {
                    if (seed is null)
                    {
                        canInvoke = false;
                        lastFailure = "self-type constructor requires an already created seed instance";
                        break;
                    }

                    args[i] = seed;
                    continue;
                }

                if (!TryCreateValue(parameterType, out var value, depth + 1))
                {
                    canInvoke = false;
                    lastFailure = $"unsupported parameter type: {parameterType.FullName}";
                    break;
                }

                args[i] = value;
            }

            if (!canInvoke)
            {
                continue;
            }

            try
            {
                var created = ctor.Invoke(args);
                if (seed is null)
                {
                    seed = created;
                }

                instance = created;
                anySucceeded = true;
            }
            catch (Exception ex)
            {
                lastFailure = ex.GetType().Name + ": " + ex.Message;
            }
        }

        if (anySucceeded)
        {
            return true;
        }

        reason = lastFailure ?? "all constructors failed";
        return false;
    }

    private static bool TryCreateValue(Type type, out object? value, int depth)
    {
        if (depth > 4)
        {
            value = null;
            return false;
        }

        var t = Nullable.GetUnderlyingType(type) ?? type;

        if (t == typeof(string))
        {
            value = "sample";
            return true;
        }

        if (t == typeof(int))
        {
            value = 1;
            return true;
        }

        if (t == typeof(long))
        {
            value = 1L;
            return true;
        }

        if (t == typeof(double))
        {
            value = 1.0;
            return true;
        }

        if (t == typeof(bool))
        {
            value = true;
            return true;
        }

        if (t == typeof(DateTimeOffset))
        {
            value = DateTimeOffset.UnixEpoch;
            return true;
        }

        if (t == typeof(DateTime))
        {
            value = DateTime.UnixEpoch;
            return true;
        }

        if (t == typeof(JsonElement))
        {
            value = JsonDocument.Parse("{\"sample\":true}").RootElement.Clone();
            return true;
        }

        if (t.IsEnum)
        {
            value = Enum.GetValues(t).GetValue(0)!;
            return true;
        }

        if (t == typeof(string[]))
        {
            value = new[] { "a", "b" };
            return true;
        }

        if (t == typeof(IReadOnlyList<string>) ||
            t == typeof(IList<string>) ||
            t == typeof(List<string>) ||
            t == typeof(IEnumerable<string>))
        {
            value = new List<string> { "a", "b" };
            return true;
        }

        if (t.IsGenericType)
        {
            var g = t.GetGenericTypeDefinition();
            if (g == typeof(IReadOnlyList<>) || g == typeof(IList<>) || g == typeof(List<>) || g == typeof(IEnumerable<>))
            {
                var elementType = t.GetGenericArguments()[0];
                if (!TryCreateValue(elementType, out var elementValue, depth + 1))
                {
                    value = null;
                    return false;
                }

                var listType = typeof(List<>).MakeGenericType(elementType);
                var list = (System.Collections.IList)Activator.CreateInstance(listType)!;
                list.Add(elementValue);
                value = list;
                return true;
            }

            if (g == typeof(IReadOnlyDictionary<,>) || g == typeof(IDictionary<,>) || g == typeof(Dictionary<,>))
            {
                var keyType = t.GetGenericArguments()[0];
                var valueType = t.GetGenericArguments()[1];
                if (!TryCreateValue(keyType, out var keyValue, depth + 1) ||
                    !TryCreateValue(valueType, out var dictValue, depth + 1))
                {
                    value = null;
                    return false;
                }

                if (keyValue is null)
                {
                    value = null;
                    return false;
                }

                var dictType = typeof(Dictionary<,>).MakeGenericType(keyType, valueType);
                var dict = (System.Collections.IDictionary)Activator.CreateInstance(dictType)!;
                dict.Add(keyValue, dictValue);
                value = dict;
                return true;
            }
        }

        if (type != t && Nullable.GetUnderlyingType(type) is not null)
        {
            value = null;
            return true;
        }

        if (t.IsClass &&
            t.Namespace is not null &&
            (t.Namespace.StartsWith("Game.Core.Contracts", StringComparison.Ordinal) ||
             t.Namespace.StartsWith("Game.Core.Domain", StringComparison.Ordinal)))
        {
            if (TryCreate(t, out var nested, out _, depth + 1))
            {
                value = nested;
                return true;
            }
        }

        value = null;
        return false;
    }

    private static void TouchObjectMembers(object instance)
    {
        var type = instance.GetType();

        foreach (var field in type.GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static))
        {
            _ = field.GetValue(null);
        }

        foreach (var property in type.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance))
        {
            if (!property.CanRead)
                continue;

            _ = property.GetValue(instance);

            if (!property.CanWrite)
                continue;

            if (!TryCreateValue(property.PropertyType, out var value, depth: 1))
                continue;

            try
            {
                property.SetValue(instance, value);
            }
            catch
            {
                // Best-effort touch for coverage; skip non-settable runtime shapes.
            }
        }
    }
}
