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
    public sealed class Task53HeadlessRunnerArtifactsSummaryTests
    {
        private const string KnownGoodScenePath = "res://Game.Godot/Scenes/Main.tscn";

        // ACC:T53.5
        [Fact]
        public void ShouldEmitSmokeArtifactsAndRunInfo_WhenSmokeRunnerExecutesWithRepoFakeGodot()
        {
            var run = RunSmokeHeadless(strict: true, useRepoFakeGodot: true);

            try
            {
                run.ExitCode.Should().Be(0);
                run.SmokeDirectory.Should().NotBeNull();
                run.SmokeDirectory!.Exists.Should().BeTrue();

                var outLog = Path.Combine(run.SmokeDirectory.FullName, "headless.out.log");
                var errLog = Path.Combine(run.SmokeDirectory.FullName, "headless.err.log");
                var summary = Path.Combine(run.SmokeDirectory.FullName, "summary.json");

                File.Exists(outLog).Should().BeTrue();
                File.Exists(errLog).Should().BeTrue();
                File.Exists(summary).Should().BeTrue();

                var outText = File.ReadAllText(outLog);
                var errText = File.ReadAllText(errLog);
                (outText + Environment.NewLine + errText).Should().NotBeNullOrWhiteSpace(
                    "artifact logs must contain run output for replay and diagnostics");
                outText.Should().Contain("[TEMPLATE_SMOKE_READY]");
                outText.Should().Contain("[DB] opened");

                using var summaryJson = JsonDocument.Parse(File.ReadAllText(summary));
                var root = summaryJson.RootElement;
                root.GetProperty("runId").GetString().Should().NotBeNullOrWhiteSpace();
                root.GetProperty("scene").GetString().Should().Be(KnownGoodScenePath);
                root.GetProperty("command").GetString().Should().Contain("--headless");
                root.GetProperty("exit_code").GetInt32().Should().Be(0);
                root.GetProperty("strict").GetBoolean().Should().BeTrue();
                root.GetProperty("markers").GetProperty("template_smoke_ready").GetBoolean().Should().BeTrue();
                root.GetProperty("artifacts").GetProperty("out_log").GetString().Should().Be(Path.GetRelativePath(run.WorkingDirectory, outLog));
                root.GetProperty("artifacts").GetProperty("err_log").GetString().Should().Be(Path.GetRelativePath(run.WorkingDirectory, errLog));
                root.GetProperty("artifacts").GetProperty("summary_json").GetString().Should().Be(Path.GetRelativePath(run.WorkingDirectory, summary));
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.5
        [Fact]
        public void ShouldPreserveArtifactsAndSummary_WhenStrictRunnerFailsWithoutMarkers()
        {
            var run = RunSmokeHeadless(strict: true, useRepoFakeGodot: false);

            try
            {
                run.ExitCode.Should().Be(1);
                run.SmokeDirectory.Should().NotBeNull();
                run.SmokeDirectory!.Exists.Should().BeTrue();

                var outLog = Path.Combine(run.SmokeDirectory.FullName, "headless.out.log");
                var errLog = Path.Combine(run.SmokeDirectory.FullName, "headless.err.log");
                var summary = Path.Combine(run.SmokeDirectory.FullName, "summary.json");

                File.Exists(outLog).Should().BeTrue();
                File.Exists(errLog).Should().BeTrue();
                File.Exists(summary).Should().BeTrue();

                var outText = File.ReadAllText(outLog);
                var errText = File.ReadAllText(errLog);
                var combined = outText + Environment.NewLine + errText;
                combined.Should().Contain("SMOKE_NO_MARKER");
                combined.Should().NotContain("[TEMPLATE_SMOKE_READY]");
                combined.Should().NotContain("[DB] opened");

                using var summaryJson = JsonDocument.Parse(File.ReadAllText(summary));
                var root = summaryJson.RootElement;
                root.GetProperty("strict").GetBoolean().Should().BeTrue();
                root.GetProperty("markers").GetProperty("template_smoke_ready").GetBoolean().Should().BeFalse();
                root.GetProperty("markers").GetProperty("db_opened").GetBoolean().Should().BeFalse();
                root.GetProperty("markers").GetProperty("any_output").GetBoolean().Should().BeTrue();
                root.GetProperty("exit_code").GetInt32().Should().Be(1);
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.5
        [Fact]
        public void ShouldUseStableArtifactFileNames_WhenSmokeRunDirectoryCreated()
        {
            var run = RunSmokeHeadless(strict: true, useRepoFakeGodot: true);

            try
            {
                var fileNames = Directory
                    .GetFiles(run.SmokeDirectory!.FullName, "*.*", SearchOption.TopDirectoryOnly)
                    .Select(Path.GetFileName)
                    .Where(name => !string.IsNullOrWhiteSpace(name))
                    .Cast<string>()
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);

                fileNames.Should().Contain("headless.out.log");
                fileNames.Should().Contain("headless.err.log");
                fileNames.Should().Contain("headless.log");
                fileNames.Should().Contain("summary.json");
            }
            finally
            {
                run.Dispose();
            }
        }

        private static SmokeRunResult RunSmokeHeadless(bool strict, bool useRepoFakeGodot)
        {
            var repoRoot = FindRepoRoot();
            var script = Path.Combine(repoRoot, "scripts", "python", "smoke_headless.py");
            var workingDirectory = CreateUniqueTempRoot();
            var godotBin = useRepoFakeGodot
                ? Path.Combine(repoRoot, "tools", "fake-godot", "Godot_v4.5.1-stable_mono_win64_console.cmd")
                : CreateFakeGodotScript(
                    workingDirectory,
                    "fake-godot-no-marker.cmd",
                    new[]
                    {
                        "echo SMOKE_NO_MARKER",
                    });

            var args = new List<string>
            {
                "--godot-bin", godotBin,
                "--project-path", ".",
                "--scene", KnownGoodScenePath,
                "--timeout-sec", "2",
            };
            if (strict)
            {
                args.Add("--strict");
            }

            var run = RunPythonScript(script, workingDirectory, args);
            return new SmokeRunResult(
                workingDirectory,
                run.ExitCode,
                run.StdOut,
                run.StdErr,
                FindLatestSmokeRunDirectory(workingDirectory));
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

        private static ProcessResult RunPythonScript(string scriptPath, string workingDirectory, IReadOnlyList<string> args)
        {
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
            foreach (var arg in args)
            {
                startInfo.ArgumentList.Add(arg);
            }

            using var process = Process.Start(startInfo);
            process.Should().NotBeNull();
            process!.WaitForExit(30000).Should().BeTrue();

            return new ProcessResult(
                process.ExitCode,
                process.StandardOutput.ReadToEnd(),
                process.StandardError.ReadToEnd());
        }

        private static DirectoryInfo? FindLatestSmokeRunDirectory(string workingDirectory)
        {
            var ciRoot = Path.Combine(workingDirectory, "logs", "ci");
            if (!Directory.Exists(ciRoot))
            {
                return null;
            }

            return new DirectoryInfo(ciRoot)
                .GetDirectories("*", SearchOption.AllDirectories)
                .Where(d => File.Exists(Path.Combine(d.FullName, "headless.out.log")))
                .OrderByDescending(d => d.FullName, StringComparer.OrdinalIgnoreCase)
                .FirstOrDefault();
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
            var path = Path.Combine(Path.GetTempPath(), "task53-artifacts-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(path);
            return path;
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

        private sealed record SmokeRunResult(
            string WorkingDirectory,
            int ExitCode,
            string StdOut,
            string StdErr,
            DirectoryInfo? SmokeDirectory) : IDisposable
        {
            public void Dispose()
            {
                Task53HeadlessRunnerArtifactsSummaryTests.SafeDeleteDirectory(WorkingDirectory);
            }
        }
    }
}
