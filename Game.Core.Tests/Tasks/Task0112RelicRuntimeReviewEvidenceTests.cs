using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0112RelicRuntimeReviewEvidenceTests
{
    private const int TaskmasterId = 112;
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string AuditDocPath = "docs/gdd/t1-t69-m1-wiring-audit.md";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0112RelicRuntimeReviewEvidenceTests.cs";

    // ACC:T112.1
    [Fact]
    public void ShouldAllowIndependentReviewLanesForT99AndT110_WhenReadingTask112Acceptance()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var labels = ReadStringArray(task, "labels");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        acceptance.Should().Contain(line =>
            line.Contains("ACC:T112.1", StringComparison.Ordinal)
            && line.Contains("T99", StringComparison.Ordinal)
            && line.Contains("T110", StringComparison.Ordinal)
            && line.Contains("reviewed in a separate lane", StringComparison.OrdinalIgnoreCase));
        testRefs.Should().Contain(ThisTaskTestRef);
        labels.Should().Contain("workflow");
        labels.Should().Contain("relic");
        labels.Should().Contain("review");
        evidenceRefs.Should().NotBeEmpty("governance closure must be backed by explicit evidence refs");
        evidenceRefs.Should().Contain(AuditDocPath);
        ReadString(task, "layer").Should().Be("docs");
    }

    // ACC:T112.2
    [Fact]
    public void ShouldKeepCombatAndRunTriggerClosuresAsDistinctRuntimeLanes_WhenReadingTask112Acceptance()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");

        var laneRule = acceptance.Single(line =>
            line.Contains("ACC:T112.2", StringComparison.Ordinal)
            && line.Contains("independent relic runtime review lanes", StringComparison.OrdinalIgnoreCase)
            && line.Contains("combat trigger closure", StringComparison.OrdinalIgnoreCase)
            && line.Contains("run trigger closure", StringComparison.OrdinalIgnoreCase));
        var laneRuleLower = laneRule.ToLowerInvariant();
        laneRuleLower.Should().Contain("must not be used as approval or failure evidence for the other lane");
    }

    // ACC:T112.2
    [Fact]
    public void ShouldRequireDistinctLaneSemanticsInsideAuditEvidence_WhenReadingEvidenceRefs()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        evidenceRefs.Should().Contain(AuditDocPath);
        foreach (var path in evidenceRefs)
        {
            var fullPath = Path.Combine(FindRepositoryRoot(), path.Replace('/', Path.DirectorySeparatorChar));
            File.Exists(fullPath).Should().BeTrue($"evidence ref must exist: {path}");
        }

        var auditText = ReadRepoText(AuditDocPath).ToLowerInvariant();
        auditText.Should().Contain("t112");
        auditText.Should().Contain("t99");
        auditText.Should().Contain("t110");
        auditText.Should().Contain("review lane");
        auditText.Should().Contain("chapter 6");
    }

    // ACC:T112.3
    [Fact]
    public void ShouldTreatCompletionAsGovernanceWorkflowEvidenceOnly_WhenReadingTask112Acceptance()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");

        var closureRule = acceptance.Single(line =>
            line.Contains("ACC:T112.3", StringComparison.Ordinal)
            && line.Contains("completion evidence is restricted to governance and workflow artifacts", StringComparison.OrdinalIgnoreCase)
            && line.Contains("gameplay implementation artifacts alone must not close t112", StringComparison.OrdinalIgnoreCase));
        closureRule.ToLowerInvariant().Should().Contain("independent re-review readiness");
    }

    // ACC:T112.4
    [Fact]
    public void ShouldRequireWorkflowSelectionBeforeForwardImplementationState_WhenReadingTask112Acceptance()
    {
        var backTask = ReadTaskNode(TasksBackPath, TaskmasterId);
        var masterTask = ReadMasterTaskNode(TaskmasterId);
        var acceptance = ReadStringArray(backTask, "acceptance");

        acceptance.Should().Contain(line =>
            line.Contains("ACC:T112.4", StringComparison.Ordinal)
            && line.Contains("Until workflow explicitly selects T112", StringComparison.Ordinal)
            && line.Contains("must not advance t112 state", StringComparison.OrdinalIgnoreCase));
        ReadString(backTask, "status").Should().Be("pending");
        ReadString(masterTask, "status").Should().Be("pending");
    }

    // ACC:T112.4
    [Fact]
    public void ShouldRejectForwardProgressSignalWithoutWorkflowSelection_WhenTask112RemainsPending()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var snapshot = string.Join("\n", acceptance);
        var forwardProgressSignalPresent = snapshot.Contains("status=done", StringComparison.OrdinalIgnoreCase)
            || snapshot.Contains("implementation advanced", StringComparison.OrdinalIgnoreCase);

        forwardProgressSignalPresent.Should().BeFalse("Task112 acceptance must not claim forward implementation progress before workflow selection");
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

    private static JsonElement ReadMasterTaskNode(int taskId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), TasksMasterPath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .GetProperty("master")
            .GetProperty("tasks")
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskId);
        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"id={taskId} must exist in {TasksMasterPath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
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
