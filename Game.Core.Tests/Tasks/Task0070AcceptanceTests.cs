using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0070AcceptanceTests
{
    private const string WorkflowSummaryTemplate = "logs/ci/<date>/single-task-light-lane-v2-batch/shards/shard-001-t70-89/summary.json";
    private const string ImplementationEvidenceTemplate = "logs/ci/<date>/task-0070.json";
    private static readonly string RepoRoot = ResolveRepoRoot();

    // ACC:T70.8
    [Fact]
    [Trait("acceptance", "ACC:T70.8")]
    public void ShouldRequireWorkflowSelectionEvidenceBeforeImplementationEvidence_WhenTask70GateIsAudited()
    {
        var backTask = ReadViewTask(".taskmaster/tasks/tasks_back.json");
        var gameplayTask = ReadViewTask(".taskmaster/tasks/tasks_gameplay.json");

        backTask.Acceptance[7].Should().Contain("before implementation evidence is accepted");
        gameplayTask.Acceptance[7].Should().Contain("before implementation evidence is accepted");
        backTask.Acceptance[7].Should().Contain("Refs: Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs");
        gameplayTask.Acceptance[7].Should().Contain("Refs: Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs");

        backTask.TestRefs.Should().Contain("Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs");
        gameplayTask.TestRefs.Should().Contain("Game.Core.Tests/Tasks/Task0070AcceptanceTests.cs");

        var workflowSummaryPath = ResolveLatestWorkflowSummaryPath();
        var implementationEvidencePath = ResolveLatestImplementationEvidencePath();

        File.Exists(workflowSummaryPath).Should().BeTrue("workflow-selection evidence must exist for Task 70 governance gate.");
        File.Exists(implementationEvidencePath).Should().BeTrue("implementation evidence must exist for Task 70 governance gate.");

        using var workflowSummary = JsonDocument.Parse(File.ReadAllText(workflowSummaryPath));
        using var implementationEvidence = JsonDocument.Parse(File.ReadAllText(implementationEvidencePath));

        ValidateWorkflowEvidenceOrder(workflowSummary, implementationEvidence);
    }

    // ACC:T70.8
    [Fact]
    [Trait("acceptance", "ACC:T70.8")]
    public void ShouldRejectTask70WorkflowEvidence_WhenTaskIdMismatches()
    {
        var mismatchedWorkflowSummary = BuildWorkflowSummaryDocumentWithTaskId(69);
        var implementationEvidence = BuildImplementationEvidenceDocument(70, "20260427-131517");

        var act = () => ValidateWorkflowEvidenceOrder(mismatchedWorkflowSummary, implementationEvidence);

        act.Should()
            .Throw<Xunit.Sdk.XunitException>()
            .WithMessage("*Expected workflowTaskId to be 70*");
    }

    // ACC:T70.8
    [Fact]
    [Trait("acceptance", "ACC:T70.8")]
    public void ShouldRejectTask70WorkflowEvidence_WhenRecordedAfterImplementationEvidence()
    {
        var workflowSummary = BuildWorkflowSummaryDocument("2026-04-27T14:30:00", 70);
        var implementationEvidence = BuildImplementationEvidenceDocument(70, "20260427-131517");

        var act = () => ValidateWorkflowEvidenceOrder(workflowSummary, implementationEvidence);

        act.Should()
            .Throw<Xunit.Sdk.XunitException>()
            .WithMessage("*before implementation evidence is accepted*");
    }

    private static ViewTask ReadViewTask(string viewRelativePath)
    {
        var absolute = Path.Combine(RepoRoot, viewRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolute).Should().BeTrue();
        using var doc = JsonDocument.Parse(File.ReadAllText(absolute));
        var task = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(item => item.TryGetProperty("taskmaster_id", out var taskId) && taskId.GetInt32() == 70);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, "taskmaster_id=70 must exist in " + viewRelativePath);

        var acceptance = task.GetProperty("acceptance").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        var testRefs = task.GetProperty("test_refs").EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
        return new ViewTask(acceptance, testRefs);
    }

    private static string ResolveRepoRoot()
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

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private sealed record ViewTask(string[] Acceptance, string[] TestRefs);

    private static string ResolveLatestWorkflowSummaryPath()
    {
        var logsRoot = Path.Combine(RepoRoot, "logs", "ci");
        Directory.Exists(logsRoot).Should().BeTrue();

        var candidate = Directory
            .EnumerateFiles(logsRoot, "summary.json", SearchOption.AllDirectories)
            .Where(path => path.Replace('\\', '/').EndsWith("/single-task-light-lane-v2-batch/shards/shard-001-t70-89/summary.json", StringComparison.Ordinal))
            .Where(path => WorkflowSummaryMatchesTask70(path))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();

        candidate.Should().NotBeNullOrWhiteSpace($"workflow evidence template {WorkflowSummaryTemplate} must resolve to a concrete file.");
        return candidate!;
    }

    private static string ResolveLatestImplementationEvidencePath()
    {
        var logsRoot = Path.Combine(RepoRoot, "logs", "ci");
        Directory.Exists(logsRoot).Should().BeTrue();

        var candidate = Directory
            .EnumerateFiles(logsRoot, "task-0070.json", SearchOption.AllDirectories)
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();

        candidate.Should().NotBeNullOrWhiteSpace($"implementation evidence template {ImplementationEvidenceTemplate} must resolve to a concrete file.");
        return candidate!;
    }

    private static void ValidateWorkflowEvidenceOrder(JsonDocument workflowSummary, JsonDocument implementationEvidence)
    {
        var workflowRoot = workflowSummary.RootElement.GetProperty("results")[0];
        var workflowTaskId = workflowRoot.GetProperty("task_id").GetInt32();
        workflowTaskId.Should().Be(70);

        var implementationTaskId = implementationEvidence.RootElement.GetProperty("task_id").GetInt32();
        implementationTaskId.Should().Be(70);

        var workflowStartedAtText = ResolveWorkflowStartedAt(workflowRoot);
        workflowStartedAtText.Should().NotBeNullOrWhiteSpace();

        var implementationTimestampText = implementationEvidence.RootElement.GetProperty("timestamp").GetString();
        implementationTimestampText.Should().NotBeNullOrWhiteSpace();

        var workflowStartedAt = DateTime.ParseExact(
            workflowStartedAtText!,
            "yyyy-MM-ddTHH:mm:ss",
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeLocal);
        var implementationTimestamp = DateTime.ParseExact(
            implementationTimestampText!,
            "yyyyMMdd-HHmmss",
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeLocal);

        workflowStartedAt.Should().BeOnOrBefore(implementationTimestamp,
            "workflow-selection evidence must be recorded before implementation evidence is accepted.");
    }

    private static string? ResolveWorkflowStartedAt(JsonElement workflowRoot)
    {
        if (workflowRoot.TryGetProperty("steps", out var stepsElement)
            && stepsElement.ValueKind == JsonValueKind.Array
            && stepsElement.GetArrayLength() > 0)
        {
            var firstStep = stepsElement[0];
            if (firstStep.TryGetProperty("started_at", out var startedAt)
                && startedAt.ValueKind == JsonValueKind.String)
            {
                return startedAt.GetString();
            }
        }

        if (workflowRoot.TryGetProperty("started_at", out var rootStartedAt)
            && rootStartedAt.ValueKind == JsonValueKind.String)
        {
            return rootStartedAt.GetString();
        }

        return null;
    }

    private static JsonDocument BuildWorkflowSummaryDocumentWithTaskId(int taskId)
    {
        return BuildWorkflowSummaryDocument("2026-04-27T13:00:00", taskId);
    }

    private static JsonDocument BuildWorkflowSummaryDocument(string startedAt, int taskId)
    {
        var payload = $$"""
{
  "results": [
    {
      "task_id": {{taskId}},
      "steps": [
        {
          "step": "preflight_extract_guard",
          "started_at": "{{startedAt}}"
        }
      ]
    }
  ]
}
""";
        return JsonDocument.Parse(payload);
    }

    private static JsonDocument BuildImplementationEvidenceDocument(int taskId, string timestamp)
    {
        var payload = $$"""
{
  "task_id": {{taskId}},
  "timestamp": "{{timestamp}}"
}
""";
        return JsonDocument.Parse(payload);
    }

    private static bool WorkflowSummaryMatchesTask70(string path)
    {
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            if (!doc.RootElement.TryGetProperty("results", out var results) || results.ValueKind != JsonValueKind.Array || results.GetArrayLength() == 0)
            {
                return false;
            }

            var first = results[0];
            if (!first.TryGetProperty("task_id", out var taskIdElement) || taskIdElement.ValueKind != JsonValueKind.Number)
            {
                return false;
            }

            return taskIdElement.GetInt32() == 70;
        }
        catch
        {
            return false;
        }
    }
}
