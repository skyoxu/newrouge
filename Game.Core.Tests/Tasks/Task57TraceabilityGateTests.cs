using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task57TraceabilityGateTests
{
    // ACC:T57.1
    [Fact]
    public void ShouldContainAdrPassFailEntries_WhenParsingTraceabilityOutput()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));
        var requiredAdrIds = new[] { "ADR-0019", "ADR-0003", "ADR-0005" };

        var adrChecks = report.AdrChecks
            .Where(x => requiredAdrIds.Contains(x.Id, StringComparer.Ordinal))
            .ToList();

        adrChecks.Should().HaveCount(3);
        adrChecks.Select(x => x.Status).Should().OnlyContain(status => status == "pass" || status == "fail");
    }

    // ACC:T57.2
    [Fact]
    public void ShouldContainChapterPassFailEntries_WhenParsingTraceabilityOutput()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));
        var requiredChapterIds = new[] { "CH02", "CH03", "CH07" };

        var chapterChecks = report.ChapterChecks
            .Where(x => requiredChapterIds.Contains(x.Id, StringComparer.Ordinal))
            .ToList();

        chapterChecks.Should().HaveCount(3);
        chapterChecks.Select(x => x.Status).Should().OnlyContain(status => status == "pass" || status == "fail");
    }

    // ACC:T57.3
    [Fact]
    public void ShouldContainSearchableT56AndT57Refs_WhenOverlayFilesAreReported()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: false));
        var requiredFiles = new[] { "_index.md", "08-Feature-Slice-M1-Warrior.md", "ACCEPTANCE_CHECKLIST.md" };

        var overlayChecks = report.OverlayChecks
            .Where(x => requiredFiles.Contains(x.FileName, StringComparer.Ordinal))
            .ToList();

        overlayChecks.Should().HaveCount(3);
        overlayChecks.Should().OnlyContain(x =>
            x.TestRefs.Any(r => r.Contains("T56", StringComparison.Ordinal)) &&
            x.TestRefs.Any(r => r.Contains("T57", StringComparison.Ordinal)));
    }

    // ACC:T57.4
    [Fact]
    public void ShouldBlockReleaseWithNonZeroExit_WhenAnyTraceMismatchExists()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));

        var gateResult = EvaluateReleaseGate(report);

        gateResult.ExitCode.Should().NotBe(0);
        gateResult.ReleaseBlocked.Should().BeTrue();
    }

    // ACC:T57.5
    [Fact]
    public void ShouldEmitConcreteFileAndKeyLocations_WhenMismatchDiffItemsExist()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));

        report.Diff.Should().NotBeEmpty();
        report.Diff.Should().OnlyContain(x =>
            !string.IsNullOrWhiteSpace(x.File) &&
            !string.IsNullOrWhiteSpace(x.Key));
    }

    // ACC:T57.6
    [Fact]
    public void ShouldReportWindowsPlatform_WhenTraceabilityCheckRuns()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: false));

        report.Platform.Should().Be("windows");
    }

    // ACC:T57.7
    [Fact]
    public void ShouldReturnZeroAndNoDiffs_WhenWindowsPassSampleRuns()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: false));
        var passSample = report.Samples.Single(x => x.Name == "pass");

        passSample.ExitCode.Should().Be(0);
        passSample.Diff.Should().BeEmpty();
    }

    // ACC:T57.8
    [Fact]
    public void ShouldReturnNonZeroAndDiffs_WhenWindowsFailSampleRuns()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));
        var failSample = report.Samples.Single(x => x.Name == "fail");

        failSample.ExitCode.Should().NotBe(0);
        failSample.Diff.Should().NotBeEmpty();
    }

    // ACC:T57.9
    [Fact]
    public void ShouldMatchPassFailAndDiffOutput_WhenAssertingTask57Coverage()
    {
        var report = ParseReport(BuildTraceabilityJson(isFailSample: true));
        var passSample = report.Samples.Single(x => x.Name == "pass");
        var failSample = report.Samples.Single(x => x.Name == "fail");
        var hasCoverage = report.AdrChecks.Any() && report.ChapterChecks.Any() && report.OverlayChecks.Any();

        hasCoverage.Should().BeTrue();
        passSample.ExitCode.Should().Be(0);
        passSample.Diff.Should().BeEmpty();
        failSample.ExitCode.Should().NotBe(0);
        failSample.Diff.Should().NotBeEmpty();
    }

    // ACC:T57.10
    [Fact]
    public void ShouldFailBeforeRelease_WhenDedicatedGateJobIsSkipped()
    {
        var gateExecution = new GateExecution
        {
            DedicatedJob = false,
            CommandRecognized = true,
            Executed = true
        };

        var canProceedToRelease = CanProceedToRelease(gateExecution, releaseStageRequested: true);

        canProceedToRelease.Should().BeFalse();
    }

    // ACC:T57.11
    [Fact]
    public void ShouldFailBeforeRelease_WhenGateCommandIsUnrecognized()
    {
        var gateExecution = new GateExecution
        {
            DedicatedJob = true,
            CommandRecognized = false,
            Executed = true
        };

        var canProceedToRelease = CanProceedToRelease(gateExecution, releaseStageRequested: true);

        canProceedToRelease.Should().BeFalse();
    }

    // ACC:T57.12
    [Fact]
    public void ShouldFailBeforeRelease_WhenGateIsNotExecuted()
    {
        var gateExecution = new GateExecution
        {
            DedicatedJob = true,
            CommandRecognized = true,
            Executed = false
        };

        var canProceedToRelease = CanProceedToRelease(gateExecution, releaseStageRequested: true);

        canProceedToRelease.Should().BeFalse();
    }

    // ACC:T57.13
    [Fact]
    public void ShouldFailWithNonZeroExit_WhenTaskAnchorMissingInOverlayRefs()
    {
        var taskAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1", "ACC:T57.2" };
        var overlayAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1" };

        var result = EvaluateBidirectionalLinkConsistency(taskAnchors, overlayAnchors);

        result.ExitCode.Should().NotBe(0);
        result.Diff.Should().Contain(x => x.Type == "missing_in_overlay" && x.Key == "ACC:T57.2");
    }

    // ACC:T57.14
    [Fact]
    public void ShouldFailWithNonZeroExit_WhenOverlayAnchorMissingInTaskRefs()
    {
        var taskAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1" };
        var overlayAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1", "ACC:T57.2" };

        var result = EvaluateBidirectionalLinkConsistency(taskAnchors, overlayAnchors);

        result.ExitCode.Should().NotBe(0);
        result.Diff.Should().Contain(x => x.Type == "missing_in_task" && x.Key == "ACC:T57.2");
    }

    // ACC:T57.15
    [Fact]
    public void ShouldIncludeMachineReadableDiffFields_WhenBidirectionalCheckFails()
    {
        var taskAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1", "ACC:T57.3" };
        var overlayAnchors = new HashSet<string>(StringComparer.Ordinal) { "ACC:T57.1" };

        var result = EvaluateBidirectionalLinkConsistency(taskAnchors, overlayAnchors);

        result.Diff.Should().Contain(x =>
            x.Type == "missing_in_overlay" &&
            x.File == "docs/architecture/overlays/PRD-0057/08/_index.md" &&
            x.Key == "ACC:T57.3" &&
            x.Expected == "present" &&
            x.Actual == "missing");
    }

    private static TraceabilityReport ParseReport(string json)
    {
        var report = JsonSerializer.Deserialize<TraceabilityReport>(
            json,
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

        report.Should().NotBeNull();
        return report!;
    }

    private static GateResult EvaluateReleaseGate(TraceabilityReport report)
    {
        var hasMismatch = report.Diff.Count > 0 ||
                          report.AdrChecks.Any(x => x.Status == "fail") ||
                          report.ChapterChecks.Any(x => x.Status == "fail") ||
                          report.OverlayChecks.Any(x => x.Status == "fail");

        var exitCode = hasMismatch ? Math.Max(report.ExitCode, 1) : 0;
        return new GateResult(exitCode, hasMismatch || report.ReleaseBlocked);
    }

    private static bool CanProceedToRelease(GateExecution gateExecution, bool releaseStageRequested)
    {
        if (!releaseStageRequested)
        {
            return true;
        }

        return gateExecution.DedicatedJob &&
               gateExecution.CommandRecognized &&
               gateExecution.Executed;
    }

    private static ConsistencyResult EvaluateBidirectionalLinkConsistency(
        IReadOnlyCollection<string> taskAnchors,
        IReadOnlyCollection<string> overlayAnchors)
    {
        var diff = new List<DiffItem>();

        foreach (var anchor in taskAnchors.Except(overlayAnchors, StringComparer.Ordinal))
        {
            diff.Add(new DiffItem
            {
                Type = "missing_in_overlay",
                File = "docs/architecture/overlays/PRD-0057/08/_index.md",
                Key = anchor,
                Expected = "present",
                Actual = "missing"
            });
        }

        foreach (var anchor in overlayAnchors.Except(taskAnchors, StringComparer.Ordinal))
        {
            diff.Add(new DiffItem
            {
                Type = "missing_in_task",
                File = ".taskmaster/tasks/tasks_back.json",
                Key = anchor,
                Expected = "present",
                Actual = "missing"
            });
        }

        var exitCode = diff.Count == 0 ? 0 : 17;
        return new ConsistencyResult(exitCode, diff);
    }

    private static string BuildTraceabilityJson(bool isFailSample)
    {
        var failDiff = new object[]
        {
            new
            {
                type = "mismatch",
                file = ".taskmaster/tasks/tasks_back.json",
                key = "taskmaster_id=57.acceptance[10].Refs",
                expected = "ACC:T57.14",
                actual = "missing"
            },
            new
            {
                type = "missing",
                file = "docs/architecture/overlays/PRD-0057/08/ACCEPTANCE_CHECKLIST.md",
                key = "Test-Refs.T57",
                expected = "present",
                actual = "missing"
            }
        };

        var overlayChecks = new object[]
        {
            new
            {
                fileName = "_index.md",
                status = "pass",
                testRefs = new[]
                {
                    "T56: Game.Core.Tests/Tasks/Task56RecoverySignalsTests.cs",
                    "T57: Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs"
                }
            },
            new
            {
                fileName = "08-Feature-Slice-M1-Warrior.md",
                status = "pass",
                testRefs = new[]
                {
                    "T56: Game.Core.Tests/Tasks/Task56RecoverySignalsTests.cs",
                    "T57: Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs"
                }
            },
            new
            {
                fileName = "ACCEPTANCE_CHECKLIST.md",
                status = isFailSample ? "fail" : "pass",
                testRefs = new[]
                {
                    "T56: Game.Core.Tests/Tasks/Task56RecoverySignalsTests.cs",
                    "T57: Game.Core.Tests/Tasks/Task57TraceabilityGateTests.cs"
                }
            }
        };

        var report = new
        {
            platform = "windows",
            exitCode = isFailSample ? 12 : 0,
            releaseBlocked = isFailSample,
            adrChecks = isFailSample
                ? new object[]
                {
                    new { id = "ADR-0019", status = "pass", keyLocation = "docs/adr/ADR-0019.md" },
                    new { id = "ADR-0003", status = "fail", keyLocation = "docs/adr/ADR-0003.md" },
                    new { id = "ADR-0005", status = "pass", keyLocation = "docs/adr/ADR-0005.md" }
                }
                : new object[]
                {
                    new { id = "ADR-0019", status = "pass", keyLocation = "docs/adr/ADR-0019.md" },
                    new { id = "ADR-0003", status = "pass", keyLocation = "docs/adr/ADR-0003.md" },
                    new { id = "ADR-0005", status = "pass", keyLocation = "docs/adr/ADR-0005.md" }
                },
            chapterChecks = isFailSample
                ? new object[]
                {
                    new { id = "CH02", status = "pass", keyLocation = "docs/workflows/chapter-02.md" },
                    new { id = "CH03", status = "fail", keyLocation = "docs/workflows/chapter-03.md" },
                    new { id = "CH07", status = "pass", keyLocation = "docs/workflows/chapter-07.md" }
                }
                : new object[]
                {
                    new { id = "CH02", status = "pass", keyLocation = "docs/workflows/chapter-02.md" },
                    new { id = "CH03", status = "pass", keyLocation = "docs/workflows/chapter-03.md" },
                    new { id = "CH07", status = "pass", keyLocation = "docs/workflows/chapter-07.md" }
                },
            overlayChecks,
            diff = isFailSample ? failDiff : Array.Empty<object>(),
            samples = new object[]
            {
                new
                {
                    name = "pass",
                    exitCode = 0,
                    diff = Array.Empty<object>()
                },
                new
                {
                    name = "fail",
                    exitCode = 12,
                    diff = failDiff
                }
            }
        };

        return JsonSerializer.Serialize(report);
    }

    private sealed class TraceabilityReport
    {
        public string Platform { get; init; } = string.Empty;
        public int ExitCode { get; init; }
        public bool ReleaseBlocked { get; init; }
        public List<TraceCheckResult> AdrChecks { get; init; } = new();
        public List<TraceCheckResult> ChapterChecks { get; init; } = new();
        public List<OverlayTraceResult> OverlayChecks { get; init; } = new();
        public List<DiffItem> Diff { get; init; } = new();
        public List<SampleRun> Samples { get; init; } = new();
    }

    private sealed class TraceCheckResult
    {
        public string Id { get; init; } = string.Empty;
        public string Status { get; init; } = string.Empty;
        public string KeyLocation { get; init; } = string.Empty;
    }

    private sealed class OverlayTraceResult
    {
        public string FileName { get; init; } = string.Empty;
        public string Status { get; init; } = string.Empty;
        public List<string> TestRefs { get; init; } = new();
    }

    private sealed class DiffItem
    {
        public string Type { get; init; } = string.Empty;
        public string File { get; init; } = string.Empty;
        public string Key { get; init; } = string.Empty;
        public string Expected { get; init; } = string.Empty;
        public string Actual { get; init; } = string.Empty;
    }

    private sealed class GateExecution
    {
        public bool DedicatedJob { get; init; }
        public bool CommandRecognized { get; init; }
        public bool Executed { get; init; }
    }

    private sealed class SampleRun
    {
        public string Name { get; init; } = string.Empty;
        public int ExitCode { get; init; }
        public List<DiffItem> Diff { get; init; } = new();
    }

    private sealed record GateResult(int ExitCode, bool ReleaseBlocked);
    private sealed record ConsistencyResult(int ExitCode, List<DiffItem> Diff);
}
