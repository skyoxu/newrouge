using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T26")]
public sealed class Task0026AcceptanceTests
{
    private static readonly string[] RequiredDifficultyJsonFields =
    {
        "difficulty_id",
        "label_key",
        "description_key",
        "ruleset_id",
    };

    private static readonly string[] RequiredDifficultyPropertyNames =
    {
        "DifficultyId",
        "LabelKey",
        "DescriptionKey",
        "RulesetId",
    };

    // ACC:T26.4
    [Fact]
    [Trait("acceptance", "ACC:T26.4")]
    public void ShouldReferenceTask0026AcceptanceTests_WhenAcceptanceRequiresRunMetadataVerification()
    {
        var acceptanceItems = ReadAcceptanceItemsForTask26();

        acceptanceItems.Should().Contain(item =>
            item.Contains("xUnit tests must assert that the selected difficulty value is persisted into run metadata at run start.", StringComparison.Ordinal) &&
            item.Contains("Refs: Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs", StringComparison.Ordinal));
    }

    // ACC:T26.5
    [Fact]
    [Trait("acceptance", "ACC:T26.5")]
    public void ShouldReferenceTask0026AcceptanceTests_WhenAcceptanceRequiresDifficultyImmutabilityVerification()
    {
        var acceptanceItems = ReadAcceptanceItemsForTask26();

        acceptanceItems.Should().Contain(item =>
            item.Contains("xUnit tests verify difficulty is immutable after run start (reject or value unchanged).", StringComparison.Ordinal) &&
            item.Contains("Refs: Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs", StringComparison.Ordinal));
    }

    // ACC:T26.6
    [Fact]
    [Trait("acceptance", "ACC:T26.6")]
    public async Task ShouldPersistSelectedDifficultyValue_WhenRunStarts()
    {
        var selectedDifficulty = new DifficultyConfig(
            DifficultyId: 7,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard");

        selectedDifficulty.DifficultyId.Should().BeGreaterOrEqualTo(1);
        selectedDifficulty.DifficultyId.Should().BeLessOrEqualTo(10);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        await service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-enter",
            selectedDifficulty: selectedDifficulty));

