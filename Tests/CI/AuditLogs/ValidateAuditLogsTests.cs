using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Tests.CI.AuditLogs;

public sealed class ValidateAuditLogsTests
{
    private static readonly string[] RequiredAdrRefs = { "ADR-0019", "ADR-0003", "ADR-0005" };
    private static readonly string[] RequiredChapterRefs = { "CH02", "CH03", "CH07" };
    private static readonly string[] RequiredEvidenceRefs =
    {
        "Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs",
        "Tests/CI/AuditLogs/ValidateAuditLogsTests.cs",
        "Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs",
        "Game.Core.Tests/Tasks/Task56QualityGateAuditIntegrationTests.cs",
        "logs/ci/task-0056-summary.json",
        "logs/ci/security-audit.jsonl",
    };

    // ACC:T56.2
    [Fact]
    public void ShouldReportLineNumbersAndFixReasons_WhenAuditValidatorProcessesInvalidFixture()
    {
        var repoRoot = FindRepoRoot();
        var invalidFixture = Path.Combine(repoRoot, "Tests", "CI", "AuditLogs", "Fixtures", "invalid-audit.jsonl");
        var outPath = CreateTempFilePath("task56-invalid-summary", ".json");

        try
        {
            var run = RunPy(
                repoRoot,
                $"-3 scripts/python/validate_audit_logs.py --input \"{invalidFixture}\" --out \"{outPath}\"");

            run.ExitCode.Should().NotBe(0);
            File.Exists(outPath).Should().BeTrue();

            using var doc = JsonDocument.Parse(File.ReadAllText(outPath, Encoding.UTF8));
            var root = doc.RootElement;
            root.GetProperty("ok").GetBoolean().Should().BeFalse();
            var issues = root.GetProperty("issues").EnumerateArray().ToList();
            issues.Should().NotBeEmpty();
            issues.Any(x => x.GetProperty("line").GetInt32() == 2).Should().BeTrue();
            issues.Any(x => x.GetProperty("line").GetInt32() == 3).Should().BeTrue();
            issues.All(x => x.TryGetProperty("fix", out _)).Should().BeTrue();
        }
        finally
        {
            SafeDeleteFile(outPath);
        }
    }

    // ACC:T56.5
    [Fact]
    public void ShouldReproducePassAndFailRuns_WhenUsingRealJsonlFixtures()
    {
        var repoRoot = FindRepoRoot();
        var validFixture = Path.Combine(repoRoot, "Tests", "CI", "AuditLogs", "Fixtures", "valid-audit.jsonl");
        var invalidFixture = Path.Combine(repoRoot, "Tests", "CI", "AuditLogs", "Fixtures", "invalid-audit.jsonl");
        var validOut = CreateTempFilePath("task56-valid-summary", ".json");
        var invalidOut = CreateTempFilePath("task56-invalid-summary", ".json");

        try
        {
            var validRun = RunPy(
                repoRoot,
                $"-3 scripts/python/validate_audit_logs.py --input \"{validFixture}\" --out \"{validOut}\"");
            var invalidRun = RunPy(
                repoRoot,
                $"-3 scripts/python/validate_audit_logs.py --input \"{invalidFixture}\" --out \"{invalidOut}\"");

            validRun.ExitCode.Should().Be(0);
            invalidRun.ExitCode.Should().NotBe(0);

            using var validDoc = JsonDocument.Parse(File.ReadAllText(validOut, Encoding.UTF8));
            using var invalidDoc = JsonDocument.Parse(File.ReadAllText(invalidOut, Encoding.UTF8));
            validDoc.RootElement.GetProperty("ok").GetBoolean().Should().BeTrue();
            invalidDoc.RootElement.GetProperty("ok").GetBoolean().Should().BeFalse();
        }
        finally
        {
            SafeDeleteFile(validOut);
            SafeDeleteFile(invalidOut);
        }
    }

