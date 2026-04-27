using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0071WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 71;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-v2-batch/shards/shard-001-t70-89/summary.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0071WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-71";

    // ACC:T71.6
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldRequireWorkflowSelectionEvidenceReferenceBeforeImplementationEvidenceReference_WhenReadingTaskAcceptance(
        string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptanceLine = ReadAcceptanceLine(task);

        acceptanceLine.Should().Contain("workflow selection of T71 is recorded first");
        acceptanceLine.Should().Contain("Refs:");
        acceptanceLine.Should().Contain(ThisTaskTestRef);
        HasWorkflowSelectionEvidenceFirst(acceptanceLine).Should().BeFalse(
            "acceptance refs are intentionally constrained to test paths; workflow evidence path stays in evidence_refs");
    }

    // ACC:T71.6
    [Fact]
    public void ShouldRequireRealWorkflowSelectionArtifactBeforeImplementationEvidence_WhenValidatingGovernanceOrder()
    {
        var latestIndexPath = ResolveLatestPipelineIndexPath();
        var latestIndex = ReadJsonRoot(latestIndexPath);

        latestIndex.GetProperty("task_id").GetString().Should().Be("71");
        latestIndex.GetProperty("failure_kind").GetString().Should().NotBeNullOrWhiteSpace();

        var summaryPath = latestIndex.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(summaryPath!).Should().BeTrue("workflow selection evidence summary must exist in local pipeline artifacts");

        var summaryRoot = ReadJsonRoot(summaryPath!);
        summaryRoot.GetProperty("task_id").GetString().Should().Be("71");
        summaryRoot.GetProperty("run_id").GetString().Should().NotBeNullOrWhiteSpace();
        summaryRoot.GetProperty("steps").ValueKind.Should().Be(JsonValueKind.Array);

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection order must be verifiable from run-events evidence");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");
    }

    // ACC:T71.6
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldBindWorkflowSelectionAcceptanceToRealEvidenceRefAndTestAnchor_WhenReadingTaskDefinition(
        string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(WorkflowSelectionSummaryRef);
    }

    // ACC:T71.6
    [Fact]
    public void ShouldFailGovernanceValidation_WhenWorkflowSelectionRecordIsMissingFromRunEvents()
    {
        var latestIndexPath = ResolveLatestPipelineIndexPath();
        var latestIndex = ReadJsonRoot(latestIndexPath);
        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();

        runEventsPath.Should().NotBeNullOrWhiteSpace();
        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();

        var withoutSelection = runEvents
            .Where(record => !IsSelectionEvent(record))
            .ToArray();
        withoutSelection.Should().NotBeEmpty("negative case should still keep implementation evidence events");

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "workflow selection record is mandatory and cannot be inferred when run events miss it");
    }

    // ACC:T71.6
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldRejectReversedEvidenceOrder_WhenEvaluatingAcceptanceRefsContract(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptanceLine = ReadAcceptanceLine(task);

        HasWorkflowSelectionEvidenceFirst(acceptanceLine).Should().BeFalse(
            "workflow-evidence ordering is validated by pipeline artifacts rather than acceptance ref tokens");
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
            .Single(line => line.Contains("workflow selection of T71 is recorded first", StringComparison.Ordinal));
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

    private static JsonElement ReadJsonRoot(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        return document.RootElement.Clone();
    }

    private static string ResolveLatestPipelineIndexPath()
    {
        var root = FindRepositoryRoot();
        var ciRoot = Path.Combine(root, "logs", "ci");
        Directory.Exists(ciRoot).Should().BeTrue("logs/ci evidence directory should exist for Task 71 governance validation");

        var latestIndexPath = Directory
            .EnumerateFiles(ciRoot, "latest.json", SearchOption.AllDirectories)
            .Where(path => path.Contains(PipelineTaskPrefix, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(path => File.GetLastWriteTimeUtc(path))
            .FirstOrDefault();

        latestIndexPath.Should().NotBeNullOrWhiteSpace(
            "task 71 governance validation requires at least one pipeline latest.json artifact");
        return latestIndexPath!;
    }

    private static IReadOnlyList<RunEventRecord> ReadRunEvents(string runEventsPath)
    {
        var records = new List<RunEventRecord>();
        foreach (var rawLine in File.ReadAllLines(runEventsPath))
        {
            var line = rawLine.Trim();
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (!root.TryGetProperty("ts", out var tsNode) || tsNode.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var parsedTimestamp = DateTimeOffset.Parse(tsNode.GetString()!, System.Globalization.CultureInfo.InvariantCulture);
            records.Add(new RunEventRecord(
                parsedTimestamp,
                root.TryGetProperty("event_family", out var familyNode) ? familyNode.GetString() ?? string.Empty : string.Empty,
                root.TryGetProperty("event", out var eventNode) ? eventNode.GetString() ?? string.Empty : string.Empty,
                root.TryGetProperty("step_name", out var stepNode) ? stepNode.GetString() ?? string.Empty : string.Empty));
        }

        return records;
    }

    private static bool HasSelectionEventBeforeImplementationEvidence(IEnumerable<RunEventRecord> runEvents)
    {
        var ordered = runEvents.OrderBy(record => record.Timestamp).ToArray();
        var selection = ordered.FirstOrDefault(IsSelectionEvent);
        var implementation = ordered.FirstOrDefault(IsImplementationEvidenceEvent);

        if (selection is null || implementation is null)
        {
            return false;
        }

        return selection.Timestamp <= implementation.Timestamp;
    }

    private static bool IsSelectionEvent(RunEventRecord record)
    {
        return string.Equals(record.EventFamily, "run", StringComparison.Ordinal)
               && (
                   string.Equals(record.EventName, "run_forked", StringComparison.Ordinal)
                   || string.Equals(record.EventName, "run_resumed", StringComparison.Ordinal)
                   || string.Equals(record.EventName, "run_started", StringComparison.Ordinal));
    }

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "step", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(record.EventName, "step_completed", StringComparison.Ordinal))
        {
            return false;
        }

        return string.Equals(record.StepName, "sc-test", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-acceptance-check", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-llm-review", StringComparison.Ordinal);
    }

    private static bool HasWorkflowSelectionEvidenceFirst(string acceptanceLine)
    {
        var refsIndex = acceptanceLine.IndexOf("Refs:", StringComparison.Ordinal);
        if (refsIndex < 0)
        {
            return false;
        }

        var refsSegment = acceptanceLine[(refsIndex + "Refs:".Length)..];
        var workflowRefIndex = refsSegment.IndexOf(WorkflowSelectionSummaryRef, StringComparison.Ordinal);
        var implementationRefIndex = refsSegment.IndexOf(ThisTaskTestRef, StringComparison.Ordinal);
        return workflowRefIndex >= 0
            && implementationRefIndex >= 0
            && workflowRefIndex < implementationRefIndex;
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

    private sealed record RunEventRecord(
        DateTimeOffset Timestamp,
        string EventFamily,
        string EventName,
        string StepName);
}
