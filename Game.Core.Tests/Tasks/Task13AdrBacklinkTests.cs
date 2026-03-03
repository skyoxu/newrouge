using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task13AdrBacklinkTests
{
    private const int TaskId = 13;
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task13AdrBacklinkTests.cs";
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";

    private static readonly string[] TaskViewPaths =
    {
        ".taskmaster/tasks/tasks_back.json",
        ".taskmaster/tasks/tasks_gameplay.json",
    };

    // ACC:T13.4
    [Fact]
    public void ShouldIncludeAdr0021AndAdr0022InTask13AdrRefs_WhenLoadingTaskViews()
    {
        var taskViews = LoadTask13Views();

        taskViews.Should().HaveCount(2);

        foreach (var task in taskViews)
        {
            var adrRefs = EnumerateStringArray(task, "adr_refs")
                .ToArray();
            adrRefs.Should().Contain("ADR-0021");
            adrRefs.Should().Contain("ADR-0022");

            var testRefs = EnumerateStringArray(task, "test_refs").ToArray();
            testRefs.Should().Contain(ThisTestRef, "Task 13 should backlink this governance test in test_refs.");
        }
    }

    [Fact]
    public void ShouldIncludeAdr0021AndAdr0022InOverlayAcceptanceChecklist_WhenTask13RequiresAdrBacklinks()
    {
        var checklistPath = Path.Combine(FindRepoRoot(), OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(checklistPath).Should().BeTrue("Task 13 evidence must include an overlay acceptance checklist.");

        var checklistText = File.ReadAllText(checklistPath);

        checklistText.Should().Contain("ADR-0021",
            "Task 13 acceptance requires explicit ADR-0021 backlink evidence in the checklist.");
        checklistText.Should().Contain("ADR-0022",
            "Task 13 acceptance requires explicit ADR-0022 backlink evidence in the checklist.");
    }

    [Fact]
    public void ShouldUseRepoRelativeRefs_WhenParsingTask13AcceptanceItems()
    {
        var taskViews = LoadTask13Views();

        foreach (var task in taskViews)
        {
            var acceptanceItems = EnumerateStringArray(task, "acceptance").ToArray();
            acceptanceItems.Should().NotBeEmpty();
            foreach (var item in acceptanceItems)
            {
                var refs = ParseRefs(item).ToArray();
                refs.Should().NotBeEmpty("each acceptance item should include Refs for evidence traceability.");
                refs.Should().OnlyContain(path => !Path.IsPathRooted(path),
                    "acceptance Refs entries must stay repository-relative.");
            }
        }
    }

    private static IEnumerable<string> ParseRefs(string acceptanceItem)
    {
        var refsIndex = acceptanceItem.IndexOf("Refs:", StringComparison.OrdinalIgnoreCase);
        refsIndex.Should().BeGreaterOrEqualTo(0, "acceptance entries must contain a Refs section.");

        var refsText = acceptanceItem[(refsIndex + "Refs:".Length)..];
        var tokens = refsText
            .Replace(',', ' ')
            .Split(' ', StringSplitOptions.RemoveEmptyEntries)
            .Select(token => token.Trim());

        foreach (var token in tokens)
        {
            if (token.Length > 0)
            {
                yield return token;
            }
        }
    }

    private static IReadOnlyList<JsonElement> LoadTask13Views()
    {
        var results = new List<JsonElement>(TaskViewPaths.Length);
        foreach (var relativePath in TaskViewPaths)
        {
            results.Add(LoadTaskById(relativePath, TaskId));
        }

        return results;
    }

    private static JsonElement LoadTaskById(string repoRelativePath, int taskId)
    {
        var absolutePath = Path.Combine(FindRepoRoot(), repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"expected repository file at {repoRelativePath}");

        using var doc = JsonDocument.Parse(File.ReadAllText(absolutePath));
        doc.RootElement.ValueKind.Should().Be(JsonValueKind.Array, $"{repoRelativePath} must be an array view file");

        foreach (var task in doc.RootElement.EnumerateArray())
        {
            if (!task.TryGetProperty("taskmaster_id", out var idElement))
            {
                continue;
            }

            if (idElement.ValueKind == JsonValueKind.Number && idElement.GetInt32() == taskId)
            {
                return task.Clone();
            }
        }

        throw new InvalidOperationException($"Task {taskId} was not found in {repoRelativePath}.");
    }

    private static IEnumerable<string> EnumerateStringArray(JsonElement item, string propertyName)
    {
        if (!item.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }

        foreach (var element in property.EnumerateArray())
        {
            var value = element.GetString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                yield return value!;
            }
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
}