    // ACC:T56.4
    [Fact]
    public void ShouldReturnNonZeroExitCode_WhenAuditValidationEnabledAndValidatorFails()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: true, fakeValidatorRc: 1);

        run.ExitCode.Should().Be(1);
        File.Exists(run.Task0056Path).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var audit = doc.RootElement.GetProperty("audit_validation");
        audit.GetProperty("enabled").GetBoolean().Should().BeTrue();
        audit.GetProperty("executed").GetBoolean().Should().BeTrue();
        audit.GetProperty("pass_fail").GetString().Should().Be("fail");
    }

    // ACC:T56.6
    [Fact]
    public void ShouldSkipAuditValidator_WhenAuditValidationDisabled()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: false, fakeValidatorRc: 1);

        run.ExitCode.Should().Be(0);
        File.Exists(run.Task0056Path).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var audit = doc.RootElement.GetProperty("audit_validation");
        audit.GetProperty("enabled").GetBoolean().Should().BeFalse();
        audit.GetProperty("executed").GetBoolean().Should().BeFalse();
        audit.GetProperty("pass_fail").GetString().Should().Be("skipped");
    }

    // ACC:T56.9
    [Fact]
    public void ShouldContainRequiredEvidenceEntries_WhenTask0056RecordIsGenerated()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: true, fakeValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var evidence = doc.RootElement.GetProperty("evidence");
        var keys = evidence.EnumerateObject().Select(x => x.Name).ToArray();

        keys.Should().Contain(RequiredEvidenceRefs);
    }

    // ACC:T56.10
    [Fact]
    public void ShouldContainAllRequiredAdrRefs_WhenTask0056RecordIsGenerated()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: true, fakeValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var adrRefs = doc.RootElement.GetProperty("adr_refs").EnumerateArray().Select(x => x.GetString()).Where(x => x is not null).Cast<string>().ToArray();
        adrRefs.Should().Contain(RequiredAdrRefs);
    }

    // ACC:T56.11
    [Fact]
    public void ShouldContainAllRequiredChapterRefs_WhenTask0056RecordIsGenerated()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: true, fakeValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var chapterRefs = doc.RootElement.GetProperty("chapter_refs").EnumerateArray().Select(x => x.GetString()).Where(x => x is not null).Cast<string>().ToArray();
        chapterRefs.Should().Contain(RequiredChapterRefs);
    }

    // ACC:T56.12
    [Fact]
    public void ShouldRequireArtifactEvidenceRefs_WhenTask0056RecordIsGenerated()
    {
        var run = RunQualityGates(repoRoot: FindRepoRoot(), enableAuditValidation: true, fakeValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var testRefs = doc.RootElement.GetProperty("test_refs").EnumerateArray().Select(x => x.GetString()).Where(x => x is not null).Cast<string>().ToArray();

        testRefs.Should().Contain("logs/ci/task-0056-summary.json");
        testRefs.Should().Contain("logs/ci/security-audit.jsonl");
    }

    // ACC:T56.13
    [Fact]
    public void ShouldFailClosed_WhenTask0056RequiredFieldsAreMissing()
    {
        var run = RunQualityGates(
            repoRoot: FindRepoRoot(),
            enableAuditValidation: true,
            fakeValidatorRc: 0,
            fakeTask0056MissingFields: true);

        run.ExitCode.Should().Be(1);
        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var root = doc.RootElement;
        root.GetProperty("record_validation").GetProperty("valid").GetBoolean().Should().BeFalse();
        root.GetProperty("exit_code").GetInt32().Should().Be(1);
    }

    private static GateRunResult RunQualityGates(
        string repoRoot,
        bool enableAuditValidation,
        int fakeValidatorRc,
        bool fakeTask0056MissingFields = false)
    {
        var date = DateTime.Today.ToString("yyyy-MM-dd");
        var task0056Path = Path.Combine(repoRoot, "logs", "ci", date, "task-0056.json");
        if (File.Exists(task0056Path))
        {
            File.Delete(task0056Path);
        }

        var psi = new ProcessStartInfo
        {
            FileName = "py",
            Arguments = "-3 scripts/python/quality_gates.py all --godot-bin MOCK_GODOT --security-profile host-safe --no-require-lock-files",
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };

        psi.Environment["QUALITY_GATES_SKIP_PREREQS"] = "1";
        psi.Environment["QUALITY_GATES_FAKE_CI_RC"] = "0";
        psi.Environment["QUALITY_GATES_ENABLE_AUDIT_VALIDATION"] = enableAuditValidation ? "1" : "0";
        psi.Environment["QUALITY_GATES_FAKE_AUDIT_VALIDATOR_RC"] = fakeValidatorRc.ToString();
        if (fakeTask0056MissingFields)
        {
            psi.Environment["QUALITY_GATES_FAKE_TASK0056_MISSING_FIELDS"] = "1";
        }

        using var process = Process.Start(psi);
        process.Should().NotBeNull();
        var stdout = process!.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        return new GateRunResult(process.ExitCode, stdout, stderr, task0056Path);
    }

    private static ProcessResult RunPy(string repoRoot, string arguments)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "py",
            Arguments = arguments,
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };

        using var process = Process.Start(psi);
        process.Should().NotBeNull();
        var stdout = process!.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        return new ProcessResult(process.ExitCode, stdout, stderr);
    }

    private static string CreateTempFilePath(string stem, string ext)
    {
        var folder = Path.Combine(Path.GetTempPath(), "newrouge-task56-fixtures");
        Directory.CreateDirectory(folder);
        return Path.Combine(folder, stem + "-" + Guid.NewGuid().ToString("N") + ext);
    }

    private static void SafeDeleteFile(string path)
    {
        if (!File.Exists(path))
        {
            return;
        }

        try
        {
            File.Delete(path);
        }
        catch
        {
            // Best effort cleanup for temp files.
        }
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

    private sealed record ProcessResult(int ExitCode, string StdOut, string StdErr);

    private sealed record GateRunResult(int ExitCode, string StdOut, string StdErr, string Task0056Path);
}
