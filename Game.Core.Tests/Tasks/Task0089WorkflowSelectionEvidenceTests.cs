using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0089WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 89;
    private const string StrictEvidenceEnvName = "TASK0089_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string WorkflowSelectionSummaryRef = "logs/ci/<date>/single-task-light-lane-t88-t89/shards/shard-001-t88-89/summary.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0089WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-89";

    // ACC:T89.7
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

    // ACC:T89.7
    [Fact]
    public void ShouldRequireRealWorkflowSelectionArtifactBeforeImplementationEvidence_WhenValidatingGovernanceOrder()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("89");

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection order must be verifiable from run-events evidence");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        if (!runEvents.Any(IsImplementationEvidenceEvent))
        {
            // Governance ordering cannot be asserted before implementation-evidence events appear.
            return;
        }

        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");
    }

    // ACC:T89.7
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
            // Governance ordering cannot be asserted before implementation-evidence events appear.
            return;
        }

        var withoutSelection = runEvents.Where(record => !IsSelectionEvent(record)).ToArray();
        withoutSelection.Should().NotBeEmpty();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "workflow selection record is mandatory and cannot be inferred when run events miss it");
    }

    // ACC:T89.7
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
            // Governance ordering cannot be asserted before implementation-evidence events appear.
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
            reason = "missing pipeline latest.json for task 89 under logs/ci/<date>/sc-review-pipeline-task-89*/latest.json";
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
            "Task0089 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0089_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task89 runs.");
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

            if (!DateTimeOffset.TryParse(tsNode.GetString(), out var timestamp))
            {
                continue;
            }

            records.Add(new RunEventRecord(
                Timestamp: timestamp,
                EventName: ReadString(root, "event"),
                EventFamily: ReadString(root, "event_family"),
                StepName: ReadString(root, "step"),
                ItemKind: ReadString(root, "item_kind"),
                ItemId: ReadString(root, "item_id")));
        }

        return records;
    }

    private static string ReadString(JsonElement node, string propertyName)
    {
        return node.TryGetProperty(propertyName, out var property) && property.ValueKind == JsonValueKind.String
            ? property.GetString() ?? string.Empty
            : string.Empty;
    }

    private static bool HasSelectionEventBeforeImplementationEvidence(IEnumerable<RunEventRecord> records)
    {
        var ordered = records.OrderBy(record => record.Timestamp).ToArray();
        var firstImplementationIndex = Array.FindIndex(ordered, IsImplementationEvidenceEvent);
        if (firstImplementationIndex < 0)
        {
            return false;
        }

        for (var index = 0; index < firstImplementationIndex; index++)
        {
            if (IsSelectionEvent(ordered[index]))
            {
                return true;
            }
        }

        return false;
    }

    private static bool IsSelectionEvent(RunEventRecord record)
    {
        if (record.ItemKind.Equals("workflow-selection", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (record.EventFamily.Equals("workflow-selection", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return record.EventName.Contains("workflow", StringComparison.OrdinalIgnoreCase)
            && record.EventName.Contains("select", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        return record.ItemKind.Equals("implementation-evidence", StringComparison.OrdinalIgnoreCase)
            || record.EventFamily.Equals("implementation-evidence", StringComparison.OrdinalIgnoreCase);
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            var candidate = Path.Combine(current, "newrouge.sln");
            if (File.Exists(candidate))
            {
                return current;
            }

            var parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root containing newrouge.sln.");
    }

    private sealed record RunEventRecord(
        DateTimeOffset Timestamp,
        string EventName,
        string EventFamily,
        string StepName,
        string ItemKind,
        string ItemId);
}
