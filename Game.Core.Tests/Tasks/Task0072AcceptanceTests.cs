using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0072AcceptanceTests
{
    private const int TaskmasterId = 72;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string CombatScenePath = "Game.Godot/Scripts/UI/CombatScene.cs";
    private const string UiBindingsPath = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_ui_bindings.gd";
    private const string FeedbackPath = "Tests.Godot/tests/Scenes/Combat/test_combat_scene_feedback_log.gd";
    private const string IntegrationPath = "Tests.Godot/tests/Integration/test_m1_visible_text_flow.gd";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0072AcceptanceTests.cs";
    private const string Chapter6SummaryRelPath = "logs/ci/2026-04-27/single-task-chapter6-task-72/summary.json";
    private const string PipelineLatestRelPath = "logs/ci/2026-04-27/sc-review-pipeline-task-72/latest.json";

    // ACC:T72.2 / ACC:T72.8 governance: semantic anchors must point to behavior tests.
    [Fact]
    public void ShouldBindSemanticAcceptanceToBehaviorTests_InsteadOfRefsOnlyChecks()
    {
        foreach (var taskFile in new[] { TasksBackPath, TasksGameplayPath })
        {
            var task = ReadTaskNode(taskFile, TaskmasterId);
            var acceptance = ReadAcceptance(task);
            acceptance.Length.Should().BeGreaterThanOrEqualTo(10);

            var refsT722 = ParseRefs(acceptance[1]);
            refsT722.Should().Contain(UiBindingsPath);
            refsT722.Should().Contain(ThisTaskTestRef);

            var refsT723 = ParseRefs(acceptance[2]);
            refsT723.Should().Contain(FeedbackPath);

            var refsT725 = ParseRefs(acceptance[4]);
            refsT725.Should().Contain(IntegrationPath);

            var refsT728 = ParseRefs(acceptance[7]);
            refsT728.Should().Contain(UiBindingsPath);
        }
    }

    // ACC:T72.8 implementation contract: no second card-definition path family.
    [Fact]
    public void ShouldKeepCombatSceneOnExistingCardDefinitionDataFamily_WithoutFallbackModel()
    {
        var source = ReadRepositoryText(CombatScenePath);
        source.Should().Contain("CardDefinitionCandidatePaths", "card-definition loading must remain data-driven.");
        source.Should().NotContain("RegisterFallbackCardDefinitions", "parallel fallback card-definition source is forbidden.");
        source.Should().NotContain("string.Equals(id, \"card.warrior.power_through\"", "exhaust routing must not be hardcoded by card id.");
        source.Should().Contain("TryLoadCardDefinitionsFromData", "runtime definitions must still come from existing data files.");
    }

    // ACC:T72.9 governance: workflow-selection record must exist before implementation evidence judgement.
    [Fact]
    public void ShouldRequireWorkflowSelectionEvidenceBeforeImplementationEvidence()
    {
        var chapter6SummaryPath = Path.Combine(FindRepositoryRoot(), Chapter6SummaryRelPath.Replace('/', Path.DirectorySeparatorChar));
        var pipelineLatestPath = Path.Combine(FindRepositoryRoot(), PipelineLatestRelPath.Replace('/', Path.DirectorySeparatorChar));

        File.Exists(chapter6SummaryPath).Should().BeTrue($"workflow-selection summary must exist: {chapter6SummaryPath}");
        File.Exists(pipelineLatestPath).Should().BeTrue($"pipeline latest pointer must exist: {pipelineLatestPath}");

        using var chapter6Doc = JsonDocument.Parse(File.ReadAllText(chapter6SummaryPath));
        using var pipelineLatestDoc = JsonDocument.Parse(File.ReadAllText(pipelineLatestPath));

        var chapter6 = chapter6Doc.RootElement;
        var latest = pipelineLatestDoc.RootElement;

        chapter6.GetProperty("cmd").GetString().Should().Be("run-single-task-chapter6");
        chapter6.GetProperty("task_id").GetString().Should().Be("72");
        var planned = chapter6.GetProperty("planned_steps").EnumerateArray().Select(x => x.GetString() ?? string.Empty).ToArray();
        planned.Should().Contain("resume-task");
        planned.Should().Contain("chapter6-route-initial");

        latest.GetProperty("task_id").GetString().Should().Be("72");
        latest.GetProperty("status").GetString().Should().Be("ok");
        latest.GetProperty("summary_path").GetString().Should().NotBeNullOrWhiteSpace();

        var workflowMtime = File.GetLastWriteTimeUtc(chapter6SummaryPath);
        var latestMtime = File.GetLastWriteTimeUtc(pipelineLatestPath);
        workflowMtime.Should().BeOnOrBefore(latestMtime, "workflow-selection record must be available before evaluating implementation evidence.");

        var rejectedWhenNotSelected = CanClaimImplementationDelivery(
            chapter6SummaryPath: Path.Combine(FindRepositoryRoot(), "logs/ci/2099-01-01/single-task-chapter6-task-72/summary.json"),
            pipelineLatestPath: pipelineLatestPath);
        rejectedWhenNotSelected.Should().BeFalse("when workflow-selection evidence is missing, implementation must not be claimable as delivered.");

        var acceptedWhenSelected = CanClaimImplementationDelivery(
            chapter6SummaryPath: chapter6SummaryPath,
            pipelineLatestPath: pipelineLatestPath);
        acceptedWhenSelected.Should().BeTrue("once workflow-selection evidence exists, implementation evidence can be evaluated.");

        foreach (var taskFile in new[] { TasksBackPath, TasksGameplayPath })
        {
            var task = ReadTaskNode(taskFile, TaskmasterId);
            var acceptance = ReadAcceptance(task);
            acceptance[9].Should().Contain("workflow selection evidence marks Task 72 as selected");
            var refsT7210 = ParseRefs(acceptance[9]);
            refsT7210.Should().Contain(ThisTaskTestRef);
        }
    }

    private static bool CanClaimImplementationDelivery(string chapter6SummaryPath, string pipelineLatestPath)
    {
        if (!File.Exists(chapter6SummaryPath) || !File.Exists(pipelineLatestPath))
        {
            return false;
        }

        using var chapter6Doc = JsonDocument.Parse(File.ReadAllText(chapter6SummaryPath));
        using var latestDoc = JsonDocument.Parse(File.ReadAllText(pipelineLatestPath));
        var chapter6 = chapter6Doc.RootElement;
        var latest = latestDoc.RootElement;

        if (!string.Equals(chapter6.GetProperty("cmd").GetString(), "run-single-task-chapter6", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(chapter6.GetProperty("task_id").GetString(), "72", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(latest.GetProperty("task_id").GetString(), "72", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(latest.GetProperty("status").GetString(), "ok", StringComparison.Ordinal))
        {
            return false;
        }

        var planned = chapter6.GetProperty("planned_steps").EnumerateArray().Select(x => x.GetString() ?? string.Empty).ToArray();
        return planned.Contains("resume-task", StringComparer.Ordinal)
            && planned.Contains("chapter6-route-initial", StringComparer.Ordinal);
    }

    private static string[] ReadAcceptance(JsonElement taskNode)
    {
        return taskNode.GetProperty("acceptance")
            .EnumerateArray()
            .Select(item => item.GetString() ?? string.Empty)
            .ToArray();
    }

    private static string[] ParseRefs(string acceptanceLine)
    {
        var refsIndex = acceptanceLine.IndexOf("Refs:", StringComparison.Ordinal);
        refsIndex.Should().BeGreaterOrEqualTo(0, "acceptance line must contain Refs:");
        return acceptanceLine[(refsIndex + "Refs:".Length)..]
            .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string ReadRepositoryText(string relativePath)
    {
        var absolute = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolute).Should().BeTrue($"required file must exist: {relativePath}");
        return File.ReadAllText(absolute);
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

        throw new DirectoryNotFoundException("Unable to locate repository root containing NewRouge.sln.");
    }
}
