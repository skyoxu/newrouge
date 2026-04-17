using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0045AcceptanceTests
{
    private const int TaskmasterId = 45;
    private const string ThisGdTestRef = "Tests.Godot/tests/Tasks/test_task0045_acceptance.gd";
    private const string ThisCsTestRef = "Game.Core.Tests/Tasks/Task0045AcceptanceTests.cs";

    [Fact]
    public void ShouldIncludeTaskScopedRefsAndAcceptanceRefs_WhenReadingTask45Metadata()
    {
        using var metadata = ReadGameplayTaskMetadata();
        var root = metadata.RootElement;

        var testRefs = ReadStringArray(root, "test_refs");
        testRefs.Should().Contain(ThisGdTestRef);
        testRefs.Should().Contain(ThisCsTestRef);
        testRefs.Should().OnlyHaveUniqueItems();

        var acceptanceJoined = string.Join(Environment.NewLine, ReadStringArray(root, "acceptance"));
        acceptanceJoined.Should().Contain(ThisGdTestRef);
        acceptanceJoined.Should().Contain(ThisCsTestRef);
    }

    [Fact]
    public void ShouldKeepTask45AcceptanceAnchorsInGdUnitSuite_WhenAuditingTraceability()
    {
        var gdText = ReadRepoText("Tests.Godot", "tests", "Tasks", "test_task0045_acceptance.gd");

        gdText.Should().Contain("ACC:T45.1");
        gdText.Should().Contain("ACC:T45.2");
        gdText.Should().Contain("ACC:T45.3");
        gdText.Should().Contain("ACC:T45.4");
        gdText.Should().Contain("ACC:T45.5");
        gdText.Should().Contain("ACC:T45.6");
    }

    [Fact]
    public void ShouldMapDifficultyLockSemanticsToExecutableCoverage_WhenAuditingTask45()
    {
        using var metadata = ReadGameplayTaskMetadata();
        var acceptance = ReadStringArray(metadata.RootElement, "acceptance");

        acceptance.Should().Contain(item =>
            item.Contains("must keep", StringComparison.OrdinalIgnoreCase)
            && item.Contains("unchanged", StringComparison.OrdinalIgnoreCase),
            "Task 45 must explicitly require immutable HUD/summary difficulty during an active run.");

        var gdText = ReadRepoText("Tests.Godot", "tests", "Tasks", "test_task0045_acceptance.gd");
        gdText.Should().Contain("test_hud_difficulty_display_stays_constant_during_run_progression");
        gdText.Should().Contain("test_difficulty_display_remains_unchanged_through_flow_and_player_operations");
    }

    [Fact]
    public void ShouldAllowPreRunChangesAndRejectPostRunChanges_WhenDifficultyPolicyLocksOnRunStart()
    {
        var policy = new RunDifficultyLockPolicy(initialDifficultyId: 2);

        policy.IsLocked.Should().BeFalse();
        policy.SelectedDifficultyId.Should().Be(2);

        var changedBeforeLock = policy.SelectDifficulty(7);
        changedBeforeLock.Should().BeTrue();
        policy.SelectedDifficultyId.Should().Be(7);

        policy.Lock();
        policy.IsLocked.Should().BeTrue();

        var changedAfterLock = policy.SelectDifficulty(4);
        changedAfterLock.Should().BeFalse("difficulty must become read-only once the run is active");
        policy.SelectedDifficultyId.Should().Be(7);
    }

    private static JsonDocument ReadGameplayTaskMetadata()
    {
        var gameplayPath = Path.Combine(
            FindRepositoryRoot(),
            ".taskmaster",
            "tasks",
            "tasks_gameplay.json");
        var json = File.ReadAllText(gameplayPath);
        using var document = JsonDocument.Parse(json);
        var taskNode = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("taskmaster_id", out var idNode) &&
                idNode.ValueKind == JsonValueKind.Number &&
                idNode.GetInt32() == TaskmasterId);

        taskNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task 45 metadata must exist in tasks_gameplay.json");
        return JsonDocument.Parse(taskNode.GetRawText());
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement node, string fieldName)
    {
        if (!node.TryGetProperty(fieldName, out var field) || field.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        var values = new List<string>();
        foreach (var entry in field.EnumerateArray())
        {
            if (entry.ValueKind == JsonValueKind.String)
            {
                var value = entry.GetString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    values.Add(value);
                }
            }
        }

        return values;
    }

    private static string ReadRepoText(params string[] pathParts)
    {
        var path = Path.Combine(new[] { FindRepositoryRoot() }.Concat(pathParts).ToArray());
        File.Exists(path).Should().BeTrue($"Required file missing: {path}");
        return File.ReadAllText(path);
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
}
