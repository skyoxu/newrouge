using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0102WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 102;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0102WorkflowSelectionEvidenceTests.cs";
    private const string AuditDocRef = "docs/gdd/t1-t69-m1-wiring-audit.md";

    // ACC:T102.1
    // ACC:T102.2
    // ACC:T102.3
    // ACC:T102.4
    // ACC:T102.5
    [Fact]
    public void ShouldKeepTask102AsGovernanceOnlySizingAudit_WhenReadingTask102Metadata()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        var labels = ReadStringArray(task, "labels");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(5);
        acceptance.Should().OnlyContain(line => line.Contains("Refs: " + ThisTaskTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("T70-T101", StringComparison.Ordinal)
            && line.Contains("identified and split", StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("governance audit findings", StringComparison.Ordinal)
            && line.Contains("does not deliver gameplay feature implementation", StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("has not been selected", StringComparison.OrdinalIgnoreCase)
            && line.Contains("no implementation work advances", StringComparison.OrdinalIgnoreCase));

        testRefs.Should().ContainSingle().Which.Should().Be(ThisTaskTestRef);
        evidenceRefs.Should().Contain(AuditDocRef);
        labels.Should().Contain("chapter6");
        labels.Should().Contain("sizing");

        var description = task.TryGetProperty("description", out var descriptionNode) ? descriptionNode.GetString() ?? string.Empty : string.Empty;
        description.ToLowerInvariant().Should().Contain("governance");
        description.Should().Contain("Chapter 6 run");
    }

    // ACC:T102.1-T102.4
    [Fact]
    public void ShouldRequireAuditDocumentToMentionTask102SizingDecisionScope_WhenValidatingGovernanceEvidenceCarrier()
    {
        var content = ReadRepoText(AuditDocRef);

        content.Should().Contain("T70-T101");
        content.Should().Contain("Chapter 6");
        content.ToLowerInvariant().Should().Contain("audit");
        content.Should().Contain("T102-T104");
        content.Should().Contain("T103");
        content.Should().Contain("T104");
        content.Should().Contain("T108");
    }

    // ACC:T102.2
    [Fact]
    public void ShouldExposeSplitGovernanceTasksForPostT70SizingClosure_WhenReadingTaskViews()
    {
        var splitTaskIds = new[] { 103, 104, 108 };
        var backTasks = ReadTaskViewArray(TasksBackPath).EnumerateArray().ToArray();

        foreach (var splitId in splitTaskIds)
        {
            var task = backTasks.SingleOrDefault(node => TryReadTaskmasterId(node, out var id) && id == splitId);
            task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={splitId} must exist in tasks_back for sizing split governance.");

            var labels = ReadStringArray(task, "labels");
            labels.Should().Contain("workflow");

            var acceptance = ReadStringArray(task, "acceptance");
            acceptance.Length.Should().BeGreaterThan(0);
            acceptance.Any(line =>
                    line.Contains("separate", StringComparison.OrdinalIgnoreCase)
                    || line.Contains("split", StringComparison.OrdinalIgnoreCase))
                .Should().BeTrue($"taskmaster_id={splitId} should keep split/separate governance language.");
        }
    }

    // ACC:T102.4
    [Fact]
    public void ShouldKeepTask102AsGovernanceTaskWithoutGameplayLayer_WhenReadingTaskLayerAndLabels()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var layer = task.TryGetProperty("layer", out var layerNode) ? layerNode.GetString() ?? string.Empty : string.Empty;
        var labels = ReadStringArray(task, "labels");

        layer.Should().Be("docs");
        labels.Should().NotContain("combat");
        labels.Should().NotContain("runtime");
        labels.Should().Contain("workflow");
        labels.Should().Contain("sizing");
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var task = ReadTaskViewArray(taskFilePath)
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static JsonElement ReadTaskViewArray(string taskFilePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        return JsonDocument.Parse(document.RootElement.GetRawText()).RootElement.Clone();
    }

    private static bool TryReadTaskmasterId(JsonElement node, out int taskmasterId)
    {
        taskmasterId = -1;
        if (!node.TryGetProperty("taskmaster_id", out var idNode) || idNode.ValueKind != JsonValueKind.Number)
        {
            return false;
        }

        taskmasterId = idNode.GetInt32();
        return true;
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

    private static string ReadRepoText(string repoRelativePath)
    {
        var root = FindRepositoryRoot();
        var absolutePath = Path.Combine(root, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required evidence file missing: {repoRelativePath}");
        return File.ReadAllText(absolutePath);
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
