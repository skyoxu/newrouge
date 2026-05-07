using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0109SettlementReviewLaneSplitEvidenceTests
{
    private const int TaskmasterId = 109;
    private const int Task91Id = 91;
    private const int Task107Id = 107;
    private const int Task113Id = 113;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0109SettlementReviewLaneSplitEvidenceTests.cs";
    private const string AuditDocRef = "docs/gdd/t1-t69-m1-wiring-audit.md";
    private const string ExecutionPlanRef = "execution-plans/2026-05-07-task-109-settlement-review-lane-split-governance-evidence.md";

    // ACC:T109.1
    // ACC:T109.2
    // ACC:T109.3
    // ACC:T109.4
    [Fact]
    public void ShouldKeepTask109AsGovernanceOnlySettlementReviewSplit_WhenReadingTask109Metadata()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        var labels = ReadStringArray(task, "labels");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(4);
        acceptance.Should().OnlyContain(line =>
            line.Contains("Refs: ", StringComparison.Ordinal)
            && line.Contains(ThisTaskTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("one-to-one mapping", StringComparison.OrdinalIgnoreCase)
            && line.Contains("T91", StringComparison.Ordinal)
            && line.Contains("owner-surface closure", StringComparison.OrdinalIgnoreCase)
            && line.Contains("T107", StringComparison.Ordinal)
            && line.Contains("reward/relic metadata", StringComparison.OrdinalIgnoreCase)
            && line.Contains("T113", StringComparison.Ordinal)
            && line.Contains("resume evidence", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("exactly one lane", StringComparison.OrdinalIgnoreCase)
            && line.Contains("must not combine", StringComparison.OrdinalIgnoreCase)
            && line.Contains("owner-surface", StringComparison.OrdinalIgnoreCase)
            && line.Contains("reward/relic metadata", StringComparison.OrdinalIgnoreCase)
            && line.Contains("resume evidence", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("governance", StringComparison.OrdinalIgnoreCase)
            && line.Contains("do not include gameplay feature implementation", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("not workflow-selected", StringComparison.OrdinalIgnoreCase)
            && line.Contains("implementation and status remain unchanged", StringComparison.OrdinalIgnoreCase)
            && line.Contains("must not record any forward-advancing implementation state", StringComparison.OrdinalIgnoreCase));

        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(AuditDocRef);
        evidenceRefs.Should().Contain(ExecutionPlanRef);
        labels.Should().Contain("workflow");
        labels.Should().Contain("settlement");
        labels.Should().Contain("review");

        ReadString(task, "layer").Should().Be("docs");
    }

    // ACC:T109.1
    // ACC:T109.2
    [Fact]
    public void ShouldRequireSettlementLaneSplitEvidenceInAuditAndExecutionPlan_WhenValidatingEvidenceCarrier()
    {
        var auditText = ReadRepoText(AuditDocRef);
        var auditLower = auditText.ToLowerInvariant();
        auditText.Should().Contain("T109");
        auditLower.Should().Contain("settlement");
        auditLower.Should().Contain("review / recovery");

        var planText = ReadRepoText(ExecutionPlanRef);
        var planLower = planText.ToLowerInvariant();
        planText.Should().Contain("Task 91");
        planText.Should().Contain("Task 107");
        planText.Should().Contain("Task 113");
        planLower.Should().Contain("one-to-one mapping");
        planLower.Should().Contain("owner-surface closure lane");
        planLower.Should().Contain("reward/relic metadata lane");
        planLower.Should().Contain("resume evidence lane");
        planLower.Should().Contain("exactly one lane");
        planLower.Should().Contain("must not combine");
        planLower.Should().Contain("independent re-review");
        planLower.Should().Contain("not-a-prerequisite");
    }

    // ACC:T109.4
    [Fact]
    public void ShouldKeepSettlementImplementationPending_WhenTask109IsNotWorkflowSelected()
    {
        var masterTasks = ReadMasterTasksById();
        masterTasks.Should().ContainKey(TaskmasterId);
        masterTasks.Should().ContainKey(Task91Id);
        masterTasks.Should().ContainKey(Task107Id);
        masterTasks.Should().ContainKey(Task113Id);

        ReadString(masterTasks[TaskmasterId], "status").Should().Be("pending");
        ReadString(masterTasks[Task91Id], "status").Should().Be("pending");
        ReadString(masterTasks[Task107Id], "status").Should().Be("pending");
        ReadString(masterTasks[Task113Id], "status").Should().Be("pending");
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

    private static string ReadString(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
    }

    private static System.Collections.Generic.Dictionary<int, JsonElement> ReadMasterTasksById()
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), TasksMasterPath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        return document.RootElement
            .GetProperty("master")
            .GetProperty("tasks")
            .EnumerateArray()
            .Where(node => node.TryGetProperty("id", out var idNode) && idNode.ValueKind == JsonValueKind.Number)
            .ToDictionary(
                node => node.GetProperty("id").GetInt32(),
                node => JsonDocument.Parse(node.GetRawText()).RootElement.Clone());
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
