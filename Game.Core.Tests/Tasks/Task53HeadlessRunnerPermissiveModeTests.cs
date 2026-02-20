using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task53HeadlessRunnerPermissiveModeTests
{
    private const int RunnerTimeoutMilliseconds = 20000;
    private const string ScriptRelativePath = "scripts/python/smoke_headless.py";
    private const string PowerShellRunnerRelativePath = "scripts/ci/smoke_headless.ps1";

    // ACC:T53.7
    [Fact]
    public void ShouldReturnZeroAndEmitLogsAndSummaryJson_WhenPermissiveModeAndSuccessMarkerMissing()
    {
        var workingDirectory = CreateUniqueTempRoot();

        try
        {
            var runResult = RunSmokeHeadless(workingDirectory, strict: false);

            runResult.ExitCode.Should().Be(0, "permissive mode must not gate on success markers");

            var smokeRunDirectory = FindLatestSmokeRunDirectory(workingDirectory);
            var outLogPath = Path.Combine(smokeRunDirectory, "headless.out.log");
            var errLogPath = Path.Combine(smokeRunDirectory, "headless.err.log");
            var summaryPath = Path.Combine(smokeRunDirectory, "summary.json");

            File.Exists(outLogPath).Should().BeTrue("permissive mode must persist stdout log");
            File.Exists(errLogPath).Should().BeTrue("permissive mode must persist stderr log");

            var combinedText = ReadTextSafe(outLogPath) + Environment.NewLine + ReadTextSafe(errLogPath);
            combinedText.Should().NotContain("[TEMPLATE_SMOKE_READY]");
            combinedText.Should().NotContain("[DB] opened");

            File.Exists(summaryPath).Should().BeTrue(
                "permissive mode must persist summary.json even when success markers are absent");
        }
        finally
        {
            SafeDeleteDirectory(workingDirectory);
        }
    }

    // ACC:T53.6
    [Fact]
    public void ShouldReturnNonZero_WhenStrictModeAndSuccessMarkersAreMissing()
    {
        var workingDirectory = CreateUniqueTempRoot();

        try
        {
            var runResult = RunSmokeHeadless(workingDirectory, strict: true);

            runResult.ExitCode.Should().Be(1, "strict mode must fail without smoke success markers");

            var smokeRunDirectory = FindLatestSmokeRunDirectory(workingDirectory);
            File.Exists(Path.Combine(smokeRunDirectory, "headless.out.log")).Should().BeTrue();
            File.Exists(Path.Combine(smokeRunDirectory, "headless.err.log")).Should().BeTrue();
        }
        finally
        {
            SafeDeleteDirectory(workingDirectory);
        }
    }

    // ACC:T53.6
    [Fact]
    public void ShouldReturnZero_WhenStrictModeAndTemplateMarkerPresent()
    {
        var workingDirectory = CreateUniqueTempRoot();

        try
        {
            var fakeGodot = CreateFakeGodotScript(
                workingDirectory,
                scriptName: "fake-godot-marker.cmd",
                bodyLines: new[] { "echo [TEMPLATE_SMOKE_READY]" });

            var runResult = RunSmokeHeadless(workingDirectory, strict: true, godotBinary: fakeGodot);
            runResult.ExitCode.Should().Be(0);

            var smokeRunDirectory = FindLatestSmokeRunDirectory(workingDirectory);
            using var summary = JsonDocument.Parse(ReadTextSafe(Path.Combine(smokeRunDirectory, "summary.json")));
            summary.RootElement.GetProperty("markers").GetProperty("template_smoke_ready").GetBoolean().Should().BeTrue();
        }
        finally
        {
            SafeDeleteDirectory(workingDirectory);
        }
    }

    // ACC:T53.6
    [Fact]
    public void ShouldReturnZero_WhenStrictModeAndDbOpenedMarkerPresent()
    {
        var workingDirectory = CreateUniqueTempRoot();

        try
        {
            var fakeGodot = CreateFakeGodotScript(
                workingDirectory,
                scriptName: "fake-godot-db.cmd",
                bodyLines: new[] { "echo [DB] opened" });

            var runResult = RunSmokeHeadless(workingDirectory, strict: true, godotBinary: fakeGodot);
            runResult.ExitCode.Should().Be(0);

            var smokeRunDirectory = FindLatestSmokeRunDirectory(workingDirectory);
            using var summary = JsonDocument.Parse(ReadTextSafe(Path.Combine(smokeRunDirectory, "summary.json")));
            summary.RootElement.GetProperty("markers").GetProperty("db_opened").GetBoolean().Should().BeTrue();
        }
        finally
        {
            SafeDeleteDirectory(workingDirectory);
        }
    }

    // ACC:T53.8
    [Fact]
    public void ShouldMatchPowerShellStrictTimeoutSemantics_WhenTimeoutOccursWithoutMarkers()
    {
        var pythonWorkingDirectory = CreateUniqueTempRoot();
        var powerShellWorkingDirectory = CreateUniqueTempRoot();

        try
        {
            var pythonSlowGodot = CreateFakeGodotScript(
                pythonWorkingDirectory,
                scriptName: "fake-godot-slow.cmd",
                bodyLines: new[]
                {
                    "ping 127.0.0.1 -n 6 >nul"
                });
            var powerShellSlowGodot = CreateFakeGodotScript(
                powerShellWorkingDirectory,
                scriptName: "fake-godot-slow.cmd",
                bodyLines: new[]
                {
                    "ping 127.0.0.1 -n 6 >nul"
                });

            var pythonResult = RunSmokeHeadless(pythonWorkingDirectory, strict: true, godotBinary: pythonSlowGodot, timeoutSec: 1);
            var powerShellResult = RunPowerShellSmokeHeadless(powerShellWorkingDirectory, strict: true, godotBinary: powerShellSlowGodot, timeoutSec: 1);

            pythonResult.ExitCode.Should().Be(1, "python strict runner should fail on timeout without markers");
            powerShellResult.ExitCode.Should().Be(1, "powershell strict runner should fail on timeout without markers");

            var pythonSmokeRunDirectory = FindLatestSmokeRunDirectory(pythonWorkingDirectory);
            var powerShellArtifacts = TryParsePowerShellArtifacts(powerShellResult.StdOut);
            powerShellArtifacts.Should().NotBeNull("powershell runner output must expose artifact paths for deterministic assertions");

            File.Exists(Path.Combine(pythonSmokeRunDirectory, "summary.json")).Should().BeTrue();
            File.Exists(powerShellArtifacts!.OutLogPath).Should().BeTrue();
            File.Exists(powerShellArtifacts.ErrLogPath).Should().BeTrue();
            File.Exists(powerShellArtifacts.HeadlessLogPath).Should().BeTrue();

            powerShellArtifacts.OutLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.out\.log$");
            powerShellArtifacts.ErrLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.err\.log$");
            powerShellArtifacts.HeadlessLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.log$");

            Path.GetDirectoryName(powerShellArtifacts.OutLogPath)
                .Should().Be(Path.GetDirectoryName(powerShellArtifacts.ErrLogPath));
            Path.GetDirectoryName(powerShellArtifacts.OutLogPath)
                .Should().Be(Path.GetDirectoryName(powerShellArtifacts.HeadlessLogPath));

            using var pythonSummary = JsonDocument.Parse(ReadTextSafe(Path.Combine(pythonSmokeRunDirectory, "summary.json")));
            pythonSummary.RootElement.GetProperty("strict").GetBoolean().Should().BeTrue();
            pythonSummary.RootElement.GetProperty("exit_code").GetInt32().Should().Be(1);
        }
        finally
        {
            SafeDeleteDirectory(pythonWorkingDirectory);
            SafeDeleteDirectory(powerShellWorkingDirectory);
        }
    }

    // ACC:T53.8
    [Fact]
    public void ShouldMatchPowerShellPermissiveTimeoutSemantics_WhenTimeoutOccursWithoutMarkers()
    {
        var pythonWorkingDirectory = CreateUniqueTempRoot();
        var powerShellWorkingDirectory = CreateUniqueTempRoot();

        try
        {
            var pythonSlowGodot = CreateFakeGodotScript(
                pythonWorkingDirectory,
                scriptName: "fake-godot-slow-permissive.cmd",
                bodyLines: new[]
                {
                    "ping 127.0.0.1 -n 6 >nul"
                });
            var powerShellSlowGodot = CreateFakeGodotScript(
                powerShellWorkingDirectory,
                scriptName: "fake-godot-slow-permissive.cmd",
                bodyLines: new[]
                {
                    "ping 127.0.0.1 -n 6 >nul"
                });

            var pythonResult = RunSmokeHeadless(pythonWorkingDirectory, strict: false, godotBinary: pythonSlowGodot, timeoutSec: 1);
            var powerShellResult = RunPowerShellSmokeHeadless(powerShellWorkingDirectory, strict: false, godotBinary: powerShellSlowGodot, timeoutSec: 1);

            pythonResult.ExitCode.Should().Be(0, "python permissive runner should not fail on timeout without markers");
            powerShellResult.ExitCode.Should().Be(0, "powershell permissive runner should not fail on timeout without markers");

            var pythonSmokeRunDirectory = FindLatestSmokeRunDirectory(pythonWorkingDirectory);
            var powerShellArtifacts = TryParsePowerShellArtifacts(powerShellResult.StdOut);
            powerShellArtifacts.Should().NotBeNull("powershell runner output must expose artifact paths for deterministic assertions");

            File.Exists(Path.Combine(pythonSmokeRunDirectory, "summary.json")).Should().BeTrue();
            File.Exists(powerShellArtifacts!.OutLogPath).Should().BeTrue();
            File.Exists(powerShellArtifacts.ErrLogPath).Should().BeTrue();
            File.Exists(powerShellArtifacts.HeadlessLogPath).Should().BeTrue();

            powerShellArtifacts.OutLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.out\.log$");
            powerShellArtifacts.ErrLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.err\.log$");
            powerShellArtifacts.HeadlessLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.log$");

            using var pythonSummary = JsonDocument.Parse(ReadTextSafe(Path.Combine(pythonSmokeRunDirectory, "summary.json")));
            pythonSummary.RootElement.GetProperty("strict").GetBoolean().Should().BeFalse();
            pythonSummary.RootElement.GetProperty("exit_code").GetInt32().Should().Be(0);
        }
        finally
        {
            SafeDeleteDirectory(pythonWorkingDirectory);
            SafeDeleteDirectory(powerShellWorkingDirectory);
        }
    }

    // ACC:T53.8
    [Fact]
    public void ShouldMatchPowerShellStrictMarkerSemantics_WhenMarkerIsPresentWithoutTimeout()
    {
        var pythonWorkingDirectory = CreateUniqueTempRoot();
        var powerShellWorkingDirectory = CreateUniqueTempRoot();

        try
        {
            var pythonMarkerGodot = CreateFakeGodotScript(
                pythonWorkingDirectory,
                scriptName: "fake-godot-marker.cmd",
                bodyLines: new[]
                {
                    "echo [TEMPLATE_SMOKE_READY]"
                });
            var powerShellMarkerGodot = CreateFakeGodotScript(
                powerShellWorkingDirectory,
                scriptName: "fake-godot-marker.cmd",
                bodyLines: new[]
                {
                    "echo [TEMPLATE_SMOKE_READY]"
                });

            var pythonResult = RunSmokeHeadless(pythonWorkingDirectory, strict: true, godotBinary: pythonMarkerGodot, timeoutSec: 2);
            var powerShellResult = RunPowerShellSmokeHeadless(powerShellWorkingDirectory, strict: true, godotBinary: powerShellMarkerGodot, timeoutSec: 2);

            pythonResult.ExitCode.Should().Be(0, "python strict runner should pass when marker is present");
            powerShellResult.ExitCode.Should().Be(0, "powershell strict runner should pass when marker is present");

            var pythonSmokeRunDirectory = FindLatestSmokeRunDirectory(pythonWorkingDirectory);
            var powerShellArtifacts = TryParsePowerShellArtifacts(powerShellResult.StdOut);
            powerShellArtifacts.Should().NotBeNull();

            using var pythonSummary = JsonDocument.Parse(ReadTextSafe(Path.Combine(pythonSmokeRunDirectory, "summary.json")));
            pythonSummary.RootElement.GetProperty("strict").GetBoolean().Should().BeTrue();
            pythonSummary.RootElement.GetProperty("exit_code").GetInt32().Should().Be(0);
            pythonSummary.RootElement.GetProperty("markers").GetProperty("template_smoke_ready").GetBoolean().Should().BeTrue();

            var powerShellOut = ReadTextSafe(powerShellArtifacts!.OutLogPath);
            powerShellOut.Should().Contain("[TEMPLATE_SMOKE_READY]");
            powerShellArtifacts.OutLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.out\.log$");
            powerShellArtifacts.ErrLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.err\.log$");
        }
        finally
        {
            SafeDeleteDirectory(pythonWorkingDirectory);
            SafeDeleteDirectory(powerShellWorkingDirectory);
        }
    }

    // ACC:T53.8
    [Fact]
    public void ShouldMatchPowerShellPermissiveAnyOutputSemantics_WhenOutputHasNoMarkers()
    {
        var pythonWorkingDirectory = CreateUniqueTempRoot();
        var powerShellWorkingDirectory = CreateUniqueTempRoot();

        try
        {
            var pythonOutputGodot = CreateFakeGodotScript(
                pythonWorkingDirectory,
                scriptName: "fake-godot-any-output.cmd",
                bodyLines: new[]
                {
                    "echo SMOKE_ANY_OUTPUT",
                });
            var powerShellOutputGodot = CreateFakeGodotScript(
                powerShellWorkingDirectory,
                scriptName: "fake-godot-any-output.cmd",
                bodyLines: new[]
                {
                    "echo SMOKE_ANY_OUTPUT",
                });

            var pythonResult = RunSmokeHeadless(pythonWorkingDirectory, strict: false, godotBinary: pythonOutputGodot, timeoutSec: 2);
            var powerShellResult = RunPowerShellSmokeHeadless(powerShellWorkingDirectory, strict: false, godotBinary: powerShellOutputGodot, timeoutSec: 2);

            pythonResult.ExitCode.Should().Be(0, "python permissive runner should pass on any output");
            powerShellResult.ExitCode.Should().Be(0, "powershell permissive runner should pass on any output");

            var pythonSmokeRunDirectory = FindLatestSmokeRunDirectory(pythonWorkingDirectory);
            var powerShellArtifacts = TryParsePowerShellArtifacts(powerShellResult.StdOut);
            powerShellArtifacts.Should().NotBeNull();

            using var pythonSummary = JsonDocument.Parse(ReadTextSafe(Path.Combine(pythonSmokeRunDirectory, "summary.json")));
            pythonSummary.RootElement.GetProperty("strict").GetBoolean().Should().BeFalse();
            pythonSummary.RootElement.GetProperty("exit_code").GetInt32().Should().Be(0);
            pythonSummary.RootElement.GetProperty("markers").GetProperty("template_smoke_ready").GetBoolean().Should().BeFalse();
            pythonSummary.RootElement.GetProperty("markers").GetProperty("db_opened").GetBoolean().Should().BeFalse();
            pythonSummary.RootElement.GetProperty("markers").GetProperty("any_output").GetBoolean().Should().BeTrue();

            var powerShellCombined = ReadTextSafe(powerShellArtifacts!.OutLogPath) + Environment.NewLine + ReadTextSafe(powerShellArtifacts.ErrLogPath);
            powerShellCombined.Should().Contain("SMOKE_ANY_OUTPUT");
            powerShellArtifacts.OutLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.out\.log$");
            powerShellArtifacts.ErrLogPath.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}[\\/]headless\.err\.log$");
        }
        finally
        {
            SafeDeleteDirectory(pythonWorkingDirectory);
            SafeDeleteDirectory(powerShellWorkingDirectory);
        }
    }

    private static ProcessResult RunSmokeHeadless(string workingDirectory, bool strict, string? godotBinary = null, int timeoutSec = 1)
    {
        var repoRoot = FindRepoRoot();
        var scriptPath = Path.Combine(repoRoot, ScriptRelativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
        File.Exists(scriptPath).Should().BeTrue("smoke_headless.py must exist for Task53 acceptance tests");

        var fakeGodotBinary = string.IsNullOrWhiteSpace(godotBinary)
            ? Path.Combine(Environment.SystemDirectory, "where.exe")
            : godotBinary;
        File.Exists(fakeGodotBinary).Should().BeTrue("where.exe must exist on Windows for deterministic smoke simulation");

        var startInfo = new ProcessStartInfo
        {
            FileName = "py",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = workingDirectory,
        };

        startInfo.ArgumentList.Add("-3");
        startInfo.ArgumentList.Add(scriptPath);
        startInfo.ArgumentList.Add("--godot-bin");
        startInfo.ArgumentList.Add(fakeGodotBinary);
        startInfo.ArgumentList.Add("--project-path");
        startInfo.ArgumentList.Add(".");
        startInfo.ArgumentList.Add("--scene");
        startInfo.ArgumentList.Add("res://Game.Godot/Scenes/Main.tscn");
        startInfo.ArgumentList.Add("--timeout-sec");
        startInfo.ArgumentList.Add(timeoutSec.ToString());
        if (strict)
        {
            startInfo.ArgumentList.Add("--strict");
        }

        using var process = Process.Start(startInfo);
        process.Should().NotBeNull("Python launcher `py` must be available on Windows");

        process!.WaitForExit(RunnerTimeoutMilliseconds)
            .Should().BeTrue("smoke_headless.py should finish within the test timeout");

        var standardOutput = process.StandardOutput.ReadToEnd();
        var standardError = process.StandardError.ReadToEnd();

        return new ProcessResult(process.ExitCode, standardOutput, standardError);
    }

    private static ProcessResult RunPowerShellSmokeHeadless(string workingDirectory, bool strict, string godotBinary, int timeoutSec)
    {
        var repoRoot = FindRepoRoot();
        var scriptPath = Path.Combine(repoRoot, PowerShellRunnerRelativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
        File.Exists(scriptPath).Should().BeTrue("smoke_headless.ps1 must exist for semantics alignment check");

        var startInfo = new ProcessStartInfo
        {
            FileName = "powershell",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = workingDirectory,
        };

        startInfo.ArgumentList.Add("-NoProfile");
        startInfo.ArgumentList.Add("-ExecutionPolicy");
        startInfo.ArgumentList.Add("Bypass");
        startInfo.ArgumentList.Add("-File");
        startInfo.ArgumentList.Add(scriptPath);
        startInfo.ArgumentList.Add("-GodotBin");
        startInfo.ArgumentList.Add(godotBinary);
        startInfo.ArgumentList.Add("-ProjectPath");
        startInfo.ArgumentList.Add(".");
        startInfo.ArgumentList.Add("-Scene");
        startInfo.ArgumentList.Add("res://Game.Godot/Scenes/Main.tscn");
        startInfo.ArgumentList.Add("-TimeoutSec");
        startInfo.ArgumentList.Add(timeoutSec.ToString());
        if (strict)
        {
            startInfo.ArgumentList.Add("-Strict");
        }

        using var process = Process.Start(startInfo);
        process.Should().NotBeNull();
        process!.WaitForExit(RunnerTimeoutMilliseconds).Should().BeTrue();

        return new ProcessResult(
            process.ExitCode,
            process.StandardOutput.ReadToEnd(),
            process.StandardError.ReadToEnd());
    }

    private static string CreateFakeGodotScript(string workingDirectory, string scriptName, IReadOnlyList<string> bodyLines)
    {
        var scriptPath = Path.Combine(workingDirectory, scriptName);
        var lines = new List<string> { "@echo off", "setlocal" };
        lines.AddRange(bodyLines);
        lines.Add("exit /b 0");
        File.WriteAllLines(scriptPath, lines);
        return scriptPath;
    }

    private static string FindLatestSmokeRunDirectory(string workingDirectory)
    {
        var ciRoot = Path.Combine(workingDirectory, "logs", "ci");
        Directory.Exists(ciRoot).Should().BeTrue("smoke run should create logs/ci");

        var runDirectories = Directory
            .GetFiles(ciRoot, "headless.out.log", SearchOption.AllDirectories)
            .Select(Path.GetDirectoryName)
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Cast<string>()
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderByDescending(path => path, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        runDirectories.Should().NotBeEmpty("smoke run should create a timestamped artifact directory");
        return runDirectories[0];
    }

    private static PowerShellArtifacts? TryParsePowerShellArtifacts(string stdOut)
    {
        if (string.IsNullOrWhiteSpace(stdOut))
        {
            return null;
        }

        var match = Regex.Match(
            stdOut,
            @"Smoke log saved at (?<log>.+?) \(out=(?<out>.+?), err=(?<err>.+?)\)",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        if (!match.Success)
        {
            return null;
        }

        return new PowerShellArtifacts(
            match.Groups["log"].Value.Trim(),
            match.Groups["out"].Value.Trim(),
            match.Groups["err"].Value.Trim());
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

    private static string CreateUniqueTempRoot()
    {
        var path = Path.Combine(Path.GetTempPath(), "task53-headless-permissive-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private static string ReadTextSafe(string path)
    {
        try
        {
            return File.ReadAllText(path);
        }
        catch (IOException)
        {
            return string.Empty;
        }
        catch (UnauthorizedAccessException)
        {
            return string.Empty;
        }
    }

    private static void SafeDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private sealed record ProcessResult(int ExitCode, string StdOut, string StdErr);
    private sealed record PowerShellArtifacts(string HeadlessLogPath, string OutLogPath, string ErrLogPath);
}
