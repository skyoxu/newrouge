using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0091WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 91;
    private const string StrictEvidenceEnvName = "TASK0091_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-t90-t95/shards/shard-001-t90-95/summary.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0091WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-91";

    // ACC:T91.5
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

    // ACC:T91.5
    [Fact]
    public void ShouldRequireRealWorkflowSelectionArtifactBeforeImplementationEvidence_WhenValidatingGovernanceOrder()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("91");

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
        if (!runEvents.Any(IsSelectionEvent))
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain workflow selection events");
            return;
        }

        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");
    }

    // ACC:T91.5
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

    // ACC:T91.5
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

        return property
            .EnumerateArray()
            .Where(entry => entry.ValueKind == JsonValueKind.String)
            .Select(entry => entry.GetString() ?? string.Empty)
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .ToArray();
    }

    private static JsonElement ReadJsonRoot(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        return JsonDocument.Parse(document.RootElement.GetRawText()).RootElement.Clone();
    }

    private static bool TryResolveLatestPipelineIndexPath(out string latestIndexPath, out string reason)
    {
        var repoRoot = FindRepositoryRoot();
        var logsRoot = Path.Combine(repoRoot, "logs", "ci");
        if (!Directory.Exists(logsRoot))
        {
            latestIndexPath = string.Empty;
            reason = "logs/ci directory does not exist";
            return false;
        }

        var latestCandidates = Directory
            .EnumerateFiles(logsRoot, "latest.json", SearchOption.AllDirectories)
            .Where(path => path.Replace('\\', '/').Contains($"/{PipelineTaskPrefix}/", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .ToArray();
        if (latestCandidates.Length == 0)
        {
            latestIndexPath = string.Empty;
            reason = $"no latest.json found under {PipelineTaskPrefix}";
            return false;
        }

        latestIndexPath = latestCandidates[0];
        reason = string.Empty;
        return true;
    }

    private static IReadOnlyList<RunEventRecord> ReadRunEvents(string runEventsPath)
    {
        var records = new List<RunEventRecord>();
        foreach (var line in File.ReadLines(runEventsPath))
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            records.Add(new RunEventRecord(
                ReadString(root, "event_family"),
                ReadString(root, "event_name"),
                ReadString(root, "step_name"),
                ReadTimestamp(root),
                root.GetRawText()));
        }

        return records;
    }

    private static bool HasSelectionEventBeforeImplementationEvidence(IEnumerable<RunEventRecord> runEvents)
    {
        var ordered = runEvents.OrderBy(record => record.Timestamp).ToArray();
        var firstImplementationIndex = Array.FindIndex(ordered, IsImplementationEvidenceEvent);
        if (firstImplementationIndex < 0)
        {
            return false;
        }

        return ordered
            .Take(firstImplementationIndex + 1)
            .Any(IsSelectionEvent);
    }

    private static bool IsSelectionEvent(RunEventRecord record) =>
        record.EventFamily.Equals("workflow-selection", StringComparison.OrdinalIgnoreCase)
        || record.StepName.Equals("workflow-selection", StringComparison.OrdinalIgnoreCase)
        || record.RawJson.Contains("\"workflow_selection\"", StringComparison.OrdinalIgnoreCase);

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        if (record.EventFamily.Equals("workflow-selection", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (record.EventFamily.Contains("build", StringComparison.OrdinalIgnoreCase)
            || record.EventFamily.Contains("review", StringComparison.OrdinalIgnoreCase)
            || record.EventFamily.Contains("acceptance", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return record.StepName.Equals("green", StringComparison.OrdinalIgnoreCase)
            || record.StepName.Equals("refactor", StringComparison.OrdinalIgnoreCase)
            || record.StepName.Equals("run-review-pipeline", StringComparison.OrdinalIgnoreCase);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, ".taskmaster", "tasks", "tasks_back.json");
            if (File.Exists(candidate))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Unable to locate repository root from test base directory.");
    }

    private static string ReadString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
    }

    private static DateTimeOffset ReadTimestamp(JsonElement root)
    {
        var candidates = new[] { "timestamp", "created_at", "time" };
        foreach (var field in candidates)
        {
            if (!root.TryGetProperty(field, out var value) || value.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var raw = value.GetString();
            if (DateTimeOffset.TryParse(raw, out var parsed))
            {
                return parsed;
            }
        }

        return DateTimeOffset.MinValue;
    }

    private static void EnsurePipelineEvidenceOrSkip(string reason)
    {
        if (!ShouldRequirePipelineEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0091 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0091_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task91 runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (!string.IsNullOrWhiteSpace(raw))
        {
            if (raw.Equals("0", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("false", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("off", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("no", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            if (raw.Equals("1", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("on", StringComparison.OrdinalIgnoreCase)
                || raw.Equals("yes", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private sealed record RunEventRecord(
        string EventFamily,
        string EventName,
        string StepName,
        DateTimeOffset Timestamp,
        string RawJson);
}
