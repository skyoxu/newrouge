using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks
{
    public sealed class Task32AcceptanceTests
    {
        private const int TaskId = 54;
        private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
        private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
        private static readonly string[] RequiredTaskRefs =
        {
            "Tests.Godot/tests/ci/test_gdunit_suite_wiring.gd",
            "Game.Core.Tests/Tasks/Task32AcceptanceTests.cs",
        };

        // ACC:T54.11
        [Fact]
        public void ShouldContainRequiredTaskRefs_WhenLoadingTask54Metadata()
        {
            var taskBack = LoadViewTaskById(TasksBackPath, TaskId);
            var taskGameplay = LoadViewTaskById(TasksGameplayPath, TaskId);

            var testRefsBack = taskBack.GetProperty("test_refs").EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).ToArray();
            var testRefsGameplay = taskGameplay.GetProperty("test_refs").EnumerateArray().Select(x => x.GetString()).Where(x => !string.IsNullOrWhiteSpace(x)).ToArray();

            testRefsBack.Should().Contain(RequiredTaskRefs[0]);
            testRefsBack.Should().Contain(RequiredTaskRefs[1]);
            testRefsGameplay.Should().Contain(RequiredTaskRefs[0]);
            testRefsGameplay.Should().Contain(RequiredTaskRefs[1]);
        }

        [Theory]
        [InlineData("adapters", "hard")]
        [InlineData("security", "hard")]
        [InlineData("integration", "soft")]
        [InlineData("ui", "soft")]
        [InlineData("unknown", "soft")]
        public void ShouldMapGdUnitSuitesToExpectedGateMode_WhenComputingSuitePolicy(string suite, string expected)
        {
            var gateMode = GetGateModeForSuite(suite);

            gateMode.Should().Be(expected);
        }

        [Fact]
        public void ShouldNormalizeRepoRelativeRefs_WhenBuildingAcceptanceRefSet()
        {
            const string rawRefs = "Tests.Godot/tests/Integration/test_quality_gates_gdunit_suite_wiring.gd, Game.Core.Tests/Tasks/Task32AcceptanceTests.cs";
            var normalized = NormalizeRefs(rawRefs);

            normalized.Should().HaveCount(2);
            normalized.Should().OnlyContain(path => !Path.IsPathRooted(path));
            normalized.Should().Contain("Tests.Godot/tests/Integration/test_quality_gates_gdunit_suite_wiring.gd");
            normalized.Should().Contain("Game.Core.Tests/Tasks/Task32AcceptanceTests.cs");
        }

        private static string GetGateModeForSuite(string suiteName)
        {
            var normalized = (suiteName ?? string.Empty).Trim().ToLowerInvariant();
            return normalized is "adapters" or "security" ? "hard" : "soft";
        }

        private static IReadOnlyList<string> NormalizeRefs(string rawRefs)
        {
            var tokens = (rawRefs ?? string.Empty)
                .Replace(',', ' ')
                .Split(' ', StringSplitOptions.RemoveEmptyEntries)
                .Select(token => token.Trim())
                .Where(token => token.Length > 0)
                .Distinct(StringComparer.Ordinal)
                .ToArray();

            return tokens;
        }

        private static JsonElement LoadViewTaskById(string repoRelativePath, int taskId)
        {
            var repoRoot = FindRepoRoot();
            var tasksPath = Path.Combine(repoRoot, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));

            using var doc = JsonDocument.Parse(File.ReadAllText(tasksPath));
            var tasks = doc.RootElement;
            tasks.ValueKind.Should().Be(JsonValueKind.Array, $"{repoRelativePath} must be an array view file");
            foreach (var task in tasks.EnumerateArray())
            {
                if (!task.TryGetProperty("taskmaster_id", out var idElement))
                {
                    continue;
                }

                if (idElement.GetInt32() == taskId)
                {
                    return task.Clone();
                }
            }

            throw new InvalidOperationException($"Task {taskId} was not found in {repoRelativePath}.");
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
    }
}
