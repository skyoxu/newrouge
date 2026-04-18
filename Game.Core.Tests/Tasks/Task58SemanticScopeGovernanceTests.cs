using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task58SemanticScopeGovernanceTests
{
    // ACC:T58.1
    [Fact]
    public void ShouldExposeRequiredGovernanceKeys_WhenParsingTaskSemanticGovernanceRecord()
    {
        using var sample = GenerateGovernanceSample("pass");
        using var document = JsonDocument.Parse(File.ReadAllText(sample.OutputPath));
        var root = document.RootElement;

        root.GetProperty("semantic_policy_mode").GetString().Should().NotBeNullOrWhiteSpace();
        root.GetProperty("gate_precedence").GetString().Should().NotBeNullOrWhiteSpace();
        root.GetProperty("governance_result").GetString().Should().NotBeNullOrWhiteSpace();
    }

    // ACC:T58.2
    [Fact]
    public void ShouldClassifyOutOfScopeExpansionAsAdvisory_WhenEvaluatingPolicyScope()
    {
        var findings = new[]
        {
            new Dictionary<string, object?>
            {
                ["id"] = "scope:repo.scan",
                ["severity"] = "warn",
                ["scope_item"] = "repo.scan"
            },
            new Dictionary<string, object?>
            {
                ["id"] = "warn-in-scope",
                ["severity"] = "warn",
                ["scope_item"] = "task.mapped.acceptance"
            }
        };

        using var nonEmptyMasterDetails = GenerateGovernanceFromInput(
            findings,
            acceptanceCheck: "ok",
            includeTaskId: true);
        using var nonEmptyDoc = JsonDocument.Parse(File.ReadAllText(nonEmptyMasterDetails.OutputPath));
        var nonEmptyRoot = nonEmptyDoc.RootElement;

        nonEmptyRoot.GetProperty("governance_result").GetString().Should().Be("pass");
        nonEmptyRoot.GetProperty("blocker_findings").GetArrayLength().Should().Be(0);
        nonEmptyRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .Contain(item =>
                item.GetProperty("id").GetString() == "scope:repo.scan" &&
                item.GetProperty("classification").GetString() == "advisory_out_of_scope");
        nonEmptyRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .Contain(item =>
                item.GetProperty("id").GetString() == "warn-in-scope" &&
                item.GetProperty("classification").GetString() == "advisory_warn");
        nonEmptyRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .NotContain(item =>
                item.GetProperty("id").GetString() == "warn-in-scope" &&
                item.GetProperty("classification").GetString() == "advisory_out_of_scope");
        nonEmptyRoot.GetProperty("task_context")
            .GetProperty("allowed_scope_items")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Should()
            .Contain("task.master.details")
            .And
            .Contain("task.mapped.acceptance");

        var emptyMasterDetailsFindings = new[]
        {
            new Dictionary<string, object?>
            {
                ["id"] = "warn-empty-master-in-scope",
                ["severity"] = "warn",
                ["scope_item"] = "task.mapped.acceptance"
            },
            new Dictionary<string, object?>
            {
                ["id"] = "warn-empty-master-out-of-scope",
                ["severity"] = "warn",
                ["scope_item"] = "task.master.details"
            }
        };
        var emptyMasterDetailsContext = new Dictionary<string, object?>
        {
            ["task_id"] = 58,
            ["master_details_present"] = false,
            ["mapped_acceptance_count"] = 1,
            ["mapped_acceptance_ids"] = new[] { "ACC:T58.2" },
            ["allowed_scope_items"] = new[] { "task.mapped.acceptance" }
        };

        using var emptyMasterDetails = GenerateGovernanceFromInput(
            emptyMasterDetailsFindings,
            acceptanceCheck: "ok",
            includeTaskId: false,
            taskContext: emptyMasterDetailsContext);
        using var emptyDoc = JsonDocument.Parse(File.ReadAllText(emptyMasterDetails.OutputPath));
        var emptyRoot = emptyDoc.RootElement;

        emptyRoot.GetProperty("task_context")
            .GetProperty("allowed_scope_items")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Should()
            .BeEquivalentTo(new[] { "task.mapped.acceptance" });
        emptyRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .Contain(item =>
                item.GetProperty("id").GetString() == "warn-empty-master-in-scope" &&
                item.GetProperty("classification").GetString() == "advisory_warn");
        emptyRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .Contain(item =>
                item.GetProperty("id").GetString() == "warn-empty-master-out-of-scope" &&
                item.GetProperty("classification").GetString() == "advisory_out_of_scope");
    }

    // ACC:T58.3
    [Fact]
    public void ShouldPassWithAdvisoryNotes_WhenAcceptanceIsOkAndWarnFindingsAreNotElevated()
    {
        using var sample = GenerateGovernanceSample("advisory-warning");
        using var document = JsonDocument.Parse(File.ReadAllText(sample.OutputPath));
        var root = document.RootElement;

        root.GetProperty("governance_result").GetString().Should().Be("pass");
        root.GetProperty("blocker_findings").GetArrayLength().Should().Be(0);
        root.GetProperty("advisory_findings").GetArrayLength().Should().BeGreaterThan(0);
        root.GetProperty("advisory_notes").GetArrayLength().Should().BeGreaterThan(0);
    }

    // ACC:T58.4
    [Fact]
    public void ShouldFailRegardlessOfLlmReview_WhenAcceptanceCheckFails()
    {
        using var sample = GenerateGovernanceSample("acceptance-fail");
        using var document = JsonDocument.Parse(File.ReadAllText(sample.OutputPath));
        var root = document.RootElement;

        root.GetProperty("acceptance_check").GetString().Should().Be("fail");
        root.GetProperty("governance_result").GetString().Should().Be("fail");
    }

    // ACC:T58.5
    [Fact]
    public void ShouldExposeStableFindingKeys_WhenGovernanceOutputIsSerialized()
    {
        using var sample = GenerateGovernanceSample("elevated-blocker");
        using var document = JsonDocument.Parse(File.ReadAllText(sample.OutputPath));
        var root = document.RootElement;

        var blocker = root.GetProperty("blocker_findings").EnumerateArray().Single();
        blocker.TryGetProperty("id", out _).Should().BeTrue();
        blocker.TryGetProperty("classification", out _).Should().BeTrue();
        blocker.TryGetProperty("elevation_rule_id", out _).Should().BeTrue();
        blocker.TryGetProperty("evidence", out _).Should().BeTrue();

        var advisory = root.GetProperty("advisory_findings").EnumerateArray().Single();
        advisory.TryGetProperty("id", out _).Should().BeTrue();
        advisory.TryGetProperty("classification", out _).Should().BeTrue();
        advisory.TryGetProperty("elevation_rule_id", out _).Should().BeTrue();
        advisory.TryGetProperty("evidence", out _).Should().BeTrue();
    }

    // ACC:T58.6
    [Fact]
    public void ShouldIncludeWindowsPlatformAndRunId_WhenBuildingExecutionEvidence()
    {
        using var sample = GenerateGovernanceSample("pass");
        using var document = JsonDocument.Parse(File.ReadAllText(sample.OutputPath));
        var root = document.RootElement;

        root.GetProperty("platform").GetString().Should().Be("windows");
        root.GetProperty("run_id").GetString().Should().NotBeNullOrWhiteSpace();
    }

    // ACC:T58.9
    [Fact]
    public void ShouldProduceStableClassificationAcrossRepeatedRuns_WhenInputIsUnchanged()
    {
        var findings = new[]
        {
            new Dictionary<string, object?>
            {
                ["id"] = "warn-stable-in-scope",
                ["severity"] = "warn",
                ["scope_item"] = "task.mapped.acceptance"
            },
            new Dictionary<string, object?>
            {
                ["id"] = "warn-stable-out-of-scope",
                ["severity"] = "warn",
                ["scope_item"] = "repo.scan"
            }
        };

        using var first = GenerateGovernanceFromInput(findings, acceptanceCheck: "ok", includeTaskId: true);
        using var second = GenerateGovernanceFromInput(findings, acceptanceCheck: "ok", includeTaskId: true);
        using var firstDoc = JsonDocument.Parse(File.ReadAllText(first.OutputPath));
        using var secondDoc = JsonDocument.Parse(File.ReadAllText(second.OutputPath));

        firstDoc.RootElement.GetProperty("governance_result").GetString().Should().Be(secondDoc.RootElement.GetProperty("governance_result").GetString());

        var firstClassifications = firstDoc.RootElement
            .GetProperty("advisory_findings")
            .EnumerateArray()
            .Select(item => $"{item.GetProperty("id").GetString()}:{item.GetProperty("classification").GetString()}")
            .OrderBy(item => item)
            .ToArray();
        var secondClassifications = secondDoc.RootElement
            .GetProperty("advisory_findings")
            .EnumerateArray()
            .Select(item => $"{item.GetProperty("id").GetString()}:{item.GetProperty("classification").GetString()}")
            .OrderBy(item => item)
            .ToArray();
        firstClassifications.Should().Equal(secondClassifications);
    }

    // ACC:T58.7
    [Fact]
    public void ShouldProducePassAndAdvisorySamplesWithoutManualEdits_WhenRunningLocalScriptSamples()
    {
        using var passSample = GenerateGovernanceSample("pass");
        using var advisorySample = GenerateGovernanceSample("advisory-warning");

        using var passDoc = JsonDocument.Parse(File.ReadAllText(passSample.OutputPath));
        using var advisoryDoc = JsonDocument.Parse(File.ReadAllText(advisorySample.OutputPath));

        passDoc.RootElement.GetProperty("sample").GetString().Should().Be("pass");
        passDoc.RootElement.GetProperty("governance_result").GetString().Should().Be("pass");
        passDoc.RootElement.GetProperty("manual_edit_required").GetBoolean().Should().BeFalse();
        passDoc.RootElement.GetProperty("command").GetString().Should().Contain("py -3 scripts/python/task58_semantic_governance_sample.py");
        passDoc.RootElement.GetProperty("evidence_refs")
            .GetProperty("acceptance_check_summary")
            .GetString()
            .Should()
            .Contain("logs/ci/<date>/sc-acceptance-check-task-<id>/summary.json");
        passDoc.RootElement.GetProperty("evidence_refs")
            .GetProperty("llm_review_summary")
            .GetString()
            .Should()
            .Contain("logs/ci/<date>/sc-llm-review-task-<id>/summary.json");

        advisoryDoc.RootElement.GetProperty("sample").GetString().Should().Be("advisory-warning");
        advisoryDoc.RootElement.GetProperty("governance_result").GetString().Should().Be("pass");
        advisoryDoc.RootElement.GetProperty("manual_edit_required").GetBoolean().Should().BeFalse();
        advisoryDoc.RootElement.GetProperty("command").GetString().Should().Contain("py -3 scripts/python/task58_semantic_governance_sample.py");
        advisoryDoc.RootElement.GetProperty("evidence_refs")
            .GetProperty("acceptance_check_summary")
            .GetString()
            .Should()
            .Contain("logs/ci/<date>/sc-acceptance-check-task-<id>/summary.json");
        advisoryDoc.RootElement.GetProperty("evidence_refs")
            .GetProperty("llm_review_summary")
            .GetString()
            .Should()
            .Contain("logs/ci/<date>/sc-llm-review-task-<id>/summary.json");
    }

    // ACC:T58.10
    [Fact]
    public void ShouldEmitCompleteMinimalEvidenceSummaryFields_WhenBuildingPassAndAdvisorySamples()
    {
        using var passSample = GenerateGovernanceSample("pass");
        using var advisorySample = GenerateGovernanceSample("advisory-warning");
        using var passDoc = JsonDocument.Parse(File.ReadAllText(passSample.OutputPath));
        using var advisoryDoc = JsonDocument.Parse(File.ReadAllText(advisorySample.OutputPath));

        AssertMinimalEvidenceSummary(passDoc.RootElement);
        AssertMinimalEvidenceSummary(advisoryDoc.RootElement);
    }

    // ACC:T58.8
    [Fact]
    public void ShouldPromoteWarnToBlockerOnlyWithExplicitElevationAndEvidence_WhenEvaluatingElevationRules()
    {
        using var elevated = GenerateGovernanceSample("elevated-blocker");
        using var missingEvidence = GenerateGovernanceSample("elevated-missing-evidence");

        using var elevatedDoc = JsonDocument.Parse(File.ReadAllText(elevated.OutputPath));
        using var missingDoc = JsonDocument.Parse(File.ReadAllText(missingEvidence.OutputPath));

        var elevatedRoot = elevatedDoc.RootElement;
        elevatedRoot.GetProperty("governance_result").GetString().Should().Be("fail");
        elevatedRoot.GetProperty("blocker_findings")
            .EnumerateArray()
            .Should()
            .ContainSingle(item =>
                item.GetProperty("id").GetString() == "warn-elevated" &&
                item.GetProperty("elevation_rule_id").GetString() == "RULE-ELV-001" &&
                !string.IsNullOrWhiteSpace(item.GetProperty("evidence").GetString()));

        var missingRoot = missingDoc.RootElement;
        missingRoot.GetProperty("governance_result").GetString().Should().Be("pass");
        missingRoot.GetProperty("blocker_findings").GetArrayLength().Should().Be(0);
        missingRoot.GetProperty("advisory_findings")
            .EnumerateArray()
            .Should()
            .Contain(item =>
                item.GetProperty("id").GetString() == "warn-elevated-missing-evidence" &&
                item.GetProperty("classification").GetString() == "invalid_elevation_missing_evidence");
    }

    private static GovernanceSampleRun GenerateGovernanceSample(string sample)
    {
        var repoRoot = FindRepositoryRoot();
        var workingDirectory = CreateUniqueTempRoot();
        var outPath = Path.Combine(workingDirectory, "logs", "ci", DateTime.Today.ToString("yyyy-MM-dd"), "task-0058-semantic-governance.json");
        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);

        var scriptPath = Path.Combine(repoRoot, "scripts", "python", "task58_semantic_governance_sample.py");
        var command = $"py -3 scripts/python/task58_semantic_governance_sample.py --sample {sample} --out \"{outPath}\"";
        var result = RunPythonScript(
            scriptPath,
            repoRoot,
            "--sample",
            sample,
            "--out",
            outPath);

        result.ExitCode.Should().Be(0, $"sample `{sample}` should be reproducible by local script");
        File.Exists(outPath).Should().BeTrue("governance sample output should be generated");

        return new GovernanceSampleRun(workingDirectory, outPath, command);
    }

    private static GovernanceSampleRun GenerateGovernanceFromInput(
        IReadOnlyList<Dictionary<string, object?>> findings,
        string acceptanceCheck,
        bool includeTaskId,
        Dictionary<string, object?>? taskContext = null)
    {
        var repoRoot = FindRepositoryRoot();
        var workingDirectory = CreateUniqueTempRoot();
        var outPath = Path.Combine(workingDirectory, "logs", "ci", DateTime.Today.ToString("yyyy-MM-dd"), "task-0058-semantic-governance.json");
        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);

        var inputPath = Path.Combine(workingDirectory, "task58-semantic-governance-input.json");
        var inputPayload = new Dictionary<string, object?>
        {
            ["acceptance_check"] = acceptanceCheck,
            ["findings"] = findings
        };
        if (taskContext is not null)
        {
            inputPayload["task_context"] = taskContext;
        }
        File.WriteAllText(inputPath, JsonSerializer.Serialize(inputPayload), System.Text.Encoding.UTF8);

        var scriptPath = Path.Combine(repoRoot, "scripts", "python", "task58_semantic_governance_sample.py");
        var command = $"py -3 scripts/python/task58_semantic_governance_sample.py --input-json \"{inputPath}\" --out \"{outPath}\"";
        var args = new List<string>
        {
            "--input-json",
            inputPath,
            "--out",
            outPath,
        };
        if (includeTaskId)
        {
            args.Insert(2, "--task-id");
            args.Insert(3, "58");
        }
        var result = RunPythonScript(scriptPath, repoRoot, args.ToArray());

        result.ExitCode.Should().Be(0, "input-driven governance sample should be reproducible by local script");
        File.Exists(outPath).Should().BeTrue("governance sample output should be generated");

        return new GovernanceSampleRun(workingDirectory, outPath, command);
    }

    private static void AssertMinimalEvidenceSummary(JsonElement root)
    {
        var acceptance = root.GetProperty("evidence_summaries").GetProperty("acceptance_check");
        acceptance.GetProperty("status").GetString().Should().NotBeNullOrWhiteSpace();
        acceptance.GetProperty("task_id").GetInt32().Should().BeGreaterThan(0);
        acceptance.GetProperty("generated_at").GetString().Should().NotBeNullOrWhiteSpace();
        acceptance.GetProperty("finding_count").GetInt32().Should().BeGreaterOrEqualTo(0);

        var llmReview = root.GetProperty("evidence_summaries").GetProperty("llm_review");
        llmReview.GetProperty("status").GetString().Should().NotBeNullOrWhiteSpace();
        llmReview.GetProperty("task_id").GetInt32().Should().BeGreaterThan(0);
        llmReview.GetProperty("generated_at").GetString().Should().NotBeNullOrWhiteSpace();
        llmReview.GetProperty("summary_count").GetInt32().Should().BeGreaterOrEqualTo(0);
    }

    private static ProcessResult RunPythonScript(string scriptPath, string workingDirectory, params string[] args)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "py",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = workingDirectory
        };

        startInfo.ArgumentList.Add("-3");
        startInfo.ArgumentList.Add(scriptPath);
        foreach (var arg in args)
        {
            startInfo.ArgumentList.Add(arg);
        }

        using var process = Process.Start(startInfo);
        process.Should().NotBeNull("Python launcher `py` must be available on Windows");
        process!.WaitForExit(30000).Should().BeTrue();
        return new ProcessResult(process.ExitCode, process.StandardOutput.ReadToEnd(), process.StandardError.ReadToEnd());
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

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }

    private static string CreateUniqueTempRoot()
    {
        var path = Path.Combine(Path.GetTempPath(), "task58-governance-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private sealed record ProcessResult(int ExitCode, string StdOut, string StdErr);

    private sealed record GovernanceSampleRun(string WorkingDirectory, string OutputPath, string Command) : IDisposable
    {
        public void Dispose()
        {
            try
            {
                if (Directory.Exists(WorkingDirectory))
                {
                    Directory.Delete(WorkingDirectory, recursive: true);
                }
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
