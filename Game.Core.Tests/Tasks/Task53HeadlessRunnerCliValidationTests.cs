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
    public sealed class Task53HeadlessRunnerCliValidationTests
    {
        private const int RunnerTaskId = 53;
        private const string KnownGoodScenePath = "res://Game.Godot/Scenes/Main.tscn";
        private static readonly string[] ExpectedTask53TestRefs =
        {
            "Game.Core.Tests/Tasks/Task53HeadlessRunnerCliValidationTests.cs",
            "Game.Core.Tests/Tasks/Task53HeadlessRunnerArtifactsSummaryTests.cs",
            "Game.Core.Tests/Tasks/Task53HeadlessRunnerPermissiveModeTests.cs",
        };

        // ACC:T53.1
        [Fact]
        public void ShouldWriteTaskSummaryJsonUnderLogsCiDateFolder_WhenSmokeRunCompletes()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true);

            try
            {
                run.ExitCode.Should().Be(0);
                run.TaskSummaryPath.Should().NotBeNull();
                run.TaskSummaryPath!.Exists.Should().BeTrue();
                run.TaskSummaryPath.FullName.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]task-0053\.json$");
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.2
        [Fact]
        public void ShouldRecordCommandExitCodeAndArtifactPaths_WhenTaskSummaryGenerated()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true);

            try
            {
                using var taskJson = JsonDocument.Parse(File.ReadAllText(run.TaskSummaryPath!.FullName));
                var root = taskJson.RootElement;

                root.GetProperty("platform").GetString().Should().Be("windows");
                root.GetProperty("command").GetString().Should().Contain("py -3 scripts/python/smoke_headless.py");
                root.GetProperty("exit_code").GetInt32().Should().Be(run.ExitCode);

                var artifacts = root.GetProperty("artifacts");
                artifacts.GetProperty("headless_out_log").GetString().Should().NotBeNullOrWhiteSpace();
                artifacts.GetProperty("headless_err_log").GetString().Should().NotBeNullOrWhiteSpace();
                artifacts.GetProperty("summary_json").GetString().Should().NotBeNullOrWhiteSpace();
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.3
        [Fact]
        public void ShouldReferenceTask53TestRefsInOverlayDocs_WhenOverlayUpdated()
        {
            var repoRoot = FindRepoRoot();
            var overlayIndex = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "_index.md"));
            var featureSlice = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "08-Feature-Slice-M1-Warrior.md"));
            var checklist = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "ACCEPTANCE_CHECKLIST.md"));

            AssertContainsAllRefs(repoRoot, overlayIndex, ExpectedTask53TestRefs);
            AssertContainsAllRefs(repoRoot, featureSlice, ExpectedTask53TestRefs);
            AssertContainsAllRefs(repoRoot, checklist, ExpectedTask53TestRefs);
        }

        // ACC:T53.4
        [Fact]
        public void ShouldReturnReadableErrorsForMissingOrInvalidArguments_WhenRunnerInvokedFromCli()
        {
            var repoRoot = FindRepoRoot();
            var script = Path.Combine(repoRoot, "scripts", "python", "smoke_headless.py");
            var fakeGodot = Path.Combine(repoRoot, "tools", "fake-godot", "Godot_v4.5.1-stable_mono_win64_console.cmd");
            var workingDirectory = CreateUniqueTempRoot();

            try
            {
                var help = RunPythonScript(script, workingDirectory, new[] { "--help" });
                help.ExitCode.Should().Be(0);
                help.StdOut.Should().Contain("--godot-bin");
                help.StdOut.Should().Contain("--scene");
                help.StdOut.Should().Contain("--timeout-sec");
                help.StdOut.Should().Contain("--project-path");
                help.StdOut.Should().Contain("--strict");

                var missingGodot = RunPythonScript(script, workingDirectory, new[] { "--scene", KnownGoodScenePath, "--timeout-sec", "2", "--project-path", "." });
                missingGodot.ExitCode.Should().BeGreaterThan(0);
                missingGodot.StdErr.ToLowerInvariant().Should().Contain("required");

                var invalidGodotPath = RunPythonScript(script, workingDirectory, new[] { "--godot-bin", "not-exists-godot.exe", "--scene", KnownGoodScenePath, "--timeout-sec", "2", "--project-path", "." });
                invalidGodotPath.ExitCode.Should().BeGreaterThan(0);
                invalidGodotPath.StdErr.Should().Contain("GODOT_BIN not found");

                var invalidTimeout = RunPythonScript(script, workingDirectory, new[] { "--godot-bin", fakeGodot, "--scene", KnownGoodScenePath, "--timeout-sec", "0", "--project-path", "." });
                invalidTimeout.ExitCode.Should().BeGreaterThan(0);
                invalidTimeout.StdErr.ToLowerInvariant().Should().Contain("timeout-sec");

                var invalidProjectPath = RunPythonScript(script, workingDirectory, new[] { "--godot-bin", fakeGodot, "--scene", KnownGoodScenePath, "--timeout-sec", "2", "--project-path", "not-exists-dir" });
                invalidProjectPath.ExitCode.Should().BeGreaterThan(0);
                invalidProjectPath.StdErr.ToLowerInvariant().Should().Contain("project-path");
            }
            finally
            {
                SafeDeleteDirectory(workingDirectory);
            }
        }

        // ACC:T53.9
        [Fact]
        public void ShouldPersistLocalWindowsEvidenceInTaskSummary_WhenSmokeExecutes()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true);

            try
            {
                using var taskJson = JsonDocument.Parse(File.ReadAllText(run.TaskSummaryPath!.FullName));
                var root = taskJson.RootElement;
                root.GetProperty("platform").GetString().Should().Be("windows");
                root.GetProperty("runner").GetString().Should().Contain("scripts/python/smoke_headless.py");
                root.GetProperty("exit_code").GetInt32().Should().Be(run.ExitCode);
                root.GetProperty("known_good_scene").GetString().Should().MatchRegex(@"^res://.+\.tscn$");

                var verification = root.GetProperty("verification");
                verification.GetProperty("headless_out_log_exists").GetBoolean().Should().BeTrue();
                verification.GetProperty("headless_err_log_exists").GetBoolean().Should().BeTrue();
                verification.GetProperty("summary_json_exists").GetBoolean().Should().BeTrue();
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.10
        [Fact]
        public void ShouldArchiveSmokeArtifactsUnderLogsCi_WhenSmokeExecutes()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true);

            try
            {
                run.SmokeDirectory.Should().NotBeNull();
                run.SmokeDirectory!.Exists.Should().BeTrue();
                run.SmokeDirectory.FullName.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]smoke[\\/]\d{8}-\d{6}$");
                File.Exists(Path.Combine(run.SmokeDirectory.FullName, "headless.out.log")).Should().BeTrue();
                File.Exists(Path.Combine(run.SmokeDirectory.FullName, "headless.err.log")).Should().BeTrue();
                File.Exists(Path.Combine(run.SmokeDirectory.FullName, "summary.json")).Should().BeTrue();
                run.TaskSummaryPath.Should().NotBeNull();
                run.TaskSummaryPath!.FullName.Should().MatchRegex(@"[\\/]logs[\\/]ci[\\/]\d{4}-\d{2}-\d{2}[\\/]task-0053\.json$");

                var smokeDateDirectory = run.SmokeDirectory.Parent?.Parent;
                smokeDateDirectory.Should().NotBeNull("smoke artifacts must be archived under logs/ci/<date>/smoke/<timestamp>");
                Path.GetDirectoryName(run.TaskSummaryPath.FullName)
                    .Should().Be(smokeDateDirectory!.FullName);
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.11
        [Fact]
        public void ShouldRecordAdrRefsInTaskMetadata_WhenTask53Loaded()
        {
            var task = LoadMasterTask53();
            var details = task.GetProperty("details").GetString() ?? string.Empty;

            details.Should().Contain("ADR-0005");
            details.Should().Contain("ADR-0011");
            details.Should().Contain("ADR-0018");
            details.Should().Contain("ADR-0024");
        }

        // ACC:T53.12
        [Fact]
        public void ShouldRecordChapterAlignmentInTaskMetadata_WhenTask53Loaded()
        {
            var task = LoadMasterTask53();
            var details = task.GetProperty("details").GetString() ?? string.Empty;

            details.Should().Contain("CH01");
            details.Should().Contain("CH06");
            details.Should().Contain("CH07");
            details.Should().Contain("CH10");
        }

        // ACC:T53.13
        [Fact]
        public void ShouldListTask53TestRefsInAcceptanceChecklist_WhenChecklistMaintained()
        {
            var repoRoot = FindRepoRoot();
            var checklist = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "ACCEPTANCE_CHECKLIST.md"));

            checklist.Should().Contain("logs/ci/<date>/task-0053.json");
            checklist.Should().Contain("logs/ci/<date>/smoke/<timestamp>/headless.out.log");
            checklist.Should().Contain("logs/ci/<date>/smoke/<timestamp>/headless.err.log");
            checklist.Should().Contain("logs/ci/<date>/smoke/<timestamp>/summary.json");
            AssertContainsAllRefs(repoRoot, checklist, ExpectedTask53TestRefs);
        }

        // ACC:T53.14
        [Fact]
        public void ShouldFailWhenKnownGoodScenePathIsMissing_WhenRunnerInvoked()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true, scene: "Scenes/Main.tscn");

            try
            {
                run.ExitCode.Should().BeGreaterThan(0);
                run.StdErr.ToLowerInvariant().Should().Contain("known-good");
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.15
        [Fact]
        public void ShouldIncludeCommandExitAndArtifactVerificationInTaskSummary_WhenKnownGoodRunCompletes()
        {
            var run = RunSmokeHeadlessWithRepoFake(strict: true);

            try
            {
                using var taskJson = JsonDocument.Parse(File.ReadAllText(run.TaskSummaryPath!.FullName));
                var root = taskJson.RootElement;
                var verification = root.GetProperty("verification");

                root.GetProperty("command").GetString().Should().Contain("smoke_headless.py");
                root.GetProperty("exit_code").GetInt32().Should().Be(run.ExitCode);
                verification.GetProperty("headless_out_log_exists").GetBoolean().Should().BeTrue();
                verification.GetProperty("headless_err_log_exists").GetBoolean().Should().BeTrue();
                verification.GetProperty("summary_json_exists").GetBoolean().Should().BeTrue();
            }
            finally
            {
                run.Dispose();
            }
        }

        // ACC:T53.16
        [Fact]
        public void ShouldIncludeTask53BackLinkAndStrictNonStrictRulesInOverlayIndex_WhenDocsSynced()
        {
            var repoRoot = FindRepoRoot();
            var overlayIndex = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "_index.md"));

            overlayIndex.Should().Contain("Task53");
            overlayIndex.ToLowerInvariant().Should().Contain("strict");
            overlayIndex.ToLowerInvariant().Should().Contain("non-strict");
            overlayIndex.Should().Contain("task-0053.json");
            overlayIndex.Should().Contain("headless.out.log");
            overlayIndex.Should().Contain("headless.err.log");
            overlayIndex.Should().Contain("summary.json");
        }

        // ACC:T53.17
        [Fact]
        public void ShouldAlignFeatureSliceWithChecklistForTask53Refs_WhenAcceptanceConcluded()
        {
            var repoRoot = FindRepoRoot();
            var featureSlice = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "08-Feature-Slice-M1-Warrior.md"));
            var checklist = File.ReadAllText(Path.Combine(repoRoot, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "ACCEPTANCE_CHECKLIST.md"));

            featureSlice.Should().Contain("Task53");
            checklist.Should().Contain("Task53");
            featureSlice.Should().Contain("task-0053.json");
            checklist.Should().Contain("logs/ci/<date>/task-0053.json");
            featureSlice.ToLowerInvariant().Should().Contain("strict/non-strict");
            AssertContainsAllRefs(repoRoot, featureSlice, ExpectedTask53TestRefs);
            AssertContainsAllRefs(repoRoot, checklist, ExpectedTask53TestRefs);
        }

        private static SmokeRunResult RunSmokeHeadlessWithRepoFake(bool strict, string? scene = null)
        {
            var repoRoot = FindRepoRoot();
            var script = Path.Combine(repoRoot, "scripts", "python", "smoke_headless.py");
            var fakeGodot = Path.Combine(repoRoot, "tools", "fake-godot", "Godot_v4.5.1-stable_mono_win64_console.cmd");
            var workingDirectory = CreateUniqueTempRoot();
            var effectiveScene = string.IsNullOrWhiteSpace(scene) ? KnownGoodScenePath : scene;

            var args = new[]
            {
                "--godot-bin", fakeGodot,
                "--project-path", ".",
                "--scene", effectiveScene!,
                "--timeout-sec", "2",
                "--task-id", RunnerTaskId.ToString()
            }.ToList();
            if (strict)
            {
                args.Add("--strict");
            }

            var run = RunPythonScript(script, workingDirectory, args.ToArray());
            return new SmokeRunResult(
                workingDirectory,
                run.ExitCode,
                run.StdOut,
                run.StdErr,
                FindLatestSmokeRunDirectory(workingDirectory),
                FindTaskSummaryPath(workingDirectory));
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
            process.Should().NotBeNull("Python launcher `py` must be available on Windows");
            process!.WaitForExit(30000).Should().BeTrue();

            return new ProcessResult(
                process.ExitCode,
                process.StandardOutput.ReadToEnd(),
                process.StandardError.ReadToEnd());
        }

        private static void AssertContainsAllRefs(string repoRoot, string text, IEnumerable<string> expectedRefs)
        {
            foreach (var reference in expectedRefs)
            {
                text.Should().Contain(reference);
                var normalizedPath = Path.Combine(
                    repoRoot,
                    reference.Replace("/", Path.DirectorySeparatorChar.ToString()));
                File.Exists(normalizedPath).Should().BeTrue($"referenced test file should exist: {reference}");
            }
        }

        private static JsonElement LoadMasterTask53()
        {
            var repoRoot = FindRepoRoot();
            var tasksPath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks.json");
            using var doc = JsonDocument.Parse(File.ReadAllText(tasksPath));
            var tasks = doc.RootElement.GetProperty("master").GetProperty("tasks");
            foreach (var task in tasks.EnumerateArray())
            {
                if (task.GetProperty("id").GetInt32() == 53)
                {
                    return task.Clone();
                }
            }

            throw new InvalidOperationException("Task 53 not found in tasks.json.");
        }

        private static DirectoryInfo? FindLatestSmokeRunDirectory(string workingDirectory)
        {
            var ciRoot = Path.Combine(workingDirectory, "logs", "ci");
            if (!Directory.Exists(ciRoot))
            {
                return null;
            }

            var candidates = new DirectoryInfo(ciRoot)
                .GetDirectories("*", SearchOption.AllDirectories)
                .Where(d => File.Exists(Path.Combine(d.FullName, "headless.out.log")))
                .OrderByDescending(d => d.FullName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            return candidates.FirstOrDefault();
        }

        private static FileInfo? FindTaskSummaryPath(string workingDirectory)
        {
            var ciRoot = Path.Combine(workingDirectory, "logs", "ci");
            if (!Directory.Exists(ciRoot))
            {
                return null;
            }

            var files = Directory.GetFiles(ciRoot, "task-0053.json", SearchOption.AllDirectories);
            if (files.Length == 0)
            {
                return null;
            }

            Array.Sort(files, StringComparer.OrdinalIgnoreCase);
            return new FileInfo(files[^1]);
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
            var path = Path.Combine(Path.GetTempPath(), "task53-cli-validation-" + Guid.NewGuid().ToString("N"));
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
            DirectoryInfo? SmokeDirectory,
            FileInfo? TaskSummaryPath) : IDisposable
        {
            public void Dispose()
            {
                Task53HeadlessRunnerCliValidationTests.SafeDeleteDirectory(WorkingDirectory);
            }
        }
    }
}
