using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T24")]
[Trait("adr", "ADR-0033")]
public sealed class Task0024AcceptanceTests
{
    private static readonly string[] ExpectedM1WarriorCardIds =
    {
        "card.warrior.cleave",
        "card.warrior.guard",
        "card.warrior.rage_surge",
        "card.warrior.bloodrush",
        "card.warrior.taunt",
        "card.warrior.shield_wall",
        "card.warrior.overpower",
        "card.warrior.battlecry",
        "card.warrior.crush",
        "card.warrior.relentless",
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
        "M1Definitions",
        "WarriorCards",
    };

    // ACC:T24.1
    [Fact]
    public void ShouldContainExactlyM1WarriorIds_WhenStartingDeckIsInitialized()
    {
        var deckEntries = ReadWarriorStartingDeckEntries();

        deckEntries.Should().HaveCount(10);
        deckEntries
            .Select(entry => entry.CardId)
            .Should()
            .BeEquivalentTo(ExpectedM1WarriorCardIds, options => options.WithoutStrictOrdering());
    }

    // ACC:T24.1
    [Fact]
    public void ShouldRejectMissingOrExtraCards_WhenM1ManifestDoesNotMatchDeck()
    {
        var simulatedActualCardIds = ExpectedM1WarriorCardIds
            .Where(cardId => !string.Equals(cardId, "card.warrior.crush", StringComparison.Ordinal))
            .Append("card.warrior.placeholder")
            .ToArray();

        var validation = ValidateManifestAgainstM1(ExpectedM1WarriorCardIds, simulatedActualCardIds);

        validation.IsValid.Should().BeFalse("manifest mismatch must fail instead of silently passing");
        validation.DiffLines.Should().Contain("missing: card.warrior.crush");
        validation.DiffLines.Should().Contain("extra: card.warrior.placeholder");
    }

    // ACC:T24.2
    [Fact]
    public void ShouldExposeTagsAndIntentForEachCard_WhenReadingWarriorCardDefinitions()
    {
        var deckEntries = ReadWarriorStartingDeckEntries();

        deckEntries.Select(entry => entry.CardId).Should().Contain("card.warrior.cleave");
        deckEntries.Should().OnlyContain(entry =>
            entry.Tags.Count > 0 &&
            entry.Tags.All(tag => !string.IsNullOrWhiteSpace(tag)));
        deckEntries.Should().OnlyContain(entry => !string.IsNullOrWhiteSpace(entry.Intent));
    }

