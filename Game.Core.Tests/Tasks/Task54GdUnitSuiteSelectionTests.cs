using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Collection("Task54QualityGatesSerial")]
public sealed class Task54GdUnitSuiteSelectionTests
{
    // ACC:T54.1
    [Fact]
    public void ShouldWriteExplicitExecutedAndSkippedSuiteStates_WhenGdUnitToggleChanges()
    {
        var enabled = RunQualityGatesWithMocks(gdunitSuites: "integration");

        enabled.Summary.GetProperty("gdunit_suites").GetProperty("integration").GetProperty("state").GetString().Should().Be("executed");
        enabled.Summary.GetProperty("gdunit_suites").GetProperty("adapters").GetProperty("state").GetString().Should().Be("skipped");
        enabled.Summary.GetProperty("suites").GetProperty("integration_ui").GetProperty("state").GetString().Should().Be("executed");

        var disabled = RunQualityGatesWithMocks(gdunitSuites: string.Empty);

        foreach (var suiteName in new[] { "adapters", "security", "integration", "ui" })
        {
            disabled.Summary.GetProperty("gdunit_suites").GetProperty(suiteName).GetProperty("state").GetString().Should().Be("skipped");
        }

        disabled.Summary.GetProperty("suites").GetProperty("integration_ui").GetProperty("state").GetString().Should().Be("skipped");
    }

    // ACC:T54.8
    [Fact]
    public void ShouldDistinguishSelectedSuiteSubset_WhenSummaryIsBuiltFromScriptExecution()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "adapters,ui");
        var gdunitSuites = result.Summary.GetProperty("gdunit_suites");

        gdunitSuites.GetProperty("adapters").GetProperty("selected").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("adapters").GetProperty("state").GetString().Should().Be("executed");
        gdunitSuites.GetProperty("security").GetProperty("selected").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("security").GetProperty("state").GetString().Should().Be("skipped");
        gdunitSuites.GetProperty("ui").GetProperty("selected").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("ui").GetProperty("state").GetString().Should().Be("executed");
        gdunitSuites.GetProperty("integration").GetProperty("selected").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("integration").GetProperty("state").GetString().Should().Be("skipped");
    }

    // ACC:T54.8
    [Fact]
    public void ShouldMarkAllSuitesExplicitly_WhenSelectingSecurityAndIntegrationSubset()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "security,integration");
        var gdunitSuites = result.Summary.GetProperty("gdunit_suites");

        gdunitSuites.GetProperty("adapters").GetProperty("selected").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("adapters").GetProperty("executed").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("adapters").GetProperty("state").GetString().Should().Be("skipped");

        gdunitSuites.GetProperty("security").GetProperty("selected").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("security").GetProperty("executed").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("security").GetProperty("state").GetString().Should().Be("executed");

        gdunitSuites.GetProperty("integration").GetProperty("selected").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("integration").GetProperty("executed").GetBoolean().Should().BeTrue();
        gdunitSuites.GetProperty("integration").GetProperty("state").GetString().Should().Be("executed");

        gdunitSuites.GetProperty("ui").GetProperty("selected").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("ui").GetProperty("executed").GetBoolean().Should().BeFalse();
        gdunitSuites.GetProperty("ui").GetProperty("state").GetString().Should().Be("skipped");
    }

    // ACC:T54.8
    [Fact]
    public void ShouldKeepStateFieldExplicitForEverySuite_WhenSummaryIsProduced()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "security");

        foreach (var suiteName in new[] { "adapters", "security", "integration", "ui" })
        {
            var state = result.Summary.GetProperty("gdunit_suites").GetProperty(suiteName).GetProperty("state").GetString();
            state.Should().Match(s => s == "executed" || s == "skipped");
        }
    }

    // ACC:T54.9
    [Fact]
    public void ShouldReportInvalidSuiteTokensAndKeepGateDecisionConsistent_WhenCsvContainsUnknownValues()
    {
        var result = RunQualityGatesWithMocks(gdunitSuites: "adapters,unknown_suite");

        var invalid = result.Summary.GetProperty("invalid_gdunit_suites").EnumerateArray().Select(x => x.GetString()).ToArray();
        invalid.Should().ContainSingle().Which.Should().Be("unknown_suite");

        var selected = result.Summary.GetProperty("selected_gdunit_suites").EnumerateArray().Select(x => x.GetString()).ToArray();
        selected.Should().Contain("adapters");
        selected.Should().NotContain("unknown_suite");

        var overall = result.Summary.GetProperty("overall_gate_conclusion").GetString();
        (overall == "pass" || overall == "fail").Should().BeTrue();
        result.ExitCode.Should().Be(overall == "pass" ? 0 : 1);
    }

    private static MockRunResult RunQualityGatesWithMocks(
        string gdunitSuites,
        int ciRc = 0,
        int adaptersRc = 0,
        int securityRc = 0,
        int integrationRc = 0,
        int uiRc = 0)
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
        psi.Environment["QUALITY_GATES_FAKE_SKIP_XML"] = "0";

        using var process = Process.Start(psi);
        process.Should().NotBeNull("quality_gates.py should start from Task54 suite selection tests");
        var stdout = process!.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        File.Exists(summaryPath).Should().BeTrue($"expected summary at {summaryPath}\n{stdout}\n{stderr}");
        File.Exists(taskPath).Should().BeTrue($"expected task record at {taskPath}\n{stdout}\n{stderr}");

        using var summaryDoc = JsonDocument.Parse(File.ReadAllText(summaryPath));
        using var taskDoc = JsonDocument.Parse(File.ReadAllText(taskPath));
        return new MockRunResult(process.ExitCode, summaryDoc.RootElement.Clone(), taskDoc.RootElement.Clone());
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

    private sealed record MockRunResult(int ExitCode, JsonElement Summary, JsonElement TaskRecord);
}
