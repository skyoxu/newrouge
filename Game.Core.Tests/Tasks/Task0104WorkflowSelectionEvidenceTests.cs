using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0104WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 104;
    private const int Task90Id = 90;
    private const int Task100Id = 100;
    private const int Task101Id = 101;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0104WorkflowSelectionEvidenceTests.cs";
    private const string AuditDocRef = "docs/gdd/t1-t69-m1-wiring-audit.md";
    private static readonly string[] ImplementationStatuses = { "in-progress", "done", "review" };

    // ACC:T104.1
    // ACC:T104.2
    // ACC:T104.3
    // ACC:T104.4
    // ACC:T104.5
    [Fact]
    public void ShouldKeepTask104AsGovernanceOnlyCombatRuleReviewSplit_WhenReadingTask104Metadata()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        var labels = ReadStringArray(task, "labels");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(5);
        acceptance.Should().OnlyContain(line => line.Contains("Refs: " + ThisTaskTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("lane boundaries", StringComparison.OrdinalIgnoreCase)
            && line.Contains("core rule integration", StringComparison.OrdinalIgnoreCase)
            && line.Contains("AOE ordering", StringComparison.OrdinalIgnoreCase)
            && line.Contains("feedback reconciliation", StringComparison.OrdinalIgnoreCase)
            && line.Contains("input/output", StringComparison.OrdinalIgnoreCase)
            && line.Contains("review owner", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("T90", StringComparison.Ordinal)
            && line.Contains("T100", StringComparison.Ordinal)
            && line.Contains("T101", StringComparison.Ordinal)
            && line.Contains("separate deterministic closures", StringComparison.OrdinalIgnoreCase)
            && line.Contains("independent re-review records", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("CH06 narrow-loop scope", StringComparison.OrdinalIgnoreCase)
            && line.Contains("re-run", StringComparison.OrdinalIgnoreCase)
            && line.Contains("re-reviewed", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("remain evidence-only", StringComparison.OrdinalIgnoreCase)
            && line.Contains("not workflow-selected", StringComparison.OrdinalIgnoreCase)
            && line.Contains("must not transition T90, T100, or T101 into implementation execution", StringComparison.OrdinalIgnoreCase));

        testRefs.Should().ContainSingle().Which.Should().Be(ThisTaskTestRef);
        evidenceRefs.Should().Contain(AuditDocRef);
        labels.Should().Contain("workflow");
        labels.Should().Contain("combat");
        labels.Should().Contain("review");

        var layer = task.TryGetProperty("layer", out var layerNode) ? layerNode.GetString() ?? string.Empty : string.Empty;
        layer.Should().Be("docs");
    }

    // ACC:T104.2
    // ACC:T104.3
    [Fact]
    public void ShouldKeepStructuredLaneMappingAndChapter6NarrowLoopEvidence_WhenReadingTask104AcceptanceLines()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(5);

        var laneMappingLine = acceptance[1];
        laneMappingLine.Should().Contain("T90 to the core rule integration lane");
        laneMappingLine.Should().Contain("T100 to the AOE ordering lane");
        laneMappingLine.Should().Contain("T101 to the feedback reconciliation lane");
        laneMappingLine.Should().Contain("independent re-review records");

        var chapter6Line = acceptance[2];
        chapter6Line.Should().Contain("CH06 narrow-loop scope per lane");
        chapter6Line.Should().Contain("without forcing re-open or merge of the other two lanes");
        chapter6Line.Should().Contain("re-run");
        chapter6Line.Should().Contain("re-reviewed");
    }

    // ACC:T104.5
    [Fact]
    public void ShouldRejectImplementationTransitionForT90T100T101_WhenTask104IsNotWorkflowSelected()
    {
        var masterTasks = ReadMasterTasksById();
        masterTasks.Should().ContainKey(TaskmasterId);
        masterTasks.Should().ContainKey(Task90Id);
        masterTasks.Should().ContainKey(Task100Id);
        masterTasks.Should().ContainKey(Task101Id);

        var task104Status = ReadString(masterTasks[TaskmasterId], "status");
        task104Status.Should().BeOneOf("pending", "in-progress", "review", "done");

        var currentViolations = EvaluateNoImplementationTransitionViolations(task104Status, new[]
        {
            (Task90Id, ReadString(masterTasks[Task90Id], "status")),
            (Task100Id, ReadString(masterTasks[Task100Id], "status")),
            (Task101Id, ReadString(masterTasks[Task101Id], "status")),
        });
        currentViolations.Should().BeEmpty("no downstream implementation lane should transition through Task 104 when Task 104 is not workflow-selected.");

        var simulatedViolation = EvaluateNoImplementationTransitionViolations("pending", new[]
        {
            (Task90Id, "in-progress"),
            (Task100Id, ReadString(masterTasks[Task100Id], "status")),
            (Task101Id, ReadString(masterTasks[Task101Id], "status")),
        });
        simulatedViolation.Should().Contain(item =>
            item.Contains("task 90", StringComparison.OrdinalIgnoreCase)
            && item.Contains("in-progress", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T104.1
    // ACC:T104.2
    // ACC:T104.3
    [Fact]
    public void ShouldRequireAuditDocumentToCarryCombatRuleReviewNarrowingEvidence_WhenValidatingEvidenceCarrier()
    {
        var content = ReadRepoText(AuditDocRef);

        content.Should().Contain("T102-T104");
        content.Should().Contain("T103/T104");
        content.Should().Contain("combat rule promotion");
        content.Should().Contain("T90");
        content.Should().Contain("T100");
        content.Should().Contain("T101");
    }

    // ACC:T104.3
    [Fact]
    public void ShouldExposeCombatRulePromotionDependencies_WhenReadingTask104DependencyBoundary()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var dependsOn = ReadStringArray(task, "depends_on");

        dependsOn.Should().Contain("NG-0065");
        dependsOn.Should().Contain("NG-0072");
        dependsOn.Should().Contain("NG-0073");
        dependsOn.Should().Contain("NG-0074");
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

    private static System.Collections.Generic.Dictionary<int, JsonElement> ReadMasterTasksById()
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), TasksMasterPath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));

        var tasks = document.RootElement
            .GetProperty("master")
            .GetProperty("tasks")
            .EnumerateArray()
            .Where(node => node.TryGetProperty("id", out var idNode) && idNode.ValueKind == JsonValueKind.Number)
            .ToDictionary(
                node => node.GetProperty("id").GetInt32(),
                node => JsonDocument.Parse(node.GetRawText()).RootElement.Clone());

        return tasks;
    }

    private static string ReadString(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
    }

    private static string[] EvaluateNoImplementationTransitionViolations(
        string task104Status,
        (int taskId, string status)[] laneStatuses)
    {
        var violations = new System.Collections.Generic.List<string>();
        if (!string.Equals(task104Status, "pending", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(task104Status, "in-progress", StringComparison.OrdinalIgnoreCase))
        {
            return violations.ToArray();
        }

        foreach (var (taskId, status) in laneStatuses)
        {
            if (ImplementationStatuses.Any(implementationStatus =>
                    string.Equals(status, implementationStatus, StringComparison.OrdinalIgnoreCase)))
            {
                violations.Add($"task {taskId} entered {status} while task 104 is not workflow-selected.");
            }
        }

        return violations.ToArray();
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
