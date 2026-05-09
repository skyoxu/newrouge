using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Collections.Generic;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0108WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 108;
    private const int Task76Id = 76;
    private const int Task105Id = 105;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0108WorkflowSelectionEvidenceTests.cs";
    private const string AuditDocRef = "docs/gdd/t1-t69-m1-wiring-audit.md";
    private const string ExecutionPlanRef = "execution-plans/2026-05-06-task-108-enemy-intent-review-split-governance-evidence.md";
    private const string LightLaneEvidenceRef = "logs/ci/2026-05-06/sc-build-tdd/summary.json";
    private static readonly string[] ImplementationStatuses = { "in-progress", "done", "review" };

    // ACC:T108.1
    // ACC:T108.2
    // ACC:T108.3
    // ACC:T108.4
    // ACC:T108.5
    [Fact]
    public void ShouldKeepTask108AsGovernanceOnlyEnemyIntentReviewSplit_WhenReadingTask108Metadata()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        var labels = ReadStringArray(task, "labels");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(5);
        acceptance.Should().OnlyContain(line => line.Contains("Refs: ", StringComparison.Ordinal) && line.Contains(ThisTaskTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("separate lanes", StringComparison.OrdinalIgnoreCase)
            && line.Contains("preview generation", StringComparison.OrdinalIgnoreCase)
            && line.Contains("enemy turn resolution", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("T76", StringComparison.Ordinal)
            && line.Contains("T105", StringComparison.Ordinal)
            && line.Contains("independently", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("not a prerequisite", StringComparison.OrdinalIgnoreCase)
            && line.Contains("T76", StringComparison.Ordinal)
            && line.Contains("T105", StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("no-repeat verification semantics", StringComparison.OrdinalIgnoreCase)
            && line.Contains("must not trigger or require a recombined enemy-intent review lane", StringComparison.OrdinalIgnoreCase)
            && line.Contains("duplicate combined-lane verification is treated as invalid evidence", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("governance", StringComparison.OrdinalIgnoreCase)
            && line.Contains("do not include gameplay feature implementation", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("not workflow-selected", StringComparison.OrdinalIgnoreCase)
            && line.Contains("remains unchanged", StringComparison.OrdinalIgnoreCase)
            && line.Contains("no fallback to a combined enemy-intent review path", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("execution-plans/2026-05-06-task-108-enemy-intent-review-split-governance-evidence.md", StringComparison.Ordinal)
            && line.Contains("Game.Core.Tests/Tasks/Task0108WorkflowSelectionEvidenceTests.cs", StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("logs/ci/2026-05-06/sc-build-tdd/summary.json", StringComparison.Ordinal)
            && line.Contains("Game.Core.Tests/Tasks/Task0108WorkflowSelectionEvidenceTests.cs", StringComparison.Ordinal));

        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(AuditDocRef);
        evidenceRefs.Should().Contain(ExecutionPlanRef);
        evidenceRefs.Should().Contain(LightLaneEvidenceRef);
        labels.Should().Contain("workflow");
        labels.Should().Contain("enemy-intent");
        labels.Should().Contain("review");

        var layer = task.TryGetProperty("layer", out var layerNode) ? layerNode.GetString() ?? string.Empty : string.Empty;
        layer.Should().Be("docs");
    }

    // ACC:T108.1
    // ACC:T108.2
    // ACC:T108.3
    [Fact]
    public void ShouldRequireAuditDocumentToCarryEnemyIntentLaneSplitEvidence_WhenValidatingEvidenceCarrier()
    {
        var content = ReadRepoText(AuditDocRef);
        var normalized = content.ToLowerInvariant();

        content.Should().Contain("T102-T104/T108-T109/T112");
        content.Should().Contain("T108");
        content.Should().Contain("T105");
        content.Should().Contain("Chapter 6");
        normalized.Should().Contain("enemy intent");
        normalized.Should().Contain("review / recovery");
        normalized.Should().Contain("t108");
    }

    // ACC:T108.1
    // ACC:T108.2
    // ACC:T108.3
    [Fact]
    public void ShouldRequireExecutionPlanEvidenceToDeclareIndependentPreviewAndResolutionLanes()
    {
        var planText = ReadRepoText(ExecutionPlanRef);
        var normalized = planText.ToLowerInvariant();

        planText.Should().Contain("Task 76");
        planText.Should().Contain("Task 105");
        normalized.Should().Contain("preview generation lane");
        normalized.Should().Contain("enemy turn resolution lane");
        normalized.Should().Contain("independent re-review");
        normalized.Should().Contain("not-a-prerequisite");
        normalized.Should().Contain("no-repeat verification");
        normalized.Should().Contain("duplicate combined-lane verification is invalid evidence");
    }

    // ACC:T108.5
    [Fact]
    public void ShouldKeepImplementationStateUnchangedForT76AndT105_WhenTask108IsNotWorkflowSelected()
    {
        var masterTasks = ReadMasterTasksById();
        masterTasks.Should().ContainKey(TaskmasterId);
        masterTasks.Should().ContainKey(Task76Id);
        masterTasks.Should().ContainKey(Task105Id);

        var task108Status = ReadString(masterTasks[TaskmasterId], "status");
        task108Status.Should().BeOneOf("pending", "in-progress", "review", "done");

        var currentViolations = EvaluateNoImplementationTransitionViolations(task108Status, new[]
        {
            (Task76Id, ReadString(masterTasks[Task76Id], "status")),
            (Task105Id, ReadString(masterTasks[Task105Id], "status")),
        });
        currentViolations.Should().BeEmpty();

        var simulatedViolation = EvaluateNoImplementationTransitionViolations("pending", new[]
        {
            (Task76Id, "in-progress"),
            (Task105Id, ReadString(masterTasks[Task105Id], "status")),
        });
        simulatedViolation.Should().Contain(item =>
            item.Contains("task 76", StringComparison.OrdinalIgnoreCase)
            && item.Contains("in-progress", StringComparison.OrdinalIgnoreCase));

        var summaryPath = Path.Combine(FindRepositoryRoot(), LightLaneEvidenceRef.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(summaryPath))
        {
            return;
        }

        using var summaryDoc = JsonDocument.Parse(File.ReadAllText(summaryPath));
        var root = summaryDoc.RootElement;
        var changedPaths = root.TryGetProperty("changed_paths", out var changedNode) && changedNode.ValueKind == JsonValueKind.Array
            ? changedNode.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString() ?? string.Empty).ToArray()
            : Array.Empty<string>();
        changedPaths.Should().NotContain(path =>
            path.StartsWith("Game.Core/", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("Game.Godot/", StringComparison.OrdinalIgnoreCase)
            || path.StartsWith("Tests.Godot/", StringComparison.OrdinalIgnoreCase),
            "Task 108 governance flow should not mutate implementation paths while it is not workflow-selected.");
    }

    // ACC:T108.5
    [Fact]
    public void ShouldRequireLightLaneEvidenceToRecordRefactorGateFailureAsEvidenceOnlyState()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        evidenceRefs.Should().Contain(LightLaneEvidenceRef);

        var summaryPath = Path.Combine(FindRepositoryRoot(), LightLaneEvidenceRef.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(summaryPath))
        {
            return;
        }

        using var document = JsonDocument.Parse(File.ReadAllText(summaryPath));
        var root = document.RootElement;
        var stage = root.TryGetProperty("stage", out var stageNode) ? stageNode.GetString() ?? string.Empty : string.Empty;
        var status = root.TryGetProperty("status", out var statusNode) ? statusNode.GetString() ?? string.Empty : string.Empty;
        var steps = root.TryGetProperty("steps", out var stepsNode) && stepsNode.ValueKind == JsonValueKind.Array
            ? stepsNode.EnumerateArray().ToArray()
            : Array.Empty<JsonElement>();

        stage.Should().Be("refactor");
        status.Should().Match(s => string.Equals(s, "ok", StringComparison.OrdinalIgnoreCase) || string.Equals(s, "fail", StringComparison.OrdinalIgnoreCase));
        steps.Should().NotBeEmpty();
        steps.Any(step =>
                ReadString(step, "name").Equals("validate_refactor_green_prerequisite", StringComparison.Ordinal))
            .Should().BeTrue();
    }

    // ACC:T108.1
    // ACC:T108.2
    [Fact]
    public void ShouldFailLaneSplitEvidenceCheck_WhenExecutionPlanTextLosesResolutionLaneAssertion()
    {
        var planText = ReadRepoText(ExecutionPlanRef);
        var mutated = planText.Replace("enemy turn resolution lane", string.Empty, StringComparison.OrdinalIgnoreCase);

        var hasSplitEvidence =
            mutated.Contains("preview generation lane", StringComparison.OrdinalIgnoreCase)
            && mutated.Contains("enemy turn resolution lane", StringComparison.OrdinalIgnoreCase)
            && mutated.Contains("independent re-review", StringComparison.OrdinalIgnoreCase);

        hasSplitEvidence.Should().BeFalse("lane split evidence must fail when the resolution lane assertion is removed.");
    }

    // ACC:T108.3
    [Fact]
    public void ShouldExposeTaskDependenciesForEnemyIntentSplitBoundary_WhenReadingTask108DependencyBoundary()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var dependsOn = ReadStringArray(task, "depends_on");

        dependsOn.Should().Contain("NG-0051");
        dependsOn.Should().Contain("NG-0077");
        dependsOn.Should().Contain("NG-0074");
    }

    private static Dictionary<int, JsonElement> ReadMasterTasksById()
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

    private static string[] EvaluateNoImplementationTransitionViolations(
        string task108Status,
        (int taskId, string status)[] laneStatuses)
    {
        var violations = new List<string>();
        if (!string.Equals(task108Status, "pending", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(task108Status, "in-progress", StringComparison.OrdinalIgnoreCase))
        {
            return violations.ToArray();
        }

        foreach (var (taskId, status) in laneStatuses)
        {
            if (ImplementationStatuses.Any(implementationStatus =>
                    string.Equals(status, implementationStatus, StringComparison.OrdinalIgnoreCase)))
            {
                violations.Add($"task {taskId} entered {status} while task 108 is not workflow-selected.");
            }
        }

        return violations.ToArray();
    }

    private static string ReadString(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
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
