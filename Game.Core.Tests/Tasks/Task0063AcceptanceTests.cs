using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0063AcceptanceTests
{
    private const int TaskmasterId = 63;
    private const string MainMenuScriptPath = "Game.Godot/Scripts/UI/MainMenu.cs";
    private const string MainMenuScenePath = "Game.Godot/Scenes/UI/MainMenu.tscn";
    private const string GdUnitTestPath = "Tests.Godot/tests/UI/test_main_menu_continue_blocked_message.gd";
    private const string Task0063TestPath = "Game.Core.Tests/Tasks/Task0063AcceptanceTests.cs";
    private const string Task0014TestPath = "Tests.Godot/tests/Tasks/test_task0014_acceptance.gd";

    // ACC:T63.1
    [Fact]
    [Trait("acceptance", "ACC:T63.1")]
    public void ShouldWireVisibleBlockedReasonsToRealMainMenuImplementation()
    {
        var repoRoot = ResolveRepoRoot();
        var script = ReadRepoFile(repoRoot, MainMenuScriptPath);
        var scene = ReadRepoFile(repoRoot, MainMenuScenePath);
        var gdunit = ReadRepoFile(repoRoot, GdUnitTestPath);

        scene.Should().Contain("ContinueBlockedDialog");
        scene.Should().Contain("MessageLabel");
        script.Should().Contain("ShowContinueBlockedState");
        script.Should().Contain("BuildContinueBlockedMessage");
        script.Should().Contain("missing_save");
        script.Should().Contain("invalid_integrity");
        script.Should().Contain("migration_failed");
        script.Should().Contain("RunContinueBlocked");
        gdunit.Should().Contain("test_continue_blocked_message_names_reason_for_missing_invalid_and_migration_failures");
        gdunit.Should().Contain("\"missing\"");
        gdunit.Should().Contain("\"invalid_integrity\"");
        gdunit.Should().Contain("\"migration_failure\"");
    }

    // ACC:T63.3
    [Fact]
    [Trait("acceptance", "ACC:T63.3")]
    public void ShouldStateSupportedRecoveryBoundaryInRealMainMenuAndSceneTest()
    {
        var repoRoot = ResolveRepoRoot();
        var script = ReadRepoFile(repoRoot, MainMenuScriptPath);
        var gdunit = ReadRepoFile(repoRoot, GdUnitTestPath);

        script.Should().Contain("Start a new run or return to the menu");
        script.Should().Contain("mid-combat resume is not supported");
        gdunit.Should().Contain("test_migration_failure_message_states_supported_recovery_boundary");
        gdunit.Should().Contain("start a new run");
        gdunit.Should().Contain("return to the menu");
        gdunit.Should().Contain("mid-combat resume is not supported");
    }

    // ACC:T63.4
    [Fact]
    [Trait("acceptance", "ACC:T63.4")]
    public void ShouldKeepContinueGateAndOverwriteConfirmationWiredInRealMainMenu()
    {
        var repoRoot = ResolveRepoRoot();
        var script = ReadRepoFile(repoRoot, MainMenuScriptPath);
        var scene = ReadRepoFile(repoRoot, MainMenuScenePath);
        var task14Gdunit = ReadRepoFile(repoRoot, Task0014TestPath);

        script.Should().Contain("RefreshContinueAvailability");
        script.Should().Contain("HasValidAutosave");
        script.Should().Contain("EvaluateContinueLoad");
        script.Should().Contain("OverwriteConfirmDialog");
        script.Should().Contain("PopupCentered");
        scene.Should().Contain("OverwriteConfirmDialog");
        task14Gdunit.Should().Contain("test_main_menu_initializes_continue_and_new_run_from_real_autosave_file");
        task14Gdunit.Should().Contain("OverwriteConfirmDialog");
    }

    // ACC:T63.5
    [Fact]
    [Trait("acceptance", "ACC:T63.5")]
    public void ShouldKeepBlockedContinueOnMainMenuUntilRealRecoveryAction()
    {
        var repoRoot = ResolveRepoRoot();
        var script = ReadRepoFile(repoRoot, MainMenuScriptPath);
        var scene = ReadRepoFile(repoRoot, MainMenuScenePath);
        var gdunit = ReadRepoFile(repoRoot, GdUnitTestPath);

        script.Should().Contain("if (!validation.ContinueAllowed)");
        script.Should().Contain("return;");
        script.Should().Contain("Publish(EventTypes.RunResumed");
        script.Should().Contain("OnContinueBlockedNewRunPressed");
        script.Should().Contain("StartNewRun();");
        script.Should().Contain("OnContinueBlockedDismissed");
        script.Should().Contain("ShowMenu();");
        scene.Should().Contain("BtnNewRun");
        scene.Should().Contain("BtnCancel");
        scene.Should().Contain("BtnReturnToMenu");
        gdunit.Should().Contain("test_continue_refuses_resume_until_player_selects_recovery_action");
        gdunit.Should().Contain("test_continue_blocked_state_exposes_recovery_actions_without_dismissing_feedback");
        gdunit.Should().Contain("core.run.resumed");
        gdunit.Should().Contain("core.run.started");
    }

    // ACC:T63.6
    [Fact]
    [Trait("acceptance", "ACC:T63.6")]
    public void ShouldResolveTaskRefsAndWindowsSmokeEvidenceForBlockedContinue()
    {
        var repoRoot = ResolveRepoRoot();
        var gameplayTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var testRefs = ReadStringArray(gameplayTask, "test_refs");
        var gdunit = ReadRepoFile(repoRoot, GdUnitTestPath);

        testRefs.Should().Contain(GdUnitTestPath);
        testRefs.Should().Contain(Task0063TestPath);
        foreach (var testRef in testRefs)
        {
            File.Exists(ResolveRepoPath(repoRoot, testRef)).Should().BeTrue(
                "task test_ref must resolve to a concrete file: {0}",
                testRef);
        }

        gdunit.Should().Contain("test_windows_smoke_surfaces_missing_and_invalid_save_blocked_attempts_to_player");
        gdunit.Should().Contain("\"missing\"");
        gdunit.Should().Contain("\"invalid_integrity\"");
    }

    private static string ReadRepoFile(string repoRoot, string relativePath)
    {
        var path = ResolveRepoPath(repoRoot, relativePath);
        File.Exists(path).Should().BeTrue("required Task 63 evidence file must exist: {0}", relativePath);
        return File.ReadAllText(path);
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        File.Exists(taskFilePath).Should().BeTrue("task metadata file must exist: {0}", taskFilePath);

        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var matched = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var taskmasterNode)
                && taskmasterNode.ValueKind == JsonValueKind.Number
                && taskmasterNode.GetInt32() == taskmasterId);

        matched.ValueKind.Should().NotBe(
            JsonValueKind.Undefined,
            "taskmaster_id={0} should exist in {1}",
            taskmasterId,
            taskFilePath);
        return matched.Clone();
    }

    private static string[] ReadStringArray(JsonElement taskNode, string propertyName)
    {
        taskNode.TryGetProperty(propertyName, out var property).Should().BeTrue(
            "property {0} should exist in task metadata",
            propertyName);
        property.ValueKind.Should().Be(JsonValueKind.Array);

        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value!)
            .ToArray();
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private static string ResolveRepoPath(string repoRoot, string relativePath)
    {
        return Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
    }
}
