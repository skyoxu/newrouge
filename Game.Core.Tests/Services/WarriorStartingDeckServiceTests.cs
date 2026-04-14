using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

public sealed class WarriorStartingDeckServiceTests
{
    private static readonly IReadOnlyList<WarriorStartingDeckManifestEntry> ExpectedM1WarriorCards =
        new List<WarriorStartingDeckManifestEntry>
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

    private static readonly string[] ProviderMemberNameCandidates =
    {
        "BuildStartingDeck",
        "CreateStartingDeck",
        "GetStartingDeck",
        "GetStarterDeck",
        "GetStartingDeckCards",
        "GetCards",
        "Cards",
        "StartingDeck",
        "StarterDeck",
        "Definitions",
        "Manifest",
    };

    public static IEnumerable<object[]> ExpectedM1WarriorCardsForTheory()
    {
        return ExpectedM1WarriorCards.Select(card => new object[]
        {
            card.CardId,
            card.Rarity,
            card.CardType,
            card.IsStarterDeck,
            card.Intent,
            card.Tags.ToArray(),
        });
    }

    // ACC:T24.4
    [Fact]
    public void ShouldMatchM1CardCountAndIds_WhenBuildingWarriorStartingDeck()
    {
        var actualCards = ReadWarriorStartingDeckManifest();

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
    public void ShouldMatchM1CoreAttributes_WhenBuildingWarriorStartingDeck(
        string cardId,
        string rarity,
        string cardType,
        bool isStarterDeck,
        string intent,
        string[] tags)
    {
        var actualCardsById = ReadWarriorStartingDeckManifest()
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
    public void ShouldExposeReadableTagsAndIntent_WhenBuildingWarriorStartingDeck()
    {
        var actualCards = ReadWarriorStartingDeckManifest();

        actualCards.Should().OnlyContain(card =>
            card.Tags.Count > 0 &&
            card.Tags.All(tag => !string.IsNullOrWhiteSpace(tag)));

        actualCards.Should().OnlyContain(card => !string.IsNullOrWhiteSpace(card.Intent));
    }

    [Fact]
    public void ShouldRejectManifestMismatch_WhenValidatingAgainstM1()
    {
        var actualCardIds = ExpectedM1WarriorCards
            .Select(card => card.CardId)
            .Where(cardId => !string.Equals(cardId, "card.warrior.crush", StringComparison.Ordinal))
            .Append("card.warrior.placeholder")
            .ToArray();

        var validation = ValidateManifestAgainstM1(
            ExpectedM1WarriorCards.Select(card => card.CardId).ToArray(),
            actualCardIds);

        validation.IsValid.Should().BeFalse("a mismatch against the M1 content list must fail validation");
        validation.DiffLines.Should().Contain("missing: card.warrior.crush");
        validation.DiffLines.Should().Contain("extra: card.warrior.placeholder");
    }

    private static IReadOnlyList<WarriorStartingDeckManifestEntry> ReadWarriorStartingDeckManifest()
    {
        var providerType = ResolveWarriorStartingDeckProviderType();

        providerType.Should().NotBeNull(
            "Task 24 requires a Warrior starting deck provider that exposes the M1 deck manifest.");

        var definitions = ReadDefinitionsCollection(providerType!);

        definitions.Should().NotBeNull("the Warrior starting deck provider must return an enumerable deck manifest");
        var entries = definitions!.Cast<object>().Select(ReadManifestEntry).ToArray();

        entries.Should().NotBeEmpty("the Warrior starting deck manifest must contain cards");
        return entries;
    }

    private static Type? ResolveWarriorStartingDeckProviderType()
    {
        var exactTypeNames = new[]
        {
            "Game.Core.Services.WarriorStartingDeckService",
            "Game.Core.Domain.WarriorCardDefinitions",
            "Game.Core.Domain.Cards.WarriorCardDefinitions",
            "Game.Core.Content.WarriorCardDefinitions",
            "Game.Core.Services.WarriorCardDefinitions",
        };

        var typeNameCandidates = new[]
        {
            "WarriorStartingDeckService",
            "WarriorCardDefinitions",
            "WarriorCardCatalog",
            "WarriorCardManifest",
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
        return AppDomain.CurrentDomain
            .GetAssemblies()
            .Where(assembly => !assembly.IsDynamic)
            .Where(assembly =>
            {
                var assemblyName = assembly.GetName().Name;
                return !string.IsNullOrWhiteSpace(assemblyName)
                       && assemblyName.StartsWith("Game.Core", StringComparison.Ordinal);
            });
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
        var bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;

        foreach (var memberName in ProviderMemberNameCandidates)
        {
            var value = ReadMemberValue(providerType, instance: null, bindingFlags, memberName);
            if (value is not null)
            {
                return value;
            }
        }

        return null;
    }

    private static object? ReadFromInstanceMembers(Type providerType, object instance)
    {
        var bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;

        foreach (var memberName in ProviderMemberNameCandidates)
        {
            var value = ReadMemberValue(providerType, instance, bindingFlags, memberName);
            if (value is not null)
            {
                return value;
            }
        }

        return null;
    }

    private static object? ReadMemberValue(Type providerType, object? instance, BindingFlags bindingFlags, string memberName)
    {
        var property = providerType.GetProperty(memberName, bindingFlags);
        if (property is not null && property.GetIndexParameters().Length == 0)
        {
            return property.GetValue(instance);
        }

        var field = providerType.GetField(memberName, bindingFlags);
        if (field is not null)
        {
            return field.GetValue(instance);
        }

        var method = providerType
            .GetMethods(bindingFlags)
            .FirstOrDefault(candidate =>
                string.Equals(candidate.Name, memberName, StringComparison.Ordinal)
                && candidate.GetParameters().Length == 0);

        if (method is not null)
        {
            return method.Invoke(instance, null);
        }

        return null;
    }

    private static bool TryAsEnumerable(object? value, out IEnumerable enumerable)
    {
        if (value is IEnumerable sequence && value is not string)
        {
            enumerable = sequence;
            return true;
        }

        enumerable = Array.Empty<object>();
        return false;
    }

    private static WarriorStartingDeckManifestEntry ReadManifestEntry(object rawDefinition)
    {
        var cardId = ReadRequiredString(rawDefinition, "card_id", "CardId", "stable_id", "StableId", "id", "Id");
        var rarity = ReadRequiredString(rawDefinition, "rarity", "Rarity");
        var cardType = ReadRequiredString(rawDefinition, "type", "Type", "card_type", "CardType");
        var isStarterDeck = ReadRequiredBoolean(rawDefinition, "starter_deck", "StarterDeck", "IsStarterDeck");
        var intent = ReadRequiredString(rawDefinition, "intent", "Intent", "intent_key", "IntentKey", "role", "Role");
        var tags = ReadRequiredStringList(rawDefinition, "tags", "Tags", "labels", "Labels");

        return new WarriorStartingDeckManifestEntry(cardId, rarity, cardType, isStarterDeck, tags, intent);
    }

    private static string ReadRequiredString(object rawDefinition, params string[] memberNames)
    {
        foreach (var memberName in memberNames)
        {
            var value = ReadMemberValue(
                rawDefinition.GetType(),
                rawDefinition,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                memberName);

            if (value is string text && !string.IsNullOrWhiteSpace(text))
            {
                return text;
            }
        }

        throw new InvalidOperationException($"Missing required string member on card definition: [{string.Join(", ", memberNames)}]");
    }

    private static bool ReadRequiredBoolean(object rawDefinition, params string[] memberNames)
    {
        foreach (var memberName in memberNames)
        {
            var value = ReadMemberValue(
                rawDefinition.GetType(),
                rawDefinition,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                memberName);

            if (value is bool flag)
            {
                return flag;
            }

            if (value is string text && bool.TryParse(text, out var parsed))
            {
                return parsed;
            }
        }

        throw new InvalidOperationException($"Missing required boolean member on card definition: [{string.Join(", ", memberNames)}]");
    }

    private static IReadOnlyList<string> ReadRequiredStringList(object rawDefinition, params string[] memberNames)
    {
        foreach (var memberName in memberNames)
        {
            var value = ReadMemberValue(
                rawDefinition.GetType(),
                rawDefinition,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                memberName);

            if (value is IEnumerable sequence && value is not string)
            {
                var list = sequence
                    .Cast<object>()
                    .Select(item => item?.ToString())
                    .Where(item => !string.IsNullOrWhiteSpace(item))
                    .Cast<string>()
                    .ToArray();

                if (list.Length > 0)
                {
                    return list;
                }
            }
        }

        throw new InvalidOperationException($"Missing required string-list member on card definition: [{string.Join(", ", memberNames)}]");
    }

    private static WarriorDeckManifestValidationResult ValidateManifestAgainstM1(
        IReadOnlyCollection<string> expectedCardIds,
        IReadOnlyCollection<string> actualCardIds)
    {
        WarriorStartingDeckService.Definitions
            .Select(card => card.CardId)
            .Should()
            .BeEquivalentTo(expectedCardIds, options => options.WithoutStrictOrdering());

        return WarriorStartingDeckService.ValidateManifestAgainstM1(actualCardIds);
    }

    private sealed class WarriorStartingDeckManifestEntry
    {
        public WarriorStartingDeckManifestEntry(
            string cardId,
            string rarity,
            string cardType,
            bool isStarterDeck,
            IEnumerable<string> tags,
            string intent)
        {
            CardId = cardId;
            Rarity = rarity;
            CardType = cardType;
            IsStarterDeck = isStarterDeck;
            Tags = tags.ToArray();
            Intent = intent;
        }

        public string CardId { get; }

        public string Rarity { get; }

        public string CardType { get; }

        public bool IsStarterDeck { get; }

        public IReadOnlyList<string> Tags { get; }

        public string Intent { get; }
    }

}
