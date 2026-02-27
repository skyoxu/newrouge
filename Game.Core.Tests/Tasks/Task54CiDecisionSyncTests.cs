using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks
{
    [Collection("Task54QualityGatesSerial")]
    public sealed class Task54CiDecisionSyncTests
    {
        private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
        private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";

        [Theory]
        [InlineData("pass", 0)]
        [InlineData("fail", 1)]
        [InlineData("unexpected", 1)]
        [InlineData("", 1)]
        public void ShouldMapOverallSummaryStatusToStableExitCode_WhenStatusVaries(string overallStatus, int expectedExitCode)
        {
            var exitCode = MapCiExitCodeFromOverallStatus(overallStatus);

            exitCode.Should().Be(expectedExitCode);
        }

        [Fact]
        public void ShouldExposeTask54EvidencePathsInTaskViews_WhenLoadingTaskMetadata()
        {
            var refs = LoadTask54RefsFromViews();

            refs.TestRefs.Should().Contain("Tests.Godot/tests/ci/test_gdunit_suite_wiring.gd");
            refs.EvidenceRefs.Should().Contain("logs/ci/<date>/quality-gates/summary.json");
            refs.EvidenceRefs.Should().Contain("logs/e2e/<date>/gdunit/junit.xml");
            refs.EvidenceRefs.Should().Contain("logs/ci/<date>/task-0054.json");
        }

        // ACC:T54.9
        [Fact]
        public void ShouldUseSummaryOverallConclusionAsCiDecisionSource_WhenResultChanges()
        {
            var pass = RunQualityGatesWithMocks(ciRc: 0, adaptersRc: 0, securityRc: 0, integrationRc: 1, uiRc: 1);
            var fail = RunQualityGatesWithMocks(ciRc: 0, adaptersRc: 1, securityRc: 0, integrationRc: 0, uiRc: 0);

            var passConclusion = pass.Summary.GetProperty("overall_gate_conclusion").GetString();
            var failConclusion = fail.Summary.GetProperty("overall_gate_conclusion").GetString();

            passConclusion.Should().Be("pass");
            failConclusion.Should().Be("fail");
            MapCiExitCodeFromOverallStatus(passConclusion).Should().Be(pass.ExitCode);
            MapCiExitCodeFromOverallStatus(failConclusion).Should().Be(fail.ExitCode);
        }

        // ACC:T54.2, ACC:T54.7
        [Fact]
        public void ShouldReturnNonZeroAndWriteFailSummary_WhenAnyHardSuiteFailsInMockMode()
        {
            var result = RunQualityGatesWithMocks(ciRc: 0, adaptersRc: 1, securityRc: 0, integrationRc: 1, uiRc: 1);

            result.ExitCode.Should().Be(1);
            result.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("fail");
            result.Summary.GetProperty("suites").GetProperty("adapters_security").GetProperty("status").GetString().Should().Be("failed");
            result.TaskRecord.GetProperty("exit_code").GetInt32().Should().Be(1);
        }

        // ACC:T54.2, ACC:T54.7
        [Fact]
        public void ShouldReturnZero_WhenOnlySoftSuitesFailInMockMode()
        {
            var result = RunQualityGatesWithMocks(ciRc: 0, adaptersRc: 0, securityRc: 0, integrationRc: 1, uiRc: 1);

            result.ExitCode.Should().Be(0);
            result.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("pass");
            result.Summary.GetProperty("suites").GetProperty("adapters_security").GetProperty("status").GetString().Should().Be("passed");
            result.Summary.GetProperty("suites").GetProperty("integration_ui").GetProperty("status").GetString().Should().Be("failed");
            result.TaskRecord.GetProperty("exit_code").GetInt32().Should().Be(0);
        }

        // ACC:T54.11
        [Fact]
        public void ShouldKeepOverallDecisionStable_WhenNoGdUnitSuitesAreSelected()
        {
            var withSuites = RunQualityGatesWithMocks(
                ciRc: 0,
                adaptersRc: 0,
                securityRc: 0,
                integrationRc: 0,
                uiRc: 0,
                gdunitSuites: "adapters,security,integration,ui");

            var withoutSuites = RunQualityGatesWithMocks(
                ciRc: 0,
                adaptersRc: 0,
                securityRc: 0,
                integrationRc: 0,
                uiRc: 0,
                gdunitSuites: string.Empty);

            withSuites.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("pass");
            withoutSuites.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("pass");
            withSuites.ExitCode.Should().Be(0);
            withoutSuites.ExitCode.Should().Be(0);

            var gdunitSuites = withoutSuites.Summary.GetProperty("selected_gdunit_suites").EnumerateArray().Select(x => x.GetString()).ToArray();
            gdunitSuites.Should().BeEmpty();
        }

        // ACC:T54.11
        [Fact]
        public void ShouldFail_WhenCiFailsAndNoGdUnitSuitesAreSelected()
        {
            var result = RunQualityGatesWithMocks(
                ciRc: 1,
                adaptersRc: 0,
                securityRc: 0,
                integrationRc: 0,
                uiRc: 0,
                gdunitSuites: string.Empty);

            result.Summary.GetProperty("overall_gate_conclusion").GetString().Should().Be("fail");
            result.ExitCode.Should().Be(1);
            result.TaskRecord.GetProperty("exit_code").GetInt32().Should().Be(1);

            var gdunitSuites = result.Summary.GetProperty("selected_gdunit_suites").EnumerateArray().Select(x => x.GetString()).ToArray();
            gdunitSuites.Should().BeEmpty();
        }

        private static int MapCiExitCodeFromOverallStatus(string? overallStatus)
        {
            return string.Equals(overallStatus, "pass", StringComparison.Ordinal) ? 0 : 1;
        }

        private static (IReadOnlyCollection<string> TestRefs, IReadOnlyCollection<string> EvidenceRefs) LoadTask54RefsFromViews()
        {
            var testRefs = new HashSet<string>(StringComparer.Ordinal);
            var evidenceRefs = new HashSet<string>(StringComparer.Ordinal);
            foreach (var path in new[] { TasksBackPath, TasksGameplayPath })
            {
                var absolutePath = Path.Combine(FindRepoRoot(), path);
                File.Exists(absolutePath).Should().BeTrue($"expected repository file at {path}");
                using var doc = JsonDocument.Parse(File.ReadAllText(absolutePath));
                foreach (var item in doc.RootElement.EnumerateArray())
                {
                    if (!item.TryGetProperty("taskmaster_id", out var taskIdProperty))
                    {
                        continue;
                    }

                    if (!string.Equals(taskIdProperty.ToString(), "54", StringComparison.Ordinal))
                    {
                        continue;
                    }

                    foreach (var value in EnumerateStringArray(item, "test_refs"))
                    {
                        testRefs.Add(value);
                    }

                    foreach (var value in EnumerateStringArray(item, "evidence_refs"))
                    {
                        evidenceRefs.Add(value);
                    }
                }
            }

            return (testRefs.ToArray(), evidenceRefs.ToArray());
        }

        private static IEnumerable<string> EnumerateStringArray(JsonElement item, string name)
        {
            if (!item.TryGetProperty(name, out var arrayProperty) || arrayProperty.ValueKind != JsonValueKind.Array)
            {
                yield break;
            }

            foreach (var element in arrayProperty.EnumerateArray())
            {
                var value = element.GetString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    yield return value!;
                }
            }
        }

        private static MockRunResult RunQualityGatesWithMocks(
            int ciRc,
            int adaptersRc,
            int securityRc,
            int integrationRc,
            int uiRc,
            string gdunitSuites = "adapters,security,integration,ui")
        {
            var repoRoot = FindRepoRoot();
            var date = DateTime.Today.ToString("yyyy-MM-dd");
            var summaryPath = Path.Combine(repoRoot, "logs", "ci", date, "quality-gates", "summary.json");
            var taskPath = Path.Combine(repoRoot, "logs", "ci", date, "task-0054.json");

            if (File.Exists(summaryPath))
            {
                File.Delete(summaryPath);
            }

            if (File.Exists(taskPath))
            {
                File.Delete(taskPath);
            }

            var psi = new ProcessStartInfo
            {
                FileName = "py",
                Arguments = "-3 scripts/python/quality_gates.py all --godot-bin MOCK_GODOT --security-profile host-safe --no-require-lock-files",
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = System.Text.Encoding.UTF8,
                StandardErrorEncoding = System.Text.Encoding.UTF8,
            };

            psi.Environment["QUALITY_GATES_SKIP_PREREQS"] = "1";
            psi.Environment["QUALITY_GATES_FAKE_CI_RC"] = ciRc.ToString();
            psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_ADAPTERS"] = adaptersRc.ToString();
            psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_SECURITY"] = securityRc.ToString();
            psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_INTEGRATION"] = integrationRc.ToString();
            psi.Environment["QUALITY_GATES_FAKE_GDUNIT_RC_UI"] = uiRc.ToString();
            psi.Environment["QUALITY_GATES_FAKE_SMOKE_RC"] = "0";
            if (!string.IsNullOrWhiteSpace(gdunitSuites))
            {
                psi.Arguments += $" --gdunit-suites {gdunitSuites}";
            }

            using var process = Process.Start(psi);
            process.Should().NotBeNull("quality_gates.py should start from unit test");
            var stdout = process!.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            process.WaitForExit();
            process.ExitCode.Should().NotBe(int.MinValue, $"{stdout}\n{stderr}");

            File.Exists(summaryPath).Should().BeTrue($"expected summary at {summaryPath}\n{stdout}\n{stderr}");
            File.Exists(taskPath).Should().BeTrue($"expected task record at {taskPath}\n{stdout}\n{stderr}");

            using var summaryDoc = JsonDocument.Parse(File.ReadAllText(summaryPath));
            using var taskDoc = JsonDocument.Parse(File.ReadAllText(taskPath));
            return new MockRunResult(process.ExitCode, summaryDoc.RootElement.Clone(), taskDoc.RootElement.Clone());
        }

        private sealed record MockRunResult(int ExitCode, JsonElement Summary, JsonElement TaskRecord);

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
    }
}