    // ACC:T24.3
    [Fact]
    public void ShouldKeepTask24TestRefsScoped_WhenOverlayChecklistIsPresent()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            24);

        var testRefs = ReadStringArray(taskNode, "test_refs");

        testRefs.Should().Contain("Game.Core.Tests/Tasks/Task0024AcceptanceTests.cs");
        testRefs.Should().Contain("Game.Core.Tests/Services/WarriorStartingDeckServiceTests.cs");
        testRefs.Should().Contain("Game.Core.Tests/Domain/WarriorCardDefinitionsTests.cs");
        testRefs.Should().Contain("Game.Core.Tests/Services/WarriorDeckManifestValidationTests.cs");
        testRefs.Should().OnlyContain(path =>
            path.StartsWith("Game.Core.Tests/", StringComparison.Ordinal) &&
            (path.Contains("Task0024", StringComparison.Ordinal) || path.Contains("Warrior", StringComparison.Ordinal)));

        var overlayRefs = ReadStringArray(taskNode, "overlay_refs");
        var overlayChecklistRef = overlayRefs.FirstOrDefault(path =>
            path.EndsWith("ACCEPTANCE_CHECKLIST.md", StringComparison.Ordinal));

        if (overlayChecklistRef is not null)
        {
            var overlayChecklistPath = Path.Combine(repoRoot, overlayChecklistRef.Replace('/', Path.DirectorySeparatorChar));
            File.Exists(overlayChecklistPath).Should().BeTrue(
                "task 24 declares an overlay acceptance checklist and it must resolve to a real file");
        }
    }

    // ACC:T24.6
    [Fact]
    public void ShouldExposeNamedStarterDeckInitializer_WhenBuildingWarriorDeck()
    {
        var providerType = ResolveWarriorStartingDeckProviderType();

        providerType.Should().NotBeNull(
            "task 24 requires an explicitly named starter deck initializer service or equivalent component");

        var deckEntries = ReadWarriorStartingDeckEntries();

        deckEntries.Should().HaveCount(10);
    }

    // ACC:T24.7
    [Fact]
    public void ShouldReferenceAdr0033InTaskMetadataAndTests_WhenAuditingTraceability()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            24);

        var adrRefs = ReadStringArray(taskNode, "adr_refs");
        adrRefs.Should().Contain("ADR-0033");

        var thisSource = File.ReadAllText(GetCurrentSourceFilePath());
        thisSource.Should().Contain("ADR-0033", "Task 24 implementation and tests must explicitly reference ADR-0033");
    }

    private static IReadOnlyList<WarriorDeckEntry> ReadWarriorStartingDeckEntries()
    {
        var providerType = ResolveWarriorStartingDeckProviderType();

        providerType.Should().NotBeNull(
            "task 24 requires a warrior starter deck provider that can be consumed by acceptance tests");

        var definitions = ReadDefinitionsCollection(providerType!);

        definitions.Should().NotBeNull("the warrior starter deck provider must expose an enumerable output");
        var entries = definitions!.Cast<object>().Select(ReadWarriorDeckEntry).ToArray();

        entries.Should().NotBeEmpty("the warrior starter deck provider must produce at least one card entry");
        return entries;
    }

    private static Type? ResolveWarriorStartingDeckProviderType()
    {
        var exactTypeNames = new[]
        {
            "Game.Core.Services.WarriorStartingDeckService",
            "Game.Core.Services.WarriorStartingDeckInitializer",
            "Game.Core.Domain.WarriorCardDefinitions",
            "Game.Core.Domain.Cards.WarriorCardDefinitions",
            "Game.Core.Content.WarriorCardDefinitions",
            "Game.Core.Services.WarriorCardDefinitions",
        };

        var simpleTypeNameCandidates = new[]
        {
            "WarriorStartingDeckService",
            "WarriorStartingDeckInitializer",
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
                if (simpleTypeNameCandidates.Any(name =>
                        string.Equals(candidateType.Name, name, StringComparison.Ordinal)))
                {
                    return candidateType;
                }
            }
        }

        return null;
    }

    private static IEnumerable<Assembly> GetGameCoreAssemblies()
    {
        var loadedAssemblies = AppDomain.CurrentDomain
            .GetAssemblies()
            .Where(assembly => !assembly.IsDynamic)
            .ToList();

        if (!loadedAssemblies.Any(assembly =>
                string.Equals(assembly.GetName().Name, "Game.Core", StringComparison.OrdinalIgnoreCase)))
        {
            try
            {
                loadedAssemblies.Add(Assembly.Load("Game.Core"));
            }
            catch
            {
                // Keep reflection-based tests runnable even when assembly loading is constrained.
            }
        }

        return loadedAssemblies.Where(assembly =>
            assembly.GetName().Name is not null &&
            assembly.GetName().Name!.StartsWith("Game.Core", StringComparison.OrdinalIgnoreCase));
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
        var staticValue = ReadFromMembers(providerType, instance: null, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
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
        var instanceValue = ReadFromMembers(providerType, instance, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);

        return TryAsEnumerable(instanceValue, out var instanceEnumerable) ? instanceEnumerable : null;
    }

    private static object? ReadFromMembers(Type ownerType, object? instance, BindingFlags bindingFlags)
    {
        foreach (var memberName in ProviderMemberNameCandidates)
        {
            var value = TryReadMemberValue(ownerType, instance, bindingFlags, memberName);
            if (value is not null)
            {
                return value;
            }
        }

        return null;
    }

    private static object? TryReadMemberValue(Type ownerType, object? instance, BindingFlags bindingFlags, string memberName)
    {
        var property = ownerType.GetProperty(memberName, bindingFlags);
        if (property is not null && property.GetIndexParameters().Length == 0)
        {
            return property.GetValue(instance);
        }

        var field = ownerType.GetField(memberName, bindingFlags);
        if (field is not null)
        {
            return field.GetValue(instance);
        }

        var method = ownerType
            .GetMethods(bindingFlags)
            .FirstOrDefault(candidate =>
                string.Equals(candidate.Name, memberName, StringComparison.Ordinal) &&
                candidate.GetParameters().Length == 0);

        return method?.Invoke(instance, null);
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

    private static WarriorDeckEntry ReadWarriorDeckEntry(object rawDefinition)
    {
        var cardId = ReadRequiredString(rawDefinition, "card_id", "CardId", "stable_id", "StableId", "id", "Id");
        var tags = ReadRequiredStringList(rawDefinition, "tags", "Tags", "labels", "Labels");
        var intent = ReadRequiredString(rawDefinition, "intent", "Intent", "intent_key", "IntentKey", "role", "Role");

        return new WarriorDeckEntry(cardId, tags, intent);
    }

    private static string ReadRequiredString(object source, params string[] memberNames)
    {
        foreach (var memberName in memberNames)
        {
            var value = TryReadMemberValue(
                source.GetType(),
                source,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                memberName);

            if (value is string text && !string.IsNullOrWhiteSpace(text))
            {
                return text;
            }
        }

        throw new InvalidOperationException($"Missing required string member: [{string.Join(", ", memberNames)}]");
    }

    private static IReadOnlyList<string> ReadRequiredStringList(object source, params string[] memberNames)
    {
        foreach (var memberName in memberNames)
        {
            var value = TryReadMemberValue(
                source.GetType(),
                source,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                memberName);

            if (value is string text)
            {
                var splitValues = text
                    .Split(',', StringSplitOptions.RemoveEmptyEntries)
                    .Select(part => part.Trim())
                    .Where(part => part.Length > 0)
                    .ToArray();

                if (splitValues.Length > 0)
                {
                    return splitValues;
                }
            }

            if (value is IEnumerable sequence && value is not string)
            {
                var values = sequence
                    .Cast<object>()
                    .Select(item => item?.ToString())
                    .Where(item => !string.IsNullOrWhiteSpace(item))
                    .Select(item => item!.Trim())
                    .ToArray();

                if (values.Length > 0)
                {
                    return values;
                }
            }
        }

        throw new InvalidOperationException($"Missing required string-list member: [{string.Join(", ", memberNames)}]");
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        File.Exists(taskFilePath).Should().BeTrue("task metadata file must exist: {0}", taskFilePath);

        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var matched = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var value) &&
                value.ValueKind == JsonValueKind.Number &&
                value.GetInt32() == taskmasterId);

        matched.ValueKind.Should().NotBe(JsonValueKind.Undefined, "taskmaster_id={0} must exist in {1}", taskmasterId, taskFilePath);
        return matched.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        node.TryGetProperty(propertyName, out var property).Should().BeTrue("property {0} must exist in task metadata", propertyName);
        property.ValueKind.Should().Be(JsonValueKind.Array, "property {0} must be an array", propertyName);

        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
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

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from test execution directory.");
    }

    private static string GetCurrentSourceFilePath([CallerFilePath] string path = "") => path;

    private sealed record WarriorDeckEntry(
        string CardId,
        IReadOnlyList<string> Tags,
        string Intent);
}
