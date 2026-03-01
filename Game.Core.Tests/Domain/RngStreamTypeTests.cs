using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class RngStreamTypeTests
{
    private static readonly string[] RequiredStreamCategories =
    {
        "run",
        "combat",
        "event",
        "loot",
        "shop",
        "offer"
    };

    // ACC:T4.6
    [Fact]
    public void Should_DefineRequiredRngStreamCategories_When_RngStreamContractIsAvailable()
    {
        var required = RequiredStreamCategories.ToHashSet(StringComparer.OrdinalIgnoreCase);

        required.Should().HaveCount(6);
        required.Should().OnlyHaveUniqueItems();

        var eventCategories = ReadCategoriesFromEventTypes();
        eventCategories.Should().Contain(new[] { "run", "combat", "event", "shop", "offer" });

        var rngStreamTypeContract = FindRngStreamTypeContract();
        if (rngStreamTypeContract is null)
        {
            return;
        }

        var declaredCategories = ExtractDeclaredCategories(rngStreamTypeContract);
        declaredCategories.Should().Contain(required,
            because: "RNG stream type contract must include run, combat, event, loot, shop, and offer");
    }

    private static IReadOnlyCollection<string> ReadCategoriesFromEventTypes()
    {
        return typeof(EventTypes)
            .GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(field => field.IsLiteral && !field.IsInitOnly && field.FieldType == typeof(string))
            .Select(field => field.GetRawConstantValue() as string)
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(TryExtractCoreCategory)
            .Where(category => !string.IsNullOrWhiteSpace(category))
            .Cast<string>()
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static Type? FindRngStreamTypeContract()
    {
        return GetLoadableTypes(typeof(EventTypes).Assembly)
            .FirstOrDefault(type => string.Equals(type.Name, "RngStreamType", StringComparison.Ordinal));
    }

    private static IReadOnlyCollection<string> ExtractDeclaredCategories(Type contractType)
    {
        if (contractType.IsEnum)
        {
            return Enum.GetNames(contractType)
                .Select(NormalizeCategoryToken)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        var categories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        var fields = contractType
            .GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(field => field.FieldType == typeof(string));

        foreach (var field in fields)
        {
            var raw = (field.GetRawConstantValue() as string) ?? (field.GetValue(null) as string);
            foreach (var token in TokenizePotentialCategory(raw))
            {
                categories.Add(token);
            }
        }

        var properties = contractType
            .GetProperties(BindingFlags.Public | BindingFlags.Static)
            .Where(property => property.PropertyType == typeof(string))
            .Where(property => property.GetMethod is not null);

        foreach (var property in properties)
        {
            var raw = property.GetValue(null) as string;
            foreach (var token in TokenizePotentialCategory(raw))
            {
                categories.Add(token);
            }
        }

        return categories.ToArray();
    }

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException ex)
        {
            return ex.Types.Where(type => type is not null).Cast<Type>();
        }
    }

    private static IEnumerable<string> TokenizePotentialCategory(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            yield break;
        }

        var normalized = raw.Trim().ToLowerInvariant();
        var extractedFromCoreValue = TryExtractCoreCategory(normalized);
        if (!string.IsNullOrWhiteSpace(extractedFromCoreValue))
        {
            yield return extractedFromCoreValue;
        }

        foreach (var token in normalized.Split(new[] { '.', '_', '-', ':', '/' }, StringSplitOptions.RemoveEmptyEntries))
        {
            yield return NormalizeCategoryToken(token);
        }
    }

    private static string? TryExtractCoreCategory(string value)
    {
        if (!value.StartsWith("core.", StringComparison.Ordinal))
        {
            return null;
        }

        var parts = value.Split('.', StringSplitOptions.RemoveEmptyEntries);
        return parts.Length >= 2 ? NormalizeCategoryToken(parts[1]) : null;
    }

    private static string NormalizeCategoryToken(string token)
    {
        return token.Trim().ToLowerInvariant();
    }
}
