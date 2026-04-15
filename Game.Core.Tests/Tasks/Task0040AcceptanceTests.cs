using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0040AcceptanceTests
{
    private const int TaskmasterId = 40;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0040AcceptanceTests.cs";
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";

    private static readonly string[] RequiredEnemyCategories = { "normal", "elite", "boss" };

    private static readonly string[] DisallowedIntentLogicTokens =
    {
        "SelectIntent(",
        "ChooseIntent(",
        "ResolveIntent(",
        "IntentSelector",
        "Random.Shared",
        "new Random("
    };

    // ACC:T40.1
    [Fact]
    public void ShouldContainNormalEliteAndBossDefinitionsWithStatsAndIntentPools_WhenReadingAct1EnemyDefinitions()
    {
        var definitions = LoadAct1EnemyDefinitions();

        definitions.Should().NotBeEmpty("Act 1 enemy definitions must be provided as data.");

        definitions.Select(definition => definition.Category)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Should()
            .Contain(RequiredEnemyCategories);

        definitions.Should().OnlyContain(definition => definition.HasStats && definition.HasIntentPool);
    }

    [Fact]
    public void ShouldRefuseIntentSelectionLogic_WhenInspectingAct1EnemyDefinitionSources()
    {
        var dataFiles = DiscoverAct1EnemyDataFiles();
        var violatingFiles = dataFiles
            .Where(path =>
            {
                var source = File.ReadAllText(path);
                return DisallowedIntentLogicTokens.Any(token => source.Contains(token, StringComparison.Ordinal));
            })
            .ToArray();

        dataFiles.Should().NotBeEmpty("Task 40 requires explicit enemy data sources.");
        violatingFiles.Should().BeEmpty("Task 40 is data-only and must not include intent selection logic implementation.");
    }

    // ACC:T40.2
    [Fact]
    public void ShouldKeepEnemyDefinitionOrderDeterministic_WhenLoadingAct1EnemyDefinitionsRepeatedly()
    {
        var firstRun = LoadAct1EnemyDefinitions().Select(definition => definition.Id).ToArray();
        var secondRun = LoadAct1EnemyDefinitions().Select(definition => definition.Id).ToArray();

        firstRun.Should().NotBeEmpty();
        firstRun.Should().OnlyHaveUniqueItems();
        firstRun.Should().Equal(secondRun);
    }

    // ACC:T40.3
    [Fact]
    public void ShouldKeepTaskTestRefsTraceable_WhenOverlayChecklistExistsForTask40()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        var taskTestRefs = ReadStringArray(taskNode, "test_refs");
        taskTestRefs.Should().Contain(ThisTaskTestRef);

        var checklistPath = Path.Combine(FindRepositoryRoot(), OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(checklistPath))
        {
            return;
        }

        var checklist = File.ReadAllText(checklistPath);
        var hasTask40Section = checklist.Contains("Task 40", StringComparison.OrdinalIgnoreCase)
            || checklist.Contains("Task0040", StringComparison.OrdinalIgnoreCase)
            || checklist.Contains("GM-0140", StringComparison.OrdinalIgnoreCase);

        if (!hasTask40Section)
        {
            return;
        }

        checklist.Should().Contain(ThisTaskTestRef);
    }

    // ACC:T40.4
    [Fact]
    [Trait("adr", "ADR-0021")]
    public void ShouldReferenceAdr0021_WhenValidatingTaskMetadataAndTestSource()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var adrRefs = ReadStringArray(taskNode, "adr_refs");

        var source = File.ReadAllText(Path.Combine(
            FindRepositoryRoot(),
            ThisTaskTestRef.Replace('/', Path.DirectorySeparatorChar)));

        adrRefs.Should().Contain("ADR-0021");
        source.Should().Contain("ADR-0021");
    }

    private static IReadOnlyList<EnemyDefinitionView> LoadAct1EnemyDefinitions()
    {
        var definitions = new List<EnemyDefinitionView>();

        foreach (var filePath in DiscoverAct1EnemyDataFiles())
        {
            using var document = JsonDocument.Parse(File.ReadAllText(filePath));
            CollectDefinitionViews(document.RootElement, definitions);
        }

        return definitions;
    }

    private static IReadOnlyList<string> DiscoverAct1EnemyDataFiles()
    {
        var repositoryRoot = FindRepositoryRoot();
        var gameCoreDirectory = Path.Combine(repositoryRoot, "Game.Core");
        if (!Directory.Exists(gameCoreDirectory))
        {
            return Array.Empty<string>();
        }

        return Directory.EnumerateFiles(gameCoreDirectory, "*.json", SearchOption.AllDirectories)
            .Where(path =>
                !path.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase)
                && !path.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase))
            .Where(path =>
            {
                var fileName = Path.GetFileName(path);
                if (fileName.Contains("enemy", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }

                var source = File.ReadAllText(path);
                return source.Contains("EnemyDefinition", StringComparison.Ordinal)
                    && source.Contains("Act 1", StringComparison.OrdinalIgnoreCase);
            })
            .OrderBy(path => path, StringComparer.Ordinal)
            .ToArray();
    }

    private static void CollectDefinitionViews(JsonElement element, ICollection<EnemyDefinitionView> definitions)
    {
        if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                CollectDefinitionViews(item, definitions);
            }

            return;
        }

        if (element.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        if (TryCreateDefinitionView(element, out var definition))
        {
            definitions.Add(definition);
        }

        foreach (var property in element.EnumerateObject())
        {
            CollectDefinitionViews(property.Value, definitions);
        }
    }

    private static bool TryCreateDefinitionView(JsonElement element, out EnemyDefinitionView definition)
    {
        definition = default!;

        var id = ReadString(element, "id", "enemyId", "key", "name");
        var category = ReadString(element, "category", "type", "tier", "archetype");

        if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(category))
        {
            return false;
        }

        var hasStats = HasObjectWithAnyProperty(element, "stats", "statBlock");
        var hasIntentPool = HasStringArrayWithAnyItem(element, "intentPools", "intentPool", "intents");

        definition = new EnemyDefinitionView(
            id.Trim(),
            category.Trim().ToLowerInvariant(),
            hasStats,
            hasIntentPool);

        return true;
    }

    private static bool HasObjectWithAnyProperty(JsonElement element, params string[] propertyNames)
    {
        if (!TryGetProperty(element, out var property, propertyNames) || property.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        return property.EnumerateObject().Any();
    }

    private static bool HasStringArrayWithAnyItem(JsonElement element, params string[] propertyNames)
    {
        if (!TryGetProperty(element, out var property, propertyNames) || property.ValueKind != JsonValueKind.Array)
        {
            return false;
        }

        return property.EnumerateArray().Any(item =>
            item.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(item.GetString()));
    }

    private static string ReadString(JsonElement element, params string[] propertyNames)
    {
        if (!TryGetProperty(element, out var property, propertyNames) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
    }

    private static bool TryGetProperty(JsonElement element, out JsonElement property, params string[] propertyNames)
    {
        foreach (var propertyName in propertyNames)
        {
            if (element.TryGetProperty(propertyName, out property))
            {
                return true;
            }
        }

        property = default;
        return false;
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));

        foreach (var taskNode in document.RootElement.EnumerateArray())
        {
            if (taskNode.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.TryGetInt32(out var value)
                && value == taskmasterId)
            {
                return taskNode.Clone();
            }
        }

        throw new InvalidOperationException($"Task with taskmaster_id={taskmasterId} was not found in {taskFilePath}.");
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var propertyNode) || propertyNode.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return propertyNode.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string FindRepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, ".taskmaster")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new InvalidOperationException("Repository root could not be located from the test runtime directory.");
    }

    private sealed record EnemyDefinitionView(string Id, string Category, bool HasStats, bool HasIntentPool);
}
