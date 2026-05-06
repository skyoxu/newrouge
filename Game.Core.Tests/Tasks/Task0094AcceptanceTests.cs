using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0094AcceptanceTests
{
    private const int TaskmasterId = 94;
    private const string StrictEvidenceEnvName = "TASK0094_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksMasterPath = ".taskmaster/tasks/tasks.json";
    private const string SecurityHttpClientPath = "Game.Godot/Scripts/Security/SecurityHttpClient.cs";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0094AcceptanceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-94";

    // ACC:T94.1
    [Fact]
    public void ShouldValidateSignalContractDeterministically_WhenSecuritySignalDefinitionMatchesExpectedContract()
    {
        var source = ReadRepoText(SecurityHttpClientPath);
        var actual = ParseSignalContract(source);
        var expected = new ExpectedSignalContract(
            SignalName: "RequestBlocked",
            Parameters: new[]
            {
                new ExpectedSignalParameter("string", "reason"),
                new ExpectedSignalParameter("string", "url"),
            });

        var result = ValidateSignalContract(actual, expected);

        result.IsValid.Should().BeTrue();
        result.ErrorCode.Should().Be("none");
        result.FailureCategory.Should().Be("none");
    }

    // ACC:T94.2
    [Fact]
    public void ShouldExposeTask94InExecutableMainlineTaskViews_WhenReadingTaskMetadata()
    {
        var repoRoot = FindRepositoryRoot();
        var masterTask = ReadMasterTaskById(Path.Combine(repoRoot, TasksMasterPath.Replace('/', Path.DirectorySeparatorChar)), TaskmasterId);
        var backTask = ReadBackTaskByTaskmasterId(Path.Combine(repoRoot, TasksBackPath.Replace('/', Path.DirectorySeparatorChar)), TaskmasterId);

        masterTask.GetProperty("id").GetInt32().Should().Be(TaskmasterId);
        masterTask.GetProperty("title").GetString().Should().NotBeNullOrWhiteSpace();
        masterTask.GetProperty("details").GetString().Should().Contain(
            "Do not execute implementation until this task is selected by workflow.",
            "Task94 must be wired into the executable workflow-selection guardrail instead of backlog-only tracking");
        masterTask.GetProperty("testStrategy").GetString().Should().Contain(
            "deterministic",
            "mainline task metadata must require deterministic contract validation");

        backTask.GetProperty("taskmaster_exported").GetBoolean().Should().BeTrue("Task94 must be exported into executable task views");
        ReadStringArray(backTask, "acceptance").Length.Should().BeGreaterThan(0);
        ReadStringArray(backTask, "test_refs").Should().Contain(ThisTaskTestRef);
    }

    // ACC:T94.3
    [Fact]
    public void ShouldReportDeterministicFailureCode_WhenSignalContractIsIntentionallyDrifted()
    {
        var source = ReadRepoText(SecurityHttpClientPath);
        var actual = ParseSignalContract(source);
        var drifted = new ExpectedSignalContract(
            SignalName: "RequestBlocked",
            Parameters: new[]
            {
                new ExpectedSignalParameter("string", "reason"),
                new ExpectedSignalParameter("int", "url"),
            });

        var first = ValidateSignalContract(actual, drifted);
        var second = ValidateSignalContract(actual, drifted);

        first.IsValid.Should().BeFalse();
        first.ErrorCode.Should().Be("signal_parameter_type_mismatch");
        first.FailureCategory.Should().Be("contract-drift");

        second.IsValid.Should().Be(first.IsValid);
        second.ErrorCode.Should().Be(first.ErrorCode, "drift classification must be deterministic");
        second.FailureCategory.Should().Be(first.FailureCategory, "drift category must be deterministic");
    }

    // ACC:T94.5
    [Fact]
    public void ShouldRequireWorkflowSelectionRecordBeforeImplementationEvidence_WhenValidatingRunEventsOrdering()
    {
        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        latestIndex.GetProperty("task_id").GetString().Should().Be("94");

        var runEventsPath = latestIndex.GetProperty("run_events_path").GetString();
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue();

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();
        if (!runEvents.Any(IsImplementationEvidenceEvent))
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain implementation evidence events");
            return;
        }

        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection evidence must appear before implementation evidence events");

        var withoutSelection = runEvents
            .Where(record => !IsSelectionEvent(record))
            .OrderBy(record => record.Timestamp)
            .ToArray();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "without workflow selection records, implementation entry must be considered refused");

        var implementationWithSelection = runEvents
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();
        var implementationWithoutSelection = withoutSelection
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();

        implementationWithoutSelection.Should().Equal(
            implementationWithSelection,
            "removing workflow selection records should not mutate implementation evidence payload/order");
    }

    // ACC:T94.6
    [Fact]
    public void ShouldDeclareMachineReadableDeterministicFailureSemantics_WhenReadingTask94AcceptanceMetadata()
    {
        var repoRoot = FindRepositoryRoot();
        var backTask = ReadBackTaskByTaskmasterId(Path.Combine(repoRoot, TasksBackPath.Replace('/', Path.DirectorySeparatorChar)), TaskmasterId);
        var acceptanceItems = ReadStringArray(backTask, "acceptance");

        acceptanceItems.Should().Contain(item =>
                item.Contains("CI-consumable deterministic failure result", StringComparison.Ordinal)
                && item.Contains("stable error code/category", StringComparison.Ordinal),
            "Task94 acceptance must require machine-readable deterministic failure semantics for CI gating");
        acceptanceItems.Should().Contain(item =>
                item.Contains("canonical signal name plus expected argument shape/order", StringComparison.Ordinal)
                && item.Contains("not skip, not silent behavior change", StringComparison.Ordinal),
            "Task94 integration acceptance must forbid skip/silent semantics when validating signal-contract drift");
    }

    private static SignalContract ParseSignalContract(string source)
    {
        var delegateMatch = Regex.Match(
            source,
            @"\[Signal\]\s+public\s+delegate\s+void\s+(?<name>\w+)EventHandler\s*\((?<args>[^\)]*)\)\s*;",
            RegexOptions.Multiline);
        delegateMatch.Success.Should().BeTrue("SecurityHttpClient must define a [Signal] delegate contract.");

        var signalName = delegateMatch.Groups["name"].Value;
        var parameters = ParseParameters(delegateMatch.Groups["args"].Value);

        var emitMatch = Regex.Match(
            source,
            @"EmitSignal\(\s*SignalName\.(?<name>\w+)\s*,\s*(?<args>[^\)]*)\)",
            RegexOptions.Multiline);
        emitMatch.Success.Should().BeTrue("SecurityHttpClient must emit the signal via SignalName.");

        var emitName = emitMatch.Groups["name"].Value;
        var emitArgs = emitMatch.Groups["args"].Value
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToArray();

        return new SignalContract(signalName, parameters, emitName, emitArgs);
    }

    private static SignalParameter[] ParseParameters(string argsText)
    {
        var args = argsText
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(raw =>
            {
                var tokens = raw
                    .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
                tokens.Length.Should().BeGreaterThanOrEqualTo(2, $"Unexpected signal argument token shape: `{raw}`");
                return new SignalParameter(tokens[0], tokens[^1]);
            })
            .ToArray();

        return args;
    }

    private static SignalValidationResult ValidateSignalContract(SignalContract actual, ExpectedSignalContract expected)
    {
        if (!string.Equals(actual.SignalName, expected.SignalName, StringComparison.Ordinal))
        {
            return SignalValidationResult.Fail("signal_name_mismatch", "contract-drift");
        }

        if (actual.Parameters.Length != expected.Parameters.Length)
        {
            return SignalValidationResult.Fail("signal_arity_mismatch", "contract-drift");
        }

        for (var i = 0; i < expected.Parameters.Length; i += 1)
        {
            var expectedParameter = expected.Parameters[i];
            var actualParameter = actual.Parameters[i];

            if (!string.Equals(actualParameter.TypeName, expectedParameter.TypeName, StringComparison.OrdinalIgnoreCase))
            {
                return SignalValidationResult.Fail("signal_parameter_type_mismatch", "contract-drift");
            }

            if (!string.Equals(actualParameter.ParameterName, expectedParameter.ParameterName, StringComparison.Ordinal))
            {
                return SignalValidationResult.Fail("signal_parameter_name_mismatch", "contract-drift");
            }
        }

        if (!string.Equals(actual.EmitSignalName, expected.SignalName, StringComparison.Ordinal))
        {
            return SignalValidationResult.Fail("emit_signal_name_mismatch", "contract-drift");
        }

        if (actual.EmitArguments.Length != expected.Parameters.Length)
        {
            return SignalValidationResult.Fail("emit_signal_argument_arity_mismatch", "contract-drift");
        }

        for (var i = 0; i < expected.Parameters.Length; i += 1)
        {
            if (!string.Equals(actual.EmitArguments[i], expected.Parameters[i].ParameterName, StringComparison.Ordinal))
            {
                return SignalValidationResult.Fail("emit_signal_argument_mismatch", "contract-drift");
            }
        }

        return SignalValidationResult.Ok();
    }

    private static JsonElement ReadMasterTaskById(string tasksMasterPath, int taskId)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(tasksMasterPath));
        var tasks = document.RootElement.GetProperty("master").GetProperty("tasks").EnumerateArray();
        foreach (var task in tasks)
        {
            if (task.TryGetProperty("id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskId)
            {
                return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
            }
        }

        throw new Xunit.Sdk.XunitException($"task id={taskId} was not found in {tasksMasterPath}");
    }

    private static JsonElement ReadBackTaskByTaskmasterId(string tasksBackPath, int taskmasterId)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(tasksBackPath));
        foreach (var task in document.RootElement.EnumerateArray())
        {
            if (task.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId)
            {
                return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
            }
        }

        throw new Xunit.Sdk.XunitException($"taskmaster_id={taskmasterId} was not found in {tasksBackPath}");
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
        return document.RootElement.Clone();
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
                ReadString(root, "event"),
                ReadString(root, "step_name"),
                ReadTimestamp(root)));
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

    private static bool IsSelectionEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "run", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return string.Equals(record.EventName, "run_started", StringComparison.OrdinalIgnoreCase)
               || string.Equals(record.EventName, "run_resumed", StringComparison.OrdinalIgnoreCase)
               || string.Equals(record.EventName, "run_forked", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "step", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return string.Equals(record.EventName, "step_completed", StringComparison.OrdinalIgnoreCase)
               && (
                   string.Equals(record.StepName, "sc-test", StringComparison.OrdinalIgnoreCase)
                   || string.Equals(record.StepName, "sc-acceptance-check", StringComparison.OrdinalIgnoreCase)
                   || string.Equals(record.StepName, "sc-llm-review", StringComparison.OrdinalIgnoreCase)
               );
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
        if (!root.TryGetProperty("ts", out var value) || value.ValueKind != JsonValueKind.String)
        {
            return DateTimeOffset.MinValue;
        }

        if (DateTimeOffset.TryParse(value.GetString(), out var parsed))
        {
            return parsed;
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
            "Task0094 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0094_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task94 runs.");
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

    private static string ReadRepoText(string relativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required source file missing: {relativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "Game.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Unable to locate repository root containing Game.sln.");
    }

    private sealed record SignalContract(
        string SignalName,
        SignalParameter[] Parameters,
        string EmitSignalName,
        string[] EmitArguments);

    private sealed record SignalParameter(string TypeName, string ParameterName);

    private sealed record ExpectedSignalContract(
        string SignalName,
        ExpectedSignalParameter[] Parameters);

    private sealed record ExpectedSignalParameter(string TypeName, string ParameterName);

    private sealed record SignalValidationResult(bool IsValid, string ErrorCode, string FailureCategory)
    {
        public static SignalValidationResult Ok() => new(true, "none", "none");

        public static SignalValidationResult Fail(string errorCode, string category) => new(false, errorCode, category);
    }

    private sealed record RunEventRecord(
        string EventFamily,
        string EventName,
        string StepName,
        DateTimeOffset Timestamp);
}
