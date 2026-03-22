using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Collection("Task54QualityGatesSerial")]
public sealed class Task0056AcceptanceTests
{
    // ACC:T56.1
    [Fact]
    public void ShouldReturnNonZero_WhenAuditJsonlContainsInvalidRow()
    {
        var repoRoot = FindRepoRoot();
        var scriptPath = Path.Combine(repoRoot, "scripts", "python", "validate_audit_logs.py");
        var tempRoot = CreateUniqueTempRoot();

        try
        {
            var auditPath = Path.Combine(tempRoot, "security-audit.jsonl");
            var outPath = Path.Combine(tempRoot, "audit-validation.json");

            var validLine = "{\"ts\":\"2026-03-10T00:00:00Z\",\"action\":\"open_url\",\"reason\":\"allowed\",\"target\":\"https://example.com\",\"caller\":\"security_test\"}";
            var invalidLine = "{\"ts\":\"2026-03-10T00:00:01Z\",\"action\":\"open_url\",\"reason\":\"allowed\",\"target\":\"https://example.com\"}";
            File.WriteAllText(auditPath, validLine + Environment.NewLine + invalidLine + Environment.NewLine, Encoding.UTF8);

            var run = RunPy(repoRoot, $"-3 \"{scriptPath}\" --input \"{auditPath}\" --out \"{outPath}\"");

            run.ExitCode.Should().NotBe(0, "any invalid JSONL row must fail validation");
            if (File.Exists(outPath))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(outPath, Encoding.UTF8));
                var root = doc.RootElement;
                var ok = root.TryGetProperty("ok", out var okValue) && okValue.ValueKind == JsonValueKind.True;
                ok.Should().BeFalse("validator output must not mark invalid audit logs as passed");
            }
        }
        finally
        {
            SafeDeleteDirectory(tempRoot);
        }
    }

    // ACC:T56.3
    [Fact]
    public void ShouldWriteExecutedAndPassFailIntoTask0056Summary_WhenAuditValidationEnabled()
    {
        var run = RunQualityGatesWithAuditValidation(enabled: true, fakeAuditValidatorRc: 0);

        run.ExitCode.Should().Be(0, "gate should stay green when all hard checks including audit validation pass");
        File.Exists(run.Task0056Path).Should().BeTrue("task-0056 summary must be emitted when audit validation is enabled");

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var root = doc.RootElement;

        root.TryGetProperty("audit_validation", out var auditValidation).Should().BeTrue();
        auditValidation.TryGetProperty("executed", out var executed).Should().BeTrue();
        auditValidation.TryGetProperty("pass_fail", out var passFail).Should().BeTrue();

        executed.ValueKind.Should().Be(JsonValueKind.True);
        passFail.GetString().Should().Be("pass");
    }

    // ACC:T56.4
    [Fact]
    public void ShouldExitNonZero_WhenAuditValidationEnabledAndValidatorFails()
    {
        var run = RunQualityGatesWithAuditValidation(enabled: true, fakeAuditValidatorRc: 1);

        run.ExitCode.Should().Be(1, "quality gate must fail when enabled audit validation fails");

        if (File.Exists(run.Task0056Path))
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
            var root = doc.RootElement;
            if (root.TryGetProperty("audit_validation", out var auditValidation) &&
                auditValidation.TryGetProperty("pass_fail", out var passFail))
            {
                passFail.GetString().Should().Be("fail");
            }
        }
    }

    // ACC:T56.6
    [Fact]
    public void ShouldWriteSkippedAuditStatus_WhenAuditValidationDisabled()
    {
        var run = RunQualityGatesWithAuditValidation(enabled: false, fakeAuditValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        File.Exists(run.Task0056Path).Should().BeTrue("task-0056 summary must be emitted even when audit validation is disabled");

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var root = doc.RootElement;
        root.TryGetProperty("audit_validation", out var auditValidation).Should().BeTrue();
        auditValidation.GetProperty("enabled").GetBoolean().Should().BeFalse();
        auditValidation.GetProperty("executed").GetBoolean().Should().BeFalse();
        auditValidation.GetProperty("pass_fail").GetString().Should().Be("skipped");
        root.GetProperty("exit_code").GetInt32().Should().Be(0);
    }

    [Fact]
    public void ShouldContainRequiredMetadataAndEvidence_WhenWritingTask0056Summary()
    {
        var run = RunQualityGatesWithAuditValidation(enabled: true, fakeAuditValidatorRc: 0);

        run.ExitCode.Should().Be(0);
        File.Exists(run.Task0056Path).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var root = doc.RootElement;

        root.TryGetProperty("adr_refs", out var adrRefs).Should().BeTrue();
        adrRefs.ValueKind.Should().Be(JsonValueKind.Array);
        adrRefs.GetArrayLength().Should().BeGreaterThan(0);

        root.TryGetProperty("chapter_refs", out var chapterRefs).Should().BeTrue();
        chapterRefs.ValueKind.Should().Be(JsonValueKind.Array);
        chapterRefs.GetArrayLength().Should().BeGreaterThan(0);

        root.TryGetProperty("test_refs", out var testRefs).Should().BeTrue();
        testRefs.ValueKind.Should().Be(JsonValueKind.Array);
        testRefs.GetArrayLength().Should().BeGreaterThan(0);

        root.TryGetProperty("evidence", out var evidence).Should().BeTrue();
        evidence.ValueKind.Should().Be(JsonValueKind.Object);
        evidence.EnumerateObject().Should().NotBeEmpty();
    }

    [Fact]
    public void ShouldFailClosed_WhenTask0056RequiredFieldsAreMissing()
    {
        var run = RunQualityGatesWithAuditValidation(
            enabled: true,
            fakeAuditValidatorRc: 0,
            fakeTask0056MissingFields: true);

        run.ExitCode.Should().Be(1, "record validation must be fail-closed when required fields are missing");
        File.Exists(run.Task0056Path).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(run.Task0056Path, Encoding.UTF8));
        var root = doc.RootElement;
        root.GetProperty("exit_code").GetInt32().Should().Be(1);
        root.GetProperty("record_validation").GetProperty("valid").GetBoolean().Should().BeFalse();
    }

    private static GateRunResult RunQualityGatesWithAuditValidation(
        bool enabled,
        int fakeAuditValidatorRc,
        bool fakeTask0056MissingFields = false)
    {
        var repoRoot = FindRepoRoot();
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
        psi.Environment["QUALITY_GATES_ENABLE_AUDIT_VALIDATION"] = enabled ? "1" : "0";
        psi.Environment["QUALITY_GATES_FAKE_AUDIT_VALIDATOR_RC"] = fakeAuditValidatorRc.ToString();
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

    private static string CreateUniqueTempRoot()
    {
        var path = Path.Combine(Path.GetTempPath(), "newrouge-task0056-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private static void SafeDeleteDirectory(string path)
    {
        if (!Directory.Exists(path))
        {
            return;
        }

        try
        {
            Directory.Delete(path, recursive: true);
        }
        catch
        {
            // Best effort cleanup for test temp folders.
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

