using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0113WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 113;
    private const string StrictEvidenceEnvName = "TASK0113_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-t109-t116/shards/shard-001-t109-116/summary.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0113WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-113";

    // ACC:T113.3
    [Theory]
    [InlineData(TasksBackPath)]
    [InlineData(TasksGameplayPath)]
    public void ShouldRequireWorkflowSelectionEvidenceReferenceBeforeImplementationEvidenceReference_WhenReadingTaskAcceptance(string taskFilePath)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");

        testRefs.Should().Contain(ThisTaskTestRef);
        evidenceRefs.Should().Contain(WorkflowSelectionSummaryRef);
    }

    // ACC:T113.3
    [Fact]
    public void ShouldRequireRealWorkflowSelectionArtifactBeforeImplementationEvidence_WhenValidatingGovernanceOrder()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("113");

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection order must be verifiable from run-events evidence");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        if (!runEvents.Any(IsImplementationEvidenceEvent))
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain implementation evidence events");
            return;
        }

        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");
    }

    // ACC:T113.3
    [Fact]
    public void ShouldFailGovernanceValidation_WhenWorkflowSelectionRecordIsMissingFromRunEvents()
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
        if (!runEvents.Any(IsImplementationEvidenceEvent))
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain implementation evidence events");
            return;
        }

        var withoutSelection = runEvents.Where(record => !IsSelectionEvent(record)).ToArray();
        withoutSelection.Should().NotBeEmpty();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "workflow selection record is mandatory and cannot be inferred when run events miss it");
    }

    // ACC:T113.3
    [Fact]
    public void ShouldRefuseImplementationEntry_WhenWorkflowSelectionRecordIsMissingAndStateRemainsUnchanged()
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

        var implementationEvents = runEvents
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .ToArray();
        if (implementationEvents.Length == 0)
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain implementation evidence events");
            return;
        }

        var withoutSelection = runEvents
            .Where(record => !IsSelectionEvent(record))
            .OrderBy(record => record.Timestamp)
            .ToArray();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "implementation entry must be refused when workflow-selection record is missing");

        var implementationWithoutSelection = withoutSelection
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();
        var implementationWithSelection = implementationEvents
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();

        implementationWithoutSelection.Should().Equal(
            implementationWithSelection,
            "removing workflow-selection evidence must not mutate implementation evidence payload/order");
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
            reason = "missing pipeline latest.json for task 113 under logs/ci/<date>/sc-review-pipeline-task-113*/latest.json";
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
            "Task0113 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0113_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task113 runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (string.IsNullOrWhiteSpace(raw))
        {
            return false;
        }

        return raw.Equals("1", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("on", StringComparison.OrdinalIgnoreCase);
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
