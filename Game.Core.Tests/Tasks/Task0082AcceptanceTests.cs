using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0082AcceptanceTests
{
    private const int TaskmasterId = 82;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0082AcceptanceTests.cs";
    private const string UiBindingsRef = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd";
    private const string FeedbackLogRef = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd";
    private const string WorkflowEvidenceRef = "Game.Core.Tests/Tasks/Task0084AcceptanceTests.cs";

    // ACC:T82.1
    [Fact]
    [Trait("acceptance", "ACC:T82.1")]
    public void ShouldReferenceHudTotalDeckCounterEvidence_WhenValidatingAcceptanceLine1()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 0, UiBindingsRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 0, UiBindingsRef, ThisTestRef);

        var uiBindings = ReadRepositoryText(UiBindingsRef);
        uiBindings.Should().Contain("\"HUD/DrawPileValue\"");
        uiBindings.Should().Contain("\"HUD/DiscardPileValue\"");
        uiBindings.Should().Contain("GetDiscardPileCountForTest");
    }

    // ACC:T82.2
    [Fact]
    [Trait("acceptance", "ACC:T82.2")]
    public void ShouldReferencePileInvariantEvidence_WhenValidatingAcceptanceLine2()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 1, UiBindingsRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 1, UiBindingsRef, ThisTestRef);

        var deckService = new DeckService();
        var initialState = new DeckState(
            DrawPile: new[] { "d-3", "d-1", "d-2" },
            Hand: new[] { "h-1" },
            DiscardPile: new[] { "x-2", "x-1" },
            ExhaustPile: Array.Empty<string>(),
            RetainedInstanceIds: new HashSet<string>(StringComparer.Ordinal),
            HandLimit: 10);

        var afterDraw = deckService.Draw(initialState, 2);
        var afterDiscard = deckService.Discard(afterDraw, new[] { "d-3" });
        var afterEndTurn = deckService.EndOfTurn(afterDiscard);

        var initialTotal = CountDeckTotal(initialState);
        CountDeckTotal(afterDraw).Should().Be(initialTotal);
        CountDeckTotal(afterDiscard).Should().Be(initialTotal);
        CountDeckTotal(afterEndTurn).Should().Be(initialTotal);
    }

    // ACC:T82.3
    [Fact]
    [Trait("acceptance", "ACC:T82.3")]
    public void ShouldReferenceVisibleMismatchFallbackEvidence_WhenValidatingAcceptanceLine3()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 2, FeedbackLogRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 2, FeedbackLogRef, ThisTestRef);

        var feedbackLogTests = ReadRepositoryText(FeedbackLogRef);
        feedbackLogTests.Should().Contain("latest_feedback.find(\"refused\") >= 0");
        feedbackLogTests.Should().Contain("latest_feedback.find(\"That action is invalid\") >= 0");

        var combatSceneSource = ReadRepositoryText("Game.Godot/Scripts/UI/CombatScene.cs");
        combatSceneSource.Should().Contain("AppendCommandFeedback(\"end_turn\", accepted: false, refusalReasonKey: \"combat.invalid_action\")");
        combatSceneSource.Should().Contain("AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: \"combat.feedback.refusal_reason.missing_card_definition\")");
    }

    // ACC:T82.4
    [Fact]
    [Trait("acceptance", "ACC:T82.4")]
    public void ShouldKeepScopeOnSharedDeckServicePath_WhenValidatingAcceptanceLine4()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 3, UiBindingsRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 3, UiBindingsRef, ThisTestRef);

        var combatSceneSource = ReadRepositoryText("Game.Godot/Scripts/UI/CombatScene.cs");
        combatSceneSource.Should().Contain("_combatService.PlayCard(");
        combatSceneSource.Should().Contain("_combatService.ResolveEndTurnProgression(");
        combatSceneSource.Should().NotContain("SceneLocalDeckRuntime");
    }

    // ACC:T82.5
    [Fact]
    [Trait("acceptance", "ACC:T82.5")]
    public void ShouldRequireWorkflowSelectionEvidenceBeforeImplementationEvidence_WhenValidatingAcceptanceLine5()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 4, WorkflowEvidenceRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 4, WorkflowEvidenceRef, ThisTestRef);
    }

    // ACC:T82.6
    [Fact]
    [Trait("acceptance", "ACC:T82.6")]
    public void ShouldRequireUiAndStateTestsForTransitionInvariant_WhenValidatingAcceptanceLine6()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 5, UiBindingsRef, FeedbackLogRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 5, UiBindingsRef, FeedbackLogRef, ThisTestRef);

        var uiBindings = ReadRepositoryText(UiBindingsRef);
        uiBindings.Should().Contain("GetDiscardPileCountForTest");
        uiBindings.Should().Contain("runtime_discard_count");

        var feedbackLogTests = ReadRepositoryText(FeedbackLogRef);
        feedbackLogTests.Should().Contain("GetFeedbackHistoryForTest");
        feedbackLogTests.Should().Contain("feedback_history.size()");
    }

    // ACC:T82.7
    [Fact]
    [Trait("acceptance", "ACC:T82.7")]
    public void ShouldRequireT80T81EvidenceDependencyBeforeClaimingT82Delivery_WhenValidatingAcceptanceLine7()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 6, UiBindingsRef, WorkflowEvidenceRef, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 6, UiBindingsRef, WorkflowEvidenceRef, ThisTestRef);

        var uiBindings = ReadRepositoryText(UiBindingsRef);
        uiBindings.Should().Contain("ACC:T80.7");
        uiBindings.Should().Contain("ACC:T81.6");
    }

    private static void AssertAcceptanceRefsContain(string taskFilePath, int index, params string[] expectedRefs)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        acceptance.Length.Should().BeGreaterThan(index, $"acceptance[{index}] must exist in {taskFilePath}");
        var refs = ParseRefs(acceptance[index]);
        foreach (var expected in expectedRefs)
        {
            refs.Should().Contain(expected, $"{taskFilePath} acceptance[{index}] should include {expected}");
        }

        var testRefs = ReadStringArray(task, "test_refs");
        testRefs.Should().Contain(ThisTestRef, $"{taskFilePath} test_refs should include this task acceptance test file");
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return property.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string[] ParseRefs(string acceptanceLine)
    {
        const string marker = "Refs:";
        var markerIndex = acceptanceLine.IndexOf(marker, StringComparison.Ordinal);
        if (markerIndex < 0)
        {
            return Array.Empty<string>();
        }

        var refsPart = acceptanceLine[(markerIndex + marker.Length)..].Trim();
        if (refsPart.Length == 0)
        {
            return Array.Empty<string>();
        }

        return refsPart
            .Split(new[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    }

    private static int CountDeckTotal(DeckState state)
    {
        return state.DrawPile.Count + state.Hand.Count + state.DiscardPile.Count;
    }

    private static string ReadRepositoryText(string relativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required file is missing: {relativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            var candidate = Path.Combine(current, "newrouge.sln");
            if (File.Exists(candidate))
            {
                return current;
            }

            var parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root containing newrouge.sln.");
    }
}