        var runMetadata = await service.ReadContinueMetadataAsync();
        AssertMetadataMatchesSnapshot(runMetadata, selectedDifficulty);
    }

    // ACC:T26.7
    [Fact]
    [Trait("acceptance", "ACC:T26.7")]
    public async Task ShouldKeepDifficultyUnchanged_WhenMutationIsRequestedAfterRunStart()
    {
        var initialSnapshot = new DifficultyConfig(
            DifficultyId: 4,
            LabelKey: "difficulty.label.normal",
            DescriptionKey: "difficulty.description.normal",
            RulesetId: "ruleset.m1");
        var mutationSnapshot = new DifficultyConfig(
            DifficultyId: 9,
            LabelKey: "difficulty.label.nightmare",
            DescriptionKey: "difficulty.description.nightmare",
            RulesetId: "ruleset.m9");

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        await service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-enter",
            selectedDifficulty: initialSnapshot));

        var exception = await Record.ExceptionAsync(() => service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-post-enter",
            selectedDifficulty: mutationSnapshot)));

        exception.Should().BeOfType<InvalidOperationException>();
        exception.Should().NotBeNull();
        exception!.Message.Should().Contain("reason_code=difficulty_immutable");
        exception.Data["reason"]?.ToString().Should().Be("difficulty_immutable");

        var runMetadata = await service.ReadContinueMetadataAsync();
        AssertMetadataMatchesSnapshot(runMetadata, initialSnapshot);
    }

    // ACC:T26.8
    [Fact]
    [Trait("acceptance", "ACC:T26.8")]
    public void ShouldExposeRequiredDifficultySnapshotFields_WhenDefiningDifficultyConfigContract()
    {
        var propertyNames = typeof(DifficultyConfig)
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Select(property => property.Name)
            .ToArray();

        propertyNames.Should().Contain(RequiredDifficultyPropertyNames);
    }

    // ACC:T26.9
    [Fact]
    [Trait("acceptance", "ACC:T26.9")]
    public void ShouldRejectDifficultyFieldMutationRequests_WhenRunMetadataIsPersisted()
    {
        var runMetadataType = ResolveRunMetadataType();
        runMetadataType.Should().NotBeNull();

        var mutableDifficultyProperties = RequiredDifficultyPropertyNames
            .Select(propertyName => runMetadataType!.GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance))
            .Where(property => property is not null && property.SetMethod is not null)
            .Select(property => property!.Name)
            .ToArray();

        mutableDifficultyProperties.Should().BeEmpty();
    }

    // ACC:T26.10
    [Fact]
    [Trait("acceptance", "ACC:T26.10")]
    public async Task ShouldContainAllRequiredDifficultyFields_WhenRunMetadataIsProducedAtRunStart()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();

        var incompleteException = await Record.ExceptionAsync(() => service.WriteAutosaveAsync(CreateSnapshotWithIncompleteDifficulty(
            runId: "run-26",
            savePointId: "node-pre-enter")));
        incompleteException.Should().BeOfType<InvalidOperationException>();
        incompleteException.Should().NotBeNull();
        incompleteException!.Message.Should().Contain("reason_code=difficulty_snapshot_incomplete");
        incompleteException.Data["reason"]?.ToString().Should().Be("difficulty_snapshot_incomplete");

        var selectedDifficulty = new DifficultyConfig(
            DifficultyId: 5,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard");

        await service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-enter",
            selectedDifficulty: selectedDifficulty));

        var runMetadataType = ResolveRunMetadataType();
        runMetadataType.Should().NotBeNull();

        var jsonFieldNames = runMetadataType!
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Select(GetJsonFieldName)
            .ToArray();

        jsonFieldNames.Should().Contain(RequiredDifficultyJsonFields);
    }

    // ACC:T26.11
    [Fact]
    [Trait("acceptance", "ACC:T26.11")]
    public async Task ShouldMatchSnapshotFieldTypes_WhenRunMetadataPersistsDifficultySelection()
    {
        var selectedDifficulty = new DifficultyConfig(
            DifficultyId: 6,
            LabelKey: "difficulty.label.expert",
            DescriptionKey: "difficulty.description.expert",
            RulesetId: "ruleset.expert");

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        await service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-enter",
            selectedDifficulty: selectedDifficulty));

        var runMetadata = await service.ReadContinueMetadataAsync();
        AssertMetadataMatchesSnapshot(runMetadata, selectedDifficulty);

        var runMetadataType = runMetadata!.GetType();
        foreach (var propertyName in RequiredDifficultyPropertyNames)
        {
            var snapshotProperty = typeof(DifficultyConfig).GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
            var metadataProperty = runMetadataType.GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);

            snapshotProperty.Should().NotBeNull();
            metadataProperty.Should().NotBeNull();
            if (snapshotProperty is not null && metadataProperty is not null)
            {
                metadataProperty.PropertyType.Should().Be(snapshotProperty.PropertyType);
            }
        }
    }

    // ACC:T26.12
    [Fact]
    [Trait("acceptance", "ACC:T26.12")]
    public async Task ShouldRemainUnchangedAfterMutationRequests_WhenPersistedDifficultyFieldsAreStored()
    {
        var initialSnapshot = new DifficultyConfig(
            DifficultyId: 3,
            LabelKey: "difficulty.label.easy",
            DescriptionKey: "difficulty.description.easy",
            RulesetId: "ruleset.easy");
        var mutationSnapshot = new DifficultyConfig(
            DifficultyId: 8,
            LabelKey: "difficulty.label.nightmare",
            DescriptionKey: "difficulty.description.nightmare",
            RulesetId: "ruleset.nightmare");

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        await service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-enter",
            selectedDifficulty: initialSnapshot));

        await Record.ExceptionAsync(() => service.WriteAutosaveAsync(CreateSnapshot(
            runId: "run-26",
            savePointId: "node-pre-boss",
            selectedDifficulty: mutationSnapshot)));

        var runMetadata = await service.ReadContinueMetadataAsync();
        AssertMetadataMatchesSnapshot(runMetadata, initialSnapshot);
    }

    [Fact]
    public void ShouldRejectOutOfRangeDifficultyId_WhenCreatingDifficultyConfig()
    {
        Action act = () => _ = new DifficultyConfig(
            DifficultyId: 11,
            LabelKey: "difficulty.label.invalid",
            DescriptionKey: "difficulty.description.invalid",
            RulesetId: "ruleset.invalid");

        act.Should().Throw<ArgumentOutOfRangeException>();
    }

    private static void AssertMetadataMatchesSnapshot(ContinueMetadata? runMetadata, DifficultyConfig selectedDifficulty)
    {
        runMetadata.Should().NotBeNull();
        runMetadata!.DifficultyId.Should().Be(selectedDifficulty.DifficultyId);
        runMetadata.LabelKey.Should().Be(selectedDifficulty.LabelKey);
        runMetadata.DescriptionKey.Should().Be(selectedDifficulty.DescriptionKey);
        runMetadata.RulesetId.Should().Be(selectedDifficulty.RulesetId);
    }

    private static AutosaveSnapshot CreateSnapshot(string runId, string savePointId, DifficultyConfig selectedDifficulty)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            offer_locks = new[] { "offer-26-a", "offer-26-b" },
            difficulty = new
            {
                difficulty_id = selectedDifficulty.DifficultyId,
                label_key = selectedDifficulty.LabelKey,
                description_key = selectedDifficulty.DescriptionKey,
                ruleset_id = selectedDifficulty.RulesetId,
            },
        });

        return new AutosaveSnapshot(
            RunId: runId,
            SavePointId: savePointId,
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
    }

    private static AutosaveSnapshot CreateSnapshotWithIncompleteDifficulty(string runId, string savePointId)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            offer_locks = new[] { "offer-26-a", "offer-26-b" },
            difficulty = new
            {
                difficulty_id = 4,
                label_key = "difficulty.label.normal",
                description_key = "difficulty.description.normal",
            },
        });

        return new AutosaveSnapshot(
            RunId: runId,
            SavePointId: savePointId,
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
    }

    private static string[] ReadAcceptanceItemsForTask26()
    {
        var repoRoot = FindRepositoryRoot();
        var taskFilePath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");

        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var taskNode = document.RootElement
            .EnumerateArray()
            .First(node =>
                node.TryGetProperty("taskmaster_id", out var taskmasterId) &&
                taskmasterId.ValueKind == JsonValueKind.Number &&
                taskmasterId.GetInt32() == 26);

        return taskNode
            .GetProperty("acceptance")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
    }

    private static Type? ResolveRunMetadataType()
    {
        var candidateTypeNames = new[]
        {
            "Game.Core.Contracts.Save.RunMetadata",
            "Game.Core.Contracts.Save.RunStartMetadata",
            "Game.Core.Contracts.Save.ContinueMetadata",
        };

        var assemblies = AppDomain.CurrentDomain
            .GetAssemblies()
            .Where(assembly => !assembly.IsDynamic)
            .ToList();

        if (!assemblies.Any(assembly => string.Equals(assembly.GetName().Name, "Game.Core", StringComparison.OrdinalIgnoreCase)))
        {
            try
            {
                assemblies.Add(Assembly.Load("Game.Core"));
            }
            catch
            {
            }
        }

        foreach (var assembly in assemblies)
        {
            foreach (var candidateTypeName in candidateTypeNames)
            {
                var candidate = assembly.GetType(candidateTypeName, throwOnError: false, ignoreCase: false);
                if (candidate is not null)
                {
                    return candidate;
                }
            }
        }

        return null;
    }

    private static string GetJsonFieldName(PropertyInfo property)
    {
        var attribute = property.GetCustomAttribute<JsonPropertyNameAttribute>();
        return attribute is null ? ToSnakeCase(property.Name) : attribute.Name;
    }

    private static string ToSnakeCase(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        var chars = value
            .SelectMany((current, index) => char.IsUpper(current) && index > 0
                ? new[] { '_', char.ToLowerInvariant(current) }
                : new[] { char.ToLowerInvariant(current) })
            .ToArray();
        return new string(chars);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root.");
    }

    private sealed class SaveServiceSandbox : IDisposable
    {
        private SaveServiceSandbox(string rootPath)
        {
            RootPath = rootPath;
        }

        public string RootPath { get; }

        public static SaveServiceSandbox Create()
        {
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task0026-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(RootPath))
                {
                    Directory.Delete(RootPath, true);
                }
            }
            catch
            {
            }
        }
    }

    private sealed class NoOpDataStore : IDataStore
    {
        public Task SaveAsync(string key, string json)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.SaveAsync.");
        }

        public Task<string?> LoadAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.LoadAsync.");
        }

        public Task DeleteAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.DeleteAsync.");
        }
    }
}
