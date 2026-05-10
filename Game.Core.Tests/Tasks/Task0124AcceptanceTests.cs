using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0124AcceptanceTests
{
    private const int TaskmasterId = 124;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string UiBindingsPath = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0124AcceptanceTests.cs";

    [Fact]
    public void ShouldReferenceTask0124Evidence_WhenAcceptanceUsesRefs()
    {
        foreach (var taskFile in new[] { TasksBackPath, TasksGameplayPath })
        {
            var task = ReadTaskNode(taskFile, TaskmasterId);
            var acceptance = ReadAcceptance(task);
            acceptance.Length.Should().BeGreaterOrEqualTo(6);

            foreach (var line in acceptance)
            {
                var refs = ParseRefs(line);
                refs.Should().Contain(UiBindingsPath);
                refs.Should().Contain(ThisTaskTestRef);
            }
        }
    }

    [Fact]
    public void ShouldDescribeDragAndClickSharedResolution_WhenAcceptanceIsTask124()
    {
        foreach (var taskFile in new[] { TasksBackPath, TasksGameplayPath })
        {
            var task = ReadTaskNode(taskFile, TaskmasterId);
            var acceptance = ReadAcceptance(task);
            var first = acceptance[0];
            first.Should().Contain("drag-to-play");
            first.Should().Contain("click-to-play");
            first.Should().Contain("same CombatService-backed runtime card-play path");
        }
    }

    [Fact]
    public void ShouldEnforceEmptyStatePrerequisite_WhenRuntimeOrHandMissing()
    {
        foreach (var taskFile in new[] { TasksBackPath, TasksGameplayPath })
        {
            var task = ReadTaskNode(taskFile, TaskmasterId);
            var acceptance = ReadAcceptance(task);
            var emptyState = acceptance[3];
            emptyState.Should().Contain("Until both combat runtime and hand state are available");
            emptyState.Should().Contain("if either prerequisite is missing");
            emptyState.Should().Contain("playable controls or targeting preview are shown, acceptance fails");
        }
    }

    private static string[] ReadAcceptance(JsonElement taskNode)
    {
        return taskNode.GetProperty("acceptance")
            .EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .ToArray();
    }

    private static string[] ParseRefs(string acceptanceLine)
    {
        var refsIndex = acceptanceLine.IndexOf("Refs:", System.StringComparison.Ordinal);
        refsIndex.Should().BeGreaterOrEqualTo(0);
        return acceptanceLine[(refsIndex + "Refs:".Length)..]
            .Split(' ', System.StringSplitOptions.RemoveEmptyEntries | System.StringSplitOptions.TrimEntries)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
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
        task.ValueKind.Should().NotBe(JsonValueKind.Undefined);
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(System.AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }
            current = current.Parent;
        }
        throw new DirectoryNotFoundException("Unable to locate repository root containing NewRouge.sln.");
    }
}
