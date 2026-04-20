using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0059AcceptanceTests
{
    private const string TaskRefPath = "Game.Core.Tests/Tasks/Task0059AcceptanceTests.cs";
    private const string IntegrationRefPath = "Tests.Godot/tests/Integration/test_m1_run_entry_vertical_slice.gd";
    private const string MainMenuRefPath = "Tests.Godot/tests/Tasks/test_task0014_acceptance.gd";

    // ACC:T59.1
    [Fact]
    public void ShouldIncludeTask0059TestRef_WhenReadingTask59Definition()
    {
        using var task59 = ReadTask59Definition();
        var testRefs = task59.RootElement.GetProperty("test_refs").EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();

        testRefs.Should().Contain(TaskRefPath);
        testRefs.Should().Contain(IntegrationRefPath);
        testRefs.Should().Contain(MainMenuRefPath);
    }

    // ACC:T59.2
    [Fact]
    public void ShouldBindAccT59_2ToIntegrationAnchor_WhenReadingAcceptanceSemantics()
    {
        using var task59 = ReadTask59Definition();
        var acceptanceLine = task59.RootElement.GetProperty("acceptance").EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Single(text => text.Contains("ACC:T59.2", StringComparison.Ordinal));

        acceptanceLine.Should().Contain("selecting a difficulty without confirmation must keep the current route on DifficultySelect");
        acceptanceLine.Should().Contain($"{IntegrationRefPath} (anchor: ACC:T59.2)");
    }

    // ACC:T59.3
    [Fact]
    public void ShouldBindAccT59_3ToIntegrationAnchor_WhenReadingAcceptanceSemantics()
    {
        using var task59 = ReadTask59Definition();
        var acceptanceLine = task59.RootElement.GetProperty("acceptance").EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Single(text => text.Contains("ACC:T59.3", StringComparison.Ordinal));

        acceptanceLine.Should().Contain("changing character selection without confirmation must keep the current route on CharacterSelect");
        acceptanceLine.Should().Contain($"{IntegrationRefPath} (anchor: ACC:T59.3)");
    }

    // ACC:T59.4
    [Fact]
    public void ShouldBindAccT59_4ToMainMenuAndIntegrationAnchors_WhenReadingAcceptanceSemantics()
    {
        using var task59 = ReadTask59Definition();
        var acceptanceLine = task59.RootElement.GetProperty("acceptance").EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Single(text => text.Contains("ACC:T59.4", StringComparison.Ordinal));

        acceptanceLine.Should().Contain("cancel must keep the current scene on MainMenu");
        acceptanceLine.Should().Contain("confirm must enter the M1 entry chain at DifficultySelect");
        acceptanceLine.Should().Contain($"{MainMenuRefPath} (anchor: ACC:T59.4)");
        acceptanceLine.Should().Contain($"{IntegrationRefPath} (anchor: ACC:T59.4)");
    }

    // ACC:T59.5
    [Fact]
    public void ShouldBindAccT59_5ToFinalSceneAndRouteOrder_WhenReadingAcceptanceSemantics()
    {
        using var task59 = ReadTask59Definition();
        var acceptanceLine = task59.RootElement.GetProperty("acceptance").EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .Single(text => text.Contains("ACC:T59.5", StringComparison.Ordinal));

        acceptanceLine.Should().Contain("route-history order MainMenu -> DifficultySelect -> CharacterSelect -> Map");
        acceptanceLine.Should().Contain("final current scene = Map");
        acceptanceLine.Should().Contain($"{IntegrationRefPath} (anchor: ACC:T59.5)");
    }

    private static JsonDocument ReadTask59Definition()
    {
        var repoRoot = FindRepositoryRoot();
        var tasksPath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        var tasksJson = JsonDocument.Parse(File.ReadAllText(tasksPath));
        var taskElement = tasksJson.RootElement
            .EnumerateArray()
            .Single(item =>
                item.TryGetProperty("taskmaster_id", out var idProp)
                && idProp.ValueKind == JsonValueKind.Number
                && idProp.GetInt32() == 59);

        return JsonDocument.Parse(taskElement.GetRawText());
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
}
