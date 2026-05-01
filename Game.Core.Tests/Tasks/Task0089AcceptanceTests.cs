using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0089AcceptanceTests
{
    private const int TaskmasterId = 89;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string CombatScenePath = "Game.Godot/Scripts/UI/CombatScene.cs";

    // ACC:T89.1
    [Fact]
    public void ShouldPreferDataBackedEnemyRuntimeInstantiation_WhenEncounterIsPrepared()
    {
        var source = ReadRepositoryText(CombatScenePath);

        source.Should().Contain("TryGenerateEnemyIntentPreviewFromDataDefinitions", "enemy runtime setup should reuse data-backed definitions.");
        source.Should().Contain("ApplyDefaultM1EnemyStateIfEmpty", "fallback should only be a default guard when data-backed state is unavailable.");
    }

    // ACC:T89.2
    [Fact]
    public void ShouldKeepEncounterCreatedEnemyStateAuthoritative_WhenNoPlaceholderAuthoritySplitExists()
    {
        var source = ReadRepositoryText(CombatScenePath);

        source.Should().Contain("_enemyCombatById", "combat scene should maintain authoritative enemy runtime state collection.");
        source.Should().NotContain("PlaceholderEnemyRuntime", "task scope forbids introducing a second placeholder enemy authority model.");
    }

    // ACC:T89.3
    [Fact]
    public void ShouldKeepCurrentTargetOwnershipPath_WhenUsingDataBackedEnemyRuntime()
    {
        var source = ReadRepositoryText(CombatScenePath);

        source.Should().Contain("TrySelectEnemyTarget", "existing target selection ownership path must remain in use.");
        source.Should().Contain("GetAvailableEnemyTargetIdsForTest", "target-resolution evidence should remain on current runtime ownership path.");
    }

    // ACC:T89.4
    [Fact]
    public void ShouldKeepCurrentEnemyIntentOwnershipPath_WhenUsingDataBackedEnemyRuntime()
    {
        var source = ReadRepositoryText(CombatScenePath);

        source.Should().Contain("_enemyIntentByEnemy", "enemy-intent ownership should remain on current runtime map.");
        source.Should().Contain("ApplyEnemyIntentPreview", "intent preview ingestion should keep the current ownership path.");
    }

    // ACC:T89.5
    [Fact]
    public void ShouldKeepScopeLimitedToInstantiationAndAuthority_WhenDeferredFallbackBehaviorIsNotClaimed()
    {
        var source = ReadRepositoryText(CombatScenePath);

        source.Should().NotContain("InvalidEnemyDefinitionFallbackService", "invalid-definition visible fallback remains deferred to follow-up scope.");
        source.Should().NotContain("VisibleEnemyStatFallbackPresenter", "visible stat fallback ownership is out of T89 scope.");
    }

    // ACC:T89.6
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldReferenceTask0089TestsForEnemyRuntimeEvidence_WhenReadingTaskAcceptance(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var testRefs = ReadStringArray(task, "test_refs");
        var acceptance = ReadStringArray(task, "acceptance");

        testRefs.Should().Contain("Game.Core.Tests/Tasks/Task0089AcceptanceTests.cs");
        acceptance.Should().Contain(
            line => line.Contains("Game.Core.Tests/Tasks/Task0089AcceptanceTests.cs", StringComparison.Ordinal),
            "Task 89 acceptance refs should include the Task0089 acceptance evidence path even when refs are combined.");
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return property.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string ReadRepositoryText(string relativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required source file is missing: {relativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            var candidate = Path.Combine(current, "newrouge.sln");
            if (File.Exists(candidate))
            {
                return current;
            }

            var parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root containing newrouge.sln.");
    }
}
