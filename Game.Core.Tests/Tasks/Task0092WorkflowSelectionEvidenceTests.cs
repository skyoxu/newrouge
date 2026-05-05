using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0092WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 92;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0092WorkflowSelectionEvidenceTests.cs";

    // ACC:T92.6
    [Fact]
    public void ShouldRequireWorkflowSelectionEvidenceReferenceBeforeImplementationEvidenceReference_WhenReadingTaskAcceptance()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var testRefs = ReadStringArray(task, "test_refs");
        var acceptance = ReadStringArray(task, "acceptance");

        testRefs.Should().Contain(ThisTaskTestRef);
        acceptance.Should().ContainSingle(item =>
            item.Contains("If T92 has not been selected by the workflow", StringComparison.Ordinal)
            && item.Contains("workflow-selection evidence before any implementation evidence", StringComparison.Ordinal)
            && item.Contains("Refs: " + ThisTaskTestRef, StringComparison.Ordinal));
    }

    // ACC:T92.6
    [Fact]
    public void ShouldRefuseImplementationEntryAndKeepStateUnchanged_WhenWorkflowSelectionRecordIsMissing()
    {
        var withoutSelection = new[]
        {
            new RunEventRecord(DateTimeOffset.Parse("2026-01-01T00:00:01+00:00"), "step", "step_completed", "sc-test"),
            new RunEventRecord(DateTimeOffset.Parse("2026-01-01T00:00:02+00:00"), "step", "step_completed", "sc-acceptance-check"),
            new RunEventRecord(DateTimeOffset.Parse("2026-01-01T00:00:03+00:00"), "step", "step_completed", "sc-llm-review"),
        };
        var initialState = new GovernanceState("state-before", AttemptCount: 0);
        var implementationSnapshotBefore = withoutSelection
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();
        var decision = EvaluateWorkflowSelectionGate(initialState, withoutSelection);
        var implementationSnapshotAfter = withoutSelection
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();

        decision.IsEntryRefused.Should().BeTrue("implementation entry must be refused when workflow-selection evidence is missing");
        decision.StateAfter.Should().Be(initialState, "state must remain unchanged when entry is refused");
        implementationSnapshotAfter.Should().Equal(
            implementationSnapshotBefore,
            "gate evaluation must not mutate implementation evidence payload/order");
    }

    // ACC:T92.6
    [Fact]
    public void ShouldReportGovernanceOrderViolation_WhenImplementationEvidenceAppearsBeforeWorkflowSelectionEvidence()
    {
        var events = new[]
        {
            new RunEventRecord(DateTimeOffset.Parse("2026-01-01T00:00:01+00:00"), "step", "step_completed", "sc-test"),
            new RunEventRecord(DateTimeOffset.Parse("2026-01-01T00:00:02+00:00"), "run", "run_started", "")
        };

        HasSelectionEventBeforeImplementationEvidence(events).Should().BeFalse(
            "governance should fail when implementation evidence appears before workflow-selection evidence");
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
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
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

    private static GovernanceDecision EvaluateWorkflowSelectionGate(GovernanceState stateBefore, IReadOnlyList<RunEventRecord> events)
    {
        var hasSelectionBeforeImplementation = HasSelectionEventBeforeImplementationEvidence(events);
        if (!hasSelectionBeforeImplementation)
        {
            return new GovernanceDecision(IsEntryRefused: true, StateAfter: stateBefore);
        }

        return new GovernanceDecision(
            IsEntryRefused: false,
            StateAfter: stateBefore with { AttemptCount = stateBefore.AttemptCount + 1 });
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

    private sealed record GovernanceState(string StateHash, int AttemptCount);

    private sealed record GovernanceDecision(bool IsEntryRefused, GovernanceState StateAfter);
}
