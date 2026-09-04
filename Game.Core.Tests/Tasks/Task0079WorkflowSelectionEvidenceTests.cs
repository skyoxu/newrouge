using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0079WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 79;
    private const string StrictEvidenceEnvName = "TASK0079_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-v2-batch/shards/shard-001-t70-89/summary.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0079WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-79";

    // ACC:T79.6
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldBindWorkflowSelectionAcceptanceToTask79EvidenceAndTask79TestRef_WhenReadingTaskViews(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptanceLine = ReadAcceptanceLine(task);
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        acceptanceLine.Should().Contain("workflow selection of T79 is recorded first");
        acceptanceLine.Should().Contain("Refs:");
        acceptanceLine.Should().Contain(ThisTaskTestRef);
        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(WorkflowSelectionSummaryRef);
    }

    // ACC:T79.6
    [Fact]
    public void ShouldRequireSelectionRunEventBeforeImplementationEvidence_WhenValidatingTask79WorkflowGovernanceOrder()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("79");

        var summaryPath = latestIndex.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(summaryPath!).Should().BeTrue("workflow selection evidence summary must exist in local pipeline artifacts");

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection order must be verifiable from run-events evidence");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");
    }

    // ACC:T79.6
    [Fact]
    public void ShouldRejectImplementationClaim_WhenSelectionRunEventIsRemovedForTask79()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();

        var withoutSelection = runEvents.Where(record => !IsSelectionEvent(record)).ToArray();
        withoutSelection.Should().NotBeEmpty("negative case should keep implementation events while removing selection events");
        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "workflow selection record is mandatory and cannot be inferred when run events miss it");
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
            .Single(line => line.Contains("workflow selection of T79 is recorded first", StringComparison.Ordinal));
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

    private static bool TryResolveLatestPipelineIndexPath(out string latestIndexPath, out string reason)
    {
        var root = FindRepositoryRoot();
        var ciRoot = Path.Combine(root, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            latestIndexPath = string.Empty;
            reason = $"missing logs/ci root: {ciRoot}";
            return false;
        }

        latestIndexPath = Directory
            .EnumerateFiles(ciRoot, "latest.json", SearchOption.AllDirectories)
            .Where(path => path.Contains(PipelineTaskPrefix, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(path => File.GetLastWriteTimeUtc(path))
            .FirstOrDefault() ?? string.Empty;

        if (string.IsNullOrWhiteSpace(latestIndexPath))
        {
            reason = "missing pipeline latest.json for task 79 under logs/ci/<date>/sc-review-pipeline-task-79*/latest.json";
            return false;
        }

        reason = string.Empty;
        return true;
    }

    private static void EnsurePipelineEvidenceOrSkip(string reason)
    {
        if (!ShouldRequirePipelineEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0079 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0079_GATE_EVIDENCE_REQUIRED=0 to suppress, or =1 to force this check in infrastructure-only runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (!string.IsNullOrWhiteSpace(raw))
        {
            if (raw.Equals("0", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("false", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("no", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("off", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            if (raw.Equals("1", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("on", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        // Auto-mode: require only when task-79 pipeline artifacts are present locally.
        // This keeps generic CI green while still enforcing governance checks in task-scoped runs.
        return TryResolveLatestPipelineIndexPath(out _, out _);
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

        var isStepTerminalEvent = string.Equals(record.EventName, "step_completed", StringComparison.Ordinal)
                                  || string.Equals(record.EventName, "step_failed", StringComparison.Ordinal);
        if (!isStepTerminalEvent)
        {
            return false;
        }

        return string.Equals(record.StepName, "sc-test", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-acceptance-check", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-llm-review", StringComparison.Ordinal);
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
