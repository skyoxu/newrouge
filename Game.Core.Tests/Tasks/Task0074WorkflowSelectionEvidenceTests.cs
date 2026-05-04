using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0074WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 74;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0074WorkflowSelectionEvidenceTests.cs";
    private const string WorkflowSummaryRef = "logs/ci/<date>/single-task-light-lane-v2-batch/shards/shard-001-t70-89/summary.json";

    // ACC:T74.7
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldBindWorkflowSelectionAcceptanceToTask74EvidenceAndTask74TestRef_WhenReadingTaskViews(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptanceLine = ReadAcceptanceLine(task);
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        acceptanceLine.Should().Contain("workflow explicitly selects T74");
        acceptanceLine.Should().Contain("Refs:");
        acceptanceLine.Should().Contain(ThisTaskTestRef);
        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(WorkflowSummaryRef);
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

    private static string ReadAcceptanceLine(JsonElement taskNode)
    {
        return taskNode.GetProperty("acceptance")
            .EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Single(line => line.Contains("workflow explicitly selects T74", StringComparison.Ordinal));
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

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
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
