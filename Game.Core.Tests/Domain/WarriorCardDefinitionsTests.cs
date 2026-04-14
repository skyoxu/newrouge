using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class WarriorCardDefinitionsTests
{
    private static readonly IReadOnlyList<WarriorCardManifestEntry> ExpectedM1WarriorCards =
        new List<WarriorCardManifestEntry>
        {
            new("card.warrior.cleave", "common", "attack", true, new[] { "rage", "aoe" }, "damage"),
            new("card.warrior.guard", "common", "skill", true, new[] { "rage", "defense" }, "defense"),
            new("card.warrior.rage_surge", "common", "skill", true, new[] { "rage", "engine" }, "setup"),
            new("card.warrior.bloodrush", "common", "attack", true, new[] { "rage", "risk", "finisher" }, "burst"),
            new("card.warrior.taunt", "common", "skill", true, new[] { "control", "defense" }, "control"),
            new("card.warrior.shield_wall", "uncommon", "skill", true, new[] { "defense", "engine" }, "sustain"),
            new("card.warrior.overpower", "uncommon", "attack", true, new[] { "rage", "finisher" }, "finisher"),
            new("card.warrior.battlecry", "common", "skill", true, new[] { "engine", "draw" }, "engine"),
            new("card.warrior.crush", "common", "attack", true, new[] { "rage", "single_target" }, "damage"),
            new("card.warrior.relentless", "rare", "power", true, new[] { "engine", "rage" }, "archetype"),
        };

    // ACC:T24.4
    [Fact]
    public void ShouldMatchM1CardCountAndIds_WhenReadingWarriorCardDefinitions()
    {
        var actualCards = ReadWarriorCardManifest();

        actualCards.Should().HaveCount(10);
        actualCards
            .Select(card => card.CardId)
            .Should()
            .BeEquivalentTo(
                ExpectedM1WarriorCards.Select(card => card.CardId),
                options => options.WithoutStrictOrdering());
    }

    // ACC:T24.4
    [Theory]
    [MemberData(nameof(ExpectedM1WarriorCardsForTheory))]
    public void ShouldMatchM1CoreAttributes_WhenReadingWarriorCardDefinitions(
        string cardId,
        string rarity,
        string cardType,
        bool isStarterDeck,
        string intent,
        string[] tags)
    {
        var actualCardsById = ReadWarriorCardManifest()
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);

        actualCardsById.Should().ContainKey(cardId, "every M1 warrior card id must be present");
        var actualCard = actualCardsById[cardId];

        actualCard.Rarity.Should().Be(rarity);
        actualCard.CardType.Should().Be(cardType);
        actualCard.IsStarterDeck.Should().Be(isStarterDeck);
        actualCard.Intent.Should().Be(intent);
        actualCard.Tags.Should().BeEquivalentTo(tags, options => options.WithoutStrictOrdering());
    }

    // ACC:T24.4
    [Fact]
    public void ShouldExposeReadableTagsAndIntent_WhenReadingWarriorCardDefinitions()
    {
        var actualCards = ReadWarriorCardManifest();

        actualCards.Should().OnlyContain(card =>
            card.Tags.Count > 0 &&
            card.Tags.All(tag => !string.IsNullOrWhiteSpace(tag)));

        actualCards.Should().OnlyContain(card => !string.IsNullOrWhiteSpace(card.Intent));
    }

    [Fact]
    public void ShouldReportMissingAndExtraIds_WhenManifestDiffIsComputed()
    {
        var expectedIds = ExpectedM1WarriorCards.Select(card => card.CardId).ToArray();
        var simulatedActualIds = expectedIds
            .Where(cardId => !string.Equals(cardId, "card.warrior.crush", StringComparison.Ordinal))
            .Append("card.warrior.placeholder")
            .ToArray();

        var diff = BuildIdDiff(expectedIds, simulatedActualIds);

        diff.Should().Contain("missing: card.warrior.crush");
        diff.Should().Contain("extra: card.warrior.placeholder");
    }

    public static IEnumerable<object[]> ExpectedM1WarriorCardsForTheory()
    {
        foreach (var card in ExpectedM1WarriorCards)
        {
            yield return new object[]
            {
                card.CardId,
                card.Rarity,
                card.CardType,
                card.IsStarterDeck,
                card.Intent,
                card.Tags.ToArray(),
            };
        }
    }

    private static IReadOnlyList<WarriorCardManifestEntry> ReadWarriorCardManifest()
    {
        var providerType = ResolveWarriorCardProviderType();

        providerType.Should().NotBeNull(
            "Task 24 requires an explicit Warrior card definition provider for the M1 starter deck manifest.");

        var definitions = ReadDefinitionsCollection(providerType!);

        definitions.Should().NotBeNull("the warrior card definition provider must return an enumerable manifest");
        var entries = definitions!.Cast<object>().Select(ReadManifestEntry).ToArray();

        entries.Should().NotBeEmpty("the warrior card definition manifest must contain cards");
        return entries;
    }

    private static Type? ResolveWarriorCardProviderType()
    {
        var exactTypeNames = new[]
        {
            "Game.Core.Domain.WarriorCardDefinitions",
            "Game.Core.Domain.Cards.WarriorCardDefinitions",
            "Game.Core.Content.WarriorCardDefinitions",
            "Game.Core.Services.WarriorCardDefinitions",
            "Game.Core.Services.WarriorStartingDeckService",
        };

        var typeNameCandidates = new[]
        {
            "WarriorCardDefinitions",
            "WarriorCardCatalog",
            "WarriorCardManifest",
            "WarriorStartingDeckService",
        };

        foreach (var assembly in GetGameCoreAssemblies())
        {
            foreach (var exactTypeName in exactTypeNames)
            {
                var exactType = assembly.GetType(exactTypeName, throwOnError: false, ignoreCase: false);
                if (exactType is not null)
                {
                    return exactType;
                }
            }

            foreach (var candidateType in GetLoadableTypes(assembly))
            {
                if (typeNameCandidates.Any(name => string.Equals(candidateType.Name, name, StringComparison.Ordinal)))
                {
                    return candidateType;
                }
            }
        }

        return null;
    }

    private static IEnumerable<Assembly> GetGameCoreAssemblies()
    {
        var loadedAssemblies = AppDomain.CurrentDomain.GetAssemblies().ToList();

        if (!loadedAssemblies.Any(a => string.Equals(a.GetName().Name, "Game.Core", StringComparison.OrdinalIgnoreCase)))
        {
            loadedAssemblies.Add(typeof(CardDefinition).Assembly);
        }

        return loadedAssemblies.Where(a =>
            a.GetName().Name is not null &&
            a.GetName().Name!.StartsWith("Game.Core", StringComparison.OrdinalIgnoreCase));
    }

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException exception)
        {
            return exception.Types.Where(type => type is not null).Cast<Type>();
        }
    }

    private static IEnumerable? ReadDefinitionsCollection(Type providerType)
    {
        var staticValue = ReadFromStaticMembers(providerType);
        if (TryAsEnumerable(staticValue, out var staticEnumerable))
        {
            return staticEnumerable;
        }

        if (providerType.IsAbstract)
        {
            return null;
        }

        var ctor = providerType.GetConstructor(Type.EmptyTypes);
        if (ctor is null)
        {
            return null;
        }

        var instance = ctor.Invoke(null);
        var instanceValue = ReadFromInstanceMembers(providerType, instance);

        return TryAsEnumerable(instanceValue, out var instanceEnumerable) ? instanceEnumerable : null;
    }

    private static object? ReadFromStaticMembers(Type providerType)
    {
        const BindingFlags Flags = BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy | BindingFlags.IgnoreCase;

        var memberNames = new[]
        {
            "M1Definitions",
            "M1Cards",
            "WarriorCards",
            "Cards",
            "Definitions",
            "All",
            "GetM1Definitions",
            "GetDefinitions",
            "GetWarriorCards",
        };

        foreach (var memberName in memberNames)
        {
            var property = providerType.GetProperty(memberName, Flags);
            if (property is not null)
            {
                return property.GetValue(null);
            }

            var field = providerType.GetField(memberName, Flags);
            if (field is not null)
            {
                return field.GetValue(null);
            }

            var method = providerType.GetMethod(memberName, Flags, binder: null, types: Type.EmptyTypes, modifiers: null);
            if (method is not null)
            {
                return method.Invoke(null, null);
            }
        }

        return null;
    }

    private static object? ReadFromInstanceMembers(Type providerType, object instance)
    {
        const BindingFlags Flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase;

        var memberNames = new[]
        {
            "M1Definitions",
            "M1Cards",
            "WarriorCards",
            "Cards",
            "Definitions",
            "All",
            "GetM1Definitions",
            "GetDefinitions",
            "GetWarriorCards",
        };

        foreach (var memberName in memberNames)
        {
            var property = providerType.GetProperty(memberName, Flags);
            if (property is not null)
            {
                return property.GetValue(instance);
            }

            var field = providerType.GetField(memberName, Flags);
            if (field is not null)
            {
                return field.GetValue(instance);
            }

            var method = providerType.GetMethod(memberName, Flags, binder: null, types: Type.EmptyTypes, modifiers: null);
            if (method is not null)
            {
                return method.Invoke(instance, null);
            }
        }

        return null;
    }

    private static bool TryAsEnumerable(object? source, out IEnumerable? enumerable)
    {
        if (source is IEnumerable value && source is not string)
        {
            enumerable = value;
            return true;
        }

        enumerable = null;
        return false;
    }

    private static WarriorCardManifestEntry ReadManifestEntry(object rawDefinition)
    {
        var cardId = ReadRequiredString(rawDefinition, "card_id", "CardId", "stable_id", "StableId", "id", "Id");
        var rarity = ReadRequiredString(rawDefinition, "rarity", "Rarity");
        var cardType = ReadRequiredString(rawDefinition, "type", "Type", "card_type", "CardType");
        var isStarterDeck = ReadRequiredBoolean(rawDefinition, "starter_deck", "StarterDeck", "IsStarterDeck");
        var intent = ReadRequiredString(rawDefinition, "intent", "Intent", "intent_key", "IntentKey", "role", "Role");
        var tags = ReadRequiredStringList(rawDefinition, "tags", "Tags", "labels", "Labels");

        return new WarriorCardManifestEntry(cardId, rarity, cardType, isStarterDeck, tags, intent);
    }

    private static object? ReadMemberValue(object source, params string[] memberNames)
    {
        const BindingFlags Flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase;
        var sourceType = source.GetType();

        foreach (var memberName in memberNames)
        {
            var property = sourceType.GetProperty(memberName, Flags);
            if (property is not null)
            {
                return property.GetValue(source);
            }

            var field = sourceType.GetField(memberName, Flags);
            if (field is not null)
            {
                return field.GetValue(source);
            }
        }

        return null;
    }

    private static string ReadRequiredString(object source, params string[] memberNames)
    {
        var rawValue = ReadMemberValue(source, memberNames);

        rawValue.Should().NotBeNull(
            "expected one of these members on {0}: {1}",
            source.GetType().FullName,
            string.Join(", ", memberNames));

        (rawValue is string).Should().BeTrue(
            "expected member value for {0} on {1} to be a string",
            string.Join("/", memberNames),
            source.GetType().FullName);

        var value = (string)rawValue!;
        value.Should().NotBeNullOrWhiteSpace();
        return value;
    }

    private static bool ReadRequiredBoolean(object source, params string[] memberNames)
    {
        var rawValue = ReadMemberValue(source, memberNames);

        rawValue.Should().NotBeNull(
            "expected one of these members on {0}: {1}",
            source.GetType().FullName,
            string.Join(", ", memberNames));

        if (rawValue is bool boolValue)
        {
            return boolValue;
        }

        if (rawValue is string text)
        {
            var normalized = text.Trim();
            if (string.Equals(normalized, "y", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(normalized, "yes", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            if (string.Equals(normalized, "n", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(normalized, "no", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            var parsed = bool.TryParse(normalized, out var boolFromString);
            parsed.Should().BeTrue(
                "expected boolean-like text for {0} on {1}, got {2}",
                string.Join("/", memberNames),
                source.GetType().FullName,
                normalized);

            return boolFromString;
        }

        rawValue.Should().BeOfType<bool>(
            "expected {0} on {1} to be bool or bool-like text",
            string.Join("/", memberNames),
            source.GetType().FullName);

        return false;
    }

    private static IReadOnlyList<string> ReadRequiredStringList(object source, params string[] memberNames)
    {
        var rawValue = ReadMemberValue(source, memberNames);

        rawValue.Should().NotBeNull(
            "expected one of these members on {0}: {1}",
            source.GetType().FullName,
            string.Join(", ", memberNames));

        if (rawValue is string text)
        {
            var splitValues = text
                .Split(',', StringSplitOptions.RemoveEmptyEntries)
                .Select(part => part.Trim())
                .Where(part => part.Length > 0)
                .ToArray();

            splitValues.Should().NotBeEmpty("tag/label string should contain at least one value");
            return splitValues;
        }

        if (rawValue is IEnumerable enumerable && rawValue is not string)
        {
            var values = enumerable
                .Cast<object>()
                .Select(item => item?.ToString())
                .Where(item => !string.IsNullOrWhiteSpace(item))
                .Select(item => item!.Trim())
                .ToArray();

            values.Should().NotBeEmpty("tag/label collection should contain at least one value");
            return values;
        }

        rawValue.Should().BeAssignableTo<IEnumerable>(
            "expected {0} on {1} to be a string or collection of strings",
            string.Join("/", memberNames),
            source.GetType().FullName);

        return Array.Empty<string>();
    }

    private static IReadOnlyList<string> BuildIdDiff(IEnumerable<string> expectedIds, IEnumerable<string> actualIds)
    {
        var expected = new HashSet<string>(expectedIds, StringComparer.Ordinal);
        var actual = new HashSet<string>(actualIds, StringComparer.Ordinal);

        var missing = expected
            .Except(actual)
            .OrderBy(cardId => cardId, StringComparer.Ordinal)
            .Select(cardId => $"missing: {cardId}");

        var extra = actual
            .Except(expected)
            .OrderBy(cardId => cardId, StringComparer.Ordinal)
            .Select(cardId => $"extra: {cardId}");

        return missing.Concat(extra).ToArray();
    }

    private sealed record WarriorCardManifestEntry(
        string CardId,
        string Rarity,
        string CardType,
        bool IsStarterDeck,
        IReadOnlyList<string> Tags,
        string Intent);
}
