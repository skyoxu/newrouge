using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Collection("Task54QualityGatesSerial")]
public sealed class Task54QualityGateSummaryTests
{
    // ACC:T54.5
    [Fact]
    public void ShouldSerializeMachineReadableSummary_WhenIncludingSuiteStatusGateLevelAndOverallConclusion()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "adapters,security,integration,ui", fixtureName: "summary-pass.json");
        var root = result.Summary;

        root.TryGetProperty("suites", out var suites).Should().BeTrue();
        root.TryGetProperty("gate_level", out var gateLevel).Should().BeTrue();
        root.TryGetProperty("overall_gate_conclusion", out var overall).Should().BeTrue();
        root.TryGetProperty("chapter_refs", out var chapterRefs).Should().BeTrue();
        root.TryGetProperty("junit_artifact", out var junitArtifact).Should().BeTrue();

        gateLevel.GetString().Should().Be("mixed");
        overall.GetString().Should().Be("pass");
        chapterRefs.GetArrayLength().Should().BeGreaterOrEqualTo(3);

        suites.GetProperty("adapters_security").GetProperty("status").GetString().Should().Be("passed");
        suites.GetProperty("adapters_security").GetProperty("gate_level").GetString().Should().Be("hard");
        suites.GetProperty("integration_ui").GetProperty("gate_level").GetString().Should().Be("soft");

        junitArtifact.GetProperty("path").GetString().Should().Be($"logs/e2e/{DateTime.Today:yyyy-MM-dd}/gdunit/junit.xml");
    }

    [Fact]
    public void ShouldBuildSummaryOutputPath_WhenDateIsProvided()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "security");

        result.Summary.GetProperty("output").GetString().Should().Be($"logs/ci/{DateTime.Today:yyyy-MM-dd}/quality-gates/summary.json");
        result.SummaryPath.Replace("\\", "/").Should().EndWith($"/logs/ci/{DateTime.Today:yyyy-MM-dd}/quality-gates/summary.json");
    }

    [Fact]
    public void ShouldSetOverallGateConclusion_WhenHardGateResultChanges()
    {
        var pass = RunQualityGatesWithMocks(gdunitSuites: "security", securityRc: 0);
        var fail = RunQualityGatesWithMocks(gdunitSuites: "security", securityRc: 1);

        pass.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("pass");
        pass.ExitCode.Should().Be(0);
        fail.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("fail");
        fail.ExitCode.Should().Be(1);
    }

    [Fact]
    public void ShouldWriteMissingReason_WhenJunitArtifactIsNotGenerated()
    {
        var result = RunQualityGatesWithMocks(
            gdunitSuites: "integration",
            skipFakeXml: true,
            fixtureName: "summary-missing-junit.json");

        var junitArtifact = result.Summary.GetProperty("junit_artifact");
        junitArtifact.GetProperty("status").GetString().Should().Be("missing");
        junitArtifact.GetProperty("exists").GetBoolean().Should().BeFalse();
        junitArtifact.GetProperty("missing_reason").GetString().Should().Be("gdunit_results_xml_not_found");
        result.FixturePath.Should().NotBeNull();
        File.Exists(result.FixturePath!).Should().BeTrue();
    }

    // ACC:T54.12
    [Fact]
    public void ShouldAggregateCiAndGdUnitInSingleSummaryDocument_WhenQualityGatesCompletes()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "adapters,ui");
        var root = result.Summary;

        root.TryGetProperty("suites", out var suites).Should().BeTrue();
        suites.TryGetProperty("ci_pipeline", out var ciPipeline).Should().BeTrue();
        ciPipeline.GetProperty("status").GetString().Should().NotBeNullOrWhiteSpace();

        root.TryGetProperty("gdunit_suites", out var gdunitSuites).Should().BeTrue();
        gdunitSuites.TryGetProperty("adapters", out _).Should().BeTrue();
        gdunitSuites.TryGetProperty("security", out _).Should().BeTrue();
        gdunitSuites.TryGetProperty("integration", out _).Should().BeTrue();
        gdunitSuites.TryGetProperty("ui", out _).Should().BeTrue();

        root.TryGetProperty("overall_gate_conclusion", out var overall).Should().BeTrue();
        var overallText = overall.GetString();
        (overallText == "pass" || overallText == "fail").Should().BeTrue();
        result.ExitCode.Should().Be(overallText == "pass" ? 0 : 1);

        var checklistPath = Path.Combine(
            FindRepoRoot(),
            "docs",
            "architecture",
            "overlays",
            "PRD-NEWROUGE-GAME-0001",
            "08",
            "ACCEPTANCE_CHECKLIST.md");
        File.Exists(checklistPath).Should().BeTrue("Task54 checklist must exist for ADR traceability assertions");
        var checklistText = File.ReadAllText(checklistPath);
        var task54SectionStart = checklistText.IndexOf("## Task54 Gate Notes", StringComparison.Ordinal);
        task54SectionStart.Should().BeGreaterOrEqualTo(0);
        var task54Section = checklistText.Substring(task54SectionStart);
        task54Section.Should().Contain("ADR-0005");
        task54Section.Should().Contain("ADR-0011");
        task54Section.Should().Contain("ADR-0024");
    }

    private static MockRunResult RunQualityGatesWithMocks(
        string gdunitSuites,
        int ciRc = 0,
        int adaptersRc = 0,
        int securityRc = 0,
        int integrationRc = 0,
        int uiRc = 0,
        bool skipFakeXml = false,
        string? fixtureName = null)
    {
        var repoRoot = FindRepoRoot();
        var date = DateTime.Today.ToString("yyyy-MM-dd");
        var qualityDir = Path.Combine(repoRoot, "logs", "e2e", date, "quality-gates");
        var summaryPath = Path.Combine(repoRoot, "logs", "ci", date, "quality-gates", "summary.json");
        var taskPath = Path.Combine(repoRoot, "logs", "ci", date, "task-0054.json");

        if (Directory.Exists(qualityDir))
        {
            Directory.Delete(qualityDir, recursive: true);
        }
        if (File.Exists(summaryPath))
        {
            File.Delete(summaryPath);
        }
        if (File.Exists(taskPath))
        {
            File.Delete(taskPath);
        }

        var args = "-3 scripts/python/quality_gates.py all --godot-bin MOCK_GODOT --security-profile host-safe --no-require-lock-files";
        if (!string.IsNullOrWhiteSpace(gdunitSuites))
        {
            args += $" --gdunit-suites {gdunitSuites}";
        }

        var psi = new ProcessStartInfo
        {
            FileName = "py",
            Arguments = args,
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };

        psi.Environment["QUALITY_GATES_SKIP_PREREQS"] = "1";
        psi.Environment["QUALITY_GATES_FAKE_CI_RC"] = ciRc.ToString();
        psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_ADAPTERS"] = adaptersRc.ToString();
        psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_SECURITY"] = securityRc.ToString();
        psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_INTEGRATION"] = integrationRc.ToString();
        psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_UI"] = uiRc.ToString();
        psi.Environment["QUALITY_GATES_FAKE_SMOKE_RC"] = "0";
        psi.Environment["QUALITY_GATES_FAKE_SKIP_XML"] = skipFakeXml ? "1" : "0";

        using var process = Process.Start(psi);
        process.Should().NotBeNull("quality_gates.py should start from Task54 summary tests");
        var stdout = process!.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        File.Exists(summaryPath).Should().BeTrue($"expected summary at {summaryPath}\n{stdout}\n{stderr}");
        File.Exists(taskPath).Should().BeTrue($"expected task record at {taskPath}\n{stdout}\n{stderr}");

        string? fixturePath = null;
        if (!string.IsNullOrWhiteSpace(fixtureName))
        {
            var fixtureDir = Path.Combine(repoRoot, "logs", "ci", date, "quality-gates", "task54-fixtures");
            Directory.CreateDirectory(fixtureDir);
            fixturePath = Path.Combine(fixtureDir, fixtureName);
            File.Copy(summaryPath, fixturePath, overwrite: true);
        }

        using var summaryDoc = JsonDocument.Parse(File.ReadAllText(summaryPath));
        using var taskDoc = JsonDocument.Parse(File.ReadAllText(taskPath));
        return new MockRunResult(process.ExitCode, summaryDoc.RootElement.Clone(), taskDoc.RootElement.Clone(), summaryPath, fixturePath);
    }

    private static string FindRepoRoot()
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

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }

    private sealed record MockRunResult(
        int ExitCode,
        JsonElement Summary,
        JsonElement TaskRecord,
        string SummaryPath,
        string? FixturePath);
}
